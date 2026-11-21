"""Benchmark: compare baseline / temporal / memory_lane pipelines on an annotated longitudinal corpus.

The corpus lives in a hidden benchmark account so it never pollutes a real archive. The offline writer is used
so runs are fast, free and reproducible.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Dict, List

from app.core.database import get_db
from app.evaluation.benchmark_dataset import BENCHMARK_CORPUS_DOCUMENTS, BENCHMARK_QUERIES
from app.models.schemas import ChatRequest
from app.storage.repo import Documents, EvalRuns, Users

BENCH_USER = "user_benchmark"


def _ensure_corpus() -> None:
    from app.ingestion.service import ingest_text
    from app.reasoning.analysis import refresh_analysis

    if not Users.get(BENCH_USER):
        Users.create("__benchmark__", "Benchmark", None, None, None, user_id=BENCH_USER)
    if len(Documents.list(BENCH_USER)) >= len(BENCHMARK_CORPUS_DOCUMENTS):
        return
    with get_db() as c:
        c.execute("DELETE FROM documents WHERE user_id=?", (BENCH_USER,))
    for d in BENCHMARK_CORPUS_DOCUMENTS:
        ingest_text(BENCH_USER, d["content"], d["title"], d["date"], refresh=False)
    refresh_analysis(BENCH_USER)


def _ordering(dates: List[str]) -> float:
    dates = [d for d in dates if d]
    if len(dates) < 2:
        return 1.0
    pairs = [(dates[i], dates[j]) for i in range(len(dates)) for j in range(i + 1, len(dates))]
    return round(sum(a <= b for a, b in pairs) / len(pairs), 3)


def _coverage(dates: List[str], expected: List[str]) -> float:
    if not expected:
        return 1.0
    return round(len({d[:4] for d in dates if d} & set(expected)) / len(expected), 3)


def _cp_f1(changes, truth) -> float:
    if not truth and not changes:
        return 1.0
    if not truth or not changes:
        return 0.0
    found = {((c.from_date or "")[:4], (c.to_date or "")[:4]) for c in changes}
    gold = {(a, b) for a, b, _ in truth}
    tp = len(found & gold)
    if not tp:
        return 0.0
    p, r = tp / len(found), tp / len(gold)
    return round(2 * p * r / (p + r), 3)


def _unsupported(answer: str) -> float:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", answer) if len(s.split()) >= 6 and not s.lstrip().startswith(("#", "_", "**"))]
    if not sentences:
        return 0.0
    return round(sum(1 for s in sentences if not re.search(r"\[\d+\]", s)) / len(sentences), 3)


def run(user_id: str, name: str, pipelines: List[str]) -> Dict:
    from app.ai import llm
    from app.synthesis.answer import answer

    _ensure_corpus()
    original = llm.active_provider
    llm.active_provider = lambda: "offline"  # deterministic, cost-free runs
    try:
        metrics: Dict[str, Dict] = {}
        for pipe in pipelines:
            rows = []
            for q in BENCHMARK_QUERIES:
                t0 = time.perf_counter()
                res = answer(BENCH_USER, ChatRequest(query=q["query"], pipeline_mode=pipe, top_k=6))
                ms = (time.perf_counter() - t0) * 1000
                dates = [c.date for c in res.citations]
                rows.append({"coa": _ordering(dates), "tcr": _coverage(dates, q["expected_years"]),
                             "f1": _cp_f1(res.changes, q["ground_truth_transitions"]),
                             "ucr": _unsupported(res.answer), "ms": ms, "per_query": {
                                 "query": q["query"], "citations": len(res.citations)}})
            n = len(rows)
            metrics[pipe] = {
                "pipeline": pipe,
                "chronological_ordering_accuracy": round(sum(r["coa"] for r in rows) / n, 3),
                "temporal_coverage_recall": round(sum(r["tcr"] for r in rows) / n, 3),
                "change_point_f1": round(sum(r["f1"] for r in rows) / n, 3),
                "unsupported_claim_rate": round(sum(r["ucr"] for r in rows) / n, 3),
                "average_latency_ms": round(sum(r["ms"] for r in rows) / n, 1),
            }
    finally:
        llm.active_provider = original

    base, ml = metrics.get("baseline"), metrics.get("memory_lane")
    if base and ml:
        summary = (f"Memory Lane recovered {round((ml['temporal_coverage_recall'] - base['temporal_coverage_recall']) * 100)}"
                   f" pts more of the relevant years than the baseline, with change-point F1 of "
                   f"{ml['change_point_f1']:.2f} and {round(ml['unsupported_claim_rate'] * 100)}% uncited sentences.")
    else:
        summary = "Run complete."
    run_id = f"eval_{uuid.uuid4().hex[:10]}"
    EvalRuns.save(user_id, run_id, name, {"pipelines": pipelines, "queries": len(BENCHMARK_QUERIES)}, metrics,
                  summary)
    return {"id": run_id, "run_name": name, "metrics": metrics, "summary": summary}
