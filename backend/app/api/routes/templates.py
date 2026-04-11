from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models.kanban import KanbanTemplate, KanbanTemplateColumn
from app.models.project import Project
from app.models.user import User
from app.schemas.template import (
    ColumnCreate,
    ColumnPatch,
    DuplicateTemplateBody,
    ReorderColumnsBody,
    TemplateCreate,
    TemplateOut,
    TemplatePatch,
)
from app.services.audit import log_action
from app.services.column_rules import default_rules_dict, dumps_rules, merge_rules, parse_rules
from app.services.governance_catalog import resolve_effective_rule_flags

router = APIRouter(prefix="/kanban-templates", tags=["kanban-templates"])


async def _get_template(session: AsyncSession, template_id: int) -> KanbanTemplate | None:
    return (
        await session.execute(
            select(KanbanTemplate)
            .options(selectinload(KanbanTemplate.columns))
            .where(KanbanTemplate.id == template_id)
        )
    ).scalar_one_or_none()


def _out(tpl: KanbanTemplate) -> TemplateOut:
    return TemplateOut.from_orm_template(tpl)


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(KanbanTemplate)
        .options(selectinload(KanbanTemplate.columns))
        .where(KanbanTemplate.status == "publicado")
        .order_by(KanbanTemplate.name)
    )
    return [_out(t) for t in result.scalars().unique().all()]


@router.get("/all", response_model=list[TemplateOut])
async def list_all_templates(
    _: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(KanbanTemplate).options(selectinload(KanbanTemplate.columns)).order_by(KanbanTemplate.name)
    )
    return [_out(t) for t in result.scalars().unique().all()]


@router.post("", response_model=TemplateOut)
async def create_template_draft(
    body: TemplateCreate,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    tpl = KanbanTemplate(
        name=body.name.strip(),
        status="rascunho",
        version=1,
        description=(body.description.strip() if body.description else None) or None,
        methodology=(body.methodology.strip() if body.methodology else None) or None,
    )
    session.add(tpl)
    await session.flush()
    for i, title in enumerate(body.column_titles):
        if not title.strip():
            continue
        session.add(
            KanbanTemplateColumn(
                template_id=tpl.id,
                title=title.strip(),
                position=i,
                rules_json=dumps_rules(default_rules_dict(i)),
            )
        )
    await session.flush()
    await log_action(
        session,
        actor_email=user.email,
        action="template.create_draft",
        entity_type="kanban_template",
        entity_id=tpl.id,
    )
    await session.commit()
    reloaded = await _get_template(session, tpl.id)
    assert reloaded
    return _out(reloaded)


@router.patch("/{template_id}", response_model=TemplateOut)
async def patch_template(
    template_id: int,
    body: TemplatePatch,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    tpl = await _get_template(session, template_id)
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado")
    if body.name is not None:
        tpl.name = body.name.strip()
    if body.description is not None:
        tpl.description = body.description.strip() or None
    if body.methodology is not None:
        tpl.methodology = body.methodology.strip() or None
    await log_action(
        session,
        actor_email=user.email,
        action="template.patch",
        entity_type="kanban_template",
        entity_id=tpl.id,
        detail=body.name,
    )
    await session.commit()
    await session.refresh(tpl)
    reloaded = await _get_template(session, tpl.id)
    assert reloaded
    return _out(reloaded)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    tpl = await _get_template(session, template_id)
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado")
    n = await session.scalar(select(func.count()).select_from(Project).where(Project.template_id == template_id))
    if n and n > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir: existem projetos vinculados a este template.",
        )
    for c in list(tpl.columns):
        await session.delete(c)
    await session.delete(tpl)
    await log_action(
        session,
        actor_email=user.email,
        action="template.delete",
        entity_type="kanban_template",
        entity_id=template_id,
    )
    await session.commit()


@router.post("/{template_id}/duplicate", response_model=TemplateOut)
async def duplicate_template(
    template_id: int,
    body: DuplicateTemplateBody,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    tpl = await _get_template(session, template_id)
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado")
    name = (body.name or f"{tpl.name} (cópia)").strip()
    new_tpl = KanbanTemplate(
        name=name,
        status="rascunho",
        version=1,
        description=tpl.description,
        methodology=tpl.methodology,
    )
    session.add(new_tpl)
    await session.flush()
    for c in sorted(tpl.columns, key=lambda x: x.position):
        rj = c.rules_json if c.rules_json else dumps_rules(default_rules_dict(c.position))
        session.add(
            KanbanTemplateColumn(
                template_id=new_tpl.id,
                title=c.title,
                position=c.position,
                rules_json=rj,
            )
        )
    await session.flush()
    await log_action(
        session,
        actor_email=user.email,
        action="template.duplicate",
        entity_type="kanban_template",
        entity_id=new_tpl.id,
        detail=f"from={template_id}",
    )
    await session.commit()
    reloaded = await _get_template(session, new_tpl.id)
    assert reloaded
    return _out(reloaded)


@router.post("/{template_id}/columns", response_model=TemplateOut)
async def add_column(
    template_id: int,
    body: ColumnCreate,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    tpl = await _get_template(session, template_id)
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado")
    max_pos = max((c.position for c in tpl.columns), default=-1)
    pos = max_pos + 1
    rules = default_rules_dict(pos)
    if body.color_hex:
        rules["color_hex"] = str(body.color_hex).strip()[:16]
    if body.rules:
        rules.update(body.rules.model_dump())
    col = KanbanTemplateColumn(
        template_id=tpl.id,
        title=body.title.strip(),
        position=pos,
        rules_json=dumps_rules(rules),
    )
    session.add(col)
    await session.flush()
    await log_action(
        session,
        actor_email=user.email,
        action="template.column.add",
        entity_type="kanban_template",
        entity_id=tpl.id,
        detail=col.title,
    )
    await session.commit()
    reloaded = await _get_template(session, tpl.id)
    assert reloaded
    return _out(reloaded)


@router.patch("/{template_id}/columns/{column_id}", response_model=TemplateOut)
async def patch_column(
    template_id: int,
    column_id: int,
    body: ColumnPatch,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    tpl = await _get_template(session, template_id)
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado")
    col = next((c for c in tpl.columns if c.id == column_id), None)
    if not col:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coluna não encontrada")
    if body.title is not None:
        col.title = body.title.strip()
    if body.applied_rule_ids is not None:
        d = parse_rules(col.rules_json)
        d["applied_rule_ids"] = list(body.applied_rule_ids)
        if body.applied_rule_ids:
            eff = await resolve_effective_rule_flags(session, list(body.applied_rule_ids))
            d["require_description"] = eff["require_description"]
            d["require_attachment_audit"] = eff["require_attachment_audit"]
            d["require_po_assigned"] = eff["require_po_assigned"]
            d["require_github_tag"] = eff["require_github_tag"]
            d["min_tag_count"] = eff["min_tag_count"]
        else:
            d["require_description"] = False
            d["require_attachment_audit"] = False
            d["require_po_assigned"] = False
            d["require_github_tag"] = False
            d["min_tag_count"] = 0
        col.rules_json = dumps_rules(d)
    else:
        patch: dict = {}
        if body.color_hex is not None:
            patch["color_hex"] = body.color_hex
        if body.rules is not None:
            patch.update(body.rules.model_dump())
            patch["applied_rule_ids"] = []
        if patch:
            merged = merge_rules(col.rules_json, patch)
            col.rules_json = dumps_rules(merged)
    await session.flush()
    await log_action(
        session,
        actor_email=user.email,
        action="template.column.patch",
        entity_type="kanban_template_column",
        entity_id=col.id,
        detail=col.title,
    )
    await session.commit()
    reloaded = await _get_template(session, tpl.id)
    assert reloaded
    return _out(reloaded)


@router.delete("/{template_id}/columns/{column_id}", response_model=TemplateOut)
async def delete_column(
    template_id: int,
    column_id: int,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    tpl = await _get_template(session, template_id)
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado")
    col = next((c for c in tpl.columns if c.id == column_id), None)
    if not col:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coluna não encontrada")
    n = await session.scalar(
        select(func.count()).select_from(Project).where(Project.current_column_id == column_id)
    )
    if n and n > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir: há projeto(s) com esta fase como coluna atual. Mova-os antes.",
        )
    await session.delete(col)
    await session.flush()
    remaining = (
        await session.execute(
            select(KanbanTemplateColumn)
            .where(KanbanTemplateColumn.template_id == template_id)
            .order_by(KanbanTemplateColumn.position)
        )
    ).scalars().all()
    for i, c in enumerate(remaining):
        c.position = i
    await log_action(
        session,
        actor_email=user.email,
        action="template.column.delete",
        entity_type="kanban_template_column",
        entity_id=column_id,
    )
    await session.commit()
    reloaded = await _get_template(session, tpl.id)
    assert reloaded
    return _out(reloaded)


@router.post("/{template_id}/columns/reorder", response_model=TemplateOut)
async def reorder_columns(
    template_id: int,
    body: ReorderColumnsBody,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    tpl = await _get_template(session, template_id)
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado")
    by_id = {c.id: c for c in tpl.columns}
    if set(body.ordered_column_ids) != set(by_id.keys()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lista de colunas incompleta ou inválida.",
        )
    for i, cid in enumerate(body.ordered_column_ids):
        by_id[cid].position = i
    await log_action(
        session,
        actor_email=user.email,
        action="template.column.reorder",
        entity_type="kanban_template",
        entity_id=tpl.id,
    )
    await session.commit()
    reloaded = await _get_template(session, tpl.id)
    assert reloaded
    return _out(reloaded)


@router.post("/{template_id}/publish", response_model=TemplateOut)
async def publish_template(
    template_id: int,
    user: User = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    tpl = await _get_template(session, template_id)
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado")
    tpl.status = "publicado"
    await log_action(
        session,
        actor_email=user.email,
        action="template.publish",
        entity_type="kanban_template",
        entity_id=tpl.id,
    )
    await session.commit()
    reloaded = await _get_template(session, tpl.id)
    assert reloaded
    return _out(reloaded)
