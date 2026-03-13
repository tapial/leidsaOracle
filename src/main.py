"""
LeidsaOracle — FastAPI Application Factory

LEIDSA Lottery Statistical Analysis System.
This is a probabilistic research tool for analyzing historical lottery patterns.
Lottery draws are independent random events — past patterns do NOT predict future outcomes.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import get_settings
from src.database.engine import dispose_engine, init_db

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init DB on startup, dispose on shutdown."""
    logger.info("LeidsaOracle starting up...")
    await init_db()
    logger.info("Database initialized.")
    yield
    logger.info("LeidsaOracle shutting down...")
    await dispose_engine()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="LeidsaOracle",
        description=(
            "LEIDSA Lottery Statistical Analysis System.\n\n"
            "**DISCLAIMER**: This is a probabilistic research tool. "
            "Lottery draws are independent random events. "
            "Past frequency patterns do NOT predict future outcomes. "
            "No combination is more or less likely to win than any other. "
            "Use this tool for research and entertainment purposes only."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    from src.api.router import api_router
    app.include_router(api_router)

    return app


# Module-level app instance for uvicorn
app = create_app()
