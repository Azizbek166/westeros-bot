import json
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


def calculate_army_upkeep(army: models.Army, weather_type: str = "normal") -> float:
    """Armiyaning soatlik oziq-ovqat iste'moli (Ob-havo hisobi bilan)"""
    if not army:
        return 0.0
    base = (
        (army.infantry * UPKEEP_FOOD_PER_INFANTRY)
        + (army.archers * UPKEEP_FOOD_PER_ARCHER)
        + (army.cavalry * UPKEEP_FOOD_PER_CAVALRY)
        + (army.spearmen * UPKEEP_FOOD_PER_SPEARMAN)
        + (army.special_troops * UPKEEP_FOOD_PER_SPECIAL)
    )
    if weather_type == "severe_winter":
        base *= 1.25  # Qattiq qishda sovuq tufayli oziq-ovqat sarfi +25%
    return base


async def calculate_hourly_income(session: AsyncSession, user: models.User, weather_type: str = "normal") -> Dict[str, int]:
    """O'yinchining hududlari, temir koni, don tegirmoni va bazaviy soatlik daromadlari"""
    mine_lvl = getattr(user, "iron_mine_level", 1) or 1
    mine_iron = mine_lvl * 50  # Har daraja uchun +50 temir/soat

    mill_lvl = getattr(user, "grain_mill_level", 1) or 1
    mill_food = mill_lvl * 75  # Har daraja uchun +75 oziq-ovqat/soat

    base_gold = 50
    base_food = 100 + mill_food
    base_iron = 20 + mine_iron

    if not user.house_id:
        total_gold = base_gold
        total_food = base_food
        total_iron = base_iron
    else:
        # Xonadonga qarashli hududlar daromadidan ulush (Qal'a darajasiga ko'ra +25% bonus bilan)
        res = await session.execute(
            select(models.Territory).where(models.Territory.owner_house_id == user.house_id)
        )
        territories = res.scalars().all()

        terr_gold = sum(int((t.gold_income or 0) * (1.0 + (max(1, getattr(t, 'castle_level', 1) or 1) - 1) * 0.25)) for t in territories) // 5
        terr_food = sum(int((t.food_income or 0) * (1.0 + (max(1, getattr(t, 'castle_level', 1) or 1) - 1) * 0.25)) for t in territories) // 5
        terr_iron = sum(int((t.iron_income or 0) * (1.0 + (max(1, getattr(t, 'castle_level', 1) or 1) - 1) * 0.25)) for t in territories) // 5

        total_gold = base_gold + terr_gold
        total_food = base_food + terr_food
        total_iron = base_iron + terr_iron

    # Yozgi mo'l-ko'llik: Oltin va oziq-ovqat daromadiga bonus
    if weather_type == "summer_abundance":
        total_gold = int(total_gold * 1.25)
        total_food = int(total_food * 1.50)

    return {
        "gold": total_gold,
        "food": total_food,
        "iron": total_iron,
    }


async def process_hourly_tick(session: AsyncSession):
    """
    Barcha o'yinchilar uchun soatlik iqtisodiy tick:
    - Resurslar qo'shiladi (ob-havo inobatga olingan)
    - Oziq-ovqat iste'moli yechiladi
    - Agar Food = 0 bo'lsa, armiyada 5% askarlar ochlikdan qochib ketadi (Desertion)
    """
    # Ob-havoni aniqlash
    weather_type = "normal"
    try:
        w_res = await session.execute(
            select(models.EventState).where(models.EventState.event_name == "world_weather")
        )
        w_ev = w_res.scalar_one_or_none()
        if w_ev and w_ev.data_json:
            w_data = json.loads(w_ev.data_json)
            weather_type = w_data.get("weather_type", "normal")
    except Exception:
        pass

    users_res = await session.execute(select(models.User))
    users = users_res.scalars().all()

    for user in users:
        await session.refresh(user, ["army"])
        income = await calculate_hourly_income(session, user, weather_type=weather_type)
        upkeep = calculate_army_upkeep(user.army, weather_type=weather_type)

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

