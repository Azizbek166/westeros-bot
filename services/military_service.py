from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models
from core.economy_engine import calculate_army_upkeep
from core.anti_cheat import validate_recruitment
from data.units_data import UNITS_DATA


async def get_army_overview(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    O'yinchi armiyasi, qamal qurollari, oziq-ovqat xarajati va resurslari ma'lumotlari.
    """
    user = await crud.get_user_with_relations(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return None

    army = user.army
    upkeep = calculate_army_upkeep(army) if army else 0
    special_name = user.house.special_troop_name if user.house else "Maxsus Qo'shin"

    inf = army.infantry if army else 0
    arc = army.archers if army else 0
    cav = army.cavalry if army else 0
    spm = army.spearmen if army else 0
    spc = army.special_troops if army else 0
    cats = getattr(army, "catapults", 0) or 0
    twrs = getattr(army, "siege_towers", 0) or 0
    wfire = getattr(army, "wildfire", 0) or 0

    return {
        "user_id": user.id,
        "gold": user.gold or 0,
        "food": user.food or 0,
        "iron": user.iron or 0,
        "upkeep_food_hourly": int(upkeep),
        "special_troop_name": special_name,
        "troops": {
            "infantry": inf,
            "archers": arc,
            "cavalry": cav,
            "spearmen": spm,
            "special_troops": spc,
            "total": inf + arc + cav + spm + spc,
        },
        "siege_weapons": {
            "catapults": cats,
            "max_catapults": 20,
            "siege_towers": twrs,
            "max_siege_towers": 10,
            "wildfire": wfire,
            "max_wildfire": 5,
        },
        "units_config": {
            k: {
                "name": v["name"],
                "gold_cost": v["gold_cost"],
                "iron_cost": v["iron_cost"],
                "food_upkeep": v.get("upkeep", 0.5),
                "attack": v["attack"],
                "defense": v["defense"],
            }
            for k, v in UNITS_DATA.items()
        },
    }


async def recruit_troops_service(
    session: AsyncSession,
    identifier: int,
    unit_type: str,
    amount: int
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Askar yollash xizmati: Validatsiya, hisob-kitob, tranzaksiya va kvest tekshiruvi.
    """
    user = await crud.get_user_with_relations(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    is_valid, gold_cost, iron_cost, err_msg = validate_recruitment(user, unit_type, amount)
    if not is_valid:
        return False, err_msg, {}

    res = await crud.recruit_troops(
        session=session,
        user_id=user.id,
        unit_type=unit_type,
        amount=amount,
        gold_cost=gold_cost,
        iron_cost=iron_cost,
    )
    ok = res[0] if isinstance(res, (tuple, list)) else bool(res)
    quest_completed = res[1] if isinstance(res, (tuple, list)) and len(res) > 1 else False

    if not ok:
        return False, "Qo'shin yollashda xatolik yuz berdi.", {}

    unit_name = UNITS_DATA.get(unit_type, {}).get("name", unit_type)
    msg = f"✅ Safarbarlik muvaffaqiyatli! +{amount:,} ta {unit_name} safga qo'shildi!"
    if quest_completed:
        msg += "\n\n🎉 Kunlik vazifa bajarildi (100+ askar yollash): +350🪙 Oltin, +700🌾 Oziq-ovqat, +150 XP!"

    return True, msg, {
        "user_id": user.id,
        "unit_type": unit_type,
        "amount": amount,
        "gold_spent": gold_cost,
        "iron_spent": iron_cost,
        "remaining_gold": user.gold,
        "remaining_iron": user.iron,
        "quest_completed": quest_completed,
    }


async def build_siege_service(
    session: AsyncSession,
    identifier: int,
    weapon_type: str,
    amount: int = 1
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Qamal qurolini (katapulta / qamal minorasi) yasash xizmati.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    ok, msg = await crud.build_siege_weapon(session, user.id, weapon_type, amount)
    if not ok:
        return False, msg, {}

    army = await crud.get_user_army(session, user.id)
    return True, msg, {
        "weapon_type": weapon_type,
        "amount": amount,
        "catapults": getattr(army, "catapults", 0) if army else 0,
        "siege_towers": getattr(army, "siege_towers", 0) if army else 0,
        "remaining_gold": user.gold,
        "remaining_iron": user.iron,
        "remaining_food": user.food,
    }
