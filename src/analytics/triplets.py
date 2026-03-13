"""
Triplet co-occurrence analysis for lottery draw numbers.

Counts how often every triplet of numbers has appeared together in the
same draw, computes the expected count under a uniform-random model, and
derives a *lift* metric.  Only triplets that have occurred at least
twice are retained to keep the output manageable (rare one-off triplets
carry little statistical signal).
"""

from __future__ import annotations

import itertools
import math
from collections import Counter
from dataclasses import dataclass

import numpy as np

from src.config.constants import GameDefinition


# ── Result dataclass ──────────────────────────────────────────────────────


@dataclass
class TripletResult:
    """Complete output of :class:`TripletAnalyzer`.

    Attributes:
        triplets: Mapping ``{"i,j,k": {count, expected, lift}}`` for the
            top triplets sorted by count descending.  Keys use the
            canonical ``"min,mid,max"`` string form.
        expected_count: Theoretical expected count per triplet under the
            uniform-random model.
        total_draws: Total number of draws analysed.
        min_count_threshold: Minimum observed count required for inclusion.
    """

    triplets: dict[str, dict]
    expected_count: float
    total_draws: int
    min_count_threshold: int


# ── Combinatorial helpers ────────────────────────────────────────────────


def _comb(n: int, k: int) -> int:
    """Exact binomial coefficient C(n, k)."""
    if k < 0 or k > n:
        return 0
    return math.comb(n, k)


# ── Analyzer ──────────────────────────────────────────────────────────────


class TripletAnalyzer:
    """Measure co-occurrence lift for number triplets.

    **Expected count derivation**

    In a single draw of ``number_count`` numbers from a pool of
    ``pool_size``, the probability that a fixed triplet ``(i, j, k)``
    all appear is::

        P(i,j,k in draw) = C(pool_size - 3, number_count - 3)
                            / C(pool_size,   number_count)

    Over ``N`` draws the expected count is ``N * P``.  The **lift** is
    ``observed / expected``.
    """

    def analyze(
        self,
        draws: np.ndarray,
        game_def: GameDefinition,
        top_n: int = 50,
        min_count: int = 2,
    ) -> TripletResult:
        """Run triplet co-occurrence analysis.

        Parameters
        ----------
        draws:
            ``(N, number_count)`` array, oldest draw first.
        game_def:
            Game specification.
        top_n:
            Maximum number of triplets to include in the result.
        min_count:
            Only include triplets observed at least this many times.

        Returns
        -------
        TripletResult
        """
        n_draws = draws.shape[0]
        pool_size = game_def.pool_size
        number_count = game_def.number_count

        # ── Count triplet co-occurrences ─────────────────────────────
        triplet_counter: Counter[tuple[int, int, int]] = Counter()
        for row_idx in range(n_draws):
            row = sorted(int(x) for x in draws[row_idx])
            for triplet in itertools.combinations(row, 3):
                triplet_counter[triplet] += 1

        # ── Expected count under uniform model ───────────────────────
        #   P(i,j,k all drawn) = C(S-3, nc-3) / C(S, nc)
        numerator = _comb(pool_size - 3, number_count - 3)
        denominator = _comb(pool_size, number_count)
        p_triplet = numerator / denominator if denominator > 0 else 0.0
        expected_count = n_draws * p_triplet

        # ── Filter by min_count, then take top_n ─────────────────────
        filtered = [
            (triplet, count)
            for triplet, count in triplet_counter.items()
            if count >= min_count
        ]
        # Sort by count descending, then lexicographically for stability.
        filtered.sort(key=lambda x: (-x[1], x[0]))

        if top_n > 0:
            filtered = filtered[:top_n]

        triplets: dict[str, dict] = {}
        for (a, b, c), count in filtered:
            key = f"{a},{b},{c}"
            lift = count / expected_count if expected_count > 0 else 0.0
            triplets[key] = {
                "count": count,
                "expected": round(expected_count, 4),
                "lift": round(lift, 4),
            }

        return TripletResult(
            triplets=triplets,
            expected_count=expected_count,
            total_draws=n_draws,
            min_count_threshold=min_count,
        )
