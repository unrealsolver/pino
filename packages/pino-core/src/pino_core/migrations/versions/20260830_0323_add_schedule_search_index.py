"""Add the PostgreSQL schedule search index.

Revision ID: 20260830_0323
Revises: 20260814_2344
Create Date: 2026-08-30 03:23:00.000000
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from pino_core.schedules import compile_weekly_pattern, normalize_schedule

revision = "20260830_0323"
down_revision = "20260814_2344"
branch_labels = None
depends_on = None

_TABLE = "refinement_schedule_index"
_INDEX = "ix_refinement_schedule_index_weekly_pattern_gist"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.create_table(
        _TABLE,
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
        _INDEX,
        _TABLE,
        ["weekly_pattern"],
        unique=False,
        postgresql_using="gist",
    )
    if not context.is_offline_mode():
        _backfill(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_table(_TABLE)


def _backfill(bind: sa.Connection) -> None:
    rows = bind.execute(
        sa.text(
            """
            SELECT id, schedule, relevant_from, relevant_to
            FROM refinements
            WHERE schedule IS NOT NULL
            """
        )
    ).mappings()
    insert_index = sa.text(
        """
        INSERT INTO refinement_schedule_index
            (refinement_id, timezone, weekly_pattern)
        VALUES
            (:refinement_id, :timezone, CAST(:weekly_pattern AS int4multirange))
        """
    )
    for row in rows:
        schedule = normalize_schedule(
            row["schedule"],
            relevant_from=row["relevant_from"],
            relevant_to=row["relevant_to"],
        )
        if schedule is None:
            continue
        pattern = compile_weekly_pattern(schedule)
        bind.execute(
            insert_index,
            {
                "refinement_id": row["id"],
                "timezone": pattern.timezone,
                "weekly_pattern": pattern.as_postgresql_multirange(),
            },
        )
