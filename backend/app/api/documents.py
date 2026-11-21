from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from app.core.config import settings
from app.core.security import CurrentUser
from app.ingestion.service import DuplicateDocument, ingest_bytes, ingest_text, reprocess
from app.models.schemas import DocumentDetail, DocumentOut, DocumentUpdate, NoteCreate
from app.reasoning.analysis import refresh_analysis
from app.reasoning.versions import compare
from app.storage.repo import Documents, Memories

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=List[DocumentOut])
def list_documents(q: Optional[str] = None, tag: Optional[str] = None, favorite: Optional[bool] = None,
                   sort: str = "date", user=CurrentUser):
    return Documents.list(user.id, q=q, tag=tag, favorite=favorite, sort=sort)


@router.get("/tags")
def tags(user=CurrentUser):
    return Documents.tags(user.id)


@router.get("/series")
def series(user=CurrentUser):
    return Documents.series(user.id)


@router.get("/compare")
def compare_documents(earlier: str, later: str, user=CurrentUser):
    diff = compare(user.id, earlier, later)
    if not diff:
        raise HTTPException(404, "One of those documents wasn't found.")
    return diff


@router.post("/upload")
async def upload(files: List[UploadFile] = File(...), document_date: Optional[str] = Form(None),
                 tags: Optional[str] = Form(None), user=CurrentUser):
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    results = []
    for f in files:
        data = await f.read(limit + 1)
        name = f.filename or "upload.txt"
        if len(data) > limit:
            results.append({"file": name, "status": "error", "detail": f"Larger than {settings.MAX_UPLOAD_MB} MB."})
            continue
        try:
            doc_id = ingest_bytes(user.id, name, data, document_date=document_date or None, tags=tag_list,
                                  refresh=False)
            results.append({"file": name, "status": "ok", "document": Documents.get(user.id, doc_id).model_dump()})
        except DuplicateDocument as dup:
            results.append({"file": name, "status": "duplicate", "document_id": dup.document_id,
                            "detail": "You've already added this file."})
        except Exception as exc:
            results.append({"file": name, "status": "error", "detail": str(exc)[:300]})
    if any(r["status"] == "ok" for r in results):
        refresh_analysis(user.id)
    return {"results": results}


@router.post("/note", response_model=DocumentOut)
def create_note(body: NoteCreate, user=CurrentUser):
    if not body.content.strip():
        raise HTTPException(400, "Write something first.")
    doc_id = ingest_text(user.id, body.content, body.title.strip(), body.document_date, body.tags)
    return Documents.get(user.id, doc_id)


@router.get("/{doc_id}", response_model=DocumentDetail)
def get_document(doc_id: str, user=CurrentUser):
    doc = Documents.get(user.id, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    raw = Documents.raw(user.id, doc_id)
    return DocumentDetail(**doc.model_dump(), content=raw["content"],
                          memories=Memories.list(user.id, document_id=doc_id))


@router.patch("/{doc_id}", response_model=DocumentOut)
def update_document(doc_id: str, body: DocumentUpdate, user=CurrentUser):
    before = Documents.raw(user.id, doc_id)
    if not before:
        raise HTTPException(404, "Document not found.")
    Documents.update(user.id, doc_id, **body.model_dump(exclude_unset=True))
    if body.document_date is not None and body.document_date != before["document_date"]:
        reprocess(user.id, doc_id)
    return Documents.get(user.id, doc_id)


@router.delete("/{doc_id}")
def delete_document(doc_id: str, user=CurrentUser):
    raw = Documents.raw(user.id, doc_id)
    if not raw or not Documents.delete(user.id, doc_id):
        raise HTTPException(404, "Document not found.")
    if raw.get("file_path"):
        p = Path(raw["file_path"])
        if p.is_file() and settings.UPLOADS_DIR in p.resolve().parents:
            p.unlink(missing_ok=True)
    refresh_analysis(user.id)
    return {"ok": True}


@router.get("/{doc_id}/download")
def download(doc_id: str, user=CurrentUser):
    raw = Documents.raw(user.id, doc_id)
    if not raw:
        raise HTTPException(404, "Document not found.")
    p = Path(raw["file_path"]) if raw.get("file_path") else None
    if p and p.is_file():
        return FileResponse(p, filename=raw["file_name"] or p.name)
    return PlainTextResponse(raw["content"], headers={
        "Content-Disposition": f'attachment; filename="{(raw["title"] or "note")[:60]}.md"'})
