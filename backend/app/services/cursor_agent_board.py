"""Mover tarefa para revisão quando um agente Cursor termina (webhook ou sincronização com a API)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_cursor_agent_run import ProjectCursorAgentRun
from app.models.project_task import ProjectTask
from app.services.audit import log_action
from app.services.cursor_cloud_agents import fetch_cursor_agent
from app.services.project_task_columns import list_columns_ordered

logger = logging.getLogger(__name__)

# Estados que contam como «trabalho concluído com sucesso» para mover o cartão.
AGENT_FINISHED_STATUSES = frozenset(
    {
        "FINISHED",
        "COMPLETE",
        "COMPLETED",
        "SUCCESS",
        "SUCCEEDED",
        "DONE",
    }
)

CURSOR_AUTOMATION_ACTOR = "cursor-cloud-webhook"


def _column_key_by_id(cols: list[Any], key: str) -> str | None:
    for c in cols:
        if getattr(c, "key", None) == key:
            return c.key
    return None


async def _next_task_position(session: AsyncSession, project_id: int, column_key: str) -> int:
    m = await session.scalar(
        select(func.coalesce(func.max(ProjectTask.position), -1)).where(
            ProjectTask.project_id == project_id,
            ProjectTask.column_key == column_key,
        )
    )
    return int(m if m is not None else -1) + 1


async def move_task_to_review_after_agent_finish(
    session: AsyncSession,
    run: ProjectCursorAgentRun,
    agent_id: str,
) -> None:
    """Move a tarefa associada ao run para a coluna «review», salvo se já estiver em revisão ou concluída."""
    cols = await list_columns_ordered(session, run.project_id)
    review_key = _column_key_by_id(cols, "review")
    done_keys = {c.key for c in cols if getattr(c, "is_done", False)}
    if not review_key:
        logger.error("cursor board: raia review não encontrada projeto=%s", run.project_id)
        return
    task = (
        await session.execute(
            select(ProjectTask).where(
                ProjectTask.id == run.task_id,
                ProjectTask.project_id == run.project_id,
            )
        )
    ).scalar_one_or_none()
    if not task:
        return
    if task.column_key == review_key:
        logger.info("cursor board: tarefa %s já em revisão (agente %s)", task.id, agent_id)
        return
    if task.column_key in done_keys:
        logger.info(
            "cursor board: tarefa %s em coluna concluída, não movida (agente %s)",
            task.id,
            agent_id,
        )
        return
    prev_col = task.column_key
    task.column_key = review_key
    task.position = await _next_task_position(session, run.project_id, review_key)
    await log_action(
        session,
        actor_email=CURSOR_AUTOMATION_ACTOR,
        action="project.cursor_dev.finished",
        entity_type="project",
        entity_id=run.project_id,
        detail=f"task_id={task.id},cursor_agent_id={agent_id},from_col={prev_col}"[:200],
    )


async def refresh_stale_cursor_runs_from_api(
    session: AsyncSession,
    project_id: int,
    api_key: str,
) -> None:
    """
    Actualiza na BD runs ainda em CREATING/RUNNING com o estado real na Cursor e, se já terminou,
    tenta mover a tarefa para revisão (útil quando o webhook não chegou).
    """
    rows = (
        await session.execute(
            select(ProjectCursorAgentRun).where(
                ProjectCursorAgentRun.project_id == project_id,
                ProjectCursorAgentRun.status.in_(("CREATING", "RUNNING")),
            )
        )
    ).scalars().all()
    for run in rows:
        try:
            data = await fetch_cursor_agent(api_key, run.cursor_agent_id)
        except Exception as e:
            logger.warning(
                "cursor sync: falha ao consultar agente %s (projeto %s): %s",
                run.cursor_agent_id,
                project_id,
                e,
            )
            continue
        if data is None:
            run.status = "NOT_FOUND"
            continue
        remote = str(data.get("status") or "").strip().upper()
        if remote:
            run.status = remote
        if isinstance(data.get("summary"), str) and data.get("summary"):
            run.summary = str(data["summary"])[:8000]
        if remote in AGENT_FINISHED_STATUSES:
            await move_task_to_review_after_agent_finish(session, run, run.cursor_agent_id)
    await session.flush()
