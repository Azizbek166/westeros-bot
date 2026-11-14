"""
Dragon System Service for Telegram Mini App & Bot.
Unified 6-species config, egg hatching, feeding, training, combat stats, and recovery.
"""
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models
from config import DRAGON_SPECIES_CONFIG, DRAGON_BALANCE_CONFIG


async def get_dragon_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Ajdarlar uyasi (Dragon Roost) bosh sahifasi ma'lumotlari (Bot va Mini App uchun bitta mantiq).
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        return None

    dragons = await crud.get_user_dragons(session, user.id)
    max_castle_lvl = await crud.get_user_max_castle_level(session, user)
    user_lvl = getattr(user, "level", 1) or 1
    iron_mine_lvl = getattr(user, "iron_mine_level", 1) or 1
    grain_mill_lvl = getattr(user, "grain_mill_level", 1) or 1

    dragon_list = []
    for d in dragons:
        costs = crud.get_dragon_upgrade_cost(d)
        feed_cost = crud.get_dragon_feed_cost(d)
        stats = crud.get_dragon_combat_stats(d)
        spec = crud.get_dragon_species_config(d.name, getattr(d, "grade", "C"))
        deploy_st = await crud.get_dragon_deployment_status(session, d.id)

        dragon_list.append({
            "id": d.id,
            "name": d.name,
            "grade": getattr(d, "grade", spec["grade"]) or spec["grade"],
            "species_title": spec["title"],
            "level": d.level or 1,
            "max_level": DRAGON_BALANCE_CONFIG.get("max_level", 20),
            "power": d.power or stats["power"],
            "max_power": stats["max_power"],
            "attack": stats["attack"],
            "defense": stats["defense"],
            "hp": stats["hp"],
            "max_hp": stats["max_hp"],
            "is_wounded": stats["is_wounded"],
            "recovery_status": stats["recovery_status"],
            "hunger": getattr(d, "hunger", 100) if getattr(d, "hunger", None) is not None else 100,
            "stage": getattr(d, "stage", "baby") or "baby",
            "is_egg": (getattr(d, "stage", "") == "egg"),
            "feed_food_cost": feed_cost,
            "upgrade_costs": costs,
            "hatch_costs": {
                "gold": spec.get("hatch_cost_gold", 3000),
                "iron": spec.get("hatch_cost_iron", 2500),
                "food": spec.get("hatch_cost_food", 5000),
                "hours": spec.get("hatch_hours", 2),
            },
            "is_stationed": (deploy_st.get("type") == "stationed"),
            "deployment": deploy_st,
        })

    species_catalog = []
    for sp_name, sp in DRAGON_SPECIES_CONFIG.items():
        meets_reqs = (
            user_lvl >= sp["req_player_level"]
            and max_castle_lvl >= sp["req_castle_level"]
            and iron_mine_lvl >= sp["req_iron_mine_level"]
            and grain_mill_lvl >= sp["req_grain_mill_level"]
        )
        can_afford = (
            (user.gold or 0) >= sp["price_gold"]
            and (user.iron or 0) >= sp["price_iron"]
            and (user.food or 0) >= sp["price_food"]
        )
        species_catalog.append({
            **sp,
            "meets_requirements": meets_reqs,
            "can_afford": can_afford,
        })

    return {
        "user_id": user.id,
        "user_level": user_lvl,
        "user_food": user.food or 0,
        "user_gold": user.gold or 0,
        "user_iron": user.iron or 0,
        "castle_level": max_castle_lvl,
        "iron_mine_level": iron_mine_lvl,
        "grain_mill_level": grain_mill_lvl,
        "max_dragons": DRAGON_BALANCE_CONFIG.get("max_dragons_per_player", 2),
        "dragons_count": len(dragon_list),
        "dragons": dragon_list,
        "has_dragon": len(dragon_list) > 0,
        "species_catalog": species_catalog,
        "anti_dragon_info": {
            "scorpion_reduction_per_castle_lvl_pct": int(DRAGON_BALANCE_CONFIG.get("scorpion_defense_per_castle_level", 0.08) * 100),
            "max_reduction_pct": int(DRAGON_BALANCE_CONFIG.get("max_anti_dragon_damage_reduction", 0.60) * 100),
        },
    }


async def claim_starter_dragon_egg_service(
    session: AsyncSession,
    identifier: int,
    name: str,
    grade: str = "C",
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Ajdar tuxumini xarid qilish (config.DRAGON_SPECIES_CONFIG shartlari va narxlari bilan)"""
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", None

    clean_name = name.strip() or "Arrax"
    ok, msg, dragon = await crud.claim_dragon_egg(session, user.id, clean_name, grade=grade)
    if not ok:
        return False, msg, None

    return True, msg, {
        "id": dragon.id,
        "name": dragon.name,
        "grade": dragon.grade,
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
    """Ajdahoni oziqlantirish va yaradorlikdan tiklash"""
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
