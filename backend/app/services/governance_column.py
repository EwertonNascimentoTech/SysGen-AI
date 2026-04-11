"""Regras efetivas de uma coluna Kanban (catálogo + legado)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kanban import KanbanTemplateColumn
from app.services.column_rules import parse_rules
from app.services.governance_catalog import resolve_effective_rule_flags


async def effective_rules_for_column(
    session: AsyncSession,
    column: KanbanTemplateColumn,
) -> dict:
    d = parse_rules(column.rules_json)
    ids = d.get("applied_rule_ids") or []
    if ids:
        eff = await resolve_effective_rule_flags(session, ids)
        eff["color_hex"] = d.get("color_hex")
        eff["applied_rule_ids"] = ids
        return eff
    return d
