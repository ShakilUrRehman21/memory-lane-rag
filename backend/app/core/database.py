"""SQLite storage: schema, connections and lightweight migrations."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from app.core.config import settings

SCHEMA_VERSION = 2
_init_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    password_salt TEXT,
    display_name TEXT NOT NULL,
    avatar_color TEXT NOT NULL DEFAULT '#8b9cff',
    bio TEXT,
    preferences TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,          -- upload | note | capsule | import
    file_name TEXT,
    file_path TEXT,
    file_type TEXT NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    hash_sha256 TEXT NOT NULL,
    document_date TEXT,
    date_confidence REAL NOT NULL DEFAULT 0,
    content TEXT NOT NULL DEFAULT '',
    word_count INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    favorite INTEGER NOT NULL DEFAULT 0,
    series_name TEXT,
    version_label TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_docs_user ON documents(user_id, document_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_docs_user_hash ON documents(user_id, hash_sha256);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    start_char INTEGER NOT NULL,
    end_char INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id TEXT,
    memory_type TEXT NOT NULL,
    statement TEXT NOT NULL,
    event_date_start TEXT,
    event_date_end TEXT,
    date_granularity TEXT NOT NULL,
    date_confidence REAL NOT NULL,
    date_source TEXT NOT NULL,
    stance_polarity REAL NOT NULL DEFAULT 0,
    sentiment REAL NOT NULL DEFAULT 0,
    importance REAL NOT NULL DEFAULT 0.5,
    entities TEXT NOT NULL DEFAULT '[]',
    topics TEXT NOT NULL DEFAULT '[]',
    pinned INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mem_user_date ON memories(user_id, event_date_start);
CREATE INDEX IF NOT EXISTS idx_mem_doc ON memories(document_id);

CREATE TABLE IF NOT EXISTS embeddings (
    item_id TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- memory | chunk
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL,
    PRIMARY KEY (item_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_emb_user ON embeddings(user_id, kind);

CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    source_memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    rationale TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rel_user ON relationships(user_id, relation_type);

CREATE TABLE IF NOT EXISTS change_points (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    change_type TEXT NOT NULL,
    magnitude REAL NOT NULL,
    earlier_memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    later_memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    from_date TEXT,
    to_date TEXT,
    uncertainty TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cp_user ON change_points(user_id);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    feedback INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    run_name TEXT NOT NULL,
    config TEXT NOT NULL,
    metrics TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    id UNINDEXED, user_id UNINDEXED, statement, entities, topics,
    tokenize='porter unicode61'
);
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    id UNINDEXED, user_id UNINDEXED, title, content,
    tokenize='porter unicode61'
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(settings.DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _legacy_schema(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='temporal_memories'"
    ).fetchone()
    return row is not None


SKIP_V1_USERS = {"user_alex", "user_sophia", "user_marcus", "benchmark_eval_user"}


def _is_test_account(row) -> bool:
    uid, email = row["id"], (row["email"] or "")
    return uid in SKIP_V1_USERS or uid.startswith("test_user") or email.endswith("@memorylane.test")


def init_db() -> None:
    """Create the schema. A v1 database is archived, its real accounts carried over, and their documents
    queued for re-import (see migrate_v1_documents)."""
    settings.ensure_directories()
    with _init_lock:
        legacy_users = []
        backup = settings.DB_PATH.with_name("memory_lane.v1-backup.db")
        if settings.DB_PATH.exists():
            with get_db() as conn:
                legacy = _legacy_schema(conn)
                if legacy:
                    legacy_users = [dict(r) for r in conn.execute("SELECT * FROM users") if not _is_test_account(r)]
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if legacy:
                for suffix in ("-wal", "-shm"):
                    side = settings.DB_PATH.with_name(settings.DB_PATH.name + suffix)
                    if side.exists():
                        side.unlink()
                settings.DB_PATH.replace(backup)
        with get_db() as conn:
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            for u in legacy_users:
                conn.execute(
                    """INSERT OR IGNORE INTO users (id,email,username,password_hash,password_salt,display_name,
                       avatar_color,bio,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (u["id"], u.get("email"), u["username"], u.get("password_hash"), u.get("password_salt"),
                     u["display_name"], u.get("avatar_color") or "#8b9cff", u.get("bio"), u["created_at"]))
            if legacy_users:
                conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('v1_import', ?)", (str(backup),))


def migrate_v1_documents() -> int:
    """Re-ingest documents that carried-over v1 accounts owned. Runs once, in the background."""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key='v1_import'").fetchone()
        users = {r["id"] for r in conn.execute("SELECT id FROM users")}
    if not row:
        return 0
    from pathlib import Path
    from app.ingestion.service import ingest_text
    from app.reasoning.analysis import refresh_analysis
    count = 0
    old = sqlite3.connect(row["value"])
    old.row_factory = sqlite3.Row
    try:
        docs = old.execute("SELECT id, user_id, title, document_date FROM documents").fetchall()
        for d in docs:
            if d["user_id"] not in users or d["user_id"] in SKIP_V1_USERS:
                continue
            text = "\n\n".join(r["content"] for r in old.execute(
                "SELECT content FROM chunks WHERE document_id=? ORDER BY chunk_index", (d["id"],)))
            if text.strip():
                ingest_text(d["user_id"], text, d["title"], d["document_date"], ["imported"], source_type="import",
                            refresh=False)
                count += 1
        for uid in users:
            refresh_analysis(uid)
    finally:
        old.close()
        with get_db() as conn:
            conn.execute("DELETE FROM meta WHERE key='v1_import'")
    return count
