from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_session
from app.models.audit import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditOut(BaseModel):
    id: int
    created_at: object
    actor_email: str
    action: str
    entity_type: str | None
    entity_id: int | None
    detail: str | None

    class Config:
        from_attributes = True


@router.get("", response_model=list[AuditOut])
async def list_audit(
    _: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(200))
    return list(result.scalars().all())
