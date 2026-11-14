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


async def get_buildings_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    O'yinchining barcha qurilish inshootlari (Temir koni, Don tegirmoni, Qal'a istehkomlari & Ajdarlar uyasi).
    """
    import config
    user = await crud.get_user_any(session, identifier)
    if not user:
        return None

    castles = await crud.get_user_and_house_castles(session, user)
    mine_lvl = getattr(user, "iron_mine_level", 1) or 1
    mill_lvl = getattr(user, "grain_mill_level", 1) or 1
    max_castle_lvl = max([(getattr(c, "castle_level", 1) or 1) for c in castles], default=1)

    b_cfg = getattr(config, "BUILDINGS_CONFIG", {})
    mine_cfg = b_cfg.get("iron_mine", {})
    mill_cfg = b_cfg.get("grain_mill", {})
    castle_cfg = b_cfg.get("castle_keep", {})

    mine_max = int(mine_cfg.get("max_level", 10))
    mill_max = int(mill_cfg.get("max_level", 10))
    castle_max = int(castle_cfg.get("max_level", 5))

    mine_gold_cost = int(mine_cfg.get("gold_per_level", mine_cfg.get("base_gold_cost", 400))) * mine_lvl
    mine_food_cost = int(mine_cfg.get("food_per_level", mine_cfg.get("base_food_cost", 250))) * mine_lvl

    mill_gold_cost = int(mill_cfg.get("gold_per_level", mill_cfg.get("base_gold_cost", 350))) * mill_lvl
    mill_iron_cost = int(mill_cfg.get("iron_per_level", mill_cfg.get("base_iron_cost", 200))) * mill_lvl

    castle_buildings = []
    for c in castles:
        c_lvl = getattr(c, "castle_level", 1) or 1
        c_gold, c_iron, c_food = crud.get_castle_upgrade_cost(c_lvl)
        castle_buildings.append({
            "territory_id": c.id,
            "name": c.castle_name or c.name,
            "region": c.region,
            "level": c_lvl,
            "max_level": castle_max,
            "is_max": c_lvl >= castle_max,
            "defense": c.defense or 0,
            "scorpion_dr_pct": min(60, c_lvl * 8),
            "upgrade_cost": {
                "gold": c_gold,
                "iron": c_iron,
                "food": c_food,
            },
            "can_afford": (
                c_lvl < castle_max
                and (user.gold or 0) >= c_gold
                and (user.iron or 0) >= c_iron
                and (user.food or 0) >= c_food
            ),
        })

    buildings = [
        {
            "key": "iron_mine",
            "name": mine_cfg.get("name", "Temir Koni"),
            "emoji": mine_cfg.get("emoji", "⛏️"),
            "description": mine_cfg.get("description", "Har soatlik temir qazib olish hajmini oshiradi va yuqori darajali ajdarlar uchun talab qilinadi."),
            "level": mine_lvl,
            "max_level": mine_max,
            "is_max": mine_lvl >= mine_max,
            "current_Production": mine_lvl * int(mine_cfg.get("hourly_iron_per_level", 15)),
            "next_production": (mine_lvl + 1) * int(mine_cfg.get("hourly_iron_per_level", 15)),
            "production_unit": "⛓️ Temir/soat",
            "upgrade_cost": {
                "gold": mine_gold_cost,
                "food": mine_food_cost,
                "iron": 0,
            },
            "can_afford": (
                mine_lvl < mine_max
                and (user.gold or 0) >= mine_gold_cost
                and (user.food or 0) >= mine_food_cost
            ),
        },
        {
            "key": "grain_mill",
            "name": mill_cfg.get("name", "Don Tegirmoni"),
            "emoji": mill_cfg.get("emoji", "🌾"),
            "description": mill_cfg.get("description", "Har soatlik bug'doy hosildorligini oshiradi va qo'shin hamda ajdarlarni boqish manbai."),
            "level": mill_lvl,
            "max_level": mill_max,
            "is_max": mill_lvl >= mill_max,
            "current_production": mill_lvl * int(mill_cfg.get("hourly_food_per_level", 25)),
            "next_production": (mill_lvl + 1) * int(mill_cfg.get("hourly_food_per_level", 25)),
            "production_unit": "🌾 Bug'doy/soat",
            "upgrade_cost": {
                "gold": mill_gold_cost,
                "food": 0,
                "iron": mill_iron_cost,
            },
            "can_afford": (
                mill_lvl < mill_max
                and (user.gold or 0) >= mill_gold_cost
                and (user.iron or 0) >= mill_iron_cost
            ),
        },
    ]

    return {
        "user_id": user.id,
        "resources": {
            "gold": user.gold or 0,
            "food": user.food or 0,
            "iron": user.iron or 0,
        },
        "summary": {
            "iron_mine_level": mine_lvl,
            "grain_mill_level": mill_lvl,
            "max_castle_level": max_castle_lvl,
        },
        "buildings": buildings,
        "castle_fortifications": castle_buildings,
    }


async def upgrade_building_service(
    session: AsyncSession,
    identifier: int,
    building_type: str,
    territory_id: Optional[int] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Inshoot yoki qal'a istehkomini ko'tarish (iron_mine, grain_mill, castle_keep).
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    b_type = (building_type or "").strip().lower()
    if b_type in ("iron_mine", "mine"):
        ok, msg = await crud.upgrade_building(session, user.id, "mine")
    elif b_type in ("grain_mill", "mill"):
        ok, msg = await crud.upgrade_building(session, user.id, "mill")
    elif b_type in ("castle_keep", "castle"):
        if not territory_id:
            castles = await crud.get_user_and_house_castles(session, user)
            if not castles:
                return False, "Sizda yoki Xonadoningizda qal'a mavjud emas!", {}
            territory_id = castles[0].id
        ok, msg = await crud.upgrade_castle_fortification(session, user.id, int(territory_id))
    else:
        return False, "Noma'lum inshoot turi.", {}

    hub = await get_buildings_hub_data(session, user.id) if ok else {}
    return ok, msg, hub or {}
