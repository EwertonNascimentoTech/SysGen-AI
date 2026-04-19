"""Leitura de variáveis Azure AI (env + pydantic) sem dependência de SQLAlchemy."""

from __future__ import annotations

import os

from app.core.config import settings

K_ENDPOINT = "AZURE_AI_PROJECT_ENDPOINT"
K_CONN = "AZURE_AI_PROJECT_CONNECTION_STRING"
K_AGENT = "AZURE_AI_AGENT_ID"
K_AGENT_PROTOTIPO = "AZURE_AI_AGENT_PROTOTIPO_ID"
K_AGENT_PLANEJADOR = "AZURE_AI_AGENT_PLANEJADOR_ID"
K_TENANT = "AZURE_TENANT_ID"
K_CLIENT = "AZURE_CLIENT_ID"
K_SECRET = "AZURE_CLIENT_SECRET"

_ALL_KEYS = (K_ENDPOINT, K_CONN, K_AGENT, K_TENANT, K_CLIENT, K_SECRET)


def _from_pydantic() -> dict[str, str]:
    return {
        K_ENDPOINT: (getattr(settings, "azure_ai_project_endpoint", None) or "").strip(),
        K_CONN: (getattr(settings, "azure_ai_project_connection_string", None) or "").strip(),
        K_AGENT: (getattr(settings, "azure_ai_agent_id", None) or "").strip(),
        K_TENANT: (getattr(settings, "azure_tenant_id", None) or "").strip(),
        K_CLIENT: (getattr(settings, "azure_client_id", None) or "").strip(),
        K_SECRET: (getattr(settings, "azure_client_secret", None) or "").strip(),
    }


def get_runtime_azure_settings() -> dict[str, str]:
    """Valores efectivos: pydantic + os.getenv (sem base de dados)."""
    base = _from_pydantic()
    for k in _ALL_KEYS:
        env_v = (os.getenv(k) or "").strip()
        if env_v:
            base[k] = env_v
        elif not base.get(k):
            base[k] = ""
    return base


def agents_endpoint_for_client(cfg: dict[str, str]) -> str:
    return (cfg.get(K_CONN) or "").strip() or (cfg.get(K_ENDPOINT) or "").strip()


def azure_agent_runtime_ready(cfg: dict[str, str]) -> bool:
    return bool(agents_endpoint_for_client(cfg) and (cfg.get(K_AGENT) or "").strip())


def get_prototipo_agent_id() -> str:
    """Prioridade: variável de ambiente, depois Settings (pydantic)."""
    v = (os.getenv(K_AGENT_PROTOTIPO) or "").strip()
    if v:
        return v
    return (getattr(settings, "azure_ai_agent_prototipo_id", None) or "").strip()


def get_planejador_agent_id() -> str:
    """Prioridade: variável de ambiente, depois Settings (pydantic)."""
    v = (os.getenv(K_AGENT_PLANEJADOR) or "").strip()
    if v:
        return v
    return (getattr(settings, "azure_ai_agent_planejador_id", None) or "").strip()
