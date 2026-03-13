"""Individual feature score computation (0-1 normalized) for lottery combinations."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from src.config.constants import GameDefinition

logger = logging.getLogger(__name__)


@dataclass
class AnalysisData:
    """Lightweight container for pre-computed analysis data needed by the scorer."""

    # Per-number data
    frequency_percentiles: dict[int, float]  # number -> percentile (0-1)
    overdue_ratios: dict[int, float]         # number -> overdue_ratio (gap/avg_gap)
    hot_cold_z_scores: dict[int, float]      # number -> z_score
    pair_lifts: dict[tuple[int, int], float]  # (i,j) -> lift where i<j
    triplet_lifts: dict[tuple[int, int, int], float]  # (i,j,k) -> lift where i<j<k

    # Distribution stats
    sum_mean: float
    sum_std: float
    number_frequencies: dict[int, float]     # number -> frequency proportion


class FeatureScorer:
    """Compute 10 individual 0-1 normalized feature scores for a combination."""

    def __init__(self, game_def: GameDefinition, analysis: AnalysisData):
        self.game_def = game_def
        self.analysis = analysis

    def score(self, combination: list[int]) -> dict[str, float]:
        """
        Compute all 10 feature scores for a combination.

        Returns:
            Dictionary mapping feature name to score in [0, 1].
        """
        return {
            "frequency_score": self._frequency_score(combination),
            "recency_score": self._recency_score(combination),
            "hot_cold_score": self._hot_cold_score(combination),
            "pair_score": self._pair_score(combination),
            "triplet_score": self._triplet_score(combination),
            "odd_even_score": self._odd_even_score(combination),
            "low_high_score": self._low_high_score(combination),
            "sum_score": self._sum_score(combination),
            "spread_score": self._spread_score(combination),
            "entropy_score": self._entropy_score(combination),
        }

    def _frequency_score(self, combo: list[int]) -> float:
        """Mean of per-number frequency percentiles."""
        scores = [self.analysis.frequency_percentiles.get(n, 0.5) for n in combo]
        return sum(scores) / len(scores) if scores else 0.5

    def _recency_score(self, combo: list[int]) -> float:
        """Mean of per-number overdue ratios, capped and normalized."""
        scores = []
        for n in combo:
            ratio = self.analysis.overdue_ratios.get(n, 1.0)
            # Cap at 1.0: numbers overdue by 2x their avg gap get max score
            scores.append(min(ratio / 2.0, 1.0))
        return sum(scores) / len(scores) if scores else 0.5

    def _hot_cold_score(self, combo: list[int]) -> float:
        """Mean of z-score mappings. Maps z ∈ [-3, 3] to [0, 1]."""
        scores = []
        for n in combo:
            z = self.analysis.hot_cold_z_scores.get(n, 0.0)
            score = max(0.0, min(1.0, (z + 3.0) / 6.0))
            scores.append(score)
        return sum(scores) / len(scores) if scores else 0.5

    def _pair_score(self, combo: list[int]) -> float:
        """Mean lift of all C(n,2) pairs in the combination, normalized."""
        lifts = []
        for i in range(len(combo)):
            for j in range(i + 1, len(combo)):
                pair = (min(combo[i], combo[j]), max(combo[i], combo[j]))
                lift = self.analysis.pair_lifts.get(pair, 1.0)
                lifts.append(lift)

        if not lifts:
            return 0.5

        mean_lift = sum(lifts) / len(lifts)
        # Normalize: lift of 1.0 = random expectation -> 0.5; lift of 2.0 -> 1.0
        return max(0.0, min(1.0, mean_lift / 2.0))

    def _triplet_score(self, combo: list[int]) -> float:
        """Mean lift of all C(n,3) triplets in the combination, normalized."""
        lifts = []
        for i in range(len(combo)):
            for j in range(i + 1, len(combo)):
                for k in range(j + 1, len(combo)):
                    triplet = tuple(sorted([combo[i], combo[j], combo[k]]))
                    lift = self.analysis.triplet_lifts.get(triplet, 1.0)
                    lifts.append(lift)

        if not lifts:
            return 0.5

        mean_lift = sum(lifts) / len(lifts)
        return max(0.0, min(1.0, mean_lift / 2.0))

    def _odd_even_score(self, combo: list[int]) -> float:
        """Score = 1 - |odd - even| / n. Perfect 3/3 split -> 1.0."""
        odd = sum(1 for n in combo if n % 2 != 0)
        even = len(combo) - odd
        return 1.0 - abs(odd - even) / len(combo)

    def _low_high_score(self, combo: list[int]) -> float:
        """Score = 1 - |low - high| / n."""
        midpoint = (self.game_def.pool_min + self.game_def.pool_max) / 2
        low = sum(1 for n in combo if n <= midpoint)
        high = len(combo) - low
        return 1.0 - abs(low - high) / len(combo)

    def _sum_score(self, combo: list[int]) -> float:
        """Gaussian: exp(-0.5 * ((sum - mean) / std)^2). 1.0 at mean, decays."""
        total = sum(combo)
        if self.analysis.sum_std == 0:
            return 0.5
        z = (total - self.analysis.sum_mean) / self.analysis.sum_std
        return math.exp(-0.5 * z * z)

    def _spread_score(self, combo: list[int]) -> float:
        """(max - min) / (pool_max - pool_min). Good spread -> high score."""
        spread = max(combo) - min(combo)
        pool_range = self.game_def.pool_max - self.game_def.pool_min
        if pool_range == 0:
            return 0.5
        return spread / pool_range

    def _entropy_score(self, combo: list[int]) -> float:
        """Entropy of the frequency distribution of chosen numbers."""
        freqs = [self.analysis.number_frequencies.get(n, 0.0) for n in combo]
        total = sum(freqs)
        if total == 0:
            return 0.5

        # Normalize to probabilities
        probs = [f / total for f in freqs]

        # Shannon entropy
        entropy = 0.0
        for p in probs:
            if p > 0:
                entropy -= p * math.log2(p)

        # Max entropy for n items = log2(n)
        max_entropy = math.log2(len(combo)) if len(combo) > 1 else 1.0

        return entropy / max_entropy if max_entropy > 0 else 0.5
