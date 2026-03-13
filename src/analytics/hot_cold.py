"""
Hot/cold classification for lottery numbers using binomial z-scores.

For each number in the pool, counts how often it appeared in a trailing
window of draws, computes a z-score against the binomial expectation
under a fair draw, and classifies numbers into five temperature bands.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from src.config.constants import GameDefinition


# ── Result dataclass ──────────────────────────────────────────────────────


@dataclass
class HotColdResult:
    """Complete output of :class:`HotColdAnalyzer`.

    Attributes:
        per_number: Mapping ``{number: {count, z_score, classification}}``
            where *count* is the observed appearances in the window,
            *z_score* is the standard score against the binomial mean,
            and *classification* is one of ``very_hot``, ``hot``,
            ``neutral``, ``cold``, or ``very_cold``.
        window: Number of trailing draws used for the analysis.
    """

    per_number: dict[int, dict]
    window: int


# ── Classification thresholds ────────────────────────────────────────────

_CLASSIFICATION_THRESHOLDS: list[tuple[float, str]] = [
    (1.5, "very_hot"),
    (0.5, "hot"),
    (-0.5, "neutral"),
    (-1.5, "cold"),
]
_DEFAULT_CLASSIFICATION = "very_cold"


def _classify(z_score: float) -> str:
    """Map a z-score to a temperature classification."""
    for threshold, label in _CLASSIFICATION_THRESHOLDS:
        if z_score > threshold:
            return label
    return _DEFAULT_CLASSIFICATION


# ── Analyzer ──────────────────────────────────────────────────────────────


class HotColdAnalyzer:
    """Classify numbers as hot or cold based on recent draw frequency.

    The underlying model is the **binomial distribution**: each draw selects
    ``number_count`` numbers from a pool of ``pool_size``, so the probability
    of any given number being drawn is ``p = number_count / pool_size``.

    Over *window* draws the expected count is ``window * p`` with standard
    deviation ``sqrt(window * p * (1 - p))``.  The z-score measures how
    far the observed count deviates from expectation in standard-deviation
    units.
    """

    def analyze(
        self,
        draws: np.ndarray,
        game_def: GameDefinition,
        window: int = 30,
    ) -> HotColdResult:
        """Run hot/cold analysis on the trailing *window* draws.

        Parameters
        ----------
        draws:
            ``(N, number_count)`` array, oldest draw first.
        game_def:
            Game specification.
        window:
            Number of most-recent draws to consider.  Clamped to the
            total number of available draws when fewer exist.

        Returns
        -------
        HotColdResult
        """
        n_draws = draws.shape[0]
        effective_window = min(window, n_draws)
        pool_size = game_def.pool_size
        number_count = game_def.number_count
        all_numbers = range(game_def.pool_min, game_def.pool_max + 1)

        # Probability that a single number appears in one draw.
        p = number_count / pool_size

        # Binomial expectation and standard deviation over the window.
        expected = effective_window * p
        std = math.sqrt(effective_window * p * (1.0 - p))

        # Count appearances in the last *effective_window* draws.
        window_draws = draws[-effective_window:]
        counts: dict[int, int] = {num: 0 for num in all_numbers}
        for num in window_draws.flat:
            counts[int(num)] += 1

        # Compute z-scores and classify.
        per_number: dict[int, dict] = {}
        for num in all_numbers:
            observed = counts[num]
            z_score = (observed - expected) / std if std > 0 else 0.0
            per_number[num] = {
                "count": observed,
                "z_score": z_score,
                "classification": _classify(z_score),
            }

        return HotColdResult(per_number=per_number, window=effective_window)
