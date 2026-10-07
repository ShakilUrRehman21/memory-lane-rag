from typing import List, Dict, Any, Tuple
from app.models.schemas import TimelinePoint, GroundedClaim, ChangePointResponse

class EvaluationMetrics:
    """Computes quantitative research metrics comparing RAG architectures."""

    @staticmethod
    def chronological_ordering_accuracy(timeline: List[TimelinePoint]) -> float:
        """Measures whether retrieved events follow true monotonic chronological order."""
        if len(timeline) < 2:
            return 1.0

        dates = [p.event_date for p in timeline if p.event_date and p.event_date != "Unrecorded"]
        if len(dates) < 2:
            return 1.0

        concordant = 0
        total_pairs = 0
        for i in range(len(dates) - 1):
            for j in range(i + 1, len(dates)):
                total_pairs += 1
                if dates[i] <= dates[j]:
                    concordant += 1

        return round(concordant / total_pairs, 3) if total_pairs > 0 else 1.0

    @staticmethod
    def temporal_coverage_recall(timeline: List[TimelinePoint], expected_years: List[str]) -> float:
        """Measures what fraction of the target historical span was successfully recovered."""
        if not expected_years:
            return 1.0

        covered_years = set()
        for p in timeline:
            if p.event_date and len(p.event_date) >= 4 and p.event_date[:4] in expected_years:
                covered_years.add(p.event_date[:4])

        return round(len(covered_years) / len(expected_years), 3)

    @staticmethod
    def change_point_f1(
        detected_changes: List[ChangePointResponse],
        ground_truth: List[Tuple[str, str, str]]
    ) -> float:
        """Calculates F1 score of detected change points against annotated transitions."""
        if not ground_truth and not detected_changes:
            return 1.0
        if not ground_truth or not detected_changes:
            return 0.0

        tp = 0
        for dt in detected_changes:
            dt_from = (dt.from_period or "")[:4]
            dt_to = (dt.to_period or "")[:4]
            for gt_from, gt_to, gt_type in ground_truth:
                if dt_from == gt_from and dt_to == gt_to:
                    tp += 1
                    break

        precision = tp / len(detected_changes) if detected_changes else 0.0
        recall = tp / len(ground_truth) if ground_truth else 0.0

        if precision + recall == 0:
            return 0.0
        return round(2 * (precision * recall) / (precision + recall), 3)

    @staticmethod
    def unsupported_claim_rate(claims: List[GroundedClaim]) -> float:
        """Measures hallucination rate: proportion of claims lacking source backing."""
        if not claims:
            return 0.0
        unsupported = sum(1 for c in claims if not c.evidence_tmu_ids or len(c.evidence_tmu_ids) == 0)
        return round(unsupported / len(claims), 3)
