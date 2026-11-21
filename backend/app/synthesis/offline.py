"""The offline writer: answers without a language model, shaped to the question that was asked.

It recognises a few common question shapes ("when did I start/stop X", "what did I love in 2022",
"how did X change", greetings) and answers each directly, quoting the person's own words with
citations. When nothing in the evidence actually matches, it says so instead of guessing.
"""
from __future__ import annotations

import calendar
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Set

from app.ai.embeddings import STOPWORDS, _WORD2CONCEPT, CONCEPTS, _stem
from app.models.schemas import MemoryOut, MemoryType
from app.retrieval.router import STOP

# ------------------------------------------------------------------ question shapes
SMALLTALK = re.compile(
    r"^\s*(hi+|hello+|hey+|hiya|yo|sup|good (morning|afternoon|evening|night)|thanks?( you)?|thank u|ty|ok(ay)?|cool|"
    r"nice|great|bye|goodbye|who are you|what are you|what can you do|help|how are you)\b[\s!.?]*$", re.I)
START_Q = re.compile(r"\bwhen (?:did|do) i (?:first |really )?(?:start|started|begin|began|get into|got into|pick up|"
                     r"take up|become interested|get interested)|\bhow did i (?:start|get into|begin)|"
                     r"\bwhen did .{1,40}\b(?:start|begin)\b|\bfirst time i\b", re.I)
STOP_Q = re.compile(r"\bwhen (?:did|do) i (?:stop|stopped|quit|leave|left|give up|gave up|drop|abandon|move away|"
                    r"lose interest)|\bwhy did i (?:stop|quit|leave|give up)", re.I)
LOVE_Q = re.compile(r"\b(love|loved|like|liked|enjoy|enjoyed|favou?rite|passion|passionate|excite|excited)\b", re.I)
FEEL_Q = re.compile(r"\b(feel|feeling|felt|mood|happy|happier|sad|anxious|stress|stressed|emotion)", re.I)

START_WORDS = re.compile(r"\b(start(ed|ing)?|began|begin|first|learn(ing|ed)?|join(ed)?|accepted|decided|picked up|"
                         r"took up|curious|curiosity|discover(ed)?)\b", re.I)
STOP_WORDS_RE = re.compile(r"\b(stopp?ed|quit|moved away|no longer|gave up|left|abandon(ed)?|dropped|anymore|"
                           r"not satisfying|dead)\b", re.I)
LOVE_WORDS = re.compile(r"\b(love|loved|enjoy|enjoyed|favou?rite|passion|passionate|proud|excited|thrilled|grateful|"
                        r"anchor|fascinat\w*|like)\b", re.I)

QUESTION_FILLER = {"when", "did", "do", "does", "start", "started", "begin", "began", "stop", "stopped", "quit", "first",
                   "love", "loved", "like", "liked", "enjoy", "enjoyed", "feel", "felt", "feeling", "think", "thought",
                   "get", "got", "into", "about", "really", "using", "use", "doing", "working", "with", "on", "my",
                   "how", "why", "what", "which", "who", "where", "change", "changed", "evolve", "evolved", "year",
                   "years", "time", "things", "thing", "most", "ever", "lately", "recently", "give", "up", "leave"}


BROAD_WORDS = {"ai", "ml", "career", "job", "work", "health", "fitness", "family", "relationships", "money",
               "finance", "travel", "research", "learning", "coding", "programming", "code"}


def is_smalltalk(q: str) -> bool:
    return bool(SMALLTALK.match(q.strip()))


def smalltalk_reply(q: str) -> str:
    low = q.lower()
    if re.search(r"thank|ty\b", low):
        return "You're welcome. Ask me anything else about your past whenever you like."
    if re.search(r"bye", low):
        return "See you soon."
    if re.search(r"who are you|what are you|what can you do|help", low):
        return ("I'm Memory Lane. I read your journals and notes and answer questions about your own past, "
                "always pointing to the exact entry. Try asking:\n\n"
                "- *How has my view of my career changed?*\n- *When did I start learning AI?*\n"
                "- *What did I care about in 2021?*")
    return ("Hi! Ask me anything about your past: what you believed, when something started, or how a view "
            "changed over the years.")


def subject_terms(query: str) -> Set[str]:
    """Content words of the question, stemmed and expanded with related concepts (ai → machine learning …)."""
    words = re.findall(r"[a-z0-9+#]+", query.lower())
    core = [w for w in words if w not in STOP and w not in STOPWORDS and w not in QUESTION_FILLER
            and not re.fullmatch(r"(19|20)\d\d", w) and len(w) > 1]
    out: Set[str] = set()
    for w in core:
        out.add(_stem(w))
        c = _WORD2CONCEPT.get(w)
        if c and (w == c or w in BROAD_WORDS):  # only broad words fan out ("ai" → machine learning…)
            out.update(_stem(x) for x in CONCEPTS[c])
    return out


def _tokens(m: MemoryOut) -> Set[str]:
    text = " ".join([m.statement, " ".join(m.entities), " ".join(m.topics)]).lower()
    return {_stem(w) for w in re.findall(r"[a-z0-9+#]+", text)}


def matches(m: MemoryOut, terms: Set[str]) -> bool:
    return bool(terms) and bool(_tokens(m) & terms)


def subject_label(query: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9+#.]+", query)
             if w.lower() not in STOP and w.lower() not in STOPWORDS and w.lower() not in QUESTION_FILLER
             and not re.fullmatch(r"(19|20)\d\d", w)]
    label = " ".join(words).strip(" ?.")
    if not label:
        return "that"
    return label.upper() if len(label) <= 3 else label


# ------------------------------------------------------------------ formatting helpers
def _when(d: Optional[str]) -> str:
    if not d:
        return "an undated entry"
    try:
        m = int(d[5:7])
        return f"{calendar.month_name[m]} {d[:4]}" if m and d[5:10] != "01-01" else d[:4]
    except Exception:
        return d[:4]


def _q(m: MemoryOut) -> str:
    s = m.statement.strip()
    return f"“{s if s.endswith(('.', '!', '?')) else s + '.'}”"


def _period(plan: Dict[str, Any]) -> str:
    a, b = plan.get("start_year"), plan.get("end_year")
    if a and b:
        return f"in {a}" if a == b else f"between {a} and {b}"
    if a:
        return f"since {a}"
    if b:
        return f"before {b + 1}"
    return "in your entries"


# ------------------------------------------------------------------ the writer
def write(query: str, plan: Dict[str, Any], results: List[Dict[str, Any]], changes) -> str:
    mems: List[MemoryOut] = [c["memory"] for c in results]
    if not mems:
        return (f"I couldn't find anything {_period(plan)} about that. Try different words, or add an entry that "
                "covers it.")
    idx = {m.id: i + 1 for i, m in enumerate(mems)}
    cite = lambda m: f"[{idx[m.id]}]"  # noqa: E731
    terms = subject_terms(query)
    relevant = [m for m in mems if matches(m, terms)] if terms else list(mems)
    dated = lambda ms: sorted([m for m in ms if m.event_date_start], key=lambda m: (m.event_date_start, m.id))  # noqa
    subject = subject_label(query)

    # ---- when did I start X?
    if START_Q.search(query):
        pool = dated(relevant)
        if not pool:
            return f"I couldn't find any mention of {subject} in your entries, so I can't tell when you started."
        starts = [m for m in pool if START_WORDS.search(m.statement) and m.stance_polarity >= -0.5]
        first = starts[0] if starts else next((m for m in pool if m.stance_polarity >= 0), pool[0])
        out = [f"Your entries point to **{_when(first.event_date_start)}**. That's when you wrote {_q(first)} {cite(first)}"]
        before = [m for m in pool if m.event_date_start < first.event_date_start]
        if before:
            b = before[-1]
            out.append(f"Before that, in {_when(b.event_date_start)}, you'd written {_q(b)} {cite(b)}")
        after = [m for m in pool if m.event_date_start > first.event_date_start][:2]
        if after:
            out.append("What came next:\n" + "\n".join(f"- {_when(m.event_date_start)}: {_q(m)} {cite(m)}" for m in after))
        return "\n\n".join(out)

    # ---- when did I stop X?
    if STOP_Q.search(query):
        pool = dated(relevant)
        if not pool:
            return f"I couldn't find any mention of {subject} in your entries, so I can't tell when you stopped."
        stops = [m for m in pool if STOP_WORDS_RE.search(m.statement) or m.stance_polarity <= -0.5]
        if not stops:
            last = pool[-1]
            return (f"I don't see an entry where you stopped {subject}. The latest mention is from "
                    f"{_when(last.event_date_start)}: {_q(last)} {cite(last)}")
        stop = stops[0]
        out = [f"By **{_when(stop.event_date_start)}** you had moved on. You wrote {_q(stop)} {cite(stop)}"]
        earlier = [m for m in pool if m.event_date_start < stop.event_date_start and m.stance_polarity >= 0]
        if earlier:
            e = earlier[-1]
            out.append(f"The last time you wrote about it positively was {_when(e.event_date_start)}: {_q(e)} {cite(e)}")
            gap_years = int(stop.event_date_start[:4]) - int(e.event_date_start[:4])
            if gap_years >= 2:
                out.append(f"There are no entries about it in between, so the exact moment isn't recorded.")
        return "\n\n".join(out)

    # ---- what did I love / enjoy (in a period)?
    if LOVE_Q.search(query):
        pool = [m for m in relevant if (LOVE_WORDS.search(m.statement) and m.stance_polarity >= 0)
                or m.memory_type == MemoryType.PREFERENCE or m.sentiment >= 0.4]
        if pool:
            lines = "\n".join(f"- {_when(m.event_date_start)}: {_q(m)} {cite(m)}" for m in dated(pool)[:4])
            return f"Here's what you wrote about enjoying {_period(plan)}:\n\n{lines}"
        nearby = dated(mems)[:3]
        lines = "\n".join(f"- {_when(m.event_date_start)}: {_q(m)} {cite(m)}" for m in nearby)
        return (f"You didn't write about loving or enjoying anything specific {_period(plan)}. "
                f"Here's what you did write about then:\n\n{lines}")

    # ---- feelings
    if FEEL_Q.search(query):
        pool = [m for m in mems if m.memory_type == MemoryType.FEELING or abs(m.sentiment) >= 0.3]
        if not pool:
            return f"You didn't write much about your feelings {_period(plan)}."
        lines = "\n".join(f"- {_when(m.event_date_start)}: {_q(m)} {cite(m)}" for m in dated(pool)[:5])
        return f"Here's how you described your feelings {_period(plan)}:\n\n{lines}"

    if terms and not relevant:
        lines = "\n".join(f"- {_when(m.event_date_start)}: {_q(m)} {cite(m)}" for m in mems[:2])
        return (f"I couldn't find anything about **{subject}** {_period(plan)}. The closest entries I found:\n\n{lines}")

    # ---- how did it change over time?
    pool = dated(relevant)
    years = sorted({m.event_date_start[:4] for m in pool})
    if (plan.get("is_longitudinal") or len(years) >= 3) and len(years) >= 2:
        first = max((m for m in pool if m.event_date_start[:4] == years[0]), key=lambda m: m.importance)
        last = max((m for m in pool if m.event_date_start[:4] == years[-1]), key=lambda m: m.importance)
        out = [f"In {_when(first.event_date_start)} you wrote {_q(first)} {cite(first)} "
               f"By {_when(last.event_date_start)}: {_q(last)} {cite(last)}"]
        by_year: "OrderedDict[str, List[MemoryOut]]" = OrderedDict()
        for m in pool:
            by_year.setdefault(m.event_date_start[:4], []).append(m)
        steps = [f"- **{y}**: {_q(max(ms, key=lambda m: m.importance))} {cite(max(ms, key=lambda m: m.importance))}"
                 for y, ms in by_year.items()]
        out.append("**Along the way**\n" + "\n".join(steps))
        rel = [c for c in changes if c.earlier.id in idx and c.later.id in idx
               and (not terms or matches(c.later, terms) or matches(c.earlier, terms))][:2]
        if rel:
            words = {"reversal": "reversed", "intensified": "grew stronger", "softened": "softened",
                     "new_commitment": "became a commitment", "direction_shift": "changed direction"}
            out.append("\n".join(f"Your view on **{c.subject}** {words.get(c.change_type, 'shifted')} between "
                                 f"{_when(c.from_date)} and {_when(c.to_date)}." for c in rel))
        return "\n\n".join(out)

    # ---- simple lookup
    top = pool or relevant or mems
    best = top[0] if not pool else max(pool, key=lambda m: next((c["score"] for c in results if c["memory"].id == m.id), 0))
    out = [f"In {_when(best.event_date_start)} you wrote {_q(best)} {cite(best)}"]
    others = [m for m in (pool or top) if m.id != best.id][:3]
    if others:
        out.append("Related:\n" + "\n".join(f"- {_when(m.event_date_start)}: {_q(m)} {cite(m)}" for m in others))
    return "\n\n".join(out)
