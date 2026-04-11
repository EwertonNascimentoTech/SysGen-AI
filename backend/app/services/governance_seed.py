"""Catálogo inicial de regras de avanço + vínculo com fases existentes (uma vez)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.governance_advance_rule import GovernanceAdvanceRule
from app.models.kanban import KanbanTemplateColumn
from app.services.column_rules import dumps_rules, parse_rules
from app.services.governance_catalog import rule_flags_from_catalog_rows


DEFAULT_RULES: list[dict] = [
    {
        "name": "Descrição mínima do projeto",
        "description": "Nome/descrição do projeto com pelo menos 10 caracteres antes de avançar.",
        "rule_key": "require_description",
        "min_tags_value": None,
    },
    {
        "name": "Anexo de auditoria",
        "description": "Exige documento de auditoria (PDF ou tipo com 'audit' / 'auditoria').",
        "rule_key": "require_attachment_audit",
        "min_tags_value": None,
    },
    {
        "name": "Product Owner atribuído",
        "description": "PO ou responsável válido preenchido no projeto.",
        "rule_key": "require_po_assigned",
        "min_tags_value": None,
    },
    {
        "name": "Tag GitHub informada",
        "description": "Pelo menos uma tag ou referência GitHub no projeto.",
        "rule_key": "require_github_tag",
        "min_tags_value": None,
    },
    *[
        {
            "name": f"Mínimo de {n} tag(s) GitHub",
            "description": f"Exige pelo menos {n} tag(s) separadas por vírgula no campo GitHub.",
            "rule_key": "min_tag_count",
            "min_tags_value": n,
        }
        for n in (1, 2, 3, 4, 5)
    ],
    {
        "name": "Repositório GitHub vinculado",
        "description": "URL do repositório preenchida no cadastro do projeto.",
        "rule_key": "require_github_repo",
        "min_tags_value": None,
        "on_violation": "bloqueio",
    },
    {
        "name": "Metodologia PRD",
        "description": "Projeto cadastrado com metodologia PRD.",
        "rule_key": "require_methodology_prd",
        "min_tags_value": None,
        "on_violation": "bloqueio",
    },
    {
        "name": "Pelo menos um anexo",
        "description": "Exige qualquer arquivo anexado ao projeto.",
        "rule_key": "require_any_attachment",
        "min_tags_value": None,
        "on_violation": "alerta",
    },
]


async def ensure_governance_advance_rules(session: AsyncSession) -> None:
    n = await session.scalar(select(func.count()).select_from(GovernanceAdvanceRule))
    if n and n > 0:
        return
    for row in DEFAULT_RULES:
        session.add(
            GovernanceAdvanceRule(
                name=row["name"],
                description=row["description"],
                rule_key=row["rule_key"],
                min_tags_value=row["min_tags_value"],
                active=True,
                on_violation=str(row.get("on_violation") or "bloqueio"),
            )
        )
    await session.flush()

    by_key: dict[str, list[GovernanceAdvanceRule]] = {}
    all_rules = (await session.execute(select(GovernanceAdvanceRule))).scalars().all()
    for r in all_rules:
        by_key.setdefault(r.rule_key, []).append(r)

    def pick(rule_key: str, min_v: int | None = None) -> GovernanceAdvanceRule | None:
        lst = by_key.get(rule_key) or []
        if rule_key == "min_tag_count" and min_v is not None:
            for x in lst:
                if x.min_tags_value == min_v:
                    return x
            return None
        return lst[0] if lst else None

    cols = (await session.execute(select(KanbanTemplateColumn))).scalars().all()
    for col in cols:
        d = parse_rules(col.rules_json)
        ids: list[int] = []
        if d.get("require_description"):
            p = pick("require_description")
            if p:
                ids.append(p.id)
        if d.get("require_attachment_audit"):
            p = pick("require_attachment_audit")
            if p:
                ids.append(p.id)
        if d.get("require_po_assigned"):
            p = pick("require_po_assigned")
            if p:
                ids.append(p.id)
        if d.get("require_github_tag"):
            p = pick("require_github_tag")
            if p:
                ids.append(p.id)
        m = int(d.get("min_tag_count") or 0)
        if m > 0:
            p = pick("min_tag_count", m)
            if p:
                ids.append(p.id)
        if not ids:
            continue
        picked = [r for r in all_rules if r.id in ids]
        flags = rule_flags_from_catalog_rows(picked)
        d["applied_rule_ids"] = ids
        d["require_description"] = bool(flags.get("require_description"))
        d["require_attachment_audit"] = bool(flags.get("require_attachment_audit"))
        d["require_po_assigned"] = bool(flags.get("require_po_assigned"))
        d["require_github_tag"] = bool(flags.get("require_github_tag"))
        d["min_tag_count"] = int(flags.get("min_tag_count") or 0)
        col.rules_json = dumps_rules(d)

    await session.commit()
