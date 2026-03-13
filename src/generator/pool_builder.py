"""Tiered number pool builder for candidate generation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from src.config.constants import GameDefinition

logger = logging.getLogger(__name__)


@dataclass
class NumberPool:
    """Tiered number pool with per-number desirability scores."""

    tier_1: list[int] = field(default_factory=list)  # Top 25% - primary
    tier_2: list[int] = field(default_factory=list)  # 25-50% - secondary
    tier_3: list[int] = field(default_factory=list)  # 50-75% - neutral
    tier_4: list[int] = field(default_factory=list)  # Bottom 25% - contrarian
    scores: dict[int, float] = field(default_factory=dict)  # number -> desirability

    @property
    def all_numbers(self) -> list[int]:
        return self.tier_1 + self.tier_2 + self.tier_3 + self.tier_4

    def get_sampling_weights(self) -> tuple[list[int], np.ndarray]:
        """Return (numbers, weights) for numpy.random.choice."""
        numbers = self.all_numbers
        raw_weights = np.array([self.scores.get(n, 0.0) for n in numbers])
        # Ensure all weights are positive
        raw_weights = np.maximum(raw_weights, 0.01)
        weights = raw_weights / raw_weights.sum()
        return numbers, weights


class PoolBuilder:
    """Build tiered number pools from analysis results."""

    def build(
        self,
        per_number_scores: dict[str, dict[int, float]],
        game_def: GameDefinition,
        tier_weights: dict[str, float] | None = None,
    ) -> NumberPool:
        """
        Build a tiered number pool from per-number feature scores.

        Args:
            per_number_scores: {feature_name: {number: score}} - per-number 0-1 scores
            game_def: Game definition
            tier_weights: Weights for combining features into desirability.
                         Defaults to equal weighting.
        """
        if tier_weights is None:
            tier_weights = {
                "frequency_score": 0.35,
                "recency_score": 0.30,
                "hot_cold_score": 0.20,
                "pair_partner_score": 0.15,
            }

        pool_range = list(range(game_def.pool_min, game_def.pool_max + 1))
        pool_size = len(pool_range)

        # Compute composite desirability for each number
        desirability: dict[int, float] = {}
        for number in pool_range:
            score = 0.0
            total_weight = 0.0
            for feature, weight in tier_weights.items():
                feature_scores = per_number_scores.get(feature, {})
                if number in feature_scores:
                    score += weight * feature_scores[number]
                    total_weight += weight
            desirability[number] = score / max(total_weight, 1e-9)

        # Sort numbers by desirability descending
        sorted_numbers = sorted(pool_range, key=lambda n: desirability[n], reverse=True)

        # Tier assignment by quartiles
        q1 = pool_size // 4
        q2 = pool_size // 2
        q3 = 3 * pool_size // 4

        pool = NumberPool(
            tier_1=sorted_numbers[:q1],
            tier_2=sorted_numbers[q1:q2],
            tier_3=sorted_numbers[q2:q3],
            tier_4=sorted_numbers[q3:],
            scores=desirability,
        )

        logger.info(
            "Built number pool: T1=%d, T2=%d, T3=%d, T4=%d numbers",
            len(pool.tier_1),
            len(pool.tier_2),
            len(pool.tier_3),
            len(pool.tier_4),
        )
        return pool
