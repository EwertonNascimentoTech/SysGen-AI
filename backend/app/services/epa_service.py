"""
Integração Azure AI Agents (MindOps): credenciais, runtime e geração de texto.

Leitura unificada com fallback para os.getenv; opcionalmente sobrescreve com valores
guardados em `app_settings` (PUT /api/settings/azure-runtime).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.services.azure_runtime_env import (
    K_AGENT,
    K_CLIENT,
    K_CONN,
    K_ENDPOINT,
    K_SECRET,
    K_TENANT,
    agents_endpoint_for_client,
    azure_agent_runtime_ready,
    get_runtime_azure_settings,
)
from app.services.azure_agent_limits import truncate_string_for_azure_agent_user_message
from app.services.prd_ai_common import (
    SYSTEM_CHAT,
    SYSTEM_INTERVIEW,
    SYSTEM_PLANEJADOR,
    SYSTEM_PROTOTIPO,
    flatten_user_content_for_agent,
)
from app.services.token_crypt import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

# Chaves na tabela app_settings (≤ 64 caracteres)
_DB_ENDPOINT = "azure_runtime.endpoint"
_DB_CONN = "azure_runtime.conn_str"
_DB_AGENT = "azure_runtime.agent_id"
_DB_TENANT = "azure_runtime.tenant_id"
_DB_CLIENT = "azure_runtime.client_id"
_DB_SECRET = "azure_runtime.client_secret"

_DB_MAP = {
    K_ENDPOINT: _DB_ENDPOINT,
    K_CONN: _DB_CONN,
    K_AGENT: _DB_AGENT,
    K_TENANT: _DB_TENANT,
    K_CLIENT: _DB_CLIENT,
    K_SECRET: _DB_SECRET,
}


async def _load_db_overrides(session: AsyncSession) -> dict[str, str]:
    out: dict[str, str] = {}
    for env_key, db_key in _DB_MAP.items():
        row = (await session.execute(select(AppSetting).where(AppSetting.key == db_key))).scalar_one_or_none()
        if row and row.value_encrypted:
            try:
                out[env_key] = decrypt_token(row.value_encrypted).strip()
            except Exception as e:  # noqa: BLE001
                logger.warning("epa_service decrypt failed key=%s err=%s", db_key, e)
    return out


async def merge_runtime_azure_settings(session: AsyncSession | None) -> dict[str, str]:
    merged = get_runtime_azure_settings()
    if session is None:
        return merged
    overrides = await _load_db_overrides(session)
    for k, v in overrides.items():
        if v:
            merged[k] = v
    return merged


async def _upsert_secret(session: AsyncSession, db_key: str, plain: str | None) -> None:
    if plain is None:
        return
    plain = plain.strip()
    row = (await session.execute(select(AppSetting).where(AppSetting.key == db_key))).scalar_one_or_none()
    if not plain:
        if row:
            await session.delete(row)
        return
    enc = encrypt_token(plain)
    if row:
        row.value_encrypted = enc
        row.hint_suffix = plain[-4:] if len(plain) >= 4 else None
    else:
        session.add(
            AppSetting(
                key=db_key,
                value_encrypted=enc,
                hint_suffix=plain[-4:] if len(plain) >= 4 else None,
            )
        )


async def persist_runtime_azure_settings(
    session: AsyncSession,
    payload: dict[str, str | None],
) -> None:
    """Persiste apenas campos presentes em payload (None = não alterar)."""
    field_to_env = {
        "azure_ai_project_endpoint": K_ENDPOINT,
        "azure_ai_project_connection_string": K_CONN,
        "azure_ai_agent_id": K_AGENT,
        "azure_tenant_id": K_TENANT,
        "azure_client_id": K_CLIENT,
        "azure_client_secret": K_SECRET,
    }
    for field, env_k in field_to_env.items():
        if field not in payload:
            continue
        val = payload[field]
        if val is None:
            continue
        if not isinstance(val, str):
            continue
        await _upsert_secret(session, _DB_MAP[env_k], val)
    await session.commit()


def _mask(val: str, head: int = 12) -> str:
    if not val:
        return ""
    if len(val) <= head:
        return "***"
    return f"{val[:head]}…"


async def build_masked_runtime_view(session: AsyncSession | None) -> dict[str, Any]:
    merged = await merge_runtime_azure_settings(session)
    ep = agents_endpoint_for_client(merged)
    aid = merged.get(K_AGENT) or ""
    return {
        "azure_ai_project_endpoint_masked": _mask(ep) if ep else "",
        "azure_ai_project_connection_string_set": bool((merged.get(K_CONN) or "").strip()),
        "azure_ai_agent_id_masked": _mask(aid) if aid else "",
        "azure_tenant_id_set": bool((merged.get(K_TENANT) or "").strip()),
        "azure_client_id_set": bool((merged.get(K_CLIENT) or "").strip()),
        "azure_client_secret_set": bool((merged.get(K_SECRET) or "").strip()),
        "ready_for_agents": azure_agent_runtime_ready(merged),
    }


async def generate_text_with_azure_agent(
    *,
    session: AsyncSession | None,
    mode: str,
    messages: list[dict[str, str]],
    attachment_dicts: list[dict[str, str]],
    agent_id_override: str | None = None,
    max_completion_tokens: int = 4096,
) -> tuple[str, str | None]:
    """
    Executa um turno via Azure AI Agents. Em falha de configuração ou run failed, levanta RuntimeError
    ou devolve mensagem de fallback explícita.
    """
    merged = await merge_runtime_azure_settings(session)
    endpoint = agents_endpoint_for_client(merged)
    agent_id = ((agent_id_override or "").strip() or (merged.get(K_AGENT) or "").strip())
    if not endpoint or not agent_id:
        return (
            "A integração Azure AI Agents não está configurada (AZURE_AI_PROJECT_ENDPOINT ou "
            "AZURE_AI_PROJECT_CONNECTION_STRING, e AZURE_AI_AGENT_ID).",
            None,
        )

    from azure.ai.agents.aio import AgentsClient  # lazy import
    from azure.ai.agents.models import (
        AgentThreadCreationOptions,
        ListSortOrder,
        MessageRole,
        RunStatus,
        ThreadMessageOptions,
    )
    from azure.identity.aio import ClientSecretCredential, DefaultAzureCredential

    if mode == "interview":
        system = SYSTEM_INTERVIEW
    elif mode == "prototipo":
        system = SYSTEM_PROTOTIPO
    elif mode == "planejamento":
        system = SYSTEM_PLANEJADOR
    else:
        system = SYSTEM_CHAT

    thread_msg_opts: list[Any] = []
    for i, m in enumerate(messages):
        role = m.get("role")
        content = m.get("content") or ""
        if role not in ("user", "assistant"):
            continue
        if role == "user" and i == len(messages) - 1 and attachment_dicts:
            content = flatten_user_content_for_agent(content, attachment_dicts)
        if role == "user" and isinstance(content, str):
            content = truncate_string_for_azure_agent_user_message(content)
        mr = MessageRole.USER if role == "user" else MessageRole.AGENT
        thread_msg_opts.append(ThreadMessageOptions(role=mr, content=content))

    tenant = (merged.get(K_TENANT) or "").strip()
    cid = (merged.get(K_CLIENT) or "").strip()
    csec = (merged.get(K_SECRET) or "").strip()
    if tenant and cid and csec:
        credential: Any = ClientSecretCredential(tenant_id=tenant, client_id=cid, client_secret=csec)
    else:
        credential = DefaultAzureCredential()

    client = AgentsClient(endpoint, credential)
    try:
        try:
            run = await client.create_thread_and_process_run(
                agent_id=agent_id,
                thread=AgentThreadCreationOptions(messages=thread_msg_opts),
                instructions=system,
                temperature=0.7,
                max_completion_tokens=max_completion_tokens,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("azure_agents_request_failed")
            raise RuntimeError(f"Azure AI Agents: {e}") from e

        status = run.status
        if status == RunStatus.FAILED or (isinstance(status, str) and status.lower() == "failed"):
            err = getattr(run, "last_error", None)
            detail = getattr(err, "message", None) if err is not None else str(run)
            logger.warning("azure_agents_run_failed detail=%s", detail)
            return (
                "Não foi possível obter resposta do agente Azure (execução falhou). "
                "Verifique o agente no portal Azure ou os registos do servidor.",
                None,
            )

        if status not in (RunStatus.COMPLETED, "completed"):
            logger.warning("azure_agents_run_unexpected_status status=%s", status)
            return ("Resposta do agente Azure incompleta ou cancelada.", None)

        thread_id = run.thread_id
        text_out = ""
        async for msg in client.messages.list(
            thread_id=thread_id,
            order=ListSortOrder.DESCENDING,
            limit=20,
        ):
            role = getattr(msg, "role", None)
            if role != MessageRole.AGENT and role != "assistant":
                continue
            for tpart in msg.text_messages:
                tv = getattr(getattr(tpart, "text", None), "value", None)
                if tv:
                    text_out += tv
            if text_out.strip():
                break
    finally:
        await client.close()
        close_c = getattr(credential, "close", None)
        if callable(close_c):
            await close_c()

    out = (text_out or "").strip()
    if not out:
        return ("(Resposta vazia do agente Azure.)", None)
    return out, "stop"


async def test_azure_openai_rest_connection() -> tuple[bool, str]:
    """
    Verifica API key e listagem de deployments; confirma se AZURE_OPENAI_DEPLOYMENT existe.
    """
    from app.core.config import settings

    ep = (settings.azure_openai_endpoint or "").strip().rstrip("/")
    key = (settings.azure_openai_api_key or "").strip()
    dep = (settings.azure_openai_deployment or "").strip()
    ver = (settings.azure_openai_api_version or "2024-08-01-preview").strip()

    if not ep or not key or not dep:
        return False, "Azure OpenAI incompleto: defina AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY e AZURE_OPENAI_DEPLOYMENT."

    import httpx

    url = f"{ep}/openai/deployments?api-version={ver}"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.get(url, headers={"api-key": key})
    except Exception as e:  # noqa: BLE001
        logger.warning("test_azure_openai_rest_connection http_error: %s", e)
        return False, f"Erro de rede ao contactar Azure OpenAI: {e}"

    if r.status_code != 200:
        return False, f"Azure OpenAI HTTP {r.status_code}: {(r.text or '')[:400]}"

    try:
        data = r.json()
    except Exception:
        return True, "Ligação OK (resposta de deployments não-JSON; confira o deployment no portal)."

    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return True, "Ligação OK (lista de deployments em formato inesperado)."

    ids = {str(x.get("id", "")) for x in items if isinstance(x, dict)}
    if dep in ids:
        return True, f"Ligação OK — deployment «{dep}» encontrado no recurso."
    return (
        False,
        f"Ligação ao recurso OK, mas o deployment «{dep}» não aparece na lista. "
        f"Deployments: {', '.join(sorted(ids)[:12])}{'…' if len(ids) > 12 else ''}",
    )


async def run_azure_ai_connection_tests(session: AsyncSession | None) -> dict[str, Any]:
    """
    Executa testes Agents (se configurado) e OpenAI REST (se configurado).
    Retorna dict compatível com AzureRuntimeTestResponse.
    """
    merged = await merge_runtime_azure_settings(session)
    ep_ok = agents_endpoint_for_client(merged)
    aid = (merged.get(K_AGENT) or "").strip()

    agents_ok: bool | None = None
    agents_detail: str | None = None
    if ep_ok and aid:
        agents_ok, agents_detail = await test_azure_agent_connection(session)
    else:
        agents_detail = "Ignorado — defina AZURE_AI_PROJECT_ENDPOINT (ou connection string) e AZURE_AI_AGENT_ID."

    openai_ok: bool | None = None
    openai_detail: str | None = None
    from app.core.config import settings as _s

    openai_configured = bool(
        (_s.azure_openai_endpoint or "").strip()
        and (_s.azure_openai_api_key or "").strip()
        and (_s.azure_openai_deployment or "").strip()
    )
    if openai_configured:
        openai_ok, openai_detail = await test_azure_openai_rest_connection()
    else:
        openai_detail = "Ignorado — defina AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY e AZURE_OPENAI_DEPLOYMENT."

    overall = bool((agents_ok is True) or (openai_ok is True))
    if overall:
        parts = []
        if agents_ok is True:
            parts.append("Azure AI Agents")
        if openai_ok is True:
            parts.append("Azure OpenAI")
        message = "Ligação OK — " + " e ".join(parts) + "."
    elif agents_ok is None and openai_ok is None:
        message = (
            "Nenhum caminho configurado: defina endpoint + AZURE_AI_AGENT_ID (Agents) "
            "ou AZURE_OPENAI_* (OpenAI REST)."
        )
    elif agents_ok is False and openai_ok is False:
        message = "Falha nos testes de Agents e de OpenAI. Veja os detalhes abaixo."
    else:
        message = "Nenhum caminho passou no teste. Veja agents_detail e openai_detail."

    return {
        "ok": overall,
        "message": message,
        "agents_ok": agents_ok,
        "agents_detail": agents_detail,
        "openai_ok": openai_ok,
        "openai_detail": openai_detail,
    }


async def test_azure_agent_connection(session: AsyncSession | None) -> tuple[bool, str]:
    """Valida credenciais e existência do agente (get_agent)."""
    merged = await merge_runtime_azure_settings(session)
    endpoint = agents_endpoint_for_client(merged)
    agent_id = (merged.get(K_AGENT) or "").strip()
    if not endpoint or not agent_id:
        return False, "Defina AZURE_AI_PROJECT_ENDPOINT (ou connection string) e AZURE_AI_AGENT_ID."

    from azure.ai.agents.aio import AgentsClient
    from azure.identity.aio import ClientSecretCredential, DefaultAzureCredential

    tenant = (merged.get(K_TENANT) or "").strip()
    cid = (merged.get(K_CLIENT) or "").strip()
    csec = (merged.get(K_SECRET) or "").strip()
    if tenant and cid and csec:
        credential: Any = ClientSecretCredential(tenant_id=tenant, client_id=cid, client_secret=csec)
    else:
        credential = DefaultAzureCredential()

    client = AgentsClient(endpoint, credential)
    try:
        await client.get_agent(agent_id)
        return True, "Ligação OK (agente encontrado)."
    except Exception as e:  # noqa: BLE001
        logger.warning("test_azure_agent_connection failed: %s", e)
        return False, f"Falha ao contactar Azure AI Agents: {e}"
    finally:
        await client.close()
        c = getattr(credential, "close", None)
        if callable(c):
            await c()


async def probe_azure_openai_chat_request() -> tuple[bool, str]:
    """
    Uma requisição POST real a chat/completions (mínima) para validar key, deployment e API.
    """
    import httpx

    from app.core.config import settings

    ep = (settings.azure_openai_endpoint or "").strip().rstrip("/")
    key = (settings.azure_openai_api_key or "").strip()
    dep = (settings.azure_openai_deployment or "").strip()
    ver = (settings.azure_openai_api_version or "2024-08-01-preview").strip()

    if not ep or not key or not dep:
        return False, "Azure OpenAI não configurado (AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT)."

    url = f"{ep}/openai/deployments/{dep}/chat/completions?api-version={ver}"
    body = {
        "messages": [{"role": "user", "content": "Responda apenas com a palavra: ok"}],
        "max_tokens": 24,
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(
                url,
                headers={"api-key": key, "Content-Type": "application/json"},
                json=body,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("probe_azure_openai_chat_request: %s", e)
        return False, f"Erro de rede: {e}"

    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {(r.text or '')[:800]}"

    try:
        data = r.json()
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        preview = (content or "").strip()[:200]
        return True, f"Requisição OK — resposta do modelo ({len(content)} chars): {preview!r}"
    except Exception as e:  # noqa: BLE001
        return False, f"Resposta não-JSON ou inesperada: {e}"


async def probe_azure_agent_chat_request(session: AsyncSession | None) -> tuple[bool, str]:
    """
    Um turno mínimo via Azure AI Agents (mesmo fluxo do chat PRD), sem anexos.
    """
    merged = await merge_runtime_azure_settings(session)
    if not azure_agent_runtime_ready(merged):
        return False, "Azure AI Agents não configurado (endpoint + AZURE_AI_AGENT_ID)."

    try:
        text, _reason = await generate_text_with_azure_agent(
            session=session,
            mode="chat",
            messages=[{"role": "user", "content": "Responda só com: OK"}],
            attachment_dicts=[],
        )
    except RuntimeError as e:
        return False, str(e)

    if not (text or "").strip():
        return False, "Resposta vazia do agente."
    if "não está configurada" in (text or "") and "Azure AI Agents" in (text or ""):
        return False, text
    preview = (text or "").strip()[:300]
    return True, f"Requisição OK — resposta ({len(text or '')} chars): {preview!r}"


async def run_azure_ai_request_probes(session: AsyncSession | None) -> dict[str, Any]:
    """Resultado agregado para script/CLI: testes de requisição (não só metadados)."""
    o_ok, o_msg = await probe_azure_openai_chat_request()
    a_ok, a_msg = await probe_azure_agent_chat_request(session)
    overall = o_ok or a_ok
    if overall:
        parts = []
        if o_ok:
            parts.append("OpenAI (chat/completions)")
        if a_ok:
            parts.append("Agents (turno)")
        summary = "Requisição(ões) OK: " + " e ".join(parts) + "."
    else:
        summary = "Nenhuma requisição bem-sucedida. Veja openai_request e agents_request."
    return {
        "ok": overall,
        "message": summary,
        "openai_request_ok": o_ok,
        "openai_request_detail": o_msg,
        "agents_request_ok": a_ok,
        "agents_request_detail": a_msg,
    }
