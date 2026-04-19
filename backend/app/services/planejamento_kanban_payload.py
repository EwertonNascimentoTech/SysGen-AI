"""Extração e formatação do planejamento para cards Kanban (sem dependência de ORM)."""

from __future__ import annotations

import json
from typing import Any

MARKER = "__SYSGEN_PLANEJAMENTO__"

PREP_ROOT_KEYS = (
    "preparacao",
    "preparação",
    "setup_inicial",
    "fundacao",
    "fundacao_tecnica",
    "antes_fases",
    "ambiente_arquitetura",
    "pre_fases",
)

CHILD_KEYS = (
    "itens",
    "atividades",
    "items",
    "tasks",
    "historias",
    "children",
    "subitens",
    "filhos",
)

# Alinhado a `LAYOUT_BLOCK_KEYS` em `PlanejamentoRoadmapView.vue` — caminhos export (ex.: prototipo_export/…).
LAYOUT_BLOCK_KEYS: tuple[str, ...] = (
    "layout",
    "layouts",
    "caminhos_layout",
    "ficheiros_layout",
    "prototipo_paths",
    "html_paths",
    "paths",
)

# Chaves onde o agente costuma colocar o relatório «o que foi entregue» (ficheiros, bullets, etc.).
ENTREGA_BLOCK_KEYS: tuple[str, ...] = (
    "o_que_foi_entregue",
    "oque_foi_entregue",
    "entrega_resumo",
    "entrega",
    "entregue",
    "entregaveis",
    "entregáveis",
    "what_was_delivered",
    "deliverables",
    "resumo_entrega",
    "agent_delivery",
    "relatorio_entrega",
    "relatório_entrega",
)

DEFAULT_PREP_TITLE = "Preparação: ambiente, arquitetura e Cursor"
DESC_MAX = 7800
ENTREGA_MAX = 16000


def _obj(v: Any) -> dict[str, Any] | None:
    if v is None or not isinstance(v, dict):
        return None
    return v


def _read_title(o: dict[str, Any]) -> str:
    for k in ("titulo", "nome", "title", "epico", "fase", "label"):
        t = o.get(k)
        if isinstance(t, str) and t.strip():
            return t.strip()
    return ""


def _child_array_key(o: dict[str, Any]) -> str | None:
    for k in CHILD_KEYS:
        v = o.get(k)
        if isinstance(v, list) and len(v) > 0:
            return k
    for k in sorted(o.keys()):
        v = o.get(k)
        if isinstance(v, list) and any(x is not None and isinstance(x, (dict, str)) for x in v):
            return k
    return None


def _item_title(it: Any) -> str:
    if isinstance(it, str) and it.strip():
        return it.strip()
    io = _obj(it)
    if not io:
        return "—"
    return _read_title(io) or "—"


def _item_layout_block(io: dict[str, Any]) -> str:
    """Texto de caminhos / layout (string ou lista de strings), como no detalhe do roadmap."""
    for k in LAYOUT_BLOCK_KEYS:
        if k not in io:
            continue
        v = io[k]
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list) and v:
            parts = [str(x).strip() for x in v if isinstance(x, str) and x.strip()]
            if parts:
                return " e ".join(parts)
    return ""


def _item_entrega_block(io: dict[str, Any]) -> str:
    """Texto «o que foi entregue»: string longa ou lista de linhas (ficheiros / bullets)."""
    for k in ENTREGA_BLOCK_KEYS:
        if k not in io:
            continue
        v = io[k]
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list) and v:
            lines: list[str] = []
            for x in v:
                if isinstance(x, str) and x.strip():
                    lines.append(x.strip())
                elif isinstance(x, dict):
                    t = _read_title(x)
                    if t and t != "—":
                        lines.append(t)
            if lines:
                return "\n".join(lines)
    return ""


def _item_description(it: Any) -> str:
    io = _obj(it)
    if not io:
        return ""
    base = ""
    for k in ("descricao", "descricao_detalhada", "sumario", "texto", "description", "detalhe"):
        v = io.get(k)
        if isinstance(v, str) and v.strip():
            base = v.strip()
            break
    layout = _item_layout_block(io)
    if layout:
        if base:
            return f"{base}\n\nlayout: {layout}"
        return f"layout: {layout}"
    return base


def flatten_planejamento_for_kanban(parsed: Any) -> list[tuple[str, str, str, str]]:
    """
    Lista ordenada de (titulo_bloco_fase, titulo_item, descricao_item, entrega_resumo) para criar cards no Kanban.
    Ordem: itens de preparacao (primeira chave encontrada), depois cada fase em `fases`/`phases`/`etapas`.
    """
    rows: list[tuple[str, str, str, str]] = []

    if isinstance(parsed, list):
        for ph in parsed:
            po = _obj(ph)
            if not po:
                continue
            phase_title = _read_title(po) or "Fase"
            ck = _child_array_key(po)
            if not ck:
                continue
            arr = po.get(ck)
            if not isinstance(arr, list):
                continue
            for it in arr:
                if isinstance(it, (dict, str)):
                    io = _obj(it)
                    entrega = _item_entrega_block(io) if io else ""
                    rows.append((phase_title, _item_title(it), _item_description(it), entrega))
        return rows

    root = _obj(parsed)
    if not root:
        return rows

    for pk in PREP_ROOT_KEYS:
        if pk not in root:
            continue
        po = _obj(root.get(pk))
        if not po:
            continue
        phase_title = _read_title(po) or DEFAULT_PREP_TITLE
        ck = _child_array_key(po)
        if not ck:
            break
        arr = po.get(ck)
        if not isinstance(arr, list):
            break
        for it in arr:
            if isinstance(it, (dict, str)):
                io = _obj(it)
                entrega = _item_entrega_block(io) if io else ""
                rows.append((phase_title, _item_title(it), _item_description(it), entrega))
        break

    for prop in ("fases", "phases", "etapas"):
        arr = root.get(prop)
        if not isinstance(arr, list) or not arr:
            continue
        for ph in arr:
            po = _obj(ph)
            if not po:
                continue
            phase_title = _read_title(po) or "Fase"
            ck = _child_array_key(po)
            if not ck:
                continue
            sub = po.get(ck)
            if not isinstance(sub, list):
                continue
            for it in sub:
                if isinstance(it, (dict, str)):
                    io = _obj(it)
                    entrega = _item_entrega_block(io) if io else ""
                    rows.append((phase_title, _item_title(it), _item_description(it), entrega))
        break

    return rows


TITLE_MAX = 512
BLOCO_TAG_MAX = 512


def build_task_title(item_title: str) -> str:
    """Título do cartão no quadro = nome da tarefa (limite 512)."""
    rest = (item_title or "—").strip()
    if len(rest) > TITLE_MAX:
        rest = rest[: TITLE_MAX - 1] + "…"
    return rest


def truncate_entrega_resumo(text: str) -> str | None:
    """Limita o campo persistido (TEXT)."""
    t = (text or "").strip()
    if not t:
        return None
    if len(t) > ENTREGA_MAX:
        return t[: ENTREGA_MAX - 1] + "…"
    return t


def truncate_bloco_tag(phase_title: str) -> str | None:
    """Texto da tag de bloco/fase (ex.: Preparação: ambiente…)."""
    t = (phase_title or "").strip()
    if not t:
        return None
    if len(t) > BLOCO_TAG_MAX:
        return t[: BLOCO_TAG_MAX - 1] + "…"
    return t


def build_card_description(item_title: str, item_desc: str) -> str:
    desc_body = (item_desc or "").strip() or (item_title or "—").strip()
    body = (
        f"{MARKER}\n"
        f"Título: {item_title.strip()}\n"
        f"Descrição: {desc_body}\n"
    )
    if len(body) > DESC_MAX:
        body = body[: DESC_MAX - 1] + "…"
    return body


def parse_planejamento_json(raw: str) -> Any | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None
