"""
Player and Read-Only endpoints for Telegram Mini App.
All data queries strictly resolved via verified Telegram initData.
"""
from typing import Dict, Any, Tuple
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import models
from api.auth import get_current_player, get_db_session
import services

router = APIRouter(prefix="/api/player", tags=["Player"])


@router.get("/profile")
async def get_player_profile_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Joriy o'yinchi profili, unvoni, darajasi va resurslari.
    """
    user, _ = auth
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
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Bir martalik tezkor so'rov: Mobil ilova ochilganda barcha read-only ekranlarni
    1 ta roundtrip orqali yuklash (Zaif aloqa va sekin tarmoqlar uchun maksimal tezlik).
    """
    user, _ = auth
    profile_data = await services.get_player_profile(session, user.id)
    army_data = await services.get_army_overview(session, user.id)
    castles_data = await services.get_castles_overview(session, user.id)
    rankings_data = await services.get_rankings_overview(session, user.id)
    world_data = await services.get_world_events_overview(session, user.id)
    daily_data = await services.get_daily_hub_data(session, user.id)

    return {
        "success": True,
        "authenticated_telegram_id": user.telegram_id,
        "data": {
            "profile": profile_data,
            "army": army_data,
            "castles": castles_data,
            "rankings": rankings_data,
            "world": world_data,
            "daily": daily_data,
        }
    }
