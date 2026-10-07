from typing import List, Dict, Any
from collections import defaultdict
from app.models.schemas import TMUResponse

class StratifiedTemporalSampler:
    """
    Prevents temporal recency and density bias by grouping candidates into
    chronological epochs (e.g. Years) and ensuring proportional, balanced representation
    across the entire historical span.
    """

    @staticmethod
    def sample(
        scored_tmus: List[Dict[str, Any]],
        target_k: int = 10,
        min_per_epoch: int = 1
    ) -> List[Dict[str, Any]]:
        if not scored_tmus:
            return []

        # 1. Group candidates into temporal epochs (by Year)
        epochs: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in scored_tmus:
            tmu: TMUResponse = item["tmu"]
            # Extract year from event_date_start or fallback to created_at
            dt = tmu.event_date_start or tmu.created_at
            epoch_key = dt[:4] if dt and len(dt) >= 4 else "Unrecorded"
            epochs[epoch_key].append(item)

        # Sort each epoch's candidates by composite score descending
        for epoch_key in epochs:
            epochs[epoch_key].sort(key=lambda x: x["score"], reverse=True)

        sorted_epoch_keys = sorted(
            [k for k in epochs.keys() if k != "Unrecorded"]
        )
        if "Unrecorded" in epochs:
            sorted_epoch_keys.append("Unrecorded")

        num_epochs = len(sorted_epoch_keys)
        if num_epochs == 0:
            return scored_tmus[:target_k]

        # 2. Stratified round-robin sampling: Guarantee at least min_per_epoch from each epoch
        sampled_ids = set()
        selected: List[Dict[str, Any]] = []

        # First pass: Pick best candidate from each epoch in chronological order
        for epoch_key in sorted_epoch_keys:
            if epochs[epoch_key]:
                top_item = epochs[epoch_key][0]
                if top_item["tmu"].id not in sampled_ids:
                    selected.append(top_item)
                    sampled_ids.add(top_item["tmu"].id)

        # Second pass: If slots remain, pick second best, etc.
        round_idx = 1
        while len(selected) < target_k:
            added_this_round = 0
            for epoch_key in sorted_epoch_keys:
                if len(selected) >= target_k:
                    break
                if len(epochs[epoch_key]) > round_idx:
                    item = epochs[epoch_key][round_idx]
                    if item["tmu"].id not in sampled_ids:
                        selected.append(item)
                        sampled_ids.add(item["tmu"].id)
                        added_this_round += 1
            if added_this_round == 0:
                break
            round_idx += 1

        # Fill any remaining slots with highest overall scores not yet selected
        if len(selected) < target_k:
            all_sorted = sorted(scored_tmus, key=lambda x: x["score"], reverse=True)
            for item in all_sorted:
                if len(selected) >= target_k:
                    break
                if item["tmu"].id not in sampled_ids:
                    selected.append(item)
                    sampled_ids.add(item["tmu"].id)

        # Return sorted chronologically by event_date_start for longitudinal coherence
        selected.sort(key=lambda x: (x["tmu"].event_date_start or "9999", x["score"]))
        return selected
