"""Add remote script repository."""
from alembic import op
import sqlalchemy as sa

revision = "0004_script_repository"
down_revision = "0003_software_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repositorio_scripts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(160), nullable=False),
        sa.Column("nome_arquivo", sa.String(255), nullable=False),
        sa.Column("data_upload", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("tipo", sa.String(8), nullable=False),
    )
    op.create_index("ix_repositorio_scripts_nome", "repositorio_scripts", ["nome"])


def downgrade() -> None:
    op.drop_index("ix_repositorio_scripts_nome", table_name="repositorio_scripts")
    op.drop_table("repositorio_scripts")
