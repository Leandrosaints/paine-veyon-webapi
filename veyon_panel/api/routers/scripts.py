"""Script upload, execution and remote result callbacks."""
import asyncio
import base64
import ipaddress
import logging
import secrets
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from veyon_panel.api.routers.veyon import connection_request, connections
from veyon_panel.core.config import (
    PANEL_API_KEY, PANEL_PUBLIC_BASE_URL, SCRIPT_EXECUTION_TIMEOUT_SECONDS, UPLOADS_DIR,
)
from veyon_panel.db.session import get_db
from veyon_panel.models.resources import RepositoryScript
from veyon_panel.services.veyon import payload

router = APIRouter(tags=["Hub de scripts"])
logger = logging.getLogger("veyon.audit")
START_APP_FEATURE = "da9ca56a-b2ad-4fff-8f8a-929b2927b442"
MAX_SCRIPT_SIZE = 5 * 1024 * 1024
pending_results: dict[tuple[str, str], asyncio.Future] = {}
latest_logs: dict[str, dict] = {}


class ExecuteScriptsRequest(BaseModel):
    script_id: int = Field(gt=0)
    ips: list[str] = Field(min_length=1, max_length=500)


class RemoteResult(BaseModel):
    output: str = ""
    exit_code: int | None = None
    run_id: str | None = None


class InventoryResult(BaseModel):
    inventory: list[dict] = Field(default_factory=list)


def require_public_base() -> str:
    if not PANEL_PUBLIC_BASE_URL:
        raise HTTPException(503, "Configure PANEL_PUBLIC_BASE_URL para que os computadores alcancem o painel.")
    return PANEL_PUBLIC_BASE_URL


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def encoded_command(script: str) -> str:
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return f"powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -EncodedCommand {encoded}"


async def start_remote(connection_id: str, conn, script: str):
    response = await connection_request(
        connection_id, conn, "PUT", f"feature/{START_APP_FEATURE}",
        json={"active": True, "arguments": {"applications": [encoded_command(script)]}},
    )
    return payload(response)


def connection_for_ip(ip: str):
    try:
        ipaddress.ip_address(ip)
    except ValueError as exc:
        raise HTTPException(422, f"Alvo inválido: {ip}") from exc
    found = next(((connection_id, conn) for connection_id, conn in connections.items()
                  if conn.host == ip), None)
    if found is None:
        raise HTTPException(401, f"{ip}: autentique o computador para continuar.")
    return found


def callback_url(kind: str, ip: str) -> str:
    return f"{require_public_base()}/api/{kind}/{quote(ip, safe='')}"


def callback_post_script(url: str, key: str, body_expression: str) -> str:
    return (
        f"$callback={ps_quote(url)};$apiKey={ps_quote(key)};"
        f"$payload={body_expression};"
        "$json=$payload|ConvertTo-Json -Depth 8 -Compress;"
        "Invoke-RestMethod -Uri $callback -Method Post -Headers @{'X-API-Key'=$apiKey} "
        "-ContentType 'application/json' -Body $json|Out-Null"
    )


@router.post("/scripts/upload")
async def upload_script(file: UploadFile = File(...), nome: str | None = Form(None),
                        db: Session = Depends(get_db)):
    original_name = Path(file.filename or "").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".ps1", ".bat"}:
        raise HTTPException(415, "Envie somente arquivos .ps1 ou .bat.")
    content = await file.read(MAX_SCRIPT_SIZE + 1)
    if not content:
        raise HTTPException(400, "O arquivo está vazio.")
    if len(content) > MAX_SCRIPT_SIZE:
        raise HTTPException(413, "O script excede o limite de 5 MB.")
    record = RepositoryScript(nome=(nome or Path(original_name).stem).strip()[:160] or Path(original_name).stem,
                              nome_arquivo=original_name, tipo=suffix[1:])
    try:
        db.add(record)
        db.flush()
        (UPLOADS_DIR / f"{record.id}.{record.tipo}").write_bytes(content)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        if record.id is not None:
            (UPLOADS_DIR / f"{record.id}.{record.tipo}").unlink(missing_ok=True)
        raise
    logger.info("Ação: upload de script | Arquivo: %s | Sucesso", original_name)
    return {"id": record.id, "nome": record.nome, "nome_arquivo": original_name,
            "data_upload": record.data_upload, "tipo": record.tipo}


@router.get("/scripts")
def list_scripts(db: Session = Depends(get_db)):
    return [{"id": script.id, "nome": script.nome,
             "nome_arquivo": script.nome_arquivo, "data_upload": script.data_upload,
             "tipo": script.tipo}
            for script in db.scalars(select(RepositoryScript).order_by(RepositoryScript.nome)).all()]


@router.get("/scripts/file/{script_id}")
def get_script_file(script_id: int, db: Session = Depends(get_db)):
    script = db.get(RepositoryScript, script_id)
    if script is None:
        raise HTTPException(404, "Script não encontrado.")
    path = UPLOADS_DIR / f"{script.id}.{script.tipo}"
    if not path.is_file():
        raise HTTPException(404, "Arquivo de script não encontrado no servidor.")
    from fastapi.responses import FileResponse
    return FileResponse(path, filename=script.nome_arquivo)


@router.post("/scripts/execute")
async def execute_scripts(body: ExecuteScriptsRequest, db: Session = Depends(get_db)):
    script_record = db.get(RepositoryScript, body.script_id)
    if script_record is None:
        raise HTTPException(404, "Script não encontrado.")
    base = require_public_base()
    script_url = f"{base}/api/scripts/file/{script_record.id}"
    results = []
    semaphore = asyncio.Semaphore(5)

    async def execute(ip: str):
        async with semaphore:
            run_id = secrets.token_urlsafe(18)
            result_key = (ip, f"execute:{run_id}")
            result_future = asyncio.get_running_loop().create_future()
            try:
                connection_id, conn = connection_for_ip(ip)
                pending_results[result_key] = result_future
                callback = callback_url("scripts/log", ip)
                setup = ("$ErrorActionPreference='Stop';$exitCode=0;$combined='';"
                         "$log=Join-Path $env:TEMP 'veyon_script_log.txt';"
                         "$out=Join-Path $env:TEMP 'veyon_script_output.txt';")
                fetch = ("$scriptPath=Join-Path $env:TEMP " +
                         ps_quote(f"veyon_{script_record.id}.{script_record.tipo}") + ";" +
                         f"Invoke-WebRequest -Uri {ps_quote(script_url)} "
                         f"-Headers @{{'X-API-Key'={ps_quote(PANEL_API_KEY)}}} -OutFile $scriptPath;")
                if script_record.tipo == "ps1":
                    launch = "& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $scriptPath *> $out;$exitCode=$LASTEXITCODE;"
                else:
                    launch = "& cmd.exe /d /c ('\"'+$scriptPath+'\"') *> $out;$exitCode=$LASTEXITCODE;"
                callback_body = (f"@{{ip={ps_quote(ip)};run_id={ps_quote(run_id)};"
                                 "output=$combined;exit_code=$exitCode}")
                post = callback_post_script(callback, PANEL_API_KEY, callback_body)
                remote_script = (
                    setup + "try{" + fetch + launch +
                    "$combined=Get-Content -LiteralPath $out -Raw -ErrorAction SilentlyContinue;"
                    "}catch{$exitCode=1;$combined=$_.Exception.ToString();}"
                    "finally{try{Set-Content -LiteralPath $log -Value $combined -ErrorAction SilentlyContinue;}catch{}" +
                    post + "}"
                )
                await start_remote(connection_id, conn, remote_script)
                logger.info("Script run %s | Host: %s | waiting for completion callback", body.script_id, ip)
                result = await asyncio.wait_for(result_future, SCRIPT_EXECUTION_TIMEOUT_SECONDS)
                logger.info("Script run %s | Host: %s | finished with exit code %s",
                            body.script_id, ip, result["exit_code"])
                return {"ip": ip, "status": "completed", **result}
            except asyncio.TimeoutError:
                logger.warning("Script run %s | Host: %s | completion callback timed out", body.script_id, ip)
                return {"ip": ip, "status": "timeout",
                        "detail": "Command accepted but no completion callback arrived. Use Ver Log to retrieve the result."}
            except HTTPException as exc:
                logger.warning("A??o: executar script %s | Host: %s | Erro %s", body.script_id, ip, exc.status_code)
                return {"ip": ip, "status": "error", "detail": exc.detail, "http_status": exc.status_code}
            except Exception as exc:
                logger.exception("Falha ao executar script no host %s", ip)
                return {"ip": ip, "status": "error", "detail": str(exc)}
            finally:
                pending_results.pop(result_key, None)

    for offset in range(0, len(body.ips), 5):
        results.extend(await asyncio.gather(*(execute(ip) for ip in body.ips[offset:offset + 5])))
    return {"results": results}


@router.post("/scripts/log/{ip}")
async def receive_script_log(ip: str, body: RemoteResult):
    record = {"ip": ip, "output": body.output, "exit_code": body.exit_code}
    latest_logs[ip] = record
    if body.run_id:
        run_future = pending_results.get((ip, f"execute:{body.run_id}"))
        if run_future is not None and not run_future.done():
            run_future.set_result(record)
    future = pending_results.get((ip, "log"))
    if future is not None and not future.done():
        future.set_result(record)
    return {"ok": True}


async def collect_remote(ip: str, kind: str, script: str, timeout: float = 25):
    connection_id, conn = connection_for_ip(ip)
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    pending_results[(ip, kind)] = future
    try:
        await start_remote(connection_id, conn, script)
        return await asyncio.wait_for(future, timeout)
    except asyncio.TimeoutError as exc:
        raise HTTPException(504, f"Tempo esgotado aguardando resultado de {ip}.") from exc
    finally:
        pending_results.pop((ip, kind), None)


@router.get("/scripts/log/{ip}")
async def get_script_log(ip: str):
    callback = callback_url("scripts/log", ip)
    script = (
        "$path=Join-Path $env:TEMP 'veyon_script_log.txt';"
        "$content=if(Test-Path -LiteralPath $path){Get-Content -LiteralPath $path -Raw}else{'Arquivo de log ainda não existe.'};"
        + callback_post_script(callback, PANEL_API_KEY, "@{output=$content;exit_code=$null}")
    )
    result = await collect_remote(ip, "log", script)
    latest_logs[ip] = result
    return result


@router.post("/inventory/{ip}")
async def receive_inventory(ip: str, body: InventoryResult):
    future = pending_results.get((ip, "inventory"))
    if future is not None and not future.done():
        future.set_result(body.inventory)
    return {"ok": True}


@router.get("/inventory/{ip}")
async def inventory(ip: str):
    callback = callback_url("inventory", ip)
    command = (
        "$paths=@('HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*');"
        "$items=foreach($path in $paths){Get-ItemProperty $path -ErrorAction SilentlyContinue|"
        "Where-Object {$_.DisplayName}|Select-Object @{n='nome';e={$_.DisplayName}},"
        "@{n='versao';e={$_.DisplayVersion}},@{n='fabricante';e={$_.Publisher}}};"
        + callback_post_script(callback, PANEL_API_KEY, "@{inventory=@($items)}")
    )
    return {"ip": ip, "softwares": await collect_remote(ip, "inventory", command)}
