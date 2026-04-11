"""Validação de transição Kanban: catálogo (por regra + bloqueio/alerta) ou legado (flags fundidas)."""

from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.governance_advance_rule import GovernanceAdvanceRule
from app.models.project import Project, ProjectAttachment
from app.models.kanban import KanbanTemplateColumn
from app.schemas.project import GovernanceNotice
from app.services.column_rules import parse_rules
from app.services.governance_catalog import load_active_rules_by_ids


def _po_ok(product_owner: str | None) -> bool:
    s = (product_owner or "").strip()
    return len(s) >= 2 and s not in ("—", "-", "N/A", "n/a")


def href_for_governance_fix(project_id: int, rule_key: str) -> str:
    """Rota no frontend (Vue Router) para o utilizador corrigir a pendência."""
    base = f"/projetos/{project_id}"
    if rule_key in ("require_attachment_audit", "require_any_attachment"):
        return f"{base}?tab=anexos#governance-anexos"
    if rule_key == "require_github_repo":
        return f"{base}?tab=github#governance-repo-url"
    if rule_key in ("require_github_tag", "min_tag_count"):
        return f"{base}?tab=github#governance-github-tag"
    if rule_key == "require_po_assigned":
        return f"{base}?tab=resumo#governance-po"
    if rule_key == "require_description":
        return f"{base}?tab=resumo#governance-nome"
    if rule_key == "require_methodology_prd":
        return f"{base}?tab=resumo#governance-metodologia"
    return f"{base}?tab=resumo"


async def _audit_attachment_exists(session: AsyncSession, project_id: int) -> bool:
    audit_cond = or_(
        ProjectAttachment.attachment_type.ilike("%audit%"),
        ProjectAttachment.attachment_type.ilike("%auditoria%"),
        ProjectAttachment.file_name.ilike("%.pdf"),
        ProjectAttachment.content_type.ilike("%pdf%"),
    )
    n = await session.scalar(
        select(func.count())
        .select_from(ProjectAttachment)
        .where(and_(ProjectAttachment.project_id == project_id, audit_cond))
    )
    return bool(n)


async def _any_attachment_exists(session: AsyncSession, project_id: int) -> bool:
    n = await session.scalar(
        select(func.count()).select_from(ProjectAttachment).where(ProjectAttachment.project_id == project_id)
    )
    return bool(n)


async def violation_message_for_rule(
    session: AsyncSession,
    project: Project,
    row: GovernanceAdvanceRule,
) -> str | None:
    """Mensagem de violação ou None se a regra passa."""
    key = row.rule_key
    if key == "require_po_assigned":
        if not _po_ok(project.product_owner):
            return "Governança: preencha o PO / responsável do projeto antes de avançar para esta fase."
    elif key == "require_github_tag":
        if not (project.github_tag or "").strip():
            return "Governança: informe a tag GitHub (release/branch) exigida para esta fase."
    elif key == "min_tag_count":
        need = int(row.min_tags_value or 0)
        if need < 1:
            return None
        raw = (project.github_tag or "").strip()
        tags = [t.strip() for t in raw.replace(";", ",").split(",") if t.strip()]
        if len(tags) < need:
            return (
                f"Governança: esta fase exige pelo menos {need} tag(s) GitHub (separadas por vírgula)."
            )
    elif key == "require_description":
        if len((project.name or "").strip()) < 10:
            return "Governança: o nome do projeto deve ter pelo menos 10 caracteres (critério de descrição mínima)."
    elif key == "require_attachment_audit":
        if not await _audit_attachment_exists(session, project.id):
            return (
                "Governança: anexe pelo menos um documento de auditoria (PDF ou tipo contendo 'audit' / 'auditoria')."
            )
    elif key == "require_github_repo":
        if not (project.github_repo_url or "").strip():
            return "Governança: vincule a URL do repositório GitHub ao projeto antes de avançar."
    elif key == "require_methodology_prd":
        if (project.methodology or "").strip() != "prd":
            return "Governança: esta fase exige metodologia PRD no cadastro do projeto."
    elif key == "require_any_attachment":
        if not await _any_attachment_exists(session, project.id):
            return "Governança: anexe pelo menos um arquivo ao projeto (qualquer tipo) antes de avançar."
    return None


async def notice_for_catalog_row(
    session: AsyncSession,
    project: Project,
    row: GovernanceAdvanceRule,
) -> GovernanceNotice | None:
    msg = await violation_message_for_rule(session, project, row)
    if not msg:
        return None
    return GovernanceNotice(message=msg, href=href_for_governance_fix(project.id, row.rule_key))


async def _validate_legacy(session: AsyncSession, project: Project, rules: dict) -> list[GovernanceNotice]:
    pid = project.id
    out: list[GovernanceNotice] = []
    if rules.get("require_po_assigned") and not _po_ok(project.product_owner):
        out.append(
            GovernanceNotice(
                message="Governança: preencha o PO / responsável do projeto antes de avançar para esta fase.",
                href=href_for_governance_fix(pid, "require_po_assigned"),
            )
        )
    if rules.get("require_github_tag") and not (project.github_tag or "").strip():
        out.append(
            GovernanceNotice(
                message="Governança: informe a tag GitHub (release/branch) exigida para esta fase.",
                href=href_for_governance_fix(pid, "require_github_tag"),
            )
        )
    min_tags = int(rules.get("min_tag_count") or 0)
    if min_tags > 0:
        raw = (project.github_tag or "").strip()
        tags = [t.strip() for t in raw.replace(";", ",").split(",") if t.strip()]
        if len(tags) < min_tags:
            out.append(
                GovernanceNotice(
                    message=f"Governança: esta fase exige pelo menos {min_tags} tag(s) GitHub (separadas por vírgula).",
                    href=href_for_governance_fix(pid, "min_tag_count"),
                )
            )
    if rules.get("require_description"):
        if len((project.name or "").strip()) < 10:
            out.append(
                GovernanceNotice(
                    message="Governança: o nome do projeto deve ter pelo menos 10 caracteres (critério de descrição mínima).",
                    href=href_for_governance_fix(pid, "require_description"),
                )
            )
    if rules.get("require_attachment_audit"):
        if not await _audit_attachment_exists(session, project.id):
            out.append(
                GovernanceNotice(
                    message="Governança: anexe pelo menos um documento de auditoria (PDF ou tipo contendo 'audit' / 'auditoria').",
                    href=href_for_governance_fix(pid, "require_attachment_audit"),
                )
            )
    return out


async def _validate_from_catalog(
    session: AsyncSession,
    project: Project,
    ordered_ids: list[int],
) -> tuple[list[GovernanceNotice], list[GovernanceNotice]]:
    by_id = {r.id: r for r in await load_active_rules_by_ids(session, ordered_ids)}
    blocks: list[GovernanceNotice] = []
    warns: list[GovernanceNotice] = []
    for rid in ordered_ids:
        row = by_id.get(rid)
        if not row:
            continue
        notice = await notice_for_catalog_row(session, project, row)
        if not notice:
            continue
        mode = (row.on_violation or "bloqueio").strip().lower()
        if mode == "alerta":
            warns.append(notice)
        else:
            blocks.append(notice)
    return blocks, warns


async def validate_transition(
    session: AsyncSession,
    project: Project,
    target_column: KanbanTemplateColumn,
) -> tuple[list[GovernanceNotice], list[GovernanceNotice]]:
    """
    Retorna (bloqueios, avisos).
    Avisos não impedem o movimento; devem ser mostrados ao utilizador após sucesso.
    """
    d = parse_rules(target_column.rules_json)
    ids = d.get("applied_rule_ids") or []
    if ids:
        return await _validate_from_catalog(session, project, ids)
    legacy = await _validate_legacy(session, project, d)
    return legacy, []
