"""Ensure refinement schedule column.

Revision ID: 20260611_0241
Revises: 20260611_0154
Create Date: 2026-06-11 02:41:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260611_0241"
down_revision = "20260611_0154"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "refinements" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("refinements")}
    if "schedule" not in columns:
        op.add_column("refinements", sa.Column("schedule", sa.JSON(), nullable=True))


def downgrade() -> None:
    pass
