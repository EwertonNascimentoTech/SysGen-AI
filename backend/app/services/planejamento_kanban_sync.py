"""Sincroniza itens do JSON de planejamento aprovado com `project_tasks` (aba Desenvolvimento)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_task import ProjectTask
from app.services.planejamento_kanban_payload import (
    MARKER,
    build_card_description,
    build_task_title,
    flatten_planejamento_for_kanban,
    parse_planejamento_json,
    truncate_bloco_tag,
    truncate_entrega_resumo,
)
from app.services.project_task_columns import ensure_default_project_task_columns, list_columns_ordered


async def _backlog_column_key(session: AsyncSession, project_id: int) -> str:
    await ensure_default_project_task_columns(session, project_id)
    cols = await list_columns_ordered(session, project_id)
    if not cols:
        return "todo"
    return cols[0].key


async def delete_planejamento_marker_tasks(session: AsyncSession, project_id: int) -> int:
    res = await session.execute(
        delete(ProjectTask).where(
            ProjectTask.project_id == project_id,
            ProjectTask.description.isnot(None),
            ProjectTask.description.like(f"{MARKER}%"),
        )
    )
    return int(res.rowcount or 0)


async def insert_planejamento_kanban_tasks(
    session: AsyncSession,
    project_id: int,
    flat: list[tuple[str, str, str, str]],
) -> int:
    if not flat:
        return 0
    backlog_key = await _backlog_column_key(session, project_id)
    existing = (
        await session.scalars(
            select(ProjectTask)
            .where(ProjectTask.project_id == project_id, ProjectTask.column_key == backlog_key)
            .order_by(ProjectTask.position, ProjectTask.id)
        )
    ).all()
    for i, row in enumerate(flat):
        phase_title, item_title, item_desc, item_entrega = row
        title = build_task_title(item_title)
        description = build_card_description(item_title, item_desc)
        session.add(
            ProjectTask(
                project_id=project_id,
                title=title,
                bloco_tag=truncate_bloco_tag(phase_title),
                description=description,
                entrega_resumo=truncate_entrega_resumo(item_entrega),
                column_key=backlog_key,
                position=i,
                priority="medium",
                assignee=None,
                due_date=None,
                governance_aligned=False,
            )
        )
    offset = len(flat)
    for j, t in enumerate(existing):
        t.position = offset + j
    return len(flat)


async def sync_planejamento_to_kanban(
    session: AsyncSession,
    project_id: int,
    planejamento_json: str,
    approved: bool,
) -> tuple[int, int]:
    """
    Se `approved`: remove cards antigas geradas pelo planejamento e cria novas na primeira raia, na ordem do JSON.
    Se não `approved`: remove só as cards geradas pelo planejamento.
    Devolve (tarefas_removidas, tarefas_criadas).
    """
    removed = await delete_planejamento_marker_tasks(session, project_id)
    created = 0
    if approved:
        parsed = parse_planejamento_json(planejamento_json)
        if parsed is not None:
            flat = flatten_planejamento_for_kanban(parsed)
            created = await insert_planejamento_kanban_tasks(session, project_id, flat)
    await session.flush()
    return removed, created
