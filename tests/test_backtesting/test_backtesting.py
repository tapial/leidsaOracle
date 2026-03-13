"""Tests for backtesting modules."""

from __future__ import annotations

import numpy as np
import pytest

from src.config.constants import GAME_REGISTRY
from src.config.settings import get_settings


class TestBacktestMetrics:
    """Tests for backtest metric computation."""

    def test_hypergeometric_baseline(self, loto_game):
        from src.backtesting.metrics import BacktestMetrics

        calculator = BacktestMetrics(loto_game)
        baseline = calculator._hypergeometric_baseline()

        # Probabilities should sum to 1.0
        total_prob = sum(baseline.probabilities.values())
        assert abs(total_prob - 1.0) < 1e-9

        # P(match=0) should be the largest
        assert baseline.probabilities[0] > baseline.probabilities[6]

    def test_empty_metrics(self, loto_game):
        from src.backtesting.metrics import BacktestMetrics

        calculator = BacktestMetrics(loto_game)
        empty = calculator._empty_metrics()
        assert empty.total_steps == 0
        assert empty.total_combos_evaluated == 0


class TestBacktestReporter:
    """Tests for backtest reporting."""

    def test_interpret_results(self, loto_game):
        from src.backtesting.metrics import BacktestMetrics
        from src.backtesting.reporter import BacktestReporter

        reporter = BacktestReporter(loto_game)
        empty = reporter.metrics_calculator._empty_metrics()
        interpretation = reporter._interpret_results(empty)
        # Should always mention disclaimer
        assert "random" in interpretation.lower() or "independent" in interpretation.lower()


class TestExplanationNarrator:
    """Tests for explanation generation."""

    def test_explain_generates_text(self, loto_game, sample_combination):
        from src.explainability.narrator import ExplanationNarrator

        narrator = ExplanationNarrator(loto_game)
        explanation = narrator.explain(
            numbers=sample_combination,
            rank=1,
            ensemble_score=0.75,
            feature_scores={"frequency_score": 0.8, "recency_score": 0.6},
            sum_mean=120.0,
            sum_std=20.0,
        )

        assert len(explanation) > 100
        assert "DISCLAIMER" in explanation
        assert "#1" in explanation or "ranks #1" in explanation
