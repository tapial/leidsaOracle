"""Shared Pydantic schemas: pagination, error responses, and disclaimer mixin."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from src.explainability.templates import DISCLAIMER

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""

    limit: int = Field(default=50, ge=1, le=500, description="Maximum items to return.")
    offset: int = Field(default=0, ge=0, description="Number of items to skip.")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic wrapper for paginated list responses."""

    total: int = Field(description="Total number of items matching the query.")
    items: list[T] = Field(description="Page of results.")
    limit: int
    offset: int
    has_more: bool = Field(description="True if more items exist beyond this page.")


class ErrorResponse(BaseModel):
    """Standard error payload returned by all error handlers."""

    detail: str


class DisclaimerMixin(BaseModel):
    """Injects the legal disclaimer into any response that includes generated data."""

    disclaimer: str = Field(
        default=DISCLAIMER,
        description="Legal disclaimer — lottery draws are independent random events.",
    )
