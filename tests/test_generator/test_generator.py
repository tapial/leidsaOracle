"""Tests for the combination generator pipeline."""

from __future__ import annotations

import numpy as np
import pytest

from src.config.constants import GAME_REGISTRY
from src.config.settings import get_settings
from src.config.weights import DEFAULT_WEIGHTS


class TestPoolBuilder:
    """Tests for pool building."""

    def test_build_returns_pool(self, sample_draws, loto_game):
        from src.analytics.engine import AnalyticsEngine
        from src.generator.pool_builder import PoolBuilder

        settings = get_settings()
        engine = AnalyticsEngine(loto_game, settings)
        result = engine.run_full_analysis(sample_draws)
        scores = engine.build_per_number_scores(result)

        pool_builder = PoolBuilder()
        pool = pool_builder.build(scores, loto_game)

        assert len(pool.all_numbers) == loto_game.pool_size
        assert all(loto_game.pool_min <= n <= loto_game.pool_max for n in pool.all_numbers)


class TestConstraints:
    """Tests for combination constraints."""

    def test_valid_combination_passes(self, loto_game):
        from src.generator.constraints import CombinationConstraints

        constraints = CombinationConstraints(loto_game, sum_mean=120, sum_std=20)
        valid = constraints.filter_valid([[3, 7, 15, 22, 28, 35]])
        assert len(valid) == 1

    def test_wrong_count_rejected(self, loto_game):
        from src.generator.constraints import CombinationConstraints

        constraints = CombinationConstraints(loto_game, sum_mean=120, sum_std=20)
        valid = constraints.filter_valid([[1, 2, 3]])  # Too few numbers
        assert len(valid) == 0


class TestCombinationGenerator:
    """Tests for the full generation pipeline."""

    def test_generates_correct_count(self, sample_draws, loto_game):
        from src.analytics.engine import AnalyticsEngine
        from src.generator.combination_generator import CombinationGenerator, GenerationConfig
        from src.generator.constraints import CombinationConstraints
        from src.generator.pool_builder import PoolBuilder
        from src.scoring.ensemble import EnsembleScorer
        from src.scoring.feature_scores import AnalysisData, FeatureScorer

        settings = get_settings()
        engine = AnalyticsEngine(loto_game, settings)
        analysis = engine.run_full_analysis(sample_draws)
        per_number_scores = engine.build_per_number_scores(analysis)

        pool = PoolBuilder().build(per_number_scores, loto_game)
        constraints = CombinationConstraints(
            loto_game,
            sum_mean=analysis.distribution.sum_mean,
            sum_std=analysis.distribution.sum_std,
        )

        # Build scorer — recency.per_number has NumberRecency dataclass objects
        freq = analysis.frequency
        max_count = max(freq.global_counts.values()) if freq.global_counts else 1
        analysis_data = AnalysisData(
            frequency_percentiles={n: c / max_count for n, c in freq.global_counts.items()},
            overdue_ratios={
                n: nr.overdue_ratio
                for n, nr in analysis.recency.per_number.items()
            },
            hot_cold_z_scores={
                n: d.get("z_score", 0.0) if isinstance(d, dict) else 0.0
                for n, d in analysis.hot_cold.per_number.items()
            },
            pair_lifts={},
            triplet_lifts={},
            sum_mean=analysis.distribution.sum_mean,
            sum_std=analysis.distribution.sum_std,
            number_frequencies={
                n: c / max(sum(freq.global_counts.values()), 1)
                for n, c in freq.global_counts.items()
            },
        )
        feature_scorer = FeatureScorer(loto_game, analysis_data)
        ensemble_scorer = EnsembleScorer(DEFAULT_WEIGHTS)

        def scorer_fn(combo):
            fs = feature_scorer.score(combo)
            es = ensemble_scorer.score(fs)
            return fs, es

        gen_config = GenerationConfig(
            candidate_pool_size=500,
            final_count=10,
            min_hamming_distance=3,
            seed=42,
        )
        generator = CombinationGenerator(loto_game, gen_config)
        results = generator.generate(pool, constraints, scorer_fn, DEFAULT_WEIGHTS)

        assert len(results) == 10
        # All combinations should have 6 numbers in range
        for cand in results:
            assert len(cand.numbers) == 6
            assert all(1 <= n <= 38 for n in cand.numbers)


class TestDiversity:
    """Tests for diversity enforcement."""

    def test_hamming_distance(self):
        from src.generator.diversity import hamming_distance

        # hamming_distance = len(symmetric_difference) // 2
        a = [1, 2, 3, 4, 5, 6]
        b = [1, 2, 3, 4, 5, 7]  # 1 number different
        assert hamming_distance(a, b) == 1

        c = [1, 2, 3, 4, 5, 6]
        d = [1, 2, 3, 7, 8, 9]  # 3 numbers different
        assert hamming_distance(c, d) == 3

    def test_enforcer_min_distance(self):
        from src.generator.diversity import DiversityEnforcer, ScoredCandidate

        candidates = [
            ScoredCandidate(numbers=[1, 2, 3, 4, 5, 6], ensemble_score=0.9, feature_scores={}),
            ScoredCandidate(numbers=[1, 2, 3, 4, 5, 7], ensemble_score=0.85, feature_scores={}),
            ScoredCandidate(numbers=[10, 20, 25, 30, 35, 38], ensemble_score=0.8, feature_scores={}),
            ScoredCandidate(numbers=[5, 10, 15, 20, 25, 30], ensemble_score=0.75, feature_scores={}),
        ]

        enforcer = DiversityEnforcer(min_hamming=3)
        final = enforcer.enforce(candidates, 3)
        assert len(final) >= 1
