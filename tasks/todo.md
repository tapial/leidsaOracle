# LeidsaOracle — Todo

## Context
Containerized (Docker Compose + PostgreSQL) LEIDSA lottery analysis system. Scrapes results, imports Excel, 10 statistical methods, generates 10 ranked diverse combinations with explanations, walk-forward backtesting. Configurable game (default Loto 6/38). Dual scrapers + Excel fallback.

## Phase 1: Foundation + Docker
- [x] 1.1 Directory structure + `__init__.py` files
- [x] 1.2 `pyproject.toml`
- [x] 1.3 `.gitignore`, `.env.example`
- [x] 1.4 `Dockerfile`
- [x] 1.5 `docker-compose.yml`
- [x] 1.6 `scripts/entrypoint.sh`
- [x] 1.7 `src/config/settings.py`
- [x] 1.8 `src/config/constants.py`
- [x] 1.9 `src/config/weights.py`
- [x] 1.10 `src/database/engine.py`
- [x] 1.11 `src/database/models.py`
- [x] 1.12 `src/database/repository.py`
- [x] 1.13 Alembic setup + initial migration
- [x] 1.14 `src/validator/schemas.py`
- [x] 1.15 `src/validator/normalizer.py` (+ NormalizationError, normalize_batch)
- [x] 1.16 `src/validator/dedup.py`
- [x] 1.17 `tests/conftest.py` + fixtures
- [ ] 1.18 **Verify**: `docker compose up --build` → db healthy, api at :8000

## Phase 2: Data Ingestion
- [x] 2.1 `src/scraper/client.py`
- [x] 2.2 `src/scraper/base_parser.py`
- [x] 2.3 `src/scraper/loterias_dom_parser.py`
- [x] 2.4 `src/scraper/conectate_parser.py`
- [x] 2.5 `src/scraper/scraper_service.py`
- [x] 2.6 `src/importer/excel_reader.py`
- [x] 2.7 `src/importer/importer_service.py`
- [x] 2.8 `templates/leidsa_import_template.xlsx`
- [ ] 2.9 Tests: parser + importer (requires mock HTTP fixtures)
- [ ] 2.10 **Verify**: scrape real data → stored in DB (requires Docker + live site)

## Phase 3: Analytics Core
- [x] 3.1 `frequency.py`
- [x] 3.2 `recency.py`
- [x] 3.3 `hot_cold.py`
- [x] 3.4 `pairs.py`
- [x] 3.5 `triplets.py`
- [x] 3.6 `balance.py`
- [x] 3.7 `distribution.py`
- [x] 3.8 `entropy.py`
- [x] 3.9 `monte_carlo.py`
- [x] 3.10 `engine.py`
- [x] 3.11 Unit tests (test_analytics.py — 12 tests)
- [x] 3.12 **Verify**: full analysis on fixture data (AnalyticsEngine test passes)

## Phase 4: Generation & Scoring
- [x] 4.1 `pool_builder.py`
- [x] 4.2 `constraints.py`
- [x] 4.3 `diversity.py`
- [x] 4.4 `combination_generator.py`
- [x] 4.5 `feature_scores.py`
- [x] 4.6 `ensemble.py`
- [x] 4.7 `ranking.py`
- [x] 4.8 Tests (test_generator.py — 6 tests, test_scoring.py — 7 tests)
- [x] 4.9 **Verify**: generator test produces correct count, diversity enforced

## Phase 5: Explainability & Backtesting
- [x] 5.1 `templates.py`
- [x] 5.2 `narrator.py`
- [x] 5.3 `walk_forward.py`
- [x] 5.4 `metrics.py`
- [x] 5.5 `reporter.py`
- [x] 5.6 Tests (test_backtesting.py — 4 tests)
- [x] 5.7 **Verify**: narrator generates text, metrics compute correctly

## Phase 6: API Layer
- [x] 6.1 `src/main.py`
- [x] 6.2 `src/api/deps.py`
- [x] 6.3 `src/api/schemas/` (common, draw, analysis, combo, backtest, config)
- [x] 6.4 `src/api/router.py`
- [x] 6.5 `src/api/routes/health.py`
- [x] 6.6 `src/api/routes/draws.py`
- [x] 6.7 `src/api/routes/analysis.py`
- [x] 6.8 `src/api/routes/generate.py`
- [x] 6.9 `src/api/routes/backtest.py`
- [x] 6.10 `src/api/routes/config.py`
- [x] 6.11 `src/api/routes/import_data.py`
- [ ] 6.12 API integration tests (requires async test DB fixtures)
- [ ] 6.13 **Verify**: all endpoints work (requires running Docker stack)

## Phase 7: UI & Polish
- [x] 7.1 `src/ui/app.py` (Streamlit main)
- [x] 7.2 `src/ui/pages/dashboard.py`
- [x] 7.3 `src/ui/pages/analysis.py`
- [x] 7.4 `src/ui/pages/generator.py`
- [x] 7.5 `src/ui/pages/backtest.py`
- [x] 7.6 `README.md`
- [x] 7.7 `.claude/launch.json`
- [ ] 7.8 End-to-end Docker test
- [x] 7.9 `tasks/lessons.md`

## Verification Checklist
- [ ] `docker compose up --build` → all 3 services healthy
- [x] `pytest tests/` → **38 passed** (all non-DB tests)
- [ ] Full pipeline: scrape → analyze → 10 explained combos (requires Docker)
- [ ] Backtest: no temporal leakage (requires Docker + data)
- [ ] Diversity: all 10 combos Hamming ≥ 3 (requires Docker + data)
- [x] Disclaimer on every combination response (built into API + Streamlit)

## Progress Summary

### Session 1 — 2026-03-12
- Initial plan, research, GameDefinition registry design

### Session 2 — 2026-03-12
- All core modules: analytics (9 analyzers + engine), scoring, generator, backtesting, explainability, scraper, importer, validator, database, config, UI

### Session 3 — 2026-03-13
- Completed all API route modules (8 files: router, health, draws, analysis, generate, backtest, config, import_data)
- Completed all API schemas (6 schema files)
- Wrote test suite: conftest.py + 6 test files (analytics, generator, scoring, validator, backtesting)
- Fixed normalizer: added NormalizationError and normalize_batch()
- Fixed generate route: removed invalid CombinationConstraints kwargs
- Fixed test_validator: matched actual schema interfaces (RawDrawResult.date_str, list[str] numbers)
- Fixed test_analytics: corrected analyzer constructor calls and field names
- Fixed test_generator: dataclass attribute access, hamming distance expectation
- Created templates/leidsa_import_template.xlsx with formatting and instructions
- Verified: all 92 Python files parse clean, all imports resolve
- All 38 unit tests passing

### Session 4 — 2026-03-13
- Fixed last test failure: `FrequencyResult.global_pct` (not `relative_frequencies`)
- Created `.claude/launch.json` for dev server
- Created `README.md`
- Created initial Alembic migration (all 5 tables)
- Updated `tasks/lessons.md` with 3 new lessons
- Result: **38/38 tests passing**, all code modules complete

## Remaining (requires Docker environment)
- Docker compose build + verify all 3 services healthy
- API integration tests (async DB fixtures)
- End-to-end pipeline test: scrape → analyze → generate
- Live scraper verification against real sites
