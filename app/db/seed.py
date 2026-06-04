import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models import SubscriptionPlan


def plan_seed_data() -> list[dict]:
    settings = get_settings()
    return [
        {
            "tier": "Starter",
            "billing_period": "Weekly",
            "name": "Starter Weekly",
            "stripe_price_id": settings.stripe_price_starter_weekly,
            "tier_rank": 10,
            "billing_period_rank": 10,
        },
        {
            "tier": "Starter",
            "billing_period": "Monthly",
            "name": "Starter Monthly",
            "stripe_price_id": settings.stripe_price_starter_monthly,
            "tier_rank": 10,
            "billing_period_rank": 20,
        },
        {
            "tier": "Pro",
            "billing_period": "Weekly",
            "name": "Pro Weekly",
            "stripe_price_id": settings.stripe_price_pro_weekly,
            "tier_rank": 20,
            "billing_period_rank": 10,
        },
        {
            "tier": "Pro",
            "billing_period": "Monthly",
            "name": "Pro Monthly",
            "stripe_price_id": settings.stripe_price_pro_monthly,
            "tier_rank": 20,
            "billing_period_rank": 20,
        },
    ]


async def seed_plans() -> None:
    async with AsyncSessionLocal() as session:
        for row in plan_seed_data():
            if not row["stripe_price_id"]:
                continue
            result = await session.execute(
                select(SubscriptionPlan).where(
                    SubscriptionPlan.tier == row["tier"],
                    SubscriptionPlan.billing_period == row["billing_period"],
                )
            )
            plan = result.scalar_one_or_none()
            if plan:
                for key, value in row.items():
                    setattr(plan, key, value)
            else:
                session.add(SubscriptionPlan(**row))
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_plans())
