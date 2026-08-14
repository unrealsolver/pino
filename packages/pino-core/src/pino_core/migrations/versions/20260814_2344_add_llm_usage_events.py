"""Add LLM usage events table.

Revision ID: 20260814_2344
Revises: 20260611_0241
Create Date: 2026-08-14 23:44:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260814_2344"
down_revision = "20260611_0241"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "llm_usage_events" in inspector.get_table_names():
        return
    op.create_table(
        "llm_usage_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_usage_events")
