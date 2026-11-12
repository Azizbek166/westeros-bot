"""
Errors & Bug Reporting Router for Telegram Mini App.
Accepts frontend error reports (window.onerror, unhandledrejection, API failures),
validates initData, rate limits, and routes to core.error_reporter.
"""
from typing import Dict, Any, Optional, Tuple, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_player_or_none, require_admin_player, get_db_session
from api.rate_limiter import SlidingWindowRateLimiter
from core.error_reporter import report_system_error, get_recent_errors, resolve_system_error
from database import models

router = APIRouter(prefix="/api/errors", tags=["Errors"])

# Limit: max 10 error reports per minute per player
error_report_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)


class FrontendErrorReportRequest(BaseModel):
    error_type: str = Field(..., max_length=100, description="Xato turi (masalan TypeError, NetworkError)")
    error_message: str = Field(..., max_length=1500, description="Xato xabari matni")
    stack_trace: Optional[str] = Field(None, max_length=4000, description="JavaScript call stack")
    location: Optional[str] = Field(None, max_length=255, description="Sahifa yoki modal nomi")
    browser_info: Optional[str] = Field(None, max_length=255, description="Brauzer / qurilma ma'lumotlari")
    component: Optional[str] = Field(None, max_length=100, description="Xato yuz bergan komponent")


class ResolveErrorRequest(BaseModel):
    error_id: int = Field(..., description="Hal qilingan SystemErrorLog ID si")


@router.post("/report")
async def report_frontend_error_endpoint(
    req: FrontendErrorReportRequest,
    auth: Tuple[Optional[models.User], Dict[str, Any]] = Depends(get_current_player_or_none),
) -> Dict[str, Any]:
    """
    Mini App frontendidagi xatolarni (window.onerror, unhandledrejection, API)
    server orqali ERROR_CHAT_ID Telegram guruhiga yuborish.
    initData HMAC validatsiyasi va rate limiting bilan to'liq himoyalangan.
    """
    user, validated = auth
    user_info = validated.get("user", {})
    user_id = int(user_info.get("id")) if "id" in user_info else (user.telegram_id if user else None)

    # Rate limiting per player ID
    rate_key = f"error_rep_{user_id or 'anon'}"
    error_report_limiter.check(rate_key)

    extra = {}
    if req.browser_info:
        extra["Qurilma"] = req.browser_info[:150]
    if req.component:
        extra["Komponent"] = req.component[:100]

    ok = await report_system_error(
        source="miniapp",
        error_type=req.error_type,
        error_message=req.error_message,
        handler_name=req.location or "frontend",
        user_telegram_id=user_id,
        stack_trace=req.stack_trace,
        extra_details=extra if extra else None,
    )

    return {
        "success": True,
        "reported": ok,
        "detail": "Xato xabari qabul qilindi va tizim jurnaliga qayd etildi."
    }


@router.get("/admin/list")
async def get_admin_errors_list_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(require_admin_player),
    limit: int = 25,
    only_unresolved: bool = False,
) -> Dict[str, Any]:
    """
    Admin paneli uchun so'nggi xatolar ro'yxati (Faqat ADMIN_IDS uchun).
    """
    errors = await get_recent_errors(limit=limit, only_unresolved=only_unresolved)
    return {
        "success": True,
        "total_returned": len(errors),
        "errors": errors,
    }


@router.post("/admin/resolve")
async def resolve_error_endpoint(
    req: ResolveErrorRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(require_admin_player),
) -> Dict[str, Any]:
    """
    Xatoni 'Hal qilindi' deb belgilash (Faqat ADMIN_IDS uchun).
    """
    admin_user, _ = auth
    ok, msg = await resolve_system_error(
        error_id=req.error_id,
        admin_telegram_id=admin_user.telegram_id,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)

    return {
        "success": True,
        "detail": msg,
        "error_id": req.error_id,
    }
