"""Configuration endpoints — games and weights."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.schemas.config_schemas import (
    GameDefinitionResponse,
    GamesResponse,
    UpdateWeightsRequest,
    WeightsResponse,
)
from src.config.constants import GAME_REGISTRY
from src.config.settings import get_settings
from src.config.weights import DEFAULT_WEIGHTS, WEIGHT_NAMES, validate_weights

router = APIRouter(prefix="/config")


@router.get("/games", response_model=GamesResponse, summary="List games")
async def list_games():
    """Return all available game definitions."""
    games = [
        GameDefinitionResponse(
            code=g.code,
            display_name=g.display_name,
            number_count=g.number_count,
            pool_min=g.pool_min,
            pool_max=g.pool_max,
            pool_size=g.pool_size,
            has_bonus=g.has_bonus,
            bonus_min=g.bonus_min,
            bonus_max=g.bonus_max,
            draw_days=list(g.draw_days),
            draw_time=g.draw_time,
        )
        for g in GAME_REGISTRY.values()
    ]
    return GamesResponse(
        games=games,
        default_game=get_settings().default_game_type,
    )


@router.get("/weights", response_model=WeightsResponse, summary="Current weights")
async def get_weights():
    """Return the current default ensemble scoring weights."""
    return WeightsResponse(
        weights=dict(DEFAULT_WEIGHTS),
        weight_names=list(WEIGHT_NAMES),
    )


@router.post("/weights/validate", response_model=WeightsResponse, summary="Validate weights")
async def validate_custom_weights(body: UpdateWeightsRequest):
    """Validate a set of custom weights without persisting them."""
    try:
        validated = validate_weights(body.weights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WeightsResponse(
        weights=validated,
        weight_names=list(WEIGHT_NAMES),
    )
