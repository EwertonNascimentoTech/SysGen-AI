"""Planejamento técnico via Azure AI Agents (PRD + export MinIO)."""

from __future__ import annotations

import base64
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models.project import Project, ProjectPrdVersion, ProjectStitchGeneration
from app.models.user import User
from app.core.config import settings
from app.schemas.planejamento import (
    PlanejamentoAgentOut,
    PlanejamentoApprovalBody,
    PlanejamentoApprovalOut,
    PlanejamentoContextOut,
    PlanejamentoStoredOut,
)
from app.services.audit import log_action
from app.services.azure_openai_chat import is_planejador_ai_configured
from app.services.epa_service import generate_text_with_azure_agent
from app.services.azure_runtime_env import get_planejador_agent_id
from app.services.planejamento_attachments import (
    build_minio_prefix_inventory_attachment,
    load_stitch_export_attachment_dicts,
)
from app.services.planejamento_kanban_sync import sync_planejamento_to_kanban

router = APIRouter(prefix="/projects", tags=["planejamento"])

PLANEJAMENTO_STACK_DOCUMENTADA = (
    "Frontend Vue 3 + TypeScript; backend FastAPI + Python; filas e wiki assíncronas com Redis quando "
    "configurado; anexos e export Stitch via MinIO/S3 quando o endpoint S3 está definido."
)


async def build_planejamento_context(session: AsyncSession, p: Project) -> PlanejamentoContextOut:
    gh_oauth = bool((settings.github_client_id or "").strip() and (settings.github_client_secret or "").strip())
    s3_ok = bool((getattr(settings, "s3_endpoint_url", None) or "").strip())
    stitch_ok = bool((getattr(settings, "stitch_api_key", None) or "").strip())
    planejador_ok = await is_planejador_ai_configured(session)
    return PlanejamentoContextOut(
        stack_documentada=PLANEJAMENTO_STACK_DOCUMENTADA,
        methodology=(p.methodology or "").strip() or "—",
        github_repo_url=(p.github_repo_url or "").strip() or None,
        github_tag=(p.github_tag or "").strip() or None,
        s3_configured=s3_ok,
        github_oauth_configured=gh_oauth,
        stitch_api_configured=stitch_ok,
        azure_planejador_ready=planejador_ok,
    )


@router.get("/{project_id}/planejamento", response_model=PlanejamentoStoredOut)
async def get_planejamento_stored(
    project_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Devolve o último JSON de planejamento guardado na base (sem regenerar)."""
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    raw = (p.planejamento_json or "").strip()
    ctx = await build_planejamento_context(session, p)
    return PlanejamentoStoredOut(
        text=raw or None,
        saved_at=p.planejamento_json_saved_at,
        approved_at=p.planejamento_json_approved_at,
        context=ctx,
    )


@router.post("/{project_id}/planejamento/approval", response_model=PlanejamentoApprovalOut)
async def set_planejamento_approval(
    project_id: int,
    body: PlanejamentoApprovalBody,
    user: User = Depends(require_roles("admin", "coordenador", "po")),
    session: AsyncSession = Depends(get_session),
):
    """Marca ou remove a aprovação do último JSON de planejamento guardado."""
    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    if not (p.planejamento_json or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não há planejamento guardado para aprovar.",
        )
    if body.approved:
        p.planejamento_json_approved_at = datetime.now(timezone.utc)
    else:
        p.planejamento_json_approved_at = None
    raw_json = (p.planejamento_json or "").strip()
    removed, created = await sync_planejamento_to_kanban(session, project_id, raw_json, body.approved)
    await log_action(
        session,
        actor_email=user.email,
        action="project.planejamento.approval",
        entity_type="project",
        entity_id=p.id,
        detail=f"approved={body.approved} tasks_removed={removed} tasks_created={created}",
    )
    await session.commit()
    return PlanejamentoApprovalOut(
        approved_at=p.planejamento_json_approved_at,
        tasks_removed=removed,
        tasks_created=created,
    )


PLANEJAMENTO_USER_PROMPT = (
    "Transforma PRD + protótipo + stack em planejamento técnico estruturado em JSON para execução no "
    "Cursor, com frontend-first, fidelidade total ao layout e histórias organizadas por fases, dependências "
    "e batches.\n\n"
    "Em anexo: `prd.md` com o PRD guardado em Markdown e, em `prototipo_export/`, apenas HTML (.html/.htm) e "
    "imagens PNG do protótipo exportado no MinIO.\n\n"
    f"Stack de referência da plataforma (salvo o PRD indicar outro): {PLANEJAMENTO_STACK_DOCUMENTADA}\n\n"
    "O JSON na raiz DEVE ser um objecto com duas áreas, por esta ordem lógica:\n"
    "1) `preparacao` (objecto, obrigatório): trabalho ANTES das fases de funcionalidades — preparar ambiente de "
    "desenvolvimento, repositório e branch strategy, Cursor (regras, extensões, contexto), contratos de API ou "
    "stubs, arquitetura em alto nível (módulos, front/back), convenções de código, pipelines mínimos e critérios "
    "de «definition of ready» para começar tarefas integradas no Cursor. Campos: `titulo` (ex.: "
    "«Preparação: ambiente, arquitetura e Cursor»), `percentual_concluido` (0–100), `itens` (array de tarefas "
    "com `titulo`, `status` em pt-BR, `descricao` opcional, `batch`/`id`/`layout` quando fizer sentido).\n"
    "2) `fases` (array, obrigatório): fases de entrega alinhadas ao PRD e ao protótipo (cada fase com `titulo`, "
    "`percentual_concluido`, `itens` com a mesma estrutura).\n\n"
    "Ordem de execução sugerida ao equipa: concluir o máximo possível em `preparacao` antes de avançar nas "
    "`fases`.\n\n"
    "Gere a saída sempre em JSON com conteúdo textual em português do Brasil (pt-BR).\n\n"
    "Responde única e exclusivamente com o JSON final pedido (válido RFC 8259), sem cercas ``` nem texto "
    "antes ou depois."
)


@router.post("/{project_id}/planejamento/azure-agent", response_model=PlanejamentoAgentOut)
async def run_planejamento_azure_agent(
    project_id: int,
    user: User = Depends(require_roles("admin", "coordenador", "po")),
    session: AsyncSession = Depends(get_session),
):
    """
    Chama o agente `AZURE_AI_AGENT_PLANEJADOR_ID` com o PRD actual e, do último export Stitch no MinIO,
    apenas ficheiros `.html`/`.htm` e `.png`.
    """
    if not await is_planejador_ai_configured(session):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Agente de planejamento não configurado: defina AZURE_AI_PROJECT_ENDPOINT (ou "
                "AZURE_AI_PROJECT_CONNECTION_STRING) e AZURE_AI_AGENT_PLANEJADOR_ID."
            ),
        )
    agent_id = get_planejador_agent_id()
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Defina AZURE_AI_AGENT_PLANEJADOR_ID com o ID do agente Azure.",
        )

    p = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    latest_prd = (
        await session.execute(
            select(ProjectPrdVersion)
            .where(ProjectPrdVersion.project_id == project_id)
            .order_by(ProjectPrdVersion.version.desc())
            .limit(1),
        )
    ).scalar_one_or_none()

    if latest_prd:
        md = (latest_prd.markdown or "").strip()
    else:
        md = (p.prd_markdown or "").strip()

    if not md:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não há PRD guardado neste projeto. Guarde um PRD antes de gerar o planejamento.",
        )

    # Última geração com export gravado (evita escolher uma geração nova ainda sem «Aprovar» no MinIO).
    row = (
        await session.execute(
            select(ProjectStitchGeneration)
            .where(ProjectStitchGeneration.project_id == project_id)
            .where(
                and_(
                    ProjectStitchGeneration.export_storage_prefix.isnot(None),
                    ProjectStitchGeneration.export_storage_prefix != "",
                ),
            )
            .order_by(
                ProjectStitchGeneration.approved_at.desc().nullslast(),
                ProjectStitchGeneration.created_at.desc(),
            )
            .limit(1),
        )
    ).scalar_one_or_none()
    if not row or not (row.export_storage_prefix or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não há protótipo exportado no MinIO. Aprove e grave o export na aba Protótipo primeiro.",
        )

    prefix = row.export_storage_prefix.strip()
    try:
        export_attachments, export_warnings = load_stitch_export_attachment_dicts(prefix)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Falha ao ler export do MinIO: {e!s}",
        ) from e

    if not export_attachments:
        inv, inv_warnings = build_minio_prefix_inventory_attachment(prefix)
        export_warnings.extend(inv_warnings)
        if inv:
            export_attachments = [inv]
            export_warnings.append(
                "Nenhum ficheiro .html/.htm/.png encontrado; foi anexada apenas a listagem de caminhos no MinIO.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "O export no MinIO está vazio ou inacessível, ou não contém ficheiros .html/.htm/.png utilizáveis. "
                    f"({' '.join(inv_warnings)})"
                ),
            )

    prd_b64 = base64.standard_b64encode(md.encode("utf-8")).decode("ascii")
    attachment_dicts: list[dict[str, str]] = [
        {
            "filename": "prd.md",
            "mime_type": "text/markdown; charset=utf-8",
            "content_base64": prd_b64,
        },
        *export_attachments,
    ]

    try:
        text, finish = await generate_text_with_azure_agent(
            session=session,
            mode="planejamento",
            messages=[{"role": "user", "content": PLANEJAMENTO_USER_PROMPT}],
            attachment_dicts=attachment_dicts,
            agent_id_override=agent_id,
            max_completion_tokens=12_288,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)[:4000] or "Falha ao invocar o Azure AI Agents.",
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(e) or "Anexos demasiado grandes (limite agregado 8 MB para o agente).",
        ) from e

    if not (text or "").strip() or text.startswith("A integração Azure AI Agents"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=text or "Resposta vazia do agente Azure.",
        )

    out_text = text.strip()
    now = datetime.now(timezone.utc)
    p.planejamento_json = out_text
    p.planejamento_json_saved_at = now
    p.planejamento_json_approved_at = None

    await log_action(
        session,
        actor_email=user.email,
        action="project.planejamento.azure_agent",
        entity_type="project",
        entity_id=p.id,
        detail=f"export_prefix={prefix} anexos_export={len(export_attachments)} saved=1",
    )
    await session.commit()

    return PlanejamentoAgentOut(text=out_text, finish_reason=finish, warnings=export_warnings)
