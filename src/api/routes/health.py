"""Health-check endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from src.database.engine import _get_engine

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", summary="Health check")
async def health_check():
    """Return service status with database connectivity and draw count."""
    db_ok = False
    draw_count = 0

    try:
        engine = _get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_ok = True
            result = await conn.execute(text("SELECT COUNT(*) FROM draws"))
            row = result.scalar()
            draw_count = row or 0
    except Exception as exc:
        logger.warning("Health check DB probe failed: %s", exc)

    return {
        "status": "ok" if db_ok else "degraded",
        "service": "LeidsaOracle",
        "version": "1.0.0",
        "db_ok": db_ok,
        "draw_count": draw_count,
    }
