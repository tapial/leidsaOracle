"""Tests for scoring modules."""

from __future__ import annotations

import pytest

from src.config.constants import GAME_REGISTRY
from src.config.weights import DEFAULT_WEIGHTS, WEIGHT_NAMES


class TestEnsembleScorer:
    """Tests for ensemble scoring."""

    def test_score_with_default_weights(self):
        from src.scoring.ensemble import EnsembleScorer

        scorer = EnsembleScorer(DEFAULT_WEIGHTS)
        feature_scores = {name: 0.5 for name in WEIGHT_NAMES}
        result = scorer.score(feature_scores)
        assert abs(result - 0.5) < 1e-6  # All 0.5 with weights summing to 1.0

    def test_score_with_zeros(self):
        from src.scoring.ensemble import EnsembleScorer

        scorer = EnsembleScorer(DEFAULT_WEIGHTS)
        feature_scores = {name: 0.0 for name in WEIGHT_NAMES}
        result = scorer.score(feature_scores)
        assert result == 0.0

    def test_score_with_ones(self):
        from src.scoring.ensemble import EnsembleScorer

        scorer = EnsembleScorer(DEFAULT_WEIGHTS)
        feature_scores = {name: 1.0 for name in WEIGHT_NAMES}
        result = scorer.score(feature_scores)
        assert abs(result - 1.0) < 1e-6

    def test_invalid_weights_rejected(self):
        from src.scoring.ensemble import EnsembleScorer

        with pytest.raises(ValueError):
            EnsembleScorer({"frequency_score": 2.0})  # Doesn't sum to 1.0


class TestFeatureScorer:
    """Tests for feature scoring."""

    def test_all_features_present(self, loto_game):
        from src.scoring.feature_scores import AnalysisData, FeatureScorer

        analysis_data = AnalysisData(
            frequency_percentiles={i: 0.5 for i in range(1, 39)},
            overdue_ratios={i: 1.0 for i in range(1, 39)},
            hot_cold_z_scores={i: 0.0 for i in range(1, 39)},
            pair_lifts={},
            triplet_lifts={},
            sum_mean=120.0,
            sum_std=20.0,
            number_frequencies={i: 1 / 38 for i in range(1, 39)},
        )

        scorer = FeatureScorer(loto_game, analysis_data)
        result = scorer.score([3, 7, 15, 22, 28, 35])

        assert len(result) == len(WEIGHT_NAMES)
        for name in WEIGHT_NAMES:
            assert name in result
            assert 0.0 <= result[name] <= 1.0


class TestWeights:
    """Tests for weight validation."""

    def test_default_weights_valid(self):
        from src.config.weights import validate_weights
        validated = validate_weights(DEFAULT_WEIGHTS)
        assert sum(validated.values()) == pytest.approx(1.0, abs=1e-9)

    def test_missing_key_raises(self):
        from src.config.weights import validate_weights
        partial = {k: v for k, v in DEFAULT_WEIGHTS.items() if k != "frequency_score"}
        with pytest.raises(ValueError, match="Missing"):
            validate_weights(partial)

    def test_negative_weight_raises(self):
        from src.config.weights import validate_weights
        bad = dict(DEFAULT_WEIGHTS)
        bad["frequency_score"] = -0.1
        with pytest.raises(ValueError, match="non-negative"):
            validate_weights(bad)
