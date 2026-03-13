"""Backtest report generation in JSON, Markdown, and DataFrame formats."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

import pandas as pd

from src.backtesting.metrics import BacktestMetrics, MetricsSummary
from src.backtesting.walk_forward import BacktestRunResult
from src.config.constants import GameDefinition
from src.explainability.templates import DISCLAIMER

logger = logging.getLogger(__name__)


class BacktestReporter:
    """Generate human-readable and machine-readable backtest reports."""

    def __init__(self, game_def: GameDefinition):
        self.game_def = game_def
        self.metrics_calculator = BacktestMetrics(game_def)

    def full_report(self, result: BacktestRunResult) -> dict[str, Any]:
        """Generate a comprehensive report dict."""
        metrics = self.metrics_calculator.compute(result)
        return {
            "summary": self.to_summary_dict(result, metrics),
            "metrics": self.to_metrics_dict(metrics),
            "config": self._config_dict(result),
            "disclaimer": DISCLAIMER,
        }

    def to_summary_dict(
        self, result: BacktestRunResult, metrics: MetricsSummary
    ) -> dict[str, Any]:
        """Summary statistics for API response."""
        return {
            "game_type": result.game_type,
            "total_steps": metrics.total_steps,
            "total_combinations_evaluated": metrics.total_combos_evaluated,
            "elapsed_seconds": round(result.elapsed_seconds, 2),
            "number_hit_rate": round(metrics.number_hit_rate, 4),
            "number_hit_baseline": round(metrics.number_hit_baseline, 4),
            "number_hit_improvement": round(
                metrics.number_hit_rate / max(metrics.number_hit_baseline, 1e-9), 2
            ),
            "score_match_correlation": round(metrics.score_match_correlation, 4),
            "score_match_p_value": round(metrics.score_match_p_value, 4),
            "interpretation": self._interpret_results(metrics),
        }

    def to_metrics_dict(self, metrics: MetricsSummary) -> dict[str, Any]:
        """Detailed metrics for API response."""
        return {
            "match_distribution": {
                str(k): {
                    "actual_rate": round(v, 6),
                    "random_baseline": round(
                        metrics.random_baseline.probabilities.get(k, 0), 6
                    ),
                    "improvement_factor": round(
                        metrics.improvement_factors.get(k, 0), 2
                    ),
                }
                for k, v in metrics.match_distribution.items()
            },
            "feature_stability": metrics.feature_stability,
        }

    def to_markdown(self, result: BacktestRunResult) -> str:
        """Generate a human-readable Markdown report."""
        metrics = self.metrics_calculator.compute(result)
        lines = [
            "# Backtest Report",
            "",
            f"**Game**: {self.game_def.display_name} ({self.game_def.code})",
            f"**Steps**: {metrics.total_steps}",
            f"**Combinations evaluated**: {metrics.total_combos_evaluated:,}",
            f"**Duration**: {result.elapsed_seconds:.1f}s",
            "",
            "## Number Hit Rate",
            f"- Actual: **{metrics.number_hit_rate:.2%}**",
            f"- Random baseline: {metrics.number_hit_baseline:.2%}",
            f"- Improvement: **{metrics.number_hit_rate / max(metrics.number_hit_baseline, 1e-9):.2f}×**",
            "",
            "## Match Distribution",
            "| Match | Actual | Random | Improvement |",
            "|-------|--------|--------|-------------|",
        ]

        for k in range(self.game_def.number_count + 1):
            actual = metrics.match_distribution.get(k, 0)
            baseline = metrics.random_baseline.probabilities.get(k, 0)
            imp = metrics.improvement_factors.get(k, 0)
            lines.append(f"| {k} | {actual:.4%} | {baseline:.4%} | {imp:.2f}× |")

        lines.extend([
            "",
            "## Score-Performance Correlation",
            f"- Spearman ρ = {metrics.score_match_correlation:.4f}",
            f"- p-value = {metrics.score_match_p_value:.4f}",
            "",
            "## Interpretation",
            self._interpret_results(metrics),
            "",
            f"---\n\n{DISCLAIMER}",
        ])

        return "\n".join(lines)

    def to_dataframe(self, result: BacktestRunResult) -> pd.DataFrame:
        """Generate step-by-step DataFrame for analysis."""
        rows = []
        for step in result.steps:
            for i, (combo, match, score) in enumerate(
                zip(step.generated_numbers, step.match_counts, step.ensemble_scores)
            ):
                rows.append({
                    "step_index": step.step_index,
                    "combo_rank": i + 1,
                    "numbers": combo,
                    "match_count": match,
                    "ensemble_score": score,
                    "test_draw": step.test_draw,
                })
        return pd.DataFrame(rows)

    def _config_dict(self, result: BacktestRunResult) -> dict[str, Any]:
        """Serialize config for reproducibility."""
        return {
            "train_window": result.config.train_window,
            "test_window": result.config.test_window,
            "step_size": result.config.step_size,
            "combinations_per_step": result.config.combinations_per_step,
            "max_steps": result.config.max_steps,
            "weights": result.config.weights,
            "seed": result.config.seed,
        }

    def _interpret_results(self, metrics: MetricsSummary) -> str:
        """Generate honest interpretation of backtest results."""
        parts = []

        # Number hit rate interpretation
        nhr = metrics.number_hit_rate
        baseline = metrics.number_hit_baseline
        if nhr > baseline * 1.1:
            parts.append(
                f"The system's number hit rate ({nhr:.2%}) is {nhr/baseline:.2f}× "
                f"the random baseline ({baseline:.2%}), suggesting the heuristics "
                f"provide a modest advantage in individual number selection."
            )
        elif nhr > baseline * 0.95:
            parts.append(
                f"The number hit rate ({nhr:.2%}) is very close to the random "
                f"baseline ({baseline:.2%}), indicating minimal advantage from "
                f"the heuristic selection."
            )
        else:
            parts.append(
                f"The number hit rate ({nhr:.2%}) is below the random baseline "
                f"({baseline:.2%}). The heuristics did not improve selection."
            )

        # Correlation interpretation
        corr = metrics.score_match_correlation
        p_val = metrics.score_match_p_value
        if p_val < 0.05 and corr > 0.05:
            parts.append(
                f"There is a statistically significant (p={p_val:.4f}) positive "
                f"correlation (ρ={corr:.4f}) between ensemble scores and match counts. "
                f"Higher-scored combinations tended to match slightly more numbers."
            )
        else:
            parts.append(
                f"No statistically significant correlation (ρ={corr:.4f}, p={p_val:.4f}) "
                f"was found between ensemble scores and actual match counts. "
                f"This is consistent with lottery draws being independent random events."
            )

        # Honest framing
        parts.append(
            "IMPORTANT: Even modest improvements over random baselines should be "
            "interpreted cautiously. Lottery draws are independent random events, "
            "and past patterns do not predict future outcomes. Any observed advantage "
            "may be due to statistical noise rather than genuine predictive power."
        )

        return " ".join(parts)
