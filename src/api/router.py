"""Central API router — aggregates all endpoint groups."""

from __future__ import annotations

from fastapi import APIRouter

from src.api.routes.health import router as health_router
from src.api.routes.draws import router as draws_router
from src.api.routes.analysis import router as analysis_router
from src.api.routes.generate import router as generate_router
from src.api.routes.backtest import router as backtest_router
from src.api.routes.config import router as config_router
from src.api.routes.import_data import router as import_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health_router, tags=["Health"])
api_router.include_router(draws_router, tags=["Draws"])
api_router.include_router(analysis_router, tags=["Analysis"])
api_router.include_router(generate_router, tags=["Generate"])
api_router.include_router(backtest_router, tags=["Backtest"])
api_router.include_router(config_router, tags=["Config"])
api_router.include_router(import_router, tags=["Import"])
