from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models


async def get_castles_overview(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    O'yinchining barcha qal'alari (poytaxt, egallangan, xonadon qal'alari) va ulardan
    yig'ilgan o'lpon holati to'liq ko'rinishi.
    """
    user = await crud.get_user_with_relations(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return None

    castles = await crud.get_user_and_house_castles(session, user)
    now = datetime.utcnow()

    castles_list = []
    ready_count = 0
    total_accumulated_gold = 0
    total_accumulated_food = 0
    total_accumulated_iron = 0
    min_rem_wait = 60

    h_castles_len = len(castles)
    for c in castles:
        hours, rem_min = crud.get_user_castle_tax_hours(user, c, now)
        if hours >= 1:
            ready_count += 1
        elif rem_min > 0 and rem_min < min_rem_wait:
            min_rem_wait = rem_min

        tot_gar = (
            (c.garrison_infantry or 0)
            + (c.garrison_archers or 0)
            + (c.garrison_cavalry or 0)
            + (c.garrison_spearmen or 0)
        )
        is_lib = crud.is_castle_liberable(user, c, user_castles_count=h_castles_len)
        is_cap = (
            crud.is_ancestral_capital_of_house(c, user.house_id)
            if user.house_id
            else c.is_capital
        )

        c_lvl = getattr(c, "castle_level", 1) or 1
        lvl_mult = 1.0 + (max(1, c_lvl) - 1) * 0.25
        c_gh = int((c.gold_income or 20) * lvl_mult)
        c_fh = int((c.food_income or 50) * lvl_mult)
        c_ih = int((c.iron_income or 15) * lvl_mult)

        accum_gold = c_gh * max(1, hours) if hours >= 1 else 0
        accum_food = c_fh * max(1, hours) if hours >= 1 else 0
        accum_iron = c_ih * max(1, hours) if hours >= 1 else 0

        total_accumulated_gold += accum_gold
        total_accumulated_food += accum_food
        total_accumulated_iron += accum_iron

        castles_list.append({
            "id": c.id,
            "code": c.code,
            "name": c.name,
            "castle_name": c.castle_name or c.name,
            "region": c.region,
            "is_capital": is_cap,
            "is_liberable": is_lib,
            "castle_level": c_lvl,
            "defense": c.defense or 0,
            "garrison_total": tot_gar,
            "hourly_income": {
                "gold": c_gh,
                "food": c_fh,
                "iron": c_ih,
            },
            "tax": {
                "hours_ready": hours,
                "is_ready": hours >= 1,
                "rem_minutes": rem_min,
                "accumulated_gold": accum_gold,
                "accumulated_food": accum_food,
                "accumulated_iron": accum_iron,
            },
        })

    return {
        "user_id": user.id,
        "total_castles": len(castles),
        "ready_castles_count": ready_count,
        "min_wait_minutes": min_rem_wait if ready_count == 0 else 0,
        "total_claimable": {
            "gold": total_accumulated_gold,
            "food": total_accumulated_food,
            "iron": total_accumulated_iron,
        },
        "castles": castles_list,
    }


async def collect_castle_tax_service(
    session: AsyncSession,
    identifier: int,
    territory_id: int
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Bitta qal'adan to'plangan soatlik o'lponni yig'ib olish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    ok, msg, res = await crud.collect_castle_tax(session, user.id, territory_id)
    return ok, msg, res or {}


async def collect_all_castles_tax_service(
    session: AsyncSession,
    identifier: int
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Barcha tayyor qal'alardan 1-bosishda bir vaqtning o'zida o'lpon yig'ib olish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    ok, msg, res = await crud.collect_all_castles_tax(session, user.id)
    return ok, msg, res or {}


async def get_castle_detail_service(
    session: AsyncSession,
    identifier: int,
    territory_id: int
) -> Optional[Dict[str, Any]]:
    """
    Tanlangan qal'aning to'liq tafsilotlari (garnizon tarkibi, devor darajasi, mudofaa va o'lpon).
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return None

    terr = await crud.get_territory_by_id(session, territory_id)
    if not terr:
        return None

    now = datetime.utcnow()
    hours, rem_min = crud.get_user_castle_tax_hours(user, terr, now)
    c_lvl = getattr(terr, "castle_level", 1) or 1
    lvl_mult = 1.0 + (max(1, c_lvl) - 1) * 0.25

    return {
        "id": terr.id,
        "name": terr.name,
        "castle_name": terr.castle_name or terr.name,
        "region": terr.region,
        "castle_level": c_lvl,
        "defense": terr.defense or 0,
        "max_defense": 2000,
        "is_capital": terr.is_capital,
        "owner_house_id": terr.owner_house_id,
        "conquered_by_user_id": terr.conquered_by_user_id,
        "garrison": {
            "infantry": terr.garrison_infantry or 0,
            "archers": terr.garrison_archers or 0,
            "cavalry": terr.garrison_cavalry or 0,
            "spearmen": terr.garrison_spearmen or 0,
            "total": (
                (terr.garrison_infantry or 0)
                + (terr.garrison_archers or 0)
                + (terr.garrison_cavalry or 0)
                + (terr.garrison_spearmen or 0)
            ),
        },
        "income": {
            "gold_hourly": int((terr.gold_income or 20) * lvl_mult),
            "food_hourly": int((terr.food_income or 50) * lvl_mult),
            "iron_hourly": int((terr.iron_income or 15) * lvl_mult),
        },
        "tax": {
            "hours_ready": hours,
            "is_ready": hours >= 1,
            "rem_minutes": rem_min,
            "accumulated_gold": int((terr.gold_income or 20) * lvl_mult * max(1, hours)) if hours >= 1 else 0,
        },
    }
