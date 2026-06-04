from dataclasses import dataclass
from typing import Any, Protocol

from app.models import SubscriptionPlan, User


@dataclass(frozen=True)
class CheckoutSessionResult:
    id: str
    url: str


@dataclass(frozen=True)
class PlanChangeResult:
    payment_url: str | None = None


class PaymentProvider(Protocol):
    async def create_checkout_session(self, user: User, plan: SubscriptionPlan) -> CheckoutSessionResult: ...
    async def cancel_subscription(self, stripe_subscription_id: str) -> None: ...
    async def create_plan_change_checkout_session(
        self, user: User, plan: SubscriptionPlan, current_stripe_subscription_id: str
    ) -> CheckoutSessionResult: ...
    async def update_subscription_plan(
        self, stripe_subscription_id: str, new_price_id: str
    ) -> PlanChangeResult: ...
    async def retrieve_subscription(self, stripe_subscription_id: str) -> dict[str, Any]: ...
    async def construct_webhook_event(self, payload: bytes, signature: str) -> dict[str, Any]: ...
