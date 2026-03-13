"""Pydantic schemas for combination generation endpoints."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.explainability.templates import DISCLAIMER


class ConstraintsInput(BaseModel):
    """Optional structural constraints for combination generation."""

    must_include: list[int] = Field(
        default_factory=list,
        description="Numbers that must appear in every generated combination.",
    )
    must_exclude: list[int] = Field(
        default_factory=list,
        description="Numbers that must NOT appear in any generated combination.",
    )
    min_sum: int | None = Field(
        default=None,
        description="Minimum sum of numbers in a combination.",
    )
    max_sum: int | None = Field(
        default=None,
        description="Maximum sum of numbers in a combination.",
    )


class GenerateRequest(BaseModel):
    """Request body for generating new combinations."""

    game_type: str = Field(description="Game identifier (e.g. 'loto').")
    count: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of combinations to generate.",
    )
    weights: dict[str, float] | None = Field(
        default=None,
        description="Custom ensemble weights. Must sum to 1.0 if provided.",
    )
    constraints: ConstraintsInput | None = Field(
        default=None,
        description="Optional structural constraints.",
    )


class CombinationResponse(BaseModel):
    """A single scored combination."""

    rank: int
    numbers: list[int]
    ensemble_score: float
    percentile: float | None = Field(
        default=None,
        description="Monte Carlo percentile (0-100), if available.",
    )
    feature_scores: dict[str, float] = Field(
        description="Individual feature scores (0-1)."
    )
    explanation: str | None = Field(
        default=None,
        description="Human-readable explanation of why this combination was selected.",
    )

    model_config = {"from_attributes": True}


class GenerationResponse(BaseModel):
    """Full response from a combination generation run."""

    batch_id: str
    game_type: str
    generated_at: datetime.datetime
    disclaimer: str = Field(default=DISCLAIMER)
    combinations: list[CombinationResponse]
