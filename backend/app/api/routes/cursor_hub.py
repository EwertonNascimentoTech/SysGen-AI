from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_session
from app.models.cursor_artifact import CursorArtifact, ProjectCursorArtifact
from app.models.project import Project
from app.models.user import User
from app.schemas.cursor import CursorArtifactCreate, CursorArtifactOut, LinkArtifactBody
from app.services.audit import log_action

router = APIRouter(prefix="/cursor-artifacts", tags=["cursor-artifacts"])


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
            status=a.status,
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
        status="rascunho",
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


@router.post("/{artifact_id}/publish", response_model=CursorArtifactOut)
async def publish_artifact(
    artifact_id: int,
    user: User = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    art = (await session.execute(select(CursorArtifact).where(CursorArtifact.id == artifact_id))).scalar_one_or_none()
    if not art:
        raise HTTPException(status_code=404, detail="Artefato não encontrado")
    art.status = "publicado"
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
    if art.status != "publicado":
        raise HTTPException(status_code=400, detail="Apenas artefatos publicados podem ser vinculados")
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
