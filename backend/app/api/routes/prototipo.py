from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.db.session import get_session
from app.models.project import (
    Project,
    ProjectPrdVersion,
    ProjectPrototipoPromptVersion,
    ProjectStitchGeneration,
)
from app.models.user import User
from app.schemas.prototipo import (
    PrototipoDocumentOut,
    PrototipoPromptOut,
    PrototipoPromptSaveBody,
    StitchApiGenerateOut,
    StitchApiStatusOut,
    StitchApproveExportOut,
    StitchExportManifestOut,
    StitchLatestOut,
    PrototipoVersionDetailOut,
    PrototipoVersionItemOut,
)
from app.services.audit import log_action
from app.services.azure_openai_chat import is_prototipo_ai_configured
from app.services.epa_service import generate_text_with_azure_agent
from app.services.azure_runtime_env import get_prototipo_agent_id
from app.services.stitch_api_runner import (
    run_stitch_collect_export,
    run_stitch_generate,
    save_stitch_export_to_minio,
    stitch_api_configured,
    stitch_api_status_detail,
)
from app.services.storage import (
    content_type_for_storage_key,
    list_object_keys_under_prefix,
    read_object_bytes,
    relative_paths_under_prefix,
)

router = APIRouter(prefix="/projects", tags=["prototipo"])


async def _persist_new_prototipo_version(
    session: AsyncSession,
    p: Project,
    prompt_text: str,
    prd_version_used: int | None,
    user_email: str | None,
) -> int:
    """Insere linha de versão e actualiza espelho em `projects`. Devolve o número da nova versão."""
    now = datetime.now(timezone.utc)
    max_v = await session.scalar(
        select(func.coalesce(func.max(ProjectPrototipoPromptVersion.version), 0)).where(
            ProjectPrototipoPromptVersion.project_id == p.id,
        ),
    )
    next_v = int(max_v or 0) + 1
    session.add(
        ProjectPrototipoPromptVersion(
            project_id=p.id,
            version=next_v,
            prompt=prompt_text.strip(),
            prd_version_used=prd_version_used,
            created_by_email=user_email,
        ),
    )
    p.prototipo_prompt = prompt_text.strip()
    p.prototipo_prompt_saved_at = now
    p.prototipo_current_version = next_v
    return next_v


@router.get("/{project_id}/prototipo", response_model=PrototipoDocumentOut)
async def get_prototipo_document(
    project_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Última versão do prompt de protótipo guardada."""
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    latest = (
        await session.execute(
            select(ProjectPrototipoPromptVersion)
            .where(ProjectPrototipoPromptVersion.project_id == project_id)
            .order_by(ProjectPrototipoPromptVersion.version.desc())
            .limit(1),
        )
    ).scalar_one_or_none()
    stitch_row = (
        await session.execute(
            select(ProjectStitchGeneration)
            .where(ProjectStitchGeneration.project_id == project_id)
            .order_by(ProjectStitchGeneration.created_at.desc())
            .limit(1),
        )
    ).scalar_one_or_none()
    stitch_latest = (
        StitchLatestOut(
            stitch_project_id=stitch_row.stitch_project_id,
            screen_id=stitch_row.screen_id,
            html_url=stitch_row.html_url,
            image_url=stitch_row.image_url,
            created_at=stitch_row.created_at,
            saved_id=stitch_row.id,
            approved_at=stitch_row.approved_at,
            approved_by_email=stitch_row.approved_by_email,
            export_storage_prefix=stitch_row.export_storage_prefix,
        )
        if stitch_row
        else None
    )
    if latest:
        return PrototipoDocumentOut(
            prompt=latest.prompt,
            version=latest.version,
            saved_at=latest.created_at,
            prd_version_used=latest.prd_version_used,
            stitch_latest=stitch_latest,
        )
    text = (p.prototipo_prompt or "").strip()
    return PrototipoDocumentOut(
        prompt=text,
        version=p.prototipo_current_version,
        saved_at=p.prototipo_prompt_saved_at,
        prd_version_used=None,
        stitch_latest=stitch_latest,
    )


@router.post("/{project_id}/prototipo/versions", response_model=PrototipoVersionDetailOut)
async def append_prototipo_version(
    project_id: int,
    body: PrototipoPromptSaveBody,
    user: User = Depends(require_roles("admin", "coordenador", "po")),
    session: AsyncSession = Depends(get_session),
):
    """
    Acrescenta sempre uma **nova** versão com o texto enviado (edição da última versão no ecrã).
    O histórico anterior mantém-se; não é necessário indicar o número da versão na URL.
    Reutiliza `prd_version_used` da versão mais recente quando existir (ex.: após geração por IA).
    """
    prompt_text = body.prompt.strip()
    if not prompt_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O prompt não pode ficar vazio.")

    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    latest = (
        await session.execute(
            select(ProjectPrototipoPromptVersion)
            .where(ProjectPrototipoPromptVersion.project_id == project_id)
            .order_by(ProjectPrototipoPromptVersion.version.desc())
            .limit(1),
        )
    ).scalar_one_or_none()
    prd_v = latest.prd_version_used if latest else None

    next_v = await _persist_new_prototipo_version(session, p, prompt_text, prd_v, user.email)

    await log_action(
        session,
        actor_email=user.email,
        action="project.prototipo.prompt.save",
        entity_type="project",
        entity_id=p.id,
        detail=f"v={next_v}",
    )
    await session.commit()

    new_row = (
        await session.execute(
            select(ProjectPrototipoPromptVersion).where(
                ProjectPrototipoPromptVersion.project_id == project_id,
                ProjectPrototipoPromptVersion.version == next_v,
            ),
        )
    ).scalar_one()

    return PrototipoVersionDetailOut(
        version=new_row.version,
        prompt=new_row.prompt,
        prd_version_used=new_row.prd_version_used,
        created_at=new_row.created_at,
        created_by_email=new_row.created_by_email,
        is_latest=True,
    )


@router.get("/{project_id}/prototipo/versions", response_model=list[PrototipoVersionItemOut])
async def list_prototipo_versions(
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
                select(ProjectPrototipoPromptVersion)
                .where(ProjectPrototipoPromptVersion.project_id == project_id)
                .order_by(ProjectPrototipoPromptVersion.version.desc()),
            )
        )
        .scalars()
        .all()
    )
    max_v = max((r.version for r in rows), default=None)
    return [
        PrototipoVersionItemOut(
            version=r.version,
            created_at=r.created_at,
            created_by_email=r.created_by_email,
            is_latest=(max_v is not None and r.version == max_v),
        )
        for r in rows
    ]


@router.get("/{project_id}/prototipo/versions/{version}", response_model=PrototipoVersionDetailOut)
async def get_prototipo_version(
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
            select(ProjectPrototipoPromptVersion).where(
                ProjectPrototipoPromptVersion.project_id == project_id,
                ProjectPrototipoPromptVersion.version == version,
            ),
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Versão de protótipo não encontrada")
    max_v = await session.scalar(
        select(func.max(ProjectPrototipoPromptVersion.version)).where(
            ProjectPrototipoPromptVersion.project_id == project_id,
        ),
    )
    return PrototipoVersionDetailOut(
        version=row.version,
        prompt=row.prompt,
        prd_version_used=row.prd_version_used,
        created_at=row.created_at,
        created_by_email=row.created_by_email,
        is_latest=(max_v is not None and row.version == max_v),
    )


@router.patch("/{project_id}/prototipo/versions/{version}", response_model=PrototipoVersionDetailOut)
async def patch_prototipo_version(
    project_id: int,
    version: int,
    body: PrototipoPromptSaveBody,
    user: User = Depends(require_roles("admin", "coordenador", "po")),
    session: AsyncSession = Depends(get_session),
):
    """Edita só a última versão; grava uma nova linha de versão (histórico imutável nas anteriores)."""
    prompt_text = body.prompt.strip()
    if not prompt_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O prompt não pode ficar vazio.")

    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    row = (
        await session.execute(
            select(ProjectPrototipoPromptVersion).where(
                ProjectPrototipoPromptVersion.project_id == project_id,
                ProjectPrototipoPromptVersion.version == version,
            ),
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Versão de protótipo não encontrada")

    max_v = await session.scalar(
        select(func.coalesce(func.max(ProjectPrototipoPromptVersion.version), 0)).where(
            ProjectPrototipoPromptVersion.project_id == project_id,
        ),
    )
    max_v = int(max_v or 0)
    if max_v == 0 or version != max_v:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Só a última versão do prompt pode ser editada.",
        )

    next_v = await _persist_new_prototipo_version(
        session,
        p,
        prompt_text,
        row.prd_version_used,
        user.email,
    )

    await log_action(
        session,
        actor_email=user.email,
        action="project.prototipo.prompt.save",
        entity_type="project",
        entity_id=p.id,
        detail=f"v={next_v}",
    )
    await session.commit()

    new_row = (
        await session.execute(
            select(ProjectPrototipoPromptVersion).where(
                ProjectPrototipoPromptVersion.project_id == project_id,
                ProjectPrototipoPromptVersion.version == next_v,
            ),
        )
    ).scalar_one()

    return PrototipoVersionDetailOut(
        version=new_row.version,
        prompt=new_row.prompt,
        prd_version_used=new_row.prd_version_used,
        created_at=new_row.created_at,
        created_by_email=new_row.created_by_email,
        is_latest=True,
    )


@router.post("/{project_id}/prototipo/generate-prompt", response_model=PrototipoPromptOut)
async def generate_prototipo_prompt(
    project_id: int,
    user: User = Depends(require_roles("admin", "coordenador", "po")),
    session: AsyncSession = Depends(get_session),
):
    """Gera com o agente `AZURE_AI_AGENT_PROTOTIPO_ID`, guarda nova versão na base."""
    if not await is_prototipo_ai_configured(session):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Agente de protótipo não configurado: defina AZURE_AI_PROJECT_ENDPOINT (ou "
                "AZURE_AI_PROJECT_CONNECTION_STRING) e AZURE_AI_AGENT_PROTOTIPO_ID."
            ),
        )

    agent_id = get_prototipo_agent_id()
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Defina AZURE_AI_AGENT_PROTOTIPO_ID com o ID do agente Azure.",
        )

    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    latest = (
        await session.execute(
            select(ProjectPrdVersion)
            .where(ProjectPrdVersion.project_id == project_id)
            .order_by(ProjectPrdVersion.version.desc())
            .limit(1),
        )
    ).scalar_one_or_none()

    if latest:
        md = (latest.markdown or "").strip()
        ver = latest.version
    else:
        md = (p.prd_markdown or "").strip()
        ver = p.prd_current_version

    if not md:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não há PRD guardado neste projeto. Crie e guarde um PRD antes de gerar o prompt de protótipo.",
        )

    user_content = (
        "Gera o prompt de protótipo solicitado com base exclusivamente no seguinte PRD "
        f"(versão {ver if ver is not None else '—'}).\n\n"
        "--- PRD ---\n\n"
        f"{md}"
    )

    text, finish = await generate_text_with_azure_agent(
        session=session,
        mode="prototipo",
        messages=[{"role": "user", "content": user_content}],
        attachment_dicts=[],
        agent_id_override=agent_id,
    )

    if not (text or "").strip() or text.startswith("A integração Azure AI Agents"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=text or "Resposta vazia do agente Azure.",
        )

    prompt_clean = text.strip()
    next_v = await _persist_new_prototipo_version(session, p, prompt_clean, ver, user.email)

    await log_action(
        session,
        actor_email=user.email,
        action="project.prototipo.prompt.generate",
        entity_type="project",
        entity_id=p.id,
        detail=f"prd_v={ver} prompt_v={next_v}",
    )
    await session.commit()
    await session.refresh(p)

    return PrototipoPromptOut(
        prompt=prompt_clean,
        prd_version=ver,
        prompt_version=next_v,
        finish_reason=finish,
    )


async def _latest_prototipo_prompt_text(session: AsyncSession, project_id: int, p: Project) -> str:
    latest = (
        await session.execute(
            select(ProjectPrototipoPromptVersion)
            .where(ProjectPrototipoPromptVersion.project_id == project_id)
            .order_by(ProjectPrototipoPromptVersion.version.desc())
            .limit(1),
        )
    ).scalar_one_or_none()
    if latest and (latest.prompt or "").strip():
        return (latest.prompt or "").strip()
    return (p.prototipo_prompt or "").strip()


@router.get("/{project_id}/prototipo/stitch-api/status", response_model=StitchApiStatusOut)
async def stitch_api_status(
    project_id: int,
    _: User = Depends(get_current_user),
):
    """Indica se o servidor pode chamar a API MCP do Google Stitch (`@google/stitch-sdk`)."""
    del project_id
    detail = stitch_api_status_detail()
    return StitchApiStatusOut(ready=stitch_api_configured(), detail=detail)


@router.post("/{project_id}/prototipo/stitch-api/generate", response_model=StitchApiGenerateOut)
async def stitch_api_generate_screen(
    project_id: int,
    user: User = Depends(require_roles("admin", "coordenador", "po")),
    session: AsyncSession = Depends(get_session),
):
    """
    Gera um ecrã no Stitch via API oficial (MCP), usando o texto do último prompt de protótipo guardado.
    Requer `STITCH_API_KEY`, Node.js e `backend/stitch_runner` com `npm ci`.
    """
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    prompt_text = await _latest_prototipo_prompt_text(session, project_id, p)
    if not prompt_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não há prompt de protótipo. Gere ou escreva um prompt na aba Protótipo antes.",
        )

    if not stitch_api_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=stitch_api_status_detail() or "API Stitch indisponível neste servidor.",
        )

    try:
        out = await run_stitch_generate(
            prompt=prompt_text,
            project_title=f"{p.name} — protótipo",
            stitch_project_id=(settings.stitch_project_id or "").strip() or None,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    row = ProjectStitchGeneration(
        project_id=p.id,
        stitch_project_id=str(out["stitch_project_id"]),
        screen_id=str(out["screen_id"]),
        html_url=out["html_url"],
        image_url=out["image_url"],
        created_by_email=user.email,
    )
    session.add(row)
    await session.flush()

    await log_action(
        session,
        actor_email=user.email,
        action="project.prototipo.stitch.api.generate",
        entity_type="project",
        entity_id=p.id,
        detail=f"saved_id={row.id} stitch_project={out.get('stitch_project_id', '')} screen={out.get('screen_id', '')}",
    )
    await session.commit()

    return StitchApiGenerateOut(
        stitch_project_id=out["stitch_project_id"],
        screen_id=out["screen_id"],
        html_url=out["html_url"],
        image_url=out["image_url"],
        saved_id=row.id,
    )


@router.post("/{project_id}/prototipo/stitch-api/approve-and-export", response_model=StitchApproveExportOut)
async def stitch_api_approve_and_save_to_minio(
    project_id: int,
    user: User = Depends(require_roles("admin", "coordenador", "po")),
    session: AsyncSession = Depends(get_session),
):
    """
    Marca a última geração Stitch como aprovada e grava no MinIO/S3 só o conteúdo dos ecrãs,
    em `prototipo/{nome_do_projeto}/{id}/`, com uma pasta por ecrã nomeada pelo título da página.
    """
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    row = (
        await session.execute(
            select(ProjectStitchGeneration)
            .where(ProjectStitchGeneration.project_id == project_id)
            .order_by(ProjectStitchGeneration.created_at.desc())
            .limit(1),
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não há geração Stitch na base. Use «Gerar ecrã (API Stitch)» primeiro.",
        )

    if not stitch_api_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=stitch_api_status_detail() or "API Stitch indisponível neste servidor.",
        )
    if not (settings.s3_endpoint_url or "").strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MinIO/S3 não configurado (S3_ENDPOINT_URL). Não é possível gravar o pacote.",
        )

    try:
        payload = await run_stitch_collect_export(row.stitch_project_id)
        prefix = await save_stitch_export_to_minio(project_id, p.name, payload)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    now = datetime.now(timezone.utc)
    row.approved_at = now
    row.approved_by_email = user.email
    row.export_storage_prefix = prefix
    await log_action(
        session,
        actor_email=user.email,
        action="project.prototipo.stitch.approve_export",
        entity_type="project",
        entity_id=p.id,
        detail=f"saved_id={row.id} stitch_project={row.stitch_project_id} minio_prefix={prefix}",
    )
    await session.commit()

    return StitchApproveExportOut(storage_prefix=prefix)


def _normalize_stitch_export_rel(rel: str) -> str:
    s = rel.replace("\\", "/").strip("/")
    if not s or any(p == ".." for p in s.split("/")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Caminho rel inválido.")
    return s


@router.get("/{project_id}/prototipo/stitch-api/export-manifest", response_model=StitchExportManifestOut)
async def stitch_export_manifest(
    project_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lista ficheiros gravados no MinIO sob o último prefixo de export (para descarregar pasta sem ZIP)."""
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    row = (
        await session.execute(
            select(ProjectStitchGeneration)
            .where(ProjectStitchGeneration.project_id == project_id)
            .order_by(ProjectStitchGeneration.created_at.desc())
            .limit(1),
        )
    ).scalar_one_or_none()
    if not row or not (row.export_storage_prefix or "").strip():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Não há export gravado no MinIO. Aprove e grave primeiro.",
        )
    if not (settings.s3_endpoint_url or "").strip():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="S3/MinIO não configurado.")

    prefix = row.export_storage_prefix.strip()
    try:
        keys = list_object_keys_under_prefix(prefix)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    files = relative_paths_under_prefix(prefix, keys)
    return StitchExportManifestOut(storage_prefix=prefix, files=files)


@router.get("/{project_id}/prototipo/stitch-api/export-file")
async def stitch_export_file_proxy(
    project_id: int,
    rel: str = Query(..., min_length=1, description="Caminho relativo ao prefixo, ex. Titulo/meta.json"),
    _: User = Depends(require_roles("admin", "coordenador", "po")),
    session: AsyncSession = Depends(get_session),
):
    """Serve um ficheiro do export via API (evita CORS do MinIO ao gravar pasta local no browser)."""
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    row = (
        await session.execute(
            select(ProjectStitchGeneration)
            .where(ProjectStitchGeneration.project_id == project_id)
            .order_by(ProjectStitchGeneration.created_at.desc())
            .limit(1),
        )
    ).scalar_one_or_none()
    if not row or not (row.export_storage_prefix or "").strip():
        raise HTTPException(status_code=404, detail="Não há export gravado.")
    if not (settings.s3_endpoint_url or "").strip():
        raise HTTPException(status_code=503, detail="S3/MinIO não configurado.")

    prefix = row.export_storage_prefix.strip().rstrip("/")
    rel_norm = _normalize_stitch_export_rel(rel)
    key = f"{prefix}/{rel_norm}"
    if not key.startswith(prefix + "/"):
        raise HTTPException(status_code=400, detail="Caminho fora do prefixo.")

    try:
        data = read_object_bytes(key)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Objecto não encontrado: {e!s}") from e

    filename = rel_norm.split("/")[-1]
    ctype = content_type_for_storage_key(key)
    return Response(
        content=data,
        media_type=ctype,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=0",
        },
    )
