"""Hybrid temporal retrieval: dense + BM25 + passage hits → RRF → temporal filters → boosts →
year-stratified MMR. Three pipelines are exposed for the research lab:

* baseline     – dense vector top-k only
* temporal     – hybrid fusion + time filters + year stratification
* memory_lane  – everything, plus intent-aware boosts and MMR diversity
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.core.config import settings
from app.models.schemas import MemoryOut, MemoryType, QueryIntent
from app.retrieval.router import analyze
from app.storage import vectors
from app.storage.repo import Memories

_fresh_checked: set = set()
EMOTION_Q = re.compile(r"\b(feel|feeling|felt|mood|emotion|happy|happier|sad|anxious|anxiety|stress|burnout|"
                       r"wellbeing|well-being|mental|lonely|calm)\b", re.I)

INTENT_TYPE_BOOST = {
    QueryIntent.EVOLUTION_ANALYSIS: {MemoryType.BELIEF: 0.25, MemoryType.GOAL: 0.25, MemoryType.DECISION: 0.3,
                                     MemoryType.REFLECTION: 0.2},
    QueryIntent.CHANGE_POINT_ANALYSIS: {MemoryType.DECISION: 0.35, MemoryType.REFLECTION: 0.25, MemoryType.GOAL: 0.15},
    QueryIntent.CONTRADICTION_ANALYSIS: {MemoryType.BELIEF: 0.3, MemoryType.PREFERENCE: 0.2, MemoryType.GOAL: 0.15},
    QueryIntent.STABLE_PATTERN_ANALYSIS: {MemoryType.BELIEF: 0.2, MemoryType.PREFERENCE: 0.25},
    QueryIntent.TIMELINE_REQUEST: {MemoryType.EVENT: 0.15, MemoryType.DECISION: 0.25},
    QueryIntent.SUMMARY: {MemoryType.REFLECTION: 0.2, MemoryType.GOAL: 0.15, MemoryType.DECISION: 0.15},
}


def _mmr(cands: List[Dict[str, Any]], vecs: Dict[str, np.ndarray], k: int, lam: float) -> List[Dict[str, Any]]:
    if len(cands) <= k:
        return cands
    chosen: List[Dict[str, Any]] = []
    pool = list(cands)
    top = max(c["score"] for c in pool) or 1.0
    while pool and len(chosen) < k:
        best, best_val = None, -1e9
        for c in pool:
            rel = c["score"] / top
            v = vecs.get(c["memory"].id)
            red = 0.0
            if v is not None and chosen:
                red = max(float(np.dot(v, vecs[x["memory"].id])) for x in chosen if x["memory"].id in vecs) \
                    if any(x["memory"].id in vecs for x in chosen) else 0.0
            val = lam * rel - (1 - lam) * red
            if val > best_val:
                best, best_val = c, val
        chosen.append(best)
        pool.remove(best)
    return chosen


def _stratify(cands: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    by_year: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in cands:
        by_year[(c["memory"].event_date_start or "????")[:4]].append(c)
    years = sorted(by_year)
    chosen, round_i = [], 0
    while len(chosen) < k:
        added = False
        for y in years:
            if round_i < len(by_year[y]) and len(chosen) < k:
                chosen.append(by_year[y][round_i])
                added = True
        if not added:
            break
        round_i += 1
    return chosen


def retrieve(user_id: str, query: str, *, mode: str = "memory_lane", top_k: int = settings.DEFAULT_TOP_K,
             start_year: Optional[int] = None, end_year: Optional[int] = None,
             memory_types: Optional[Sequence[MemoryType]] = None, plan: Optional[Dict[str, Any]] = None,
             extra_ids: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    t0 = time.perf_counter()
    if user_id not in _fresh_checked:
        vectors.ensure_fresh(user_id)
        _fresh_checked.add(user_id)

    plan = plan or analyze(query)
    intent: QueryIntent = plan["intent"]
    if mode != "baseline":
        start_year = start_year or plan["start_year"]
        end_year = end_year or plan["end_year"]
    else:
        start_year = end_year = None

    pool = max(60, top_k * 6)
    scores: Dict[str, float] = defaultdict(float)
    signals: Dict[str, Dict[str, float]] = defaultdict(dict)

    # Time window first: when the question names a period, search inside it so the right years always surface.
    window_ids: Optional[set] = None
    if start_year or end_year:
        window_ids = {m.id for m in Memories.list(user_id, start_year=start_year, end_year=end_year)}

    dense = vectors.search(user_id, query, "memory", pool, allowed=window_ids)
    for rank, d in enumerate(dense):
        scores[d["id"]] += 1.0 / (settings.RRF_K + rank + 1)
        signals[d["id"]]["dense"] = d["score"]

    if mode != "baseline":
        for rank, s in enumerate(x for x in Memories.fts(user_id, query, pool)
                                 if window_ids is None or x["id"] in window_ids):
            scores[s["id"]] += 0.85 / (settings.RRF_K + rank + 1)
            signals[s["id"]]["bm25"] = s["score"]
        # passage-level hits lift the memories inside them
        chunk_hits = vectors.search(user_id, query, "chunk", 24)
        if chunk_hits:
            chunk_rank = {c["id"]: r for r, c in enumerate(chunk_hits)}
            for mid, cid in Memories.ids_for_chunks(user_id, chunk_rank.keys()):
                if window_ids is None or mid in window_ids:
                    scores[mid] += 0.5 / (settings.RRF_K + chunk_rank[cid] + 1)

    for mid in extra_ids or []:  # memories the caller already knows are about the subject
        scores[mid] += 0.4 / (settings.RRF_K + 1)
        signals[mid]["bm25"] = signals[mid].get("bm25", 0.0)

    if not scores:  # nothing matched at all: fall back to most important memories (inside the window, if any)
        pool_mems = Memories.list(user_id, start_year=start_year, end_year=end_year)
        for m in sorted(pool_mems, key=lambda m: -m.importance)[:top_k]:
            scores[m.id] = m.importance * 0.001

    # Relevance floor: drop weak semantic-only matches so focused questions stay focused.
    # A named time window is itself strong evidence of relevance, so it skips the floor.
    if mode != "baseline" and window_ids is None and len(dense) >= 8:
        sims = np.array([d["score"] for d in dense])
        floor = float(sims.mean() + (-0.3 if plan["is_longitudinal"] else 0.35) * sims.std())
        lexical = {k for k, v in signals.items() if "bm25" in v}
        keep = {k for k in scores if k in lexical or signals.get(k, {}).get("dense", -1) >= floor}
        if len(keep) >= 3:
            scores = defaultdict(float, {k: v for k, v in scores.items() if k in keep})

    feeling_q = bool(EMOTION_Q.search(query))
    mems = Memories.get_many(user_id, scores.keys())
    cands: List[Dict[str, Any]] = []
    type_boost = INTENT_TYPE_BOOST.get(intent, {}) if mode == "memory_lane" else {}
    for mid, base in scores.items():
        m = mems.get(mid)
        if not m:
            continue
        year = int(m.event_date_start[:4]) if m.event_date_start else None
        if start_year and (year is None or year < start_year):
            continue
        if end_year and (year is None or year > end_year):
            continue
        if memory_types and m.memory_type not in memory_types:
            continue
        mult = 1.0
        if mode == "memory_lane":
            mult += type_boost.get(m.memory_type, 0.0)
            mult += 0.25 * (m.importance - 0.5)
            if m.pinned:
                mult += 0.15
            if feeling_q and (m.memory_type == MemoryType.FEELING or abs(m.sentiment) >= 0.3):
                mult += 0.45
            if plan["is_longitudinal"] and abs(m.stance_polarity) >= 0.5:
                mult += 0.15
        cands.append({"memory": m, "score": base * mult, "signals": signals.get(mid, {})})
    cands.sort(key=lambda c: -c["score"])

    if mode == "baseline":
        final = cands[:top_k]
    else:
        shortlist = cands[: top_k * 4]
        if plan["is_longitudinal"]:
            final = _stratify(shortlist, top_k)
        else:
            final = shortlist
        if mode == "memory_lane":
            vecs = vectors.vectors_for(user_id, "memory", [c["memory"].id for c in final])
            final = _mmr(final, vecs, top_k, settings.MMR_LAMBDA)
        final = final[:top_k]

    if plan["is_longitudinal"]:
        final.sort(key=lambda c: (c["memory"].event_date_start or "9999", -c["score"]))

    return {
        "plan": plan,
        "results": final,
        "year_range": [start_year, end_year] if (start_year or end_year) else None,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def memories_only(result: Dict[str, Any]) -> List[MemoryOut]:
    return [c["memory"] for c in result["results"]]
