"""
Shannon entropy analysis for lottery draw frequency distributions.

Measures how uniformly the historical draws are spread across all
numbers in the pool.  A perfectly uniform distribution (every number
drawn equally often) yields the maximum possible entropy; a degenerate
distribution where only one number ever appears yields zero entropy.

Also provides a static scoring function that evaluates how "diverse"
a candidate combination is in terms of the per-number historical
frequencies it draws from.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from src.config.constants import GameDefinition


# ── Result dataclass ──────────────────────────────────────────────────────


@dataclass
class EntropyResult:
    """Complete output of :class:`EntropyAnalyzer`.

    Attributes:
        entropy: Shannon entropy of the per-number frequency
            distribution (base-2, in bits).
        max_entropy: Maximum possible entropy for the pool
            (``log2(pool_size)``).
        normalized_entropy: ``entropy / max_entropy``, in ``[0, 1]``.
            Values close to 1 indicate a near-uniform historical
            frequency; values close to 0 indicate strong bias.
        per_number_frequencies: Mapping ``{number: relative_frequency}``
            where relative_frequency sums to 1.0 over all pool numbers.
    """

    entropy: float
    max_entropy: float
    normalized_entropy: float
    per_number_frequencies: dict[int, float]


# ── Analyzer ──────────────────────────────────────────────────────────────


class EntropyAnalyzer:
    """Compute Shannon entropy of the historical frequency distribution."""

    def analyze(
        self,
        draws: np.ndarray,
        game_def: GameDefinition,
    ) -> EntropyResult:
        """Run entropy analysis on all draws.

        Parameters
        ----------
        draws:
            ``(N, number_count)`` array, oldest draw first.
        game_def:
            Game specification.

        Returns
        -------
        EntropyResult
        """
        pool_size = game_def.pool_size
        all_numbers = range(game_def.pool_min, game_def.pool_max + 1)

        # ── Count raw appearances ────────────────────────────────────
        counts: dict[int, int] = {num: 0 for num in all_numbers}
        for num in draws.flat:
            counts[int(num)] += 1

        total = sum(counts.values())

        # ── Relative frequencies ─────────────────────────────────────
        per_number_frequencies: dict[int, float] = {}
        if total > 0:
            for num in all_numbers:
                per_number_frequencies[num] = counts[num] / total
        else:
            for num in all_numbers:
                per_number_frequencies[num] = 0.0

        # ── Shannon entropy (base 2) ────────────────────────────────
        entropy = 0.0
        for freq in per_number_frequencies.values():
            if freq > 0:
                entropy -= freq * math.log2(freq)

        max_entropy = math.log2(pool_size) if pool_size > 1 else 1.0
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0

        return EntropyResult(
            entropy=entropy,
            max_entropy=max_entropy,
            normalized_entropy=normalized_entropy,
            per_number_frequencies=per_number_frequencies,
        )

    # ── Static scoring helper ────────────────────────────────────────

    @staticmethod
    def score_combination_entropy(
        combination: list[int],
        frequencies: dict[int, float],
    ) -> float:
        """Score a combination based on the entropy of its chosen numbers' frequencies.

        Computes the Shannon entropy of the sub-distribution formed by
        the frequencies of the numbers in *combination*, then normalises
        by the maximum possible entropy for that many numbers
        (``log2(len(combination))``).

        A score of 1.0 means the combination draws numbers that are all
        equally frequent (maximum diversity).  A score near 0.0 means
        the combination is dominated by numbers of very unequal
        frequency.

        Parameters
        ----------
        combination:
            List of drawn numbers.
        frequencies:
            Per-number relative frequencies from an :class:`EntropyResult`.

        Returns
        -------
        float
            Score in ``[0, 1]``.
        """
        n = len(combination)
        if n <= 1:
            return 1.0  # Trivial case: one number is maximally "uniform".

        # Collect the raw frequencies for the chosen numbers.
        raw_freqs = [frequencies.get(num, 0.0) for num in combination]
        total = sum(raw_freqs)
        if total == 0:
            return 0.5  # No historical data: assume neutral.

        # Normalise to a probability distribution within the combination.
        probs = [f / total for f in raw_freqs]

        # Shannon entropy of the sub-distribution.
        entropy = 0.0
        for p in probs:
            if p > 0:
                entropy -= p * math.log2(p)

        max_entropy = math.log2(n)
        return entropy / max_entropy if max_entropy > 0 else 0.5
