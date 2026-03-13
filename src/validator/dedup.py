"""
Deduplication logic for lottery draw imports.

Filters out draws that already exist in the database based on the
``(game_type, draw_date)`` unique constraint, preventing duplicate
insertion errors during bulk imports.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Draw
from src.validator.schemas import ValidatedDraw

logger = logging.getLogger(__name__)


class Deduplicator:
    """Filters validated draws against existing database records."""

    @staticmethod
    async def filter_new(
        session: AsyncSession,
        draws: list[ValidatedDraw],
        game_type: str,
    ) -> list[ValidatedDraw]:
        """Return only draws that do not already exist in the database.

        Performs a single batch query to check all ``(game_type, draw_date)``
        pairs, avoiding N+1 queries during bulk import.

        Args:
            session: Active async database session.
            draws: List of validated draws to check.
            game_type: Game identifier to scope the dedup query.

        Returns:
            A filtered list containing only draws whose ``draw_date``
            does not yet exist in the ``draws`` table for the given
            ``game_type``.  Ordering is preserved.
        """
        if not draws:
            return []

        # Collect all candidate dates from the input.
        candidate_dates = [d.draw_date for d in draws]

        # Query existing (game_type, draw_date) pairs in a single round-trip.
        stmt = (
            select(Draw.draw_date)
            .where(
                Draw.game_type == game_type,
                Draw.draw_date.in_(candidate_dates),
            )
        )
        result = await session.execute(stmt)
        existing_dates: set = {row[0] for row in result.all()}

        # Partition into new vs. skipped.
        new_draws: list[ValidatedDraw] = []
        skipped_count = 0

        for draw in draws:
            if draw.draw_date in existing_dates:
                skipped_count += 1
            else:
                new_draws.append(draw)

        if skipped_count:
            logger.info(
                "Dedup: %d of %d draws already exist for game '%s' and were skipped.",
                skipped_count,
                len(draws),
                game_type,
            )
        else:
            logger.debug(
                "Dedup: all %d draws are new for game '%s'.",
                len(draws),
                game_type,
            )

        return new_draws
