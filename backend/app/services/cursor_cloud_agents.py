from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx

CURSOR_API_BASE = "https://api.cursor.com"


def verify_cursor_webhook_signature(secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    if not secret or signature_header is None:
        return False
    sig = signature_header.strip()
    if not sig.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _cursor_basic_auth(api_key: str) -> tuple[str, str]:
    return (api_key, "")


async def launch_cloud_agent(
    api_key: str,
    *,
    prompt_text: str,
    repository_url: str,
    ref: str | None,
    webhook_url: str,
    webhook_secret: str,
    model: str | None = None,
    integration_branch_name: str | None = None,
    cursor_target_disable_pr_only: bool = False,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "prompt": {"text": prompt_text},
        "source": {"repository": repository_url.strip()},
        "webhook": {"url": webhook_url, "secret": webhook_secret},
    }
    if ref:
        body["source"]["ref"] = ref.strip()
    if model:
        body["model"] = model
    # Modo Auto: (1) branch novo → `branchName` + `autoCreatePr: false`.
    # (2) branch já existe → não repetir `branchName` com o mesmo `ref` (a Cursor devolve 400);
    #     enviar só `autoCreatePr: false` para desactivar PR automático por agente.
    if integration_branch_name and integration_branch_name.strip():
        body["target"] = {
            "branchName": integration_branch_name.strip(),
            "autoCreatePr": False,
        }
    elif cursor_target_disable_pr_only:
        body["target"] = {"autoCreatePr": False}
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{CURSOR_API_BASE}/v0/agents",
            json=body,
            auth=_cursor_basic_auth(api_key),
            headers={"Content-Type": "application/json"},
        )
    if r.status_code >= 400:
        detail = r.text[:2000]
        try:
            j = r.json()
            if isinstance(j, dict):
                if j.get("message"):
                    detail = str(j["message"])
                elif j.get("error"):
                    detail = str(j["error"])
        except Exception:
            pass
        raise RuntimeError(f"Cursor API {r.status_code}: {detail}")
    data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError("Resposta inválida da Cursor API")
    return data


async def fetch_cursor_agent(api_key: str, agent_id: str) -> dict[str, Any] | None:
    """
    GET /v0/agents/{id}. Devolve None se o agente já não existir (404).
    """
    aid = (agent_id or "").strip()
    if not aid:
        return None
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(
            f"{CURSOR_API_BASE}/v0/agents/{aid}",
            auth=_cursor_basic_auth(api_key),
        )
    if r.status_code == 404:
        return None
    if r.status_code >= 400:
        detail = r.text[:2000]
        try:
            j = r.json()
            if isinstance(j, dict):
                if j.get("message"):
                    detail = str(j["message"])
                elif j.get("error"):
                    detail = str(j["error"])
        except Exception:
            pass
        raise RuntimeError(f"Cursor API {r.status_code}: {detail}")
    out = r.json()
    return out if isinstance(out, dict) else None
