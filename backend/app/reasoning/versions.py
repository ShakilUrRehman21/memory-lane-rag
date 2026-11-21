"""Compare two documents (e.g. Resume v1 vs v3): entity changes, rewritten statements and a line diff."""
from __future__ import annotations

import difflib
from typing import Optional

import numpy as np

from app.models.schemas import VersionDiffOut
from app.storage import vectors
from app.storage.repo import Documents, Memories


def compare(user_id: str, earlier_id: str, later_id: str) -> Optional[VersionDiffOut]:
    a, b = Documents.raw(user_id, earlier_id), Documents.raw(user_id, later_id)
    if not a or not b:
        return None
    if (a["document_date"] or "") > (b["document_date"] or ""):
        a, b = b, a
    ma = Memories.list(user_id, document_id=a["id"])
    mb = Memories.list(user_id, document_id=b["id"])
    ea = {e for m in ma for e in m.entities} | {t for m in ma for t in m.topics}
    eb = {e for m in mb for e in m.entities} | {t for m in mb for t in m.topics}

    va = vectors.vectors_for(user_id, "memory", [m.id for m in ma])
    vb = vectors.vectors_for(user_id, "memory", [m.id for m in mb])
    changes = []
    if va and vb:
        b_ids = [m.id for m in mb if m.id in vb]
        mat = np.vstack([vb[i] for i in b_ids])
        bmap = {m.id: m for m in mb}
        for m in ma:
            if m.id not in va:
                continue
            sims = mat @ va[m.id]
            j = int(np.argmax(sims))
            s = float(sims[j])
            later = bmap[b_ids[j]]
            if later.statement.strip().lower() == m.statement.strip().lower():
                continue
            if s >= 0.35:
                changes.append({"earlier_statement": m.statement, "later_statement": later.statement,
                                "similarity": round(s, 3), "stance_delta": round(later.stance_polarity -
                                                                                   m.stance_polarity, 2)})
        changes.sort(key=lambda x: -x["similarity"])

    line_diff = []
    sm = difflib.SequenceMatcher(None, a["content"].splitlines(), b["content"].splitlines())
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for ln in a["content"].splitlines()[i1:i2]:
                line_diff.append({"op": "same", "text": ln})
        else:
            for ln in a["content"].splitlines()[i1:i2]:
                line_diff.append({"op": "removed", "text": ln})
            for ln in b["content"].splitlines()[j1:j2]:
                line_diff.append({"op": "added", "text": ln})

    added, removed, retained = sorted(eb - ea), sorted(ea - eb), sorted(ea & eb)
    la = a["version_label"] or (a["document_date"] or "earlier")[:10]
    lb = b["version_label"] or (b["document_date"] or "later")[:10]
    summary = (f"From {la} to {lb}: {len(added)} new theme{'s' if len(added) != 1 else ''}"
               f"{' (' + ', '.join(added[:4]) + ')' if added else ''}, {len(removed)} dropped"
               f"{' (' + ', '.join(removed[:4]) + ')' if removed else ''}, {len(retained)} carried through. "
               f"Text similarity {round(sm.ratio() * 100)}%.")
    return VersionDiffOut(series_name=a["series_name"] or b["series_name"] or "Comparison", earlier_version=la,
                          later_version=lb, earlier_document_id=a["id"], later_document_id=b["id"], added=added,
                          removed=removed, retained=retained, semantic_changes=changes[:8],
                          line_diff=line_diff[:600], summary=summary)
