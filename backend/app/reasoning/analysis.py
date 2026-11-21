"""Longitudinal analysis: change points, contradictions and memory-graph edges.

Results are recomputed after every ingestion/edit and stored, so queries just read them.
Thresholds adapt to the embedding model by using each user's own similarity distribution.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.core.config import settings
from app.ingestion.extractor import targeted_stance
from app.models.schemas import ChangePointOut, MemoryOut, MemoryType, RelationshipOut, RelationType
from app.storage import vectors
from app.storage.repo import Analysis, Memories

log = logging.getLogger("memory_lane.analysis")

INTENT_TYPES = {MemoryType.GOAL, MemoryType.DECISION, MemoryType.PLAN, MemoryType.BELIEF, MemoryType.PREFERENCE}
GENERIC_SUBJECTS = {"Career & Work", "Learning & Growth"}


def _year(m: MemoryOut) -> Optional[str]:
    return m.event_date_start[:4] if m.event_date_start else None


def _days_between(a: Optional[str], b: Optional[str]) -> Optional[int]:
    try:
        return abs((date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days)
    except Exception:
        return None


def _sim(vecs: Dict[str, np.ndarray], a: str, b: str) -> float:
    if a in vecs and b in vecs:
        return float(np.dot(vecs[a], vecs[b]))
    return 0.0


def _uncertainty(a: MemoryOut, b: MemoryOut) -> Optional[str]:
    gap = _days_between(a.event_date_start, b.event_date_start)
    if gap is not None and gap > settings.SPARSE_EVIDENCE_DAYS:
        months = round(gap / 30.4)
        return (f"The shift happened somewhere between {a.event_date_start[:7]} and {b.event_date_start[:7]} "
                f"(~{months} months with no record in between), so the exact turning point is unknown.")
    return None


def compute(user_id: str, mems: Sequence[MemoryOut]) -> Tuple[List[dict], List[dict]]:
    dated = sorted([m for m in mems if m.event_date_start], key=lambda m: (m.event_date_start, m.id))
    vecs = vectors.vectors_for(user_id, "memory", [m.id for m in dated])

    # Similarity baseline for this user + embedder (adaptive thresholds)
    sample = [_sim(vecs, a.id, b.id) for a, b in zip(dated, dated[1:]) if a.document_id != b.document_id]
    base = float(np.median(sample)) if sample else 0.3
    high = float(np.percentile(sample, 80)) if len(sample) >= 5 else base + 0.15

    # ---- subjects → chronologically ordered memories
    by_subject: Dict[str, List[MemoryOut]] = defaultdict(list)
    for m in dated:
        for s in set(m.entities) | (set(m.topics) - GENERIC_SUBJECTS):
            by_subject[s].append(m)

    changes: Dict[Tuple[str, str], dict] = {}
    for subject, seq in by_subject.items():
        if len(seq) < 2:
            continue
        is_entity = any(subject in m.entities for m in seq)
        stances = {m.id: targeted_stance(m.statement, subject) for m in seq}
        for a, b in zip(seq, seq[1:]):
            if _year(a) == _year(b) and a.document_id == b.document_id:
                continue
            sa, sb = stances[a.id], stances[b.id]
            flip = sa * sb < 0
            gap = abs(sb - sa)
            sim = _sim(vecs, a.id, b.id)
            ctype, magnitude = None, 0.0
            if flip and gap >= settings.POLARITY_FLIP_MIN_GAP:
                ctype, magnitude = "reversal", min(1.0, gap / 2)
            elif gap >= 0.5 and sa != 0 and sb != 0:
                ctype = "intensified" if abs(sb) > abs(sa) else "softened"
                magnitude = gap / 2
            elif sa == 0 and abs(sb) >= 0.5 and b.memory_type in INTENT_TYPES:
                ctype, magnitude = "new_commitment", abs(sb) * 0.6
            elif (a.memory_type in INTENT_TYPES and b.memory_type in INTENT_TYPES and sim < base
                  and _year(a) != _year(b)):
                ctype, magnitude = "direction_shift", min(1.0, (1 - sim))
            if not ctype:
                continue
            key = (a.id, b.id)
            score = magnitude + (0.2 if is_entity else 0)
            if key not in changes or score > changes[key]["_score"]:
                changes[key] = {
                    "id": f"cp_{a.id}_{b.id}", "subject": subject, "change_type": ctype,
                    "magnitude": round(magnitude, 3), "earlier_memory_id": a.id, "later_memory_id": b.id,
                    "from_date": a.event_date_start, "to_date": b.event_date_start, "uncertainty": _uncertainty(a, b),
                    "_score": score,
                }
    change_list = sorted(changes.values(), key=lambda c: (c["to_date"] or "", -c["_score"]))
    for c in change_list:
        c.pop("_score", None)

    # ---- relationships
    rels: Dict[str, dict] = {}

    def add(kind: RelationType, a: MemoryOut, b: MemoryOut, conf: float, why: str):
        rid = f"{kind.value}_{a.id}_{b.id}"
        if rid not in rels:
            rels[rid] = {"id": rid, "source_memory_id": a.id, "target_memory_id": b.id, "relation_type": kind.value,
                         "confidence": round(conf, 3), "rationale": why}

    # contradictions: opposite stance on a shared entity/topic, about the same thing.
    # Keep the strongest counterpart per (earlier memory) and one pair per subject+year-pair to avoid noise.
    candidates = []
    for i, a in enumerate(dated):
        if abs(a.stance_polarity) < 0.4:
            continue
        for b in dated[i + 1:]:
            if b.document_id == a.document_id or abs(b.stance_polarity) < 0.4 \
                    or a.stance_polarity * b.stance_polarity >= 0:
                continue
            ent_shared = set(a.entities) & set(b.entities)
            shared = ent_shared or ((set(a.topics) & set(b.topics)) - GENERIC_SUBJECTS)
            # the opposing stances must actually point at the shared subject
            shared = {x for x in shared if targeted_stance(a.statement, x) * targeted_stance(b.statement, x) < 0}
            if not shared:
                continue
            ent_shared &= shared
            gap = abs(b.stance_polarity - a.stance_polarity)
            sim = _sim(vecs, a.id, b.id)
            conf = min(0.98, 0.45 + gap * 0.2 + max(0.0, sim - base) * 0.8 + (0.1 if ent_shared else 0))
            if conf >= 0.6:
                candidates.append((conf, a, b, sorted(ent_shared or shared)[0]))
    candidates.sort(key=lambda x: -x[0])
    per_source: Dict[str, int] = defaultdict(int)
    seen_keys = set()
    for conf, a, b, subj in candidates:
        key = (_year(a), _year(b), a.document_id)
        if per_source[a.id] >= 1 or key in seen_keys:
            continue
        per_source[a.id] += 1
        seen_keys.add(key)
        add(RelationType.CONTRADICTS, a, b, conf,
            f"Opposite stances on {subj}: {'positive' if a.stance_polarity > 0 else 'negative'} in "
            f"{(a.event_date_start or '?')[:7]}, {'positive' if b.stance_polarity > 0 else 'negative'} in "
            f"{(b.event_date_start or '?')[:7]}.")

    for c in change_list:
        a_id, b_id = c["earlier_memory_id"], c["later_memory_id"]
        if c["change_type"] != "reversal":
            rels.setdefault(f"evolves_from_{a_id}_{b_id}", {
                "id": f"evolves_from_{a_id}_{b_id}", "source_memory_id": a_id, "target_memory_id": b_id,
                "relation_type": RelationType.EVOLVES_FROM.value, "confidence": 0.75,
                "rationale": f"{c['subject']}: {c['change_type'].replace('_', ' ')}"})

    # sequence within a document
    by_doc: Dict[str, List[MemoryOut]] = defaultdict(list)
    for m in mems:
        by_doc[m.document_id].append(m)
    for seq in by_doc.values():
        seq.sort(key=lambda m: int(m.id.rsplit("_m", 1)[-1]) if "_m" in m.id else 0)
        for a, b in zip(seq, seq[1:]):
            add(RelationType.FOLLOWS, a, b, 0.9, "Next thought in the same entry")

    # supports / related across documents
    if len(dated) > 1 and vecs:
        ids = [m.id for m in dated if m.id in vecs]
        mat = np.vstack([vecs[i] for i in ids])
        sims = mat @ mat.T
        index = {m.id: m for m in dated}
        for r, mid in enumerate(ids):
            a = index[mid]
            for col in np.argsort(-sims[r])[1:3]:
                b = index[ids[col]]
                s = float(sims[r, col])
                if b.document_id == a.document_id or s < high:
                    continue
                first, second = (a, b) if (a.event_date_start, a.id) <= (b.event_date_start, b.id) else (b, a)
                if f"contradicts_{first.id}_{second.id}" in rels:
                    continue
                kind = (RelationType.SUPPORTS if first.stance_polarity * second.stance_polarity > 0
                        else RelationType.RELATED_TO)
                add(kind, first, second, min(0.95, 0.5 + s / 2), "Semantically close memories")
    return change_list, list(rels.values())


def refresh_analysis(user_id: str) -> None:
    try:
        mems = Memories.list(user_id)
        changes, rels = compute(user_id, mems)
        Analysis.replace(user_id, changes, rels)
    except Exception:  # never let analysis break ingestion
        log.exception("Analysis refresh failed for %s", user_id)


# ---------------------------------------------------------------- read helpers
def change_points(user_id: str, subject: Optional[str] = None,
                  memory_ids: Optional[set] = None) -> List[ChangePointOut]:
    rows = Analysis.changes(user_id)
    if subject:
        rows = [r for r in rows if r["subject"].lower() == subject.lower()]
    if memory_ids is not None:
        rows = [r for r in rows if r["earlier_memory_id"] in memory_ids or r["later_memory_id"] in memory_ids]
    mems = Memories.get_many(user_id, [r["earlier_memory_id"] for r in rows] + [r["later_memory_id"] for r in rows])
    out = []
    for r in rows:
        a, b = mems.get(r["earlier_memory_id"]), mems.get(r["later_memory_id"])
        if a and b:
            out.append(ChangePointOut(id=r["id"], subject=r["subject"], change_type=r["change_type"],
                                      magnitude=r["magnitude"], earlier=a, later=b, from_date=r["from_date"],
                                      to_date=r["to_date"], uncertainty=r["uncertainty"]))
    return out


def relationships(user_id: str, relation_type: Optional[str] = None, memory_ids: Optional[set] = None,
                  hydrate: bool = True) -> List[RelationshipOut]:
    rows = Analysis.relationships(user_id, relation_type)
    if memory_ids is not None:
        rows = [r for r in rows if r["source_memory_id"] in memory_ids or r["target_memory_id"] in memory_ids]
    mems = Memories.get_many(user_id, [r["source_memory_id"] for r in rows] + [r["target_memory_id"] for r in rows]) \
        if hydrate else {}
    return [RelationshipOut(id=r["id"], source_memory_id=r["source_memory_id"],
                            target_memory_id=r["target_memory_id"], relation_type=r["relation_type"],
                            confidence=r["confidence"], rationale=r["rationale"],
                            source=mems.get(r["source_memory_id"]), target=mems.get(r["target_memory_id"]))
            for r in rows]


def subject_trajectory(user_id: str, subject: str) -> List[dict]:
    """Stance over time for one entity/topic — powers the evolution chart."""
    mems = Memories.list(user_id, entity=subject) or Memories.list(user_id, topic=subject)
    if not mems:
        mems = [m for m in Memories.list(user_id) if subject.lower() in m.statement.lower()]
    return [{"date": m.event_date_start, "stance": m.stance_polarity, "sentiment": m.sentiment,
             "statement": m.statement, "memory_id": m.id, "memory_type": m.memory_type.value}
            for m in mems if m.event_date_start]


def subjects(user_id: str, limit: int = 40) -> List[dict]:
    counts: Dict[str, dict] = {}
    for m in Memories.list(user_id):
        for s in m.entities:
            counts.setdefault(s, {"name": s, "kind": "entity", "count": 0, "years": set()})
            counts[s]["count"] += 1
            if m.event_date_start:
                counts[s]["years"].add(m.event_date_start[:4])
        for t in m.topics:
            counts.setdefault(t, {"name": t, "kind": "topic", "count": 0, "years": set()})
            counts[t]["count"] += 1
            if m.event_date_start:
                counts[t]["years"].add(m.event_date_start[:4])
    items = sorted(counts.values(), key=lambda x: (-len(x["years"]), -x["count"]))[:limit]
    return [{**x, "years": sorted(x["years"])} for x in items]
