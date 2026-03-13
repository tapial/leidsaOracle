"""
Data access layer for the LEIDSA Oracle database.

Provides repository classes with static async methods for each aggregate root.
All methods take an ``AsyncSession`` as the first parameter and use
SQLAlchemy 2.0 ``select()`` style queries.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

import numpy as np
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    AnalysisSnapshot,
    BacktestResult,
    Draw,
    GeneratedCombination,
    ImportLog,
)

logger = logging.getLogger(__name__)


# ── Draw Repository ──────────────────────────────────────────────────────


class DrawRepository:
    """Data access methods for ``Draw`` records."""

    @staticmethod
    async def insert_draw(session: AsyncSession, draw: Draw) -> Draw:
        """Insert a single draw and return it with its generated id.

        Args:
            session: Active async database session.
            draw: A ``Draw`` instance to persist.

        Returns:
            The same ``Draw`` instance after flush (with ``id`` populated).
        """
        session.add(draw)
        await session.flush()
        logger.debug("Inserted draw id=%s game=%s date=%s", draw.id, draw.game_type, draw.draw_date)
        return draw

    @staticmethod
    async def bulk_insert_draws(session: AsyncSession, draws: list[Draw]) -> int:
        """Insert multiple draws in a single batch.

        Args:
            session: Active async database session.
            draws: List of ``Draw`` instances to persist.

        Returns:
            The number of draws successfully added to the session.
        """
        if not draws:
            return 0

        session.add_all(draws)
        await session.flush()
        count = len(draws)
        logger.info("Bulk-inserted %d draws.", count)
        return count

    @staticmethod
    async def get_draws(
        session: AsyncSession,
        game_type: str,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Draw]:
        """Retrieve draws for a game, optionally filtered by date range.

        Results are ordered by ``draw_date`` descending (most recent first).

        Args:
            session: Active async database session.
            game_type: Game identifier (e.g. ``"loto"``).
            date_from: Inclusive lower bound on ``draw_date``.
            date_to: Inclusive upper bound on ``draw_date``.
            limit: Maximum number of rows to return.
            offset: Number of rows to skip for pagination.

        Returns:
            List of ``Draw`` instances matching the criteria.
        """
        stmt = select(Draw).where(Draw.game_type == game_type)

        if date_from is not None:
            stmt = stmt.where(Draw.draw_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(Draw.draw_date <= date_to)

        stmt = stmt.order_by(Draw.draw_date.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_draw_count(session: AsyncSession, game_type: str) -> int:
        """Return the total number of draws stored for a game.

        Args:
            session: Active async database session.
            game_type: Game identifier.

        Returns:
            Integer count of draw records.
        """
        stmt = select(func.count(Draw.id)).where(Draw.game_type == game_type)
        result = await session.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def get_latest_draw(session: AsyncSession, game_type: str) -> Draw | None:
        """Return the most recent draw for a game, or ``None``.

        Args:
            session: Active async database session.
            game_type: Game identifier.

        Returns:
            The ``Draw`` with the latest ``draw_date``, or ``None`` if no draws exist.
        """
        stmt = (
            select(Draw)
            .where(Draw.game_type == game_type)
            .order_by(Draw.draw_date.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def draw_exists(
        session: AsyncSession,
        game_type: str,
        draw_date: datetime.date,
    ) -> bool:
        """Check whether a draw already exists for a given game and date.

        Args:
            session: Active async database session.
            game_type: Game identifier.
            draw_date: The calendar date to check.

        Returns:
            ``True`` if a matching draw exists, ``False`` otherwise.
        """
        stmt = select(func.count(Draw.id)).where(
            Draw.game_type == game_type,
            Draw.draw_date == draw_date,
        )
        result = await session.execute(stmt)
        return result.scalar_one() > 0

    @staticmethod
    async def get_all_numbers_as_matrix(
        session: AsyncSession,
        game_type: str,
        limit: int | None = None,
    ) -> np.ndarray:
        """Return all draw numbers as a NumPy matrix, oldest-first.

        Args:
            session: Active async database session.
            game_type: Game identifier.
            limit: If given, only return the most recent *limit* draws
                   (but still ordered oldest-first in the output).

        Returns:
            A ``(N, number_count)`` NumPy ``int32`` array where each row is
            one draw's sorted number list.  Returns an empty ``(0, 0)``
            array when no draws are found.
        """
        if limit is not None:
            # Select the most recent `limit` draws, fetching both numbers
            # and draw_date so we can reverse to oldest-first order.
            stmt = (
                select(Draw.numbers, Draw.draw_date)
                .where(Draw.game_type == game_type)
                .order_by(Draw.draw_date.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = list(reversed(result.all()))
            number_lists = [row[0] for row in rows]
        else:
            stmt = (
                select(Draw.numbers)
                .where(Draw.game_type == game_type)
                .order_by(Draw.draw_date.asc())
            )
            result = await session.execute(stmt)
            number_lists = list(result.scalars().all())

        if not number_lists:
            return np.empty((0, 0), dtype=np.int32)

        return np.array(number_lists, dtype=np.int32)


# ── Analysis Repository ──────────────────────────────────────────────────


class AnalysisRepository:
    """Data access methods for ``AnalysisSnapshot`` records."""

    @staticmethod
    async def save_snapshot(
        session: AsyncSession,
        snapshot: AnalysisSnapshot,
    ) -> AnalysisSnapshot:
        """Persist an analysis snapshot and return it with its id.

        Args:
            session: Active async database session.
            snapshot: An ``AnalysisSnapshot`` instance.

        Returns:
            The flushed ``AnalysisSnapshot`` with ``id`` populated.
        """
        session.add(snapshot)
        await session.flush()
        logger.info(
            "Saved analysis snapshot id=%s game=%s date=%s",
            snapshot.id,
            snapshot.game_type,
            snapshot.snapshot_date,
        )
        return snapshot

    @staticmethod
    async def get_latest_snapshot(
        session: AsyncSession,
        game_type: str,
    ) -> AnalysisSnapshot | None:
        """Return the most recent analysis snapshot for a game, or ``None``.

        Args:
            session: Active async database session.
            game_type: Game identifier.

        Returns:
            The ``AnalysisSnapshot`` with the latest ``snapshot_date``,
            or ``None`` if none exist.
        """
        stmt = (
            select(AnalysisSnapshot)
            .where(AnalysisSnapshot.game_type == game_type)
            .order_by(AnalysisSnapshot.snapshot_date.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


# ── Combination Repository ───────────────────────────────────────────────


class CombinationRepository:
    """Data access methods for ``GeneratedCombination`` records."""

    @staticmethod
    async def save_batch(
        session: AsyncSession,
        combos: list[GeneratedCombination],
    ) -> str:
        """Persist a batch of generated combinations under a shared batch_id.

        If any combo lacks a ``batch_id``, one is generated and assigned
        to all items in the list.

        Args:
            session: Active async database session.
            combos: List of ``GeneratedCombination`` instances.

        Returns:
            The ``batch_id`` (UUID string) that groups this batch.

        Raises:
            ValueError: If the combo list is empty.
        """
        if not combos:
            raise ValueError("Cannot save an empty combination batch.")

        batch_id = combos[0].batch_id or str(uuid.uuid4())
        for combo in combos:
            combo.batch_id = batch_id

        session.add_all(combos)
        await session.flush()
        logger.info("Saved combination batch %s with %d combos.", batch_id, len(combos))
        return batch_id

    @staticmethod
    async def get_batch(
        session: AsyncSession,
        batch_id: str,
    ) -> list[GeneratedCombination]:
        """Retrieve all combinations belonging to a specific batch.

        Args:
            session: Active async database session.
            batch_id: UUID string identifying the batch.

        Returns:
            List of ``GeneratedCombination`` ordered by rank ascending.
        """
        stmt = (
            select(GeneratedCombination)
            .where(GeneratedCombination.batch_id == batch_id)
            .order_by(GeneratedCombination.rank.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_latest_batch(
        session: AsyncSession,
        game_type: str,
    ) -> list[GeneratedCombination]:
        """Retrieve the most recently generated batch for a game.

        Args:
            session: Active async database session.
            game_type: Game identifier.

        Returns:
            List of ``GeneratedCombination`` from the latest batch,
            ordered by rank.  Empty list if no batches exist.
        """
        # Find the latest batch_id for this game
        latest_batch_stmt = (
            select(GeneratedCombination.batch_id)
            .where(GeneratedCombination.game_type == game_type)
            .order_by(GeneratedCombination.created_at.desc())
            .limit(1)
        )
        result = await session.execute(latest_batch_stmt)
        batch_id = result.scalar_one_or_none()

        if batch_id is None:
            return []

        return await CombinationRepository.get_batch(session, batch_id)


# ── Backtest Repository ──────────────────────────────────────────────────


class BacktestRepository:
    """Data access methods for ``BacktestResult`` records."""

    @staticmethod
    async def save_result(
        session: AsyncSession,
        result: BacktestResult,
    ) -> BacktestResult:
        """Persist a backtest result and return it with its id.

        Args:
            session: Active async database session.
            result: A ``BacktestResult`` instance.

        Returns:
            The flushed ``BacktestResult`` with ``id`` populated.
        """
        session.add(result)
        await session.flush()
        logger.info(
            "Saved backtest result id=%s game=%s run_id=%s",
            result.id,
            result.game_type,
            result.run_id,
        )
        return result

    @staticmethod
    async def get_results(
        session: AsyncSession,
        game_type: str,
        limit: int = 5,
    ) -> list[BacktestResult]:
        """Retrieve the most recent backtest results for a game.

        Args:
            session: Active async database session.
            game_type: Game identifier.
            limit: Maximum number of results to return.

        Returns:
            List of ``BacktestResult`` ordered by ``run_date`` descending.
        """
        stmt = (
            select(BacktestResult)
            .where(BacktestResult.game_type == game_type)
            .order_by(BacktestResult.run_date.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ── Import Log Repository ────────────────────────────────────────────────


class ImportLogRepository:
    """Data access methods for ``ImportLog`` records."""

    @staticmethod
    async def create_log(session: AsyncSession, **kwargs: Any) -> ImportLog:
        """Create and persist a new import log entry.

        Args:
            session: Active async database session.
            **kwargs: Column values passed directly to the ``ImportLog``
                      constructor (e.g. ``source_type``, ``status``).

        Returns:
            The flushed ``ImportLog`` with ``id`` populated.
        """
        log = ImportLog(**kwargs)
        session.add(log)
        await session.flush()
        logger.info("Created import log id=%s source=%s", log.id, log.source_type)
        return log

    @staticmethod
    async def update_log(
        session: AsyncSession,
        log_id: int,
        **kwargs: Any,
    ) -> ImportLog:
        """Update fields on an existing import log entry.

        Args:
            session: Active async database session.
            log_id: Primary key of the ``ImportLog`` to update.
            **kwargs: Column values to update.

        Returns:
            The refreshed ``ImportLog`` instance.

        Raises:
            ValueError: If no ``ImportLog`` with the given id exists.
        """
        stmt = update(ImportLog).where(ImportLog.id == log_id).values(**kwargs)
        await session.execute(stmt)
        await session.flush()

        # Reload the updated object
        refreshed = await session.get(ImportLog, log_id)
        if refreshed is None:
            raise ValueError(f"ImportLog with id={log_id} not found after update.")

        logger.debug("Updated import log id=%s fields=%s", log_id, list(kwargs.keys()))
        return refreshed

    @staticmethod
    async def find_by_hash(
        session: AsyncSession,
        file_hash: str,
    ) -> ImportLog | None:
        """Look up an import log by its file SHA-256 hash.

        Args:
            session: Active async database session.
            file_hash: The SHA-256 hex digest to search for.

        Returns:
            The matching ``ImportLog`` or ``None`` if not found.
        """
        stmt = select(ImportLog).where(ImportLog.file_hash == file_hash).limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
