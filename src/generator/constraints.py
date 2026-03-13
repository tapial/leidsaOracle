"""Structural constraint filters for candidate combinations."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.config.constants import GameDefinition

logger = logging.getLogger(__name__)


@dataclass
class ConstraintConfig:
    """Configurable constraint parameters."""

    max_odd_even_diff: int = 4       # Max allowed |odd - even| (for 6 nums: allow 1:5 but not 0:6)
    max_low_high_diff: int = 4       # Max allowed |low - high|
    max_consecutive: int = 2         # Max consecutive numbers allowed
    min_sum_z: float = -2.0          # Min z-score for sum (relative to historical)
    max_sum_z: float = 2.0           # Max z-score for sum
    min_spread_pct: float = 0.4      # Minimum spread as fraction of pool range


class CombinationConstraints:
    """Filter combinations based on structural constraints."""

    def __init__(
        self,
        game_def: GameDefinition,
        sum_mean: float | None = None,
        sum_std: float | None = None,
        config: ConstraintConfig | None = None,
    ):
        self.game_def = game_def
        self.sum_mean = sum_mean
        self.sum_std = sum_std
        self.config = config or ConstraintConfig()

    def is_valid(self, combination: list[int]) -> bool:
        """Check all structural constraints. Returns True if valid."""
        if not self._check_odd_even(combination):
            return False
        if not self._check_low_high(combination):
            return False
        if not self._check_consecutive(combination):
            return False
        if not self._check_sum(combination):
            return False
        if not self._check_spread(combination):
            return False
        if not self._check_decade_spread(combination):
            return False
        return True

    def _check_odd_even(self, combo: list[int]) -> bool:
        odd = sum(1 for n in combo if n % 2 != 0)
        even = len(combo) - odd
        return abs(odd - even) <= self.config.max_odd_even_diff

    def _check_low_high(self, combo: list[int]) -> bool:
        midpoint = (self.game_def.pool_min + self.game_def.pool_max) / 2
        low = sum(1 for n in combo if n <= midpoint)
        high = len(combo) - low
        return abs(low - high) <= self.config.max_low_high_diff

    def _check_consecutive(self, combo: list[int]) -> bool:
        """No more than max_consecutive sequential numbers."""
        sorted_combo = sorted(combo)
        streak = 1
        for i in range(1, len(sorted_combo)):
            if sorted_combo[i] == sorted_combo[i - 1] + 1:
                streak += 1
                if streak > self.config.max_consecutive:
                    return False
            else:
                streak = 1
        return True

    def _check_sum(self, combo: list[int]) -> bool:
        if self.sum_mean is None or self.sum_std is None or self.sum_std == 0:
            return True
        total = sum(combo)
        z = (total - self.sum_mean) / self.sum_std
        return self.config.min_sum_z <= z <= self.config.max_sum_z

    def _check_spread(self, combo: list[int]) -> bool:
        spread = max(combo) - min(combo)
        pool_range = self.game_def.pool_max - self.game_def.pool_min
        return (spread / pool_range) >= self.config.min_spread_pct

    def _check_decade_spread(self, combo: list[int]) -> bool:
        """Ensure numbers aren't all in the same decade."""
        decades = {n // 10 for n in combo}
        return len(decades) >= 2

    def filter_valid(self, candidates: list[list[int]]) -> list[list[int]]:
        """Filter a list of candidates, returning only valid ones."""
        valid = [c for c in candidates if self.is_valid(c)]
        rejected = len(candidates) - len(valid)
        if rejected > 0:
            logger.debug(
                "Constraints filtered %d/%d candidates (%.1f%% rejection rate)",
                rejected,
                len(candidates),
                100 * rejected / max(len(candidates), 1),
            )
        return valid
