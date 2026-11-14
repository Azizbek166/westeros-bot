"""
Player and Read-Only endpoints for Telegram Mini App.
All data queries strictly resolved via verified Telegram initData.
"""
from typing import Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import models
from config import ADMIN_IDS
from api.auth import get_current_player, get_current_player_or_none, get_db_session
import services

router = APIRouter(prefix="/api/player", tags=["Player"])


class RegisterPlayerRequest(BaseModel):
    hero_name: str = Field(..., min_length=2, max_length=32, description="Qahramon nomi")
    house_code: Optional[str] = Field(None, description="Tanlangan xonadon kodi")
    custom_house_name: Optional[str] = Field(None, max_length=50, description="Maxsus yangi xonadon nomi")
    custom_house_region: Optional[str] = Field(None, max_length=50, description="Maxsus xonadon mintaqasi")
    custom_house_emoji: Optional[str] = Field(None, max_length=10, description="Maxsus xonadon emojisi")
    custom_castle_name: Optional[str] = Field(None, max_length=50, description="Maxsus qal'a nomi")


class UpdateStatusRequest(BaseModel):
    custom_status: Optional[str] = Field(None, max_length=100, description="Lord shiori yoki statusi")


@router.get("/profile")
async def get_player_profile_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Joriy o'yinchi profili, unvoni, darajasi va resurslari.
    """
    user, _ = auth
    # Oldingi mavsum TOP-3 g'olibi bo'lsa, bonusni avtomatik berish
    from database import crud
    pending_bonus = await crud.get_pending_season_bonus(session, user.telegram_id)
    if pending_bonus:
        await crud.apply_season_top_bonus(session, user, pending_bonus)

    profile_data = await services.get_player_profile(session, user.id)
    if not profile_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profil ma'lumotlari topilmadi.")

    return {
        "success": True,
        "authenticated_telegram_id": user.telegram_id,
        "player": profile_data
    }


@router.get("/army")
async def get_player_army_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    O'yinchining barcha qo'shinlari, qamal qurollari va jangovar statistikasi.
    """
    user, _ = auth
    army_data = await services.get_army_overview(session, user.id)
    return {
        "success": True,
        "authenticated_telegram_id": user.telegram_id,
        "army": army_data
    }


@router.get("/castles")
async def get_player_castles_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Qal'alar, mintaqalar, to'plangan o'lponlar va taymerlar.
    """
    user, _ = auth
    castles_data = await services.get_castles_overview(session, user.id)
    return {
        "success": True,
        "authenticated_telegram_id": user.telegram_id,
        "castles": castles_data
    }


@router.get("/rankings")
async def get_rankings_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Vesterosning eng kuchli lordlari va xonadonlari reytingi.
    """
    user, _ = auth
    rankings_data = await services.get_rankings_overview(session, user.id)
    return {
        "success": True,
        "authenticated_telegram_id": user.telegram_id,
        "rankings": rankings_data
    }


@router.get("/events")
async def get_world_events_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Dunyo ob-havosi, kunlik faol tadbirlar va vaqt.
    """
    user, _ = auth
    world_data = await services.get_world_events_overview(session, user.id)
    return {
        "success": True,
        "authenticated_telegram_id": user.telegram_id,
        "world": world_data
    }


@router.get("/dashboard")
async def get_full_dashboard_endpoint(
    auth: Tuple[Optional[models.User], Dict[str, Any]] = Depends(get_current_player_or_none),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Bir martalik tezkor so'rov: Mobil ilova ochilganda barcha ma'lumotlarni 1 ta so'rovda yuklash.
    Agar foydalanuvchi hali ro'yxatdan o'tmagan bo'lsa, is_registered=False va xonadonlar katalogini qaytaradi.
    """
    user, validated = auth
    user_info = validated["user"]
    tg_id = int(user_info["id"])

    # Yangi o'yinchi - onboarding rejimida ochish
    if not user or not user.house_id:
        catalog = await services.get_registration_houses_catalog(session)
        return {
            "success": True,
            "is_registered": False,
            "authenticated_telegram_id": tg_id,
            "telegram_user": user_info,
            "available_houses": catalog,
        }

    # Oldingi mavsum TOP-3 g'olibi bo'lsa, bonusni avtomatik berish
    from database import crud
    pending_bonus = await crud.get_pending_season_bonus(session, user.telegram_id)
    if pending_bonus:
        await crud.apply_season_top_bonus(session, user, pending_bonus)

    profile_data = await services.get_player_profile(session, user.id)
    army_data = await services.get_army_overview(session, user.id)
    castles_data = await services.get_castles_overview(session, user.id)
    rankings_data = await services.get_rankings_overview(session, user.id)
    world_data = await services.get_world_events_overview(session, user.id)
    daily_data = await services.get_daily_hub_data(session, user.id)

    return {
        "success": True,
        "is_registered": True,
        "authenticated_telegram_id": user.telegram_id,
        "is_admin": (user.telegram_id in ADMIN_IDS),
        "data": {
            "profile": profile_data,
            "army": army_data,
            "castles": castles_data,
            "rankings": rankings_data,
            "world": world_data,
            "daily": daily_data,
        }
    }


@router.post("/register")
async def register_player_endpoint(
    req: RegisterPlayerRequest,
    auth: Tuple[Optional[models.User], Dict[str, Any]] = Depends(get_current_player_or_none),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Mini App ichida to'g'ridan-to'g'ri yangi Lord sifatida ro'yxatdan o'tish va Qasamyod qilish.
    """
    _, validated = auth
    user_info = validated["user"]
    tg_id = int(user_info["id"])
    username = user_info.get("username")
    first_name = user_info.get("first_name", "Lord")
    last_name = user_info.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()

    ok, msg, created_user = await services.register_player_service(
        session=session,
        telegram_id=tg_id,
        username=username,
        full_name=full_name,
        hero_name=req.hero_name,
        house_code=req.house_code,
        custom_house_name=req.custom_house_name,
        custom_house_region=req.custom_house_region,
        custom_house_emoji=req.custom_house_emoji,
        custom_castle_name=req.custom_castle_name,
    )

    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    return {
        "success": True,
        "message": msg,
        "user_id": created_user.id if created_user else None,
        "authenticated_telegram_id": tg_id,
    }


@router.post("/update-status")
async def update_custom_status_endpoint(
    req: UpdateStatusRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Lord shaxsiy shiori yoki statusini yangilash.
    """
    user, _ = auth
    user.custom_status = (req.custom_status or "").strip()[:100]
    await session.commit()
    return {
        "success": True,
        "message": "Status muvaffaqiyatli yangilandi!",
        "custom_status": user.custom_status,
    }
