from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SubscriptionPlan


class SubscriptionPlanRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_active(self) -> list[SubscriptionPlan]:
        result = await self.session.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active.is_(True))
            .order_by(SubscriptionPlan.tier_rank, SubscriptionPlan.billing_period_rank)
        )
        return list(result.scalars())

    async def get_active(self, plan_id: UUID) -> SubscriptionPlan | None:
        result = await self.session.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.id == plan_id,
                SubscriptionPlan.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_price_id(self, stripe_price_id: str) -> SubscriptionPlan | None:
        result = await self.session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.stripe_price_id == stripe_price_id)
        )
        return result.scalar_one_or_none()
