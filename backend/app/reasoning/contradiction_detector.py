from typing import List, Optional
from datetime import datetime, timezone
from app.models.schemas import TMUResponse, MemoryRelationshipResponse, RelationType
from app.storage.repository import Repository

class ContradictionDetector:
    """
    Identifies potential contradictions, reversals, and stance inversions
    across time with side-by-side evidence inspection.
    """

    @staticmethod
    def detect_contradictions(
        user_id: str = "default_user",
        tmus: Optional[List[TMUResponse]] = None
    ) -> List[MemoryRelationshipResponse]:
        if tmus is None:
            tmus = Repository.list_tmus(user_id=user_id)

        # Sort chronologically
        tmus_sorted = sorted(tmus, key=lambda x: x.event_date_start or "9999")
        reversals: List[MemoryRelationshipResponse] = []
        seen_pairs = set()

        for i in range(len(tmus_sorted)):
            m1 = tmus_sorted[i]
            # Must have non-neutral polarity
            if abs(m1.stance_polarity) < 0.3:
                continue

            for j in range(i + 1, len(tmus_sorted)):
                m2 = tmus_sorted[j]
                if abs(m2.stance_polarity) < 0.3:
                    continue

                # Must share at least one entity or high-level topic
                common_entities = set(m1.entities).intersection(set(m2.entities))
                common_topics = set(m1.topics).intersection(set(m2.topics))
                if not common_entities and not common_topics:
                    continue

                # Check for polarity sign flip
                if (m1.stance_polarity * m2.stance_polarity) < 0:
                    polarity_gap = abs(m2.stance_polarity - m1.stance_polarity)
                    if polarity_gap >= 0.8:
                        pair_key = (m1.id, m2.id)
                        if pair_key in seen_pairs:
                            continue
                        seen_pairs.add(pair_key)

                        subject = list(common_entities)[0] if common_entities else list(common_topics)[0]
                        rationale = (
                            f"Detected potential stance reversal regarding '{subject}'. "
                            f"In {m1.event_date_start or 'earlier document'}, polarity was negative ({m1.stance_polarity:.2f}). "
                            f"In {m2.event_date_start or 'later document'}, polarity became positive ({m2.stance_polarity:.2f})."
                        )

                        rel = MemoryRelationshipResponse(
                            id=f"rev_{m1.id}_{m2.id}",
                            source_memory_id=m1.id,
                            target_memory_id=m2.id,
                            relation_type=RelationType.CONTRADICTS,
                            confidence=round(min(1.0, 0.6 + (polarity_gap * 0.2)), 2),
                            evidence_rationale=rationale,
                            source_statement=m1.statement,
                            target_statement=m2.statement,
                            source_date=m1.event_date_start,
                            target_date=m2.event_date_start,
                            created_at=datetime.now(timezone.utc).isoformat()
                        )
                        reversals.append(rel)

                        # Persist to repository
                        Repository.insert_relationship({
                            "id": rel.id,
                            "source_memory_id": rel.source_memory_id,
                            "target_memory_id": rel.target_memory_id,
                            "relation_type": rel.relation_type.value,
                            "confidence": rel.confidence,
                            "evidence_rationale": rel.evidence_rationale
                        })

        return reversals
