"""
Dragon System Service for Telegram Mini App.
Egg hatching, feeding, training, power progression, and dragon roster.
"""
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models


async def get_dragon_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Ajdarlar uyasi (Dragon Roost) bosh sahifasi ma'lumotlari.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        return None

    dragons = await crud.get_user_dragons(session, user.id)
    dragon_list = []

    for d in dragons:
        costs = crud.get_dragon_upgrade_cost(d) if hasattr(crud, "get_dragon_upgrade_cost") else {"gold": 1000, "iron": 500}
        feed_cost = 250 + ((d.level or 1) * 40)
        dragon_list.append({
            "id": d.id,
            "name": d.name,
            "level": d.level or 1,
            "power": d.power or 100,
            "hunger": getattr(d, "hunger", 100) or 100,
            "stage": getattr(d, "stage", "baby") or "baby",
            "is_egg": getattr(d, "is_egg", False),
            "feed_food_cost": feed_cost,
            "upgrade_costs": costs,
            "is_stationed": bool(getattr(d, "stationed_territory_id", None)),
        })

    return {
        "user_id": user.id,
        "user_food": user.food or 0,
        "user_gold": user.gold or 0,
        "dragons_count": len(dragon_list),
        "dragons": dragon_list,
        "has_dragon": len(dragon_list) > 0,
    }


async def claim_starter_dragon_egg_service(session: AsyncSession, identifier: int, name: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Boshlang'ich ajdar tuxumini olish"""
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", None

    clean_name = name.strip() or "Drogon"
    ok, msg, dragon = await crud.claim_dragon_egg(session, user.id, clean_name, grade="common")
    if not ok:
        return False, msg, None

    return True, msg, {
        "id": dragon.id,
        "name": dragon.name,
        "level": dragon.level,
        "power": dragon.power,
    }


async def hatch_dragon_service(session: AsyncSession, identifier: int, dragon_id: Optional[int] = None) -> Tuple[bool, str]:
    """Ajdaho tuxumini yorib chiqish (Hatch)"""
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi."
    return await crud.hatch_dragon(session, user.id, dragon_id)


async def feed_dragon_service(session: AsyncSession, identifier: int, dragon_id: Optional[int] = None) -> Tuple[bool, str]:
    """Ajdahoni oziqlantirish (Ozuqa sarflab quvvatini oshirish)"""
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi."
    return await crud.feed_dragon(session, user.id, dragon_id)


async def train_dragon_service(session: AsyncSession, identifier: int, dragon_id: Optional[int] = None) -> Tuple[bool, str]:
    """Ajdahoni mashq qildirish (Jangovar parvoz va Valiriya olovi)"""
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi."
    return await crud.train_dragon(session, user.id, dragon_id)
