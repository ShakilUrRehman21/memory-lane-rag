"""Ingestion pipeline: bytes → text → dated sections → chunks → memories → FTS + vectors → analysis."""
from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from typing import List, Optional

from app.core.config import settings
from app.core.database import get_db
from app.ingestion import extractor
from app.ingestion.dates import infer_document_date, parse_date
from app.ingestion.parsers import parse_bytes
from app.models.schemas import DateGranularity, DateSource, MemoryType
from app.storage import vectors
from app.storage.repo import Documents, new_id

SERIES_RE = re.compile(r"(resume|cv|proposal|statement|portfolio|plan|thesis|essay|bio)[ _-]*(v\d+|\d{4})", re.I)


class DuplicateDocument(Exception):
    def __init__(self, document_id: str):
        super().__init__(document_id)
        self.document_id = document_id


def _safe_name(name: str) -> str:
    base = Path(name).name
    stem = re.sub(r"[^\w.\- ]+", "_", Path(base).stem).strip() or "document"
    return f"{stem[:80]}{Path(base).suffix.lower()}"


def _title_from(name: str, meta: dict, text: str) -> str:
    if meta.get("title"):
        return str(meta["title"])[:160]
    first = next((ln.strip("# ").strip() for ln in text.splitlines() if ln.strip()), "")
    if first.startswith("#") or (0 < len(first) <= 70 and not first.endswith(".")) and not parse_date(first):
        return first.lstrip("# ")[:160]
    return Path(name).stem.replace("_", " ").replace("-", " ").strip().title()[:160]


def ingest_bytes(user_id: str, file_name: str, data: bytes, *, title: Optional[str] = None,
                 document_date: Optional[str] = None, tags: Optional[List[str]] = None,
                 source_type: str = "upload", allow_duplicate: bool = False, refresh: bool = True) -> str:
    sha = hashlib.sha256(data).hexdigest()
    if not allow_duplicate and (existing := Documents.find_by_hash(user_id, sha)):
        raise DuplicateDocument(existing)

    safe = _safe_name(file_name)
    text, meta = parse_bytes(safe, data)
    if not text.strip():
        raise ValueError("No readable text was found in this file.")

    if document_date:
        doc_date, conf = parse_date(document_date) or document_date[:10], 1.0
    else:
        doc_date, conf = infer_document_date(safe, text, meta)

    doc_id = new_id("doc")
    file_path = None
    if source_type == "upload":
        user_dir = settings.UPLOADS_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        path = user_dir / f"{doc_id}_{safe}"
        path.write_bytes(data)
        file_path = str(path)

    series = SERIES_RE.search(Path(safe).stem)
    doc = {
        "id": doc_id, "user_id": user_id, "title": (title or _title_from(safe, meta, text)).strip() or "Untitled",
        "source_type": source_type, "file_name": safe, "file_path": file_path,
        "file_type": Path(safe).suffix.lstrip(".") or "txt", "file_size": len(data), "hash_sha256": sha,
        "document_date": doc_date, "date_confidence": conf, "content": text,
        "tags": sorted({t.strip().lower() for t in (tags or []) if t.strip()}),
        "series_name": series.group(1).capitalize() if series else None,
        "version_label": series.group(2).lower() if series else None, "metadata": meta,
    }
    with get_db() as conn:
        Documents.insert(conn, doc)
        _index_content(conn, user_id, doc_id, text, doc_date)
    if refresh:
        from app.reasoning.analysis import refresh_analysis
        refresh_analysis(user_id)
    return doc_id


def ingest_text(user_id: str, content: str, title: str = "", document_date: Optional[str] = None,
                tags: Optional[List[str]] = None, source_type: str = "note", refresh: bool = True) -> str:
    name = (re.sub(r"[^\w]+", "_", title.lower()).strip("_") or "note") + ".md"
    return ingest_bytes(user_id, name, content.encode("utf-8"), title=title or None, document_date=document_date,
                        tags=tags, source_type=source_type, allow_duplicate=True, refresh=refresh)


def _index_content(conn, user_id: str, doc_id: str, text: str, doc_date: Optional[str]) -> None:
    chunks = extractor.chunk_text(text, doc_date)
    chunk_ids = {}
    for ch in chunks:
        cid = f"{doc_id}_c{ch.index}"
        chunk_ids[ch.index] = cid
        conn.execute("INSERT INTO chunks (id,document_id,user_id,chunk_index,content,start_char,end_char) "
                     "VALUES (?,?,?,?,?,?,?)", (cid, doc_id, user_id, ch.index, ch.content, ch.start, ch.end))
    vectors.store(conn, user_id, "chunk", [(chunk_ids[c.index], c.content) for c in chunks])

    from app.storage.repo import Memories
    mem_items = []
    for i, m in enumerate(extractor.extract(chunks, doc_date)):
        mid = f"{doc_id}_m{i}"
        Memories.insert(conn, {
            "id": mid, "user_id": user_id, "document_id": doc_id, "chunk_id": chunk_ids.get(m.chunk_index),
            "memory_type": m.memory_type.value, "statement": m.statement, "event_date_start": m.date["start"],
            "event_date_end": m.date["end"], "date_granularity": m.date["granularity"].value,
            "date_confidence": m.date["confidence"], "date_source": m.date["source"].value,
            "stance_polarity": m.stance, "sentiment": m.sentiment, "importance": m.importance,
            "entities": m.entities, "topics": m.topics,
        })
        mem_items.append((mid, vectors.memory_text(m.statement, m.entities, m.topics)))
    vectors.store(conn, user_id, "memory", mem_items)


def reprocess(user_id: str, doc_id: str) -> None:
    """Re-run chunking & extraction (after the document date changes)."""
    raw = Documents.raw(user_id, doc_id)
    if not raw:
        return
    with get_db() as conn:
        mids = [r["id"] for r in conn.execute("SELECT id FROM memories WHERE document_id=?", (doc_id,))]
        cids = [r["id"] for r in conn.execute("SELECT id FROM chunks WHERE document_id=?", (doc_id,))]
        for mid in mids:
            conn.execute("DELETE FROM memories_fts WHERE id=?", (mid,))
            conn.execute("DELETE FROM embeddings WHERE item_id=? AND kind='memory'", (mid,))
        for cid in cids:
            conn.execute("DELETE FROM embeddings WHERE item_id=? AND kind='chunk'", (cid,))
        conn.execute("DELETE FROM memories WHERE document_id=?", (doc_id,))
        conn.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
        _index_content(conn, user_id, doc_id, raw["content"], raw["document_date"])
    vectors.invalidate(user_id)
    from app.reasoning.analysis import refresh_analysis
    refresh_analysis(user_id)


def capture(user_id: str, statement: str, memory_type: Optional[MemoryType] = None,
            event_date: Optional[str] = None, context_note: Optional[str] = None,
            tags: Optional[List[str]] = None) -> str:
    """Quick-capture a single thought as its own tiny document + memory. Returns memory id."""
    today = date.today().isoformat()
    when = parse_date(event_date) if event_date else today
    when = when or today
    statement = statement.strip()
    doc_id = new_id("cap")
    content = statement + (f"\n\n{context_note.strip()}" if context_note else "")
    sha = hashlib.sha256(f"{doc_id}{content}".encode()).hexdigest()
    ents = extractor.entities(statement)
    st, sent = extractor.stance(statement), extractor.sentiment(statement)
    mtype = memory_type or extractor.classify(statement)
    from app.storage.repo import Memories
    with get_db() as conn:
        Documents.insert(conn, {
            "id": doc_id, "user_id": user_id, "title": statement[:60] + ("…" if len(statement) > 60 else ""),
            "source_type": "capsule", "file_type": "capsule", "file_size": len(content), "hash_sha256": sha,
            "document_date": when, "date_confidence": 1.0, "content": content, "tags": tags or [],
        })
        cid = f"{doc_id}_c0"
        conn.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?)", (cid, doc_id, user_id, 0, content, 0, len(content)))
        vectors.store(conn, user_id, "chunk", [(cid, content)])
        mid = f"{doc_id}_m0"
        tps = extractor.topics(statement, ents)
        Memories.insert(conn, {
            "id": mid, "user_id": user_id, "document_id": doc_id, "chunk_id": cid, "memory_type": mtype.value,
            "statement": statement, "event_date_start": when, "event_date_end": when,
            "date_granularity": DateGranularity.DAY.value, "date_confidence": 1.0,
            "date_source": DateSource.USER_OVERRIDE.value, "stance_polarity": st, "sentiment": sent,
            "importance": extractor.importance(statement, mtype, st, sent), "entities": ents, "topics": tps,
        })
        vectors.store(conn, user_id, "memory", [(mid, vectors.memory_text(statement, ents, tps))])
    from app.reasoning.analysis import refresh_analysis
    refresh_analysis(user_id)
    return mid
