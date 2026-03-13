"""
Ensemble scorer that combines multiple feature scores into a single
weighted composite.

The ensemble score is the fundamental ranking metric: higher means a
combination is more statistically aligned with historical patterns across
all analysed dimensions (frequency, recency, balance, entropy, etc.).
"""

from __future__ import annotations

import math


class EnsembleScorer:
    """Compute a weighted sum of feature scores.

    Parameters
    ----------
    weights:
        Mapping ``{feature_name: weight}`` where the weights must sum
        to approximately 1.0 (tolerance: ``1e-6``).  All values must
        be finite and non-negative.

    Raises
    ------
    ValueError
        If any weight is negative, non-finite, or if the weights do not
        sum to ~1.0.
    """

    # Tolerance for the sum-to-one check.
    _SUM_TOLERANCE: float = 1e-6

    def __init__(self, weights: dict[str, float]) -> None:
        self._validate(weights)
        self.weights = dict(weights)  # defensive copy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, feature_scores: dict[str, float]) -> float:
        """Compute the weighted ensemble score.

        Features present in *weights* but absent from *feature_scores*
        are treated as 0.0 (pessimistic default).  Extra features in
        *feature_scores* that have no corresponding weight are silently
        ignored.

        Parameters
        ----------
        feature_scores:
            Mapping ``{feature_name: score}`` where each score is
            typically in ``[0, 1]``.

        Returns
        -------
        float
            The weighted sum, typically in ``[0, 1]`` when inputs
            are in ``[0, 1]`` and weights sum to 1.
        """
        total = 0.0
        for feature, weight in self.weights.items():
            total += weight * feature_scores.get(feature, 0.0)
        return total

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @classmethod
    def _validate(cls, weights: dict[str, float]) -> None:
        """Validate the weight dictionary.

        Raises
        ------
        ValueError
            On invalid weights.
        """
        if not weights:
            raise ValueError("Weights dictionary must not be empty.")

        for key, value in weights.items():
            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"Weight '{key}' must be numeric, got {type(value).__name__}."
                )
            if math.isnan(value) or math.isinf(value):
                raise ValueError(
                    f"Weight '{key}' must be finite, got {value}."
                )
            if value < 0.0:
                raise ValueError(
                    f"Weight '{key}' must be non-negative, got {value}."
                )

        total = sum(weights.values())
        if abs(total - 1.0) > cls._SUM_TOLERANCE:
            raise ValueError(
                f"Weights must sum to ~1.0, got {total:.10f} "
                f"(difference: {abs(total - 1.0):.2e})."
            )
