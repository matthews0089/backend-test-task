from typing import Any, Protocol

from app.models import User


class AnalyticsService(Protocol):
    async def track(self, user: User, event_name: str, properties: dict[str, Any] | None = None) -> None: ...
