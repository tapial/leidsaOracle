"""
Default ensemble scoring weights and validation utilities.

Each weight controls how much influence a particular statistical feature
has on the final ensemble score used to rank generated combinations.
All weights must sum to 1.0.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

# ── Weight names (canonical order) ───────────────────────────────────────

WEIGHT_NAMES: tuple[str, ...] = (
    "frequency_score",
    "recency_score",
    "hot_cold_score",
    "pair_score",
    "triplet_score",
    "odd_even_score",
    "low_high_score",
    "sum_score",
    "spread_score",
    "entropy_score",
)

# ── Default weight profile ───────────────────────────────────────────────

DEFAULT_WEIGHTS: dict[str, float] = {
    "frequency_score": 0.15,
    "recency_score": 0.15,
    "hot_cold_score": 0.10,
    "pair_score": 0.15,
    "triplet_score": 0.05,
    "odd_even_score": 0.10,
    "low_high_score": 0.10,
    "sum_score": 0.10,
    "spread_score": 0.05,
    "entropy_score": 0.05,
}

# Tolerance for floating-point comparison when checking sum == 1.0
_SUM_TOLERANCE: float = 1e-9


# ── Validation ───────────────────────────────────────────────────────────


def validate_weights(weights: dict[str, float]) -> dict[str, float]:
    """Validate a weight dictionary and return a normalised copy.

    Checks performed:
    1. All required weight keys are present (no extras, no missing).
    2. Every value is a finite, non-negative float.
    3. The values sum to 1.0 (within floating-point tolerance).

    Args:
        weights: Mapping of feature name to its weight value.

    Returns:
        A new dict with the validated weights (same values, guaranteed order).

    Raises:
        ValueError: If any check fails.
    """
    # --- Key completeness ---
    expected = set(WEIGHT_NAMES)
    provided = set(weights)

    missing = expected - provided
    if missing:
        raise ValueError(f"Missing weight keys: {sorted(missing)}")

    extra = provided - expected
    if extra:
        raise ValueError(f"Unexpected weight keys: {sorted(extra)}")

    # --- Value validity ---
    for key in WEIGHT_NAMES:
        value = weights[key]
        if not isinstance(value, (int, float)):
            raise ValueError(f"Weight '{key}' must be numeric, got {type(value).__name__}")
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"Weight '{key}' must be finite, got {value}")
        if value < 0.0:
            raise ValueError(f"Weight '{key}' must be non-negative, got {value}")

    # --- Sum check ---
    total = sum(weights[k] for k in WEIGHT_NAMES)
    if abs(total - 1.0) > _SUM_TOLERANCE:
        raise ValueError(
            f"Weights must sum to 1.0, got {total:.10f} "
            f"(difference: {abs(total - 1.0):.2e})"
        )

    # Return a canonical-order copy
    return {k: float(weights[k]) for k in WEIGHT_NAMES}


def merge_weights(overrides: dict[str, float] | None = None) -> dict[str, float]:
    """Merge user overrides into the default weights and validate.

    Args:
        overrides: Partial or full dict of weight overrides.  ``None`` or
            an empty dict returns the defaults unchanged.

    Returns:
        A validated weight dictionary.

    Raises:
        ValueError: If the merged result fails validation.
    """
    merged = dict(DEFAULT_WEIGHTS)
    if overrides:
        merged.update(overrides)
    return validate_weights(merged)
