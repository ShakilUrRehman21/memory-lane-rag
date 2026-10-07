import time
from typing import Dict, Any, List, Optional
from app.models.schemas import (
    QueryRequest, QueryResponse, TimelinePoint, GroundedClaim,
    TMUResponse, ChangePointResponse, MemoryRelationshipResponse
)
from app.retrieval.hybrid_retriever import hybrid_retriever
from app.reasoning.change_detector import ChangePointDetector
from app.reasoning.contradiction_detector import ContradictionDetector
from app.synthesis.llm_provider import LLMProvider

SYSTEM_PROMPT = """You are Memory Lane RAG, an epistemic longitudinal assistant.
Your goal is to explain how a user's thinking, beliefs, goals, decisions, and knowledge evolved over time based strictly on their documented history.

Guiding Principles:
1. Epistemic Honesty: State only what the documents explicitly show or support. Never extrapolate internal psychology.
2. Quad-Dates: Accurately distinguish event dates from document authoring dates.
3. Uncertainty Bounds: When evidence is separated by significant time gaps, explicitly note that intermediate transitions are unrecorded.
4. Grounded Citations: Every key historical claim must be tied to evidence source passages.
5. Neutral Objectivity: Frame stance inversions as "potential revisions or reversals" rather than personal accusations.
"""

class GroundedSynthesizer:
    """
    Coordinates longitudinal retrieval, change detection, contradiction analysis,
    and grounded answer generation with citation provenance.
    """

    @staticmethod
    def synthesize(request: QueryRequest) -> QueryResponse:
        t0 = time.perf_counter()

        # Configure pipeline ablations
        disable_temporal = request.pipeline_mode == "baseline" or request.ablation_disable_temporal
        disable_rerank = request.pipeline_mode == "baseline" or request.ablation_disable_rerank
        disable_changes = request.pipeline_mode == "baseline" or request.ablation_disable_change_detection

        # 1. Retrieval
        retrieval_pack = hybrid_retriever.retrieve(
            query=request.query,
            user_id=request.user_id,
            top_k=request.top_k,
            disable_temporal=disable_temporal,
            disable_rerank=disable_rerank,
            filter_start_year=request.filter_start_year,
            filter_end_year=request.filter_end_year
        )
        retrieved_tmus: List[TMUResponse] = retrieval_pack["results"]
        intent = retrieval_pack["analysis"]["intent"]

        # 2. Timeline construction
        timeline: List[TimelinePoint] = []
        for t in sorted(retrieved_tmus, key=lambda x: x.event_date_start or "9999"):
            dt = t.event_date_start or t.created_at
            timeline.append(TimelinePoint(
                period=dt[:7] if dt else "Unrecorded",
                date_display=dt[:10] if dt else "Unrecorded",
                event_date=dt or "Unrecorded",
                headline=t.statement[:60] + ("..." if len(t.statement) > 60 else ""),
                statement=t.statement,
                memory_type=t.memory_type,
                document_title=t.document_title or "Document",
                document_id=t.document_id,
                tmu_id=t.id,
                confidence=t.date_confidence,
                stance_polarity=t.stance_polarity
            ))

        # 3. Change detection & contradiction detection
        detected_changes: List[ChangePointResponse] = []
        potential_contradictions: List[MemoryRelationshipResponse] = []

        if not disable_changes and retrieved_tmus:
            detected_changes = ChangePointDetector.detect_all_changes(
                user_id=request.user_id,
                tmus=retrieved_tmus
            )
            potential_contradictions = ContradictionDetector.detect_contradictions(
                user_id=request.user_id,
                tmus=retrieved_tmus
            )

        # 4. Synthesize with LLM provider
        raw_tmus = [t.model_dump() for t in retrieved_tmus]
        raw_changes = [c.model_dump() for c in detected_changes]
        raw_contradictions = [r.model_dump() for r in potential_contradictions]

        user_prompt = f"User Query: {request.query}\nAnalyze the evolution of documented perspectives."
        llm_output = LLMProvider.generate_synthesis(
            prompt=user_prompt,
            system_instruction=SYSTEM_PROMPT,
            context_tmus=raw_tmus,
            detected_changes=raw_changes,
            detected_contradictions=raw_contradictions
        )

        claims = [
            GroundedClaim(**c) for c in llm_output.get("claims", [])
        ]
        uncertainty_notes = llm_output.get("uncertainty_notes", [])

        # Additional uncertainty check for sparse timeline
        if len(timeline) >= 2:
            years = sorted([int(p.event_date[:4]) for p in timeline if p.event_date[:4].isdigit()])
            if years and (years[-1] - years[0]) >= 3 and len(timeline) <= 3:
                sparse_msg = f"Available evidence spans {years[0]} to {years[-1]} with few documented interim records. Trajectory between documented milestones is estimated."
                if sparse_msg not in uncertainty_notes:
                    uncertainty_notes.append(sparse_msg)

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

        return QueryResponse(
            query=request.query,
            detected_intent=intent,
            pipeline_used=request.pipeline_mode,
            answer=llm_output.get("answer", "No answer could be generated."),
            timeline=timeline,
            detected_changes=detected_changes,
            potential_contradictions=potential_contradictions,
            grounded_claims=claims,
            uncertainty_notes=uncertainty_notes,
            retrieved_tmus=retrieved_tmus,
            execution_time_ms=elapsed_ms,
            model_calls=1
        )

grounded_synthesizer = GroundedSynthesizer()
