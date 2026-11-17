import asyncio
import logging
import secrets
import time
from typing import Any, NoReturn
from urllib.parse import unquote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from veyon_panel.core.config import PANEL_API_KEY, VEYON_API_URL, VEYON_AUTH_METHOD
from veyon_panel.core.secrets import decrypt_credentials
from veyon_panel.db.session import get_db
from veyon_panel.models.resources import Computer
from veyon_panel.services.veyon import api_base_url, host_path, payload, request

router = APIRouter(tags=["Veyon WebAPI"])
logger = logging.getLogger("veyon.audit")
FRAMEBUFFER_CACHE_TTL = 2.0
OFFLINE_PLACEHOLDER = """<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360"><rect width="640" height="360" fill="#171b25"/><circle cx="320" cy="135" r="35" fill="none" stroke="#ff7484" stroke-width="8"/><path d="M296 111l48 48m0-48-48 48" stroke="#ff7484" stroke-width="8" stroke-linecap="round"/><text x="320" y="220" fill="#e8ebf2" font-family="sans-serif" font-size="26" text-anchor="middle">Máquina Offline</text><text x="320" y="255" fill="#929bad" font-family="sans-serif" font-size="15" text-anchor="middle">Não foi possível obter a captura da tela</text></svg>""".encode("utf-8")
framebuffer_cache: dict[tuple[str, str, int | None, int | None], tuple[float, bytes, str]] = {}
framebuffer_locks: dict[tuple[str, str, int | None, int | None], asyncio.Lock] = {}


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
        self.last_used = time.monotonic()


connections: dict[str, Connection] = {}
EXPIRED_SESSION_MESSAGE = "A sessão do Veyon expirou. Reconecte o computador para continuar."


def connection_or_401(connection_id: str) -> Connection:
    conn = connections.get(connection_id)
    if not conn:
        raise HTTPException(401, EXPIRED_SESSION_MESSAGE)
    conn.last_used = time.monotonic()
    return conn


def clear_connection_cache(connection_id: str) -> None:
    for key in [key for key in framebuffer_cache if key[0] == connection_id]:
        framebuffer_cache.pop(key, None)
    for key in [key for key in framebuffer_locks if key[0] == connection_id]:
        framebuffer_locks.pop(key, None)


def raise_connection_error(connection_id: str, status_code: int, detail: Any) -> NoReturn:
    if status_code == 401:
        connections.pop(connection_id, None)
        clear_connection_cache(connection_id)
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
    return payload(await request(api_base_url(base_url, VEYON_API_URL), "GET", host_path(host), timeout=3))


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
        clear_connection_cache(connection_id)
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
    now = time.monotonic()
    for expired_key, cached_frame in list(framebuffer_cache.items()):
        if cached_frame[0] <= now:
            framebuffer_cache.pop(expired_key, None)
            lock = framebuffer_locks.get(expired_key)
            if lock is not None and not lock.locked():
                framebuffer_locks.pop(expired_key, None)
    cache_key = (connection_id, format, compression, quality)
    lock = framebuffer_locks.setdefault(cache_key, asyncio.Lock())
    async with lock:
        cached = framebuffer_cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            conn.last_used = time.monotonic()
            return Response(cached[1], media_type=cached[2])
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"{conn.base_url}/api/v1/framebuffer",
                                            headers={"Connection-Uid": conn.uid}, params=params)
        except httpx.RequestError as exc:
            logger.info("Ação: framebuffer | Host: %s | Erro", conn.host)
            content, media_type = OFFLINE_PLACEHOLDER, "image/svg+xml"
        else:
            if response.status_code == 401:
                try:
                    detail = response.json()
                except ValueError:
                    detail = response.text
                raise_connection_error(connection_id, response.status_code, detail)
            if response.is_error:
                logger.info("Ação: framebuffer | Host: %s | Erro", conn.host)
                content, media_type = OFFLINE_PLACEHOLDER, "image/svg+xml"
            else:
                content = response.content
                media_type = response.headers.get("content-type", "image/jpeg")
                logger.info("Ação: framebuffer | Host: %s | Sucesso", conn.host)
        conn.last_used = time.monotonic()
        framebuffer_cache[cache_key] = (
            time.monotonic() + FRAMEBUFFER_CACHE_TTL, content, media_type
        )
        return Response(content, media_type=media_type)


@router.websocket("/connections/{connection_id}/framebuffer/live")
async def live_framebuffer(websocket: WebSocket, connection_id: str):
    offered_protocols = websocket.headers.get("sec-websocket-protocol", "").split(",")
    key_prefix = "veyon-api-key."
    supplied_key = next(
        (protocol.strip()[len(key_prefix):] for protocol in offered_protocols
         if protocol.strip().startswith(key_prefix)),
        "",
    )
    if not secrets.compare_digest(supplied_key.encode("utf-8"), PANEL_API_KEY.encode("utf-8")):
        logger.info("Ação: websocket framebuffer | Host: %s | Erro", websocket.client.host if websocket.client else "desconhecido")
        await websocket.close(code=4403, reason="API Key inválida.")
        return
    await websocket.accept(subprotocol="veyon-live")
    await websocket.send_json({"type": "ready", "status": 200})
    conn = connections.get(connection_id)
    if conn is None:
        await websocket.send_json(
            {"type": "error", "status": 401, "message": EXPIRED_SESSION_MESSAGE}
        )
        await websocket.close(code=4401, reason=EXPIRED_SESSION_MESSAGE)
        return

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            while connections.get(connection_id) is conn:
                conn.last_used = time.monotonic()
                try:
                    response = await client.get(
                        f"{conn.base_url}/api/v1/framebuffer",
                        headers={"Connection-Uid": conn.uid},
                        params={"format": "jpeg", "quality": 65},
                    )
                except httpx.RequestError as exc:
                    await websocket.send_json(
                        {"type": "error", "message": f"Erro ao obter framebuffer: {exc}"}
                    )
                    await websocket.close(code=1011, reason="Erro ao obter framebuffer")
                    return

                if response.is_error:
                    try:
                        detail = response.json()
                    except ValueError:
                        detail = response.text or response.reason_phrase
                    try:
                        raise_connection_error(connection_id, response.status_code, detail)
                    except HTTPException as exc:
                        message = EXPIRED_SESSION_MESSAGE if exc.status_code == 401 else str(exc.detail)
                        await websocket.send_json(
                            {"type": "error", "status": exc.status_code, "message": message}
                        )
                        await websocket.close(
                            code=4401 if exc.status_code == 401 else 1011,
                            reason=EXPIRED_SESSION_MESSAGE if exc.status_code == 401 else "Erro ao obter framebuffer",
                        )
                        return

                await websocket.send_bytes(response.content)
                await asyncio.sleep(0.25)
            await websocket.send_json(
                {"type": "error", "status": 401, "message": EXPIRED_SESSION_MESSAGE}
            )
            await websocket.close(code=4401, reason=EXPIRED_SESSION_MESSAGE)
    except WebSocketDisconnect:
        logger.info("Ação: websocket framebuffer | Host: %s | Sucesso", conn.host if conn else "desconhecido")
        return


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
