from fastapi import Cookie, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_db_session
from app.models import User
from app.repositories.users import UserRepository


settings = get_settings()


def safe_redirect_path(value: str | None, default: str = "/plans") -> str:
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return default


async def get_optional_web_user(
    session: AsyncSession = Depends(get_db_session),
    token: str | None = Cookie(default=None, alias=settings.auth_cookie_name),
) -> User | None:
    if not token:
        return None
    try:
        user_id = decode_access_token(token, settings)
    except ValueError:
        return None
    user = await UserRepository(session).get_by_id(user_id)
    if not user or not user.is_active:
        return None
    return user
