import json
from typing import Any

import stripe
from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
from app.integrations.payment.base import CheckoutSessionResult, PaymentProvider, PlanChangeResult
from app.models import SubscriptionPlan, User


class StripePaymentProvider(PaymentProvider):
    def __init__(self, settings: Settings):
        self.settings = settings
        stripe.api_key = settings.stripe_secret_key

    async def create_checkout_session(
        self, user: User, plan: SubscriptionPlan
    ) -> CheckoutSessionResult:
        session = await run_in_threadpool(
            stripe.checkout.Session.create,
            mode="subscription",
            customer=user.stripe_customer_id,
            customer_email=None if user.stripe_customer_id else user.email,
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            success_url=str(self.settings.stripe_success_url),
            cancel_url=str(self.settings.stripe_cancel_url),
            metadata={"user_id": str(user.id), "plan_id": str(plan.id)},
            subscription_data={"metadata": {"user_id": str(user.id), "plan_id": str(plan.id)}},
        )
        return CheckoutSessionResult(id=session["id"], url=session["url"])

    async def cancel_subscription(self, stripe_subscription_id: str) -> None:
        await run_in_threadpool(
            stripe.Subscription.delete,
            stripe_subscription_id,
        )

    async def create_plan_change_checkout_session(
        self, user: User, plan: SubscriptionPlan, current_stripe_subscription_id: str
    ) -> CheckoutSessionResult:
        metadata = {
            "user_id": str(user.id),
            "plan_id": str(plan.id),
            "replace_subscription_id": current_stripe_subscription_id,
        }
        session = await run_in_threadpool(
            stripe.checkout.Session.create,
            mode="subscription",
            customer=user.stripe_customer_id,
            customer_email=None if user.stripe_customer_id else user.email,
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            success_url=str(self.settings.stripe_success_url),
            cancel_url=str(self.settings.stripe_cancel_url),
            metadata=metadata,
            subscription_data={"metadata": metadata},
        )
        return CheckoutSessionResult(id=session["id"], url=session["url"])

    async def update_subscription_plan(
        self, stripe_subscription_id: str, new_price_id: str
    ) -> PlanChangeResult:
        subscription = await run_in_threadpool(stripe.Subscription.retrieve, stripe_subscription_id)
        item_id = subscription["items"]["data"][0]["id"]
        updated_subscription = await run_in_threadpool(
            stripe.Subscription.modify,
            stripe_subscription_id,
            items=[{"id": item_id, "price": new_price_id}],
            proration_behavior="always_invoice",
            payment_behavior="error_if_incomplete",
            cancel_at_period_end=False,
            expand=["latest_invoice"],
        )
        updated_subscription_data = json.loads(
            json.dumps(updated_subscription.to_dict(), default=str)
        )
        invoice = updated_subscription_data.get("latest_invoice")
        payment_url = invoice.get("hosted_invoice_url") if isinstance(invoice, dict) else None
        return PlanChangeResult(payment_url=payment_url)

    async def retrieve_subscription(self, stripe_subscription_id: str) -> dict[str, Any]:
        subscription = await run_in_threadpool(stripe.Subscription.retrieve, stripe_subscription_id)
        return json.loads(json.dumps(subscription.to_dict(), default=str))

    async def construct_webhook_event(self, payload: bytes, signature: str) -> dict[str, Any]:
        event = await run_in_threadpool(
            stripe.Webhook.construct_event,
            payload,
            signature,
            self.settings.stripe_webhook_secret,
        )
        return json.loads(json.dumps(event.to_dict(), default=str))
