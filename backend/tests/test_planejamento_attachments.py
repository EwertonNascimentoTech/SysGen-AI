"""Testes utilitários do módulo de anexos de planejamento (sem MinIO)."""

import base64
from datetime import datetime, timezone

from app.schemas.planejamento import PlanejamentoContextOut, PlanejamentoStoredOut
from app.services import planejamento_attachments as pa
from app.services.planejamento_attachments import (
    build_minio_prefix_inventory_attachment,
    mime_for_stitch_path,
    planejamento_export_path_included,
    stitch_export_path_is_text_like,
)
from app.services.azure_runtime_env import get_planejador_agent_id


def test_mime_for_stitch_path() -> None:
    assert "html" in mime_for_stitch_path("ecra/Screen/ecra.html").lower()
    assert mime_for_stitch_path("preview.png") == "image/png"
    assert mime_for_stitch_path("meta.json") == "application/octet-stream"


def test_planejamento_export_path_included() -> None:
    assert planejamento_export_path_included("folder/ecra.html") is True
    assert planejamento_export_path_included("x.PNG") is True
    assert planejamento_export_path_included("x.JSON") is False
    assert planejamento_export_path_included("noext") is False


def test_stitch_export_path_is_text_like_alias() -> None:
    assert stitch_export_path_is_text_like("a.htm") is True
    assert stitch_export_path_is_text_like("b.png") is True
    assert stitch_export_path_is_text_like("c.json") is False


def test_get_planejador_agent_id_from_env(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_AI_AGENT_PLANEJADOR_ID", "  agent-xyz  ")
    assert get_planejador_agent_id() == "agent-xyz"


def test_planejamento_stored_out_schema() -> None:
    now = datetime.now(timezone.utc)
    ctx = PlanejamentoContextOut(
        stack_documentada="Vue + FastAPI",
        methodology="prd",
        github_repo_url=None,
        github_tag=None,
        s3_configured=False,
        github_oauth_configured=False,
        stitch_api_configured=False,
        azure_planejador_ready=False,
    )
    o = PlanejamentoStoredOut(text='{"fases":[]}', saved_at=now, approved_at=None, context=ctx)
    assert o.text == '{"fases":[]}'
    assert o.saved_at == now
    assert o.approved_at is None
    assert o.context.methodology == "prd"


def test_build_minio_prefix_inventory_attachment(monkeypatch) -> None:
    def fake_list(prefix: str) -> list[str]:
        return [f"{prefix}/a.html", f"{prefix}/b.png"]

    monkeypatch.setattr(pa, "list_object_keys_under_prefix", fake_list)
    inv, warns = build_minio_prefix_inventory_attachment("proj/5/export")
    assert inv is not None
    assert inv["filename"] == "prototipo_export/INVENTORY.txt"
    raw = base64.standard_b64decode(inv["content_base64"]).decode("utf-8")
    assert "a.html" in raw and "b.png" in raw
    assert not warns
