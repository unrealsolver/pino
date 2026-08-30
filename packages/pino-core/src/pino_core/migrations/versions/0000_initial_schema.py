"""Create the initial storage schema.

Revision ID: 0000
Revises:
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0000"
down_revision = None
branch_labels = None
depends_on = None

_SCHEDULE_INDEX_TABLE = "refinement_schedule_index"
_SCHEDULE_INDEX = "ix_refinement_schedule_index_weekly_pattern_gist"


def upgrade() -> None:
    op.create_table(
        "records",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.UniqueConstraint("fingerprint", name="uq_records_fingerprint"),
    )
    op.create_table(
        "active_memory",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "refinements",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("record_id", sa.String(), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("taxonomy_version", sa.Integer(), nullable=False),
        sa.Column("content_kind", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("relevant_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("relevant_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schedule", sa.JSON(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("category_scores", sa.JSON(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("refiner", sa.String(), nullable=False),
        sa.Column("refined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("debug", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "record_id",
            "item_index",
            name="uq_refinements_record_item",
        ),
    )
    op.create_table(
        "source_cursors",
        sa.Column("source", sa.String(), primary_key=True),
        sa.Column("cursor", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
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

    if op.get_bind().dialect.name == "postgresql":
        op.create_table(
            _SCHEDULE_INDEX_TABLE,
            sa.Column(
                "refinement_id",
                sa.String(),
                sa.ForeignKey("refinements.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("timezone", sa.String(), nullable=False),
            sa.Column("weekly_pattern", postgresql.INT4MULTIRANGE(), nullable=False),
        )
        op.create_index(
            _SCHEDULE_INDEX,
            _SCHEDULE_INDEX_TABLE,
            ["weekly_pattern"],
            unique=False,
            postgresql_using="gist",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_table(_SCHEDULE_INDEX_TABLE)
    op.drop_table("llm_usage_events")
    op.drop_table("source_cursors")
    op.drop_table("refinements")
    op.drop_table("chat_messages")
    op.drop_table("active_memory")
    op.drop_table("records")
