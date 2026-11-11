"""
Admin Service for Telegram Mini App.
Protected by require_admin_player dependency.
Game analytics, player management, and resource adjustments.
"""
from typing import Dict, Any, List, Tuple
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models


async def get_admin_dashboard_data(session: AsyncSession) -> Dict[str, Any]:
    """
    Admin boshqaruv konsoli statistikasi.
    """
    # 1. Jami o'yinchilar
    tot_users_res = await session.execute(select(func.count(models.User.id)))
    total_users = tot_users_res.scalar() or 0

    # 2. Jami qal'alar
    tot_terrs_res = await session.execute(select(func.count(models.Territory.id)))
    total_territories = tot_terrs_res.scalar() or 0

    # 3. Faol mavsum
    active_season = await crud.get_active_season(session)
    s_num = active_season.season_number if active_season else 2

    # 4. Oxirgi 10 ta o'yinchi
    recent_users_res = await session.execute(
        select(models.User).order_by(desc(models.User.id)).limit(10)
    )
    players = []
    for u in recent_users_res.scalars().all():
        players.append({
            "id": u.id,
            "telegram_id": u.telegram_id,
            "name": u.full_name or u.username or "Lord",
            "username": u.username,
            "level": u.level or 1,
            "gold": u.gold or 0,
            "prestige": u.prestige or 0,
            "is_banned": getattr(u, "is_banned", False),
            "vip_tier": u.vip_tier or "none",
        })

    return {
        "total_players": total_users,
        "total_territories": total_territories,
        "active_season_number": s_num,
        "recent_players": players,
    }


async def admin_set_ban_status_service(
    session: AsyncSession,
    target_user_id: int,
    is_banned: bool,
) -> Tuple[bool, str]:
    """O'yinchini bloklash yoki blokdan chiqarish"""
    target = await session.get(models.User, target_user_id)
    if not target:
        return False, "O'yinchi topilmadi."

    target.is_banned = is_banned
    await session.commit()
    status_str = "bloklandi" if is_banned else "blokdan chiqarildi"
    return True, f"Lord #{target_user_id} ({target.full_name}) muvaffaqiyatli {status_str}."


async def admin_adjust_resources_service(
    session: AsyncSession,
    target_user_id: int,
    gold: int = 0,
    food: int = 0,
    iron: int = 0,
) -> Tuple[bool, str]:
    """O'yinchiga resurs berish"""
    target = await session.get(models.User, target_user_id)
    if not target:
        return False, "O'yinchi topilmadi."

    target.gold = max(0, (target.gold or 0) + gold)
    target.food = max(0, (target.food or 0) + food)
    target.iron = max(0, (target.iron or 0) + iron)
    await session.commit()

    return True, f"Lord #{target.id} ga resurslar qo'shildi: +{gold:,}🪙, +{food:,}🌾, +{iron:,}⛓️"
