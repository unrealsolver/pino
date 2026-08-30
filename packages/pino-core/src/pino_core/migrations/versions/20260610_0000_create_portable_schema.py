"""Create the portable storage schema.

Revision ID: 20260610_0000
Revises:
Create Date: 2026-06-10 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260610_0000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "records" not in existing:
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
    if "active_memory" not in existing:
        op.create_table(
            "active_memory",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
        )
    if "chat_messages" not in existing:
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
        )
    if "refinements" not in existing:
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
    if "source_cursors" not in existing:
        op.create_table(
            "source_cursors",
            sa.Column("source", sa.String(), primary_key=True),
            sa.Column("cursor", sa.String(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in (
        "source_cursors",
        "refinements",
        "chat_messages",
        "active_memory",
        "records",
    ):
        if table_name in existing:
            op.drop_table(table_name)
