import asyncio
import logging
import secrets
import time
from typing import Any, NoReturn
from urllib.parse import unquote

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
logger = logging.getLogger("veyon.audit")
FRAMEBUFFER_CACHE_TTL = 2.0
FRAMEBUFFER_REQUEST_TIMEOUT = 2.0
framebuffer_cache: dict[tuple[str, str, int | None, int | None], tuple[float, bytes, str]] = {}
framebuffer_locks: dict[tuple[str, str, int | None, int | None], asyncio.Lock] = {}


def framebuffer_not_ready(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    error = body.get("error", body) if isinstance(body, dict) else {}
    code = error.get("code") if isinstance(error, dict) else None
    message = error.get("message", "") if isinstance(error, dict) else ""
    return str(code) == "10" or "framebuffer not yet available" in str(message).lower()


class AuthRequest(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    method: str = VEYON_AUTH_METHOD
    credentials: dict[str, Any]
    base_url: str | None = None


class BulkHostsRequest(BaseModel):
    ips: list[str] = Field(min_length=1, max_length=500)


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
    cache_key = (connection_id, format, compression, quality)
    lock = framebuffer_locks.setdefault(cache_key, asyncio.Lock())

    async def capture():
        acquired = False
        try:
            await lock.acquire()
            acquired = True
            cached = framebuffer_cache.get(cache_key)
            if cached and cached[0] > time.monotonic():
                conn.last_used = time.monotonic()
                return Response(cached[1], media_type=cached[2])
            try:
                response = await request(
                    conn.base_url, "GET", "framebuffer", uid=conn.uid,
                    params=params, timeout=FRAMEBUFFER_REQUEST_TIMEOUT,
                )
            except HTTPException as exc:
                if exc.status_code == 401:
                    raise_connection_error(connection_id, exc.status_code, exc.detail)
                logger.info("Framebuffer unavailable | Host: %s | HTTP %s", conn.host, exc.status_code)
                return Response(status_code=204)
            if framebuffer_not_ready(response) or response.is_error or not response.content:
                logger.info("Framebuffer not ready | Host: %s", conn.host)
                return Response(status_code=204)
            content_type = response.headers.get("content-type", "image/jpeg")
            frame = response.content
            conn.last_used = time.monotonic()
            framebuffer_cache[cache_key] = (time.monotonic() + FRAMEBUFFER_CACHE_TTL,
                                            frame, content_type)
            return Response(frame, media_type=content_type)
        finally:
            if acquired:
                lock.release()

    try:
        return await asyncio.wait_for(capture(), timeout=FRAMEBUFFER_REQUEST_TIMEOUT)
    except asyncio.TimeoutError:
        logger.info("Framebuffer timed out | Host: %s", conn.host)
        return Response(status_code=204)


@router.post("/mass-logoff")
async def mass_logoff(body: BulkHostsRequest):
    semaphore = asyncio.Semaphore(5)

    async def logoff(ip: str):
        async with semaphore:
            try:
                connection_id = next((key for key, conn in connections.items() if conn.host == ip), None)
                if connection_id is None:
                    return {"ip": ip, "status": "error", "detail": "No active authenticated session."}
                conn = connection_or_401(connection_id)
                result = payload(await connection_request(
                    connection_id, conn, "PUT", "feature/da9ca56a-b2ad-4fff-8f8a-929b2927b442",
                    json={"active": True, "arguments": {"applications": ["shutdown.exe /l /f"]}},
                ))
                logger.info("A????o: logoff em massa | Host: %s | Sucesso", ip)
                return {"ip": ip, "status": "accepted", "result": result}
            except HTTPException as exc:
                logger.warning("A????o: logoff em massa | Host: %s | Erro %s", ip, exc.status_code)
                return {"ip": ip, "status": "error", "detail": exc.detail, "http_status": exc.status_code}
            except Exception as exc:
                logger.exception("Falha no logoff remoto para %s", ip)
                return {"ip": ip, "status": "error", "detail": str(exc)}

    return {"results": await asyncio.gather(*(logoff(ip) for ip in body.ips))}


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
    result = payload(await connection_request(connection_id, c, "PUT", f"feature/{feature_uid}",
                                               json=data))
    if feature_uid == "ccb535a2-1d24-4cc1-a709-8b47d2b2ac79":
        logger.info("Ação: %s | Host: %s | Sucesso",
                    "bloquear computador" if body.active else "desbloquear computador", c.host)
    return result


@router.get("/connections/{connection_id}/user")
async def user_info(connection_id: str):
    c = connection_or_401(connection_id)
    return payload(await connection_request(connection_id, c, "GET", "user"))


@router.get("/connections/{connection_id}/session")
async def session_info(connection_id: str):
    c = connection_or_401(connection_id)
    return payload(await connection_request(connection_id, c, "GET", "session"))
