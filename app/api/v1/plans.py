from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, get_subscription_service
from app.models import User
from app.schemas.subscriptions import PlanResponse
from app.services.subscriptions import SubscriptionService

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("", response_model=list[PlanResponse])
async def list_plans(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[SubscriptionService, Depends(get_subscription_service)],
) -> list[PlanResponse]:
    return await service.list_plans()
