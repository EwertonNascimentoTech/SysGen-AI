"""Anexos do export Stitch/MinIO para o agente de planejamento (só HTML + PNG)."""

from __future__ import annotations

import base64

from app.services.storage import list_object_keys_under_prefix, read_object_bytes, relative_paths_under_prefix

_PLANEJAMENTO_EXPORT_SUFFIXES = frozenset({".html", ".htm", ".png"})


def mime_for_stitch_path(rel: str) -> str:
    low = rel.lower()
    if low.endswith((".html", ".htm")):
        return "text/html; charset=utf-8"
    if low.endswith(".png"):
        return "image/png"
    return "application/octet-stream"


def planejamento_export_path_included(rel: str) -> bool:
    """Apenas `.html`, `.htm` e `.png` do export entram no pedido ao agente."""
    i = rel.lower().rfind(".")
    if i < 0:
        return False
    return rel[i:].lower() in _PLANEJAMENTO_EXPORT_SUFFIXES


def stitch_export_path_is_text_like(rel: str) -> bool:
    """Alias histórico para testes; equivale a `planejamento_export_path_included`."""
    return planejamento_export_path_included(rel)


def load_stitch_export_attachment_dicts(
    prefix: str,
    *,
    max_file_bytes: int = 400_000,
    max_total_bytes: int = 5_000_000,
) -> tuple[list[dict[str, str]], list[str]]:
    """
    Lê do MinIO apenas ficheiros `.html`/`.htm` e `.png` sob o prefixo do export.

    O teto agregado (`max_total_bytes`) evita ler dezenas de MB para memória; o PRD entra à parte na rota.
    A mensagem final para o Azure AI Agents continua limitada a 256k caracteres — ver `azure_agent_limits`.
    """
    warnings: list[str] = []
    pfx = prefix.strip().rstrip("/")
    keys = list_object_keys_under_prefix(pfx)
    rels = [r for r in relative_paths_under_prefix(pfx, keys) if planejamento_export_path_included(r)]
    out: list[dict[str, str]] = []
    total = 0
    for rel in sorted(rels):
        key = f"{pfx}/{rel}"
        try:
            data = read_object_bytes(key)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{rel}: {e!s}")
            continue
        if len(data) > max_file_bytes:
            data = data[:max_file_bytes] + b"\n\n... [truncado pelo servidor]"
            warnings.append(f"{rel}: truncado a {max_file_bytes} bytes")
        if total + len(data) > max_total_bytes:
            warnings.append(
                f"Limite total de anexos do protótipo ({max_total_bytes:,} bytes) atingido "
                f"após {total:,} bytes incluídos; ficheiros restantes por ordem alfabética foram omitidos."
            )
            break
        total += len(data)
        b64 = base64.standard_b64encode(data).decode("ascii")
        out.append(
            {
                "filename": f"prototipo_export/{rel}",
                "mime_type": mime_for_stitch_path(rel),
                "content_base64": b64,
            },
        )
    return out, warnings


def build_minio_prefix_inventory_attachment(
    prefix: str,
    *,
    max_lines: int = 800,
) -> tuple[dict[str, str] | None, list[str]]:
    """
    Quando não há `.html`/`.htm`/`.png` no export, gera um anexo com a listagem de caminhos no prefixo.
    """
    warnings: list[str] = []
    pfx = prefix.strip().rstrip("/")
    try:
        keys = list_object_keys_under_prefix(pfx)
    except Exception as e:  # noqa: BLE001
        return None, [f"MinIO list: {e!s}"]
    rels = relative_paths_under_prefix(pfx, keys)
    if not rels:
        return None, ["Prefixo MinIO sem ficheiros listados."]
    sorted_rels = sorted(rels)
    if len(sorted_rels) > max_lines:
        warnings.append(f"Inventário truncado a {max_lines} linhas ({len(sorted_rels)} no total).")
        sorted_rels = sorted_rels[:max_lines]
    body = "Listagem de ficheiros no export MinIO (relativos ao prefixo do projeto):\n" + "\n".join(sorted_rels)
    b64 = base64.standard_b64encode(body.encode("utf-8")).decode("ascii")
    return (
        {
            "filename": "prototipo_export/INVENTORY.txt",
            "mime_type": "text/plain; charset=utf-8",
            "content_base64": b64,
        },
        warnings,
    )
