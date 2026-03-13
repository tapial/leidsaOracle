"""
Pair co-occurrence analysis for lottery draw numbers.

Counts how often every pair of numbers has appeared together in the same
draw, computes the expected count under a uniform-random model, and
derives a *lift* metric that reveals pairs drawn together more (or less)
often than chance would predict.
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
class PairResult:
    """Complete output of :class:`PairAnalyzer`.

    Attributes:
        pairs: Mapping ``{"i,j": {count, expected, lift}}`` for the top
            pairs sorted by count descending.  Keys use the canonical
            ``"min,max"`` string form.
        expected_count: Theoretical expected count per pair under the
            uniform-random model.
        total_draws: Total number of draws analysed.
    """

    pairs: dict[str, dict]
    expected_count: float
    total_draws: int


# ── Combinatorial helpers ────────────────────────────────────────────────


def _comb(n: int, k: int) -> int:
    """Exact binomial coefficient C(n, k)."""
    if k < 0 or k > n:
        return 0
    return math.comb(n, k)


# ── Analyzer ──────────────────────────────────────────────────────────────


class PairAnalyzer:
    """Measure co-occurrence lift for all number pairs.

    **Expected count derivation**

    In a single draw of ``number_count`` numbers from a pool of
    ``pool_size``, the probability that any fixed pair ``(i, j)`` both
    appear is::

        P(i and j in draw) = C(pool_size - 2, number_count - 2)
                              / C(pool_size,     number_count)

    Over ``N`` draws the expected count is ``N * P``.

    The **lift** for a pair is simply ``observed / expected``.  A lift
    above 1 means the pair co-occurs more than chance; below 1, less.
    """

    def analyze(
        self,
        draws: np.ndarray,
        game_def: GameDefinition,
        top_n: int = 100,
    ) -> PairResult:
        """Run pair co-occurrence analysis.

        Parameters
        ----------
        draws:
            ``(N, number_count)`` array, oldest draw first.
        game_def:
            Game specification.
        top_n:
            Number of top pairs (by observed count) to include in the
            result.  Set to ``0`` or a very large number to keep all.

        Returns
        -------
        PairResult
        """
        n_draws = draws.shape[0]
        pool_size = game_def.pool_size
        number_count = game_def.number_count

        # ── Count pair co-occurrences ────────────────────────────────
        pair_counter: Counter[tuple[int, int]] = Counter()
        for row_idx in range(n_draws):
            row = sorted(int(x) for x in draws[row_idx])
            for pair in itertools.combinations(row, 2):
                pair_counter[pair] += 1

        # ── Expected count under uniform model ───────────────────────
        #   P(both i,j drawn) = C(S-2, nc-2) / C(S, nc)
        numerator = _comb(pool_size - 2, number_count - 2)
        denominator = _comb(pool_size, number_count)
        p_pair = numerator / denominator if denominator > 0 else 0.0
        expected_count = n_draws * p_pair

        # ── Build result dict (top_n by count) ───────────────────────
        if top_n <= 0:
            top_n = len(pair_counter)

        most_common = pair_counter.most_common(top_n)

        pairs: dict[str, dict] = {}
        for (a, b), count in most_common:
            key = f"{a},{b}"
            lift = count / expected_count if expected_count > 0 else 0.0
            pairs[key] = {
                "count": count,
                "expected": round(expected_count, 4),
                "lift": round(lift, 4),
            }

        return PairResult(
            pairs=pairs,
            expected_count=expected_count,
            total_draws=n_draws,
        )
