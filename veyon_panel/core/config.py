import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv, set_key

ROOT_DIR = Path(__file__).resolve().parents[2]
_env_file = ROOT_DIR / ".env"
load_dotenv(_env_file)

STATIC_DIR = ROOT_DIR / "static"
DATA_DIR = Path(os.getenv("PANEL_DATA_DIR", str(ROOT_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR = Path(os.getenv("PANEL_UPLOADS_DIR", str(DATA_DIR / "uploads")))
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
PANEL_PUBLIC_BASE_URL = os.getenv("PANEL_PUBLIC_BASE_URL", "").strip().rstrip("/")
PANEL_DEV_MODE = os.getenv("PANEL_DEV_MODE", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'veyon_panel.sqlite3').as_posix()}")
VEYON_API_URL = os.getenv("VEYON_API_URL", "http://localhost:11080").rstrip("/")
VEYON_AUTH_METHOD = os.getenv("VEYON_AUTH_METHOD", "0c69b301-81b4-42d6-8fae-128cdd113314")
LOCAL_NETWORK_CIDRS = tuple(
    network.strip() for network in os.getenv("LOCAL_NETWORK_CIDRS", "").split(",") if network.strip()
)
SCRIPT_EXECUTION_TIMEOUT_SECONDS = max(
    10.0, float(os.getenv("SCRIPT_EXECUTION_TIMEOUT_SECONDS", "300"))
)
PANEL_API_KEY = os.getenv("PANEL_API_KEY")
if not PANEL_API_KEY:
    PANEL_API_KEY = secrets.token_urlsafe(32)
    os.environ["PANEL_API_KEY"] = PANEL_API_KEY
    set_key(str(_env_file), "PANEL_API_KEY", PANEL_API_KEY)
PANEL_ENCRYPTION_KEY = os.getenv("PANEL_ENCRYPTION_KEY")
if not PANEL_ENCRYPTION_KEY:
    PANEL_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")
    set_key(str(_env_file), "PANEL_ENCRYPTION_KEY", PANEL_ENCRYPTION_KEY)
