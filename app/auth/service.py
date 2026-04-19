import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import httpx
from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode

from app.auth.schemas import LoginRequest, RegisterRequest, RenewRequest
from app.auth.utils import create_access_token, create_refresh_token, decode_token, hash_token
from app.config import settings
from app.models.refresh_token import RefreshToken
from app.models.user import User

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autorizado")
_SESSION_EXPIRED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión expirada, inicia sesión nuevamente")


# ──────────────────────────── helpers ────────────────────────────

async def _revoke_all_user_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked == False)  # noqa: E712
        .values(revoked=True)
    )


async def _store_refresh_token(db: AsyncSession, user_id: uuid.UUID, token: str) -> RefreshToken:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.REFRESH_TOKEN_EXPIRE_HOURS)
    rt = RefreshToken(
        id=uuid.uuid4(),
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=expires_at,
    )
    db.add(rt)
    return rt


def _issue_token_pair(user_id: uuid.UUID) -> tuple[str, str]:
    """Retorna (access_token, refresh_token)."""
    access_token, _ = create_access_token(user_id)
    refresh_token, _ = create_refresh_token(user_id)
    return access_token, refresh_token


# ──────────────────────────── register ────────────────────────────

async def register(db: AsyncSession, data: RegisterRequest) -> tuple[str, str]:
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El email ya está registrado")

    user = User(
        id=uuid.uuid4(),
        nombre=data.nombre,
        email=data.email,
        password_hash=_hash_password(data.password),
    )
    db.add(user)
    await db.flush()

    access_token, refresh_token = _issue_token_pair(user.id)
    await _store_refresh_token(db, user.id, refresh_token)
    return access_token, refresh_token


# ──────────────────────────── login ────────────────────────────

async def login(db: AsyncSession, data: LoginRequest) -> tuple[str, str]:
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not _verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    # Invalidar todas las sesiones previas (un solo dispositivo activo)
    await _revoke_all_user_tokens(db, user.id)

    access_token, refresh_token = _issue_token_pair(user.id)
    await _store_refresh_token(db, user.id, refresh_token)
    return access_token, refresh_token


# ──────────────────────────── google oauth ────────────────────────────

def get_google_auth_url() -> str:
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    return f"{settings.GOOGLE_AUTH_URI}?{urlencode(params)}"


async def google_callback(db: AsyncSession, code: str) -> tuple[str, str]:
    # Intercambiar code por tokens de Google
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(settings.GOOGLE_TOKEN_URI, data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        if token_resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Error al autenticar con Google")
        google_tokens = token_resp.json()

        # Obtener info del usuario de Google
        userinfo_resp = await client.get(
            settings.GOOGLE_USERINFO_URI,
            headers={"Authorization": f"Bearer {google_tokens['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se pudo obtener la información de Google")
        google_user = userinfo_resp.json()

    google_id: str = google_user["sub"]
    email: str = google_user["email"]
    nombre: str = google_user.get("name", email.split("@")[0])

    # Buscar usuario por google_id o email
    result = await db.execute(
        select(User).where((User.google_id == google_id) | (User.email == email))
    )
    user = result.scalar_one_or_none()

    if user:
        if not user.google_id:
            user.google_id = google_id
    else:
        user = User(id=uuid.uuid4(), nombre=nombre, email=email, google_id=google_id)
        db.add(user)
        await db.flush()

    await _revoke_all_user_tokens(db, user.id)
    access_token, refresh_token = _issue_token_pair(user.id)
    await _store_refresh_token(db, user.id, refresh_token)
    return access_token, refresh_token


# ──────────────────────────── renew ────────────────────────────

async def renew(db: AsyncSession, data: RenewRequest) -> str:
    # Decodificar access token SIN verificar expiración (ya sabemos que expiró)
    try:
        access_payload = decode_token(data.access_token, verify_exp=False)
    except JWTError:
        raise _UNAUTHORIZED

    if access_payload.get("type") != "access":
        raise _UNAUTHORIZED

    # Decodificar refresh token CON verificación de expiración
    try:
        refresh_payload = decode_token(data.refresh_token, verify_exp=True)
    except JWTError:
        raise _SESSION_EXPIRED

    if refresh_payload.get("type") != "refresh":
        raise _UNAUTHORIZED

    # Ambos tokens deben pertenecer al mismo usuario
    if access_payload.get("sub") != refresh_payload.get("sub"):
        raise _UNAUTHORIZED

    access_jti: str = access_payload.get("jti", "")

    # Buscar refresh token en BD por hash
    rt_hash = hash_token(data.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == rt_hash))
    rt = result.scalar_one_or_none()

    if not rt or rt.revoked:
        raise _SESSION_EXPIRED

    # Si ya se usó este access token para renovar → sesión inválida
    if rt.used_access_jti == access_jti:
        raise _SESSION_EXPIRED

    # Emitir nuevo access token y marcar el jti usado
    user_id = uuid.UUID(access_payload["sub"])
    new_access_token, _ = create_access_token(user_id)
    rt.used_access_jti = access_jti
    await db.flush()

    return new_access_token


# ──────────────────────────── logout ────────────────────────────

async def logout(db: AsyncSession, refresh_token: str) -> None:
    rt_hash = hash_token(refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == rt_hash))
    rt = result.scalar_one_or_none()
    if rt:
        rt.revoked = True
        await db.flush()
