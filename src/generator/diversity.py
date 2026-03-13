"""Diversity enforcement using Hamming distance between combinations."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScoredCandidate:
    """A combination with its ensemble score."""

    numbers: list[int]
    ensemble_score: float
    feature_scores: dict[str, float]


def hamming_distance(a: list[int], b: list[int]) -> int:
    """
    Compute Hamming distance between two lottery combinations.

    Hamming distance = count of numbers in one combination but not the other.
    E.g., {1,2,3,4,5,6} vs {1,2,3,7,8,9} -> distance 3 (differ in 3 positions).
    """
    set_a = set(a)
    set_b = set(b)
    return len(set_a.symmetric_difference(set_b)) // 2


class DiversityEnforcer:
    """Ensure selected combinations are diverse using greedy Hamming distance selection."""

    def __init__(self, min_hamming: int = 3):
        """
        Args:
            min_hamming: Minimum Hamming distance required between any pair
                        of selected combinations.
        """
        self.min_hamming = min_hamming

    def enforce(
        self,
        candidates: list[ScoredCandidate],
        final_count: int,
    ) -> list[ScoredCandidate]:
        """
        Greedy diversity-aware selection.

        1. Sort candidates by ensemble_score descending.
        2. Select #1 unconditionally.
        3. For each remaining candidate (in score order):
           - Compute Hamming distance to ALL already-selected combinations.
           - If min distance >= min_hamming, select it.
           - Otherwise skip.
        4. If insufficient diverse candidates, relax min_hamming by 1 and retry.

        Args:
            candidates: Scored candidates, will be sorted internally.
            final_count: Target number of combinations to select.

        Returns:
            List of diverse, high-scoring candidates.
        """
        if not candidates:
            return []

        # Sort by score descending
        sorted_candidates = sorted(candidates, key=lambda c: c.ensemble_score, reverse=True)

        current_min_hamming = self.min_hamming
        selected: list[ScoredCandidate] = []

        while len(selected) < final_count and current_min_hamming >= 1:
            selected = self._greedy_select(sorted_candidates, final_count, current_min_hamming)

            if len(selected) >= final_count:
                break

            # Relax constraint
            logger.info(
                "Only found %d/%d diverse combos with min_hamming=%d, relaxing to %d",
                len(selected),
                final_count,
                current_min_hamming,
                current_min_hamming - 1,
            )
            current_min_hamming -= 1

        # If we still don't have enough (very unlikely), fill with top remaining
        if len(selected) < final_count:
            selected_sets = {tuple(sorted(c.numbers)) for c in selected}
            for cand in sorted_candidates:
                if len(selected) >= final_count:
                    break
                key = tuple(sorted(cand.numbers))
                if key not in selected_sets:
                    selected.append(cand)
                    selected_sets.add(key)

        logger.info(
            "Diversity enforcement: selected %d combinations with effective min_hamming=%d",
            len(selected),
            current_min_hamming,
        )
        return selected[:final_count]

    @staticmethod
    def _greedy_select(
        candidates: list[ScoredCandidate],
        target: int,
        min_ham: int,
    ) -> list[ScoredCandidate]:
        """Greedy selection with minimum Hamming distance constraint."""
        selected: list[ScoredCandidate] = []
        for candidate in candidates:
            if len(selected) >= target:
                break
            # Check distance to all already-selected
            if all(
                hamming_distance(candidate.numbers, s.numbers) >= min_ham
                for s in selected
            ):
                selected.append(candidate)
        return selected
