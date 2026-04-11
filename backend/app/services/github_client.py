from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

GITHUB_API = "https://api.github.com"


@dataclass
class RepoRef:
    owner: str
    name: str


def parse_github_repo_url(url: str) -> RepoRef:
    u = url.strip().rstrip("/")
    if u.endswith(".git"):
        u = u[:-4]
    parsed = urlparse(u)
    host = (parsed.hostname or "").lower()
    if "github.com" not in host:
        raise ValueError("URL deve ser um repositório github.com")
    path = parsed.path.strip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("Caminho inválido: esperado owner/repo")
    return RepoRef(owner=parts[0], name=parts[1])


def _headers(token: str | None) -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _github_json_message(r: httpx.Response) -> str:
    try:
        j = r.json()
        m = j.get("message")
        return str(m).strip() if m else ""
    except Exception:
        return ""


async def github_list_tags(owner: str, repo: str, token: str | None) -> list[str]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}/tags", headers=_headers(token))
        extra = _github_json_message(r)
        suffix = f" Detalhe GitHub: {extra}" if extra else ""

        if r.status_code == 401:
            raise ValueError(
                "GitHub recusou o token (401). Volte a ligar a conta com login OAuth GitHub na plataforma "
                "(token expirado ou revogado; scopes devem incluir acesso ao repositório)."
                + suffix
            )
        if r.status_code == 403:
            raise ValueError(
                "GitHub negou o acesso (403). Repositório privado exige token com scope 'repo'; "
                "verifique também limites de taxa da API."
                + suffix
            )
        if r.status_code == 404:
            if not token:
                raise ValueError(
                    "Repositório não encontrado ou inacessível sem autenticação. "
                    "Para repositórios privados: ligue a sua conta com OAuth GitHub na plataforma. "
                    "Confirme também que a URL está no formato https://github.com/dono/repositório."
                    + suffix
                )
            raise ValueError(
                "Repositório não encontrado (404) ou o token não tem permissão para o ver. "
                "Confira dono/nome do repo na URL, se o repositório é privado (token com 'repo') e se o utilizador OAuth tem acesso ao repo."
                + suffix
            )
        r.raise_for_status()
        data = r.json()
        return [str(x["name"]) for x in data]


async def github_verify_ref(owner: str, repo: str, ref: str, token: str | None) -> bool:
    """Verifica se ref (tag ou branch) resolve para um commit."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits/{ref}",
            headers=_headers(token),
        )
        return r.status_code == 200


def _sync_headers(token: str | None) -> dict[str, str]:
    return _headers(token)


def _docs_tree_blob_supported(path: str, prefix: str) -> bool:
    """Ficheiros em docs/: Markdown e XML (ex. BPMN 2.0)."""
    p = path or ""
    if not p.startswith(prefix):
        return False
    low = p.lower()
    return low.endswith(".md") or low.endswith(".xml")


def fetch_doc_markdown_sync(owner: str, repo: str, ref: str, token: str | None) -> tuple[list[tuple[str, str, str]], str | None]:
    """
    Retorna lista (path_relativo, titulo, conteúdo) — Markdown ou XML em texto — e erro se docs/ vazia/ausente.
    """
    prefixes = ("docs/", "Docs/")
    with httpx.Client(timeout=60) as client:
        r = client.get(f"{GITHUB_API}/repos/{owner}/{repo}/commits/{ref}", headers=_sync_headers(token))
        if r.status_code != 200:
            return [], f"Ref inválida ou sem acesso (HTTP {r.status_code})"
        commit = r.json()
        tree_sha = commit.get("commit", {}).get("tree", {}).get("sha")
        if not tree_sha:
            return [], "Não foi possível obter árvore do commit"
        tr = client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{tree_sha}",
            params={"recursive": "true"},
            headers=_sync_headers(token),
        )
        if tr.status_code != 200:
            return [], f"Erro ao ler árvore Git (HTTP {tr.status_code})"
        tree = tr.json()
        items: list[dict[str, Any]] = tree.get("tree", [])
        chosen_prefix: str | None = None
        for pfx in prefixes:
            if any(_docs_tree_blob_supported(it.get("path") or "", pfx) for it in items if it.get("type") == "blob"):
                chosen_prefix = pfx
                break
        if chosen_prefix is None:
            for pfx in prefixes:
                base = pfx.rstrip("/")
                if any(
                    it.get("type") == "tree"
                    and (
                        (it.get("path") or "") == base
                        or (it.get("path") or "").startswith(pfx)
                    )
                    for it in items
                ):
                    return [], f"Pasta {pfx.rstrip('/')} existe mas não há arquivos .md ou .xml"
            return [], "Pasta docs/ não encontrada nesta referência"

        out: list[tuple[str, str, str]] = []
        for it in items:
            if it.get("type") != "blob":
                continue
            path = it.get("path") or ""
            if not _docs_tree_blob_supported(path, chosen_prefix):
                continue
            sha = it.get("sha")
            if not sha:
                continue
            br = client.get(f"{GITHUB_API}/repos/{owner}/{repo}/git/blobs/{sha}", headers=_sync_headers(token))
            if br.status_code != 200:
                continue
            blob = br.json()
            if blob.get("encoding") != "base64" or not blob.get("content"):
                continue
            raw = base64.b64decode(blob["content"]).decode("utf-8", errors="replace")
            leaf = path.rsplit("/", 1)[-1]
            low = leaf.lower()
            if low.endswith(".md"):
                title = leaf.removesuffix(".md").removesuffix(".MD")
            elif low.endswith(".xml"):
                title = leaf.removesuffix(".xml").removesuffix(".XML")
            else:
                title = leaf
            out.append((path, title, raw))
        out.sort(key=lambda x: x[0])
        if not out:
            return [], "Nenhum arquivo .md ou .xml encontrado em docs/"
        return out, None
