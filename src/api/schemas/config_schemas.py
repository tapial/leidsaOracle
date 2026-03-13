"""Pydantic schemas for configuration endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.config.weights import WEIGHT_NAMES


class WeightsResponse(BaseModel):
    """Current ensemble scoring weights."""

    weights: dict[str, float] = Field(
        description="Feature name -> weight (all values sum to 1.0)."
    )
    weight_names: list[str] = Field(
        default=list(WEIGHT_NAMES),
        description="Canonical list of valid weight keys.",
    )


class UpdateWeightsRequest(BaseModel):
    """Request body for updating ensemble weights."""

    weights: dict[str, float] = Field(
        description=(
            "Full or partial weight overrides. "
            "All values must be non-negative and the final set must sum to 1.0."
        ),
    )


class GameDefinitionResponse(BaseModel):
    """Public representation of a single game's rules."""

    code: str
    display_name: str
    number_count: int
    pool_min: int
    pool_max: int
    pool_size: int
    has_bonus: bool
    bonus_min: int | None = None
    bonus_max: int | None = None
    draw_days: list[str]
    draw_time: str


class GamesResponse(BaseModel):
    """All available game definitions."""

    games: list[GameDefinitionResponse]
    default_game: str = Field(description="Default game_type used when none is specified.")
