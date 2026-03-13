"""Pydantic schemas for draw-related API endpoints."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, Field


class DrawResponse(BaseModel):
    """Single lottery draw result."""

    id: int
    game_type: str
    draw_date: datetime.date
    numbers: list[int]
    bonus_number: int | None = None
    source: str | None = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class DrawListResponse(BaseModel):
    """Paginated list of draws."""

    total: int = Field(description="Total draws matching the query.")
    draws: list[DrawResponse]
    limit: int
    offset: int
    has_more: bool


class DrawStatsResponse(BaseModel):
    """High-level statistics about stored draws."""

    total_draws: int
    date_range: dict[str, datetime.date | None] = Field(
        description="Earliest and latest draw dates: {earliest, latest}."
    )
    games_available: list[str] = Field(
        description="List of game_type codes with at least one draw."
    )
