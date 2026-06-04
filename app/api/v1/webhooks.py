from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from stripe import SignatureVerificationError

from app.api.dependencies import get_subscription_service
from app.services.subscriptions import SubscriptionService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    service: Annotated[SubscriptionService, Depends(get_subscription_service)],
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> dict[str, bool]:
    if not stripe_signature:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing Stripe signature")
    payload = await request.body()
    try:
        event = await service.payment_provider.construct_webhook_event(payload, stripe_signature)
    except SignatureVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Stripe signature") from exc
    processed = await service.process_webhook(event)
    return {"processed": processed}
