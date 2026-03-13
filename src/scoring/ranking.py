"""
Final ranking of scored candidate combinations.

Sorts candidates by ensemble score, applies an optional diversity
penalty to discourage clusters of nearly identical combinations,
and assigns sequential rank numbers starting from 1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.generator.diversity import ScoredCandidate, hamming_distance

logger = logging.getLogger(__name__)


# ── Default tuning ───────────────────────────────────────────────────────

_DEFAULT_DIVERSITY_PENALTY: float = 0.02
_DEFAULT_DIVERSITY_THRESHOLD: int = 2


# ── Ranker ───────────────────────────────────────────────────────────────


class Ranker:
    """Sort, penalise, and rank a list of scored candidates.

    The ranking process:

    1. **Sort** by ``ensemble_score`` descending.
    2. **Diversity penalty** -- for each candidate (in score order), if
       its Hamming distance to any higher-ranked candidate is below
       ``diversity_threshold``, subtract a small penalty from its
       ensemble score.  This nudges near-duplicate combinations
       downward without removing them.
    3. **Re-sort** after penalties so the final order reflects the
       adjusted scores.
    4. **Assign ranks** ``1 .. N``.

    Parameters
    ----------
    diversity_penalty:
        Score deduction applied per "too similar" higher-ranked
        neighbour.  Defaults to 0.02.
    diversity_threshold:
        Hamming distance at or below which the penalty is applied.
        Defaults to 2.
    """

    def __init__(
        self,
        diversity_penalty: float = _DEFAULT_DIVERSITY_PENALTY,
        diversity_threshold: int = _DEFAULT_DIVERSITY_THRESHOLD,
    ) -> None:
        self.diversity_penalty = diversity_penalty
        self.diversity_threshold = diversity_threshold

    def rank(self, candidates: list[ScoredCandidate]) -> list[ScoredCandidate]:
        """Rank candidates with diversity-aware scoring.

        Parameters
        ----------
        candidates:
            Scored candidates (may be in any order).

        Returns
        -------
        list[ScoredCandidate]
            A new list sorted by adjusted ensemble score (descending),
            with ``feature_scores["rank"]`` populated as integers
            ``1 .. N``.
        """
        if not candidates:
            return []

        # Step 1: initial sort by ensemble_score descending.
        ranked = sorted(
            candidates,
            key=lambda c: c.ensemble_score,
            reverse=True,
        )

        # Step 2: diversity penalty pass.
        if self.diversity_penalty > 0 and self.diversity_threshold >= 1:
            adjusted_scores: list[float] = []
            for idx, candidate in enumerate(ranked):
                penalty = 0.0
                for prev_idx in range(idx):
                    dist = hamming_distance(candidate.numbers, ranked[prev_idx].numbers)
                    if dist <= self.diversity_threshold:
                        penalty += self.diversity_penalty
                adjusted_scores.append(candidate.ensemble_score - penalty)

            # Apply adjusted scores.
            for idx, candidate in enumerate(ranked):
                candidate.ensemble_score = adjusted_scores[idx]

            # Step 3: re-sort after penalties.
            ranked.sort(key=lambda c: c.ensemble_score, reverse=True)

        # Step 4: assign sequential ranks.
        for position, candidate in enumerate(ranked, start=1):
            candidate.feature_scores["rank"] = position

        logger.info(
            "Ranked %d candidates (diversity_penalty=%.3f, threshold=%d)",
            len(ranked),
            self.diversity_penalty,
            self.diversity_threshold,
        )
        return ranked
