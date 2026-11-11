"""
House & Dynasty Service for Telegram Mini App.
Independent service layer for House management, treasury, voting, and members.
"""
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models
from data.houses_data import HOUSES_DATA


async def get_house_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    O'yinchi xonadoni bosh sahifasi ma'lumotlari: G'azna, Lord, a'zolar va qal'alar.
    """
    user = await crud.get_user_any(session, identifier)
    if not user or not user.house_id:
        return None

    house = await session.get(models.House, user.house_id)
    if not house:
        return None

    h_data = HOUSES_DATA.get(house.code, {})

    # A'zolar ro'yxati
    members_res = await session.execute(
        select(models.User).where(models.User.house_id == house.id).order_by(models.User.prestige.desc())
    )
    members_list = []
    for m in members_res.scalars().all():
        members_list.append({
            "user_id": m.id,
            "name": m.full_name or m.username or "Lord",
            "username": m.username,
            "rank": m.rank or "member",
            "level": m.level or 1,
            "prestige": m.prestige or 0,
            "is_me": (m.id == user.id),
        })

    # Xonadonga qarashli qal'alar
    terrs = await crud.get_house_territories(session, house.id)
    castles_list = [
        {
            "id": t.id,
            "name": t.name,
            "castle_name": t.castle_name,
            "region": t.region,
            "level": getattr(t, "castle_level", 1) or 1,
            "defense": getattr(t, "defense", 500) or 500,
        }
        for t in terrs
    ]

    is_lord = (user.rank in ["king", "commander"]) or (house.lord_user_id == user.telegram_id)

    return {
        "house_id": house.id,
        "name": house.name,
        "emoji": house.emoji or "🛡️",
        "region": house.region,
        "description": h_data.get("description", house.description or ""),
        "special_troop_name": getattr(house, "special_troop_name", "Maxsus Qo'shin"),
        "lord_name": house.lord_user_id,
        "is_lord": is_lord,
        "my_rank": user.rank or "member",
        "treasury": {
            "gold": house.gold or 0,
            "food": house.food or 0,
            "iron": house.iron or 0,
        },
        "members_count": len(members_list),
        "members": members_list,
        "castles_count": len(castles_list),
        "castles": castles_list,
    }


async def deposit_to_house_treasury_service(
    session: AsyncSession,
    identifier: int,
    gold: int = 0,
    food: int = 0,
    iron: int = 0,
) -> Tuple[bool, str]:
    """Xonadon g'aznasiga shaxsiy resurslarni ehson qilish"""
    return await crud.donate_to_house_treasury(session, identifier, gold=gold, food=food, iron=iron)
