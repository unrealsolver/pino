"""Add nullable city assignment to refinements."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_INDEX = "ix_refinements_city_id"


def upgrade() -> None:
    op.add_column("refinements", sa.Column("city_id", sa.String(), nullable=True))
    op.create_index(_INDEX, "refinements", ["city_id"], unique=False)


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="refinements")
    op.drop_column("refinements", "city_id")
