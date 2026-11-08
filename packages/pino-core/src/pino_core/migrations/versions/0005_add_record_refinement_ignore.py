"""Add the ignored-refinement disposition to records."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "records",
        sa.Column("refinement_ignored_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "records",
        sa.Column("refinement_ignored_reason", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("records", "refinement_ignored_reason")
    op.drop_column("records", "refinement_ignored_at")
