from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    RegisterRequest,
    RenewRequest,
    TokenResponse,
)
from app.config import settings
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    access_token, refresh_token = await service.register(db, data)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    access_token, refresh_token = await service.login(db, data)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.get("/google")
async def google_login():
    """Redirige al usuario a la pantalla de autenticación de Google."""
    url = service.get_google_auth_url()
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(code: str, db: AsyncSession = Depends(get_db)):
    """Google redirige aquí con el código de autorización."""
    access_token, refresh_token = await service.google_callback(db, code)
    # Redirige al frontend con los tokens en el fragmento de la URL
    redirect_url = (
        f"{settings.FRONTEND_URL}/auth/callback"
        f"?access_token={access_token}&refresh_token={refresh_token}"
    )
    return RedirectResponse(redirect_url)


@router.post("/renew", response_model=AccessTokenResponse)
async def renew_token(data: RenewRequest, db: AsyncSession = Depends(get_db)):
    """
    Renueva el access token.
    - Requiere access token expirado + refresh token válido.
    - El mismo access token solo puede usarse para renovar UNA vez.
    - Si el refresh token expiró o ya se inició sesión en otro dispositivo → 401.
    """
    new_access_token = await service.renew(db, data)
    return AccessTokenResponse(access_token=new_access_token)


@router.post("/logout", status_code=204)
async def logout(data: LogoutRequest, db: AsyncSession = Depends(get_db)):
    await service.logout(db, data.refresh_token)
