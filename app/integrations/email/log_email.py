import structlog

from app.integrations.email.base import EmailService
from app.models import Subscription, User

logger = structlog.get_logger()


class LogEmailService(EmailService):
    async def payment_succeeded(self, user: User, subscription: Subscription) -> None:
        logger.info("email.payment_succeeded", user_id=str(user.id), subscription_id=str(subscription.id))

    async def subscription_upgraded(self, user: User, subscription: Subscription) -> None:
        logger.info("email.subscription_upgraded", user_id=str(user.id), subscription_id=str(subscription.id))

    async def subscription_downgraded(self, user: User, subscription: Subscription) -> None:
        logger.info("email.subscription_downgraded", user_id=str(user.id), subscription_id=str(subscription.id))

    async def subscription_canceled(self, user: User, subscription: Subscription) -> None:
        logger.info("email.subscription_canceled", user_id=str(user.id), subscription_id=str(subscription.id))
