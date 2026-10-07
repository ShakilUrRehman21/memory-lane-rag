from typing import List, Dict, Any, Optional
from app.models.schemas import TMUResponse, QueryIntent
from app.retrieval.query_router import QueryRouter
from app.retrieval.stratified_sampler import StratifiedTemporalSampler
from app.retrieval.reranker import LongitudinalReranker
from app.storage.fts_store import FTSStore
from app.storage.vector_store import tmu_vector_store
from app.storage.repository import Repository

class HybridTemporalRetriever:
    """
    Coordinates Hybrid Sparse + Dense + Temporal retrieval with Stratified Sampling
    and strict per-user data isolation.
    """

    def retrieve(
        self,
        query: str,
        user_id: str = "default_user",
        top_k: int = 10,
        disable_temporal: bool = False,
        disable_rerank: bool = False,
        filter_start_year: Optional[int] = None,
        filter_end_year: Optional[int] = None
    ) -> Dict[str, Any]:
        # 1. Analyze Query Intent & Temporal Boundaries
        analysis = QueryRouter.analyze_query(query)
        intent: QueryIntent = analysis["intent"]
        
        start_year = filter_start_year or analysis["start_year"]
        end_year = filter_end_year or analysis["end_year"]
        is_evolution = analysis["is_evolution_query"] and not disable_temporal

        # 2. Dense Vector Retrieval with user isolation
        dense_results = tmu_vector_store.search(
            query=query,
            top_k=top_k * 4,
            filter_meta={"user_id": user_id}
        )

        # 3. Sparse BM25 Full-Text Retrieval with user isolation
        sparse_results = FTSStore.search_tmus(
            query=query,
            user_id=user_id,
            limit=top_k * 4
        )

        # 4. Fetch candidate TMU models
        candidate_ids = set([r["id"] for r in dense_results] + [r["tmu_id"] for r in sparse_results])
        
        # If both vector and FTS return empty, fallback to fetching all user TMUs
        if not candidate_ids:
            all_user_tmus = Repository.list_tmus(user_id=user_id)
            for t in all_user_tmus:
                candidate_ids.add(t.id)

        all_tmus: Dict[str, TMUResponse] = {}
        for cid in candidate_ids:
            tmu_obj = Repository.get_tmu(cid)
            if not tmu_obj or tmu_obj.user_id != user_id:
                continue
            
            # Apply year boundaries if temporal filtering is active
            if not disable_temporal:
                if start_year and tmu_obj.event_date_start:
                    if int(tmu_obj.event_date_start[:4]) < start_year:
                        continue
                if end_year and tmu_obj.event_date_end:
                    if int(tmu_obj.event_date_end[:4]) > end_year:
                        continue

            all_tmus[cid] = tmu_obj

        # 5. Rerank / Fuse Ranks
        if disable_rerank:
            # Baseline vanilla top-K order by vector score
            scored_candidates = []
            for item in dense_results:
                if item["id"] in all_tmus:
                    scored_candidates.append({
                        "tmu": all_tmus[item["id"]],
                        "score": item["score"]
                    })
        else:
            scored_candidates = LongitudinalReranker.fuse_and_rerank(
                dense_results=dense_results,
                sparse_results=sparse_results,
                all_tmus=all_tmus,
                is_evolution_query=is_evolution
            )

        # 6. Temporal Stratified Sampling
        if is_evolution and not disable_temporal:
            final_sampled = StratifiedTemporalSampler.sample(
                scored_tmus=scored_candidates,
                target_k=top_k
            )
        else:
            # Traditional top-K cut
            final_sampled = scored_candidates[:top_k]

        return {
            "query": query,
            "analysis": analysis,
            "results": [item["tmu"] for item in final_sampled],
            "scored_results": final_sampled
        }

hybrid_retriever = HybridTemporalRetriever()
