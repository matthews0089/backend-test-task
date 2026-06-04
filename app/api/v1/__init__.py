from fastapi import APIRouter

from app.api.v1 import auth, plans, subscriptions, webhooks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(plans.router)
api_router.include_router(subscriptions.router)
api_router.include_router(webhooks.router)
