"""Health, provider status, research benchmark, and full-archive export/import."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.ai import llm
from app.ai.embeddings import embedding_status
from app.core.config import settings
from app.core.security import CurrentUser
from app.evaluation.runner import run as run_benchmark
from app.models.schemas import BenchmarkRequest
from app.reasoning.analysis import refresh_analysis
from app.storage import vectors
from app.storage.repo import Conversations, Documents, EvalRuns, Memories

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "service": settings.PROJECT_NAME, "version": settings.VERSION}


@router.get("/system/status")
def status(user=CurrentUser):
    emb = embedding_status()
    return {"llm": {"provider": llm.active_provider(), "label": llm.provider_label()},
            "embeddings": emb, "version": settings.VERSION, "max_upload_mb": settings.MAX_UPLOAD_MB}


@router.post("/system/reindex")
def reindex(user=CurrentUser):
    n = vectors.ensure_fresh(user.id)
    refresh_analysis(user.id)
    return {"reindexed": n}


@router.get("/export")
def export_archive(user=CurrentUser):
    docs = []
    for d in Documents.list(user.id):
        raw = Documents.raw(user.id, d.id)
        docs.append({"title": d.title, "document_date": d.document_date, "tags": d.tags, "favorite": d.favorite,
                     "source_type": d.source_type, "file_name": d.file_name, "content": raw["content"]})
    data = {
        "format": "memory-lane-archive", "version": 2, "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {"username": user.username, "display_name": user.display_name, "bio": user.bio},
        "documents": docs,
        "pinned_statements": [m.statement for m in Memories.list(user.id, pinned=True)],
        "conversations": [Conversations.get(user.id, c.id).model_dump() for c in Conversations.list(user.id)],
    }
    return Response(json.dumps(data, indent=2, default=str), media_type="application/json", headers={
        "Content-Disposition": f'attachment; filename="memory-lane-{user.username}.json"'})


@router.post("/import")
async def import_archive(file: UploadFile = File(...), user=CurrentUser):
    from app.ingestion.service import ingest_text
    try:
        data = json.loads(await file.read())
        assert data.get("format") == "memory-lane-archive"
    except Exception:
        raise HTTPException(400, "That isn't a Memory Lane export file.")
    added = 0
    for d in data.get("documents", []):
        if not (d.get("content") or "").strip():
            continue
        ingest_text(user.id, d["content"], d.get("title") or "", d.get("document_date"), d.get("tags") or [],
                    source_type="import", refresh=False)
        added += 1
    pinned = set(data.get("pinned_statements") or [])
    if pinned:
        for m in Memories.list(user.id):
            if m.statement in pinned:
                Memories.update(user.id, m.id, pinned=True)
    refresh_analysis(user.id)
    return {"imported_documents": added}


@router.post("/research/benchmark")
def benchmark(req: BenchmarkRequest, user=CurrentUser):
    pipes = [p for p in req.pipelines if p in ("baseline", "temporal", "memory_lane")] or ["memory_lane"]
    return run_benchmark(user.id, req.run_name[:80] or "Benchmark", pipes)


@router.get("/research/runs")
def runs(user=CurrentUser):
    return EvalRuns.list(user.id)
