"""
Sum and spread distribution analysis for lottery draws.

Computes descriptive statistics (mean, standard deviation, histograms)
for the *sum* and *spread* (max - min) of each draw.  Also provides
static scoring functions that evaluate how typical a given combination's
sum or spread is relative to the observed historical distribution.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

import numpy as np

from src.config.constants import GameDefinition


# ── Result dataclass ──────────────────────────────────────────────────────


@dataclass
class DistributionResult:
    """Complete output of :class:`DistributionAnalyzer`.

    Attributes:
        sum_mean: Mean of the per-draw sums.
        sum_std: Standard deviation of the per-draw sums.
        sum_histogram: Mapping ``{sum_value: count_of_draws}``.
        spread_mean: Mean of the per-draw spreads (max - min).
        spread_std: Standard deviation of the per-draw spreads.
        spread_histogram: Mapping ``{spread_value: count_of_draws}``.
    """

    sum_mean: float
    sum_std: float
    sum_histogram: dict[int, int]
    spread_mean: float
    spread_std: float
    spread_histogram: dict[int, int]


# ── Analyzer ──────────────────────────────────────────────────────────────


class DistributionAnalyzer:
    """Analyse the distribution of draw sums and spreads."""

    def analyze(
        self,
        draws: np.ndarray,
        game_def: GameDefinition,
    ) -> DistributionResult:
        """Run distribution analysis on all draws.

        Parameters
        ----------
        draws:
            ``(N, number_count)`` array, oldest draw first.
        game_def:
            Game specification.

        Returns
        -------
        DistributionResult
        """
        n_draws = draws.shape[0]

        # ── Per-draw sums ────────────────────────────────────────────
        sums = draws.sum(axis=1).astype(float)
        sum_mean = float(np.mean(sums)) if n_draws > 0 else 0.0
        sum_std = float(np.std(sums, ddof=1)) if n_draws > 1 else 0.0

        sum_counter: Counter[int] = Counter()
        for s in sums:
            sum_counter[int(s)] += 1
        sum_histogram = dict(sorted(sum_counter.items()))

        # ── Per-draw spreads ─────────────────────────────────────────
        row_maxes = draws.max(axis=1).astype(float)
        row_mins = draws.min(axis=1).astype(float)
        spreads = row_maxes - row_mins

        spread_mean = float(np.mean(spreads)) if n_draws > 0 else 0.0
        spread_std = float(np.std(spreads, ddof=1)) if n_draws > 1 else 0.0

        spread_counter: Counter[int] = Counter()
        for sp in spreads:
            spread_counter[int(sp)] += 1
        spread_histogram = dict(sorted(spread_counter.items()))

        return DistributionResult(
            sum_mean=sum_mean,
            sum_std=sum_std,
            sum_histogram=sum_histogram,
            spread_mean=spread_mean,
            spread_std=spread_std,
            spread_histogram=spread_histogram,
        )

    # ── Static scoring helpers ───────────────────────────────────────

    @staticmethod
    def score_sum(sum_val: int, mean: float, std: float) -> float:
        """Score a combination sum using a Gaussian likelihood.

        Returns ``exp(-0.5 * z^2)`` where ``z = (sum_val - mean) / std``.
        This yields 1.0 when the sum equals the historical mean and
        decays symmetrically as the sum moves away.

        Parameters
        ----------
        sum_val:
            Sum of the candidate combination.
        mean:
            Historical mean of draw sums.
        std:
            Historical standard deviation of draw sums.

        Returns
        -------
        float
            Score in ``(0, 1]``.
        """
        if std <= 0:
            return 0.5
        z = (sum_val - mean) / std
        return math.exp(-0.5 * z * z)

    @staticmethod
    def score_spread(combination: list[int], game_def: GameDefinition) -> float:
        """Score a combination's spread (max - min) normalised by pool range.

        Returns ``spread / (pool_max - pool_min)`` clipped to ``[0, 1]``.
        A spread that covers the full pool range scores 1.0; a
        degenerate zero-range spread scores 0.0.

        Parameters
        ----------
        combination:
            List of drawn numbers.
        game_def:
            Game specification.

        Returns
        -------
        float
            Score in ``[0, 1]``.
        """
        if len(combination) < 2:
            return 0.0
        pool_range = game_def.pool_max - game_def.pool_min
        if pool_range == 0:
            return 0.5
        spread = max(combination) - min(combination)
        return max(0.0, min(1.0, spread / pool_range))
