from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import numpy as np
from app.models.schemas import TMUResponse, ChangePointResponse
from app.storage.vector_store import tmu_vector_store
from app.storage.repository import Repository
from app.core.config import settings

class ChangePointDetector:
    """
    Detects semantic shifts, transition periods, and change-points across
    chronological memory sequences for entities and topics.
    """

    @staticmethod
    def detect_changes_for_topic_or_entity(
        topic_or_entity: str,
        tmus: List[TMUResponse],
        user_id: str = "default_user"
    ) -> List[ChangePointResponse]:
        # Filter TMUs mentioning topic or entity
        relevant = [
            t for t in tmus
            if topic_or_entity.lower() in [e.lower() for e in t.entities]
            or topic_or_entity.lower() in [tp.lower() for tp in t.topics]
            or topic_or_entity.lower() in t.statement.lower()
        ]

        # Sort chronologically by event date
        relevant.sort(key=lambda x: x.event_date_start or "9999")
        if len(relevant) < 2:
            return []

        detected_changes: List[ChangePointResponse] = []

        for i in range(len(relevant) - 1):
            m1 = relevant[i]
            m2 = relevant[i + 1]

            # Vector representations
            v1 = tmu_vector_store.generate_embedding(m1.statement)
            v2 = tmu_vector_store.generate_embedding(m2.statement)
            cosine_sim = float(np.dot(v1, v2))
            semantic_drift = max(0.0, 1.0 - cosine_sim)

            # Polarity delta
            polarity_delta = abs(m2.stance_polarity - m1.stance_polarity)
            polarity_sign_flip = (m1.stance_polarity * m2.stance_polarity < 0)

            # Check if this qualifies as a significant change
            is_reversal = polarity_sign_flip and polarity_delta >= settings.POLARITY_INVERSION_THRESHOLD
            is_semantic_shift = semantic_drift >= settings.SEMANTIC_DRIFT_THRESHOLD
            
            if is_reversal or is_semantic_shift:
                # Classify change type
                if is_reversal:
                    change_type = "reversal"
                elif semantic_drift > 0.65:
                    change_type = "sudden_shift"
                else:
                    change_type = "gradual_evolution"

                # Calculate uncertainty window
                p1 = m1.event_date_start or "Unknown"
                p2 = m2.event_date_start or "Unknown"
                
                uncertainty_note = None
                if p1 != "Unknown" and p2 != "Unknown":
                    try:
                        d1 = datetime.fromisoformat(p1[:10])
                        d2 = datetime.fromisoformat(p2[:10])
                        day_diff = abs((d2 - d1).days)
                        if day_diff > settings.SPARSE_EVIDENCE_DAYS:
                            uncertainty_note = (
                                f"Transition occurred between {p1[:7]} and {p2[:7]} ({day_diff} days). "
                                "Exact turning point is unrecorded in the available documents."
                            )
                    except Exception:
                        pass

                cp = ChangePointResponse(
                    id=f"cp_{m1.id}_{m2.id}",
                    user_id=user_id,
                    topic_or_entity=topic_or_entity,
                    from_period=p1,
                    to_period=p2,
                    change_type=change_type,
                    magnitude=round(semantic_drift, 3),
                    earlier_memory_id=m1.id,
                    later_memory_id=m2.id,
                    earlier_statement=m1.statement,
                    later_statement=m2.statement,
                    earlier_date=m1.event_date_start,
                    later_date=m2.event_date_start,
                    uncertainty_bounds=uncertainty_note,
                    created_at=datetime.now(timezone.utc).isoformat()
                )
                detected_changes.append(cp)

                # Persist in DB
                Repository.insert_change_point(cp.model_dump())

        return detected_changes

    @staticmethod
    def detect_all_changes(
        user_id: str = "default_user",
        tmus: Optional[List[TMUResponse]] = None
    ) -> List[ChangePointResponse]:
        if tmus is None:
            tmus = Repository.list_tmus(user_id=user_id)
        
        # Collect unique entities and topics
        all_entities = set()
        all_topics = set()
        for t in tmus:
            all_entities.update(t.entities)
            all_topics.update(t.topics)

        all_changes: List[ChangePointResponse] = []
        seen_pairs = set()

        for target in list(all_entities) + list(all_topics):
            changes = ChangePointDetector.detect_changes_for_topic_or_entity(target, tmus, user_id=user_id)
            for c in changes:
                pair_key = (c.earlier_memory_id, c.later_memory_id)
                if pair_key not in seen_pairs:
                    all_changes.append(c)
                    seen_pairs.add(pair_key)

        return all_changes
