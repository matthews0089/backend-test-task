from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.analytics.base import AnalyticsService
from app.integrations.email.base import EmailService
from app.integrations.payment.base import CheckoutSessionResult, PaymentProvider
from app.models import Subscription, User
from app.repositories.plans import SubscriptionPlanRepository
from app.repositories.subscriptions import SubscriptionRepository
from app.repositories.users import UserRepository
from app.repositories.webhook_events import WebhookEventRepository

logger = structlog.get_logger()


@dataclass(frozen=True)
class SubscriptionPlanChange:
    subscription: Subscription
    payment_url: str | None = None


class SubscriptionService:
    def __init__(
        self,
        session: AsyncSession,
        payment_provider: PaymentProvider,
        email_service: EmailService,
        analytics_service: AnalyticsService,
    ):
        self.session = session
        self.payment_provider = payment_provider
        self.email_service = email_service
        self.analytics_service = analytics_service
        self.plans = SubscriptionPlanRepository(session)
        self.subscriptions = SubscriptionRepository(session)
        self.users = UserRepository(session)
        self.webhook_events = WebhookEventRepository(session)

    async def list_plans(self):
        return await self.plans.list_active()

    async def create_checkout_session(
        self, user: User, plan_id: UUID
    ) -> CheckoutSessionResult:
        plan = await self.plans.get_active(plan_id)
        if not plan:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription plan not found")

        result = await self.payment_provider.create_checkout_session(user, plan)
        logger.info("payments.checkout_created", user_id=str(user.id), plan_id=str(plan.id))

        return result

    async def get_current_subscription(self, user: User) -> Subscription:
        subscription = await self.subscriptions.get_current_for_user(user.id)

        if not subscription:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No subscription found")

        if (
            subscription.status != "canceled"
            and (not subscription.current_period_start or not subscription.current_period_end)
        ):
            await self.sync_subscription_from_provider(subscription)

        return subscription

    async def change_plan(self, user: User, plan_id: UUID) -> SubscriptionPlanChange:
        subscription = await self.get_current_subscription(user)
        if subscription.status == "canceled":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Canceled subscriptions cannot be changed. Start a new subscription instead.",
            )

        plan = await self.plans.get_active(plan_id)
        if not plan:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription plan not found")

        if subscription.plan_id == plan.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Subscription already uses this plan")

        change_type = self.classify_plan_change(subscription.plan, plan)
        checkout = await self.payment_provider.create_plan_change_checkout_session(
            user, plan, subscription.stripe_subscription_id
        )
        logger.info(
            "subscriptions.plan_change_checkout_created",
            user_id=str(user.id),
            subscription_id=str(subscription.id),
            plan_id=str(plan.id),
            change_type=change_type,
        )
        return SubscriptionPlanChange(
            subscription=subscription,
            payment_url=checkout.url,
        )

    async def cancel(self, user: User) -> Subscription:
        subscription = await self.get_current_subscription(user)
        if subscription.status == "canceled":
            logger.info(
                "subscriptions.cancel_already_completed",
                user_id=str(user.id),
                subscription_id=str(subscription.id),
            )
            return subscription

        await self.payment_provider.cancel_subscription(subscription.stripe_subscription_id)
        subscription.status = "canceled"
        subscription.cancel_at_period_end = False
        subscription.current_period_end = datetime.now(UTC)
        await self.session.commit()
        await self.email_service.subscription_canceled(user, subscription)
        await self.analytics_service.track(
            user, "subscription_canceled", {"subscription_id": str(subscription.id)}
        )
        logger.info("subscriptions.cancel_requested", user_id=str(user.id))
        return subscription

    async def process_webhook(self, event: dict[str, Any]) -> bool:
        stored_event, is_new = await self.webhook_events.create_if_new(
            stripe_event_id=event["id"],
            event_type=event["type"],
            payload=event,
        )
        if not is_new:
            logger.info("webhooks.duplicate_ignored", stripe_event_id=event["id"])
            return False

        event_type = event["type"]
        data_object = event["data"]["object"]
        if event_type == "checkout.session.completed":
            await self.handle_checkout_completed(data_object)
        elif event_type == "invoice.payment_succeeded":
            await self.handle_payment_succeeded(data_object)
        elif event_type == "customer.subscription.updated":
            await self.handle_subscription_updated(data_object)
        elif event_type == "customer.subscription.deleted":
            await self.handle_subscription_deleted(data_object)

        await self.webhook_events.mark_processed(stored_event)
        await self.session.commit()
        logger.info("webhooks.processed", stripe_event_id=event["id"], event_type=event_type)
        return True

    async def handle_checkout_completed(self, checkout_session: dict[str, Any]) -> None:
        metadata = checkout_session.get("metadata") or {}
        if not metadata.get("user_id") or not metadata.get("plan_id"):
            logger.warning(
                "webhooks.checkout_missing_metadata",
                checkout_session_id=checkout_session.get("id"),
            )
            return

        user = await self.users.get_by_id(UUID(metadata["user_id"]))
        plan = await self.plans.get_active(UUID(metadata["plan_id"]))
        if not user or not plan:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Webhook references unknown user or plan")

        customer_id = checkout_session["customer"]
        subscription_id = checkout_session["subscription"]
        replace_subscription_id = metadata.get("replace_subscription_id")
        user.stripe_customer_id = customer_id
        existing = await self.subscriptions.get_by_stripe_subscription_id(subscription_id)
        if existing:
            return

        stripe_subscription = await self.payment_provider.retrieve_subscription(subscription_id)
        new_subscription = await self.subscriptions.create(
            Subscription(
                user_id=user.id,
                plan_id=plan.id,
                stripe_subscription_id=subscription_id,
                stripe_customer_id=customer_id,
                status=stripe_subscription.get("status", "incomplete"),
                current_period_start=self.subscription_period_start(stripe_subscription),
                current_period_end=self.subscription_period_end(stripe_subscription),
                cancel_at_period_end=bool(stripe_subscription.get("cancel_at_period_end")),
            )
        )
        await self.session.refresh(new_subscription, attribute_names=["plan"])
        if replace_subscription_id:
            await self.replace_existing_subscription(
                user=user,
                old_stripe_subscription_id=replace_subscription_id,
                new_subscription=new_subscription,
            )

    async def handle_payment_succeeded(self, invoice: dict[str, Any]) -> None:
        stripe_subscription_id = invoice.get("subscription")
        if not stripe_subscription_id:
            stripe_subscription_id = (
                (invoice.get("parent") or {})
                .get("subscription_details", {})
                .get("subscription")
            )
        if not stripe_subscription_id:
            return

        subscription = await self.subscriptions.get_by_stripe_subscription_id(stripe_subscription_id)
        if not subscription:
            return

        subscription.status = "active"
        if not subscription.current_period_start or not subscription.current_period_end:
            stripe_subscription = await self.payment_provider.retrieve_subscription(stripe_subscription_id)
            subscription.current_period_start = self.subscription_period_start(stripe_subscription)
            subscription.current_period_end = self.subscription_period_end(stripe_subscription)

        await self.email_service.payment_succeeded(subscription.user, subscription)
        await self.analytics_service.track(
            subscription.user,
            "subscription_payment_succeeded",
            {"subscription_id": str(subscription.id)},
        )

    async def handle_subscription_updated(self, stripe_subscription: dict[str, Any]) -> None:
        subscription = await self.subscriptions.get_by_stripe_subscription_id(stripe_subscription["id"])
        if not subscription:
            return

        await self.apply_stripe_subscription(subscription, stripe_subscription)

    async def handle_subscription_deleted(self, stripe_subscription: dict[str, Any]) -> None:
        subscription = await self.subscriptions.get_by_stripe_subscription_id(stripe_subscription["id"])
        if not subscription:
            return

        subscription.status = "canceled"
        subscription.cancel_at_period_end = False
        await self.email_service.subscription_canceled(subscription.user, subscription)
        await self.analytics_service.track(
            subscription.user,
            "subscription_canceled",
            {"subscription_id": str(subscription.id)},
        )

    def classify_plan_change(self, old_plan, new_plan) -> str:
        old_score = old_plan.tier_rank * 1000 + old_plan.billing_period_rank
        new_score = new_plan.tier_rank * 1000 + new_plan.billing_period_rank
        return "upgrade" if new_score > old_score else "downgrade"

    async def replace_existing_subscription(
        self,
        user: User,
        old_stripe_subscription_id: str,
        new_subscription: Subscription,
    ) -> None:
        old_subscription = await self.subscriptions.get_by_stripe_subscription_id(
            old_stripe_subscription_id
        )
        if not old_subscription or old_subscription.status == "canceled":
            return

        change_type = self.classify_plan_change(old_subscription.plan, new_subscription.plan)
        await self.payment_provider.cancel_subscription(old_subscription.stripe_subscription_id)
        old_subscription.status = "canceled"
        old_subscription.cancel_at_period_end = False

        event_name = (
            "subscription_upgraded" if change_type == "upgrade" else "subscription_downgraded"
        )
        if change_type == "upgrade":
            await self.email_service.subscription_upgraded(user, new_subscription)
        else:
            await self.email_service.subscription_downgraded(user, new_subscription)
        await self.analytics_service.track(
            user,
            event_name,
            {
                "old_subscription_id": str(old_subscription.id),
                "new_subscription_id": str(new_subscription.id),
            },
        )
        logger.info(
            "subscriptions.replaced_after_checkout",
            user_id=str(user.id),
            old_subscription_id=str(old_subscription.id),
            new_subscription_id=str(new_subscription.id),
            change_type=change_type,
        )

    async def sync_subscription_from_provider(self, subscription: Subscription) -> None:
        try:
            stripe_subscription = await self.payment_provider.retrieve_subscription(
                subscription.stripe_subscription_id
            )
        except Exception as exc:
            logger.warning(
                "subscriptions.sync_failed",
                subscription_id=str(subscription.id),
                stripe_subscription_id=subscription.stripe_subscription_id,
                error=str(exc),
            )
            return

        await self.apply_stripe_subscription(subscription, stripe_subscription)
        await self.session.commit()
        await self.session.refresh(subscription, attribute_names=["plan"])

    async def apply_stripe_subscription(
        self, subscription: Subscription, stripe_subscription: dict[str, Any]
    ) -> None:
        items = (stripe_subscription.get("items") or {}).get("data") or []
        if items:
            price_id = items[0]["price"]["id"]
            plan = await self.plans.get_by_price_id(price_id)
            if plan:
                subscription.plan_id = plan.id

        subscription.status = stripe_subscription["status"]
        subscription.cancel_at_period_end = bool(stripe_subscription.get("cancel_at_period_end"))
        subscription.current_period_start = self.subscription_period_start(stripe_subscription)
        subscription.current_period_end = self.subscription_period_end(stripe_subscription)

    def from_timestamp(self, value: int | None) -> datetime | None:
        if value is None:
            return None

        return datetime.fromtimestamp(value, tz=UTC)

    def subscription_period_start(self, stripe_subscription: dict[str, Any]) -> datetime | None:
        return self.from_timestamp(
            self.subscription_period_value(stripe_subscription, "current_period_start")
        )

    def subscription_period_end(self, stripe_subscription: dict[str, Any]) -> datetime | None:
        return self.from_timestamp(
            self.subscription_period_value(stripe_subscription, "current_period_end")
        )

    def subscription_period_value(self, stripe_subscription: dict[str, Any], key: str) -> int | None:
        value = stripe_subscription.get(key)
        if value is not None:
            return int(value)
        items = (stripe_subscription.get("items") or {}).get("data") or []
        if not items:
            return None

        item_value = items[0].get(key)
        return int(item_value) if item_value is not None else None
