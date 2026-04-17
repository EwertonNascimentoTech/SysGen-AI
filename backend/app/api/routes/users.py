from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_roles
from app.core.security import hash_password
from app.db.session import get_session
from app.models.user import Role, User
from app.schemas.user_admin import UserCreate, UserOut, UserUpdate
from app.services.audit import log_action

router = APIRouter(prefix="/users", tags=["users"])


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        full_name=u.full_name,
        is_active=u.is_active,
        roles=[r.code for r in u.roles],
        github_login=u.github_login,
    )


@router.get("", response_model=list[UserOut])
async def list_users(
    _: User = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(User).options(selectinload(User.roles)).order_by(User.email))
    return [_user_out(u) for u in result.scalars().unique().all()]


@router.post("", response_model=UserOut)
async def create_user(
    body: UserCreate,
    admin: User = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    email_norm = str(body.email).strip().lower()
    exists = (
        await session.execute(select(User).where(func.lower(func.trim(User.email)) == email_norm))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado")
    roles_result = await session.execute(select(Role).where(Role.code.in_(body.role_codes)))
    roles = list(roles_result.scalars().all())
    if len(roles) != len(set(body.role_codes)):
        raise HTTPException(status_code=400, detail="Perfil inválido")
    gh = (body.github_login or "").strip() or None
    if gh:
        taken = (
            await session.execute(
                select(User).where(func.lower(User.github_login) == gh.lower(), User.github_login.isnot(None))
            )
        ).scalar_one_or_none()
        if taken:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Login GitHub já associado a outro usuário")

    u = User(
        email=email_norm,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        roles=roles,
        github_login=gh,
    )
    session.add(u)
    await session.flush()
    await log_action(
        session,
        actor_email=admin.email,
        action="user.create",
        entity_type="user",
        entity_id=u.id,
        detail=email_norm,
    )
    await session.commit()
    await session.refresh(u, ["roles"])
    return _user_out(u)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    admin: User = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    u = (
        await session.execute(select(User).options(selectinload(User.roles)).where(User.id == user_id))
    ).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    data = body.model_dump(exclude_unset=True)
    if not data:
        await session.refresh(u, ["roles"])
        return _user_out(u)

    if "email" in data:
        new_email = str(data["email"]).strip().lower()
        if new_email != (u.email or "").strip().lower():
            other = (
                await session.execute(
                    select(User).where(
                        func.lower(func.trim(User.email)) == new_email,
                        User.id != u.id,
                    )
                )
            ).scalar_one_or_none()
            if other:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado")
        u.email = new_email

    if "full_name" in data:
        u.full_name = str(data["full_name"]).strip()

    if "password" in data:
        u.hashed_password = hash_password(data["password"])

    if "is_active" in data:
        u.is_active = bool(data["is_active"])

    if "role_codes" in data:
        codes = list(data["role_codes"])
        if not codes:
            raise HTTPException(status_code=400, detail="Informe pelo menos um perfil")
        roles_result = await session.execute(select(Role).where(Role.code.in_(codes)))
        roles = list(roles_result.scalars().all())
        if len(roles) != len(set(codes)):
            raise HTTPException(status_code=400, detail="Perfil inválido")
        u.roles = roles

    if "github_login" in data:
        raw = data["github_login"]
        gh = (str(raw).strip() if raw is not None else "") or None
        if gh:
            other = (
                await session.execute(
                    select(User).where(
                        func.lower(User.github_login) == gh.lower(),
                        User.id != u.id,
                        User.github_login.isnot(None),
                    )
                )
            ).scalar_one_or_none()
            if other:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Login GitHub já associado a outro usuário")
        u.github_login = gh

    await log_action(
        session,
        actor_email=admin.email,
        action="user.update",
        entity_type="user",
        entity_id=u.id,
        detail=u.email,
    )
    await session.commit()
    await session.refresh(u, ["roles"])
    return _user_out(u)
