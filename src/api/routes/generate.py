"""Combination generation endpoints."""

from __future__ import annotations

import datetime
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_game_def
from src.api.schemas.combo_schemas import (
    CombinationResponse,
    GenerateRequest,
    GenerationResponse,
)
from src.analytics.engine import AnalyticsEngine
from src.config.constants import GameDefinition
from src.config.settings import get_settings
from src.config.weights import DEFAULT_WEIGHTS, merge_weights
from src.database.models import GeneratedCombination
from src.database.repository import (
    AnalysisRepository,
    CombinationRepository,
    DrawRepository,
)
from src.explainability.narrator import ExplanationNarrator, NumberDetail
from src.generator.combination_generator import CombinationGenerator, GenerationConfig
from src.generator.constraints import CombinationConstraints
from src.generator.pool_builder import PoolBuilder
from src.scoring.ensemble import EnsembleScorer
from src.scoring.feature_scores import AnalysisData, FeatureScorer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/generate")


@router.post("", response_model=GenerationResponse, summary="Generate combinations")
async def generate_combinations(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate ranked, diverse lottery combinations with explanations."""
    game_type = body.game_type
    game_def = get_game_def(game_type)
    settings = get_settings()

    # Validate and merge weights
    try:
        weights = merge_weights(body.weights) if body.weights else dict(DEFAULT_WEIGHTS)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Get draw data
    draws = await DrawRepository.get_all_numbers_as_matrix(db, game_type)
    if draws.size == 0:
        raise HTTPException(status_code=404, detail=f"No draws found for game '{game_type}'.")

    # Run analysis
    engine = AnalyticsEngine(game_def, settings)
    analysis = engine.run_full_analysis(draws)
    per_number_scores = engine.build_per_number_scores(analysis)

    # Build pool
    pool_builder = PoolBuilder()
    pool = pool_builder.build(per_number_scores, game_def)

    # Build constraints (structural filters based on game rules)
    constraints = CombinationConstraints(
        game_def,
        sum_mean=analysis.distribution.sum_mean,
        sum_std=analysis.distribution.sum_std,
    )

    # Build scorer
    analysis_data = _build_analysis_data(analysis)
    feature_scorer = FeatureScorer(game_def, analysis_data)
    ensemble_scorer = EnsembleScorer(weights)

    def scorer_fn(combo):
        fs = feature_scorer.score(combo)
        es = ensemble_scorer.score(fs)
        return fs, es

    # Generate
    gen_config = GenerationConfig(
        candidate_pool_size=settings.generator.candidate_pool_size,
        final_count=body.count,
        min_hamming_distance=settings.generator.min_hamming_distance,
    )
    generator = CombinationGenerator(game_def, gen_config)
    candidates = generator.generate(pool, constraints, scorer_fn, weights)

    # Generate explanations
    narrator = ExplanationNarrator(game_def)
    batch_id = str(uuid.uuid4())
    combo_models = []
    combo_responses = []

    for cand in candidates:
        rank = cand.feature_scores.get("rank", 0)
        explanation = narrator.explain(
            numbers=cand.numbers,
            rank=int(rank),
            ensemble_score=cand.ensemble_score,
            feature_scores=cand.feature_scores,
            sum_mean=analysis.distribution.sum_mean,
            sum_std=analysis.distribution.sum_std,
        )

        combo_models.append(GeneratedCombination(
            game_type=game_type,
            batch_id=batch_id,
            generation_date=datetime.date.today(),
            numbers=cand.numbers,
            rank=int(rank),
            ensemble_score=cand.ensemble_score,
            feature_scores=cand.feature_scores,
            explanation=explanation,
        ))

        combo_responses.append(CombinationResponse(
            rank=int(rank),
            numbers=cand.numbers,
            ensemble_score=round(cand.ensemble_score, 6),
            feature_scores={k: round(v, 4) for k, v in cand.feature_scores.items() if k != "rank"},
            explanation=explanation,
        ))

    # Persist
    await CombinationRepository.save_batch(db, combo_models)
    await db.commit()

    return GenerationResponse(
        batch_id=batch_id,
        game_type=game_type,
        generated_at=datetime.datetime.now(datetime.timezone.utc),
        combinations=combo_responses,
    )


@router.get("/latest", response_model=GenerationResponse | None, summary="Latest generation")
async def latest_generation(
    game_type: str = Query(default="loto"),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recently generated combination batch."""
    combos = await CombinationRepository.get_latest_batch(db, game_type)
    if not combos:
        raise HTTPException(
            status_code=404,
            detail=f"No generated combinations found for '{game_type}'.",
        )
    return GenerationResponse(
        batch_id=combos[0].batch_id,
        game_type=game_type,
        generated_at=combos[0].created_at,
        combinations=[
            CombinationResponse(
                rank=c.rank,
                numbers=c.numbers,
                ensemble_score=c.ensemble_score,
                feature_scores=c.feature_scores,
                explanation=c.explanation,
            )
            for c in combos
        ],
    )


def _build_analysis_data(analysis) -> AnalysisData:
    """Convert AnalysisResult to AnalysisData for the feature scorer."""
    freq_data = analysis.frequency
    max_count = max(freq_data.global_counts.values()) if freq_data.global_counts else 1
    freq_percentiles = {n: count / max_count for n, count in freq_data.global_counts.items()}

    overdue_ratios = {
        n: data.get("overdue_ratio", 1.0)
        for n, data in analysis.recency.per_number.items()
    }

    z_scores = {
        n: data.get("z_score", 0.0)
        for n, data in analysis.hot_cold.per_number.items()
    }

    pair_lifts = {}
    for key, data in analysis.pairs.pairs.items():
        parts = key.split(",")
        if len(parts) == 2:
            pair_lifts[(int(parts[0]), int(parts[1]))] = data.get("lift", 1.0)

    triplet_lifts = {}
    for key, data in getattr(analysis.triplets, 'triplets', {}).items():
        parts = key.split(",")
        if len(parts) == 3:
            triplet_lifts[tuple(int(p) for p in parts)] = data.get("lift", 1.0)

    total = sum(freq_data.global_counts.values()) or 1
    number_frequencies = {n: count / total for n, count in freq_data.global_counts.items()}

    return AnalysisData(
        frequency_percentiles=freq_percentiles,
        overdue_ratios=overdue_ratios,
        hot_cold_z_scores=z_scores,
        pair_lifts=pair_lifts,
        triplet_lifts=triplet_lifts,
        sum_mean=analysis.distribution.sum_mean,
        sum_std=analysis.distribution.sum_std,
        number_frequencies=number_frequencies,
    )
