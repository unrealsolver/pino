"""Add refinement schedule.

Revision ID: 20260611_0154
Revises:
Create Date: 2026-06-11 01:54:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260611_0154"
down_revision = None
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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "refinements" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("refinements")}
    if "schedule" in columns:
        with op.batch_alter_table("refinements") as batch_op:
            batch_op.drop_column("schedule")
