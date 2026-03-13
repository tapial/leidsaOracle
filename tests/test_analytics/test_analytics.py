"""Tests for analytics modules."""

from __future__ import annotations

import numpy as np
import pytest

from src.config.constants import GameDefinition, GAME_REGISTRY
from src.config.settings import get_settings


class TestFrequencyAnalyzer:
    """Tests for frequency analysis."""

    def test_analyze_returns_global_counts(self, sample_draws, loto_game):
        from src.analytics.frequency import FrequencyAnalyzer
        analyzer = FrequencyAnalyzer()
        result = analyzer.analyze(sample_draws, loto_game)
        assert hasattr(result, "global_counts")
        assert len(result.global_counts) > 0
        # Counts should be non-negative
        assert all(v >= 0 for v in result.global_counts.values())

    def test_global_pct_values_in_range(self, sample_draws, loto_game):
        from src.analytics.frequency import FrequencyAnalyzer
        analyzer = FrequencyAnalyzer()
        result = analyzer.analyze(sample_draws, loto_game)
        # Each draw has 6 numbers out of 38, so percentages don't sum to 1
        # But they should all be between 0 and 1
        assert all(0 <= v <= 1 for v in result.global_pct.values())


class TestRecencyAnalyzer:
    """Tests for recency analysis."""

    def test_analyze_returns_per_number(self, sample_draws, loto_game):
        from src.analytics.recency import RecencyAnalyzer
        analyzer = RecencyAnalyzer()
        result = analyzer.analyze(sample_draws, loto_game)
        assert hasattr(result, "per_number")
        assert len(result.per_number) > 0

    def test_gaps_are_non_negative(self, sample_draws, loto_game):
        from src.analytics.recency import RecencyAnalyzer
        analyzer = RecencyAnalyzer()
        result = analyzer.analyze(sample_draws, loto_game)
        for nr in result.per_number.values():
            assert nr.gap >= 0


class TestHotColdAnalyzer:
    """Tests for hot/cold classification."""

    def test_classifications_are_valid(self, sample_draws, loto_game):
        from src.analytics.hot_cold import HotColdAnalyzer
        analyzer = HotColdAnalyzer()
        result = analyzer.analyze(sample_draws, loto_game)
        valid_classes = {"very_hot", "hot", "neutral", "cold", "very_cold"}
        for data in result.per_number.values():
            assert data["classification"] in valid_classes


class TestPairAnalyzer:
    """Tests for pair co-occurrence."""

    def test_pairs_have_positive_counts(self, sample_draws, loto_game):
        from src.analytics.pairs import PairAnalyzer
        analyzer = PairAnalyzer()
        result = analyzer.analyze(sample_draws, loto_game)
        assert len(result.pairs) > 0
        for data in result.pairs.values():
            assert data["count"] > 0
            assert data["lift"] > 0


class TestBalanceAnalyzer:
    """Tests for balance analysis."""

    def test_odd_even_histogram(self, sample_draws, loto_game):
        from src.analytics.balance import BalanceAnalyzer
        analyzer = BalanceAnalyzer()
        result = analyzer.analyze(sample_draws, loto_game)
        assert len(result.odd_even_histogram) > 0

    def test_score_odd_even(self, sample_combination):
        from src.analytics.balance import BalanceAnalyzer
        score = BalanceAnalyzer.score_odd_even(sample_combination)
        assert 0 <= score <= 1


class TestDistributionAnalyzer:
    """Tests for distribution analysis."""

    def test_sum_stats(self, sample_draws, loto_game):
        from src.analytics.distribution import DistributionAnalyzer
        analyzer = DistributionAnalyzer()
        result = analyzer.analyze(sample_draws, loto_game)
        assert result.sum_mean > 0
        assert result.sum_std > 0
        assert result.spread_mean > 0


class TestEntropyAnalyzer:
    """Tests for entropy analysis."""

    def test_normalized_entropy_in_range(self, sample_draws, loto_game):
        from src.analytics.entropy import EntropyAnalyzer
        analyzer = EntropyAnalyzer()
        result = analyzer.analyze(sample_draws, loto_game)
        assert 0 <= result.normalized_entropy <= 1


class TestAnalyticsEngine:
    """Tests for the full analytics engine."""

    def test_full_analysis(self, sample_draws, loto_game):
        from src.analytics.engine import AnalyticsEngine
        settings = get_settings()
        engine = AnalyticsEngine(loto_game, settings)
        result = engine.run_full_analysis(sample_draws)
        assert result.draw_count == len(sample_draws)
        assert result.frequency is not None
        assert result.recency is not None
        assert result.hot_cold is not None
        assert result.pairs is not None

    def test_build_per_number_scores(self, sample_draws, loto_game):
        from src.analytics.engine import AnalyticsEngine
        settings = get_settings()
        engine = AnalyticsEngine(loto_game, settings)
        result = engine.run_full_analysis(sample_draws)
        scores = engine.build_per_number_scores(result)
        assert "frequency_score" in scores
        assert "recency_score" in scores
        # Scores should be for numbers 1-38
        assert all(len(v) > 0 for v in scores.values())
