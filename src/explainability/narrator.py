"""Natural language explanation generator for ranked lottery combinations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.config.constants import GameDefinition
from src.explainability.templates import (
    BALANCE_ACCEPTABLE,
    BALANCE_IDEAL,
    DISCLAIMER,
    ENTROPY_DIVERSE,
    FREQUENCY_HIGH,
    FREQUENCY_NORMAL,
    HOT_COLD_TEMPLATES,
    LOW_HIGH_IDEAL,
    PAIR_STRONG,
    PERCENTILE_TEMPLATE,
    RANK_TEMPLATE,
    RECENCY_OVERDUE,
    RECENCY_RECENT,
    SPREAD_GOOD,
    SUM_EDGE,
    SUM_OPTIMAL,
)

logger = logging.getLogger(__name__)


@dataclass
class NumberDetail:
    """Per-number analysis data for explanation generation."""

    number: int
    frequency_count: int = 0
    frequency_pct: float = 0.0
    expected_pct: float = 0.0
    gap: int = 0
    avg_gap: float = 0.0
    overdue_ratio: float = 1.0
    z_score: float = 0.0
    classification: str = "neutral"


class ExplanationNarrator:
    """Generate human-readable explanations for why each combination was selected."""

    def __init__(self, game_def: GameDefinition):
        self.game_def = game_def

    def explain(
        self,
        numbers: list[int],
        rank: int,
        ensemble_score: float,
        feature_scores: dict[str, float],
        number_details: dict[int, NumberDetail] | None = None,
        pair_data: dict[str, dict[str, Any]] | None = None,
        sum_mean: float = 0.0,
        sum_std: float = 1.0,
        mc_percentile: float | None = None,
        mc_iterations: int = 100_000,
    ) -> str:
        """
        Generate a multi-paragraph explanation for a combination.

        Args:
            numbers: The combination (sorted).
            rank: 1-based rank.
            ensemble_score: Weighted ensemble score.
            feature_scores: Individual feature scores {name: 0-1 value}.
            number_details: Per-number analysis data.
            pair_data: Pair co-occurrence data.
            sum_mean: Historical sum mean.
            sum_std: Historical sum std deviation.
            mc_percentile: Monte Carlo percentile (0-100).
            mc_iterations: Number of MC iterations used.

        Returns:
            Multi-paragraph explanation string.
        """
        sections: list[str] = []

        # Header
        numbers_str = ", ".join(str(n) for n in numbers)
        sections.append(
            RANK_TEMPLATE.format(
                numbers=f"[{numbers_str}]",
                rank=rank,
                score=ensemble_score,
            )
        )

        # Monte Carlo percentile
        if mc_percentile is not None:
            sections.append(
                PERCENTILE_TEMPLATE.format(pct=mc_percentile, iterations=mc_iterations)
            )

        # Frequency section
        if number_details:
            freq_lines = self._frequency_section(numbers, number_details)
            if freq_lines:
                sections.append("Frequency: " + " ".join(freq_lines))

        # Recency section
        if number_details:
            rec_lines = self._recency_section(numbers, number_details)
            if rec_lines:
                sections.append("Recency: " + " ".join(rec_lines))

        # Hot/cold section
        if number_details:
            hc_lines = self._hot_cold_section(numbers, number_details)
            if hc_lines:
                sections.append("Temperature: " + " ".join(hc_lines))

        # Pair section
        if pair_data:
            pair_lines = self._pair_section(numbers, pair_data)
            if pair_lines:
                sections.append("Co-occurrence: " + " ".join(pair_lines))

        # Balance section
        sections.append(self._balance_section(numbers))

        # Sum section
        total = sum(numbers)
        if sum_std > 0:
            z = abs(total - sum_mean) / sum_std
            if z <= 1.0:
                sections.append(
                    SUM_OPTIMAL.format(total=total, z=z, mean=sum_mean)
                )
            else:
                sections.append(
                    SUM_EDGE.format(total=total, z=z, mean=sum_mean)
                )

        # Spread section
        spread = max(numbers) - min(numbers)
        pool_range = self.game_def.pool_max - self.game_def.pool_min
        if pool_range > 0:
            sections.append(
                SPREAD_GOOD.format(
                    spread=spread,
                    low=min(numbers),
                    high=max(numbers),
                    pct=spread / pool_range,
                )
            )

        # Entropy note
        if feature_scores.get("entropy_score", 0) > 0.6:
            sections.append(ENTROPY_DIVERSE)

        # Top feature scores summary
        top_features = sorted(
            [(k, v) for k, v in feature_scores.items() if k != "rank"],
            key=lambda x: x[1],
            reverse=True,
        )[:3]
        if top_features:
            top_str = ", ".join(
                f"{k.replace('_score', '')} ({v:.2f})" for k, v in top_features
            )
            sections.append(f"Strongest signals: {top_str}.")

        # Disclaimer
        sections.append(DISCLAIMER)

        return "\n\n".join(sections)

    def _frequency_section(
        self,
        numbers: list[int],
        details: dict[int, NumberDetail],
    ) -> list[str]:
        lines = []
        for n in numbers:
            d = details.get(n)
            if not d:
                continue
            dev = d.frequency_pct - d.expected_pct
            if abs(dev) > 0.02:  # > 2% deviation
                lines.append(
                    FREQUENCY_HIGH.format(
                        n=n,
                        count=d.frequency_count,
                        pct=d.frequency_pct,
                        dev=dev,
                        expected=d.expected_pct,
                    )
                )
        # Only report up to 3 notable numbers
        return lines[:3]

    def _recency_section(
        self,
        numbers: list[int],
        details: dict[int, NumberDetail],
    ) -> list[str]:
        lines = []
        for n in numbers:
            d = details.get(n)
            if not d:
                continue
            if d.overdue_ratio > 1.5:
                lines.append(
                    RECENCY_OVERDUE.format(
                        n=n, gap=d.gap, ratio=d.overdue_ratio, avg_gap=d.avg_gap
                    )
                )
            elif d.gap <= 3:
                lines.append(RECENCY_RECENT.format(n=n, gap=d.gap))
        return lines[:3]

    def _hot_cold_section(
        self,
        numbers: list[int],
        details: dict[int, NumberDetail],
    ) -> list[str]:
        lines = []
        for n in numbers:
            d = details.get(n)
            if not d or d.classification == "neutral":
                continue
            template = HOT_COLD_TEMPLATES.get(d.classification, "")
            if template:
                lines.append(template.format(n=n, z=d.z_score))
        return lines[:3]

    def _pair_section(
        self,
        numbers: list[int],
        pair_data: dict[str, dict[str, Any]],
    ) -> list[str]:
        lines = []
        for i in range(len(numbers)):
            for j in range(i + 1, len(numbers)):
                key = f"{min(numbers[i], numbers[j])},{max(numbers[i], numbers[j])}"
                pdata = pair_data.get(key, {})
                lift = pdata.get("lift", 1.0)
                if lift > 1.5:
                    lines.append(
                        PAIR_STRONG.format(
                            a=min(numbers[i], numbers[j]),
                            b=max(numbers[i], numbers[j]),
                            count=pdata.get("count", 0),
                            lift=lift,
                        )
                    )
        return lines[:2]  # Top 2 strong pairs

    def _balance_section(self, numbers: list[int]) -> str:
        odd = sum(1 for n in numbers if n % 2 != 0)
        even = len(numbers) - odd
        midpoint = (self.game_def.pool_min + self.game_def.pool_max) / 2
        low = sum(1 for n in numbers if n <= midpoint)
        high = len(numbers) - low

        if abs(odd - even) <= 1:
            balance = BALANCE_IDEAL.format(odd=odd, even=even)
        else:
            balance = BALANCE_ACCEPTABLE.format(odd=odd, even=even)

        lh = LOW_HIGH_IDEAL.format(low=low, high=high)
        return f"{balance} {lh}"
