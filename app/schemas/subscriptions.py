from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PlanResponse(BaseModel):
    id: UUID
    tier: str
    billing_period: str
    name: str
    is_active: bool

    model_config = {"from_attributes": True}


class CheckoutRequest(BaseModel):
    plan_id: UUID


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class SubscriptionResponse(BaseModel):
    id: UUID
    plan: PlanResponse
    status: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool

    model_config = {"from_attributes": True}


class ChangeSubscriptionPlanRequest(BaseModel):
    plan_id: UUID


class MessageResponse(BaseModel):
    message: str
