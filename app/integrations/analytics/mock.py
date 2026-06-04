from typing import Any

import structlog

from app.integrations.analytics.base import AnalyticsService
from app.models import User

logger = structlog.get_logger()


class MockAnalyticsService(AnalyticsService):
    async def track(
        self, user: User, event_name: str, properties: dict[str, Any] | None = None
    ) -> None:
        logger.info(
            "analytics.event",
            user_id=str(user.id),
            event_name=event_name,
            properties=properties or {},
        )
