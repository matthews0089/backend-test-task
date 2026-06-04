from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.db.session import get_db_session
from app.integrations.analytics.mock import MockAnalyticsService
from app.integrations.email.log_email import LogEmailService
from app.integrations.payment.stripe_provider import StripePaymentProvider
from app.models import User
from app.repositories.users import UserRepository
from app.services.auth import AuthService
from app.services.subscriptions import SubscriptionService


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(session, settings)


def get_subscription_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SubscriptionService:
    return SubscriptionService(
        session=session,
        payment_provider=StripePaymentProvider(settings),
        email_service=LogEmailService(),
        analytics_service=MockAnalyticsService(),
    )


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    token: Annotated[str | None, Cookie(alias="access_token")] = None,
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        user_id = decode_access_token(token, settings)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token") from exc
    user = await UserRepository(session).get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token")
    return user
