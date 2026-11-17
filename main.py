"""Entrypoint for the local Veyon Control Panel."""
import os

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from veyon_panel.api.routers import resources, veyon
from veyon_panel.core.config import STATIC_DIR
from veyon_panel.db.migrations import upgrade_database

upgrade_database()

app = FastAPI(
    title="Veyon Control Panel",
    description="Painel local e proxy para todas as operações da Veyon WebAPI v1.",
    version="2.0.0",
)
app.include_router(resources.router, prefix="/api")
app.include_router(veyon.router, prefix="/api")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PANEL_PORT", "8000")))
