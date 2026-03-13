"""
SQLAlchemy 2.0 ORM models for the LEIDSA Oracle database.

Uses ``Mapped[]`` type hints and PostgreSQL-specific column types
(``ARRAY``, ``JSONB``) for rich, queryable storage of lottery data.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Declarative base for all LEIDSA Oracle models."""

    pass


# ── Import Log ───────────────────────────────────────────────────────────


class ImportLog(Base):
    """Tracks each data-import run (scraper, CSV upload, etc.)."""

    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Origin of the import: 'scraper', 'csv', 'excel', 'manual'.",
    )
    source_identifier: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="URL, file path, or other identifier.",
    )
    file_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="SHA-256 hash for deduplication of file-based imports.",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="Current state: pending | running | completed | failed.",
    )
    draws_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    draws_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    draws_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    draws: Mapped[list[Draw]] = relationship("Draw", back_populates="import_log")


# ── Draw ─────────────────────────────────────────────────────────────────


class Draw(Base):
    """A single lottery draw result."""

    __tablename__ = "draws"
    __table_args__ = (
        UniqueConstraint("game_type", "draw_date", name="uq_draws_game_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Game identifier matching GAME_REGISTRY keys.",
    )
    draw_date: Mapped[datetime.date] = mapped_column(
        nullable=False,
        index=True,
        comment="Calendar date of the draw.",
    )
    numbers: Mapped[list[int]] = mapped_column(
        ARRAY(Integer),
        nullable=False,
        comment="Sorted main numbers drawn.",
    )
    bonus_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Bonus / extra number (only for games with has_bonus=True).",
    )
    source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="How this draw was obtained: 'scraper', 'csv', 'manual'.",
    )
    import_log_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("import_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    import_log: Mapped[ImportLog | None] = relationship("ImportLog", back_populates="draws")


# ── Analysis Snapshot ────────────────────────────────────────────────────


class AnalysisSnapshot(Base):
    """Point-in-time statistical analysis of historical draws."""

    __tablename__ = "analysis_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    snapshot_date: Mapped[datetime.date] = mapped_column(nullable=False, index=True)
    draw_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of draws included in the analysis.",
    )
    frequency_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Absolute and relative frequency per number.",
    )
    recency_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Draws-since-last-seen and gap statistics.",
    )
    hot_cold_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Hot/cold/warm classification per number.",
    )
    pair_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Top co-occurring number pairs with counts and lift.",
    )
    triplet_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Top co-occurring number triplets with counts and lift.",
    )
    distribution_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Odd/even, low/high, sum, and spread distributions.",
    )
    entropy_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Shannon entropy of the overall frequency distribution.",
    )
    config_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Hash of the analytics config used, for cache invalidation.",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    generated_combinations: Mapped[list[GeneratedCombination]] = relationship(
        "GeneratedCombination",
        back_populates="snapshot",
    )


# ── Generated Combination ───────────────────────────────────────────────


class GeneratedCombination(Base):
    """A single combination produced by the generator."""

    __tablename__ = "generated_combinations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID grouping all combinations from a single generation run.",
    )
    generation_date: Mapped[datetime.date] = mapped_column(nullable=False)
    numbers: Mapped[list[int]] = mapped_column(
        ARRAY(Integer),
        nullable=False,
        comment="The generated combination (sorted).",
    )
    rank: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="1-based rank within the batch.",
    )
    ensemble_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Weighted ensemble score used for ranking.",
    )
    feature_scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Individual feature scores keyed by weight name.",
    )
    explanation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable explanation of why this combination was selected.",
    )
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("analysis_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    snapshot: Mapped[AnalysisSnapshot | None] = relationship(
        "AnalysisSnapshot",
        back_populates="generated_combinations",
    )


# ── Backtest Result ──────────────────────────────────────────────────────


class BacktestResult(Base):
    """Stores output from a single backtesting run."""

    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID identifying this backtest run.",
    )
    run_date: Mapped[datetime.date] = mapped_column(nullable=False)
    train_window_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of draws used for training in each step.",
    )
    test_window_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of draws used for testing in each step.",
    )
    hit_rates: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Aggregate hit-rate metrics (e.g. match-3, match-4, ...).",
    )
    number_hit_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Overall per-number hit rate across all test windows.",
    )
    feature_stability: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Variance / stability metrics for each feature across steps.",
    )
    steps_detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Per-step detail array for drill-down analysis.",
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full configuration snapshot used for reproducibility.",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
