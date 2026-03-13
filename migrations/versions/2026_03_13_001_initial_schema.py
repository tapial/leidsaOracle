"""Initial schema — all five core tables.

Revision ID: 001
Revises: (none)
Create Date: 2026-03-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- import_logs ---
    op.create_table(
        "import_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "source_type",
            sa.String(50),
            nullable=False,
            comment="Origin of the import: 'scraper', 'csv', 'excel', 'manual'.",
        ),
        sa.Column(
            "source_identifier",
            sa.String(500),
            nullable=True,
            comment="URL, file path, or other identifier.",
        ),
        sa.Column(
            "file_hash",
            sa.String(64),
            nullable=True,
            comment="SHA-256 hash for deduplication of file-based imports.",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            comment="Current state: pending | running | completed | failed.",
        ),
        sa.Column("draws_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("draws_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("draws_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_logs_file_hash", "import_logs", ["file_hash"])

    # --- draws ---
    op.create_table(
        "draws",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "game_type",
            sa.String(20),
            nullable=False,
            comment="Game identifier matching GAME_REGISTRY keys.",
        ),
        sa.Column(
            "draw_date",
            sa.Date(),
            nullable=False,
            comment="Calendar date of the draw.",
        ),
        sa.Column(
            "numbers",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            comment="Sorted main numbers drawn.",
        ),
        sa.Column(
            "bonus_number",
            sa.Integer(),
            nullable=True,
            comment="Bonus / extra number (only for games with has_bonus=True).",
        ),
        sa.Column(
            "source",
            sa.String(50),
            nullable=True,
            comment="How this draw was obtained: 'scraper', 'csv', 'manual'.",
        ),
        sa.Column(
            "import_log_id",
            sa.Integer(),
            sa.ForeignKey("import_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_type", "draw_date", name="uq_draws_game_date"),
    )
    op.create_index("ix_draws_game_type", "draws", ["game_type"])
    op.create_index("ix_draws_draw_date", "draws", ["draw_date"])

    # --- analysis_snapshots ---
    op.create_table(
        "analysis_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_type", sa.String(20), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column(
            "draw_count",
            sa.Integer(),
            nullable=False,
            comment="Number of draws included in the analysis.",
        ),
        sa.Column("frequency_data", postgresql.JSONB(), nullable=False),
        sa.Column("recency_data", postgresql.JSONB(), nullable=False),
        sa.Column("hot_cold_data", postgresql.JSONB(), nullable=False),
        sa.Column("pair_data", postgresql.JSONB(), nullable=False),
        sa.Column("triplet_data", postgresql.JSONB(), nullable=False),
        sa.Column("distribution_data", postgresql.JSONB(), nullable=False),
        sa.Column("entropy_score", sa.Float(), nullable=False),
        sa.Column(
            "config_hash",
            sa.String(64),
            nullable=False,
            comment="Hash of the analytics config used, for cache invalidation.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_snapshots_game_type", "analysis_snapshots", ["game_type"])
    op.create_index("ix_analysis_snapshots_snapshot_date", "analysis_snapshots", ["snapshot_date"])

    # --- generated_combinations ---
    op.create_table(
        "generated_combinations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_type", sa.String(20), nullable=False),
        sa.Column(
            "batch_id",
            sa.String(36),
            nullable=False,
            comment="UUID grouping all combinations from a single generation run.",
        ),
        sa.Column("generation_date", sa.Date(), nullable=False),
        sa.Column(
            "numbers",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            comment="The generated combination (sorted).",
        ),
        sa.Column(
            "rank",
            sa.Integer(),
            nullable=False,
            comment="1-based rank within the batch.",
        ),
        sa.Column(
            "ensemble_score",
            sa.Float(),
            nullable=False,
            comment="Weighted ensemble score used for ranking.",
        ),
        sa.Column(
            "feature_scores",
            postgresql.JSONB(),
            nullable=False,
            comment="Individual feature scores keyed by weight name.",
        ),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column(
            "snapshot_id",
            sa.Integer(),
            sa.ForeignKey("analysis_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generated_combinations_game_type", "generated_combinations", ["game_type"])
    op.create_index("ix_generated_combinations_batch_id", "generated_combinations", ["batch_id"])

    # --- backtest_results ---
    op.create_table(
        "backtest_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_type", sa.String(20), nullable=False),
        sa.Column(
            "run_id",
            sa.String(36),
            nullable=False,
            unique=True,
            comment="UUID identifying this backtest run.",
        ),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column(
            "train_window_size",
            sa.Integer(),
            nullable=False,
            comment="Number of draws used for training in each step.",
        ),
        sa.Column(
            "test_window_size",
            sa.Integer(),
            nullable=False,
            comment="Number of draws used for testing in each step.",
        ),
        sa.Column("hit_rates", postgresql.JSONB(), nullable=False),
        sa.Column("number_hit_rate", sa.Float(), nullable=False),
        sa.Column("feature_stability", postgresql.JSONB(), nullable=False),
        sa.Column("steps_detail", postgresql.JSONB(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backtest_results_game_type", "backtest_results", ["game_type"])


def downgrade() -> None:
    op.drop_table("backtest_results")
    op.drop_table("generated_combinations")
    op.drop_table("analysis_snapshots")
    op.drop_table("draws")
    op.drop_table("import_logs")
