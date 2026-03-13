"""
Application settings driven by environment variables.

Uses pydantic-settings to load configuration from environment variables
with sensible defaults for local development.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection settings."""

    model_config = SettingsConfigDict(env_prefix="DB_")

    url: str = Field(
        default="postgresql+asyncpg://leidsa:leidsa_dev@localhost:5432/leidsa_oracle",
        alias="DATABASE_URL",
        description="Async SQLAlchemy database URL (must use asyncpg driver).",
    )
    pool_size: int = Field(default=10, description="Connection pool size.")
    max_overflow: int = Field(default=20, description="Max overflow connections above pool_size.")
    echo: bool = Field(default=False, description="Echo SQL statements for debugging.")


class ScraperSettings(BaseSettings):
    """Web scraper configuration."""

    model_config = SettingsConfigDict(env_prefix="SCRAPER_")

    base_url: str = Field(
        default="https://loteriasdominicanas.com",
        description="Primary scraping target (loteriasdominicanas.com).",
    )
    fallback_url: str = Field(
        default="https://www.conectate.com.do",
        description="Fallback scraping target (conectate.com.do).",
    )
    timeout: int = Field(default=30, description="HTTP request timeout in seconds.")
    max_retries: int = Field(default=3, description="Maximum number of retry attempts.")
    delay: float = Field(
        default=1.5,
        description="Delay in seconds between requests to be polite.",
    )


class AnalyticsSettings(BaseSettings):
    """Statistical analytics configuration."""

    model_config = SettingsConfigDict(env_prefix="ANALYTICS_")

    rolling_windows: list[int] = Field(
        default=[30, 60, 90, 180],
        description="Draw count windows for rolling frequency analysis.",
    )
    monte_carlo_iterations: int = Field(
        default=100_000,
        description="Number of Monte Carlo simulation iterations.",
    )
    top_pairs: int = Field(
        default=100,
        description="Number of top co-occurring pairs to track.",
    )
    top_triplets: int = Field(
        default=50,
        description="Number of top co-occurring triplets to track.",
    )
    chi_square_significance: float = Field(
        default=0.05,
        description="Significance threshold for chi-square uniformity tests.",
    )

    @field_validator("chi_square_significance")
    @classmethod
    def _validate_significance(cls, v: float) -> float:
        if not 0.0 < v < 1.0:
            raise ValueError("chi_square_significance must be between 0 and 1 (exclusive)")
        return v


class GeneratorSettings(BaseSettings):
    """Combination generator configuration."""

    model_config = SettingsConfigDict(env_prefix="GENERATOR_")

    candidate_pool_size: int = Field(
        default=5_000,
        description="Size of the initial random candidate pool.",
    )
    final_combination_count: int = Field(
        default=10,
        description="Number of final combinations to return.",
    )
    min_hamming_distance: int = Field(
        default=3,
        description="Minimum Hamming distance between selected combinations.",
    )


class APISettings(BaseSettings):
    """FastAPI server configuration."""

    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = Field(default="0.0.0.0", description="Server bind address.")
    port: int = Field(default=8000, description="Server port.")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8501"],
        description="Allowed CORS origins.",
    )


class Settings(BaseSettings):
    """
    Root application settings.

    All values can be overridden via environment variables. Nested settings
    use their own prefixes (e.g. SCRAPER_TIMEOUT, ANALYTICS_TOP_PAIRS).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Top-level settings ──────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://leidsa:leidsa_dev@localhost:5432/leidsa_oracle",
        description="Primary database URL (convenience alias).",
    )
    default_game_type: str = Field(
        default="loto",
        description="Default game type used when none is specified.",
    )

    # ── Nested setting groups ───────────────────────────────────────────
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    scraper: ScraperSettings = Field(default_factory=ScraperSettings)
    analytics: AnalyticsSettings = Field(default_factory=AnalyticsSettings)
    generator: GeneratorSettings = Field(default_factory=GeneratorSettings)
    api: APISettings = Field(default_factory=APISettings)

    @field_validator("default_game_type")
    @classmethod
    def _validate_game_type(cls, v: str) -> str:
        allowed = {"loto", "loto_mas", "loto_pool"}
        if v not in allowed:
            raise ValueError(f"default_game_type must be one of {allowed}, got '{v}'")
        return v


# ── Singleton accessor ──────────────────────────────────────────────────

_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings instance (created once)."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()
    return _settings
