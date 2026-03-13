"""Health-check endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", summary="Health check")
async def health_check():
    """Return service status."""
    return {"status": "ok", "service": "LeidsaOracle", "version": "1.0.0"}
