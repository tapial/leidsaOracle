"""Walk-forward backtesting engine with strict temporal isolation."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from src.config.constants import GameDefinition
from src.config.settings import Settings
from src.config.weights import DEFAULT_WEIGHTS

logger = logging.getLogger(__name__)


@dataclass
class BacktestStep:
    """Result of a single walk-forward step."""

    step_index: int
    train_size: int
    test_draw: list[int]  # actual draw numbers
    generated_numbers: list[list[int]]  # generated combinations
    match_counts: list[int]  # per-combo match count
    best_match: int
    ensemble_scores: list[float]


@dataclass
class BacktestConfig:
    """Walk-forward backtesting configuration."""

    train_window: int = 200
    test_window: int = 1
    step_size: int = 1
    combinations_per_step: int = 10
    max_steps: int | None = None
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    seed: int | None = 42


@dataclass
class BacktestRunResult:
    """Full result of a backtesting run."""

    config: BacktestConfig
    game_type: str
    steps: list[BacktestStep]
    total_steps: int
    elapsed_seconds: float
    run_date: datetime = field(default_factory=datetime.utcnow)


class WalkForwardBacktester:
    """
    Walk-forward backtesting engine.

    CRITICAL INVARIANT: Training data MUST be strictly BEFORE the test draw.
    This is enforced by array slicing: train = draws[i-window:i], test = draws[i].
    No future data ever leaks into the analysis.
    """

    def __init__(self, game_def: GameDefinition, settings: Settings):
        self.game_def = game_def
        self.settings = settings

    def run(
        self,
        all_draws: np.ndarray,
        config: BacktestConfig | None = None,
    ) -> BacktestRunResult:
        """
        Run walk-forward backtest.

        Args:
            all_draws: (N, number_count) matrix sorted oldest-first (index 0 = oldest).
            config: Backtesting configuration.

        Returns:
            BacktestRunResult with step-by-step details.
        """
        # Lazy imports to avoid circular dependencies
        from src.analytics.engine import AnalyticsEngine
        from src.generator.combination_generator import CombinationGenerator, GenerationConfig
        from src.generator.constraints import CombinationConstraints
        from src.generator.pool_builder import PoolBuilder
        from src.scoring.ensemble import EnsembleScorer
        from src.scoring.feature_scores import AnalysisData, FeatureScorer

        config = config or BacktestConfig()
        steps: list[BacktestStep] = []
        start_time = time.time()

        n_draws = len(all_draws)
        if n_draws < config.train_window + 1:
            logger.warning(
                "Not enough draws for backtesting: %d < %d + 1",
                n_draws, config.train_window,
            )
            return BacktestRunResult(
                config=config,
                game_type=self.game_def.code,
                steps=[],
                total_steps=0,
                elapsed_seconds=0.0,
            )

        # Determine step range
        start_idx = config.train_window
        end_idx = n_draws
        max_steps = config.max_steps or (end_idx - start_idx)

        engine = AnalyticsEngine(self.game_def, self.settings)
        ensemble_scorer = EnsembleScorer(config.weights)

        logger.info(
            "Starting walk-forward backtest: train=%d, steps=%d, combos/step=%d",
            config.train_window, min(max_steps, end_idx - start_idx),
            config.combinations_per_step,
        )

        step_count = 0
        for i in range(start_idx, end_idx, config.step_size):
            if step_count >= max_steps:
                break

            # TEMPORAL ISOLATION: train data is STRICTLY before test draw
            train_data = all_draws[i - config.train_window: i]
            test_draw = all_draws[i].tolist()

            # Verify temporal isolation (debug assertion)
            assert len(train_data) == config.train_window, (
                f"Train window mismatch: {len(train_data)} != {config.train_window}"
            )

            try:
                # Run analysis on training data ONLY
                analysis = engine.run_full_analysis(train_data)
                per_number_scores = engine.build_per_number_scores(analysis)

                # Build pool and constraints
                pool_builder = PoolBuilder()
                pool = pool_builder.build(per_number_scores, self.game_def)

                constraints = CombinationConstraints(
                    self.game_def,
                    sum_mean=analysis.distribution.sum_mean,
                    sum_std=analysis.distribution.sum_std,
                )

                # Build analysis data for feature scorer
                analysis_data = self._build_analysis_data(analysis)
                feature_scorer = FeatureScorer(self.game_def, analysis_data)

                def scorer_fn(combo: list[int]):
                    fs = feature_scorer.score(combo)
                    es = ensemble_scorer.score(fs)
                    return fs, es

                # Generate combinations
                gen_config = GenerationConfig(
                    candidate_pool_size=1000,  # Smaller for backtest speed
                    final_count=config.combinations_per_step,
                    min_hamming_distance=3,
                    seed=config.seed,
                )
                generator = CombinationGenerator(self.game_def, gen_config)
                candidates = generator.generate(pool, constraints, scorer_fn, config.weights)

                # Compare against actual test draw
                actual_set = set(test_draw)
                match_counts = []
                ensemble_scores = []
                generated_numbers = []

                for cand in candidates:
                    match = len(set(cand.numbers) & actual_set)
                    match_counts.append(match)
                    ensemble_scores.append(cand.ensemble_score)
                    generated_numbers.append(cand.numbers)

                steps.append(BacktestStep(
                    step_index=i,
                    train_size=len(train_data),
                    test_draw=test_draw,
                    generated_numbers=generated_numbers,
                    match_counts=match_counts,
                    best_match=max(match_counts) if match_counts else 0,
                    ensemble_scores=ensemble_scores,
                ))

            except Exception as exc:
                logger.warning("Backtest step %d failed: %s", i, exc)
                continue

            step_count += 1
            if step_count % 50 == 0:
                logger.info("Backtest progress: %d/%d steps", step_count, max_steps)

        elapsed = time.time() - start_time
        logger.info(
            "Backtest complete: %d steps in %.1fs (%.2f steps/sec)",
            len(steps), elapsed, len(steps) / max(elapsed, 0.01),
        )

        return BacktestRunResult(
            config=config,
            game_type=self.game_def.code,
            steps=steps,
            total_steps=len(steps),
            elapsed_seconds=elapsed,
        )

    def _build_analysis_data(self, analysis) -> AnalysisData:
        """Convert AnalysisResult to AnalysisData for the feature scorer."""
        from src.scoring.feature_scores import AnalysisData

        # Build frequency percentiles
        freq_data = analysis.frequency
        max_count = max(freq_data.global_counts.values()) if freq_data.global_counts else 1
        freq_percentiles = {
            n: count / max_count for n, count in freq_data.global_counts.items()
        }

        # Build overdue ratios
        overdue_ratios = {
            n: data.get("overdue_ratio", 1.0)
            for n, data in analysis.recency.per_number.items()
        }

        # Build z-scores
        z_scores = {
            n: data.get("z_score", 0.0)
            for n, data in analysis.hot_cold.per_number.items()
        }

        # Build pair lifts
        pair_lifts = {}
        for key, data in analysis.pairs.pairs.items():
            parts = key.split(",")
            if len(parts) == 2:
                pair_lifts[(int(parts[0]), int(parts[1]))] = data.get("lift", 1.0)

        # Build triplet lifts
        triplet_lifts = {}
        for key, data in analysis.triplets.triplets.items():
            parts = key.split(",")
            if len(parts) == 3:
                triplet_lifts[tuple(int(p) for p in parts)] = data.get("lift", 1.0)

        # Frequencies for entropy
        total = sum(freq_data.global_counts.values()) or 1
        number_frequencies = {
            n: count / total for n, count in freq_data.global_counts.items()
        }

        return AnalysisData(
            frequency_percentiles=freq_percentiles,
            overdue_ratios=overdue_ratios,
            hot_cold_z_scores=z_scores,
            pair_lifts=pair_lifts,
            triplet_lifts=triplet_lifts,
            sum_mean=analysis.distribution.sum_mean,
            sum_std=analysis.distribution.sum_std,
            number_frequencies=number_frequencies,
        )
