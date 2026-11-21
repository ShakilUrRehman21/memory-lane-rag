"""Text embeddings with graceful fallbacks.

Order for EMBEDDINGS=auto:
  1. fastembed (local ONNX model, e.g. bge-small-en-v1.5; free, private, good quality)
  2. Gemini / OpenAI embedding APIs if a key is configured
  3. A local lexical-semantic hashing embedder (no downloads, always available)

Every stored vector records the provider that made it, so switching providers
triggers a transparent re-index (see storage.vectors.ensure_fresh).
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from functools import lru_cache
from typing import List, Optional

import numpy as np

from app.core.config import settings

log = logging.getLogger("memory_lane.embeddings")

STOPWORDS = set(
    """a an the and or but if then so of to in on at by for with about against between into through during before after
    above below from up down out off over under again further once here there when where why how all any both each few more
    most other some such no nor not only own same than too very can will just should now i me my myself we our ours you your
    he him his she her it its they them their what which who whom this that these those am is are was were be been being have
    has had having do does did doing would could also really much many lot get got go going thing things think thought""".split()
)

# Small concept lexicon: lets the offline embedder relate words that never co-occur literally.
CONCEPTS = {
    "ai": ["ai", "artificial", "intelligence", "machine", "learning", "ml", "neural", "llm", "llms", "transformer",
           "transformers", "gpt", "deep", "model", "models", "pytorch", "tensorflow", "rag", "agents", "agent"],
    "career": ["career", "job", "role", "work", "promotion", "engineer", "manager", "founder", "hire", "hired",
               "position", "profession", "company", "startup", "employer", "salary"],
    "goal": ["goal", "goals", "aim", "ambition", "aspire", "want", "plan", "dream", "target", "hope", "intend"],
    "research": ["research", "paper", "papers", "publish", "academic", "phd", "thesis", "experiment", "science",
                 "conference", "study"],
    "code": ["code", "coding", "programming", "python", "java", "javascript", "typescript", "rust", "go", "c++",
             "software", "backend", "frontend", "developer"],
    "health": ["health", "exercise", "run", "running", "gym", "sleep", "diet", "doctor", "fitness", "yoga",
               "meditation", "workout", "body", "sick", "illness"],
    "emotion": ["happy", "sad", "anxious", "anxiety", "stress", "stressed", "calm", "joy", "fear", "angry", "lonely",
                "grateful", "excited", "worried", "proud", "feel", "feeling", "mood", "burnout", "tired"],
    "family": ["family", "mother", "father", "mom", "dad", "sister", "brother", "parents", "kids", "child", "children",
               "wife", "husband", "partner", "friend", "friends", "relationship", "love"],
    "money": ["money", "finance", "salary", "invest", "investing", "savings", "budget", "debt", "revenue", "funding",
              "income", "spend"],
    "learning": ["learn", "learning", "study", "course", "book", "books", "read", "reading", "skill", "skills",
                 "practice", "teach"],
    "travel": ["travel", "trip", "flight", "city", "country", "moved", "move", "abroad", "visit", "vacation"],
    "change": ["change", "changed", "shift", "shifted", "pivot", "switch", "switched", "stopped", "started",
               "transition", "evolve", "evolved", "moved", "abandon", "quit"],
    "negative": ["not", "never", "don't", "dont", "skeptical", "doubt", "hate", "dislike", "waste", "overhyped",
                 "impractical", "irrelevant", "useless"],
}
_WORD2CONCEPT = {w: c for c, ws in CONCEPTS.items() for w in ws}
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-']*")


def _stem(w: str) -> str:
    for suf in ("ization", "ations", "ation", "ments", "ment", "ness", "ings", "ing", "ies", "ied", "ers", "er",
                "ed", "ly", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _h(token: str, dim: int) -> tuple[int, float]:
    d = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    v = int.from_bytes(d, "little")
    return v % dim, (1.0 if (v >> 63) & 1 else -1.0)


class LocalEmbedder:
    """Signed feature hashing over stems, bigrams, char n-grams and concepts. Deterministic, no downloads."""

    name = "local-hash-v2"
    dim = 768

    def embed(self, texts: List[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            words = _TOKEN_RE.findall(text.lower())
            content = [w for w in words if w not in STOPWORDS or w in _WORD2CONCEPT]
            stems = [_stem(w.strip(".'-")) for w in content]
            vec = out[row]
            for s in stems:
                i, sign = _h("w:" + s, self.dim)
                vec[i] += 1.6 * sign
                padded = f"<{s}>"
                for k in range(len(padded) - 2):
                    j, sg = _h("c:" + padded[k:k + 3], self.dim)
                    vec[j] += 0.25 * sg
            for a, b in zip(stems, stems[1:]):
                i, sign = _h(f"b:{a}_{b}", self.dim)
                vec[i] += 0.8 * sign
            for w in words:
                c = _WORD2CONCEPT.get(w)
                if c:
                    i, sign = _h("k:" + c, self.dim)
                    vec[i] += 1.4 * sign
            # sublinear damping
            np.copysign(np.log1p(np.abs(vec)), vec, out=vec)
            n = np.linalg.norm(vec)
            if n > 0:
                vec /= n
        return out


def _model_source_reachable() -> bool:
    """Fail fast (instead of ~40 s of retries) when the model isn't cached and can't be downloaded."""
    if any(settings.MODEL_CACHE_DIR.glob(f"*{settings.FASTEMBED_MODEL.split('/')[-1]}*")):
        return True
    import httpx
    try:
        return httpx.get(f"https://huggingface.co/api/models/{settings.FASTEMBED_MODEL}", timeout=5).status_code == 200
    except Exception:
        return False


class FastEmbedder:
    def __init__(self):
        from fastembed import TextEmbedding  # type: ignore

        if not _model_source_reachable():
            raise RuntimeError("model not cached and download sources unreachable")

        self.model = TextEmbedding(settings.FASTEMBED_MODEL, cache_dir=str(settings.MODEL_CACHE_DIR))
        self.name = f"fastembed:{settings.FASTEMBED_MODEL}"
        self.dim = len(next(iter(self.model.embed(["probe"]))))

    def embed(self, texts: List[str]) -> np.ndarray:
        arr = np.array(list(self.model.embed(texts, batch_size=32)), dtype=np.float32)
        return _normalize(arr)


class GeminiEmbedder:
    def __init__(self):
        import httpx

        self.client = httpx.Client(timeout=30)
        self.name = "gemini:text-embedding-004"
        self.dim = 768
        self.embed(["probe"])

    def embed(self, texts: List[str]) -> np.ndarray:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents"
               f"?key={settings.GEMINI_API_KEY}")
        vecs = []
        for i in range(0, len(texts), 90):
            batch = texts[i:i + 90]
            body = {"requests": [{"model": "models/text-embedding-004", "content": {"parts": [{"text": t[:8000]}]}}
                                 for t in batch]}
            r = self.client.post(url, json=body)
            r.raise_for_status()
            vecs += [e["values"] for e in r.json()["embeddings"]]
        return _normalize(np.array(vecs, dtype=np.float32))


class OpenAIEmbedder:
    def __init__(self):
        import httpx

        self.client = httpx.Client(timeout=30, headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"})
        self.name = "openai:text-embedding-3-small"
        self.dim = 1536
        self.embed(["probe"])

    def embed(self, texts: List[str]) -> np.ndarray:
        vecs = []
        for i in range(0, len(texts), 256):
            r = self.client.post(f"{settings.OPENAI_BASE_URL}/embeddings",
                                 json={"model": "text-embedding-3-small", "input": [t[:8000] for t in texts[i:i + 256]]})
            r.raise_for_status()
            vecs += [d["embedding"] for d in r.json()["data"]]
        return _normalize(np.array(vecs, dtype=np.float32))


def _normalize(arr: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(arr, axis=1, keepdims=True)
    n[n == 0] = 1
    return arr / n


_lock = threading.Lock()
_embedder = None
_status: dict = {"provider": None, "notes": []}


def get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder
    with _lock:
        if _embedder is not None:
            return _embedder
        choice = settings.EMBEDDINGS.lower()
        candidates = []
        if settings.TESTING:
            candidates = [("local", LocalEmbedder)]
        elif choice == "auto":
            candidates = [("fastembed", FastEmbedder)]
            if settings.GEMINI_API_KEY:
                candidates.append(("gemini", GeminiEmbedder))
            if settings.OPENAI_API_KEY:
                candidates.append(("openai", OpenAIEmbedder))
            candidates.append(("local", LocalEmbedder))
        else:
            mapping = {"fastembed": FastEmbedder, "gemini": GeminiEmbedder, "openai": OpenAIEmbedder,
                       "local": LocalEmbedder}
            candidates = [(choice, mapping.get(choice, LocalEmbedder)), ("local", LocalEmbedder)]
        for label, cls in candidates:
            try:
                _embedder = cls()
                _status["provider"] = _embedder.name
                log.info("Embeddings: using %s", _embedder.name)
                break
            except Exception as exc:  # pragma: no cover - depends on environment
                note = f"{label} unavailable: {exc.__class__.__name__}: {str(exc)[:160]}"
                _status["notes"].append(note)
                log.warning("Embeddings: %s", note)
        return _embedder


def embedding_status() -> dict:
    get_embedder()
    return dict(_status)


def embed_texts(texts: List[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, get_embedder().dim), dtype=np.float32)
    return get_embedder().embed(texts)


@lru_cache(maxsize=512)
def _cached_query(text: str) -> bytes:
    return embed_texts([text])[0].tobytes()


def embed_query(text: str) -> np.ndarray:
    # bge models benefit from a retrieval instruction on the query side
    prefix = "Represent this sentence for searching relevant passages: " if "bge" in get_embedder().name else ""
    return np.frombuffer(_cached_query(prefix + text), dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def provider_name() -> Optional[str]:
    return get_embedder().name
