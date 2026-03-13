# LeidsaOracle

LEIDSA Lottery Statistical Analysis System — a containerized probabilistic research tool for analyzing Dominican Republic lottery historical patterns, generating statistically ranked combinations, and performing walk-forward backtesting.

> **DISCLAIMER**: This is a probabilistic research tool. Lottery draws are independent random events. Past frequency patterns do NOT predict future outcomes. No combination is more or less likely to win than any other. Use this tool for research and entertainment purposes only.

## Features

- **Dual data ingestion** — Web scrapers (loteriasdominicanas.com + conectate.com.do fallback) and Excel/CSV import with auto-detection
- **10 statistical analyzers** — Frequency, recency, hot/cold (binomial z-scores), pair co-occurrence, triplet co-occurrence, balance (odd/even, low/high), sum/spread distribution, Shannon entropy, Monte Carlo simulation
- **Combination generation** — 3-strategy pipeline (weighted random 60%, top-N greedy 20%, balanced 20%) with Hamming-distance diversity enforcement
- **Ensemble scoring** — 10 weighted feature scores with configurable weights
- **Natural language explanations** — Per-combination narratives explaining statistical reasoning
- **Walk-forward backtesting** — Strict temporal isolation, hypergeometric baselines, feature stability analysis
- **Configurable games** — Registry-based design supports Loto (6/38), Loto Mas (6/38+1), Loto Pool (5/31)
- **REST API** — FastAPI with async PostgreSQL, full CRUD + analysis + generation endpoints
- **Interactive UI** — Streamlit dashboard with analysis visualization, generator, and backtest pages

## Architecture

```
leidsaOracle/
├── src/
│   ├── analytics/        # 9 statistical analyzers + engine orchestrator
│   ├── api/              # FastAPI routes, schemas, dependencies
│   ├── backtesting/      # Walk-forward engine, metrics, reporter
│   ├── config/           # Settings, game definitions, weights
│   ├── database/         # SQLAlchemy models, async engine, repositories
│   ├── explainability/   # NL explanation templates + narrator
│   ├── generator/        # Pool builder, constraints, diversity, generator
│   ├── importer/         # Excel/CSV reader + import service
│   ├── scoring/          # Feature scores + ensemble scorer
│   ├── scraper/          # HTTP client, parsers, scraper service
│   ├── ui/               # Streamlit pages (dashboard, analysis, generator, backtest)
│   ├── validator/        # Normalizer, deduplicator, schemas
│   └── main.py           # FastAPI app factory
├── migrations/           # Alembic database migrations
├── tests/                # Unit + integration tests
├── templates/            # Excel import template
├── docker-compose.yml    # 3-service stack (db, api, streamlit)
├── Dockerfile
└── pyproject.toml
```

## Quick Start

### Docker (recommended)

```bash
# Clone and start all services
git clone <repo-url> leidsaOracle && cd leidsaOracle

# Create .env (optional — sensible defaults exist)
cp .env.example .env

# Build and start
docker compose up --build

# Services:
#   API:       http://localhost:8000
#   API Docs:  http://localhost:8000/docs
#   Streamlit: http://localhost:8501
#   Postgres:  localhost:5432
```

### Local Development

```bash
# Prerequisites: Python 3.11+, PostgreSQL 16+

# Install all dependencies
pip install -e ".[all]"

# Set database URL
export DATABASE_URL=postgresql+asyncpg://leidsa:leidsa_dev@localhost:5432/leidsa_oracle

# Run migrations
alembic upgrade head

# Start API server
uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload

# Start Streamlit (separate terminal)
streamlit run src/ui/app.py --server.port=8501
```

### Running Tests

```bash
# Run all tests (no database required for unit tests)
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=term-missing
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/api/v1/draws` | List draws (paginated) |
| `GET` | `/api/v1/draws/stats` | Draw statistics |
| `GET` | `/api/v1/draws/latest` | Latest draw |
| `POST` | `/api/v1/analysis/run` | Run full statistical analysis |
| `GET` | `/api/v1/analysis/latest` | Latest analysis snapshot |
| `POST` | `/api/v1/generate` | Generate ranked combinations |
| `GET` | `/api/v1/generate/latest` | Latest generated batch |
| `POST` | `/api/v1/backtest/run` | Run walk-forward backtest |
| `POST` | `/api/v1/import/scrape/latest` | Scrape latest draws |
| `POST` | `/api/v1/import/scrape/historical` | Scrape historical draws |
| `POST` | `/api/v1/import/excel` | Import from Excel/CSV |
| `GET` | `/api/v1/config/games` | List supported games |
| `GET` | `/api/v1/config/weights` | Current scoring weights |
| `POST` | `/api/v1/config/weights/validate` | Validate custom weights |

## Configuration

Environment variables (all optional with defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://leidsa:leidsa_dev@localhost:5432/leidsa_oracle` | Database connection |
| `LEIDSA_DEFAULT_GAME` | `loto` | Default game type |
| `LEIDSA_MONTE_CARLO_ITERATIONS` | `100000` | Monte Carlo simulation count |
| `LEIDSA_CANDIDATE_POOL_SIZE` | `5000` | Candidates before final selection |
| `LEIDSA_FINAL_COMBINATION_COUNT` | `10` | Combinations per generation |

## Scoring Weights

The ensemble scorer uses 10 feature scores, each normalized to [0, 1]:

| Feature | Default Weight | Description |
|---------|---------------|-------------|
| `frequency_score` | 0.15 | Historical appearance frequency |
| `recency_score` | 0.12 | Overdue ratio (gap / avg gap) |
| `hot_cold_score` | 0.10 | Binomial z-score classification |
| `pair_score` | 0.10 | Pair co-occurrence lift |
| `triplet_score` | 0.08 | Triplet co-occurrence lift |
| `odd_even_score` | 0.10 | Balance of odd/even numbers |
| `low_high_score` | 0.10 | Balance of low/high numbers |
| `sum_score` | 0.10 | Gaussian fit to historical sums |
| `spread_score` | 0.08 | Range coverage of the pool |
| `entropy_score` | 0.07 | Shannon entropy of selections |

## Tech Stack

- **API**: FastAPI, Uvicorn, Pydantic v2
- **Database**: PostgreSQL 16 + SQLAlchemy 2.0 (async) + Alembic
- **Analytics**: NumPy, SciPy, Pandas
- **UI**: Streamlit, Plotly
- **Scraping**: httpx, BeautifulSoup4, lxml
- **Container**: Docker Compose

## License

MIT
