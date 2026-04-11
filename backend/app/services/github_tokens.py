from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_identity import UserIdentity
from app.services.token_crypt import decrypt_token


def _token_from_github_identity(ident: UserIdentity) -> str | None:
    try:
        return decrypt_token(ident.access_token_encrypted)
    except Exception:
        return None


async def resolve_user_github_oauth_token_async(session: AsyncSession, user: User | None) -> str | None:
    """Token da conta GitHub OAuth ligada ao utilizador."""
    if user is None:
        return None
    await session.refresh(user, ["identities"])
    for ident in user.identities:
        if ident.provider != "github":
            continue
        t = _token_from_github_identity(ident)
        if t:
            return t
    return None


def resolve_user_github_oauth_token_sync(session: Session, user_id: int | None) -> str | None:
    """Versão síncrona (ex.: worker da wiki)."""
    if not user_id:
        return None
    user = session.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        return None
    ident = session.execute(
        select(UserIdentity).where(UserIdentity.user_id == user.id, UserIdentity.provider == "github")
    ).scalar_one_or_none()
    if not ident:
        return None
    return _token_from_github_identity(ident)


async def resolve_github_token_for_project_api_async(session: AsyncSession, user: User | None) -> str | None:
    """Token para tags, refs e wiki: apenas OAuth do utilizador."""
    return await resolve_user_github_oauth_token_async(session, user)


def resolve_github_token_for_project_api_sync(session: Session, user_id: int | None) -> str | None:
    """Equivalente síncrono para jobs (wiki)."""
    return resolve_user_github_oauth_token_sync(session, user_id)
