"""Add software deployment catalog."""
from alembic import op
import sqlalchemy as sa

revision = "0003_software_catalog"
down_revision = "0002_encrypted_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "softwares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("url_local", sa.String(2000), nullable=False),
        sa.Column("url_publica", sa.String(2000), nullable=False),
        sa.Column("argumentos_instalacao", sa.String(1000), nullable=False, server_default="/quiet /norestart"),
    )
    op.create_index("ix_softwares_nome", "softwares", ["nome"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_softwares_nome", table_name="softwares")
    op.drop_table("softwares")
