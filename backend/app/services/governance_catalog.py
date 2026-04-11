"""Resolução de flags de governança a partir do catálogo governance_advance_rules."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.governance_advance_rule import GovernanceAdvanceRule
from app.services.column_rules import default_rules_dict

RULE_KEYS = frozenset(
    {
        "require_description",
        "require_attachment_audit",
        "require_po_assigned",
        "require_github_tag",
        "min_tag_count",
        "require_github_repo",
        "require_methodology_prd",
        "require_any_attachment",
    }
)

VIOLATION_MODES = frozenset({"bloqueio", "alerta"})


def rule_flags_from_catalog_rows(rows: list[GovernanceAdvanceRule]) -> dict[str, Any]:
    out = default_rules_dict(0)
    out["applied_rule_ids"] = []
    out["require_description"] = any(r.rule_key == "require_description" for r in rows)
    out["require_attachment_audit"] = any(r.rule_key == "require_attachment_audit" for r in rows)
    out["require_po_assigned"] = any(r.rule_key == "require_po_assigned" for r in rows)
    out["require_github_tag"] = any(r.rule_key == "require_github_tag" for r in rows)
    mt = 0
    for r in rows:
        if r.rule_key == "min_tag_count" and r.min_tags_value and r.min_tags_value > 0:
            mt = max(mt, int(r.min_tags_value))
    out["min_tag_count"] = mt
    return out


async def load_active_rules_by_ids(
    session: AsyncSession, ids: list[int]
) -> list[GovernanceAdvanceRule]:
    if not ids:
        return []
    result = await session.execute(
        select(GovernanceAdvanceRule).where(
            GovernanceAdvanceRule.id.in_(ids),
            GovernanceAdvanceRule.active.is_(True),
        )
    )
    return list(result.scalars().all())


async def resolve_effective_rule_flags(session: AsyncSession, ids: list[int]) -> dict[str, Any]:
    rows = await load_active_rules_by_ids(session, ids)
    return rule_flags_from_catalog_rows(rows)
