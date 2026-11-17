import os
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv, set_key

ROOT_DIR = Path(__file__).resolve().parents[2]
_env_file = ROOT_DIR / ".env"
load_dotenv(_env_file)

STATIC_DIR = ROOT_DIR / "static"
DATA_DIR = Path(os.getenv("PANEL_DATA_DIR", str(ROOT_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'veyon_panel.sqlite3').as_posix()}")
VEYON_API_URL = os.getenv("VEYON_API_URL", "http://192.168.120.155:11080").rstrip("/")
VEYON_AUTH_METHOD = os.getenv("VEYON_AUTH_METHOD", "0c69b301-81b4-42d6-8fae-128cdd113314")
PANEL_ENCRYPTION_KEY = os.getenv("PANEL_ENCRYPTION_KEY")
if not PANEL_ENCRYPTION_KEY:
    PANEL_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")
    set_key(str(_env_file), "PANEL_ENCRYPTION_KEY", PANEL_ENCRYPTION_KEY)
