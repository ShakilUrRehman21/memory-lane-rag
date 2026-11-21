"""Grounded answer generation with inline [n] citations, streaming, and an offline writer."""
from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict
from typing import Any, Dict, Iterator, List, Optional, Tuple

from app.ai import llm
from app.models.schemas import (AnswerPayload, ChatRequest, Citation, MemoryOut, MemoryType, QueryIntent)
from app.reasoning.analysis import change_points, relationships
from app.retrieval.retriever import retrieve
from app.retrieval.router import contextualize, plan_for
from app.synthesis import offline
from app.storage.repo import Memories

log = logging.getLogger("memory_lane.answer")

SYSTEM_PROMPT = """You are Memory Lane, a warm, perceptive companion that helps a person understand how their own
thinking, goals, feelings and decisions evolved over time, using ONLY their personal archive.

Rules:
- Ground every factual claim in the numbered evidence and cite it inline like [3] or [2][5]. Never cite a number that
  is not in the evidence list. If the evidence does not answer the question, say so plainly and suggest what they
  could add to their archive.
- Speak to the person as "you". Be specific: name the dates (month + year) and quote short phrases when they matter.
- Keep event dates (when something happened) distinct from when it was written.
- When records are far apart in time, say that the exact turning point is not recorded instead of inventing one.
- Describe stance reversals neutrally ("you revised your view"), never judgmentally. Do not diagnose or speculate
  about inner psychology beyond what is written.
- Answer the exact question first, in one or two sentences, then give supporting detail. If the person asks
  "when", lead with the date. If nothing in the evidence answers it, say so instead of summarising unrelated entries.
- Format in clean Markdown. For questions about change over time, use short sections such as **Where you started**,
  **How it shifted**, **Where you are now**, then a one-line takeaway. For simple lookups, answer in 1–3 short
  paragraphs. Avoid filler and do not repeat the question.
"""

def build_citations(results: List[Dict[str, Any]]) -> List[Citation]:
    return [Citation(index=i + 1, memory_id=c["memory"].id, document_id=c["memory"].document_id,
                     document_title=c["memory"].document_title or "Entry", statement=c["memory"].statement,
                     date=c["memory"].event_date_start, memory_type=c["memory"].memory_type.value,
                     score=round(float(c["score"]), 5)) for i, c in enumerate(results)]


def evidence_block(results: List[Dict[str, Any]]) -> str:
    ctx = Memories.chunk_text(c["memory"].chunk_id for c in results)
    lines = []
    for i, c in enumerate(results, 1):
        m: MemoryOut = c["memory"]
        passage = ctx.get(m.chunk_id or "", "")
        extra = f"\n    context: \"{passage[:420]}\"" if passage and passage.strip() != m.statement.strip() else ""
        lines.append(f"[{i}] ({m.event_date_start or 'undated'}, {m.memory_type.value}, from \"{m.document_title}\")"
                     f" \"{m.statement}\"{extra}")
    return "\n".join(lines)


def follow_ups(plan: Dict[str, Any], results: List[Dict[str, Any]], changes) -> List[str]:
    ents: "OrderedDict[str, int]" = OrderedDict()
    for c in results:
        for e in c["memory"].entities + c["memory"].topics:
            ents[e] = ents.get(e, 0) + 1
    top = [e for e, _ in sorted(ents.items(), key=lambda kv: -kv[1])][:3]
    years = sorted({c["memory"].event_date_start[:4] for c in results if c["memory"].event_date_start})
    out = []
    if changes:
        out.append(f"What triggered my shift on {changes[0].subject}?")
    if top:
        out.append(f"How has my view of {top[0]} evolved over time?")
    if len(years) >= 2:
        out.append(f"What did I care about most in {years[0]} vs {years[-1]}?")
    if plan["intent"] != QueryIntent.CONTRADICTION_ANALYSIS:
        out.append("Where have I contradicted myself?")
    if len(top) > 1:
        out.append(f"Show the timeline of {top[1]}")
    return list(dict.fromkeys(out))[:4]


def _gap_notes(results: List[Dict[str, Any]], plan: Dict[str, Any]) -> List[str]:
    if not plan.get("is_longitudinal"):
        return []
    years = sorted({int(c["memory"].event_date_start[:4]) for c in results if c["memory"].event_date_start})
    notes = []
    for a, b in zip(years, years[1:]):
        if b - a >= 2:
            notes.append(f"No records between {a} and {b} — anything that happened in between isn't captured.")
    undated = sum(1 for c in results if not c["memory"].event_date_start)
    if undated:
        notes.append(f"{undated} piece{'s' if undated > 1 else ''} of evidence had no date and may be placed loosely.")
    return notes[:3]


# ---------------------------------------------------------------- main entry
def answer_stream(user_id: str, req: ChatRequest, history: List[Dict[str, str]]) -> Iterator[Tuple[str, Any]]:
    """Yields ("meta", dict), ("token", str)…, ("done", AnswerPayload)."""
    t0 = time.perf_counter()
    if offline.is_smalltalk(req.query):
        reply = offline.smalltalk_reply(req.query)
        yield "meta", {"intent": QueryIntent.FACT_LOOKUP.value, "citations": [], "year_range": None,
                       "provider": llm.provider_label(), "changes": [], "rewritten_query": None}
        for piece in re.findall(r"\S+\s*", reply):
            yield "token", piece
        yield "done", AnswerPayload(query=req.query, intent=QueryIntent.FACT_LOOKUP, pipeline=req.pipeline_mode,
                                    answer=reply, citations=[], provider="Memory Lane",
                                    follow_ups=["How has my thinking changed over the years?",
                                                "What were my biggest turning points?"])
        return
    rq = contextualize(req.query, history)
    plan_in = plan_for(req.query, rq)
    extra: List[str] = []
    if offline.START_Q.search(req.query) or offline.STOP_Q.search(req.query):
        terms = offline.subject_terms(req.query)
        extra = [m.id for m in Memories.list(user_id) if offline.matches(m, terms)][:40]
    r = retrieve(user_id, rq, mode=req.pipeline_mode, top_k=req.top_k, start_year=req.filter_start_year,
                 end_year=req.filter_end_year, memory_types=req.filter_memory_types, plan=plan_in, extra_ids=extra)
    plan, results = r["plan"], r["results"]
    t_retrieval = (time.perf_counter() - t0) * 1000

    ids = {c["memory"].id for c in results}
    use_reasoning = req.pipeline_mode != "baseline"
    changes = change_points(user_id, memory_ids=ids) if use_reasoning else []
    contradictions = relationships(user_id, "contradicts", memory_ids=ids) if use_reasoning else []
    changes = [c for c in changes if c.earlier.id in ids and c.later.id in ids] or changes[:3]
    contradictions = [x for x in contradictions if x.source_memory_id in ids and x.target_memory_id in ids] \
        or contradictions[:2]
    citations = build_citations(results)

    yield "meta", {"intent": plan["intent"].value, "citations": [c.model_dump() for c in citations],
                   "year_range": r["year_range"], "provider": llm.provider_label(),
                   "changes": [c.model_dump() for c in changes], "rewritten_query": rq if rq != req.query else None}

    provider = llm.active_provider()
    text = ""
    used_provider = "offline"
    if provider != "offline" and results:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in history[-6:]:
            msgs.append({"role": h["role"], "content": h["content"][:1500]})
        change_hint = "\n".join(f"- {c.subject}: {c.change_type} between {c.from_date} and {c.to_date}"
                                for c in changes[:6])
        msgs.append({"role": "user", "content": (
            f"Question: {req.query}\n"
            f"Detected intent: {plan['intent'].value}"
            f"{' · time window ' + str(r['year_range']) if r['year_range'] else ''}\n\n"
            f"Evidence from my archive (chronological where relevant):\n{evidence_block(results)}\n\n"
            f"{'Detected changes:' + chr(10) + change_hint if change_hint else ''}\n\n"
            "Answer using only this evidence, citing [n].")})
        try:
            for tok in llm.stream_chat(msgs):
                text += tok
                yield "token", tok
            used_provider = llm.provider_label(llm.last_used)
        except Exception as exc:
            log.warning("LLM streaming failed, using offline writer: %s", exc)
            if text:
                note = "\n\n_(The model connection dropped; the answer above may be incomplete.)_"
                text += note
                yield "token", note
                used_provider = llm.provider_label(llm.last_used)
    if not text.strip():
        text = offline.write(req.query, plan, results, changes)
        for piece in re.findall(r"\S+\s*", text):
            yield "token", piece

    used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text) if 0 < int(n) <= len(citations)})
    payload = AnswerPayload(
        query=req.query, intent=plan["intent"], pipeline=req.pipeline_mode, answer=text, citations=citations,
        used_citations=used, changes=changes, contradictions=contradictions, uncertainty_notes=_gap_notes(results, plan),
        follow_ups=follow_ups(plan, results, changes), year_range=r["year_range"], provider=used_provider,
        timings_ms={"retrieval": round(t_retrieval, 1), "total": round((time.perf_counter() - t0) * 1000, 1)},
    )
    yield "done", payload


def answer(user_id: str, req: ChatRequest, history: Optional[List[Dict[str, str]]] = None) -> AnswerPayload:
    final = None
    for kind, data in answer_stream(user_id, req, history or []):
        if kind == "done":
            final = data
    return final
