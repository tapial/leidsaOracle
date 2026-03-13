"""Draw data endpoints."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_game_def
from src.api.schemas.draw_schemas import DrawListResponse, DrawResponse, DrawStatsResponse
from src.config.constants import GameDefinition, GAME_REGISTRY
from src.database.repository import DrawRepository

router = APIRouter(prefix="/draws")


@router.get("", response_model=DrawListResponse, summary="List draws")
async def list_draws(
    game_type: str = Query(default="loto", description="Game identifier."),
    date_from: datetime.date | None = Query(default=None, description="Earliest date (inclusive)."),
    date_to: datetime.date | None = Query(default=None, description="Latest date (inclusive)."),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Return paginated draw results for a game."""
    game_def = get_game_def(game_type)
    draws = await DrawRepository.get_draws(
        db, game_type=game_type, date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    total = await DrawRepository.get_draw_count(db, game_type)
    return DrawListResponse(
        total=total,
        draws=[DrawResponse.model_validate(d) for d in draws],
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.get("/stats", response_model=DrawStatsResponse, summary="Draw statistics")
async def draw_stats(db: AsyncSession = Depends(get_db)):
    """Return high-level draw statistics across all games."""
    games_available = []
    earliest = None
    latest = None
    total = 0
    for code in GAME_REGISTRY:
        count = await DrawRepository.get_draw_count(db, code)
        if count > 0:
            games_available.append(code)
            total += count
            lt = await DrawRepository.get_latest_draw(db, code)
            draws = await DrawRepository.get_draws(db, code, limit=1, offset=0)
            # Get oldest via offset trick
            oldest_draws = await DrawRepository.get_draws(db, code, limit=1, offset=count - 1)
            if lt:
                if latest is None or lt.draw_date > latest:
                    latest = lt.draw_date
            if oldest_draws:
                d = oldest_draws[0].draw_date
                if earliest is None or d < earliest:
                    earliest = d
    return DrawStatsResponse(
        total_draws=total,
        date_range={"earliest": earliest, "latest": latest},
        games_available=games_available,
    )


@router.get("/latest", response_model=DrawResponse | None, summary="Latest draw")
async def latest_draw(
    game_type: str = Query(default="loto"),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent draw for a game."""
    draw = await DrawRepository.get_latest_draw(db, game_type)
    if draw is None:
        raise HTTPException(status_code=404, detail=f"No draws found for game '{game_type}'.")
    return DrawResponse.model_validate(draw)
