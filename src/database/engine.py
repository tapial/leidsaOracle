"""
Async SQLAlchemy engine, session factory, and database lifecycle helpers.

Provides a single ``get_session()`` async generator suitable for FastAPI
dependency injection, plus ``init_db()`` and ``wait_for_db()`` for startup.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

# ── Module-level singletons (initialised lazily) ────────────────────────

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    """Return the global async engine, creating it on first call."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow,
            echo=settings.database.echo,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        logger.info("Async engine created for %s", settings.database_url.split("@")[-1])
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the global session factory, creating it on first call."""
    global _session_factory  # noqa: PLW0603
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


# ── Public API ───────────────────────────────────────────────────────────


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an ``AsyncSession`` and ensure it is closed afterwards.

    Designed for use as a FastAPI dependency::

        @router.get("/draws")
        async def list_draws(session: AsyncSession = Depends(get_session)):
            ...
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


async def init_db() -> None:
    """Create all tables defined by the ORM metadata.

    This imports :mod:`src.database.models` to ensure every model is
    registered with ``Base.metadata`` before calling ``create_all``.
    """
    from src.database.models import Base  # noqa: F811 — local import intentional

    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created (if not existing).")


async def wait_for_db(
    max_retries: int = 30,
    retry_delay: float = 2.0,
) -> None:
    """Block until the database is reachable, retrying on failure.

    Args:
        max_retries: Maximum number of connection attempts.
        retry_delay: Seconds to wait between retries.

    Raises:
        ConnectionError: If the database is still unreachable after all retries.
    """
    engine = _get_engine()

    for attempt in range(1, max_retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(
                    # lightweight connectivity check
                    __import__("sqlalchemy").text("SELECT 1")
                )
            logger.info("Database connection established (attempt %d/%d).", attempt, max_retries)
            return
        except Exception as exc:
            logger.warning(
                "Database connection attempt %d/%d failed: %s",
                attempt,
                max_retries,
                exc,
            )
            if attempt < max_retries:
                await asyncio.sleep(retry_delay)

    raise ConnectionError(
        f"Could not connect to the database after {max_retries} attempts."
    )


async def dispose_engine() -> None:
    """Dispose the global engine (e.g. during graceful shutdown)."""
    global _engine, _session_factory  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        logger.info("Database engine disposed.")
        _engine = None
        _session_factory = None
