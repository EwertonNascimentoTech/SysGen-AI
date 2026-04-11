import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_task_column import ProjectTaskColumn

_DEFAULT_COLS: list[tuple[str, str, int, str, bool]] = [
    ("todo", "A Fazer", 0, "#94a3b8", False),
    ("in_progress", "Em Execução", 1, "#3b82f6", False),
    ("review", "Revisão Técnica", 2, "#f59e0b", False),
    ("done", "Concluído", 3, "#10b981", True),
]


def normalize_color_hex(raw: str | None) -> str:
    s = (raw or "").strip()
    if not s:
        return "#64748b"
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", s):
        return s.lower()
    if re.fullmatch(r"[0-9A-Fa-f]{6}", s):
        return f"#{s.lower()}"
    return "#64748b"


def slugify_key_base(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9]+", "_", t)
    t = re.sub(r"_+", "_", t).strip("_")
    return (t[:40] if t else "col") or "col"


def allocate_key(title: str, existing: set[str]) -> str:
    base = slugify_key_base(title)
    if base not in existing:
        return base
    i = 2
    while f"{base}_{i}" in existing:
        i += 1
    return f"{base}_{i}"


async def ensure_default_project_task_columns(session: AsyncSession, project_id: int) -> None:
    n = await session.scalar(
        select(func.count()).select_from(ProjectTaskColumn).where(ProjectTaskColumn.project_id == project_id)
    )
    if n and int(n) > 0:
        return
    for key, title, pos, color, is_done in _DEFAULT_COLS:
        session.add(
            ProjectTaskColumn(
                project_id=project_id,
                key=key,
                title=title,
                position=pos,
                color_hex=color,
                is_done=is_done,
            )
        )
    await session.flush()


async def valid_column_keys(session: AsyncSession, project_id: int) -> set[str]:
    await ensure_default_project_task_columns(session, project_id)
    rows = (
        await session.execute(
            select(ProjectTaskColumn.key).where(ProjectTaskColumn.project_id == project_id)
        )
    ).all()
    return {r[0] for r in rows}


async def list_columns_ordered(session: AsyncSession, project_id: int) -> list[ProjectTaskColumn]:
    await ensure_default_project_task_columns(session, project_id)
    result = await session.execute(
        select(ProjectTaskColumn)
        .where(ProjectTaskColumn.project_id == project_id)
        .order_by(ProjectTaskColumn.position, ProjectTaskColumn.id)
    )
    return list(result.scalars().all())


async def renumber_positions(session: AsyncSession, project_id: int) -> None:
    cols = (
        await session.execute(
            select(ProjectTaskColumn)
            .where(ProjectTaskColumn.project_id == project_id)
            .order_by(ProjectTaskColumn.position, ProjectTaskColumn.id)
        )
    ).scalars().all()
    for i, c in enumerate(cols):
        if c.position != i:
            c.position = i
