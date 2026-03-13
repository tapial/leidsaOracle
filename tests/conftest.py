"""Shared test fixtures for LeidsaOracle."""

from __future__ import annotations

import numpy as np
import pytest

from src.config.constants import GameDefinition, GAME_REGISTRY


@pytest.fixture
def loto_game() -> GameDefinition:
    """Standard Loto 6/38 game definition."""
    return GAME_REGISTRY["loto"]


@pytest.fixture
def loto_pool_game() -> GameDefinition:
    """Loto Pool 5/31 game definition."""
    return GAME_REGISTRY["loto_pool"]


@pytest.fixture
def sample_draws() -> np.ndarray:
    """50-draw sample dataset for 6/38 Loto (oldest-first)."""
    rng = np.random.default_rng(42)
    draws = []
    for _ in range(50):
        draw = sorted(rng.choice(range(1, 39), size=6, replace=False).tolist())
        draws.append(draw)
    return np.array(draws, dtype=np.int32)


@pytest.fixture
def large_draws() -> np.ndarray:
    """300-draw sample dataset for 6/38 Loto (enough for backtesting)."""
    rng = np.random.default_rng(123)
    draws = []
    for _ in range(300):
        draw = sorted(rng.choice(range(1, 39), size=6, replace=False).tolist())
        draws.append(draw)
    return np.array(draws, dtype=np.int32)


@pytest.fixture
def sample_combination() -> list[int]:
    """A single valid 6/38 combination."""
    return [3, 7, 15, 22, 28, 35]
