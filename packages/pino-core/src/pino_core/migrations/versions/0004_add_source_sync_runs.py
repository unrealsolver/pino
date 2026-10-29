"""Add durable source sync attempt records.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_LATEST_ATTEMPT_INDEX = "ix_source_sync_runs_source_started_at"
_LATEST_SUCCESS_INDEX = "ix_source_sync_runs_source_outcome_completed_at"


def upgrade() -> None:
    op.create_table(
        "source_sync_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_stage", sa.String(), nullable=True),
        sa.CheckConstraint(
            "(completed_at IS NULL AND outcome IS NULL) OR "
            "(completed_at IS NOT NULL AND outcome IS NOT NULL "
            "AND outcome IN ('success', 'failure') AND completed_at >= started_at)",
            name="ck_source_sync_runs_completion",
        ),
        sa.CheckConstraint(
            "fetched_count >= 0 AND inserted_count >= 0 AND duplicate_count >= 0 "
            "AND inserted_count + duplicate_count <= fetched_count",
            name="ck_source_sync_runs_counts",
        ),
        sa.CheckConstraint(
            "failure_stage IS NULL OR (outcome IS NOT NULL AND outcome = 'failure')",
            name="ck_source_sync_runs_failure_stage",
        ),
    )
    op.create_index(
        _LATEST_ATTEMPT_INDEX,
        "source_sync_runs",
        ["source", "started_at", "id"],
        unique=False,
    )
    op.create_index(
        _LATEST_SUCCESS_INDEX,
        "source_sync_runs",
        ["source", "outcome", "completed_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(_LATEST_SUCCESS_INDEX, table_name="source_sync_runs")
    op.drop_index(_LATEST_ATTEMPT_INDEX, table_name="source_sync_runs")
    op.drop_table("source_sync_runs")
