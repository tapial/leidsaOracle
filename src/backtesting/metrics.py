"""Backtesting metrics: hit rates, baselines, feature stability, calibration."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np
from scipy import stats as scipy_stats

from src.backtesting.walk_forward import BacktestRunResult, BacktestStep
from src.config.constants import GameDefinition

logger = logging.getLogger(__name__)


def _comb(n: int, k: int) -> int:
    """Compute binomial coefficient C(n, k)."""
    return math.comb(n, k)


@dataclass
class HypergeometricBaseline:
    """Random baseline match probabilities via hypergeometric distribution."""

    probabilities: dict[int, float]  # match_k -> P(match=k)
    pool_size: int
    number_count: int


@dataclass
class MetricsSummary:
    """Aggregated backtest metrics."""

    # Hit rates
    number_hit_rate: float  # fraction of generated numbers that appeared
    number_hit_baseline: float  # random baseline
    match_distribution: dict[int, float]  # match_k -> fraction of combos
    random_baseline: HypergeometricBaseline

    # Improvement
    improvement_factors: dict[int, float]  # match_k -> actual/baseline

    # Feature stability
    feature_stability: dict[str, dict[str, float]]  # feature -> {mean, std, cv}

    # Calibration
    score_match_correlation: float  # Spearman rank correlation
    score_match_p_value: float

    # Summary
    total_steps: int
    total_combos_evaluated: int


class BacktestMetrics:
    """Compute backtest evaluation metrics."""

    def __init__(self, game_def: GameDefinition):
        self.game_def = game_def

    def compute(self, result: BacktestRunResult) -> MetricsSummary:
        """Compute all metrics from a backtest run."""
        steps = result.steps
        if not steps:
            return self._empty_metrics()

        baseline = self._hypergeometric_baseline()
        match_dist = self._match_distribution(steps)
        number_hit = self._number_hit_rate(steps)
        improvements = self._improvement_factors(match_dist, baseline)
        stability = self._feature_stability(steps)
        corr, p_val = self._score_match_correlation(steps)

        total_combos = sum(len(s.match_counts) for s in steps)

        return MetricsSummary(
            number_hit_rate=number_hit,
            number_hit_baseline=self.game_def.number_count / self.game_def.pool_size,
            match_distribution=match_dist,
            random_baseline=baseline,
            improvement_factors=improvements,
            feature_stability=stability,
            score_match_correlation=corr,
            score_match_p_value=p_val,
            total_steps=len(steps),
            total_combos_evaluated=total_combos,
        )

    def _hypergeometric_baseline(self) -> HypergeometricBaseline:
        """
        Compute random baseline match probabilities.

        P(match=k) = C(nc,k) * C(pool-nc, nc-k) / C(pool, nc)
        where nc = number_count, pool = pool_size.
        """
        nc = self.game_def.number_count
        pool = self.game_def.pool_size
        probs: dict[int, float] = {}

        total_combos = _comb(pool, nc)
        for k in range(nc + 1):
            numerator = _comb(nc, k) * _comb(pool - nc, nc - k)
            probs[k] = numerator / total_combos if total_combos > 0 else 0.0

        return HypergeometricBaseline(
            probabilities=probs,
            pool_size=pool,
            number_count=nc,
        )

    def _match_distribution(self, steps: list[BacktestStep]) -> dict[int, float]:
        """Fraction of generated combos achieving each match level."""
        counts: dict[int, int] = {}
        total = 0
        for step in steps:
            for mc in step.match_counts:
                counts[mc] = counts.get(mc, 0) + 1
                total += 1

        nc = self.game_def.number_count
        dist = {}
        for k in range(nc + 1):
            dist[k] = counts.get(k, 0) / max(total, 1)
        return dist

    def _number_hit_rate(self, steps: list[BacktestStep]) -> float:
        """
        Fraction of individual numbers in generated combos that appeared in actual draws.

        Baseline = number_count / pool_size.
        """
        hits = 0
        total = 0
        for step in steps:
            actual = set(step.test_draw)
            for combo in step.generated_numbers:
                for n in combo:
                    if n in actual:
                        hits += 1
                    total += 1
        return hits / max(total, 1)

    def _improvement_factors(
        self,
        match_dist: dict[int, float],
        baseline: HypergeometricBaseline,
    ) -> dict[int, float]:
        """Improvement factor = actual_rate / baseline_rate for each match level."""
        factors = {}
        for k, actual in match_dist.items():
            base = baseline.probabilities.get(k, 0.0)
            if base > 0:
                factors[k] = actual / base
            else:
                factors[k] = float("inf") if actual > 0 else 1.0
        return factors

    def _feature_stability(self, steps: list[BacktestStep]) -> dict[str, dict[str, float]]:
        """
        Track which features are most stable (low coefficient of variation).

        This uses the match counts as a proxy — we track ensemble score behavior.
        """
        if not steps or not steps[0].ensemble_scores:
            return {}

        # Track per-step average ensemble scores
        avg_scores = [
            np.mean(step.ensemble_scores) if step.ensemble_scores else 0.0
            for step in steps
        ]
        avg_matches = [
            np.mean(step.match_counts) if step.match_counts else 0.0
            for step in steps
        ]

        # Ensemble stability
        stability: dict[str, dict[str, float]] = {}
        if len(avg_scores) > 1:
            scores_arr = np.array(avg_scores)
            stability["ensemble_score"] = {
                "mean": float(np.mean(scores_arr)),
                "std": float(np.std(scores_arr)),
                "cv": float(np.std(scores_arr) / max(np.mean(scores_arr), 1e-9)),
            }

        if len(avg_matches) > 1:
            matches_arr = np.array(avg_matches)
            stability["match_count"] = {
                "mean": float(np.mean(matches_arr)),
                "std": float(np.std(matches_arr)),
                "cv": float(np.std(matches_arr) / max(np.mean(matches_arr), 1e-9)),
            }

        return stability

    def _score_match_correlation(
        self, steps: list[BacktestStep]
    ) -> tuple[float, float]:
        """
        Spearman rank correlation between ensemble score and match count.

        Positive correlation means higher-scored combos genuinely tend to match more.
        """
        all_scores = []
        all_matches = []
        for step in steps:
            for score, match in zip(step.ensemble_scores, step.match_counts):
                all_scores.append(score)
                all_matches.append(match)

        if len(all_scores) < 10:
            return 0.0, 1.0

        try:
            corr, p_val = scipy_stats.spearmanr(all_scores, all_matches)
            return float(corr), float(p_val)
        except Exception:
            return 0.0, 1.0

    def _empty_metrics(self) -> MetricsSummary:
        """Return empty metrics when no steps were executed."""
        baseline = self._hypergeometric_baseline()
        return MetricsSummary(
            number_hit_rate=0.0,
            number_hit_baseline=self.game_def.number_count / self.game_def.pool_size,
            match_distribution={k: 0.0 for k in range(self.game_def.number_count + 1)},
            random_baseline=baseline,
            improvement_factors={k: 0.0 for k in range(self.game_def.number_count + 1)},
            feature_stability={},
            score_match_correlation=0.0,
            score_match_p_value=1.0,
            total_steps=0,
            total_combos_evaluated=0,
        )
