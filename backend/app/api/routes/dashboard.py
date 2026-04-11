from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.cursor_artifact import ProjectCursorArtifact
from app.models.project import Project, ProjectWiki
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def dashboard_summary(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
):
    total = int(await session.scalar(select(func.count()).select_from(Project)) or 0)
    active = int(
        await session.scalar(
            select(func.count()).select_from(Project).where(Project.ended_at.is_(None))
        )
        or 0
    )
    github = int(
        await session.scalar(
            select(func.count())
            .select_from(Project)
            .where(Project.github_repo_url.isnot(None), Project.github_repo_url != "")
        )
        or 0
    )
    wikis = int(
        await session.scalar(
            select(func.count()).select_from(ProjectWiki).where(ProjectWiki.status == "ready")
        )
        or 0
    )
    cursor_links = int(
        await session.scalar(select(func.count()).select_from(ProjectCursorArtifact)) or 0
    )
    return {
        "total_projects": total,
        "active_projects": active,
        "github_linked": github,
        "wikis_ready": wikis,
        "cursor_artifact_links": cursor_links,
    }
