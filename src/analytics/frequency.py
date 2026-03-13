"""
Frequency analysis for lottery draw numbers.

Computes global and rolling-window frequency counts, percentages, and
chi-square goodness-of-fit tests against the uniform distribution
expected from a fair lottery.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import chi2

from src.config.constants import GameDefinition


# ── Result dataclass ──────────────────────────────────────────────────────


@dataclass
class NumberFrequency:
    """Frequency statistics for a single number."""

    number: int
    count: int
    pct: float
    deviation: float  # (observed_pct - expected_pct)


@dataclass
class RollingWindow:
    """Frequency counts within a trailing window of *window_size* draws."""

    window_size: int
    counts: dict[int, int]  # number -> count in window
    pct: dict[int, float]  # number -> percentage in window


@dataclass
class FrequencyResult:
    """Complete output of :class:`FrequencyAnalyzer`."""

    total_draws: int
    pool_size: int
    number_count: int

    # Global aggregates
    global_counts: dict[int, int]
    global_pct: dict[int, float]
    expected_pct: float

    # Chi-square uniformity test
    chi_square_stat: float
    p_value: float
    is_uniform: bool  # True when p_value >= significance level (0.05)

    # Per-number breakdown
    per_number: dict[int, NumberFrequency]

    # Rolling windows
    rolling: dict[int, RollingWindow]  # window_size -> RollingWindow


# ── Analyzer ──────────────────────────────────────────────────────────────


class FrequencyAnalyzer:
    """Count per-number appearances and test for uniformity.

    Parameters
    ----------
    significance : float
        Significance level for the chi-square test (default 0.05).
    """

    def __init__(self, significance: float = 0.05) -> None:
        self.significance = significance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        draws: np.ndarray,
        game_def: GameDefinition,
        windows: list[int] | None = None,
    ) -> FrequencyResult:
        """Run frequency analysis on *draws*.

        Parameters
        ----------
        draws:
            NumPy array of shape ``(N, number_count)`` with draws sorted
            oldest-first (row 0 is the earliest draw).
        game_def:
            Game specification (pool bounds, number count, etc.).
        windows:
            Optional list of trailing-draw window sizes for rolling
            frequency.  Defaults to ``[30, 60, 90, 180]``.

        Returns
        -------
        FrequencyResult
        """
        if windows is None:
            windows = [30, 60, 90, 180]

        n_draws = draws.shape[0]
        pool_size = game_def.pool_size
        number_count = game_def.number_count
        all_numbers = range(game_def.pool_min, game_def.pool_max + 1)

        # ── Global counts ─────────────────────────────────────────────
        global_counts: dict[int, int] = {num: 0 for num in all_numbers}
        for num in draws.flat:
            global_counts[int(num)] += 1

        total_slots = n_draws * number_count
        global_pct: dict[int, float] = {
            num: (cnt / total_slots) if total_slots > 0 else 0.0
            for num, cnt in global_counts.items()
        }

        expected_pct = number_count / pool_size  # probability each number is in a draw

        # ── Chi-square goodness-of-fit ────────────────────────────────
        expected_count = total_slots / pool_size  # expected appearances per number
        chi_square_stat = sum(
            ((obs - expected_count) ** 2) / expected_count
            for obs in global_counts.values()
        ) if expected_count > 0 else 0.0

        df = pool_size - 1
        p_value = float(chi2.sf(chi_square_stat, df)) if df > 0 else 1.0
        is_uniform = p_value >= self.significance

        # ── Per-number detail ─────────────────────────────────────────
        per_number: dict[int, NumberFrequency] = {}
        for num in all_numbers:
            pct = global_pct[num]
            per_number[num] = NumberFrequency(
                number=num,
                count=global_counts[num],
                pct=pct,
                deviation=pct - expected_pct,
            )

        # ── Rolling windows ───────────────────────────────────────────
        rolling: dict[int, RollingWindow] = {}
        for w in windows:
            effective_w = min(w, n_draws)
            window_draws = draws[-effective_w:]  # last *w* draws
            w_counts: dict[int, int] = {num: 0 for num in all_numbers}
            for num in window_draws.flat:
                w_counts[int(num)] += 1

            w_total = effective_w * number_count
            w_pct: dict[int, float] = {
                num: (cnt / w_total) if w_total > 0 else 0.0
                for num, cnt in w_counts.items()
            }
            rolling[w] = RollingWindow(
                window_size=effective_w,
                counts=w_counts,
                pct=w_pct,
            )

        return FrequencyResult(
            total_draws=n_draws,
            pool_size=pool_size,
            number_count=number_count,
            global_counts=global_counts,
            global_pct=global_pct,
            expected_pct=expected_pct,
            chi_square_stat=chi_square_stat,
            p_value=p_value,
            is_uniform=is_uniform,
            per_number=per_number,
            rolling=rolling,
        )
