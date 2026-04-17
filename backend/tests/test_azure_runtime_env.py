"""Testes unitários da configuração Azure (env) — sem SQLAlchemy."""

import pytest

from app.services.azure_runtime_env import (
    K_AGENT,
    K_CONN,
    K_ENDPOINT,
    agents_endpoint_for_client,
    azure_agent_runtime_ready,
    get_runtime_azure_settings,
)


def test_agents_endpoint_prefers_connection_string():
    cfg = {
        K_CONN: "project_conn;",
        K_ENDPOINT: "https://example.services.ai.azure.com/api/projects/p",
        K_AGENT: "asst_1",
    }
    assert agents_endpoint_for_client(cfg) == "project_conn;"


def test_agents_endpoint_falls_back_to_project_url():
    cfg = {K_CONN: "", K_ENDPOINT: "https://x.services.ai.azure.com/api/projects/p", K_AGENT: "a"}
    assert agents_endpoint_for_client(cfg) == "https://x.services.ai.azure.com/api/projects/p"


def test_azure_agent_runtime_ready_requires_both():
    assert azure_agent_runtime_ready({K_ENDPOINT: "https://e", K_AGENT: ""}) is False
    assert azure_agent_runtime_ready({K_ENDPOINT: "", K_AGENT: "id"}) is False
    assert azure_agent_runtime_ready({K_ENDPOINT: "https://e", K_AGENT: "id"}) is True


def test_get_runtime_azure_settings_reads_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", "https://from-env.example/api/projects/x")
    monkeypatch.setenv("AZURE_AI_AGENT_ID", "agent-env")
    s = get_runtime_azure_settings()
    assert s[K_ENDPOINT] == "https://from-env.example/api/projects/x"
    assert s[K_AGENT] == "agent-env"
