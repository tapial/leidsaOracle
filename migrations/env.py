"""
Alembic migration environment for LeidsaOracle.

Supports both online (async) and offline (SQL generation) modes.
Reads the database URL from the ``DATABASE_URL`` environment variable,
falling back to the value in ``alembic.ini``.

All ORM models are imported via ``src.database.models.Base`` so that
Alembic's autogenerate can detect schema changes.
"""

from __future__ import annotations

import asyncio
import logging
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import the declarative Base so that all model metadata is available
# for autogenerate.  The models module registers every table when imported.
from src.database.models import Base

logger = logging.getLogger("alembic.env")

# ── Alembic Config object ────────────────────────────────────────────────

config = context.config

# Interpret the config file for Python logging if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support.
target_metadata = Base.metadata

# ── Database URL resolution ──────────────────────────────────────────────


def _get_database_url() -> str:
    """Resolve the database URL from the environment or alembic.ini.

    Priority:
    1. ``DATABASE_URL`` environment variable.
    2. ``sqlalchemy.url`` from ``alembic.ini``.

    Returns:
        The resolved database URL string.

    Raises:
        RuntimeError: If no URL could be determined.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        # Support standard postgres:// URLs by converting to asyncpg driver.
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        logger.info("Using DATABASE_URL from environment.")
        return url

    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url:
        logger.info("Using sqlalchemy.url from alembic.ini.")
        return ini_url

    raise RuntimeError(
        "No database URL configured. Set the DATABASE_URL environment variable "
        "or sqlalchemy.url in alembic.ini."
    )


# ── Offline migrations (SQL script generation) ──────────────────────────


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL statements to stdout without connecting to a live
    database.  Useful for generating migration scripts for review.
    """
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations (async connection) ─────────────────────────────────


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations within an active database connection.

    Args:
        connection: A synchronous SQLAlchemy connection (provided by
            the async engine's ``run_sync`` method).
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations within its connection.

    The engine is created from the alembic config section, with the
    ``sqlalchemy.url`` overridden by the resolved database URL.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine.

    Creates an asyncio event loop and delegates to
    ``run_async_migrations()``.
    """
    asyncio.run(run_async_migrations())


# ── Entrypoint ───────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
