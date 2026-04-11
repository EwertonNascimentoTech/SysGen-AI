from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.directory import Directory
from app.models.user import User

router = APIRouter(prefix="/directories", tags=["directories"])


class DirectoryOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


@router.get("", response_model=list[DirectoryOut])
async def list_directories(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Directory).order_by(Directory.name))
    return list(result.scalars().all())
