import json

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from veyon_panel.core.config import PANEL_ENCRYPTION_KEY

_cipher = Fernet(PANEL_ENCRYPTION_KEY.encode("ascii"))


def encrypt_credentials(value: dict) -> str:
    return _cipher.encrypt(json.dumps(value).encode("utf-8")).decode("ascii")


def decrypt_credentials(value: str) -> dict:
    try:
        return json.loads(_cipher.decrypt(value.encode("ascii")).decode("utf-8"))
    except (InvalidToken, ValueError) as exc:
        raise HTTPException(500, "Não foi possível descriptografar as credenciais salvas. Confira PANEL_ENCRYPTION_KEY no .env.") from exc
