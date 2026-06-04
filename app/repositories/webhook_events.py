from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WebhookEvent


class WebhookEventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_if_new(
        self, stripe_event_id: str, event_type: str, payload: dict
    ) -> tuple[WebhookEvent, bool]:
        result = await self.session.execute(
            select(WebhookEvent).where(WebhookEvent.stripe_event_id == stripe_event_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing, False

        event = WebhookEvent(
            stripe_event_id=stripe_event_id,
            event_type=event_type,
            payload=payload,
        )
        self.session.add(event)
        await self.session.flush()
        return event, True

    async def mark_processed(self, event: WebhookEvent) -> WebhookEvent:
        event.processed_at = datetime.now(UTC)
        await self.session.flush()
        return event
