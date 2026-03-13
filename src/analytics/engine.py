"""
Orchestrating analytics engine that runs every analyser and assembles a
unified :class:`AnalysisResult`.

The engine is the single entry-point the rest of the application uses to
obtain all statistical insights.  It also provides a convenience method
to extract per-number score dictionaries suitable for the
:mod:`src.generator.pool_builder`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from src.config.constants import GameDefinition
from src.config.settings import Settings

from src.analytics.balance import BalanceAnalyzer, BalanceResult
from src.analytics.distribution import DistributionAnalyzer, DistributionResult
from src.analytics.entropy import EntropyAnalyzer, EntropyResult
from src.analytics.frequency import FrequencyAnalyzer, FrequencyResult
from src.analytics.hot_cold import HotColdAnalyzer, HotColdResult
from src.analytics.monte_carlo import MonteCarloResult, MonteCarloSimulator
from src.analytics.pairs import PairAnalyzer, PairResult
from src.analytics.recency import RecencyAnalyzer, RecencyResult
from src.analytics.triplets import TripletAnalyzer, TripletResult

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────


@dataclass
class AnalysisResult:
    """Aggregated output from every analyser.

    Attributes:
        frequency: Global and rolling frequency statistics.
        recency: Per-number gap and overdue information.
        hot_cold: Temperature classification over a trailing window.
        pairs: Top co-occurring number pairs with lift.
        triplets: Top co-occurring number triplets with lift.
        balance: Odd/even and low/high histograms.
        distribution: Sum and spread statistics.
        entropy: Shannon entropy of the frequency distribution.
        monte_carlo: Monte Carlo baseline (``None`` when skipped).
        computed_at: UTC timestamp of when the analysis was performed.
        draw_count: Number of draws fed into the analysis.
    """

    frequency: FrequencyResult
    recency: RecencyResult
    hot_cold: HotColdResult
    pairs: PairResult
    triplets: TripletResult
    balance: BalanceResult
    distribution: DistributionResult
    entropy: EntropyResult
    monte_carlo: MonteCarloResult | None
    computed_at: datetime
    draw_count: int


# ── Engine ────────────────────────────────────────────────────────────────


class AnalyticsEngine:
    """Run the full analytics pipeline and assemble results.

    Parameters
    ----------
    game_def:
        Game specification.
    settings:
        Application settings (used for rolling-window sizes, iteration
        counts, top-N limits, etc.).
    """

    def __init__(self, game_def: GameDefinition, settings: Settings) -> None:
        self.game_def = game_def
        self.settings = settings

        # Instantiate individual analysers.
        self._frequency = FrequencyAnalyzer(
            significance=settings.analytics.chi_square_significance,
        )
        self._recency = RecencyAnalyzer()
        self._hot_cold = HotColdAnalyzer()
        self._pairs = PairAnalyzer()
        self._triplets = TripletAnalyzer()
        self._balance = BalanceAnalyzer()
        self._distribution = DistributionAnalyzer()
        self._entropy = EntropyAnalyzer()
        self._monte_carlo = MonteCarloSimulator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_full_analysis(self, draws: np.ndarray) -> AnalysisResult:
        """Execute every analyser on *draws* and return the aggregated result.

        Parameters
        ----------
        draws:
            ``(N, number_count)`` array, oldest draw first.

        Returns
        -------
        AnalysisResult
        """
        n_draws = draws.shape[0]
        analytics_cfg = self.settings.analytics
        logger.info(
            "Starting full analysis for game '%s' on %d draws",
            self.game_def.code,
            n_draws,
        )

        # ── Individual analyses ──────────────────────────────────────
        frequency = self._frequency.analyze(
            draws,
            self.game_def,
            windows=analytics_cfg.rolling_windows,
        )

        recency = self._recency.analyze(draws, self.game_def)

        hot_cold = self._hot_cold.analyze(draws, self.game_def)

        pairs = self._pairs.analyze(
            draws,
            self.game_def,
            top_n=analytics_cfg.top_pairs,
        )

        triplets = self._triplets.analyze(
            draws,
            self.game_def,
            top_n=analytics_cfg.top_triplets,
        )

        balance = self._balance.analyze(draws, self.game_def)

        distribution = self._distribution.analyze(draws, self.game_def)

        entropy = self._entropy.analyze(draws, self.game_def)

        # ── Monte Carlo (optional, can be expensive) ─────────────────
        monte_carlo: MonteCarloResult | None = None
        if analytics_cfg.monte_carlo_iterations > 0:
            # Build per-number desirability from frequency percentiles.
            number_scores = self._build_mc_number_scores(frequency, recency, hot_cold)
            monte_carlo = self._monte_carlo.simulate(
                game_def=self.game_def,
                number_scores=number_scores,
                iterations=analytics_cfg.monte_carlo_iterations,
            )

        logger.info("Full analysis complete for game '%s'", self.game_def.code)

        return AnalysisResult(
            frequency=frequency,
            recency=recency,
            hot_cold=hot_cold,
            pairs=pairs,
            triplets=triplets,
            balance=balance,
            distribution=distribution,
            entropy=entropy,
            monte_carlo=monte_carlo,
            computed_at=datetime.now(timezone.utc),
            draw_count=n_draws,
        )

    def build_per_number_scores(
        self,
        analysis: AnalysisResult,
    ) -> dict[str, dict[int, float]]:
        """Extract per-number score dictionaries for the pool builder.

        Returns a mapping ``{feature_name: {number: score}}`` where each
        score is normalised to ``[0, 1]``.  These are the raw building
        blocks that :class:`~src.generator.pool_builder.PoolBuilder` uses
        to rank numbers into tiers.

        Parameters
        ----------
        analysis:
            A previously computed :class:`AnalysisResult`.

        Returns
        -------
        dict[str, dict[int, float]]
        """
        all_numbers = list(range(self.game_def.pool_min, self.game_def.pool_max + 1))

        scores: dict[str, dict[int, float]] = {}

        # ── frequency_score: percentile rank of global count ─────────
        freq_counts = analysis.frequency.global_counts
        max_count = max(freq_counts.values()) if freq_counts else 1
        scores["frequency_score"] = {
            num: freq_counts.get(num, 0) / max(max_count, 1)
            for num in all_numbers
        }

        # ── recency_score: overdue_ratio capped and normalised ───────
        scores["recency_score"] = {}
        for num in all_numbers:
            nr = analysis.recency.per_number.get(num)
            ratio = nr.overdue_ratio if nr else 0.0
            # Cap at 2.0 -> map to [0, 1].
            scores["recency_score"][num] = min(ratio / 2.0, 1.0)

        # ── hot_cold_score: z-score mapped to [0, 1] ────────────────
        scores["hot_cold_score"] = {}
        for num in all_numbers:
            info = analysis.hot_cold.per_number.get(num, {})
            z = info.get("z_score", 0.0) if isinstance(info, dict) else 0.0
            scores["hot_cold_score"][num] = max(0.0, min(1.0, (z + 3.0) / 6.0))

        # ── pair_partner_score: mean lift across top pairs ───────────
        pair_partner_totals: dict[int, list[float]] = {n: [] for n in all_numbers}
        for key, data in analysis.pairs.pairs.items():
            parts = key.split(",")
            if len(parts) == 2:
                a, b = int(parts[0]), int(parts[1])
                lift = data.get("lift", 1.0)
                if a in pair_partner_totals:
                    pair_partner_totals[a].append(lift)
                if b in pair_partner_totals:
                    pair_partner_totals[b].append(lift)
        scores["pair_partner_score"] = {}
        for num in all_numbers:
            lifts = pair_partner_totals[num]
            mean_lift = sum(lifts) / len(lifts) if lifts else 1.0
            # Normalise: lift=1 is neutral (0.5), lift=2 -> 1.0.
            scores["pair_partner_score"][num] = max(0.0, min(1.0, mean_lift / 2.0))

        # ── entropy_score: per-number frequency normalised ───────────
        scores["entropy_score"] = {}
        max_freq = max(analysis.entropy.per_number_frequencies.values()) if analysis.entropy.per_number_frequencies else 1.0
        for num in all_numbers:
            freq = analysis.entropy.per_number_frequencies.get(num, 0.0)
            scores["entropy_score"][num] = freq / max_freq if max_freq > 0 else 0.0

        return scores

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_mc_number_scores(
        self,
        frequency: FrequencyResult,
        recency: RecencyResult,
        hot_cold: HotColdResult,
    ) -> dict[int, float]:
        """Build a simple composite desirability for Monte Carlo sampling.

        Combines frequency percentile, recency, and hot/cold z-score
        into a single 0-1 score per number.
        """
        all_numbers = list(range(self.game_def.pool_min, self.game_def.pool_max + 1))

        max_count = max(frequency.global_counts.values()) if frequency.global_counts else 1
        scores: dict[int, float] = {}

        for num in all_numbers:
            # Frequency component: normalised count.
            freq_score = frequency.global_counts.get(num, 0) / max(max_count, 1)

            # Recency component: overdue ratio capped at 2.
            nr = recency.per_number.get(num)
            recency_score = min((nr.overdue_ratio if nr else 0.0) / 2.0, 1.0)

            # Hot/cold component: z -> [0, 1].
            hc_info = hot_cold.per_number.get(num, {})
            z = hc_info.get("z_score", 0.0) if isinstance(hc_info, dict) else 0.0
            hc_score = max(0.0, min(1.0, (z + 3.0) / 6.0))

            # Equal-weight composite.
            scores[num] = (freq_score + recency_score + hc_score) / 3.0

        return scores
