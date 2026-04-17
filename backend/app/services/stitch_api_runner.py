"""Chama o runner Node `@google/stitch-sdk` (API MCP Google Stitch — não é o site stitch.withgoogle.com)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from io import BytesIO
from pathlib import Path

import anyio
import httpx

from app.core.config import settings
from app.services.storage import upload_fileobj

logger = logging.getLogger(__name__)

_RUNNER_DIR = Path(__file__).resolve().parents[2] / "stitch_runner"
_RUNNER_SCRIPT = _RUNNER_DIR / "run.mjs"
_EXPORT_SCRIPT = _RUNNER_DIR / "export_themes.mjs"


def stitch_runner_paths_ok() -> bool:
    return _RUNNER_SCRIPT.is_file() and (_RUNNER_DIR / "node_modules").is_dir()


def stitch_api_configured() -> bool:
    return bool((getattr(settings, "stitch_api_key", None) or "").strip()) and bool(shutil.which("node")) and stitch_runner_paths_ok()


def stitch_api_status_detail() -> str:
    if not (getattr(settings, "stitch_api_key", None) or "").strip():
        return "Defina STITCH_API_KEY no ambiente (Google Stitch API / Labs)."
    if not shutil.which("node"):
        return "Node.js não encontrado no PATH (necessário para o runner stitch_runner/run.mjs)."
    if not stitch_runner_paths_ok():
        return "Instale dependências: cd backend/stitch_runner && npm ci"
    return ""


async def run_stitch_generate(
    *,
    prompt: str,
    project_title: str | None,
    stitch_project_id: str | None,
) -> dict[str, str]:
    """
    Executa o runner e devolve dict com stitch_project_id, screen_id, html_url, image_url.
    Levanta RuntimeError em falha.
    """
    if not stitch_api_configured():
        raise RuntimeError(stitch_api_status_detail() or "Stitch API indisponível")

    key = (settings.stitch_api_key or "").strip()
    env = {**os.environ, "STITCH_API_KEY": key}
    payload = {
        "prompt": prompt.strip(),
        "projectTitle": (project_title or "SysGen prototype").strip(),
    }
    sid = (stitch_project_id or getattr(settings, "stitch_project_id", None) or "").strip()
    if sid:
        payload["projectId"] = sid

    proc = await asyncio.create_subprocess_exec(
        "node",
        str(_RUNNER_SCRIPT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(_RUNNER_DIR),
    )
    out_b, err_b = await proc.communicate(input=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    err_s = (err_b or b"").decode("utf-8", errors="replace").strip()
    out_s = (out_b or b"").decode("utf-8", errors="replace").strip()
    if err_s:
        logger.warning("stitch_runner stderr: %s", err_s[:2000])

    if proc.returncode != 0:
        raise RuntimeError(out_s or err_s or f"stitch runner exit {proc.returncode}")

    try:
        data = json.loads(out_s.splitlines()[-1] if out_s else "{}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Resposta inválida do runner Stitch: {out_s[:500]}") from e

    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "Falha desconhecida no Stitch API")

    return {
        "stitch_project_id": str(data.get("stitchProjectId", "")),
        "screen_id": str(data.get("screenId", "")),
        "html_url": str(data.get("htmlUrl", "")),
        "image_url": str(data.get("imageUrl", "")),
    }


def _safe_path_segment(s: str, max_len: int = 96) -> str:
    t = "".join(c if c.isalnum() or c in "-_" else "_" for c in (s or ""))
    while "__" in t:
        t = t.replace("__", "_")
    return (t.strip("_") or "item")[:max_len]


def _project_name_for_path(name: str) -> str:
    """Nome do projeto seguro para usar como segmento de caminho (prototipo/<isto>/id)."""
    s = (name or "").strip() or "projeto"
    out: list[str] = []
    for c in s:
        if c.isalnum() or c in "-_.":
            out.append(c)
        elif c in " \t\n\r":
            out.append("_")
        else:
            out.append("_")
    t = "".join(out)
    while "__" in t:
        t = t.replace("__", "_")
    return (t.strip("_") or "projeto")[:128]


def _screen_page_title(screen: dict) -> str:
    """Título legível da página (evita usar só o ID técnico do ecrã)."""
    top = screen.get("title")
    if top is not None and str(top).strip():
        return str(top).strip()
    raw = screen.get("raw")
    if isinstance(raw, dict):
        for k in ("title", "displayName", "pageTitle", "screenTitle"):
            v = raw.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        name = raw.get("name")
        if isinstance(name, str) and name.strip():
            if "/screens/" in name:
                return name.split("/screens/")[-1][:200] or str(screen.get("screenId") or "ecra")
            return name.strip()[:200]
    for k in ("title", "displayName"):
        v = screen.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return str(screen.get("screenId") or "ecra")


def _unique_screen_folder_keys(screens: list[dict]) -> list[str]:
    """Um nome de pasta por ecrã, baseado no título; desambigua colisões."""
    seen: set[str] = set()
    keys: list[str] = []
    for s in screens:
        label = _screen_page_title(s)
        base = _safe_path_segment(label, 96)
        if not base:
            base = _safe_path_segment(str(s.get("screenId") or "ecra"), 48)
        sid_short = _safe_path_segment(str(s.get("screenId") or "x"), 24)
        key = base
        if key in seen:
            key = f"{base}_{sid_short}"
        n = 2
        while key in seen:
            key = f"{base}_{n}"
            n += 1
        seen.add(key)
        keys.append(key)
    return keys


def _content_type_for_export_path(rel: str) -> str | None:
    r = rel.lower()
    if r.endswith(".json"):
        return "application/json"
    if r.endswith(".html"):
        return "text/html; charset=utf-8"
    if r.endswith(".svg"):
        return "image/svg+xml"
    if r.endswith(".png"):
        return "image/png"
    if r.endswith(".jpg") or r.endswith(".jpeg"):
        return "image/jpeg"
    if r.endswith(".webp"):
        return "image/webp"
    if r.endswith(".txt"):
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


def _image_ext_from_content_type(ct: str) -> str:
    c = (ct or "").lower()
    if "jpeg" in c or "jpg" in c:
        return ".jpg"
    if "webp" in c:
        return ".webp"
    if "png" in c:
        return ".png"
    if "svg" in c:
        return ".svg"
    return ".bin"


async def _screen_files_under_title_folder(
    client: httpx.AsyncClient,
    screen: dict,
    folder_key: str,
    export_order: int,
) -> list[tuple[str, bytes]]:
    """Ficheiros de um ecrã sob `folder_key/` (nome derivado do título da página)."""
    chunk: list[tuple[str, bytes]] = []
    raw = screen.get("raw")
    slim = {k: v for k, v in screen.items() if k != "raw"}
    slim["exportOrder"] = export_order
    chunk.append(
        (f"{folder_key}/meta.json", json.dumps(slim, ensure_ascii=False, indent=2, default=str).encode("utf-8")),
    )
    if raw is not None:
        chunk.append(
            (
                f"{folder_key}/get_screen.json",
                json.dumps(raw, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
            ),
        )
    html_u = (screen.get("htmlUrl") or "").strip()
    img_u = (screen.get("imageUrl") or "").strip()
    if html_u:
        try:
            r = await client.get(html_u)
            r.raise_for_status()
            ct = (r.headers.get("content-type") or "").lower()
            suf = ".html"
            if "svg" in ct:
                suf = ".svg"
            chunk.append((f"{folder_key}/ecra{suf}", r.content))
        except Exception as e:
            chunk.append(
                (f"{folder_key}/html-erro.txt", f"Falha ao descarregar HTML: {e}\nURL: {html_u}\n".encode()),
            )
    if img_u:
        try:
            r = await client.get(img_u)
            r.raise_for_status()
            ext = _image_ext_from_content_type(r.headers.get("content-type") or "")
            chunk.append((f"{folder_key}/preview{ext}", r.content))
        except Exception as e:
            chunk.append(
                (f"{folder_key}/imagem-erro.txt", f"Falha ao descarregar imagem: {e}\nURL: {img_u}\n".encode()),
            )
    return chunk


async def build_ecras_only_entries(payload: dict) -> list[tuple[str, bytes]]:
    """Apenas ficheiros por ecrã (sem export.json, temas nem projeto)."""
    screens = payload.get("screens") or []
    if not screens:
        return []
    folder_keys = _unique_screen_folder_keys(screens)
    async with httpx.AsyncClient(follow_redirects=True, timeout=180.0) as client:
        batches = await asyncio.gather(
            *[
                _screen_files_under_title_folder(client, screens[i], folder_keys[i], i)
                for i in range(len(screens))
            ],
        )
    out: list[tuple[str, bytes]] = []
    for b in batches:
        out.extend(b)
    return out


async def save_stitch_export_to_minio(project_id: int, project_name: str, payload: dict) -> str:
    """
    Grava só os ecrãs em `prototipo/{nome_projeto}/{id}/<pasta_título>/...` no bucket S3/MinIO.
    Devolve o prefixo no bucket.
    """
    if not getattr(settings, "s3_endpoint_url", None):
        raise RuntimeError(
            "MinIO/S3 não configurado. Defina S3_ENDPOINT_URL, S3_BUCKET e credenciais no ambiente.",
        )
    entries = await build_ecras_only_entries(payload)
    if not entries:
        raise RuntimeError("Não há ecrãs no projeto Stitch para gravar.")

    name_seg = _project_name_for_path(project_name)
    prefix = f"prototipo/{name_seg}/{project_id}"

    def _upload_all() -> None:
        for rel, data in entries:
            key = f"{prefix}/{rel}"
            upload_fileobj(BytesIO(data), key, _content_type_for_export_path(rel))

    await anyio.to_thread.run_sync(_upload_all)
    return prefix


async def run_stitch_collect_export(stitch_project_id: str) -> dict:
    """
    Chama export_themes.mjs: get_project, list_design_systems, get_screen por ecrã.
    Levanta RuntimeError em falha.
    """
    if not stitch_api_configured():
        raise RuntimeError(stitch_api_status_detail() or "Stitch API indisponível")
    if not _EXPORT_SCRIPT.is_file():
        raise RuntimeError("Falta stitch_runner/export_themes.mjs (actualize o repositório).")

    sid = (stitch_project_id or "").strip()
    if not sid:
        raise RuntimeError("stitch_project_id em falta")

    key = (settings.stitch_api_key or "").strip()
    env = {**os.environ, "STITCH_API_KEY": key}
    payload = {"projectId": sid}

    proc = await asyncio.create_subprocess_exec(
        "node",
        str(_EXPORT_SCRIPT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(_RUNNER_DIR),
    )
    out_b, err_b = await proc.communicate(input=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    err_s = (err_b or b"").decode("utf-8", errors="replace").strip()
    out_s = (out_b or b"").decode("utf-8", errors="replace").strip()
    if err_s:
        logger.warning("stitch export stderr: %s", err_s[:2000])

    if proc.returncode != 0:
        raise RuntimeError(out_s or err_s or f"stitch export exit {proc.returncode}")

    try:
        data = json.loads(out_s.splitlines()[-1] if out_s else "{}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Resposta inválida do export Stitch: {out_s[:500]}") from e

    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "Falha no export Stitch")
    return data
