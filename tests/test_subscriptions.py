from sqlalchemy import select

from app.models import Subscription, SubscriptionPlan, User
from app.services.subscriptions import SubscriptionService
from tests.conftest import create_subscription


async def test_checkout_session_creation(authenticated_client):
    plans = (await authenticated_client.get("/api/v1/plans")).json()
    response = await authenticated_client.post(
        "/api/v1/subscriptions/checkout",
        json={"plan_id": plans[0]["id"]},
    )
    assert response.status_code == 200
    assert response.json()["checkout_url"] == "https://checkout.stripe.test/session"
    assert authenticated_client.fake_payment.checkout_calls


async def test_subscription_cancellation(authenticated_client, seeded_db):
    user = (await seeded_db.execute(select(User).where(User.email == "user@example.com"))).scalar_one()
    plan = (await seeded_db.execute(select(SubscriptionPlan))).scalars().first()
    subscription = await create_subscription(seeded_db, user, plan)

    response = await authenticated_client.post("/api/v1/subscriptions/cancel")
    assert response.status_code == 200
    await seeded_db.refresh(subscription)
    assert subscription.status == "canceled"
    assert subscription.cancel_at_period_end is False
    assert authenticated_client.fake_payment.canceled == ["sub_test_123"]
    assert ("subscription_canceled", user.id, subscription.id) in authenticated_client.fake_email.events


async def test_subscription_plan_change(authenticated_client, seeded_db):
    user = (await seeded_db.execute(select(User).where(User.email == "user@example.com"))).scalar_one()
    plans = (await seeded_db.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.tier_rank))).scalars().all()
    subscription = await create_subscription(seeded_db, user, plans[0])

    response = await authenticated_client.post(
        "/api/v1/subscriptions/change-plan",
        json={"plan_id": str(plans[-1].id)},
    )
    assert response.status_code == 200
    await seeded_db.refresh(subscription)
    assert subscription.plan_id == plans[0].id
    assert authenticated_client.fake_payment.plan_change_checkout_calls == [
        (user.id, plans[-1].id, "sub_test_123")
    ]
    assert authenticated_client.fake_payment.updated == []


async def test_subscription_plan_change_removes_scheduled_cancellation(authenticated_client, seeded_db):
    user = (await seeded_db.execute(select(User).where(User.email == "user@example.com"))).scalar_one()
    plans = (await seeded_db.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.tier_rank))).scalars().all()
    subscription = await create_subscription(seeded_db, user, plans[0])
    subscription.cancel_at_period_end = True
    await seeded_db.commit()

    response = await authenticated_client.post(
        "/api/v1/subscriptions/change-plan",
        json={"plan_id": str(plans[-1].id)},
    )
    assert response.status_code == 200
    await seeded_db.refresh(subscription)
    assert subscription.cancel_at_period_end is True


async def test_canceled_subscription_plan_change_is_rejected(authenticated_client, seeded_db):
    user = (await seeded_db.execute(select(User).where(User.email == "user@example.com"))).scalar_one()
    plans = (await seeded_db.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.tier_rank))).scalars().all()
    subscription = await create_subscription(seeded_db, user, plans[0])
    subscription.status = "canceled"
    await seeded_db.commit()

    response = await authenticated_client.post(
        "/api/v1/subscriptions/change-plan",
        json={"plan_id": str(plans[-1].id)},
    )
    assert response.status_code == 400
    assert authenticated_client.fake_payment.updated == []


async def test_duplicate_webhook_processing_is_idempotent(seeded_db):
    user = User(email="webhook@example.com", hashed_password="hash", stripe_customer_id="cus_test_123")
    plan = (await seeded_db.execute(select(SubscriptionPlan))).scalars().first()
    seeded_db.add(user)
    await seeded_db.commit()

    service = SubscriptionService(
        seeded_db,
        payment_provider=authenticated_payment_provider(),
        email_service=type("E", (), {})(),
        analytics_service=type("A", (), {})(),
    )
    event = {
        "id": "evt_test_123",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_test_123",
                "subscription": "sub_test_webhook",
                "metadata": {"user_id": str(user.id), "plan_id": str(plan.id)},
            }
        },
    }

    first = await service.process_webhook(event)
    second = await service.process_webhook(event)

    assert first is True
    assert second is False
    subscriptions = (
        await seeded_db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == "sub_test_webhook")
        )
    ).scalars().all()
    assert len(subscriptions) == 1


def authenticated_payment_provider():
    class PaymentProvider:
        async def retrieve_subscription(self, stripe_subscription_id: str):
            timestamp = 1_700_000_000
            return {
                "id": stripe_subscription_id,
                "status": "active",
                "cancel_at_period_end": False,
                "current_period_start": timestamp,
                "current_period_end": timestamp + 604800,
            }

    return PaymentProvider()
