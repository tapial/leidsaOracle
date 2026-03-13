"""Data import endpoints — scraping and Excel file upload."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_game_def
from src.config.settings import get_settings
from src.importer.importer_service import ImporterService
from src.scraper.scraper_service import ScraperService
from src.validator.normalizer import Normalizer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/import")


@router.post("/scrape/latest", summary="Scrape latest draws")
async def scrape_latest(
    game_type: str = Query(default="loto", description="Game identifier."),
    db: AsyncSession = Depends(get_db),
):
    """Scrape the latest draw results from the web."""
    game_def = get_game_def(game_type)
    settings = get_settings()
    normalizer = Normalizer()
    service = ScraperService(settings, normalizer)

    result = await service.scrape_latest(game_type, db)
    await db.commit()

    return {
        "draws_found": result.draws_found,
        "draws_imported": result.draws_imported,
        "draws_skipped": result.draws_skipped,
        "errors": result.errors[:10],
    }


@router.post("/scrape/historical", summary="Scrape historical draws")
async def scrape_historical(
    game_type: str = Query(default="loto"),
    db: AsyncSession = Depends(get_db),
):
    """Scrape the full history of draw results."""
    game_def = get_game_def(game_type)
    settings = get_settings()
    normalizer = Normalizer()
    service = ScraperService(settings, normalizer)

    result = await service.scrape_full_history(game_type, db)
    await db.commit()

    return {
        "draws_found": result.draws_found,
        "draws_imported": result.draws_imported,
        "draws_skipped": result.draws_skipped,
        "errors": result.errors[:10],
    }


@router.post("/excel", summary="Import from Excel/CSV")
async def import_excel(
    game_type: str = Query(default="loto", description="Game identifier."),
    file: UploadFile = File(..., description="Excel (.xlsx) or CSV file."),
    db: AsyncSession = Depends(get_db),
):
    """Import lottery draws from an uploaded Excel or CSV file."""
    game_def = get_game_def(game_type)

    # Validate file type
    if file.filename and not file.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload .xlsx, .xls, or .csv.",
        )

    normalizer = Normalizer()
    service = ImporterService(normalizer)

    result = await service.import_excel(file, game_type, db)
    await db.commit()

    return {
        "filename": file.filename,
        "draws_found": result.draws_found,
        "draws_imported": result.draws_imported,
        "draws_skipped": result.draws_skipped,
        "errors": result.errors[:10],
    }
