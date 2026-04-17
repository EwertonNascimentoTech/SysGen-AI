from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models.project import Project, ProjectPrdVersion
from app.models.user import User
from app.schemas.prd_chat import (
    PrdAzureStatusOut,
    PrdChatRequest,
    PrdChatResponse,
    PrdMarkdownDocumentOut,
    PrdMarkdownSaveBody,
    PrdVersionDetailOut,
    PrdVersionItemOut,
)
from app.services.audit import log_action
from app.services.azure_openai_chat import is_prd_ai_configured, run_chat
from app.services.prd_reply_normalize import strip_prd_marker_and_flag

router = APIRouter(prefix="/projects", tags=["prd"])


@router.get("/{project_id}/prd/azure-status", response_model=PrdAzureStatusOut)
async def prd_azure_status(
    project_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return PrdAzureStatusOut(configured=await is_prd_ai_configured(session))


@router.get("/{project_id}/prd/markdown", response_model=PrdMarkdownDocumentOut)
async def get_prd_markdown(
    project_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    ver = p.prd_current_version
    if ver is None:
        ver = await session.scalar(
            select(func.max(ProjectPrdVersion.version)).where(ProjectPrdVersion.project_id == project_id),
        )
    return PrdMarkdownDocumentOut(markdown=p.prd_markdown, saved_at=p.prd_markdown_saved_at, version=ver)


@router.put("/{project_id}/prd/markdown", response_model=PrdMarkdownDocumentOut)
async def save_prd_markdown(
    project_id: int,
    body: PrdMarkdownSaveBody,
    user: User = Depends(require_roles("admin", "coordenador", "po")),
    session: AsyncSession = Depends(get_session),
):
    md = body.markdown.strip()
    if not md:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O Markdown não pode ficar vazio.")

    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    now = datetime.now(timezone.utc)
    max_v = await session.scalar(
        select(func.coalesce(func.max(ProjectPrdVersion.version), 0)).where(ProjectPrdVersion.project_id == p.id),
    )
    next_v = int(max_v or 0) + 1
    session.add(
        ProjectPrdVersion(
            project_id=p.id,
            version=next_v,
            markdown=md,
            created_by_email=user.email,
        ),
    )
    p.prd_markdown = md
    p.prd_markdown_saved_at = now
    p.prd_current_version = next_v
    await log_action(
        session,
        actor_email=user.email,
        action="project.prd.markdown.save",
        entity_type="project",
        entity_id=p.id,
        detail=f"v={next_v}",
    )
    await session.commit()
    await session.refresh(p)
    return PrdMarkdownDocumentOut(
        markdown=p.prd_markdown,
        saved_at=p.prd_markdown_saved_at,
        version=p.prd_current_version,
    )


@router.get("/{project_id}/prd/versions", response_model=list[PrdVersionItemOut])
async def list_prd_versions(
    project_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    rows = (
        (
            await session.execute(
                select(ProjectPrdVersion)
                .where(ProjectPrdVersion.project_id == project_id)
                .order_by(ProjectPrdVersion.version.desc()),
            )
        )
        .scalars()
        .all()
    )
    max_v = max((r.version for r in rows), default=None)
    return [
        PrdVersionItemOut(
            version=r.version,
            created_at=r.created_at,
            created_by_email=r.created_by_email,
            is_latest=(max_v is not None and r.version == max_v),
        )
        for r in rows
    ]


@router.get("/{project_id}/prd/versions/{version}", response_model=PrdVersionDetailOut)
async def get_prd_version(
    project_id: int,
    version: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    row = (
        await session.execute(
            select(ProjectPrdVersion).where(
                ProjectPrdVersion.project_id == project_id,
                ProjectPrdVersion.version == version,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Versão PRD não encontrada")
    max_v = await session.scalar(
        select(func.max(ProjectPrdVersion.version)).where(ProjectPrdVersion.project_id == project_id),
    )
    return PrdVersionDetailOut(
        version=row.version,
        markdown=row.markdown,
        created_at=row.created_at,
        created_by_email=row.created_by_email,
        is_latest=(max_v is not None and row.version == max_v),
    )


@router.patch("/{project_id}/prd/versions/{version}", response_model=PrdVersionDetailOut)
async def patch_prd_version(
    project_id: int,
    version: int,
    body: PrdMarkdownSaveBody,
    user: User = Depends(require_roles("admin", "coordenador", "po")),
    session: AsyncSession = Depends(get_session),
):
    md = body.markdown.strip()
    if not md:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O Markdown não pode ficar vazio.")

    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    row = (
        await session.execute(
            select(ProjectPrdVersion).where(
                ProjectPrdVersion.project_id == project_id,
                ProjectPrdVersion.version == version,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Versão PRD não encontrada")

    max_v = await session.scalar(
        select(func.coalesce(func.max(ProjectPrdVersion.version), 0)).where(ProjectPrdVersion.project_id == project_id),
    )
    max_v = int(max_v or 0)
    if max_v == 0 or version != max_v:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Só a última versão do PRD pode ser editada.",
        )

    now = datetime.now(timezone.utc)
    next_v = max_v + 1
    new_row = ProjectPrdVersion(
        project_id=p.id,
        version=next_v,
        markdown=md,
        created_by_email=user.email,
    )
    session.add(new_row)
    p.prd_markdown = md
    p.prd_markdown_saved_at = now
    p.prd_current_version = next_v
    await log_action(
        session,
        actor_email=user.email,
        action="project.prd.version.update",
        entity_type="project",
        entity_id=p.id,
        detail=f"v={next_v} (editado a partir de v={version})",
    )
    await session.commit()
    await session.refresh(new_row)
    await session.refresh(p)
    return PrdVersionDetailOut(
        version=new_row.version,
        markdown=new_row.markdown,
        created_at=new_row.created_at,
        created_by_email=new_row.created_by_email,
        is_latest=True,
    )


@router.post("/{project_id}/prd/chat", response_model=PrdChatResponse)
async def prd_chat(
    project_id: int,
    body: PrdChatRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    if not await is_prd_ai_configured(session):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "IA não configurada: defina Azure AI Agents (AZURE_AI_PROJECT_ENDPOINT ou "
                "AZURE_AI_PROJECT_CONNECTION_STRING + AZURE_AI_AGENT_ID) ou Azure OpenAI "
                "(AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT)."
            ),
        )

    raw_msgs = [{"role": m.role, "content": m.content} for m in body.messages]
    if not raw_msgs or raw_msgs[-1]["role"] != "user":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envie pelo menos uma mensagem do utilizador como última entrada.",
        )

    atts = [a.model_dump() for a in body.attachments]

    try:
        text, finish = await run_chat(
            mode=body.mode,
            messages=raw_msgs,
            attachment_dicts=atts,
            session=session,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    clean_text, prd_rec = strip_prd_marker_and_flag(text)

    await log_action(
        session,
        actor_email=user.email,
        action="project.prd.chat",
        entity_type="project",
        entity_id=p.id,
        detail=f"mode={body.mode}",
    )
    await session.commit()

    return PrdChatResponse(
        message=clean_text,
        finish_reason=finish,
        prd_save_recommended=prd_rec,
    )
