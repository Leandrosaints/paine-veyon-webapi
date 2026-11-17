import secrets
from typing import Any, NoReturn

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from veyon_panel.core.config import VEYON_API_URL, VEYON_AUTH_METHOD
from veyon_panel.core.secrets import decrypt_credentials
from veyon_panel.db.session import get_db
from veyon_panel.models.resources import Computer
from veyon_panel.services.veyon import api_base_url, host_path, payload, request

router = APIRouter(tags=["Veyon WebAPI"])


class AuthRequest(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    method: str = VEYON_AUTH_METHOD
    credentials: dict[str, Any]
    base_url: str | None = None


class FeatureRequest(BaseModel):
    active: bool
    arguments: dict[str, Any] | None = None


class Connection:
    def __init__(self, base_url: str, host: str, uid: str, valid_until: Any = None):
        self.base_url, self.host, self.uid, self.valid_until = base_url, host, uid, valid_until


connections: dict[str, Connection] = {}
EXPIRED_SESSION_MESSAGE = "A sessão do Veyon expirou. Reconecte o computador para continuar."


def connection_or_401(connection_id: str) -> Connection:
    conn = connections.get(connection_id)
    if not conn:
        raise HTTPException(401, EXPIRED_SESSION_MESSAGE)
    return conn


def raise_connection_error(connection_id: str, status_code: int, detail: Any) -> NoReturn:
    if status_code == 401:
        connections.pop(connection_id, None)
        raise HTTPException(401, EXPIRED_SESSION_MESSAGE)
    raise HTTPException(status_code, detail)


async def connection_request(connection_id: str, conn: Connection, method: str, path: str,
                             **kwargs: Any) -> httpx.Response:
    try:
        return await request(conn.base_url, method, path, uid=conn.uid, **kwargs)
    except HTTPException as exc:
        raise_connection_error(connection_id, exc.status_code, exc.detail)


@router.get("/authentication/{host}/methods")
async def authentication_methods(host: str, base_url: str | None = None):
    return payload(await request(api_base_url(base_url, VEYON_API_URL), "GET", host_path(host), timeout=4))


@router.post("/connections")
async def authenticate(body: AuthRequest):
    return await create_connection(body.host, body.method, body.credentials, body.base_url)


async def create_connection(host: str, method: str, credentials: dict[str, Any], base_url: str | None):
    base = api_base_url(base_url, VEYON_API_URL)
    data = payload(await request(base, "POST", host_path(host),
                                 json={"method": method, "credentials": credentials}))
    uid = data.get("connection-uid") if isinstance(data, dict) else None
    if not uid:
        raise HTTPException(502, {"message": "Resposta sem connection-uid", "response": data})
    connection_id = secrets.token_urlsafe(24)
    connections[connection_id] = Connection(base, host, uid, data.get("validUntil"))
    return {"connection_id": connection_id, "host": host,
            "validUntil": data.get("validUntil"), "connection-uid": uid}


@router.post("/connections/computer/{computer_id}")
async def authenticate_saved_computer(computer_id: int, db: Session = Depends(get_db)):
    computer = db.get(Computer, computer_id)
    if computer is None:
        raise HTTPException(404, "Computador não encontrado.")
    if not computer.auth_method or not computer.credentials_encrypted:
        raise HTTPException(409, "Este computador não tem credenciais salvas.")
    credentials = decrypt_credentials(computer.credentials_encrypted)
    return await create_connection(computer.host, computer.auth_method, credentials, computer.api_url)


@router.delete("/connections/{connection_id}")
async def close_connection(connection_id: str):
    conn = connection_or_401(connection_id)
    try:
        result = payload(await connection_request(connection_id, conn, "DELETE", host_path(conn.host)))
    finally:
        connections.pop(connection_id, None)
    return result


@router.get("/connections")
async def list_connections():
    return [{"connection_id": key, "host": c.host, "validUntil": c.valid_until}
            for key, c in connections.items()]


@router.get("/connections/{connection_id}/framebuffer")
async def framebuffer(connection_id: str,
                      format: str = Query("jpeg", regex="^(png|jpeg)$"),
                      compression: int | None = Query(None, ge=1, le=9),
                      quality: int | None = Query(75, ge=1, le=100)):
    conn = connection_or_401(connection_id)
    params = {k: v for k, v in {"format": format, "compression": compression, "quality": quality}.items()
              if v is not None}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{conn.base_url}/api/v1/framebuffer",
                                        headers={"Connection-Uid": conn.uid}, params=params)
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Erro ao obter framebuffer: {exc}") from exc
    if response.is_error:
        try: detail = response.json()
        except ValueError: detail = response.text
        raise_connection_error(connection_id, response.status_code, detail)
    return Response(response.content, media_type=response.headers.get("content-type", "image/jpeg"))


@router.get("/connections/{connection_id}/features")
async def features(connection_id: str):
    c = connection_or_401(connection_id)
    return payload(await connection_request(connection_id, c, "GET", "feature"))


@router.get("/connections/{connection_id}/features/{feature_uid}")
async def feature_status(connection_id: str, feature_uid: str):
    c = connection_or_401(connection_id)
    return payload(await connection_request(connection_id, c, "GET", f"feature/{feature_uid}"))


@router.put("/connections/{connection_id}/features/{feature_uid}")
async def set_feature(connection_id: str, feature_uid: str, body: FeatureRequest):
    c = connection_or_401(connection_id)
    data: dict[str, Any] = {"active": body.active}
    if body.arguments is not None:
        data["arguments"] = body.arguments
    return payload(await connection_request(connection_id, c, "PUT", f"feature/{feature_uid}",
                                            json=data))


@router.get("/connections/{connection_id}/user")
async def user_info(connection_id: str):
    c = connection_or_401(connection_id)
    return payload(await connection_request(connection_id, c, "GET", "user"))


@router.get("/connections/{connection_id}/session")
async def session_info(connection_id: str):
    c = connection_or_401(connection_id)
    return payload(await connection_request(connection_id, c, "GET", "session"))
