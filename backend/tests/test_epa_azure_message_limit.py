"""Limite de tamanho da mensagem user para Azure AI Agents."""

from app.services.azure_agent_limits import (
    AZURE_AGENTS_MAX_USER_MESSAGE_CHARS,
    truncate_string_for_azure_agent_user_message,
)


def test_truncate_string_for_azure_agent_user_message_noop_when_short() -> None:
    s = "hello"
    assert truncate_string_for_azure_agent_user_message(s) == s


def test_truncate_string_for_azure_agent_user_message_caps_length() -> None:
    over = "a" * (AZURE_AGENTS_MAX_USER_MESSAGE_CHARS + 12_000)
    out = truncate_string_for_azure_agent_user_message(over)
    assert len(out) == AZURE_AGENTS_MAX_USER_MESSAGE_CHARS
    assert "TRUNCADO" in out or "limite" in out.lower()
