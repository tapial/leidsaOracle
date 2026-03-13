"""
Recency analysis for lottery draw numbers.

For every number in the pool, computes how many draws ago it last appeared,
its historical average gap, maximum gap, and an *overdue ratio* that flags
numbers that have been absent significantly longer than expected.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.config.constants import GameDefinition


# ── Result dataclasses ────────────────────────────────────────────────────


@dataclass
class NumberRecency:
    """Recency statistics for a single number."""

    number: int
    last_seen_idx: int        # 0 = appeared in the most recent draw
    gap: int                  # draws since last appearance (== last_seen_idx)
    avg_gap: float            # mean gap over the number's history
    max_gap: int              # longest historical gap
    overdue_ratio: float      # gap / avg_gap  (>1 means overdue)
    appearance_count: int     # total times drawn


@dataclass
class RecencyResult:
    """Complete output of :class:`RecencyAnalyzer`."""

    total_draws: int
    per_number: dict[int, NumberRecency]


# ── Analyzer ──────────────────────────────────────────────────────────────


class RecencyAnalyzer:
    """Compute recency and gap statistics for every number in the pool."""

    def analyze(
        self,
        draws: np.ndarray,
        game_def: GameDefinition,
    ) -> RecencyResult:
        """Run recency analysis.

        Parameters
        ----------
        draws:
            ``(N, number_count)`` array, oldest draw first.
        game_def:
            Game specification.

        Returns
        -------
        RecencyResult
        """
        n_draws = draws.shape[0]
        all_numbers = range(game_def.pool_min, game_def.pool_max + 1)

        # Build a set per draw for O(1) membership checks.
        draw_sets: list[set[int]] = [
            set(int(x) for x in draws[i]) for i in range(n_draws)
        ]

        per_number: dict[int, NumberRecency] = {}

        for num in all_numbers:
            # Indices (in chronological order) where *num* appeared.
            appearance_indices: list[int] = [
                i for i, s in enumerate(draw_sets) if num in s
            ]

            appearance_count = len(appearance_indices)

            if appearance_count == 0:
                # Number has never appeared in the dataset.
                per_number[num] = NumberRecency(
                    number=num,
                    last_seen_idx=n_draws,  # "infinitely" far back
                    gap=n_draws,
                    avg_gap=float(n_draws),
                    max_gap=n_draws,
                    overdue_ratio=1.0,
                    appearance_count=0,
                )
                continue

            # last_seen_idx: 0 means the most recent draw (index n_draws-1).
            last_chrono_idx = appearance_indices[-1]
            last_seen_idx = (n_draws - 1) - last_chrono_idx
            gap = last_seen_idx  # draws since last appearance

            # Compute gaps between consecutive appearances.
            # We also count the implicit "gap from draw 0" and "gap to now".
            gaps: list[int] = []

            # Gap before the first appearance (from the start of the dataset).
            gaps.append(appearance_indices[0])

            # Gaps between consecutive appearances.
            for k in range(1, appearance_count):
                gaps.append(appearance_indices[k] - appearance_indices[k - 1] - 1)

            # Gap after the last appearance (to the current draw).
            gaps.append((n_draws - 1) - last_chrono_idx)

            avg_gap = float(np.mean(gaps)) if gaps else 0.0
            max_gap = max(gaps) if gaps else 0

            overdue_ratio = gap / avg_gap if avg_gap > 0 else 0.0

            per_number[num] = NumberRecency(
                number=num,
                last_seen_idx=last_seen_idx,
                gap=gap,
                avg_gap=avg_gap,
                max_gap=max_gap,
                overdue_ratio=overdue_ratio,
                appearance_count=appearance_count,
            )

        return RecencyResult(total_draws=n_draws, per_number=per_number)
