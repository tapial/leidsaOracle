"""
Structural balance analysis for lottery draws.

Measures the historical distribution of odd/even and low/high splits
across all draws.  Also provides static scoring functions so a single
candidate combination can be evaluated for how well it matches the
balanced ideal (equal split).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from src.config.constants import GameDefinition


# ── Result dataclass ──────────────────────────────────────────────────────


@dataclass
class BalanceResult:
    """Complete output of :class:`BalanceAnalyzer`.

    Attributes:
        odd_even_histogram: Mapping ``"odd:even"`` string to the number
            of draws with that split.  E.g. ``{"3:3": 180, "4:2": 110}``.
        low_high_histogram: Same format for low/high split, where "low"
            means ``number <= midpoint`` (midpoint is the arithmetic
            mean of ``pool_min`` and ``pool_max``).
        odd_even_mode: The ``"odd:even"`` bucket that occurred most often.
        low_high_mode: The ``"low:high"`` bucket that occurred most often.
    """

    odd_even_histogram: dict[str, int]
    low_high_histogram: dict[str, int]
    odd_even_mode: str
    low_high_mode: str


# ── Analyzer ──────────────────────────────────────────────────────────────


class BalanceAnalyzer:
    """Analyse odd/even and low/high balance across historical draws."""

    def analyze(
        self,
        draws: np.ndarray,
        game_def: GameDefinition,
    ) -> BalanceResult:
        """Run balance analysis on all draws.

        Parameters
        ----------
        draws:
            ``(N, number_count)`` array, oldest draw first.
        game_def:
            Game specification.

        Returns
        -------
        BalanceResult
        """
        n_draws = draws.shape[0]
        number_count = game_def.number_count
        midpoint = (game_def.pool_min + game_def.pool_max) / 2.0

        odd_even_counter: Counter[str] = Counter()
        low_high_counter: Counter[str] = Counter()

        for row_idx in range(n_draws):
            row = [int(x) for x in draws[row_idx]]

            odd = sum(1 for n in row if n % 2 != 0)
            even = number_count - odd
            odd_even_counter[f"{odd}:{even}"] += 1

            low = sum(1 for n in row if n <= midpoint)
            high = number_count - low
            low_high_counter[f"{low}:{high}"] += 1

        # Convert to plain dicts sorted by key for determinism.
        odd_even_histogram = dict(sorted(odd_even_counter.items()))
        low_high_histogram = dict(sorted(low_high_counter.items()))

        # Mode = most common bucket.
        odd_even_mode = odd_even_counter.most_common(1)[0][0] if odd_even_counter else "0:0"
        low_high_mode = low_high_counter.most_common(1)[0][0] if low_high_counter else "0:0"

        return BalanceResult(
            odd_even_histogram=odd_even_histogram,
            low_high_histogram=low_high_histogram,
            odd_even_mode=odd_even_mode,
            low_high_mode=low_high_mode,
        )

    # ── Static scoring helpers ───────────────────────────────────────

    @staticmethod
    def score_odd_even(combination: list[int]) -> float:
        """Score the odd/even balance of a combination.

        Returns a value in ``[0, 1]`` where 1.0 means a perfect split
        (equal odd and even counts) and 0.0 means all odd or all even.

        The formula is::

            score = 1 - |odd - even| / n

        For n=6: a 3:3 split scores 1.0, a 2:4 split scores 0.67,
        and 0:6 scores 0.0.

        Parameters
        ----------
        combination:
            List of drawn numbers.

        Returns
        -------
        float
        """
        n = len(combination)
        if n == 0:
            return 0.0
        odd = sum(1 for x in combination if x % 2 != 0)
        even = n - odd
        return 1.0 - abs(odd - even) / n

    @staticmethod
    def score_low_high(combination: list[int], game_def: GameDefinition) -> float:
        """Score the low/high balance of a combination.

        Returns a value in ``[0, 1]`` where 1.0 means a perfect split
        and 0.0 means all low or all high.

        "Low" is defined as ``number <= (pool_min + pool_max) / 2``.

        Parameters
        ----------
        combination:
            List of drawn numbers.
        game_def:
            Game specification (needed for the midpoint).

        Returns
        -------
        float
        """
        n = len(combination)
        if n == 0:
            return 0.0
        midpoint = (game_def.pool_min + game_def.pool_max) / 2.0
        low = sum(1 for x in combination if x <= midpoint)
        high = n - low
        return 1.0 - abs(low - high) / n
