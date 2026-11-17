"""Local Veyon WebAPI dashboard and same-origin proxy."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DEFAULT_BASE_URL = os.getenv("VEYON_API_URL", "http://192.168.0.5:11080").rstrip("/")
DEFAULT_AUTH_METHOD = os.getenv(
    "VEYON_AUTH_METHOD", "0c69b301-81b4-42d6-8fae-128cdd113314"
)

app = FastAPI(
    title="Veyon Control Panel",
    description="Painel local e proxy para todas as operações da Veyon WebAPI v1.",
    version="1.0.0",
)


class AuthRequest(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    method: str = DEFAULT_AUTH_METHOD
    credentials: dict[str, Any]
    base_url: str | None = None


class FeatureRequest(BaseModel):
    active: bool
    arguments: dict[str, Any] | None = None


class Connection:
    def __init__(self, base_url: str, host: str, uid: str, valid_until: Any = None):
        self.base_url, self.host, self.uid, self.valid_until = base_url, host, uid, valid_until


connections: dict[str, Connection] = {}


def get_base_url(value: str | None = None) -> str:
    url = (value or DEFAULT_BASE_URL).strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "VEYON_API_URL precisa começar com http:// ou https://")
    return url


def connection_or_401(connection_id: str) -> Connection:
    conn = connections.get(connection_id)
    if not conn:
        raise HTTPException(401, "Conexão inexistente ou expirada; autentique novamente.")
    return conn


async def request(base_url: str, method: str, path: str, *, uid: str | None = None,
                  json: Any = None, params: dict[str, Any] | None = None) -> httpx.Response:
    headers = {"Connection-Uid": uid} if uid else {}
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.request(method, f"{base_url}/api/v1/{path.lstrip('/')}",
                                            headers=headers, json=json, params=params)
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Não foi possível conectar à WebAPI do Veyon: {exc}") from exc
    if response.is_error:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text or response.reason_phrase
        raise HTTPException(response.status_code, detail)
    return response


def payload(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return response.text


@app.get("/api/config")
async def config():
    return {"base_url": DEFAULT_BASE_URL, "auth_method": DEFAULT_AUTH_METHOD}


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "veyon-control-panel", "connections": len(connections)}


@app.get("/api/authentication/{host}/methods")
async def authentication_methods(host: str, base_url: str | None = None):
    return payload(await request(get_base_url(base_url), "GET", f"authentication/{quote(host, safe='')}"))


@app.post("/api/connections")
async def authenticate(body: AuthRequest):
    base = get_base_url(body.base_url)
    data = payload(await request(base, "POST", f"authentication/{quote(body.host, safe='')}",
                                 json={"method": body.method, "credentials": body.credentials}))
    uid = data.get("connection-uid") if isinstance(data, dict) else None
    if not uid:
        raise HTTPException(502, {"message": "Resposta sem connection-uid", "response": data})
    import secrets
    connection_id = secrets.token_urlsafe(24)
    connections[connection_id] = Connection(base, body.host, uid,
                                               data.get("validUntil") if isinstance(data, dict) else None)
    return {"connection_id": connection_id, "host": body.host,
            "validUntil": data.get("validUntil"), "connection-uid": uid}


@app.delete("/api/connections/{connection_id}")
async def close_connection(connection_id: str):
    conn = connection_or_401(connection_id)
    try:
        response = await request(conn.base_url, "DELETE",
                                 f"authentication/{quote(conn.host, safe='')}", uid=conn.uid)
        result = payload(response)
    finally:
        connections.pop(connection_id, None)
    return result


@app.get("/api/connections")
async def list_connections():
    return [{"connection_id": key, "host": c.host, "validUntil": c.valid_until}
            for key, c in connections.items()]


@app.get("/api/connections/{connection_id}/framebuffer")
async def framebuffer(connection_id: str,
                      format: str = Query("jpeg", pattern="^(png|jpeg)$"),
                      compression: int | None = Query(None, ge=1, le=9),
                      quality: int | None = Query(75, ge=1, le=100),
                      width: int | None = Query(None, ge=1), height: int | None = Query(None, ge=1)):
    conn = connection_or_401(connection_id)
    params = {k: v for k, v in {"format": format, "compression": compression,
                                 "quality": quality, "width": width, "height": height}.items()
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
        raise HTTPException(response.status_code, detail)
    return Response(response.content, media_type=response.headers.get("content-type", "image/jpeg"))


@app.get("/api/connections/{connection_id}/features")
async def features(connection_id: str):
    c = connection_or_401(connection_id)
    return payload(await request(c.base_url, "GET", "feature", uid=c.uid))


@app.get("/api/connections/{connection_id}/features/{feature_uid}")
async def feature_status(connection_id: str, feature_uid: str):
    c = connection_or_401(connection_id)
    return payload(await request(c.base_url, "GET", f"feature/{quote(feature_uid, safe='')}", uid=c.uid))


@app.put("/api/connections/{connection_id}/features/{feature_uid}")
async def set_feature(connection_id: str, feature_uid: str, body: FeatureRequest):
    c = connection_or_401(connection_id)
    data: dict[str, Any] = {"active": body.active}
    if body.arguments is not None:
        data["arguments"] = body.arguments
    return payload(await request(c.base_url, "PUT", f"feature/{quote(feature_uid, safe='')}",
                                 uid=c.uid, json=data))


@app.get("/api/connections/{connection_id}/user")
async def user_info(connection_id: str):
    c = connection_or_401(connection_id)
    return payload(await request(c.base_url, "GET", "user", uid=c.uid))


@app.get("/api/connections/{connection_id}/session")
async def session_info(connection_id: str):
    c = connection_or_401(connection_id)
    return payload(await request(c.base_url, "GET", "session", uid=c.uid))


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PANEL_PORT", "8000")))
