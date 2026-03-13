"""Explanation templates for combination scoring features and legal disclaimer."""

from __future__ import annotations

DISCLAIMER = (
    "DISCLAIMER: Lottery draws are independent random events. "
    "Past frequency patterns do NOT predict future outcomes. "
    "This tool uses statistical analysis for research and entertainment purposes only. "
    "No combination is more or less likely to win than any other. "
    "Please play responsibly."
)

SHORT_DISCLAIMER = (
    "Note: This is a probabilistic research tool, not a predictor. "
    "Lottery draws are random."
)

# ── Per-feature templates ─────────────────────────────────────────────────

FREQUENCY_HIGH = (
    "Number {n} has appeared {count} times ({pct:.1%}), "
    "which is {dev:+.1%} relative to the expected {expected:.1%}."
)

FREQUENCY_NORMAL = (
    "Number {n} appears near the expected frequency ({pct:.1%})."
)

RECENCY_OVERDUE = (
    "Number {n} has not appeared in {gap} draws — "
    "{ratio:.1f}× its average gap of {avg_gap:.0f} draws."
)

RECENCY_RECENT = (
    "Number {n} appeared recently ({gap} draws ago)."
)

HOT_COLD_VERY_HOT = "Number {n} is very hot (z={z:.2f}), appearing well above expected in recent draws."
HOT_COLD_HOT = "Number {n} is hot (z={z:.2f}), trending above average recently."
HOT_COLD_NEUTRAL = "Number {n} is neutral (z={z:.2f}), appearing near expected frequency."
HOT_COLD_COLD = "Number {n} is cold (z={z:.2f}), appearing below average recently."
HOT_COLD_VERY_COLD = "Number {n} is very cold (z={z:.2f}), well below expected frequency."

PAIR_STRONG = (
    "Pair ({a}, {b}) has co-occurred {count} times (lift={lift:.2f}×), "
    "appearing together more often than random chance."
)

BALANCE_IDEAL = "This combination has an ideal {odd}/{even} odd/even split."
BALANCE_ACCEPTABLE = "This combination has a {odd}/{even} odd/even split (acceptable)."

LOW_HIGH_IDEAL = "Low/high balance: {low}/{high} — well distributed across the number range."

SUM_OPTIMAL = (
    "Sum of {total} is within {z:.1f} standard deviations of the historical mean ({mean:.0f}), "
    "well within the typical range."
)

SUM_EDGE = (
    "Sum of {total} is {z:.1f} standard deviations from the mean ({mean:.0f}), "
    "at the edge of the typical range."
)

SPREAD_GOOD = (
    "Spread of {spread} (from {low} to {high}) covers {pct:.0%} of the number range."
)

ENTROPY_DIVERSE = (
    "This combination selects numbers across the frequency spectrum, "
    "not clustered among only hot or only cold numbers."
)

PERCENTILE_TEMPLATE = (
    "This combination scores in the {pct:.0f}th percentile compared to "
    "{iterations:,} random combinations."
)

RANK_TEMPLATE = (
    "Combination {numbers} ranks #{rank} with an ensemble score of {score:.3f}."
)

# ── Classification helpers ────────────────────────────────────────────────

HOT_COLD_TEMPLATES = {
    "very_hot": HOT_COLD_VERY_HOT,
    "hot": HOT_COLD_HOT,
    "neutral": HOT_COLD_NEUTRAL,
    "cold": HOT_COLD_COLD,
    "very_cold": HOT_COLD_VERY_COLD,
}
