"""Chunking and Temporal Memory Unit (TMU) extraction.

A document becomes sections (split on dated headings, so a multi-entry journal keeps each
entry's date), then chunks (for context), then memories (one per meaningful statement).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.ingestion.dates import extract_event_date, parse_date
from app.models.schemas import MemoryType

# ---------------------------------------------------------------- taxonomy
KNOWN_ENTITIES = [
    "Python", "Java", "C++", "Rust", "JavaScript", "TypeScript", "Golang", "Kotlin", "Swift", "SQL",
    "Machine Learning", "Artificial Intelligence", "AI", "Deep Learning", "PyTorch", "TensorFlow", "Transformers",
    "LLMs", "LLM", "RAG", "NLP", "Computer Vision", "Docker", "Kubernetes", "PostgreSQL", "MySQL", "React",
    "Next.js", "FastAPI", "Spring Boot", "Distributed Systems", "AWS", "GCP", "Azure", "Mechanistic Interpretability",
    "AI Engineer", "Software Engineer", "Research Scientist", "AI Researcher", "Data Scientist", "PhD",
    "Product Manager", "Founder", "SaaS", "B2B SaaS", "Startup", "Venture Capital", "Climate", "Bioinformatics",
    "Meditation", "Running", "Marathon", "Yoga", "Therapy",
]
_ENTITY_CANON = {"llm": "LLMs", "llms": "LLMs", "artificial intelligence": "AI", "golang": "Golang"}

TOPICS: Dict[str, List[str]] = {
    "Artificial Intelligence": ["ai", "machine learning", "deep learning", "neural", "llm", "llms", "transformer",
                                "nlp", "model", "models", "agents", "gpt", "rag", "interpretability"],
    "Software Engineering": ["software", "engineering", "backend", "frontend", "architecture", "coding", "code",
                             "developer", "programming", "java", "python", "rust", "kubernetes", "database"],
    "Research & Academia": ["research", "paper", "papers", "publish", "conference", "phd", "academic", "experiment",
                            "thesis", "lab", "scientist"],
    "Career & Work": ["career", "job", "role", "promotion", "work", "team", "manager", "company", "hired", "interview",
                      "salary", "boss", "colleague", "office"],
    "Entrepreneurship": ["startup", "founder", "founded", "pivot", "venture", "investor", "funding", "customers",
                         "revenue", "saas", "business", "product"],
    "Health & Fitness": ["health", "exercise", "running", "run", "gym", "sleep", "diet", "doctor", "fitness", "yoga",
                         "marathon", "workout", "weight", "injury"],
    "Mind & Wellbeing": ["anxiety", "stress", "burnout", "meditation", "therapy", "mental", "calm", "mindful",
                         "happiness", "gratitude", "lonely", "depressed", "overwhelmed"],
    "Relationships & Family": ["family", "mother", "father", "mom", "dad", "sister", "brother", "partner", "wife",
                               "husband", "friend", "friends", "relationship", "kids", "children", "wedding"],
    "Money & Finance": ["money", "finance", "savings", "invest", "investing", "budget", "debt", "income", "spend",
                        "rent", "mortgage"],
    "Learning & Growth": ["learn", "learning", "learned", "course", "book", "books", "reading", "skill", "skills",
                          "practice", "habit", "habits", "growth"],
    "Travel & Places": ["travel", "trip", "moved", "move", "city", "abroad", "country", "visit", "relocate", "flight"],
    "Creativity & Hobbies": ["music", "guitar", "piano", "painting", "writing", "photography", "art", "hobby",
                             "drawing", "novel", "poetry", "cooking"],
}

TYPE_RULES: List[Tuple[MemoryType, List[str]]] = [
    (MemoryType.DECISION, ["decided to", "i chose", "i choose", "i will switch", "made a decision", "i'm going to",
                           "i am going to", "i quit", "i accepted", "i turned down", "committed to", "pivot"]),
    (MemoryType.GOAL, ["i want to", "my goal", "aiming to", "aim to", "aspire", "hope to", "my dream", "ambition",
                       "i'd love to", "i would love to", "goal is", "goal for"]),
    (MemoryType.PLAN, ["plan to", "planning to", "roadmap", "next step", "next month", "will start", "this week i will",
                       "schedule", "i intend"]),
    (MemoryType.BELIEF, ["i believe", "i think", "in my opinion", "i'm convinced", "convinced that", "i don't think",
                         "i do not think", "still think", "skeptical", "i doubt", "seems overhyped", "is the only", "i feel that",
                         "is dead", "matters more"]),
    (MemoryType.PREFERENCE, ["i prefer", "favorite", "favourite", "enjoy", "i love", "i like", "dislike", "i hate",
                             "can't stand"]),
    (MemoryType.REFLECTION, ["looking back", "in hindsight", "i realized", "i realised", "lesson", "reflecting",
                             "i've come to", "i have come to", "transformed", "grateful for"]),
    (MemoryType.FEELING, ["i feel", "i felt", "feeling", "i'm anxious", "i am anxious", "i'm happy", "i am happy",
                          "overwhelmed", "excited", "nervous", "proud of", "sad", "lonely", "burned out", "burnt out"]),
    (MemoryType.KNOWLEDGE, ["learned that", "learnt that", "understood", "studied", "i know now", "i discovered"]),
    (MemoryType.OBSERVATION, ["noticed", "observed", "data shows", "it seems", "apparently"]),
]

STANCE_POS = [r"want to", r"focus(?:ed|ing)? (?:purely |entirely |heavily )?on", r"started learning", r"my goal", r"love", r"fascinated", r"focusing on", r"committed to",
              r"excited about", r"passionate", r"strongly prefer", r"specialize", r"believe in", r"far more .* than",
              r"more practical potential", r"full time", r"enjoy", r"invest(?:ing)? in", r"double down", r"embrace",
              r"is the future", r"replacing", r"deepening", r"thrilled", r"convinced .* (?:will|is)",
              r"real-world power", r"pivot (?:my|our|the) .* to", r"operates entirely on"]
STANCE_NEG = [r"don't think", r"do not think", r"not relevant", r"irrelevant", r"waste of time", r"don't want",
              r"do not want", r"mov(?:ed|ing) away", r"stopped", r"abandon", r"dislike", r"skeptical", r"not interested",
              r"no longer", r"avoid", r"overhyped", r"impractical", r"not investable", r"is dead", r"hate",
              r"gave up", r"quit", r"never again", r"\bhype\b", r"don't trust", r"do not trust", r"not satisfying", r"not worth", r"doubt", r"tired of"]

POS_WORDS = set("""happy joy joyful grateful excited proud love loved calm peaceful hopeful thrilled fulfilled great
wonderful amazing satisfying confident energized inspired relieved content optimistic curious delighted""".split())
NEG_WORDS = set("""sad anxious anxiety stressed stress worried angry lonely tired exhausted burnout frustrated
afraid fear depressed overwhelmed disappointed hopeless miserable guilty bored hurt scared lost stuck""".split())

_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])|\n+")
_CAP_PHRASE = re.compile(r"(?<![.!?:]\s)(?<!^)\b([A-Z][a-zA-Z0-9+.#-]{1,}(?:\s+(?:of\s+)?[A-Z][a-zA-Z0-9+.#-]+){0,3})")
_CAP_STOP = {"I", "I'm", "I've", "I'd", "My", "The", "This", "That", "It", "We", "Our", "But", "And", "So", "Then",
             "Today", "Yesterday", "Tomorrow", "Looking", "In", "On", "At", "Over", "After", "Before", "Now", "When",
             "Also", "Still", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
             "Engineering", "Traditional", "Focus", "Journal", "Entry", "Notes", "Note", "Q1", "Q2", "Q3", "Q4"}
_MONTH_NAMES = {m.capitalize() for m in ["january", "february", "march", "april", "may", "june", "july", "august",
                                         "september", "october", "november", "december"]}


@dataclass
class Section:
    text: str
    start: int
    date: Optional[str]


@dataclass
class Chunk:
    index: int
    content: str
    start: int
    end: int
    date: Optional[str]


@dataclass
class ExtractedMemory:
    statement: str
    chunk_index: int
    memory_type: MemoryType
    date: Dict
    stance: float
    sentiment: float
    importance: float
    entities: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)


# ---------------------------------------------------------------- sections & chunks
_DATE_HEADING = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:entry|date|day)?[:\s-]*([^\n]{4,40}?)(?:\*\*)?\s*$", re.I)


def split_sections(text: str, document_date: Optional[str]) -> List[Section]:
    """Split on lines that are just a date, so journal exports keep per-entry dates."""
    sections: List[Section] = []
    current_date, buf_start, buf = document_date, 0, []
    pos = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        m = _DATE_HEADING.match(stripped) if 4 <= len(stripped) <= 48 else None
        parsed = parse_date(m.group(1)) if m else None
        if parsed and not re.search(r"[a-z]{4,}\s+[a-z]{4,}\s+[a-z]{4,}", stripped.lower()):
            if "".join(buf).strip():
                sections.append(Section("".join(buf), buf_start, current_date))
            current_date, buf, buf_start = parsed, [], pos + len(line)
        else:
            buf.append(line)
        pos += len(line)
    if "".join(buf).strip():
        sections.append(Section("".join(buf), buf_start, current_date))
    return sections or [Section(text, 0, document_date)]


def chunk_text(text: str, document_date: Optional[str], target: int = 700, overlap_sentences: int = 1) -> List[Chunk]:
    chunks: List[Chunk] = []
    for sec in split_sections(text, document_date):
        sentences: List[Tuple[str, int]] = []
        for m in re.finditer(r"[^\n.!?]+(?:[.!?]+[\"')\]]*|\n|$)", sec.text):
            s = m.group(0)
            if s.strip():
                sentences.append((s, sec.start + m.start()))
        cur: List[Tuple[str, int]] = []
        size = 0
        for s, off in sentences:
            if size + len(s) > target and cur:
                chunks.append(_mk_chunk(len(chunks), cur, sec.date))
                cur = cur[-overlap_sentences:] if overlap_sentences else []
                size = sum(len(x) for x, _ in cur)
            cur.append((s, off))
            size += len(s)
        if cur and (not chunks or "".join(x for x, _ in cur).strip() != chunks[-1].content):
            chunks.append(_mk_chunk(len(chunks), cur, sec.date))
    return chunks


def _mk_chunk(i: int, sents: List[Tuple[str, int]], date: Optional[str]) -> Chunk:
    start = sents[0][1]
    end = sents[-1][1] + len(sents[-1][0])
    content = re.sub(r"[ \t]+", " ", " ".join(s.strip() for s, _ in sents)).strip()
    return Chunk(i, content, start, end, date)


# ---------------------------------------------------------------- statement analysis
def split_statements(chunk: str) -> List[str]:
    out = []
    for raw in _SENT_RE.split(chunk):
        s = raw.strip().strip("-*•>\t ").strip()
        s = re.sub(r"^#+\s*", "", s)
        if len(s) < 18 or len(s.split()) < 4:
            continue
        if parse_date(s) and len(s) < 40:
            continue
        out.append(s)
    return out


def classify(statement: str) -> MemoryType:
    low = statement.lower()
    for mtype, cues in TYPE_RULES:
        if any(c in low for c in cues):
            return mtype
    return MemoryType.EVENT


def stance(statement: str) -> float:
    low = statement.lower()
    neg = sum(1 for p in STANCE_NEG if re.search(p, low))
    pos = sum(1 for p in STANCE_POS if re.search(p, low))
    if neg > pos:
        return max(-1.0, -0.5 - 0.25 * (neg - pos))
    if pos > neg:
        return min(1.0, 0.5 + 0.25 * (pos - neg))
    return 0.0


def subject_terms(subject: str) -> List[str]:
    if subject in TOPICS:
        return TOPICS[subject]
    return [subject.lower()]


CLAUSE_SPLIT = re.compile(r"[;:]|\s[-–—]\s|,?\s+(?:but|while|whereas|however|yet|now|instead)\s+", re.I)


def targeted_stance(statement: str, subject: str) -> float:
    """Stance toward one subject, judged only on the clauses that mention it."""
    terms = subject_terms(subject)
    clauses = [c for c in CLAUSE_SPLIT.split(statement) if c and c.strip()]
    hits = [c for c in clauses if any(re.search(rf"\b{re.escape(t)}\b", c.lower()) for t in terms)]
    if not hits:
        return stance(statement) if len(clauses) <= 1 else 0.0
    vals = [stance(c) for c in hits]
    return max(vals, key=abs)


def sentiment(statement: str) -> float:
    words = re.findall(r"[a-z']+", statement.lower())
    if not words:
        return 0.0
    score = 0.0
    for i, w in enumerate(words):
        v = 1.0 if w in POS_WORDS else -1.0 if w in NEG_WORDS else 0.0
        if v and i > 0 and words[i - 1] in ("not", "never", "no", "hardly", "don't", "isn't", "wasn't"):
            v = -v
        score += v
    return round(max(-1.0, min(1.0, score / 2.5)), 3)


def entities(statement: str) -> List[str]:
    found: List[str] = []
    for ent in KNOWN_ENTITIES:
        if re.search(rf"(?<![\w+]){re.escape(ent)}(?![\w+])", statement, re.I if len(ent) > 3 else 0):
            found.append(_ENTITY_CANON.get(ent.lower(), ent))
    for m in _CAP_PHRASE.finditer(statement):
        phrase = m.group(1).strip(".-")
        first = phrase.split()[0]
        if first in _CAP_STOP or first in _MONTH_NAMES or len(phrase) < 3 or phrase.isdigit():
            continue
        if any(phrase.lower() == f.lower() or phrase.lower() in f.lower() for f in found):
            continue
        found.append(phrase)
    # dedupe preserving order; drop substrings of longer entities
    uniq: List[str] = []
    for e in found:
        if e not in uniq:
            uniq.append(e)
    return [e for e in uniq if not any(e != o and e.lower() in o.lower().split() for o in uniq)][:8]


def topics(statement: str, ents: List[str]) -> List[str]:
    low = statement.lower() + " " + " ".join(ents).lower()
    hits = [t for t, kws in TOPICS.items() if any(re.search(rf"\b{re.escape(k)}\b", low) for k in kws)]
    return hits[:4]


def importance(statement: str, mtype: MemoryType, st: float, sent: float) -> float:
    score = 0.35
    if mtype in (MemoryType.DECISION, MemoryType.GOAL, MemoryType.REFLECTION):
        score += 0.25
    elif mtype in (MemoryType.BELIEF, MemoryType.PLAN, MemoryType.FEELING):
        score += 0.15
    score += 0.15 * abs(st) + 0.1 * abs(sent)
    if re.search(r"\b(i|my|me|we|our)\b", statement.lower()):
        score += 0.1
    if re.search(r"\b(first|finally|never|always|completely|entire|biggest|turning point)\b", statement.lower()):
        score += 0.08
    return round(min(1.0, score), 3)


def extract(chunks: List[Chunk], document_date: Optional[str]) -> List[ExtractedMemory]:
    out: List[ExtractedMemory] = []
    for ch in chunks:
        for stmt in split_statements(ch.content):
            mtype = classify(stmt)
            st, sent = stance(stmt), sentiment(stmt)
            ents = entities(stmt)
            out.append(ExtractedMemory(
                statement=stmt, chunk_index=ch.index, memory_type=mtype,
                date=extract_event_date(stmt, ch.date or document_date), stance=st, sentiment=sent,
                importance=importance(stmt, mtype, st, sent), entities=ents, topics=topics(stmt, ents),
            ))
    # de-duplicate overlapping sentences from chunk overlap
    seen, uniq = set(), []
    for m in out:
        key = m.statement.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(m)
    return uniq
