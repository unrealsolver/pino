"""Add canonical record publication timestamps.

Revision ID: 0001
Revises: 0000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = "0000"
branch_labels = None
depends_on = None

_INDEX = "ix_records_published_at"


def upgrade() -> None:
    op.add_column(
        "records",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            UPDATE records
            SET published_at = (payload ->> 'posted_at_utc')::timestamptz
            WHERE payload ->> 'posted_at_utc' IS NOT NULL
            """
        )
    elif dialect == "sqlite":
        op.execute(
            """
            UPDATE records
            SET published_at = json_extract(payload, '$.posted_at_utc')
            WHERE json_extract(payload, '$.posted_at_utc') IS NOT NULL
            """
        )
    op.create_index(_INDEX, "records", ["published_at"], unique=False)


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="records")
    op.drop_column("records", "published_at")
