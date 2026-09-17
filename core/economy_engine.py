from typing import Tuple, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import models
from config import (
    UPKEEP_FOOD_PER_INFANTRY,
    UPKEEP_FOOD_PER_ARCHER,
    UPKEEP_FOOD_PER_CAVALRY,
    UPKEEP_FOOD_PER_SPEARMAN,
    UPKEEP_FOOD_PER_SPECIAL,
)


def calculate_army_upkeep(army: models.Army) -> float:
    """Armiyaning soatlik oziq-ovqat iste'moli"""
    if not army:
        return 0.0
    return (
        (army.infantry * UPKEEP_FOOD_PER_INFANTRY)
        + (army.archers * UPKEEP_FOOD_PER_ARCHER)
        + (army.cavalry * UPKEEP_FOOD_PER_CAVALRY)
        + (army.spearmen * UPKEEP_FOOD_PER_SPEARMAN)
        + (army.special_troops * UPKEEP_FOOD_PER_SPECIAL)
    )


async def calculate_hourly_income(session: AsyncSession, user: models.User) -> Dict[str, int]:
    """O'yinchining hududlari, temir koni, don tegirmoni va bazaviy soatlik daromadlari"""
    mine_lvl = getattr(user, "iron_mine_level", 1) or 1
    mine_iron = mine_lvl * 50  # Har daraja uchun +50 temir/soat

    mill_lvl = getattr(user, "grain_mill_level", 1) or 1
    mill_food = mill_lvl * 75  # Har daraja uchun +75 oziq-ovqat/soat

    base_gold = 50
    base_food = 100 + mill_food
    base_iron = 20 + mine_iron

    if not user.house_id:
        return {"gold": base_gold, "food": base_food, "iron": base_iron}

    # Xonadonga qarashli hududlar daromadidan ulush (Qal'a darajasiga ko'ra +25% bonus bilan)
    res = await session.execute(
        select(models.Territory).where(models.Territory.owner_house_id == user.house_id)
    )
    territories = res.scalars().all()

    terr_gold = sum(int((t.gold_income or 0) * (1.0 + (max(1, getattr(t, 'castle_level', 1) or 1) - 1) * 0.25)) for t in territories) // 5
    terr_food = sum(int((t.food_income or 0) * (1.0 + (max(1, getattr(t, 'castle_level', 1) or 1) - 1) * 0.25)) for t in territories) // 5
    terr_iron = sum(int((t.iron_income or 0) * (1.0 + (max(1, getattr(t, 'castle_level', 1) or 1) - 1) * 0.25)) for t in territories) // 5

    return {
        "gold": base_gold + terr_gold,
        "food": base_food + terr_food,
        "iron": base_iron + terr_iron,
    }


async def process_hourly_tick(session: AsyncSession):
    """
    Barcha o'yinchilar uchun soatlik iqtisodiy tick:
    - Resurslar qo'shiladi
    - Oziq-ovqat iste'moli yechiladi
    - Agar Food = 0 bo'lsa, armiyada 5% askarlar ochlikdan qochib ketadi (Desertion)
    """
    users_res = await session.execute(select(models.User))
    users = users_res.scalars().all()

    for user in users:
        await session.refresh(user, ["army"])
        income = await calculate_hourly_income(session, user)
        upkeep = calculate_army_upkeep(user.army)

        user.gold += income["gold"]
        user.iron += income["iron"]

        net_food = income["food"] - int(upkeep)
        if user.food + net_food >= 0:
            user.food += net_food
        else:
            # Ocharchilik! Food = 0 va askarlar qochishi
            user.food = 0
            if user.army:
                user.army.infantry = int(user.army.infantry * 0.95)
                user.army.archers = int(user.army.archers * 0.95)
                user.army.cavalry = int(user.army.cavalry * 0.95)
                user.army.spearmen = int(user.army.spearmen * 0.95)
                user.army.special_troops = int(user.army.special_troops * 0.95)

    await session.commit()
