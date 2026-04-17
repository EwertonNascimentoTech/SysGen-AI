import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.azure_runtime_env import agents_endpoint_for_client, get_prototipo_agent_id
from app.services.epa_service import (
    azure_agent_runtime_ready,
    generate_text_with_azure_agent,
    merge_runtime_azure_settings,
)
from app.services.prd_ai_common import SYSTEM_CHAT, SYSTEM_INTERVIEW, build_user_content

logger = logging.getLogger(__name__)


def _openai_rest_configured() -> bool:
    return bool(
        settings.azure_openai_endpoint
        and settings.azure_openai_api_key
        and settings.azure_openai_deployment
    )


async def is_prd_ai_configured(session: AsyncSession | None) -> bool:
    """Azure AI Agents (project + agent) ou Azure OpenAI REST completo."""
    merged = await merge_runtime_azure_settings(session)
    if azure_agent_runtime_ready(merged):
        return True
    return _openai_rest_configured()


async def is_prototipo_ai_configured(session: AsyncSession | None) -> bool:
    """Projecto Azure + agente dedicado a protótipo (env AZURE_AI_AGENT_PROTOTIPO_ID)."""
    merged = await merge_runtime_azure_settings(session)
    return bool(agents_endpoint_for_client(merged) and get_prototipo_agent_id())


async def run_chat(
    *,
    mode: str,
    messages: list[dict[str, str]],
    attachment_dicts: list[dict[str, str]],
    session: AsyncSession | None = None,
) -> tuple[str, str | None]:
    """
    messages: lista de {role, content} sem system; a última entrada deve ser user.
    attachment_dicts: anexos da última mensagem do utilizador.
    """
    merged = await merge_runtime_azure_settings(session)
    if azure_agent_runtime_ready(merged):
        return await generate_text_with_azure_agent(
            session=session,
            mode=mode,
            messages=messages,
            attachment_dicts=attachment_dicts,
        )

    if not _openai_rest_configured():
        raise RuntimeError("Azure OpenAI não configurado")

    if not messages or messages[-1].get("role") != "user":
        raise ValueError("A última mensagem deve ser do utilizador")

    system = SYSTEM_INTERVIEW if mode == "interview" else SYSTEM_CHAT

    azure_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]

    for i, m in enumerate(messages):
        role = m.get("role")
        content = m.get("content") or ""
        if role not in ("user", "assistant"):
            continue
        if role == "user" and i == len(messages) - 1 and attachment_dicts:
            built = build_user_content(content, attachment_dicts)
            azure_messages.append({"role": "user", "content": built})
        else:
            azure_messages.append({"role": role, "content": content})

    url = (
        f"{settings.azure_openai_endpoint}/openai/deployments/{settings.azure_openai_deployment}"
        f"/chat/completions?api-version={settings.azure_openai_api_version}"
    )
    headers = {"api-key": settings.azure_openai_api_key, "Content-Type": "application/json"}
    body = {
        "messages": azure_messages,
        "max_tokens": 4096,
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, headers=headers, json=body)

    if r.status_code != 200:
        detail = r.text[:2000]
        logger.warning("azure_openai_error status=%s body=%s", r.status_code, detail)
        raise RuntimeError(f"Azure OpenAI: {r.status_code} — {detail}")

    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    out = msg.get("content") or ""
    finish = choice.get("finish_reason")
    return out.strip() or "(Resposta vazia do modelo.)", finish
