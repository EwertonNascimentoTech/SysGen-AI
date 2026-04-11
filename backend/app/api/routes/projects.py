from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.db.session import get_session
from app.jobs.wiki_job import run_generate_wiki
from app.models.cursor_artifact import ProjectCursorArtifact
from app.models.kanban import KanbanTemplate, KanbanTemplateColumn
from app.models.directory import Directory
from app.models.project import Project, ProjectAttachment, ProjectWiki, WikiDocument
from app.models.project_task import ProjectTask
from app.models.project_task_column import ProjectTaskColumn
from app.models.user import User
from app.schemas.project import (
    GitHubLinkBody,
    KanbanMoveOut,
    MoveKanbanBody,
    ProjectCreate,
    ProjectOut,
    ProjectPatch,
    TagSelectBody,
)
from app.schemas.project_task import (
    ProjectTaskCreate,
    ProjectTaskOut,
    ProjectTaskPatch,
    ProjectTaskReorderBody,
)
from app.schemas.project_task_column import (
    ProjectTaskColumnCreate,
    ProjectTaskColumnOrderBody,
    ProjectTaskColumnOut,
    ProjectTaskColumnPatch,
)
from app.services.attachments_storage import remove_attachment_storage, save_upload
from app.services.audit import log_action
from app.services.governance_transition import validate_transition
from app.services.github_client import github_list_tags, github_verify_ref, parse_github_repo_url
from app.services.github_tokens import resolve_github_token_for_project_api_async
from app.services.queue_conn import enqueue_wiki_job
from app.services.project_task_columns import (
    allocate_key,
    ensure_default_project_task_columns,
    list_columns_ordered,
    normalize_color_hex,
    renumber_positions,
    valid_column_keys,
)
from app.services.storage import presigned_get_url

router = APIRouter(prefix="/projects", tags=["projects"])


def _to_out(p: Project) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        name=p.name,
        product_owner=p.product_owner,
        directory_id=p.directory_id,
        directory_name=p.directory_ref.name if p.directory_ref else None,
        methodology=p.methodology,
        planned_start=p.planned_start,
        planned_end=p.planned_end,
        ended_at=p.ended_at,
        template_id=p.template_id,
        current_column_id=p.current_column_id,
        current_column_title=p.current_column.title if p.current_column else None,
        github_repo_url=p.github_repo_url,
        github_tag=p.github_tag,
        created_at=p.created_at,
    )


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    name: str | None = Query(None),
    directory_id: int | None = Query(None),
    product_owner: str | None = Query(None),
    methodology: str | None = Query(None),
    current_column_id: int | None = Query(None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(Project).options(
        selectinload(Project.directory_ref),
        selectinload(Project.current_column),
    )
    conds = []
    if name:
        conds.append(Project.name.ilike(f"%{name}%"))
    if directory_id is not None:
        conds.append(Project.directory_id == directory_id)
    if product_owner:
        conds.append(Project.product_owner.ilike(f"%{product_owner}%"))
    if methodology:
        conds.append(Project.methodology == methodology)
    if current_column_id is not None:
        conds.append(Project.current_column_id == current_column_id)
    if conds:
        q = q.where(and_(*conds))
    q = q.order_by(Project.name)
    result = await session.execute(q)
    projects = result.scalars().unique().all()
    return [_to_out(p) for p in projects]


@router.get("/board/kanban", response_model=list[ProjectOut])
async def kanban_board(
    template_id: int | None = Query(None),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(Project).options(
        selectinload(Project.directory_ref),
        selectinload(Project.current_column),
    )
    if template_id is not None:
        q = q.where(Project.template_id == template_id)
    q = q.order_by(Project.name)
    result = await session.execute(q)
    projects = result.scalars().unique().all()
    return [_to_out(p) for p in projects]


@router.post("", response_model=ProjectOut)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    tpl = (
        await session.execute(
            select(KanbanTemplate)
            .options(selectinload(KanbanTemplate.columns))
            .where(KanbanTemplate.id == body.template_id)
        )
    ).scalar_one_or_none()
    if not tpl or tpl.status != "publicado":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template inválido ou não publicado",
        )
    if not tpl.columns:
        raise HTTPException(status_code=400, detail="Template sem colunas")
    first_col = min(tpl.columns, key=lambda c: c.position)
    proj = Project(
        name=body.name,
        product_owner=body.product_owner,
        directory_id=body.directory_id,
        methodology=body.methodology,
        planned_start=body.planned_start,
        planned_end=body.planned_end,
        template_id=body.template_id,
        current_column_id=first_col.id,
    )
    session.add(proj)
    await session.flush()
    await ensure_default_project_task_columns(session, proj.id)
    await session.refresh(proj, ["directory_ref", "current_column"])
    await log_action(
        session,
        actor_email=user.email,
        action="project.create",
        entity_type="project",
        entity_id=proj.id,
    )
    await session.commit()
    await session.refresh(proj, ["directory_ref", "current_column"])
    return _to_out(proj)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = (
        await session.execute(
            select(Project)
            .options(selectinload(Project.directory_ref), selectinload(Project.current_column))
            .where(Project.id == project_id)
        )
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return _to_out(p)


@router.patch("/{project_id}", response_model=ProjectOut)
async def patch_project(
    project_id: int,
    body: ProjectPatch,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    p = (
        await session.execute(
            select(Project)
            .options(selectinload(Project.directory_ref), selectinload(Project.current_column))
            .where(Project.id == project_id)
        )
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    data = body.model_dump(exclude_unset=True)
    for key in ("name", "product_owner"):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip()
            if not data[key]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Nome e líder do produto não podem ficar vazios",
                )
    if not data:
        return _to_out(p)
    if "directory_id" in data:
        d = (await session.execute(select(Directory).where(Directory.id == data["directory_id"]))).scalar_one_or_none()
        if not d:
            raise HTTPException(status_code=400, detail="Diretoria inválida")
    start = data.get("planned_start", p.planned_start)
    end = data.get("planned_end", p.planned_end)
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Data de previsão de entrega deve ser igual ou posterior à de início",
        )
    for key, val in data.items():
        setattr(p, key, val)
    await session.flush()
    await session.refresh(p, ["directory_ref", "current_column"])
    await log_action(
        session,
        actor_email=user.email,
        action="project.update",
        entity_type="project",
        entity_id=p.id,
        detail=",".join(sorted(data.keys()))[:200],
    )
    await session.commit()
    await session.refresh(p, ["directory_ref", "current_column"])
    return _to_out(p)


async def _next_task_position(session: AsyncSession, project_id: int, column_key: str) -> int:
    m = await session.scalar(
        select(func.coalesce(func.max(ProjectTask.position), -1)).where(
            ProjectTask.project_id == project_id,
            ProjectTask.column_key == column_key,
        )
    )
    return int(m if m is not None else -1) + 1


@router.get("/{project_id}/task-columns", response_model=list[ProjectTaskColumnOut])
async def list_project_task_columns(
    project_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    cols = await list_columns_ordered(session, project_id)
    return [ProjectTaskColumnOut.model_validate(c) for c in cols]


@router.post("/{project_id}/task-columns", response_model=ProjectTaskColumnOut)
async def create_project_task_column(
    project_id: int,
    body: ProjectTaskColumnCreate,
    _: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    await ensure_default_project_task_columns(session, project_id)
    existing = (
        await session.execute(select(ProjectTaskColumn).where(ProjectTaskColumn.project_id == project_id))
    ).scalars().all()
    key_set = {c.key for c in existing}
    key = (body.key or "").strip().lower() if body.key else allocate_key(body.title, key_set)
    if key in key_set:
        raise HTTPException(status_code=400, detail="Chave da raia já existe neste projeto")
    max_pos = max((c.position for c in existing), default=-1)
    col = ProjectTaskColumn(
        project_id=project_id,
        key=key,
        title=body.title.strip(),
        position=max_pos + 1,
        color_hex=normalize_color_hex(body.color_hex),
        is_done=body.is_done,
    )
    session.add(col)
    await session.commit()
    await session.refresh(col)
    return ProjectTaskColumnOut.model_validate(col)


@router.patch("/{project_id}/task-columns/{column_id}", response_model=ProjectTaskColumnOut)
async def patch_project_task_column(
    project_id: int,
    column_id: int,
    body: ProjectTaskColumnPatch,
    _: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    col = (
        await session.execute(
            select(ProjectTaskColumn).where(
                ProjectTaskColumn.id == column_id,
                ProjectTaskColumn.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Raia não encontrada")
    data = body.model_dump(exclude_unset=True)
    if not data:
        return ProjectTaskColumnOut.model_validate(col)
    if "title" in data and data["title"] is not None:
        col.title = data["title"].strip()
    if "color_hex" in data and data["color_hex"] is not None:
        col.color_hex = normalize_color_hex(data["color_hex"])
    if "is_done" in data and data["is_done"] is not None:
        col.is_done = data["is_done"]
    await session.commit()
    await session.refresh(col)
    return ProjectTaskColumnOut.model_validate(col)


@router.put("/{project_id}/task-columns/order", response_model=list[ProjectTaskColumnOut])
async def order_project_task_columns(
    project_id: int,
    body: ProjectTaskColumnOrderBody,
    _: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    cols = (
        await session.execute(select(ProjectTaskColumn).where(ProjectTaskColumn.project_id == project_id))
    ).scalars().all()
    id_map = {c.id: c for c in cols}
    if set(body.column_ids) != set(id_map.keys()):
        raise HTTPException(
            status_code=400,
            detail="Envie todos os IDs das raias deste projeto, na ordem desejada",
        )
    for i, cid in enumerate(body.column_ids):
        id_map[cid].position = i
    await session.commit()
    ordered = await list_columns_ordered(session, project_id)
    return [ProjectTaskColumnOut.model_validate(c) for c in ordered]


@router.delete("/{project_id}/task-columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_task_column(
    project_id: int,
    column_id: int,
    _: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    cols = (
        await session.execute(
            select(ProjectTaskColumn)
            .where(ProjectTaskColumn.project_id == project_id)
            .order_by(ProjectTaskColumn.position, ProjectTaskColumn.id)
        )
    ).scalars().all()
    if len(cols) <= 1:
        raise HTTPException(status_code=400, detail="Não é possível excluir a única raia do quadro")
    target = next((c for c in cols if c.id == column_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Raia não encontrada")
    others = [c for c in cols if c.id != column_id]
    fallback = min(others, key=lambda c: (c.position, c.id))
    moved = (
        await session.execute(
            select(ProjectTask).where(
                ProjectTask.project_id == project_id,
                ProjectTask.column_key == target.key,
            )
        )
    ).scalars().all()
    m = await session.scalar(
        select(func.coalesce(func.max(ProjectTask.position), -1)).where(
            ProjectTask.project_id == project_id,
            ProjectTask.column_key == fallback.key,
        )
    )
    next_pos = int(m if m is not None else -1) + 1
    for t in moved:
        t.column_key = fallback.key
        t.position = next_pos
        next_pos += 1
    await session.delete(target)
    await session.flush()
    await renumber_positions(session, project_id)
    await session.commit()


@router.get("/{project_id}/tasks", response_model=list[ProjectTaskOut])
async def list_project_tasks(
    project_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    await ensure_default_project_task_columns(session, project_id)
    result = await session.execute(
        select(ProjectTask)
        .where(ProjectTask.project_id == project_id)
        .order_by(ProjectTask.column_key, ProjectTask.position, ProjectTask.id)
    )
    rows = result.scalars().all()
    return [ProjectTaskOut.model_validate(t) for t in rows]


@router.post("/{project_id}/tasks", response_model=ProjectTaskOut)
async def create_project_task(
    project_id: int,
    body: ProjectTaskCreate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    keys = await valid_column_keys(session, project_id)
    if body.column_key not in keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Coluna (raia) inválida ou inexistente neste projeto",
        )
    pos = await _next_task_position(session, project_id, body.column_key)
    task = ProjectTask(
        project_id=project_id,
        position=pos,
        title=body.title.strip(),
        description=(body.description.strip() if body.description else None) or None,
        column_key=body.column_key,
        priority=body.priority,
        assignee=(body.assignee.strip() if body.assignee else None) or None,
        due_date=body.due_date,
        governance_aligned=body.governance_aligned,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return ProjectTaskOut.model_validate(task)


@router.put("/{project_id}/tasks/reorder", response_model=list[ProjectTaskOut])
async def reorder_project_tasks_in_column(
    project_id: int,
    body: ProjectTaskReorderBody,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    keys = await valid_column_keys(session, project_id)
    if body.column_key not in keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Coluna (raia) inválida ou inexistente neste projeto",
        )
    rows = (
        await session.execute(
            select(ProjectTask).where(
                ProjectTask.project_id == project_id,
                ProjectTask.column_key == body.column_key,
            )
        )
    ).scalars().all()
    db_ids = {t.id for t in rows}
    if len(body.task_ids) != len(db_ids) or set(body.task_ids) != db_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A lista de tarefas deve conter exactamente as tarefas desta raia, sem duplicados",
        )
    id_to_task = {t.id: t for t in rows}
    for i, tid in enumerate(body.task_ids):
        id_to_task[tid].position = i
    await session.commit()
    ordered = (
        await session.execute(
            select(ProjectTask)
            .where(
                ProjectTask.project_id == project_id,
                ProjectTask.column_key == body.column_key,
            )
            .order_by(ProjectTask.position, ProjectTask.id)
        )
    ).scalars().all()
    return [ProjectTaskOut.model_validate(t) for t in ordered]


@router.patch("/{project_id}/tasks/{task_id}", response_model=ProjectTaskOut)
async def patch_project_task(
    project_id: int,
    task_id: int,
    body: ProjectTaskPatch,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    task = (
        await session.execute(
            select(ProjectTask).where(ProjectTask.id == task_id, ProjectTask.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    data = body.model_dump(exclude_unset=True)
    if not data:
        return ProjectTaskOut.model_validate(task)
    new_col = data.pop("column_key", None)
    if new_col is not None and new_col != task.column_key:
        keys = await valid_column_keys(session, project_id)
        if new_col not in keys:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coluna (raia) inválida ou inexistente neste projeto",
            )
        task.column_key = new_col
        task.position = await _next_task_position(session, project_id, task.column_key)
        data.pop("position", None)
    elif "position" in data:
        task.position = data.pop("position")
    if "title" in data and data["title"] is not None:
        data["title"] = data["title"].strip()
    if "description" in data and data["description"] is not None:
        data["description"] = data["description"].strip() or None
    if "assignee" in data and data["assignee"] is not None:
        data["assignee"] = data["assignee"].strip() or None
    for key, val in data.items():
        setattr(task, key, val)
    await session.commit()
    await session.refresh(task)
    return ProjectTaskOut.model_validate(task)


@router.delete("/{project_id}/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_task(
    project_id: int,
    task_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    task = (
        await session.execute(
            select(ProjectTask).where(ProjectTask.id == task_id, ProjectTask.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    await session.delete(task)
    await session.commit()


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    name = p.name
    atts = (
        await session.execute(select(ProjectAttachment).where(ProjectAttachment.project_id == project_id))
    ).scalars().all()
    for att in atts:
        remove_attachment_storage(att.storage_path)
        await session.delete(att)
    wikis = (await session.execute(select(ProjectWiki).where(ProjectWiki.project_id == project_id))).scalars().all()
    for w in wikis:
        await session.execute(delete(WikiDocument).where(WikiDocument.wiki_id == w.id))
        await session.delete(w)
    pcas = (
        await session.execute(select(ProjectCursorArtifact).where(ProjectCursorArtifact.project_id == project_id))
    ).scalars().all()
    for pca in pcas:
        await session.delete(pca)
    await session.delete(p)
    await log_action(
        session,
        actor_email=user.email,
        action="project.delete",
        entity_type="project",
        entity_id=project_id,
        detail=name[:200],
    )
    await session.commit()


@router.post("/{project_id}/kanban/move", response_model=KanbanMoveOut)
async def move_kanban(
    project_id: int,
    body: MoveKanbanBody,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    p = (
        await session.execute(
            select(Project)
            .options(selectinload(Project.directory_ref), selectinload(Project.current_column))
            .where(Project.id == project_id)
        )
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    col = (
        await session.execute(
            select(KanbanTemplateColumn).where(
                KanbanTemplateColumn.id == body.target_column_id,
                KanbanTemplateColumn.template_id == p.template_id,
            )
        )
    ).scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=400, detail="Coluna não pertence ao template do projeto")
    gov_errs, gov_warns = await validate_transition(session, p, col)
    if gov_errs:
        raise HTTPException(
            status_code=400,
            detail=[g.model_dump(exclude_none=True) for g in gov_errs],
        )
    src_col = p.current_column
    if src_col is not None and col.position < src_col.position:
        p.ended_at = None
    p.current_column_id = col.id
    await log_action(
        session,
        actor_email=user.email,
        action="project.kanban.move",
        entity_type="project",
        entity_id=p.id,
        detail=f"coluna={col.title}",
    )
    await session.commit()
    await session.refresh(p, ["directory_ref", "current_column"])
    return KanbanMoveOut(project=_to_out(p), governance_warnings=gov_warns)


@router.post("/{project_id}/attachments", response_model=dict)
async def add_attachment(
    project_id: int,
    attachment_type: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_roles("admin", "coordenador", "po", "dev")),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    storage_path, size, ctype = await save_upload(project_id, file)
    att = ProjectAttachment(
        project_id=project_id,
        file_name=file.filename or "arquivo",
        attachment_type=attachment_type,
        storage_path=storage_path,
        content_type=ctype,
        size_bytes=size,
    )
    session.add(att)
    await log_action(
        session,
        actor_email=user.email,
        action="project.attachment.add",
        entity_type="project",
        entity_id=project_id,
        detail=storage_path,
    )
    await session.commit()
    await session.refresh(att)
    return {"id": att.id, "storage_path": att.storage_path, "size_bytes": size}


@router.get("/{project_id}/attachments/{attachment_id}/download")
async def download_attachment(
    project_id: int,
    attachment_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    att = (
        await session.execute(
            select(ProjectAttachment).where(
                ProjectAttachment.id == attachment_id,
                ProjectAttachment.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    key = att.storage_path
    if settings.s3_endpoint_url and not key.startswith("local_storage/") and "/" in key:
        url = presigned_get_url(key)
        return RedirectResponse(url)
    path = Path(key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no storage")
    allowed_root = Path("local_storage") / str(project_id)
    try:
        path.resolve().relative_to(allowed_root.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Caminho inválido")
    return FileResponse(path, filename=att.file_name)


@router.patch("/{project_id}/github", response_model=ProjectOut)
async def link_github(
    project_id: int,
    body: GitHubLinkBody,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    p = (
        await session.execute(
            select(Project)
            .options(selectinload(Project.directory_ref), selectinload(Project.current_column))
            .where(Project.id == project_id)
        )
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    if "github.com" not in body.repo_url:
        raise HTTPException(status_code=400, detail="URL de repositório inválida")
    try:
        parse_github_repo_url(body.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    p.github_repo_url = body.repo_url.strip().rstrip("/")
    await log_action(session, actor_email=user.email, action="project.github.link", entity_type="project", entity_id=p.id)
    await session.commit()
    await session.refresh(p, ["directory_ref", "current_column"])
    return _to_out(p)


@router.get("/{project_id}/github/tags", response_model=list[str])
async def list_github_tags(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    if not p.github_repo_url:
        raise HTTPException(status_code=400, detail="Repositório não vinculado")
    try:
        ref = parse_github_repo_url(p.github_repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = await resolve_github_token_for_project_api_async(session, user)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Sem token GitHub OAuth para este utilizador. Use «Entrar com GitHub» ou «Sincronizar com GitHub» "
                "no projeto para ligar a sua conta — as operações usam apenas o token da sua conta GitHub."
            ),
        )
    try:
        return await github_list_tags(ref.owner, ref.name, token)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API: {e!s}")


@router.patch("/{project_id}/github/tag", response_model=ProjectOut)
async def select_tag(
    project_id: int,
    body: TagSelectBody,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    p = (
        await session.execute(
            select(Project)
            .options(selectinload(Project.directory_ref), selectinload(Project.current_column))
            .where(Project.id == project_id)
        )
    ).scalar_one_or_none()
    if not p or not p.github_repo_url:
        raise HTTPException(status_code=400, detail="Projeto ou repositório inválido")
    try:
        ref = parse_github_repo_url(p.github_repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = await resolve_github_token_for_project_api_async(session, user)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Sem token GitHub OAuth. Ligue a sua conta com «Entrar com GitHub» ou «Sincronizar com GitHub» "
                "para validar tags com as permissões da sua conta GitHub."
            ),
        )
    ok = await github_verify_ref(ref.owner, ref.name, body.tag, token)
    if not ok:
        raise HTTPException(status_code=400, detail="Tag ou branch inválida para este repositório")
    p.github_tag = body.tag
    await log_action(session, actor_email=user.email, action="project.github.tag", entity_type="project", entity_id=p.id, detail=body.tag)
    await session.commit()
    await session.refresh(p, ["directory_ref", "current_column"])
    return _to_out(p)


@router.post("/{project_id}/wiki/generate")
async def generate_wiki(
    project_id: int,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p or not p.github_tag:
        raise HTTPException(status_code=400, detail="Selecione uma tag válida antes de gerar a Wiki")
    wiki = ProjectWiki(project_id=p.id, tag=p.github_tag, status="pending", error_message=None)
    session.add(wiki)
    await session.flush()
    await log_action(
        session,
        actor_email=user.email,
        action="project.wiki.generate",
        entity_type="project",
        entity_id=p.id,
        detail=wiki.tag,
    )
    await session.commit()

    job_id: str | None = None
    try:
        job_id = await anyio.to_thread.run_sync(enqueue_wiki_job, wiki.id, p.id, user.id)
        await session.execute(update(ProjectWiki).where(ProjectWiki.id == wiki.id).values(rq_job_id=job_id))
        await session.commit()
    except Exception:
        await anyio.to_thread.run_sync(run_generate_wiki, wiki.id, p.id, user.id)
        refreshed = (
            await session.execute(select(ProjectWiki).where(ProjectWiki.id == wiki.id))
        ).scalar_one()
        return {"wiki_id": wiki.id, "status": refreshed.status, "job_id": None, "error": refreshed.error_message}
    return {"wiki_id": wiki.id, "status": "pending", "job_id": job_id}


@router.get("/{project_id}/wiki")
async def get_wiki(
    project_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ProjectWiki).where(ProjectWiki.project_id == project_id).order_by(ProjectWiki.id.desc()).limit(1)
    )
    wiki = result.scalar_one_or_none()
    if not wiki:
        return {
            "detail": "Nenhuma Wiki gerada ainda",
            "documents": [],
            "status": None,
            "error_message": None,
            "wiki_created_at": None,
        }
    docs = (
        await session.execute(select(WikiDocument).where(WikiDocument.wiki_id == wiki.id))
    ).scalars().all()

    def _wiki_doc_kind(path: str) -> str:
        if (path or "").lower().endswith(".xml"):
            return "bpmn-xml"
        return "markdown"

    return {
        "wiki_id": wiki.id,
        "tag": wiki.tag,
        "status": wiki.status,
        "error_message": wiki.error_message,
        "rq_job_id": wiki.rq_job_id,
        "wiki_created_at": wiki.created_at.isoformat() if wiki.created_at else None,
        "documents": [
            {"path": d.path, "title": d.title, "markdown": d.markdown, "kind": _wiki_doc_kind(d.path)} for d in docs
        ],
    }
