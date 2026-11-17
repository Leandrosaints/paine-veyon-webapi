import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT_DIR / "static"
DATA_DIR = Path(os.getenv("PANEL_DATA_DIR", str(ROOT_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'veyon_panel.sqlite3').as_posix()}")
VEYON_API_URL = os.getenv("VEYON_API_URL", "http://127.0.0.1:11080").rstrip("/")
VEYON_AUTH_METHOD = os.getenv("VEYON_AUTH_METHOD", "0c69b301-81b4-42d6-8fae-128cdd113314")
