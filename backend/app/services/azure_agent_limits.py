"""Limites da API Azure AI Agents (mensagens)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Documentado pela API: `thread.messages[].content` como string.
AZURE_AGENTS_MAX_USER_MESSAGE_CHARS = 256_000


def truncate_string_for_azure_agent_user_message(content: str) -> str:
    """Evita `string_above_max_length` ao enviar mensagens user para o AgentsClient."""
    max_len = AZURE_AGENTS_MAX_USER_MESSAGE_CHARS
    if len(content) <= max_len:
        return content
    suffix = (
        "\n\n[... TRUNCADO pelo servidor: limite Azure AI Agents de "
        f"{max_len} caracteres por mensagem do utilizador.]\n"
    )
    keep = max_len - len(suffix)
    if keep < 1:
        keep = max_len
    out = content[:keep] + suffix
    logger.warning(
        "azure_agents_user_content_truncated original_len=%s final_len=%s",
        len(content),
        len(out),
    )
    return out
