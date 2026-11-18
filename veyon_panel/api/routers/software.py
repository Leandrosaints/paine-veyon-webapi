"""Software catalog and remote deployment endpoints."""
import base64
import ipaddress
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from veyon_panel.core.config import LOCAL_NETWORK_CIDRS
from veyon_panel.db.session import get_db
from veyon_panel.models.resources import Software
from veyon_panel.api.routers.veyon import connections, connection_request, connection_or_401
from veyon_panel.services.veyon import payload

router = APIRouter(tags=["Deploy de software"])
logger = logging.getLogger("veyon.audit")
START_APP_FEATURE = "da9ca56a-b2ad-4fff-8f8a-929b2927b442"


class DeployRequest(BaseModel):
    software_id: int = Field(gt=0)
    ip: str = Field(min_length=1, max_length=253)


def is_local_target(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
        networks = [ipaddress.ip_network(item, strict=False) for item in LOCAL_NETWORK_CIDRS]
    except ValueError as exc:
        raise HTTPException(500, "LOCAL_NETWORK_CIDRS contém uma rede ou IP inválido.") from exc
    return any(address.version == network.version and address in network for network in networks)


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@router.get("/softwares")
def list_softwares(db: Session = Depends(get_db)):
    return [
        {"id": item.id, "nome": item.nome, "url_local": item.url_local,
         "url_publica": item.url_publica, "argumentos_instalacao": item.argumentos_instalacao}
        for item in db.scalars(select(Software).order_by(Software.nome)).all()
    ]


@router.post("/deploy")
async def deploy(body: DeployRequest, db: Session = Depends(get_db)):
    software = db.get(Software, body.software_id)
    if software is None:
        logger.warning("Ação: deploy | Host: %s | Bloqueado (software inexistente)", body.ip)
        raise HTTPException(404, "Software não encontrado.")
    try:
        ipaddress.ip_address(body.ip)
    except ValueError as exc:
        logger.warning("Ação: deploy | Host: %s | Bloqueado (IP inválido)", body.ip)
        raise HTTPException(422, "O alvo precisa ser um endereço IP válido.") from exc
    match = next(((cid, conn) for cid, conn in connections.items() if conn.host == body.ip), None)
    if match is None:
        logger.warning("Ação: deploy | Host: %s | Bloqueado (sem sessão autenticada)", body.ip)
        raise HTTPException(401, "Autentique o computador selecionado antes do deploy.")
    connection_id, conn = match
    connection_or_401(connection_id)
    download_url = software.url_local if is_local_target(body.ip) else software.url_publica
    if not download_url.startswith(("https://", "http://")):
        logger.warning("Ação: deploy | Host: %s | Bloqueado (URL inválida)", body.ip)
        raise HTTPException(400, "A URL configurada para este software precisa usar HTTP ou HTTPS.")

    # StartApp is Veyon's WebAPI feature for launching a command on the authenticated target.
    command = (
        "$ErrorActionPreference='Stop';"
        f"$url={ps_quote(download_url)};"
        "$file=Join-Path $env:TEMP ([IO.Path]::GetFileName(([uri]$url).AbsolutePath));"
        "if ([string]::IsNullOrWhiteSpace([IO.Path]::GetFileName($file))) { $file=Join-Path $env:TEMP 'veyon-installer.exe' };"
        "Invoke-WebRequest -Uri $url -OutFile $file;"
        f"Start-Process -FilePath $file -ArgumentList {ps_quote(software.argumentos_instalacao)} -Wait"
    )
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    app_command = f"powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {encoded}"
    try:
        response = await connection_request(
            connection_id, conn, "PUT", f"feature/{START_APP_FEATURE}",
            json={"active": True, "arguments": {"applications": [app_command]}},
        )
    except HTTPException as exc:
        logger.warning("Ação: deploy | Host: %s | Erro %s", body.ip, exc.status_code)
        raise
    logger.info("Ação: deploy | Host: %s | Aceito pelo Veyon", body.ip)
    return {"ok": True, "host": body.ip, "software": software.nome,
            "url": download_url, "veyon": payload(response)}
