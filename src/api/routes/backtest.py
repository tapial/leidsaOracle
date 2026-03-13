"""Backtesting endpoints."""

from __future__ import annotations

import datetime
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_game_def
from src.api.schemas.backtest_schemas import BacktestRequest, BacktestResponse
from src.backtesting.reporter import BacktestReporter
from src.backtesting.walk_forward import BacktestConfig, WalkForwardBacktester
from src.config.settings import get_settings
from src.database.models import BacktestResult
from src.database.repository import BacktestRepository, DrawRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/backtest")


@router.post("/run", response_model=BacktestResponse, summary="Run backtest")
async def run_backtest(
    body: BacktestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run a walk-forward backtest and return honest metrics."""
    game_type = body.game_type
    game_def = get_game_def(game_type)
    settings = get_settings()

    # Fetch draw matrix
    draws = await DrawRepository.get_all_numbers_as_matrix(db, game_type)
    if draws.size == 0:
        raise HTTPException(status_code=404, detail=f"No draws found for game '{game_type}'.")

    # Configure and run backtest
    config = BacktestConfig(
        train_window=body.train_window,
        step_size=body.step_size,
        combinations_per_step=body.combinations_per_step,
        max_steps=body.max_steps,
    )

    backtester = WalkForwardBacktester(game_def, settings)
    result = backtester.run(draws, config)

    if result.total_steps == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Not enough draws for backtesting. Need at least "
                f"{config.train_window + 1} draws, have {len(draws)}."
            ),
        )

    # Generate report
    reporter = BacktestReporter(game_def)
    report = reporter.full_report(result)

    # Persist backtest result
    metrics = reporter.metrics_calculator.compute(result)
    bt_result = BacktestResult(
        game_type=game_type,
        run_id=str(uuid.uuid4()),
        run_date=datetime.date.today(),
        train_window_size=config.train_window,
        test_window_size=config.test_window,
        hit_rates=report["metrics"]["match_distribution"],
        number_hit_rate=metrics.number_hit_rate,
        feature_stability=metrics.feature_stability,
        steps_detail={"total_steps": result.total_steps, "elapsed": result.elapsed_seconds},
        config=report["config"],
    )
    await BacktestRepository.save_result(db, bt_result)
    await db.commit()

    return BacktestResponse(
        summary=report["summary"],
        metrics=report["metrics"],
        config=report["config"],
    )
