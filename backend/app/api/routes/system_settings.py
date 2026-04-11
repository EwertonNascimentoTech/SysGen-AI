from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models.user import User
from app.schemas.system_settings import GeneralSettingsOut, GeneralSettingsUpdate
from app.services.audit import log_action
from app.services.system_general_settings import DEFAULT_ID, ensure_system_general_settings_row

router = APIRouter(prefix="/system-settings", tags=["system-settings"])

_ALLOWED_LOCALES = frozenset({"pt-BR", "en-US"})


def _to_out(row) -> GeneralSettingsOut:
    return GeneralSettingsOut(
        org_name=row.org_name,
        locale=row.locale,
        audit_strict=bool(row.audit_strict),
        ai_indexing=bool(row.ai_indexing),
    )


@router.get("/general", response_model=GeneralSettingsOut)
async def get_general_settings(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await ensure_system_general_settings_row(session)
    return _to_out(row)


@router.patch("/general", response_model=GeneralSettingsOut)
async def patch_general_settings(
    body: GeneralSettingsUpdate,
    actor: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    if body.model_dump(exclude_unset=True) == {}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum campo para atualizar")
    row = await ensure_system_general_settings_row(session)
    if body.org_name is not None:
        row.org_name = body.org_name.strip()
    if body.locale is not None:
        loc = body.locale.strip()
        if loc not in _ALLOWED_LOCALES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Localidade inválida. Use: {', '.join(sorted(_ALLOWED_LOCALES))}",
            )
        row.locale = loc
    if body.audit_strict is not None:
        row.audit_strict = body.audit_strict
    if body.ai_indexing is not None:
        row.ai_indexing = body.ai_indexing
    await log_action(
        session,
        actor_email=actor.email,
        action="system_settings.general.patch",
        entity_type="system_general_settings",
        entity_id=DEFAULT_ID,
        detail=f"org={row.org_name!r} locale={row.locale}",
    )
    await session.commit()
    await session.refresh(row)
    return _to_out(row)
