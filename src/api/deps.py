"""FastAPI dependency injection providers."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.constants import GameDefinition, get_game
from src.config.settings import Settings, get_settings
from src.database.engine import get_session as _get_session
from src.validator.normalizer import Normalizer


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session for request-scoped use."""
    async for session in _get_session():
        yield session


def get_app_settings() -> Settings:
    """Return application settings singleton."""
    return get_settings()


def get_normalizer() -> Normalizer:
    """Return a Normalizer instance."""
    return Normalizer()


def get_game_def(game_type: str | None = None) -> GameDefinition:
    """Look up a GameDefinition by type, defaulting to settings."""
    game = game_type or get_settings().default_game_type
    return get_game(game)
