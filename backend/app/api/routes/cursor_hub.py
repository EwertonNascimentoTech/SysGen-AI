from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_session
from app.models.cursor_artifact import CursorArtifact, ProjectCursorArtifact
from app.models.project import Project
from app.models.user import User
from app.schemas.cursor import CursorArtifactCreate, CursorArtifactOut, CursorArtifactPatch, LinkArtifactBody
from app.services.audit import log_action

router = APIRouter(prefix="/cursor-artifacts", tags=["cursor-artifacts"])


def _normalize_status(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if s in {"publicado", "ativo"}:
        return "ativo"
    return "inativo"


@router.get("", response_model=list[CursorArtifactOut])
async def list_artifacts(
    status_filter: str | None = Query(None),
    _: User = Depends(require_roles("admin", "coordenador", "dev")),
    session: AsyncSession = Depends(get_session),
):
    q = select(CursorArtifact).order_by(CursorArtifact.name)
    if status_filter:
        q = q.where(CursorArtifact.status == status_filter)
    result = await session.execute(q)
    arts = list(result.scalars().all())
    ids = [a.id for a in arts]
    count_map: dict[int, int] = {}
    if ids:
        r2 = await session.execute(
            select(ProjectCursorArtifact.artifact_id, func.count())
            .where(ProjectCursorArtifact.artifact_id.in_(ids))
            .group_by(ProjectCursorArtifact.artifact_id)
        )
        for aid, c in r2.all():
            count_map[int(aid)] = int(c)
    return [
        CursorArtifactOut(
            id=a.id,
            kind=a.kind,
            name=a.name,
            description=a.description,
            content=a.content,
            status=_normalize_status(a.status),
            linked_projects_count=count_map.get(a.id, 0),
        )
        for a in arts
    ]


@router.post("", response_model=CursorArtifactOut)
async def create_artifact(
    body: CursorArtifactCreate,
    user: User = Depends(require_roles("admin", "coordenador", "dev")),
    session: AsyncSession = Depends(get_session),
):
    art = CursorArtifact(
        kind=body.kind,
        name=body.name,
        description=body.description,
        content=body.content,
        status=_normalize_status(body.status),
    )
    session.add(art)
    await session.flush()
    await log_action(
        session,
        actor_email=user.email,
        action="cursor.create",
        entity_type="cursor_artifact",
        entity_id=art.id,
    )
    await session.commit()
    await session.refresh(art)
    return art


@router.patch("/{artifact_id}", response_model=CursorArtifactOut)
async def patch_artifact(
    artifact_id: int,
    body: CursorArtifactPatch,
    user: User = Depends(require_roles("admin", "coordenador", "dev")),
    session: AsyncSession = Depends(get_session),
):
    art = (await session.execute(select(CursorArtifact).where(CursorArtifact.id == artifact_id))).scalar_one_or_none()
    if not art:
        raise HTTPException(status_code=404, detail="Artefato não encontrado")
    if body.kind is not None:
        art.kind = body.kind
    if body.name is not None:
        art.name = body.name.strip()
    if body.description is not None:
        art.description = body.description.strip() or None
    if body.content is not None:
        art.content = body.content
    if body.status is not None:
        art.status = _normalize_status(body.status)
    await log_action(
        session,
        actor_email=user.email,
        action="cursor.patch",
        entity_type="cursor_artifact",
        entity_id=art.id,
    )
    await session.commit()
    await session.refresh(art)
    return CursorArtifactOut(
        id=art.id,
        kind=art.kind,
        name=art.name,
        description=art.description,
        content=art.content,
        status=_normalize_status(art.status),
        linked_projects_count=0,
    )


@router.post("/{artifact_id}/publish", response_model=CursorArtifactOut)
async def publish_artifact(
    artifact_id: int,
    user: User = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    art = (await session.execute(select(CursorArtifact).where(CursorArtifact.id == artifact_id))).scalar_one_or_none()
    if not art:
        raise HTTPException(status_code=404, detail="Artefato não encontrado")
    art.status = "ativo"
    await log_action(session, actor_email=user.email, action="cursor.publish", entity_type="cursor_artifact", entity_id=art.id)
    await session.commit()
    await session.refresh(art)
    return art


@router.post("/projects/{project_id}/link", response_model=dict)
async def link_to_project(
    project_id: int,
    body: LinkArtifactBody,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    art = (await session.execute(select(CursorArtifact).where(CursorArtifact.id == body.artifact_id))).scalar_one_or_none()
    if not p or not art:
        raise HTTPException(status_code=404, detail="Projeto ou artefato não encontrado")
    if _normalize_status(art.status) != "ativo":
        raise HTTPException(status_code=400, detail="Apenas artefatos ativos podem ser vinculados")
    session.add(ProjectCursorArtifact(project_id=project_id, artifact_id=art.id))
    await log_action(
        session,
        actor_email=user.email,
        action="cursor.link_project",
        entity_type="project",
        entity_id=project_id,
        detail=str(art.id),
    )
    await session.commit()
    return {"ok": True}


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(
    artifact_id: int,
    user: User = Depends(require_roles("admin", "coordenador", "dev")),
    session: AsyncSession = Depends(get_session),
):
    art = (await session.execute(select(CursorArtifact).where(CursorArtifact.id == artifact_id))).scalar_one_or_none()
    if not art:
        raise HTTPException(status_code=404, detail="Artefato não encontrado")
    await session.execute(delete(ProjectCursorArtifact).where(ProjectCursorArtifact.artifact_id == artifact_id))
    await session.delete(art)
    await log_action(
        session,
        actor_email=user.email,
        action="cursor.delete",
        entity_type="cursor_artifact",
        entity_id=artifact_id,
    )
    await session.commit()
