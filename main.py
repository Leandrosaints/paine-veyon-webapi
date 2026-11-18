"""Entrypoint for the local Veyon Control Panel."""
import asyncio
import logging
import os
import secrets
import time
from urllib.parse import unquote

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from veyon_panel.api.routers import resources, scripts, software, veyon
from veyon_panel.core.config import PANEL_API_KEY, STATIC_DIR
from veyon_panel.db.migrations import upgrade_database
from veyon_panel.db.session import SessionLocal
from veyon_panel.models.resources import Software
from veyon_panel.services.veyon import host_path, request as veyon_request

upgrade_database()

logger = logging.getLogger("veyon.audit")
app = FastAPI(
    title="Veyon Control Panel",
    description="Painel local e proxy para todas as operações da Veyon WebAPI v1.",
    version="2.0.0",
)
app.include_router(resources.router, prefix="/api")
app.include_router(veyon.router, prefix="/api")
app.include_router(software.router, prefix="/api")
app.include_router(scripts.router, prefix="/api")


def seed_softwares() -> None:
    """Install a sample catalog entry on first run; operators can override its URLs."""
    with SessionLocal() as db:
        if db.query(Software).filter(Software.nome == "Microsoft Visual C++ Runtime x64").first():
            return
        public_url = os.getenv(
            "SEED_SOFTWARE_PUBLIC_URL", "https://aka.ms/vs/17/release/vc_redist.x64.exe"
        )
        local_url = os.getenv("SEED_SOFTWARE_LOCAL_URL", public_url)
        db.add(Software(
            nome="Microsoft Visual C++ Runtime x64",
            url_local=local_url,
            url_publica=public_url,
            argumentos_instalacao="/install /quiet /norestart",
        ))
        db.commit()


seed_softwares()


def request_host(request: Request) -> str:
    parts = request.url.path.strip("/").split("/")
    if "connections" in parts:
        index = parts.index("connections")
        if index + 1 < len(parts):
            connection = veyon.connections.get(parts[index + 1])
            if connection:
                return connection.host
    if "authentication" in parts:
        index = parts.index("authentication")
        if index + 1 < len(parts):
            return unquote(parts[index + 1])
    return request.client.host if request.client else "desconhecido"


def request_action(request: Request) -> str:
    parts = request.url.path.strip("/").split("/")
    if "connections" in parts:
        index = parts.index("connections")
        connection_index = index + 1
        if connection_index < len(parts) and parts[connection_index] != "computer":
            parts[connection_index] = "{id}"
        elif connection_index + 1 < len(parts):
            parts[connection_index + 1] = "{id}"
    return "/" + "/".join(parts)


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if request.url.path == "/api" or request.url.path.startswith("/api/"):
        provided_key = request.headers.get("X-API-Key", "")
        action = f"{request.method} {request_action(request)}"
        if not secrets.compare_digest(provided_key.encode("utf-8"), PANEL_API_KEY.encode("utf-8")):
            logger.info("Ação: %s | Host: %s | Erro", action, request_host(request))
            return JSONResponse(status_code=401, content={"detail": "API Key inválida."})

        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            outcome = "Sucesso" if response is not None and response.status_code < 400 else "Erro"
            logger.info("Ação: %s | Host: %s | %s", action, request_host(request), outcome)
    return await call_next(request)


async def cleanup_idle_connections() -> None:
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        for connection_id, connection in list(veyon.connections.items()):
            if now - connection.last_used < 120 or veyon.connections.get(connection_id) is not connection:
                continue
            veyon.connections.pop(connection_id, None)
            veyon.clear_connection_cache(connection_id)
            try:
                await veyon_request(
                    connection.base_url, "DELETE", host_path(connection.host),
                    uid=connection.uid, timeout=3,
                )
            except HTTPException:
                logger.info("Ação: encerrar sessão inativa | Host: %s | Erro", connection.host)
            else:
                logger.info("Ação: encerrar sessão inativa | Host: %s | Sucesso", connection.host)


@app.on_event("startup")
async def start_session_cleanup() -> None:
    app.state.session_cleanup_task = asyncio.create_task(cleanup_idle_connections())


@app.on_event("shutdown")
async def stop_session_cleanup() -> None:
    task = getattr(app.state, "session_cleanup_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PANEL_PORT", "8000")))
