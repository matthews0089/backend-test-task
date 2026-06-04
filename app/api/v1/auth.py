from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_auth_service, get_current_user
from app.core.config import Settings, get_settings
from app.models import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    user = await service.register(payload.email, payload.password)
    return AuthResponse(user=UserResponse(id=str(user.id), email=user.email))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
    user, token = await service.login(payload.email, payload.password)
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
    )
    return AuthResponse(user=UserResponse(id=str(user.id), email=user.email))


@router.post("/logout")
async def logout(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    response.delete_cookie(settings.auth_cookie_name)
    return {"message": "Logged out"}


@router.get("/me", response_model=AuthResponse)
async def me(current_user: Annotated[User, Depends(get_current_user)]) -> AuthResponse:
    return AuthResponse(user=UserResponse(id=str(current_user.id), email=current_user.email))
