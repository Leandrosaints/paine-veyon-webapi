"""Create local environments and computers."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_resources"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "environments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("icon", sa.String(32), nullable=False, server_default="room"),
        sa.Column("color", sa.String(16), nullable=False, server_default="#4d78d0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_environments_name", "environments", ["name"], unique=True)
    op.create_table(
        "computers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("host", sa.String(253), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=True),
        sa.Column("api_url", sa.String(500), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_computers_name", "computers", ["name"])
    op.create_index("ix_computers_host", "computers", ["host"], unique=True)
    op.create_index("ix_computers_environment_id", "computers", ["environment_id"])


def downgrade() -> None:
    op.drop_index("ix_computers_environment_id", table_name="computers")
    op.drop_index("ix_computers_host", table_name="computers")
    op.drop_index("ix_computers_name", table_name="computers")
    op.drop_table("computers")
    op.drop_index("ix_environments_name", table_name="environments")
    op.drop_table("environments")
