"""Verificação HMAC dos webhooks Cursor Cloud Agent (sem HTTP nem BD)."""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional

import pytest

from app.services.cursor_cloud_agents import verify_cursor_webhook_signature


def _sign(secret: str, raw: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def test_verify_accepts_valid_signature() -> None:
    secret = "a" * 32
    raw = b'{"id":"bc_test","status":"FINISHED","event":"statusChange"}'
    sig = _sign(secret, raw)
    assert verify_cursor_webhook_signature(secret, raw, sig) is True


def test_verify_rejects_tampered_body() -> None:
    secret = "b" * 32
    raw = b'{"id":"bc_test","status":"FINISHED"}'
    sig = _sign(secret, raw)
    assert verify_cursor_webhook_signature(secret, raw + b" ", sig) is False


def test_verify_rejects_wrong_secret() -> None:
    raw = b'{"id":"x"}'
    sig = _sign("c" * 32, raw)
    assert verify_cursor_webhook_signature("d" * 32, raw, sig) is False


@pytest.mark.parametrize(
    "header",
    [None, "", "md5=deadbeef", "sha256=00", "sha256=gg"],
)
def test_verify_rejects_bad_headers(header: Optional[str]) -> None:
    secret = "e" * 32
    raw = b"{}"
    assert verify_cursor_webhook_signature(secret, raw, header) is False


def test_verify_rejects_empty_secret() -> None:
    raw = b"{}"
    sig = _sign("f" * 32, raw)
    assert verify_cursor_webhook_signature("", raw, sig) is False
