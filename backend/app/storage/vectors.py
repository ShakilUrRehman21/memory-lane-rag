"""Per-user vector index backed by the `embeddings` table, cached in memory as a numpy matrix."""
from __future__ import annotations

import threading
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.ai.embeddings import embed_query, embed_texts, provider_name
from app.core.database import get_db

_cache: Dict[Tuple[str, str], Tuple[List[str], np.ndarray]] = {}
_lock = threading.RLock()


def invalidate(user_id: str) -> None:
    with _lock:
        for key in [k for k in _cache if k[0] == user_id]:
            _cache.pop(key, None)


def store(conn, user_id: str, kind: str, items: Sequence[Tuple[str, str]]) -> None:
    """Embed and persist (item_id, text) pairs inside an open transaction."""
    if not items:
        return
    vecs = embed_texts([t for _, t in items])
    prov = provider_name()
    conn.executemany(
        "INSERT OR REPLACE INTO embeddings (item_id, kind, user_id, provider, dim, vector) VALUES (?,?,?,?,?,?)",
        [(iid, kind, user_id, prov, vecs.shape[1], vecs[i].astype(np.float32).tobytes())
         for i, (iid, _) in enumerate(items)],
    )
    invalidate(user_id)


def memory_text(statement: str, entities: Sequence[str], topics: Sequence[str]) -> str:
    extra = " ".join(list(entities) + list(topics))
    return f"{statement} ({extra})" if extra else statement


def ensure_fresh(user_id: str) -> int:
    """Re-embed anything made by a different provider (e.g. after installing fastembed). Returns count."""
    prov = provider_name()
    with get_db() as c:
        stale_mem = c.execute(
            """SELECT m.id, m.statement, m.entities, m.topics FROM memories m
               LEFT JOIN embeddings e ON e.item_id=m.id AND e.kind='memory'
               WHERE m.user_id=? AND (e.provider IS NULL OR e.provider != ?)""", (user_id, prov)).fetchall()
        stale_chunks = c.execute(
            """SELECT ch.id, ch.content FROM chunks ch
               LEFT JOIN embeddings e ON e.item_id=ch.id AND e.kind='chunk'
               WHERE ch.user_id=? AND (e.provider IS NULL OR e.provider != ?)""", (user_id, prov)).fetchall()
        import json
        if stale_mem:
            store(c, user_id, "memory", [(r["id"], memory_text(r["statement"], json.loads(r["entities"]),
                                                               json.loads(r["topics"]))) for r in stale_mem])
        if stale_chunks:
            store(c, user_id, "chunk", [(r["id"], r["content"]) for r in stale_chunks])
    return len(stale_mem) + len(stale_chunks)


def _matrix(user_id: str, kind: str) -> Tuple[List[str], np.ndarray]:
    key = (user_id, kind)
    with _lock:
        if key in _cache:
            return _cache[key]
        prov = provider_name()
        with get_db() as c:
            rows = c.execute("SELECT item_id, vector FROM embeddings WHERE user_id=? AND kind=? AND provider=?",
                             (user_id, kind, prov)).fetchall()
        ids = [r["item_id"] for r in rows]
        mat = np.vstack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows]) if rows else np.zeros((0, 1))
        _cache[key] = (ids, mat)
        return ids, mat


def vectors_for(user_id: str, kind: str, ids: Sequence[str]) -> Dict[str, np.ndarray]:
    all_ids, mat = _matrix(user_id, kind)
    pos = {i: n for n, i in enumerate(all_ids)}
    return {i: mat[pos[i]] for i in ids if i in pos}


def search(user_id: str, query: str, kind: str = "memory", top_k: int = 60,
           allowed: Optional[set] = None) -> List[Dict[str, float]]:
    ids, mat = _matrix(user_id, kind)
    if not ids:
        return []
    q = embed_query(query)
    if q.shape[0] != mat.shape[1]:
        return []
    sims = mat @ q
    order = np.argsort(-sims)
    out = []
    for i in order:
        if allowed is not None and ids[i] not in allowed:
            continue
        out.append({"id": ids[i], "score": float(sims[i])})
        if len(out) >= top_k:
            break
    return out
