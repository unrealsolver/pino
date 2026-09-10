"""Add ordered cached image references to records."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("records", sa.Column("images", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("records", "images")
