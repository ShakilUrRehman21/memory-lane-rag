"""Chat-model adapters with token streaming. Providers: Gemini, OpenAI (or compatible), Ollama.

When no provider is configured or a call fails, callers fall back to the offline writer in
synthesis.offline, so the app always answers.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Dict, Iterator, List, Optional

import httpx

from app.core.config import settings

log = logging.getLogger("memory_lane.llm")

Message = Dict[str, str]  # {"role": "system"|"user"|"assistant", "content": str}


class LLMError(RuntimeError):
    pass


def active_provider() -> str:
    if settings.TESTING:
        return "offline"
    p = settings.LLM_PROVIDER.lower()
    if p != "auto":
        return p
    if settings.GEMINI_API_KEY:
        return "gemini"
    if settings.OPENAI_API_KEY:
        return "openai"
    if settings.OLLAMA_URL:
        return "ollama"
    return "offline"


def provider_label(p: Optional[str] = None) -> str:
    p = p or active_provider()
    return {
        "gemini": f"Gemini · {settings.GEMINI_MODEL}",
        "openai": f"OpenAI · {settings.OPENAI_MODEL}",
        "ollama": f"Ollama · {settings.OLLAMA_MODEL}",
    }.get(p, "Offline writer")


def _split_system(messages: List[Message]):
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    rest = [m for m in messages if m["role"] != "system"]
    return system, rest


# ---------------- Gemini ----------------
def _gemini_body(messages: List[Message], temperature: float, json_mode: bool) -> dict:
    system, rest = _split_system(messages)
    body = {
        "contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                     for m in rest],
        "generationConfig": {"temperature": temperature},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    return body


AISTUDIO = "https://generativelanguage.googleapis.com/v1beta/models"
VERTEX_EXPRESS = "https://aiplatform.googleapis.com/v1/publishers/google/models"
_gemini_base: Optional[str] = None  # remembered once one endpoint works


def _gemini_bases() -> List[str]:
    """Google keys come in two kinds: AI Studio keys (AIza…) and Vertex AI express keys (AQ.…)."""
    if settings.GEMINI_ENDPOINT:
        return [settings.GEMINI_ENDPOINT.rstrip("/")]
    if _gemini_base:
        return [_gemini_base]
    order = [VERTEX_EXPRESS, AISTUDIO] if settings.GEMINI_API_KEY.startswith("AQ.") else [AISTUDIO, VERTEX_EXPRESS]
    return order


RETRYABLE = {429, 500, 502, 503, 504}
_gemini_alternates: Optional[List[str]] = None


def _gemini_alternate_models(base: str) -> List[str]:
    """Other Flash models this key can use (fetched once), tried when the main model is overloaded."""
    global _gemini_alternates
    if _gemini_alternates is not None:
        return _gemini_alternates
    names: List[str] = []
    if settings.GEMINI_FALLBACK_MODELS:
        names = [m.strip() for m in settings.GEMINI_FALLBACK_MODELS.split(",") if m.strip()]
    else:
        try:
            with httpx.Client(timeout=10) as c:
                r = c.get(f"{base}?key={settings.GEMINI_API_KEY}&pageSize=200")
            if r.status_code == 200:
                for m in r.json().get("models", []):
                    name = m.get("name", "").split("/")[-1]
                    if ("generateContent" in m.get("supportedGenerationMethods", []) and "flash" in name
                            and not re.search(r"image|tts|audio|live|embed|thinking|exp", name)):
                        names.append(name)
                names.sort(reverse=True)
        except Exception:
            pass
    _gemini_alternates = [n for n in names if n != settings.GEMINI_MODEL][:3]
    return _gemini_alternates


def _gemini_call(messages, temperature, json_mode, stream: bool):
    """Try each endpoint; retry overloaded responses with backoff, then fall back to other Flash models.

    Returns an open (client, response) pair for streaming, or the parsed JSON for normal calls.
    """
    global _gemini_base
    last: Optional[LLMError] = None
    body = _gemini_body(messages, temperature, json_mode)
    for base in _gemini_bases():
        models = [settings.GEMINI_MODEL]
        tried_alternates = False
        i = 0
        while i < len(models):
            model = models[i]
            action = "streamGenerateContent?alt=sse&" if stream else "generateContent?"
            url = f"{base}/{model}:{action}key={settings.GEMINI_API_KEY}"
            for attempt in range(3):
                c = httpx.Client(timeout=settings.LLM_TIMEOUT)
                req = c.build_request("POST", url, json=body)
                r = c.send(req, stream=stream)
                if r.status_code < 400:
                    _gemini_base = base
                    if stream:
                        return c, r
                    data = r.json()
                    c.close()
                    return data
                detail = (r.read() if stream else r.content)[:300]
                r.close(); c.close()
                last = LLMError(f"Gemini HTTP {r.status_code} ({model}): {detail!r}")
                if r.status_code not in RETRYABLE:
                    break
                if attempt < 2:
                    log.info("Gemini %s busy (HTTP %s), retrying", model, r.status_code)
                    time.sleep(1.5 * (attempt + 1))
            code = int(str(last).split("HTTP ")[1][:3]) if last else 0
            if code in (401, 403) or (code == 400 and "API key" in str(last)):
                break  # wrong endpoint for this key: try the next base
            if not tried_alternates and (code in RETRYABLE or code == 404):
                models += _gemini_alternate_models(base)
                tried_alternates = True
            i += 1
        else:
            continue
    raise last or LLMError("Gemini unavailable")


def _gemini_stream(messages, temperature) -> Iterator[str]:
    c, r = _gemini_call(messages, temperature, False, stream=True)
    try:
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            try:
                data = json.loads(line[5:].strip())
                for part in data["candidates"][0]["content"].get("parts", []):
                    if part.get("text"):
                        yield part["text"]
            except (KeyError, IndexError, json.JSONDecodeError):
                continue
    finally:
        r.close()
        c.close()


def _gemini_complete(messages, temperature, json_mode) -> str:
    data = _gemini_call(messages, temperature, json_mode, stream=False)
    parts = data["candidates"][0]["content"].get("parts", [])
    return "".join(p.get("text", "") for p in parts)


# ---------------- OpenAI-compatible ----------------
def _openai_stream(messages, temperature) -> Iterator[str]:
    headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
    body = {"model": settings.OPENAI_MODEL, "messages": messages, "temperature": temperature, "stream": True}
    with httpx.Client(timeout=settings.LLM_TIMEOUT) as c:
        with c.stream("POST", f"{settings.OPENAI_BASE_URL}/chat/completions", json=body, headers=headers) as r:
            if r.status_code >= 400:
                raise LLMError(f"OpenAI HTTP {r.status_code}: {r.read()[:300]!r}")
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = json.loads(payload)["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
                except (KeyError, IndexError, json.JSONDecodeError):
                    continue


def _openai_complete(messages, temperature, json_mode) -> str:
    headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
    body = {"model": settings.OPENAI_MODEL, "messages": messages, "temperature": temperature}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    with httpx.Client(timeout=settings.LLM_TIMEOUT) as c:
        r = c.post(f"{settings.OPENAI_BASE_URL}/chat/completions", json=body, headers=headers)
        if r.status_code >= 400:
            raise LLMError(f"OpenAI HTTP {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]


# ---------------- Ollama ----------------
def _ollama_stream(messages, temperature) -> Iterator[str]:
    body = {"model": settings.OLLAMA_MODEL, "messages": messages, "stream": True,
            "options": {"temperature": temperature}}
    with httpx.Client(timeout=settings.LLM_TIMEOUT) as c:
        with c.stream("POST", f"{settings.OLLAMA_URL.rstrip('/')}/api/chat", json=body) as r:
            if r.status_code >= 400:
                raise LLMError(f"Ollama HTTP {r.status_code}")
            for line in r.iter_lines():
                if line.strip():
                    chunk = json.loads(line)
                    if chunk.get("message", {}).get("content"):
                        yield chunk["message"]["content"]


def _ollama_complete(messages, temperature, json_mode) -> str:
    body = {"model": settings.OLLAMA_MODEL, "messages": messages, "stream": False,
            "options": {"temperature": temperature}}
    if json_mode:
        body["format"] = "json"
    with httpx.Client(timeout=settings.LLM_TIMEOUT) as c:
        r = c.post(f"{settings.OLLAMA_URL.rstrip('/')}/api/chat", json=body)
        if r.status_code >= 400:
            raise LLMError(f"Ollama HTTP {r.status_code}")
        return r.json()["message"]["content"]


_STREAMERS = {"gemini": _gemini_stream, "openai": _openai_stream, "ollama": _ollama_stream}
_COMPLETERS = {"gemini": _gemini_complete, "openai": _openai_complete, "ollama": _ollama_complete}


def configured_providers() -> List[str]:
    """The active provider first, then any other configured ones as fallbacks."""
    first = active_provider()
    if first == "offline":
        return []
    rest = [p for p, ok in (("gemini", settings.GEMINI_API_KEY), ("openai", settings.OPENAI_API_KEY),
                            ("ollama", settings.OLLAMA_URL)) if ok and p != first]
    return [first] + ([] if settings.LLM_PROVIDER.lower() != "auto" else rest)


last_used: Optional[str] = None


def stream_chat(messages: List[Message], temperature: float = 0.3) -> Iterator[str]:
    """Stream from the first provider that works; fall back to the next if one fails before answering."""
    global last_used
    errors = []
    for p in configured_providers():
        started = False
        try:
            for tok in _STREAMERS[p](messages, temperature):
                started = True
                last_used = p
                yield tok
            if started:
                return
        except Exception as exc:
            if started:
                raise
            errors.append(f"{p}: {exc}")
            log.warning("LLM provider %s failed, trying next: %s", p, exc)
    raise LLMError("; ".join(errors) or "No language model configured")


def complete(messages: List[Message], temperature: float = 0.2, json_mode: bool = False) -> str:
    errors = []
    for p in configured_providers():
        try:
            return _COMPLETERS[p](messages, temperature, json_mode)
        except Exception as exc:
            errors.append(f"{p}: {exc}")
    raise LLMError("; ".join(errors) or "No language model configured")


def complete_json(messages: List[Message]) -> Optional[dict]:
    try:
        raw = complete(messages, temperature=0.2, json_mode=True).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        return json.loads(raw)
    except Exception as exc:
        log.warning("JSON completion failed: %s", exc)
        return None
