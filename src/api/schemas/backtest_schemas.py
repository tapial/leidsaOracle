"""Pydantic schemas for backtesting endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.explainability.templates import DISCLAIMER


class BacktestRequest(BaseModel):
    """Request body for running a walk-forward backtest."""

    game_type: str = Field(description="Game identifier (e.g. 'loto').")
    train_window: int = Field(
        default=200,
        ge=50,
        description="Number of draws in each training window.",
    )
    step_size: int = Field(
        default=1,
        ge=1,
        description="Number of draws to advance between steps.",
    )
    combinations_per_step: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Combinations generated per test step.",
    )
    max_steps: int | None = Field(
        default=None,
        ge=1,
        description="Maximum number of walk-forward steps. None = all available.",
    )


class BacktestResponse(BaseModel):
    """Full response from a backtest run."""

    summary: dict[str, Any] = Field(
        description="High-level summary: hit rates, correlation, interpretation."
    )
    metrics: dict[str, Any] = Field(
        description="Detailed match distributions and feature stability."
    )
    config: dict[str, Any] = Field(
        description="Configuration used for reproducibility."
    )
    disclaimer: str = Field(default=DISCLAIMER)
