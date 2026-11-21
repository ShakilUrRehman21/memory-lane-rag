"""Timeline, evolution analysis, graph, insights, global search."""
from collections import OrderedDict
from typing import Optional

from fastapi import APIRouter

from app.core.security import CurrentUser
from app.reasoning import analysis, insights
from app.storage import vectors
from app.storage.repo import Documents, Memories

router = APIRouter(tags=["insights"])


@router.get("/insights")
def get_insights(user=CurrentUser):
    return insights.overview(user.id)


@router.get("/timeline")
def timeline(q: Optional[str] = None, memory_type: Optional[str] = None, topic: Optional[str] = None,
             entity: Optional[str] = None, start_year: Optional[int] = None, end_year: Optional[int] = None,
             user=CurrentUser):
    mems = Memories.list(user.id, q=q, memory_type=memory_type, topic=topic, entity=entity, start_year=start_year,
                         end_year=end_year)
    groups: "OrderedDict[str, list]" = OrderedDict()
    for m in mems:
        groups.setdefault((m.event_date_start or "Undated")[:4], []).append(m.model_dump())
    change_ids = {}
    for c in analysis.change_points(user.id):
        change_ids[c.later.id] = {"subject": c.subject, "change_type": c.change_type}
    return {"years": [{"year": y, "memories": ms} for y, ms in groups.items()], "total": len(mems),
            "change_markers": change_ids}


@router.get("/changes")
def changes(subject: Optional[str] = None, user=CurrentUser):
    return analysis.change_points(user.id, subject=subject)


@router.get("/contradictions")
def contradictions(user=CurrentUser):
    return analysis.relationships(user.id, "contradicts")


@router.get("/graph")
def graph(limit: int = 400, user=CurrentUser):
    return insights.graph(user.id, min(limit, 1500))


@router.post("/analysis/refresh")
def refresh(user=CurrentUser):
    analysis.refresh_analysis(user.id)
    return {"ok": True}


@router.get("/search")
def search(q: str, limit: int = 8, user=CurrentUser):
    q = q.strip()
    if not q:
        return {"memories": [], "documents": []}
    lexical = {r["id"]: r["score"] for r in Memories.fts(user.id, q, 30)}
    semantic = {r["id"]: r["score"] for r in vectors.search(user.id, q, "memory", 30)}
    ranked = sorted(set(lexical) | set(semantic),
                    key=lambda i: -((1 if i in lexical else 0) * 0.6 + semantic.get(i, 0)))[:limit]
    mems = Memories.get_many(user.id, ranked)
    docs = Documents.list(user.id, q=q)[:limit]
    return {"memories": [mems[i] for i in ranked if i in mems], "documents": docs}
