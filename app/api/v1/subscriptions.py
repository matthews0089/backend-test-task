from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, get_subscription_service
from app.models import User
from app.schemas.subscriptions import (
    ChangeSubscriptionPlanRequest,
    CheckoutRequest,
    CheckoutResponse,
    MessageResponse,
    SubscriptionResponse,
)
from app.services.subscriptions import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    payload: CheckoutRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SubscriptionService, Depends(get_subscription_service)],
) -> CheckoutResponse:
    checkout = await service.create_checkout_session(current_user, payload.plan_id)
    return CheckoutResponse(checkout_url=checkout.url, session_id=checkout.id)


@router.get("/current", response_model=SubscriptionResponse)
async def current_subscription(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SubscriptionService, Depends(get_subscription_service)],
):
    return await service.get_current_subscription(current_user)


@router.post("/change-plan", response_model=SubscriptionResponse)
async def change_plan(
    payload: ChangeSubscriptionPlanRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SubscriptionService, Depends(get_subscription_service)],
):
    result = await service.change_plan(current_user, payload.plan_id)
    return result.subscription


@router.post("/cancel", response_model=MessageResponse)
async def cancel_subscription(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SubscriptionService, Depends(get_subscription_service)],
) -> MessageResponse:
    await service.cancel(current_user)
    return MessageResponse(message="Subscription cancellation scheduled")
