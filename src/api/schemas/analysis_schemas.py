"""Pydantic schemas for analysis-related API endpoints."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, Field


class RunAnalysisRequest(BaseModel):
    """Request body for triggering a new analysis run."""

    game_type: str = Field(description="Game identifier (e.g. 'loto', 'loto_mas').")
    force_refresh: bool = Field(
        default=False,
        description="Re-run analysis even if a recent snapshot exists.",
    )


class FrequencyResponse(BaseModel):
    """Per-number absolute and relative frequency data."""

    global_counts: dict[str, int] = Field(
        description="Number -> total appearance count."
    )
    relative_frequencies: dict[str, float] = Field(
        default_factory=dict,
        description="Number -> relative frequency (0-1).",
    )
    rolling: dict[str, Any] = Field(
        default_factory=dict,
        description="Rolling-window frequency data.",
    )


class RecencyResponse(BaseModel):
    """Per-number gap and overdue information."""

    per_number: dict[str, Any] = Field(
        description="Number -> {gap, avg_gap, overdue_ratio, ...}."
    )


class HotColdResponse(BaseModel):
    """Temperature classification for each number."""

    per_number: dict[str, Any] = Field(
        description="Number -> {z_score, classification, ...}."
    )


class PairResponse(BaseModel):
    """Top co-occurring number pairs with lift statistics."""

    pairs: dict[str, Any] = Field(
        description="'a,b' -> {count, expected, lift}."
    )


class DistributionResponse(BaseModel):
    """Sum, spread, odd/even, and low/high distribution statistics."""

    sum_mean: float
    sum_std: float
    spread_mean: float = 0.0
    spread_std: float = 0.0
    odd_even: dict[str, Any] = Field(default_factory=dict)
    low_high: dict[str, Any] = Field(default_factory=dict)


class AnalysisResponse(BaseModel):
    """Full analysis snapshot returned to the client."""

    game_type: str
    snapshot_date: datetime.date
    draw_count: int
    frequency: dict[str, Any] = Field(description="Frequency analysis data.")
    recency: dict[str, Any] = Field(description="Recency analysis data.")
    hot_cold: dict[str, Any] = Field(description="Hot/cold classification data.")
    pairs: dict[str, Any] = Field(description="Pair co-occurrence data.")
    distribution: dict[str, Any] = Field(description="Distribution statistics.")
    entropy_score: float = Field(description="Shannon entropy of frequency distribution.")
