"""Analysis endpoints — run and retrieve statistical analysis."""

from __future__ import annotations

import datetime
import hashlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_game_def
from src.api.schemas.analysis_schemas import (
    AnalysisResponse,
    RunAnalysisRequest,
)
from src.analytics.engine import AnalyticsEngine
from src.config.constants import GameDefinition
from src.config.settings import get_settings
from src.database.models import AnalysisSnapshot
from src.database.repository import AnalysisRepository, DrawRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis")


def _config_hash(settings) -> str:
    """Compute a hash of analytics config for cache invalidation."""
    config_str = json.dumps({
        "rolling_windows": settings.analytics.rolling_windows,
        "monte_carlo_iterations": settings.analytics.monte_carlo_iterations,
        "top_pairs": settings.analytics.top_pairs,
        "top_triplets": settings.analytics.top_triplets,
    }, sort_keys=True)
    return hashlib.sha256(config_str.encode()).hexdigest()[:16]


@router.post("/run", response_model=AnalysisResponse, summary="Run analysis")
async def run_analysis(
    body: RunAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run a full statistical analysis on stored draws."""
    game_type = body.game_type
    game_def = get_game_def(game_type)
    settings = get_settings()

    # Check for cached snapshot (within 24h)
    if not body.force_refresh:
        existing = await AnalysisRepository.get_latest_snapshot(db, game_type)
        if existing and (datetime.date.today() - existing.snapshot_date).days < 1:
            return _snapshot_to_response(existing, game_type)

    # Fetch draw matrix
    draws = await DrawRepository.get_all_numbers_as_matrix(db, game_type)
    if draws.size == 0:
        raise HTTPException(status_code=404, detail=f"No draws found for game '{game_type}'.")

    # Run analytics engine
    engine = AnalyticsEngine(game_def, settings)
    result = engine.run_full_analysis(draws)

    # Persist snapshot
    snapshot = AnalysisSnapshot(
        game_type=game_type,
        snapshot_date=datetime.date.today(),
        draw_count=result.draw_count,
        frequency_data={
            "global_counts": {str(k): v for k, v in result.frequency.global_counts.items()},
            "relative_frequencies": {str(k): v for k, v in result.frequency.relative_frequencies.items()},
        },
        recency_data={"per_number": {str(k): v for k, v in result.recency.per_number.items()}},
        hot_cold_data={"per_number": {str(k): v for k, v in result.hot_cold.per_number.items()}},
        pair_data={"pairs": result.pairs.pairs},
        triplet_data={"triplets": getattr(result.triplets, 'triplets', {})},
        distribution_data={
            "sum_mean": result.distribution.sum_mean,
            "sum_std": result.distribution.sum_std,
            "spread_mean": result.distribution.spread_mean,
            "spread_std": result.distribution.spread_std,
            "odd_even": getattr(result.balance, 'odd_even_histogram', {}),
            "low_high": getattr(result.balance, 'low_high_histogram', {}),
        },
        entropy_score=result.entropy.normalized_entropy,
        config_hash=_config_hash(settings),
    )
    await AnalysisRepository.save_snapshot(db, snapshot)
    await db.commit()

    return _snapshot_to_response(snapshot, game_type)


@router.get("/latest", response_model=AnalysisResponse, summary="Latest analysis")
async def latest_analysis(
    game_type: str = Query(default="loto"),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent cached analysis snapshot."""
    snapshot = await AnalysisRepository.get_latest_snapshot(db, game_type)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis snapshot found for '{game_type}'. Run POST /analysis/run first.",
        )
    return _snapshot_to_response(snapshot, game_type)


def _snapshot_to_response(snapshot: AnalysisSnapshot, game_type: str) -> AnalysisResponse:
    """Convert an AnalysisSnapshot ORM model to the API response schema."""
    return AnalysisResponse(
        game_type=game_type,
        snapshot_date=snapshot.snapshot_date,
        draw_count=snapshot.draw_count,
        frequency=snapshot.frequency_data,
        recency=snapshot.recency_data,
        hot_cold=snapshot.hot_cold_data,
        pairs=snapshot.pair_data,
        distribution=snapshot.distribution_data,
        entropy_score=snapshot.entropy_score,
    )
