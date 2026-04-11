"""Regras de governança por coluna (JSON em KanbanTemplateColumn.rules_json)."""

from __future__ import annotations

import json
from typing import Any

DEFAULT_COLOR = "#64748b"

PALETTE = ["#64748b", "#3b82f6", "#0d9488", "#ca8a04", "#9333ea", "#e11d48"]


def default_rules_dict(index: int = 0) -> dict[str, Any]:
    return {
        "color_hex": PALETTE[index % len(PALETTE)],
        "require_description": False,
        "require_attachment_audit": False,
        "require_po_assigned": False,
        "require_github_tag": False,
        "min_tag_count": 0,
        "applied_rule_ids": [],
    }


def parse_rules(rules_json: str | None) -> dict[str, Any]:
    base = default_rules_dict(0)
    if not rules_json or not rules_json.strip():
        return base
    try:
        raw = json.loads(rules_json)
        if not isinstance(raw, dict):
            return base
    except json.JSONDecodeError:
        return base
    out = {**base}
    for k in (
        "color_hex",
        "require_description",
        "require_attachment_audit",
        "require_po_assigned",
        "require_github_tag",
        "min_tag_count",
    ):
        if k in raw:
            out[k] = raw[k]
    ids_raw = raw.get("applied_rule_ids")
    if isinstance(ids_raw, list):
        clean_ids: list[int] = []
        for i in ids_raw:
            try:
                clean_ids.append(int(i))
            except (TypeError, ValueError):
                pass
        out["applied_rule_ids"] = clean_ids
    else:
        out["applied_rule_ids"] = []
    if isinstance(out.get("color_hex"), str) and out["color_hex"].startswith("#"):
        pass
    else:
        out["color_hex"] = DEFAULT_COLOR
    try:
        out["min_tag_count"] = max(0, int(out.get("min_tag_count") or 0))
    except (TypeError, ValueError):
        out["min_tag_count"] = 0
    for b in (
        "require_description",
        "require_attachment_audit",
        "require_po_assigned",
        "require_github_tag",
    ):
        out[b] = bool(out.get(b))
    return out


def merge_rules(existing_json: str | None, patch: dict[str, Any]) -> dict[str, Any]:
    cur = parse_rules(existing_json)
    for k, v in patch.items():
        if v is None:
            continue
        if k == "min_tag_count":
            try:
                cur[k] = max(0, int(v))
            except (TypeError, ValueError):
                pass
        elif k == "color_hex" and isinstance(v, str) and v.strip().startswith("#"):
            cur[k] = v.strip()[:16]
        elif k == "applied_rule_ids" and isinstance(v, list):
            clean_ids: list[int] = []
            for i in v:
                try:
                    clean_ids.append(int(i))
                except (TypeError, ValueError):
                    pass
            cur["applied_rule_ids"] = clean_ids
        elif k.startswith("require_"):
            cur[k] = bool(v)
    return cur


def dumps_rules(d: dict[str, Any]) -> str:
    clean = parse_rules(json.dumps(d))
    return json.dumps(clean, ensure_ascii=False)
