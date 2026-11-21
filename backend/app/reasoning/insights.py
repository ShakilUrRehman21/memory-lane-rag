"""Dashboard insights: activity, mood, themes over time, on-this-day, streaks."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List

from app.reasoning.analysis import change_points
from app.storage.repo import Analysis, Documents, Memories


def overview(user_id: str) -> Dict[str, Any]:
    mems = Memories.list(user_id)
    docs = Documents.list(user_id)
    today = date.today()

    by_type = Counter(m.memory_type.value for m in mems)
    by_year: Dict[str, Counter] = defaultdict(Counter)
    mood: Dict[str, List[float]] = defaultdict(list)
    heat: Counter = Counter()
    entity_counts: Counter = Counter()
    for m in mems:
        entity_counts.update(m.entities)
        if not m.event_date_start:
            continue
        y = m.event_date_start[:4]
        for t in m.topics or ["Other"]:
            by_year[y][t] += 1
        mood[m.event_date_start[:7]].append(m.sentiment)
    for d in docs:
        if d.document_date:
            heat[d.document_date[:10]] += 1

    years = sorted(by_year)
    topics_all = Counter()
    for c in by_year.values():
        topics_all.update(c)
    top_topics = [t for t, _ in topics_all.most_common(7)]

    on_this_day = [m for m in mems if m.event_date_start and len(m.event_date_start) >= 10
                   and m.event_date_start[5:10] == today.isoformat()[5:10] and m.event_date_start[:4] != str(today.year)]
    if not on_this_day:  # fall back to the same month in earlier years
        on_this_day = [m for m in mems if m.event_date_start and m.event_date_start[5:7] == f"{today.month:02d}"
                       and m.event_date_start[:4] != str(today.year)]
    on_this_day.sort(key=lambda m: -m.importance)

    # writing streak (consecutive days with a document, ending today or yesterday)
    days = {d.document_date[:10] for d in docs if d.document_date} | {d.created_at[:10] for d in docs}
    streak, cursor = 0, today
    if cursor.isoformat() not in days:
        cursor -= timedelta(days=1)
    while cursor.isoformat() in days:
        streak += 1
        cursor -= timedelta(days=1)

    highlights = sorted([m for m in mems if m.importance >= 0.7], key=lambda m: -m.importance)[:6]
    pinned = [m for m in mems if m.pinned][:6]

    return {
        "counts": {
            "documents": len(docs), "memories": len(mems), "words": sum(d.word_count for d in docs),
            "years": len(years), "changes": len(Analysis.changes(user_id)),
            "contradictions": len(Analysis.relationships(user_id, "contradicts")),
            "entities": len(entity_counts),
        },
        "span": {"start": mems[0].event_date_start if mems else None,
                 "end": max((m.event_date_start or "" for m in mems), default=None) or None},
        "by_type": dict(by_type.most_common()),
        "topics_by_year": [{"year": y, **{t: by_year[y].get(t, 0) for t in top_topics}} for y in years],
        "top_topics": top_topics,
        "top_entities": [{"name": n, "count": c} for n, c in entity_counts.most_common(24)],
        "mood": [{"month": k, "value": round(sum(v) / len(v), 3), "count": len(v)} for k, v in sorted(mood.items())],
        "heatmap": [{"date": k, "count": v} for k, v in sorted(heat.items())],
        "on_this_day": [m.model_dump() for m in on_this_day[:5]],
        "highlights": [m.model_dump() for m in highlights],
        "pinned": [m.model_dump() for m in pinned],
        "recent_changes": [c.model_dump() for c in change_points(user_id)[-4:]][::-1],
        "streak_days": streak,
        "recent_documents": [d.model_dump() for d in sorted(docs, key=lambda d: d.created_at, reverse=True)[:5]],
    }


def graph(user_id: str, limit: int = 400) -> Dict[str, Any]:
    mems = sorted(Memories.list(user_id), key=lambda m: -m.importance)[:limit]
    ids = {m.id for m in mems}
    edges = [r for r in Analysis.relationships(user_id)
             if r["source_memory_id"] in ids and r["target_memory_id"] in ids]
    degree: Counter = Counter()
    for e in edges:
        degree[e["source_memory_id"]] += 1
        degree[e["target_memory_id"]] += 1
    nodes = [{"id": m.id, "label": m.statement[:70] + ("…" if len(m.statement) > 70 else ""),
              "statement": m.statement, "type": m.memory_type.value, "date": m.event_date_start,
              "document_title": m.document_title, "document_id": m.document_id, "entities": m.entities,
              "topics": m.topics, "stance": m.stance_polarity, "importance": m.importance,
              "degree": degree[m.id]} for m in mems]
    links = [{"id": e["id"], "source": e["source_memory_id"], "target": e["target_memory_id"],
              "type": e["relation_type"], "confidence": e["confidence"], "rationale": e["rationale"]} for e in edges]
    return {"nodes": nodes, "edges": links}
