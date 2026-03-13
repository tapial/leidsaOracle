"""Three-strategy candidate combination generator."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from itertools import combinations

import numpy as np

from src.config.constants import GameDefinition
from src.config.weights import DEFAULT_WEIGHTS
from src.generator.constraints import CombinationConstraints
from src.generator.diversity import DiversityEnforcer, ScoredCandidate
from src.generator.pool_builder import NumberPool

logger = logging.getLogger(__name__)


@dataclass
class GenerationConfig:
    """Configuration for combination generation."""

    candidate_pool_size: int = 5000
    final_count: int = 10
    min_hamming_distance: int = 3
    weighted_random_pct: float = 0.60
    greedy_pct: float = 0.20
    balanced_pct: float = 0.20
    greedy_top_n: int = 15
    seed: int | None = None


class CombinationGenerator:
    """
    Generates diverse, high-scoring lottery combinations using three strategies:

    1. Weighted Random (60%): Sample numbers with probability proportional to desirability
    2. Top-N Greedy (20%): Enumerate combinations from top-scored numbers
    3. Balanced Random (20%): Force structural balance, then fill by weight
    """

    def __init__(
        self,
        game_def: GameDefinition,
        config: GenerationConfig | None = None,
    ):
        self.game_def = game_def
        self.config = config or GenerationConfig()
        self.rng = np.random.default_rng(self.config.seed)

    def generate(
        self,
        pool: NumberPool,
        constraints: CombinationConstraints,
        scorer_fn: callable,
        weights: dict[str, float] | None = None,
    ) -> list[ScoredCandidate]:
        """
        Generate diverse, high-scoring combinations.

        Args:
            pool: Tiered number pool with desirability scores.
            constraints: Structural constraint checker.
            scorer_fn: Function(combination: list[int]) -> (feature_scores: dict, ensemble: float)
            weights: Ensemble weights (default from config).

        Returns:
            List of final_count diverse, scored combinations.
        """
        weights = weights or DEFAULT_WEIGHTS
        cfg = self.config
        nc = self.game_def.number_count

        # Step 1: Generate raw candidates via 3 strategies
        n_weighted = int(cfg.candidate_pool_size * cfg.weighted_random_pct)
        n_greedy = int(cfg.candidate_pool_size * cfg.greedy_pct)
        n_balanced = cfg.candidate_pool_size - n_weighted - n_greedy

        logger.info(
            "Generating %d candidates: %d weighted + %d greedy + %d balanced",
            cfg.candidate_pool_size,
            n_weighted,
            n_greedy,
            n_balanced,
        )

        candidates: list[list[int]] = []
        candidates.extend(self._weighted_random(pool, n_weighted, nc))
        candidates.extend(self._top_n_greedy(pool, n_greedy, nc))
        candidates.extend(self._balanced_random(pool, n_balanced, nc))

        # Deduplicate
        seen: set[tuple[int, ...]] = set()
        unique_candidates: list[list[int]] = []
        for c in candidates:
            key = tuple(sorted(c))
            if key not in seen:
                seen.add(key)
                unique_candidates.append(sorted(c))
        logger.info("Unique candidates after dedup: %d", len(unique_candidates))

        # Step 2: Constraint filtering
        valid = constraints.filter_valid(unique_candidates)
        logger.info("Valid candidates after constraints: %d", len(valid))

        # Step 3: Score all valid candidates
        scored: list[ScoredCandidate] = []
        for combo in valid:
            feature_scores, ensemble = scorer_fn(combo)
            scored.append(ScoredCandidate(
                numbers=combo,
                ensemble_score=ensemble,
                feature_scores=feature_scores,
            ))

        # Step 4: Diversity enforcement
        enforcer = DiversityEnforcer(min_hamming=cfg.min_hamming_distance)
        final = enforcer.enforce(scored, cfg.final_count)

        # Assign ranks
        for i, combo in enumerate(final):
            combo.feature_scores["rank"] = i + 1

        logger.info("Generated %d diverse combinations", len(final))
        return final

    def _weighted_random(
        self,
        pool: NumberPool,
        count: int,
        nc: int,
    ) -> list[list[int]]:
        """Strategy A: Sample numbers with probability proportional to desirability."""
        numbers, weights = pool.get_sampling_weights()
        numbers_arr = np.array(numbers)
        results: list[list[int]] = []

        for _ in range(count):
            try:
                chosen = self.rng.choice(numbers_arr, size=nc, replace=False, p=weights)
                results.append(sorted(chosen.tolist()))
            except ValueError:
                # Fallback if weights are problematic
                chosen = self.rng.choice(numbers_arr, size=nc, replace=False)
                results.append(sorted(chosen.tolist()))

        return results

    def _top_n_greedy(
        self,
        pool: NumberPool,
        count: int,
        nc: int,
    ) -> list[list[int]]:
        """Strategy B: Enumerate combinations from top-N scored numbers."""
        # Take top numbers by score
        all_numbers = pool.all_numbers
        sorted_nums = sorted(all_numbers, key=lambda n: pool.scores.get(n, 0), reverse=True)
        top_n = sorted_nums[: self.config.greedy_top_n]

        if len(top_n) < nc:
            top_n = sorted_nums[:nc]

        # Generate all C(top_n, nc) combinations
        all_combos = [sorted(c) for c in combinations(top_n, nc)]

        if len(all_combos) <= count:
            return all_combos

        # Score by sum of desirability and take top `count`
        combo_scores = [
            (combo, sum(pool.scores.get(n, 0) for n in combo))
            for combo in all_combos
        ]
        combo_scores.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in combo_scores[:count]]

    def _balanced_random(
        self,
        pool: NumberPool,
        count: int,
        nc: int,
    ) -> list[list[int]]:
        """Strategy C: Force structural balance, then fill by weight."""
        results: list[list[int]] = []
        all_numbers = pool.all_numbers
        midpoint = (self.game_def.pool_min + self.game_def.pool_max) / 2

        low_numbers = [n for n in all_numbers if n <= midpoint]
        high_numbers = [n for n in all_numbers if n > midpoint]
        odd_numbers = [n for n in all_numbers if n % 2 != 0]
        even_numbers = [n for n in all_numbers if n % 2 == 0]

        half = nc // 2
        remainder = nc % 2

        for _ in range(count):
            try:
                combo: set[int] = set()

                # Pick half from low, half from high (or half+1 if odd)
                n_low = half + (1 if self.rng.random() > 0.5 and remainder else 0)
                n_high = nc - n_low

                low_pool = [n for n in low_numbers if n not in combo]
                if len(low_pool) >= n_low:
                    low_weights = np.array([pool.scores.get(n, 0.01) for n in low_pool])
                    low_weights = np.maximum(low_weights, 0.01)
                    low_weights /= low_weights.sum()
                    chosen_low = self.rng.choice(low_pool, size=n_low, replace=False, p=low_weights)
                    combo.update(chosen_low.tolist())

                high_pool = [n for n in high_numbers if n not in combo]
                needed = nc - len(combo)
                if len(high_pool) >= needed and needed > 0:
                    high_weights = np.array([pool.scores.get(n, 0.01) for n in high_pool])
                    high_weights = np.maximum(high_weights, 0.01)
                    high_weights /= high_weights.sum()
                    chosen_high = self.rng.choice(
                        high_pool, size=needed, replace=False, p=high_weights
                    )
                    combo.update(chosen_high.tolist())

                # Fill any remaining
                if len(combo) < nc:
                    remaining = [n for n in all_numbers if n not in combo]
                    extra = self.rng.choice(remaining, size=nc - len(combo), replace=False)
                    combo.update(extra.tolist())

                results.append(sorted(combo))
            except (ValueError, IndexError):
                # Fallback: pure random
                chosen = self.rng.choice(all_numbers, size=nc, replace=False)
                results.append(sorted(chosen.tolist()))

        return results
