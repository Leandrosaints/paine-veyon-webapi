from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException


async def request(base_url: str, method: str, path: str, *, uid: str | None = None,
                  json: Any = None, params: dict[str, Any] | None = None,
                  timeout: float = 15) -> httpx.Response:
    headers = {"Connection-Uid": uid} if uid else {}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
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


def api_base_url(value: str | None, default: str) -> str:
    url = (value or default).strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "O endereço da WebAPI precisa começar com http:// ou https://")
    return url


def host_path(host: str) -> str:
    return f"authentication/{quote(host, safe='')}"
