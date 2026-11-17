"""Store encrypted authentication credentials per computer."""
from alembic import op
import sqlalchemy as sa

revision = "0002_encrypted_credentials"
down_revision = "0001_initial_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("computers", sa.Column("auth_method", sa.String(64), nullable=True))
    op.add_column("computers", sa.Column("credentials_encrypted", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("computers", "credentials_encrypted")
    op.drop_column("computers", "auth_method")
