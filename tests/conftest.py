from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies import get_subscription_service
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.integrations.payment.base import CheckoutSessionResult, PlanChangeResult
from app.main import app
from app.models import Subscription, SubscriptionPlan, User
from app.services.subscriptions import SubscriptionService


class FakePaymentProvider:
    def __init__(self):
        self.checkout_calls = []
        self.plan_change_checkout_calls = []
        self.canceled = []
        self.updated = []

    async def create_checkout_session(self, user: User, plan: SubscriptionPlan):
        self.checkout_calls.append((user.id, plan.id))
        return CheckoutSessionResult(id="cs_test_123", url="https://checkout.stripe.test/session")

    async def cancel_subscription(self, stripe_subscription_id: str) -> None:
        self.canceled.append(stripe_subscription_id)

    async def create_plan_change_checkout_session(
        self, user: User, plan: SubscriptionPlan, current_stripe_subscription_id: str
    ):
        self.plan_change_checkout_calls.append(
            (user.id, plan.id, current_stripe_subscription_id)
        )
        return CheckoutSessionResult(
            id="cs_change_123",
            url="https://checkout.stripe.test/change-plan",
        )

    async def update_subscription_plan(self, stripe_subscription_id: str, new_price_id: str) -> None:
        self.updated.append((stripe_subscription_id, new_price_id))
        return PlanChangeResult(payment_url="https://invoice.stripe.test/pay")

    async def retrieve_subscription(self, stripe_subscription_id: str):
        timestamp = int(datetime.now(UTC).timestamp())
        return {
            "id": stripe_subscription_id,
            "status": "active",
            "cancel_at_period_end": False,
            "current_period_start": timestamp,
            "current_period_end": timestamp + 604800,
        }

    async def construct_webhook_event(self, payload: bytes, signature: str):
        raise NotImplementedError


class FakeEmailService:
    def __init__(self):
        self.events = []

    async def payment_succeeded(self, user: User, subscription: Subscription) -> None:
        self.events.append(("payment_succeeded", user.id, subscription.id))

    async def subscription_upgraded(self, user: User, subscription: Subscription) -> None:
        self.events.append(("subscription_upgraded", user.id, subscription.id))

    async def subscription_downgraded(self, user: User, subscription: Subscription) -> None:
        self.events.append(("subscription_downgraded", user.id, subscription.id))

    async def subscription_canceled(self, user: User, subscription: Subscription) -> None:
        self.events.append(("subscription_canceled", user.id, subscription.id))


class FakeAnalyticsService:
    def __init__(self):
        self.events = []

    async def track(self, user: User, event_name: str, properties: dict | None = None) -> None:
        self.events.append((user.id, event_name, properties or {}))


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def seeded_db(db_session: AsyncSession) -> AsyncSession:
    db_session.add_all(
        [
            SubscriptionPlan(
                id=uuid4(),
                tier="Starter",
                billing_period="Weekly",
                name="Starter Weekly",
                stripe_price_id="price_starter_weekly",
                tier_rank=10,
                billing_period_rank=10,
            ),
            SubscriptionPlan(
                id=uuid4(),
                tier="Starter",
                billing_period="Monthly",
                name="Starter Monthly",
                stripe_price_id="price_starter_monthly",
                tier_rank=10,
                billing_period_rank=20,
            ),
            SubscriptionPlan(
                id=uuid4(),
                tier="Pro",
                billing_period="Monthly",
                name="Pro Monthly",
                stripe_price_id="price_pro_monthly",
                tier_rank=20,
                billing_period_rank=20,
            ),
        ]
    )
    await db_session.commit()
    return db_session


@pytest.fixture
async def client(seeded_db: AsyncSession):
    payment = FakePaymentProvider()
    email = FakeEmailService()
    analytics = FakeAnalyticsService()

    async def override_db():
        yield seeded_db

    def override_subscription_service():
        return SubscriptionService(seeded_db, payment, email, analytics)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_subscription_service] = override_subscription_service
    settings = get_settings()
    settings.jwt_secret_key = "test-secret"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        test_client.fake_payment = payment
        test_client.fake_email = email
        test_client.fake_analytics = analytics
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_client(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "password123"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    return client


async def create_subscription(session: AsyncSession, user: User, plan: SubscriptionPlan) -> Subscription:
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_test_123",
        stripe_customer_id="cus_test_123",
        status="active",
        current_period_start=datetime.now(UTC),
        current_period_end=datetime.now(UTC),
    )
    session.add(subscription)
    await session.commit()
    await session.refresh(subscription, attribute_names=["plan"])
    return subscription
