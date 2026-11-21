"""Query understanding: intent, time window and keywords."""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas import QueryIntent

YEAR = r"(19[5-9]\d|20\d{2})"

INTENT_CUES: List[Tuple[QueryIntent, List[str]]] = [
    (QueryIntent.CONTRADICTION_ANALYSIS, ["contradict", "revers", "opposite", "conflict", "change my mind",
                                          "changed my mind", "flip", "inconsisten", "u-turn"]),
    (QueryIntent.CHANGE_POINT_ANALYSIS, ["turning point", "inflection", "when did i stop", "when did i start",
                                         "when did i first", "what made me", "shift", "pivot", "why did i switch",
                                         "what changed", "moment"]),
    (QueryIntent.TIMELINE_REQUEST, ["timeline", "chronolog", "milestone", "history of", "in order", "step by step",
                                    "journey"]),
    (QueryIntent.VERSION_COMPARISON, ["version", "resume v", "diff", "revision", "compare my resume", "v1", "v2"]),
    (QueryIntent.STABLE_PATTERN_ANALYSIS, ["stable", "consistent", "never change", "always", "constant", "recurring",
                                           "pattern", "keep coming back", "core values"]),
    (QueryIntent.EVOLUTION_ANALYSIS, ["how has", "how have", "how did my", "evolv", "over time", "over the years",
                                      "progress", "grow", "changed", "develop", "trajectory", "what happened to", "become of", "from 19", "from 20",
                                      "since 19", "since 20"]),
    (QueryIntent.SUMMARY, ["summar", "overview", "tell me about myself", "who am i", "big picture", "recap",
                           "what have i been"]),
]

STOP = set("""what did i think about how has my opinion changed over the years time was were when show me a an is are and
or to in of for with on at between do does have has had my me i you your it its this that which who whom why where tell
give list find about from since before after during year years ever been be any all can could would should""".split())


def _years(lower: str) -> Tuple[Optional[int], Optional[int]]:
    this_year = date.today().year
    if m := re.search(rf"\bbetween\s+{YEAR}\s+and\s+{YEAR}\b", lower):
        a, b = int(m.group(1)), int(m.group(2))
        return min(a, b), max(a, b)
    if m := re.search(rf"\bfrom\s+{YEAR}\s+(?:to|until|till|through|-)\s+{YEAR}\b", lower):
        a, b = int(m.group(1)), int(m.group(2))
        return min(a, b), max(a, b)
    if m := re.search(rf"\b{YEAR}\s*(?:-|–|to)\s*{YEAR}\b", lower):
        a, b = int(m.group(1)), int(m.group(2))
        return min(a, b), max(a, b)
    if m := re.search(rf"\bbefore\s+{YEAR}\b", lower):
        return None, int(m.group(1)) - 1
    if m := re.search(rf"\b(?:after|since)\s+{YEAR}\b", lower):
        return int(m.group(1)), None
    if m := re.search(r"\b(?:past|last)\s+(\d+|two|three|four|five|six|seven|eight|nine|ten)\s+years\b", lower):
        n = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10}.get(m.group(1), None) or int(m.group(1))
        return this_year - n, this_year
    if re.search(r"\blast year\b", lower):
        return this_year - 1, this_year - 1
    if re.search(r"\bthis year\b", lower):
        return this_year, this_year
    if re.search(r"\b(recently|lately|these days|nowadays|right now|currently)\b", lower):
        return this_year - 1, this_year
    found = re.findall(rf"\b(?:in|during|around|of)\s+{YEAR}\b", lower)
    if len(found) == 1:
        y = int(found[0])
        return y, y
    return None, None


def analyze(query: str) -> Dict[str, Any]:
    lower = query.lower().strip()
    intent = QueryIntent.FACT_LOOKUP
    for candidate, cues in INTENT_CUES:
        if any(c in lower for c in cues):
            intent = candidate
            break
    start, end = _years(lower)
    if intent == QueryIntent.FACT_LOOKUP and start and start == end:
        intent = QueryIntent.TEMPORAL_LOOKUP
    keywords = [w for w in re.findall(r"[A-Za-z0-9+#.\-]+", query) if w.lower() not in STOP and len(w) > 1]
    return {
        "query": query,
        "intent": intent,
        "start_year": start,
        "end_year": end,
        "keywords": keywords,
        "is_longitudinal": intent in {QueryIntent.EVOLUTION_ANALYSIS, QueryIntent.TIMELINE_REQUEST,
                                      QueryIntent.CHANGE_POINT_ANALYSIS, QueryIntent.CONTRADICTION_ANALYSIS,
                                      QueryIntent.STABLE_PATTERN_ANALYSIS, QueryIntent.SUMMARY},
    }


FOLLOWUP_RE = re.compile(r"^\s*(and|but|what about|how about|so|then|also|more|tell me more|what else|same for|"
                         r"that|those|it|this|why is that|why\?|and why)\b", re.I)


def contextualize(query: str, history: List[Dict[str, str]]) -> str:
    """Make short follow-ups ("and in 2023?", "why?") self-contained for retrieval."""
    prev = [m["content"] for m in history if m["role"] == "user"]
    if not prev:
        return query
    content = [w for w in re.findall(r"[a-z0-9+#]+", query.lower()) if w not in STOP and len(w) > 1
               and not re.fullmatch(r"(19|20)\d\d", w)]
    if FOLLOWUP_RE.match(query) and len(content) <= 2:
        return f"{prev[-1]} {query}"
    return query


def plan_for(query: str, context_query: str) -> Dict[str, Any]:
    """Intent and time window come from the question itself; the conversation only fills gaps."""
    own = analyze(query)
    if context_query == query:
        return own
    ctx = analyze(context_query)
    if own["intent"] == QueryIntent.FACT_LOOKUP:
        own["intent"], own["is_longitudinal"] = ctx["intent"], ctx["is_longitudinal"]
    if not (own["start_year"] or own["end_year"]):
        own["start_year"], own["end_year"] = ctx["start_year"], ctx["end_year"]
    own["keywords"] = ctx["keywords"]
    return own
