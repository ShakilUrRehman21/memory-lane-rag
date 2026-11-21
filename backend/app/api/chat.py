import json
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from app.core.security import CurrentUser
from app.models.schemas import AnswerPayload, ChatRequest, ConversationDetail
from app.storage.repo import Conversations
from app.synthesis.answer import answer, answer_stream

router = APIRouter(tags=["chat"])


class ConvUpdate(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None


class Feedback(BaseModel):
    value: int  # -1, 0, 1


def _prepare(user_id: str, req: ChatRequest):
    q = req.query.strip()
    if not q:
        raise HTTPException(400, "Ask something first.")
    if len(q) > 2000:
        raise HTTPException(400, "That question is too long (2000 characters max).")
    if req.conversation_id:
        if not Conversations.owns(user_id, req.conversation_id):
            raise HTTPException(404, "Conversation not found.")
        cid = req.conversation_id
    else:
        cid = Conversations.create(user_id, q[:80])
    history = Conversations.history(cid)
    Conversations.add_message(cid, "user", q)
    return cid, history


@router.post("/chat/stream")
def chat_stream(req: ChatRequest, user=CurrentUser):
    """Server-sent events: conversation → meta → token… → done (or error)."""
    cid, history = _prepare(user.id, req)

    def sse(event: str, data) -> str:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    def gen():
        yield sse("conversation", {"conversation_id": cid})
        try:
            offline = None
            for kind, data in answer_stream(user.id, req, history):
                if kind == "meta":
                    offline = data["provider"] == "Offline writer"
                    yield sse("meta", data)
                elif kind == "token":
                    yield sse("token", {"t": data})
                    if offline:
                        time.sleep(0.012)  # gentle typing rhythm for the local writer
                elif kind == "done":
                    payload: AnswerPayload = data
                    mid = Conversations.add_message(cid, "assistant", payload.answer, payload.model_dump())
                    yield sse("done", {"message_id": mid, **payload.model_dump()})
        except Exception as exc:  # pragma: no cover - surfaced to the UI
            yield sse("error", {"detail": f"Something went wrong while answering: {exc}"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/chat", response_model=AnswerPayload)
def chat(req: ChatRequest, user=CurrentUser):
    cid, history = _prepare(user.id, req)
    payload = answer(user.id, req, history)
    Conversations.add_message(cid, "assistant", payload.answer, payload.model_dump())
    return payload


@router.get("/conversations")
def list_conversations(q: Optional[str] = None, user=CurrentUser):
    return Conversations.list(user.id, q)


@router.get("/conversations/{cid}", response_model=ConversationDetail)
def get_conversation(cid: str, user=CurrentUser):
    conv = Conversations.get(user.id, cid)
    if not conv:
        raise HTTPException(404, "Conversation not found.")
    return conv


@router.patch("/conversations/{cid}")
def update_conversation(cid: str, body: ConvUpdate, user=CurrentUser):
    if not Conversations.owns(user.id, cid):
        raise HTTPException(404, "Conversation not found.")
    Conversations.update(user.id, cid, body.title, body.pinned)
    return {"ok": True}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: str, user=CurrentUser):
    if not Conversations.delete(user.id, cid):
        raise HTTPException(404, "Conversation not found.")
    return {"ok": True}


@router.post("/messages/{message_id}/feedback")
def feedback(message_id: str, body: Feedback, user=CurrentUser):
    Conversations.feedback(user.id, message_id, max(-1, min(1, body.value)))
    return {"ok": True}


@router.get("/conversations/{cid}/export")
def export_conversation(cid: str, user=CurrentUser):
    conv = Conversations.get(user.id, cid)
    if not conv:
        raise HTTPException(404, "Conversation not found.")
    lines = [f"# {conv.title}", "", f"_Exported from Memory Lane · {conv.updated_at[:10]}_", ""]
    for m in conv.messages:
        if m.role == "user":
            lines += [f"## {m.content}", ""]
        else:
            lines += [m.content, ""]
            cites = m.payload.get("citations") or []
            used = set(m.payload.get("used_citations") or [])
            if cites:
                lines.append("**Sources**")
                for c in cites:
                    if not used or c["index"] in used:
                        lines.append(f"{c['index']}. {c.get('date') or 'undated'} · {c['document_title']} — "
                                     f"“{c['statement']}”")
                lines.append("")
    return PlainTextResponse("\n".join(lines), headers={
        "Content-Disposition": f'attachment; filename="memory-lane-{cid}.md"'})
