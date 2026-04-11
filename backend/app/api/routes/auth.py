from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_session
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.schemas.auth import LoginRequest, MeResponse, Token
from app.services.token_crypt import encrypt_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _safe_oauth_next_path(raw: str | None) -> str | None:
    """Caminho interno permitido após OAuth (evita open redirect)."""
    if not raw:
        return None
    s = raw.strip()
    if len(s) > 768 or "\n" in s or "\r" in s:
        return None
    if not s.startswith("/") or s.startswith("//"):
        return None
    parsed = urlparse(s)
    if parsed.scheme or parsed.netloc:
        return None
    return s


def _github_oauth_state(next_path: str | None = None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload: dict = {"exp": exp, "typ": "gh_oauth"}
    n = _safe_oauth_next_path(next_path)
    if n:
        payload["next"] = n
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


@router.post("/login", response_model=Token)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    email_norm = body.email.strip().lower()
    result = await session.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(func.lower(User.email) == email_norm)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    token = create_access_token(user.id)
    return Token(access_token=token)


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)):
    has_github = any(getattr(i, "provider", None) == "github" for i in (user.identities or []))
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=[r.code for r in user.roles],
        has_github=has_github,
    )


@router.get("/github/status")
async def github_status():
    id_set = bool(settings.github_client_id)
    secret_set = bool(settings.github_client_secret)
    return {
        "oauth_configured": id_set and secret_set,
        "github_client_id_set": id_set,
        "github_client_secret_set": secret_set,
        # Deve ser copiado para «Authorization callback URL» no OAuth App do GitHub (carácter a carácter).
        "oauth_redirect_uri": settings.github_oauth_callback_url,
    }


@router.get("/github/authorize")
async def github_authorize(next: str | None = Query(None, description="Caminho interno pós-login, ex. /projetos/1?tab=github")):
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(status_code=503, detail="GitHub OAuth não configurado")
    state = _github_oauth_state(next)
    qs = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_oauth_callback_url,
            "scope": "read:user user:email repo",
            "state": state,
            "allow_signup": "false",
        }
    )
    url = f"https://github.com/login/oauth/authorize?{qs}"
    return RedirectResponse(url)


@router.get("/github/callback")
async def github_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    front = settings.frontend_oauth_redirect_base
    if not code or not state:
        return RedirectResponse(f"{front}?error=missing_code", status_code=302)
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("typ") != "gh_oauth":
            raise JWTError()
    except JWTError:
        return RedirectResponse(f"{front}?error=invalid_state", status_code=302)
    next_after = _safe_oauth_next_path(payload.get("next"))

    async with httpx.AsyncClient(timeout=30) as client:
        tr = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_callback_url,
            },
        )
        if tr.status_code != 200:
            return RedirectResponse(f"{front}?error=token_exchange", status_code=302)
        tok = tr.json()
        access = tok.get("access_token")
        if not access:
            return RedirectResponse(f"{front}?error=no_access_token", status_code=302)

        ur = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access}", "Accept": "application/vnd.github+json"},
        )
        if ur.status_code != 200:
            return RedirectResponse(f"{front}?error=github_user", status_code=302)
        gh_user = ur.json()
        login = gh_user.get("login") or ""
        gh_id = str(gh_user.get("id") or "")

        er = await client.get(
            "https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {access}", "Accept": "application/vnd.github+json"},
        )
        if er.status_code != 200:
            return RedirectResponse(f"{front}?error=github_email", status_code=302)
        emails = er.json()
        primary = next((e for e in emails if e.get("primary")), None)
        verified = next((e for e in emails if e.get("verified")), None)
        chosen = primary or verified or (emails[0] if emails else None)
        email = (chosen or {}).get("email")
        if not email:
            return RedirectResponse(f"{front}?error=no_email", status_code=302)

    result = await session.execute(
        select(User).options(selectinload(User.roles)).where(func.lower(User.email) == email.lower())
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return RedirectResponse(f"{front}?error=no_user", status_code=302)

    user.github_login = login
    existing = await session.execute(
        select(UserIdentity).where(UserIdentity.provider == "github", UserIdentity.provider_user_id == gh_id)
    )
    ident = existing.scalar_one_or_none()
    enc = encrypt_token(access)
    if ident:
        ident.user_id = user.id
        ident.access_token_encrypted = enc
    else:
        session.add(
            UserIdentity(
                user_id=user.id,
                provider="github",
                provider_user_id=gh_id,
                access_token_encrypted=enc,
            )
        )
    await session.commit()

    jwt_app = create_access_token(user.id)
    params: dict[str, str] = {"token": jwt_app}
    if next_after:
        params["next"] = next_after
    return RedirectResponse(f"{front}?{urlencode(params)}", status_code=302)
