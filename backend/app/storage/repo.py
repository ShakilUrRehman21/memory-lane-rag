"""Data access for all tables. Everything is scoped by user_id."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.core.config import settings
from app.core.database import get_db
from app.models.schemas import (ConversationDetail, ConversationOut, DocumentOut, MemoryOut, MessageOut, UserOut)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _fts_query(q: str) -> str:
    from app.ai.embeddings import STOPWORDS
    from app.retrieval.router import STOP
    words = [w for w in re.findall(r"\w+", q.lower()) if len(w) > 1 and w not in STOP and w not in STOPWORDS
             and w not in ("stop", "start", "using", "use", "feel", "feeling", "been", "much")] \
        or [w for w in re.findall(r"\w+", q.lower()) if len(w) > 2]
    return " OR ".join(f'"{w}"*' for w in words[:24])


# ===================================================================== users
class Users:
    @staticmethod
    def _out(conn, row) -> UserOut:
        uid = row["id"]
        stats = conn.execute(
            """SELECT (SELECT COUNT(*) FROM documents WHERE user_id=?) d,
                      (SELECT COUNT(*) FROM memories WHERE user_id=?) m,
                      (SELECT MIN(event_date_start) FROM memories WHERE user_id=?) lo,
                      (SELECT MAX(event_date_start) FROM memories WHERE user_id=?) hi""",
            (uid, uid, uid, uid)).fetchone()
        return UserOut(id=uid, username=row["username"], display_name=row["display_name"], email=row["email"],
                       avatar_color=row["avatar_color"], bio=row["bio"],
                       preferences=json.loads(row["preferences"] or "{}"), created_at=row["created_at"],
                       document_count=stats["d"], memory_count=stats["m"], earliest_memory_date=stats["lo"],
                       latest_memory_date=stats["hi"])

    @staticmethod
    def create(username: str, display_name: str, email: Optional[str], pw_hash: Optional[str],
               pw_salt: Optional[str], avatar_color: str = "#8b9cff", bio: Optional[str] = None,
               user_id: Optional[str] = None) -> UserOut:
        uid = user_id or new_id("user")
        with get_db() as c:
            c.execute("""INSERT INTO users (id,email,username,password_hash,password_salt,display_name,avatar_color,
                         bio,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                      (uid, email, username, pw_hash, pw_salt, display_name, avatar_color, bio, now_iso()))
        return Users.get(uid)

    @staticmethod
    def get(uid: str) -> Optional[UserOut]:
        with get_db() as c:
            row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            return Users._out(c, row) if row else None

    @staticmethod
    def raw_by_identifier(identifier: str) -> Optional[Dict[str, Any]]:
        with get_db() as c:
            row = c.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?) OR LOWER(email)=LOWER(?)",
                            (identifier, identifier)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def raw(uid: str) -> Optional[Dict[str, Any]]:
        with get_db() as c:
            row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def update(uid: str, **fields) -> Optional[UserOut]:
        fields = {k: v for k, v in fields.items() if v is not None}
        if "preferences" in fields:
            current = json.loads((Users.raw(uid) or {}).get("preferences") or "{}")
            current.update(fields["preferences"])
            fields["preferences"] = json.dumps(current)
        if fields:
            cols = ", ".join(f"{k}=?" for k in fields)
            with get_db() as c:
                c.execute(f"UPDATE users SET {cols} WHERE id=?", (*fields.values(), uid))
        return Users.get(uid)

    @staticmethod
    def delete(uid: str) -> None:
        with get_db() as c:
            c.execute("DELETE FROM memories_fts WHERE user_id=?", (uid,))
            c.execute("DELETE FROM documents_fts WHERE user_id=?", (uid,))
            c.execute("DELETE FROM embeddings WHERE user_id=?", (uid,))
            c.execute("DELETE FROM relationships WHERE user_id=?", (uid,))
            c.execute("DELETE FROM change_points WHERE user_id=?", (uid,))
            c.execute("DELETE FROM evaluation_runs WHERE user_id=?", (uid,))
            c.execute("DELETE FROM users WHERE id=?", (uid,))
        from app.storage.vectors import invalidate
        invalidate(uid)

    # sessions
    @staticmethod
    def create_session(uid: str) -> str:
        from app.core.security import generate_token
        tok = generate_token()
        now = datetime.now(timezone.utc)
        with get_db() as c:
            c.execute("DELETE FROM sessions WHERE expires_at < ?", (now.isoformat(),))
            c.execute("INSERT INTO sessions VALUES (?,?,?,?)",
                      (tok, uid, now.isoformat(), (now + timedelta(days=settings.SESSION_DAYS)).isoformat()))
        return tok

    @staticmethod
    def by_session(token: str) -> Optional[UserOut]:
        with get_db() as c:
            row = c.execute("SELECT user_id, expires_at FROM sessions WHERE token=?", (token,)).fetchone()
            if not row:
                return None
            if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
                c.execute("DELETE FROM sessions WHERE token=?", (token,))
                return None
            urow = c.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()
            return Users._out(c, urow) if urow else None

    @staticmethod
    def delete_session(token: str) -> None:
        with get_db() as c:
            c.execute("DELETE FROM sessions WHERE token=?", (token,))


# ===================================================================== documents
DOC_COLS = """d.id,d.user_id,d.title,d.source_type,d.file_name,d.file_type,d.file_size,d.document_date,
d.date_confidence,d.word_count,d.tags,d.favorite,d.series_name,d.version_label,d.created_at,d.updated_at,
substr(d.content,1,240) AS excerpt,
(SELECT COUNT(*) FROM chunks c WHERE c.document_id=d.id) AS chunk_count,
(SELECT COUNT(*) FROM memories m WHERE m.document_id=d.id) AS memory_count"""


def _doc_out(r) -> DocumentOut:
    return DocumentOut(id=r["id"], user_id=r["user_id"], title=r["title"], source_type=r["source_type"],
                       file_name=r["file_name"], file_type=r["file_type"], file_size=r["file_size"],
                       document_date=r["document_date"], date_confidence=r["date_confidence"],
                       word_count=r["word_count"], tags=json.loads(r["tags"]), favorite=bool(r["favorite"]),
                       series_name=r["series_name"], version_label=r["version_label"],
                       excerpt=re.sub(r"\s+", " ", r["excerpt"] or "").strip(), created_at=r["created_at"],
                       updated_at=r["updated_at"], chunk_count=r["chunk_count"], memory_count=r["memory_count"])


class Documents:
    @staticmethod
    def find_by_hash(uid: str, sha: str) -> Optional[str]:
        with get_db() as c:
            row = c.execute("SELECT id FROM documents WHERE user_id=? AND hash_sha256=?", (uid, sha)).fetchone()
            return row["id"] if row else None

    @staticmethod
    def insert(conn, doc: Dict[str, Any]) -> None:
        now = now_iso()
        conn.execute("""INSERT INTO documents (id,user_id,title,source_type,file_name,file_path,file_type,file_size,
            hash_sha256,document_date,date_confidence,content,word_count,tags,favorite,series_name,version_label,
            metadata,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (doc["id"], doc["user_id"], doc["title"], doc["source_type"], doc.get("file_name"),
                      doc.get("file_path"), doc["file_type"], doc.get("file_size", 0), doc["hash_sha256"],
                      doc.get("document_date"), doc.get("date_confidence", 0), doc["content"],
                      len(doc["content"].split()), json.dumps(doc.get("tags", [])), 0, doc.get("series_name"),
                      doc.get("version_label"), json.dumps(doc.get("metadata", {})), now, now))
        conn.execute("INSERT INTO documents_fts (id,user_id,title,content) VALUES (?,?,?,?)",
                     (doc["id"], doc["user_id"], doc["title"], doc["content"]))

    @staticmethod
    def list(uid: str, q: Optional[str] = None, tag: Optional[str] = None, favorite: Optional[bool] = None,
             sort: str = "date") -> List[DocumentOut]:
        sql = f"SELECT {DOC_COLS} FROM documents d WHERE d.user_id=?"
        params: List[Any] = [uid]
        if q:
            sql += " AND d.id IN (SELECT id FROM documents_fts WHERE documents_fts MATCH ? AND user_id=?)"
            params += [_fts_query(q) or '""', uid]
        if favorite:
            sql += " AND d.favorite=1"
        order = {"date": "COALESCE(d.document_date,'0000') DESC", "created": "d.created_at DESC",
                 "title": "d.title COLLATE NOCASE ASC"}.get(sort, "COALESCE(d.document_date,'0000') DESC")
        sql += f" ORDER BY {order}"
        with get_db() as c:
            docs = [_doc_out(r) for r in c.execute(sql, params).fetchall()]
        if tag:
            docs = [d for d in docs if tag in d.tags]
        return docs

    @staticmethod
    def get(uid: str, doc_id: str) -> Optional[DocumentOut]:
        with get_db() as c:
            r = c.execute(f"SELECT {DOC_COLS} FROM documents d WHERE d.id=? AND d.user_id=?", (doc_id, uid)).fetchone()
            return _doc_out(r) if r else None

    @staticmethod
    def raw(uid: str, doc_id: str) -> Optional[Dict[str, Any]]:
        with get_db() as c:
            r = c.execute("SELECT * FROM documents WHERE id=? AND user_id=?", (doc_id, uid)).fetchone()
            return dict(r) if r else None

    @staticmethod
    def update(uid: str, doc_id: str, **fields) -> None:
        fields = {k: v for k, v in fields.items() if v is not None}
        if "tags" in fields:
            fields["tags"] = json.dumps(sorted({t.strip().lower() for t in fields["tags"] if t.strip()}))
        if "favorite" in fields:
            fields["favorite"] = int(bool(fields["favorite"]))
        if not fields:
            return
        fields["updated_at"] = now_iso()
        cols = ", ".join(f"{k}=?" for k in fields)
        with get_db() as c:
            c.execute(f"UPDATE documents SET {cols} WHERE id=? AND user_id=?", (*fields.values(), doc_id, uid))
            if "title" in fields:
                c.execute("UPDATE documents_fts SET title=? WHERE id=?", (fields["title"], doc_id))

    @staticmethod
    def delete(uid: str, doc_id: str) -> bool:
        with get_db() as c:
            mem_ids = [r["id"] for r in c.execute("SELECT id FROM memories WHERE document_id=? AND user_id=?",
                                                    (doc_id, uid))]
            chunk_ids = [r["id"] for r in c.execute("SELECT id FROM chunks WHERE document_id=?", (doc_id,))]
            cur = c.execute("DELETE FROM documents WHERE id=? AND user_id=?", (doc_id, uid))
            if not cur.rowcount:
                return False
            c.execute("DELETE FROM documents_fts WHERE id=?", (doc_id,))
            _delete_many(c, "DELETE FROM memories_fts WHERE id IN ({})", mem_ids)
            _delete_many(c, "DELETE FROM embeddings WHERE kind='memory' AND item_id IN ({})", mem_ids)
            _delete_many(c, "DELETE FROM embeddings WHERE kind='chunk' AND item_id IN ({})", chunk_ids)
        from app.storage.vectors import invalidate
        invalidate(uid)
        return True

    @staticmethod
    def tags(uid: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        with get_db() as c:
            for r in c.execute("SELECT tags FROM documents WHERE user_id=?", (uid,)):
                for t in json.loads(r["tags"]):
                    counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    @staticmethod
    def series(uid: str) -> Dict[str, List[DocumentOut]]:
        out: Dict[str, List[DocumentOut]] = {}
        with get_db() as c:
            rows = c.execute(f"""SELECT {DOC_COLS} FROM documents d WHERE d.user_id=? AND d.series_name IS NOT NULL
                                ORDER BY COALESCE(d.document_date,'0000'), d.created_at""", (uid,)).fetchall()
        for r in rows:
            out.setdefault(r["series_name"], []).append(_doc_out(r))
        return out

    @staticmethod
    def chunks(doc_id: str) -> List[Dict[str, Any]]:
        with get_db() as c:
            return [dict(r) for r in c.execute("SELECT * FROM chunks WHERE document_id=? ORDER BY chunk_index",
                                               (doc_id,))]


def _delete_many(conn, sql: str, ids: Sequence[str]) -> None:
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        conn.execute(sql.format(",".join("?" * len(part))), part)


# ===================================================================== memories
MEM_SELECT = """SELECT m.*, d.title AS document_title FROM memories m JOIN documents d ON d.id=m.document_id"""


def mem_out(r) -> MemoryOut:
    return MemoryOut(id=r["id"], user_id=r["user_id"], document_id=r["document_id"],
                     document_title=r["document_title"], chunk_id=r["chunk_id"], memory_type=r["memory_type"],
                     statement=r["statement"], event_date_start=r["event_date_start"],
                     event_date_end=r["event_date_end"], date_granularity=r["date_granularity"],
                     date_confidence=r["date_confidence"], date_source=r["date_source"],
                     stance_polarity=r["stance_polarity"], sentiment=r["sentiment"], importance=r["importance"],
                     entities=json.loads(r["entities"]), topics=json.loads(r["topics"]), pinned=bool(r["pinned"]),
                     created_at=r["created_at"])


class Memories:
    @staticmethod
    def insert(conn, m: Dict[str, Any]) -> None:
        conn.execute("""INSERT INTO memories (id,user_id,document_id,chunk_id,memory_type,statement,event_date_start,
            event_date_end,date_granularity,date_confidence,date_source,stance_polarity,sentiment,importance,entities,
            topics,pinned,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (m["id"], m["user_id"], m["document_id"], m.get("chunk_id"), m["memory_type"], m["statement"],
                      m.get("event_date_start"), m.get("event_date_end"), m["date_granularity"],
                      m["date_confidence"], m["date_source"], m["stance_polarity"], m["sentiment"], m["importance"],
                      json.dumps(m["entities"]), json.dumps(m["topics"]), int(m.get("pinned", 0)), now_iso()))
        conn.execute("INSERT INTO memories_fts (id,user_id,statement,entities,topics) VALUES (?,?,?,?,?)",
                     (m["id"], m["user_id"], m["statement"], " ".join(m["entities"]), " ".join(m["topics"])))

    @staticmethod
    def get(uid: str, mid: str) -> Optional[MemoryOut]:
        with get_db() as c:
            r = c.execute(MEM_SELECT + " WHERE m.id=? AND m.user_id=?", (mid, uid)).fetchone()
            return mem_out(r) if r else None

    @staticmethod
    def get_many(uid: str, ids: Iterable[str]) -> Dict[str, MemoryOut]:
        ids = list(dict.fromkeys(ids))
        out: Dict[str, MemoryOut] = {}
        with get_db() as c:
            for i in range(0, len(ids), 500):
                part = ids[i:i + 500]
                q = MEM_SELECT + f" WHERE m.user_id=? AND m.id IN ({','.join('?' * len(part))})"
                for r in c.execute(q, (uid, *part)):
                    out[r["id"]] = mem_out(r)
        return out

    @staticmethod
    def list(uid: str, *, q: Optional[str] = None, memory_type: Optional[str] = None, topic: Optional[str] = None,
             entity: Optional[str] = None, start_year: Optional[int] = None, end_year: Optional[int] = None,
             document_id: Optional[str] = None, pinned: Optional[bool] = None, order: str = "asc",
             limit: Optional[int] = None, offset: int = 0) -> List[MemoryOut]:
        sql = MEM_SELECT + " WHERE m.user_id=?"
        p: List[Any] = [uid]
        if q:
            sql += " AND m.id IN (SELECT id FROM memories_fts WHERE memories_fts MATCH ? AND user_id=?)"
            p += [_fts_query(q) or '""', uid]
        if memory_type:
            sql += " AND m.memory_type=?"
            p.append(memory_type)
        if start_year:
            sql += " AND substr(COALESCE(m.event_date_start,'9999'),1,4) >= ?"
            p.append(f"{start_year:04d}")
        if end_year:
            sql += " AND substr(COALESCE(m.event_date_start,'0000'),1,4) <= ?"
            p.append(f"{end_year:04d}")
        if document_id:
            sql += " AND m.document_id=?"
            p.append(document_id)
        if pinned:
            sql += " AND m.pinned=1"
        if topic:
            sql += " AND m.topics LIKE ?"
            p.append(f'%"{topic}"%')
        if entity:
            sql += " AND LOWER(m.entities) LIKE ?"
            p.append(f'%"{entity.lower()}"%')
        direction = "DESC" if order == "desc" else "ASC"
        sql += f" ORDER BY COALESCE(m.event_date_start,'9999') {direction}, m.id {direction}"
        if limit:
            sql += " LIMIT ? OFFSET ?"
            p += [limit, offset]
        with get_db() as c:
            return [mem_out(r) for r in c.execute(sql, p)]

    @staticmethod
    def count(uid: str) -> int:
        with get_db() as c:
            return c.execute("SELECT COUNT(*) n FROM memories WHERE user_id=?", (uid,)).fetchone()["n"]

    @staticmethod
    def fts(uid: str, query: str, limit: int = 60) -> List[Dict[str, Any]]:
        fq = _fts_query(query)
        if not fq:
            return []
        with get_db() as c:
            try:
                rows = c.execute("""SELECT id, bm25(memories_fts, 0, 0, 1.0, 1.6, 0.6) AS s FROM memories_fts
                                    WHERE memories_fts MATCH ? AND user_id=? ORDER BY s LIMIT ?""",
                                 (fq, uid, limit)).fetchall()
            except Exception:
                return []
        return [{"id": r["id"], "score": -float(r["s"])} for r in rows]

    @staticmethod
    def update(uid: str, mid: str, **fields) -> None:
        fields = {k: v for k, v in fields.items() if v is not None}
        if "pinned" in fields:
            fields["pinned"] = int(bool(fields["pinned"]))
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        with get_db() as c:
            c.execute(f"UPDATE memories SET {cols} WHERE id=? AND user_id=?", (*fields.values(), mid, uid))
            if "statement" in fields:
                c.execute("UPDATE memories_fts SET statement=? WHERE id=?", (fields["statement"], mid))

    @staticmethod
    def delete(uid: str, mid: str) -> bool:
        with get_db() as c:
            cur = c.execute("DELETE FROM memories WHERE id=? AND user_id=?", (mid, uid))
            c.execute("DELETE FROM memories_fts WHERE id=?", (mid,))
            c.execute("DELETE FROM embeddings WHERE item_id=? AND kind='memory'", (mid,))
        from app.storage.vectors import invalidate
        invalidate(uid)
        return bool(cur.rowcount)

    @staticmethod
    def ids_for_chunks(uid: str, chunk_ids: Iterable[str]) -> List[tuple]:
        ids = list(chunk_ids)
        if not ids:
            return []
        with get_db() as c:
            rows = c.execute(f"SELECT id, chunk_id FROM memories WHERE user_id=? AND chunk_id IN "
                             f"({','.join('?' * len(ids))})", (uid, *ids))
            return [(r["id"], r["chunk_id"]) for r in rows]

    @staticmethod
    def chunk_text(chunk_ids: Iterable[str]) -> Dict[str, str]:
        ids = [i for i in dict.fromkeys(chunk_ids) if i]
        if not ids:
            return {}
        with get_db() as c:
            rows = c.execute(f"SELECT id, content FROM chunks WHERE id IN ({','.join('?' * len(ids))})", ids)
            return {r["id"]: r["content"] for r in rows}


# ===================================================================== analysis artifacts
class Analysis:
    @staticmethod
    def replace(uid: str, changes: List[Dict[str, Any]], rels: List[Dict[str, Any]]) -> None:
        now = now_iso()
        with get_db() as c:
            c.execute("DELETE FROM change_points WHERE user_id=?", (uid,))
            c.execute("DELETE FROM relationships WHERE user_id=?", (uid,))
            c.executemany("""INSERT OR REPLACE INTO change_points (id,user_id,subject,change_type,magnitude,
                earlier_memory_id,later_memory_id,from_date,to_date,uncertainty,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                          [(x["id"], uid, x["subject"], x["change_type"], x["magnitude"], x["earlier_memory_id"],
                            x["later_memory_id"], x.get("from_date"), x.get("to_date"), x.get("uncertainty"), now)
                           for x in changes])
            c.executemany("""INSERT OR REPLACE INTO relationships (id,user_id,source_memory_id,target_memory_id,
                relation_type,confidence,rationale,created_at) VALUES (?,?,?,?,?,?,?,?)""",
                          [(x["id"], uid, x["source_memory_id"], x["target_memory_id"], x["relation_type"],
                            x["confidence"], x.get("rationale"), now) for x in rels])

    @staticmethod
    def changes(uid: str) -> List[Dict[str, Any]]:
        with get_db() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM change_points WHERE user_id=? ORDER BY COALESCE(to_date,'9999')", (uid,))]

    @staticmethod
    def relationships(uid: str, relation_type: Optional[str] = None) -> List[Dict[str, Any]]:
        sql, p = "SELECT * FROM relationships WHERE user_id=?", [uid]
        if relation_type:
            sql += " AND relation_type=?"
            p.append(relation_type)
        with get_db() as c:
            return [dict(r) for r in c.execute(sql + " ORDER BY confidence DESC", p)]


# ===================================================================== conversations
class Conversations:
    @staticmethod
    def create(uid: str, title: str) -> str:
        cid, now = new_id("conv"), now_iso()
        with get_db() as c:
            c.execute("INSERT INTO conversations VALUES (?,?,?,?,?,?)", (cid, uid, title[:120], 0, now, now))
        return cid

    @staticmethod
    def owns(uid: str, cid: str) -> bool:
        with get_db() as c:
            return c.execute("SELECT 1 FROM conversations WHERE id=? AND user_id=?", (cid, uid)).fetchone() is not None

    @staticmethod
    def list(uid: str, q: Optional[str] = None) -> List[ConversationOut]:
        sql = """SELECT cv.*, (SELECT COUNT(*) FROM messages WHERE conversation_id=cv.id) n,
                 (SELECT substr(content,1,140) FROM messages WHERE conversation_id=cv.id AND role='assistant'
                  ORDER BY created_at DESC LIMIT 1) preview FROM conversations cv WHERE cv.user_id=?"""
        p: List[Any] = [uid]
        if q:
            sql += " AND (cv.title LIKE ? OR cv.id IN (SELECT conversation_id FROM messages WHERE content LIKE ?))"
            p += [f"%{q}%", f"%{q}%"]
        sql += " ORDER BY cv.pinned DESC, cv.updated_at DESC"
        with get_db() as c:
            return [ConversationOut(id=r["id"], title=r["title"], pinned=bool(r["pinned"]), created_at=r["created_at"],
                                    updated_at=r["updated_at"], message_count=r["n"],
                                    preview=re.sub(r"\s+", " ", r["preview"] or "")) for r in c.execute(sql, p)]

    @staticmethod
    def get(uid: str, cid: str) -> Optional[ConversationDetail]:
        with get_db() as c:
            r = c.execute("SELECT * FROM conversations WHERE id=? AND user_id=?", (cid, uid)).fetchone()
            if not r:
                return None
            msgs = [MessageOut(id=m["id"], role=m["role"], content=m["content"], payload=json.loads(m["payload"]),
                               feedback=m["feedback"], created_at=m["created_at"])
                    for m in c.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at, rowid",
                                       (cid,))]
        return ConversationDetail(id=r["id"], title=r["title"], pinned=bool(r["pinned"]), created_at=r["created_at"],
                                  updated_at=r["updated_at"], message_count=len(msgs), messages=msgs)

    @staticmethod
    def history(cid: str, limit: int = 8) -> List[Dict[str, str]]:
        with get_db() as c:
            rows = c.execute("""SELECT role, content FROM messages WHERE conversation_id=?
                                ORDER BY created_at DESC, rowid DESC LIMIT ?""", (cid, limit)).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    @staticmethod
    def add_message(cid: str, role: str, content: str, payload: Optional[Dict[str, Any]] = None) -> str:
        mid, now = new_id("msg"), now_iso()
        with get_db() as c:
            c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?)",
                      (mid, cid, role, content, json.dumps(payload or {}, default=str), 0, now))
            c.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, cid))
        return mid

    @staticmethod
    def update(uid: str, cid: str, title: Optional[str] = None, pinned: Optional[bool] = None) -> None:
        with get_db() as c:
            if title is not None:
                c.execute("UPDATE conversations SET title=? WHERE id=? AND user_id=?", (title[:120], cid, uid))
            if pinned is not None:
                c.execute("UPDATE conversations SET pinned=? WHERE id=? AND user_id=?", (int(pinned), cid, uid))

    @staticmethod
    def delete(uid: str, cid: str) -> bool:
        with get_db() as c:
            return bool(c.execute("DELETE FROM conversations WHERE id=? AND user_id=?", (cid, uid)).rowcount)

    @staticmethod
    def feedback(uid: str, message_id: str, value: int) -> None:
        with get_db() as c:
            c.execute("""UPDATE messages SET feedback=? WHERE id=? AND conversation_id IN
                         (SELECT id FROM conversations WHERE user_id=?)""", (value, message_id, uid))


# ===================================================================== evaluation
class EvalRuns:
    @staticmethod
    def save(uid: str, run_id: str, name: str, config: dict, metrics: dict, summary: str) -> None:
        with get_db() as c:
            c.execute("INSERT INTO evaluation_runs VALUES (?,?,?,?,?,?,?)",
                      (run_id, uid, name, json.dumps(config), json.dumps(metrics), summary, now_iso()))

    @staticmethod
    def list(uid: str) -> List[Dict[str, Any]]:
        with get_db() as c:
            rows = c.execute("SELECT * FROM evaluation_runs WHERE user_id=? ORDER BY created_at DESC", (uid,))
            return [{"id": r["id"], "run_name": r["run_name"], "config": json.loads(r["config"]),
                     "metrics": json.loads(r["metrics"]), "summary": r["summary"], "created_at": r["created_at"]}
                    for r in rows]
