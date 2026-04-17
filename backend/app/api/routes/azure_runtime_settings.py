from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models.user import User
from app.schemas.azure_runtime import (
    AzureAiRequestProbeResponse,
    AzureRuntimeConfigPayload,
    AzureRuntimeConfigResponse,
    AzureRuntimeTestResponse,
)
from app.services.epa_service import (
    build_masked_runtime_view,
    persist_runtime_azure_settings,
    run_azure_ai_connection_tests,
    run_azure_ai_request_probes,
)

router = APIRouter(prefix="/settings", tags=["azure-runtime"])


@router.get("/azure-runtime", response_model=AzureRuntimeConfigResponse)
async def get_azure_runtime_settings(
    _: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    data = await build_masked_runtime_view(session)
    return AzureRuntimeConfigResponse(**data)


@router.put("/azure-runtime", response_model=AzureRuntimeConfigResponse)
async def put_azure_runtime_settings(
    body: AzureRuntimeConfigPayload,
    _: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum campo para atualizar")
    await persist_runtime_azure_settings(session, patch)
    data = await build_masked_runtime_view(session)
    return AzureRuntimeConfigResponse(**data)


@router.post("/azure-runtime/test", response_model=AzureRuntimeTestResponse)
async def post_azure_runtime_test(
    _: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    data = await run_azure_ai_connection_tests(session)
    return AzureRuntimeTestResponse(**data)


@router.post("/azure-runtime/request-probe", response_model=AzureAiRequestProbeResponse)
async def post_azure_ai_request_probe(
    _: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    """
    Executa requisições reais ao Azure: POST chat/completions (OpenAI) e um turno mínimo no Agents.
    Pode incorrer em custo de tokens; usar para diagnóstico pontual.
    """
    data = await run_azure_ai_request_probes(session)
    return AzureAiRequestProbeResponse(**data)
