"""
Monte Carlo simulation for estimating the score distribution of random combinations.

Generates a large number of random combinations drawn with probability
proportional to per-number desirability scores, computes the sum-of-scores
for each, and builds a reference distribution.  This distribution is then
used to place any candidate combination's score into a percentile context:
"how does this combination compare to a random one drawn from the same
weighted pool?"
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import percentileofscore

from src.config.constants import GameDefinition


# ── Result dataclass ──────────────────────────────────────────────────────


@dataclass
class MonteCarloResult:
    """Complete output of :class:`MonteCarloSimulator`.

    Attributes:
        mean: Mean of the simulated score distribution.
        std: Standard deviation of the simulated score distribution.
        percentiles: Mapping of standard percentile markers to their
            corresponding score values.
        scores: Raw array of all simulated combination scores (sorted
            ascending for efficient percentile lookups).
    """

    mean: float
    std: float
    percentiles: dict[int, float]
    scores: np.ndarray


# ── Standard percentile markers ─────────────────────────────────────────

_PERCENTILE_MARKERS: tuple[int, ...] = (5, 10, 25, 50, 75, 90, 95)


# ── Simulator ────────────────────────────────────────────────────────────


class MonteCarloSimulator:
    """Estimate the random-baseline score distribution via simulation.

    Each iteration:

    1. Draw ``number_count`` numbers without replacement, with probability
       proportional to the provided *number_scores*.
    2. Sum the scores of the drawn numbers to get a single "combination
       score".

    After all iterations, the distribution of combination scores gives
    a baseline against which real candidates can be compared.
    """

    def simulate(
        self,
        game_def: GameDefinition,
        number_scores: dict[int, float],
        iterations: int = 100_000,
        seed: int | None = None,
    ) -> MonteCarloResult:
        """Run the Monte Carlo simulation.

        Parameters
        ----------
        game_def:
            Game specification (pool bounds, number count).
        number_scores:
            Mapping ``{number: desirability_score}`` for every number in
            the pool.  Scores should be non-negative.  Missing numbers
            receive a small default weight.
        iterations:
            Number of random combinations to generate.
        seed:
            Optional RNG seed for reproducibility.

        Returns
        -------
        MonteCarloResult
        """
        rng = np.random.default_rng(seed)

        all_numbers = list(range(game_def.pool_min, game_def.pool_max + 1))
        pool_size = len(all_numbers)
        number_count = game_def.number_count

        # Build aligned arrays: numbers and their corresponding scores.
        numbers_arr = np.array(all_numbers, dtype=np.int32)
        raw_weights = np.array(
            [max(number_scores.get(n, 0.0), 0.01) for n in all_numbers],
            dtype=np.float64,
        )
        probabilities = raw_weights / raw_weights.sum()

        # Pre-compute score lookup for fast vectorised access.
        # Build a dense array indexed by (number - pool_min).
        score_lookup = np.zeros(pool_size, dtype=np.float64)
        for idx, num in enumerate(all_numbers):
            score_lookup[idx] = number_scores.get(num, 0.0)

        # ── Simulation loop ──────────────────────────────────────────
        combo_scores = np.empty(iterations, dtype=np.float64)

        for i in range(iterations):
            chosen_indices = rng.choice(
                pool_size,
                size=number_count,
                replace=False,
                p=probabilities,
            )
            combo_scores[i] = score_lookup[chosen_indices].sum()

        # ── Aggregate statistics ─────────────────────────────────────
        combo_scores.sort()

        mean = float(np.mean(combo_scores))
        std = float(np.std(combo_scores, ddof=1)) if iterations > 1 else 0.0

        percentiles: dict[int, float] = {}
        for pct in _PERCENTILE_MARKERS:
            percentiles[pct] = float(np.percentile(combo_scores, pct))

        return MonteCarloResult(
            mean=mean,
            std=std,
            percentiles=percentiles,
            scores=combo_scores,
        )

    @staticmethod
    def get_percentile(score: float, result: MonteCarloResult) -> float:
        """Compute the percentile rank of *score* within the simulation distribution.

        Uses scipy's ``percentileofscore`` with ``kind='rank'`` for
        interpolated ranking.

        Parameters
        ----------
        score:
            The combination score to evaluate.
        result:
            A previously computed :class:`MonteCarloResult`.

        Returns
        -------
        float
            Percentile rank in ``[0, 100]``.
        """
        if len(result.scores) == 0:
            return 50.0
        return float(percentileofscore(result.scores, score, kind="rank"))
