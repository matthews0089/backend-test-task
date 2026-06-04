import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.repositories.users import UserRepository

logger = structlog.get_logger()


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)

    async def register(self, email: str, password: str) -> User:
        existing = await self.users.get_by_email(email)
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
        user = await self.users.create(email, hash_password(password))
        await self.session.commit()
        logger.info("auth.registered", user_id=str(user.id), email=user.email)
        return user

    async def login(self, email: str, password: str) -> tuple[User, str]:
        user = await self.users.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is disabled")
        token = create_access_token(user.id, self.settings)
        logger.info("auth.login", user_id=str(user.id), email=user.email)
        return user, token
