"""
Westeros Map & Territories Service for Telegram Mini App.
Provides interactive map of all 22 territories, castle details, scout info, and liberation.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models
from core.anti_cheat import can_attack_target


async def get_westeros_map_data(session: AsyncSession, identifier: int) -> Dict[str, Any]:
    """
    Vesteros xaritasi: Barcha 22 ta hudud va qal'alarning to'liq ma'lumoti.
    Mintaqalar bo'yicha guruhlangan: The North, Crownlands, Riverlands, etc.
    """
    user = await crud.get_user_any(session, identifier)
    user_house_id = user.house_id if user else None

    terrs_res = await session.execute(select(models.Territory).order_by(models.Territory.id))
    territories = terrs_res.scalars().all()

    houses_res = await session.execute(select(models.House))
    houses_dict = {h.id: h for h in houses_res.scalars().all()}

    mapped_territories = []
    by_region = {}

    for t in territories:
        h = houses_dict.get(t.owner_house_id) if t.owner_house_id else None
        h_name = h.name if h else "Neytral Qal'a"
        h_emoji = h.emoji if h else "⚔️"

        is_my_house = (user_house_id is not None and t.owner_house_id == user_house_id)
        is_me_conquered = (user is not None and getattr(t, "conquered_by_user_id", None) == user.id)

        item = {
            "id": t.id,
            "code": t.code,
            "name": t.name,
            "castle_name": t.castle_name or t.name,
            "region": t.region or "Vesteros",
            "castle_level": getattr(t, "castle_level", 1) or 1,
            "defense": getattr(t, "defense", 500) or 500,
            "owner_house_id": t.owner_house_id,
            "owner_house_name": h_name,
            "owner_house_emoji": h_emoji,
            "is_capital": getattr(t, "is_capital", False) or (t.code == "kings_landing"),
            "is_kings_landing": (t.code == "kings_landing"),
            "is_my_castle": is_my_house,
            "is_conquered_by_me": is_me_conquered,
            "hourly_income": {
                "gold": t.gold_income or 0,
                "food": t.food_income or 0,
                "iron": t.iron_income or 0,
            },
        }
        mapped_territories.append(item)
        by_region.setdefault(item["region"], []).append(item)

    return {
        "user_id": user.id if user else 0,
        "my_house_id": user_house_id,
        "total_territories": len(mapped_territories),
        "territories": mapped_territories,
        "regions": by_region,
    }


async def get_territory_scout_detail(
    session: AsyncSession,
    identifier: int,
    territory_id: int
) -> Optional[Dict[str, Any]]:
    """
    Jang oldidan qal'a mudofaasi, xonadoni va holatini ko'rish.
    """
    user = await crud.get_user_any(session, identifier)
    terr = await session.get(models.Territory, territory_id)
    if not terr:
        return None

    h = await session.get(models.House, terr.owner_house_id) if terr.owner_house_id else None
    is_shielded, shield_until, defender_name = await crud.get_territory_shield_status(session, terr)

    # Tinchlik qalqoni qolgan vaqti
    hours_shield = 0
    if is_shielded and shield_until:
        diff = shield_until - datetime.utcnow()
        hours_shield = max(1, int(diff.total_seconds() // 3600))

    can_attack, reason = can_attack_target(user, terr) if user else (False, "Avval kiring")

    return {
        "id": terr.id,
        "name": terr.name,
        "castle_name": terr.castle_name or terr.name,
        "region": terr.region,
        "defense": getattr(terr, "defense", 500) or 500,
        "castle_level": getattr(terr, "castle_level", 1) or 1,
        "owner_house": {
            "id": h.id if h else None,
            "name": h.name if h else "Neytral",
            "emoji": h.emoji if h else "⚔️",
        },
        "is_peace_shielded": is_shielded,
        "shield_hours_left": hours_shield,
        "can_attack": can_attack,
        "attack_restriction_reason": reason if not can_attack else None,
        "hourly_income": {
            "gold": terr.gold_income or 0,
            "food": terr.food_income or 0,
            "iron": terr.iron_income or 0,
        },
    }
