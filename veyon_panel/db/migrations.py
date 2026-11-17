from alembic import command
from alembic.config import Config

from veyon_panel.core.config import DATABASE_URL, ROOT_DIR


def upgrade_database() -> None:
    config = Config(str(ROOT_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")
