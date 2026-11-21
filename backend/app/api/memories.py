import json
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.core.database import get_db
from app.core.security import CurrentUser
from app.ingestion import extractor
from app.ingestion.dates import parse_date
from app.ingestion.service import capture
from app.models.schemas import MemoryCapture, MemoryOut, MemoryPage, MemoryUpdate
from app.reasoning import analysis
from app.storage import vectors
from app.storage.repo import Memories

router = APIRouter(prefix="/memories", tags=["memories"])


@router.get("", response_model=MemoryPage)
def list_memories(q: Optional[str] = None, memory_type: Optional[str] = None, topic: Optional[str] = None,
                  entity: Optional[str] = None, start_year: Optional[int] = None, end_year: Optional[int] = None,
                  pinned: Optional[bool] = None, order: str = "asc", limit: int = 500, offset: int = 0,
                  user=CurrentUser):
    items = Memories.list(user.id, q=q, memory_type=memory_type, topic=topic, entity=entity, start_year=start_year,
                          end_year=end_year, pinned=pinned, order=order)
    return MemoryPage(items=items[offset:offset + min(limit, 2000)], total=len(items))


@router.post("", response_model=MemoryOut)
def capture_memory(body: MemoryCapture, user=CurrentUser):
    if len(body.statement.strip()) < 3:
        raise HTTPException(400, "Write a little more first.")
    mid = capture(user.id, body.statement, body.memory_type, body.event_date, body.context_note, body.tags)
    return Memories.get(user.id, mid)


@router.get("/subjects")
def subjects(user=CurrentUser):
    return analysis.subjects(user.id)


@router.get("/trajectory")
def trajectory(subject: str, user=CurrentUser):
    return {"subject": subject, "points": analysis.subject_trajectory(user.id, subject),
            "changes": [c.model_dump() for c in analysis.change_points(user.id, subject=subject)]}


@router.get("/{memory_id}")
def get_memory(memory_id: str, user=CurrentUser):
    m = Memories.get(user.id, memory_id)
    if not m:
        raise HTTPException(404, "Memory not found.")
    related = analysis.relationships(user.id, memory_ids={memory_id})
    similar = [s for s in vectors.search(user.id, m.statement, "memory", 7) if s["id"] != memory_id][:5]
    sim_mems = Memories.get_many(user.id, [s["id"] for s in similar])
    context = Memories.chunk_text([m.chunk_id]).get(m.chunk_id or "", "")
    return {"memory": m, "context": context,
            "related": [r.model_dump() for r in related[:12]],
            "similar": [{"memory": sim_mems[s["id"]], "score": round(s["score"], 3)} for s in similar
                        if s["id"] in sim_mems]}


@router.patch("/{memory_id}", response_model=MemoryOut)
def update_memory(memory_id: str, body: MemoryUpdate, user=CurrentUser):
    m = Memories.get(user.id, memory_id)
    if not m:
        raise HTTPException(404, "Memory not found.")
    fields = {}
    if body.statement is not None and body.statement.strip() and body.statement != m.statement:
        s = body.statement.strip()
        ents = extractor.entities(s)
        fields.update(statement=s, stance_polarity=extractor.stance(s), sentiment=extractor.sentiment(s),
                      entities=json.dumps(ents),
                      topics=json.dumps(extractor.topics(s, ents)))
    if body.memory_type is not None:
        fields["memory_type"] = body.memory_type.value
    if body.event_date:
        d = parse_date(body.event_date)
        if not d:
            raise HTTPException(400, "Couldn't understand that date.")
        fields.update(event_date_start=d, event_date_end=d, date_granularity="day", date_confidence=1.0,
                      date_source="user_override")
    if body.pinned is not None:
        fields["pinned"] = body.pinned
    Memories.update(user.id, memory_id, **fields)
    if "statement" in fields:
        new = Memories.get(user.id, memory_id)
        with get_db() as c:
            vectors.store(c, user.id, "memory", [(memory_id, vectors.memory_text(new.statement, new.entities,
                                                                                 new.topics))])
            c.execute("UPDATE memories_fts SET entities=?, topics=? WHERE id=?",
                      (" ".join(new.entities), " ".join(new.topics), memory_id))
    if set(fields) - {"pinned"}:
        analysis.refresh_analysis(user.id)
    return Memories.get(user.id, memory_id)


@router.delete("/{memory_id}")
def delete_memory(memory_id: str, user=CurrentUser):
    if not Memories.delete(user.id, memory_id):
        raise HTTPException(404, "Memory not found.")
    analysis.refresh_analysis(user.id)
    return {"ok": True}
