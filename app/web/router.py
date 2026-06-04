from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_subscription_service
from app.core.config import get_settings
from app.db.session import get_db_session
from app.models import User
from app.services.auth import AuthService
from app.services.subscriptions import SubscriptionService
from app.web.dependencies import get_optional_web_user, safe_redirect_path
from app.web.templates import templates


settings = get_settings()
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, current_user: User | None = Depends(get_optional_web_user)):
    return templates.TemplateResponse(request, "home.html", {"user": current_user})


@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    next_url: str | None = Query(default=None, alias="next"),
    current_user: User | None = Depends(get_optional_web_user),
):
    if current_user:
        return RedirectResponse("/subscription", status_code=303)
    return templates.TemplateResponse(
        request,
        "register.html",
        {"user": None, "next_url": safe_redirect_path(next_url)},
    )


@router.post("/register")
async def register_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next_url: str = Form(default="/plans", alias="next"),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        await AuthService(session, settings).register(email, password)
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "register.html",
            {
                "user": None,
                "next_url": safe_redirect_path(next_url),
                "error": exc.detail,
                "email": email,
            },
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/login?next={safe_redirect_path(next_url)}", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next_url: str | None = Query(default=None, alias="next"),
    current_user: User | None = Depends(get_optional_web_user),
):
    if current_user:
        return RedirectResponse(safe_redirect_path(next_url, "/subscription"), status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"user": None, "next_url": safe_redirect_path(next_url, "/plans")},
    )


@router.post("/login")
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next_url: str = Form(default="/plans", alias="next"),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        user, token = await AuthService(session, settings).login(email, password)
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "user": None,
                "next_url": safe_redirect_path(next_url, "/plans"),
                "error": exc.detail,
                "email": email,
            },
            status_code=exc.status_code,
        )
    response = RedirectResponse(safe_redirect_path(next_url), status_code=303)
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
    )
    return response


@router.post("/logout")
async def logout_form():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(settings.auth_cookie_name)
    return response


@router.get("/plans", response_class=HTMLResponse)
async def plans_page(
    request: Request,
    current_user: User | None = Depends(get_optional_web_user),
    service: SubscriptionService = Depends(get_subscription_service),
):
    plans = await service.list_plans()
    return templates.TemplateResponse(request, "plans.html", {"plans": plans, "user": current_user})


@router.post("/checkout")
async def checkout_form(
    plan_id: str = Form(...),
    current_user: User | None = Depends(get_optional_web_user),
    service: SubscriptionService = Depends(get_subscription_service),
):
    if not current_user:
        return RedirectResponse("/login?next=/plans", status_code=303)
    checkout = await service.create_checkout_session(current_user, UUID(plan_id))
    return RedirectResponse(checkout.url, status_code=303)


@router.get("/subscription", response_class=HTMLResponse)
async def subscription_page(
    request: Request,
    current_user: User | None = Depends(get_optional_web_user),
    service: SubscriptionService = Depends(get_subscription_service),
):
    if not current_user:
        return RedirectResponse("/login?next=/subscription", status_code=303)
    plans = await service.list_plans()
    try:
        subscription = await service.get_current_subscription(current_user)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND:
            raise
        return templates.TemplateResponse(
            request,
            "subscription_empty.html",
            {
                "plans": plans,
                "user": current_user,
            },
        )
    messages = {
        "subscription_canceled": "Subscription was canceled.",
        "plan_changed": "Plan change started. Complete checkout to activate the new plan.",
    }
    return templates.TemplateResponse(
        request,
        "subscription.html",
        {
            "subscription": subscription,
            "plans": plans,
            "user": current_user,
            "message_key": request.query_params.get("message"),
            "message": messages.get(request.query_params.get("message")),
        },
    )


@router.get("/subscription/success", response_class=HTMLResponse)
async def subscription_success(
    request: Request,
    current_user: User | None = Depends(get_optional_web_user),
):
    return templates.TemplateResponse(request, "success.html", {"user": current_user})


@router.post("/subscription/change")
async def subscription_change_form(
    plan_id: str = Form(...),
    current_user: User = Depends(get_current_user),
    service: SubscriptionService = Depends(get_subscription_service),
):
    try:
        result = await service.change_plan(current_user, UUID(plan_id))
    except HTTPException:
        return RedirectResponse("/subscription", status_code=303)
    if result.payment_url:
        return RedirectResponse(result.payment_url, status_code=303)
    return RedirectResponse("/subscription?message=plan_changed", status_code=303)


@router.post("/subscription/cancel")
async def subscription_cancel_form(
    current_user: User = Depends(get_current_user),
    service: SubscriptionService = Depends(get_subscription_service),
):
    await service.cancel(current_user)
    return RedirectResponse("/subscription?message=subscription_canceled", status_code=303)
