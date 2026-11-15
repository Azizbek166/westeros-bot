"""
Dengiz Janglari va Flot xizmati (kemalar qurish, qaroqchilarga reyd, PvP dengiz janglari).
"""
import json
import random
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from config import escape_md
from core.leveling import check_user_level_up
from data.naval_data import (
    SHIP_TYPES,
    SEA_ZONES,
    DAILY_NAVAL_PVE_LIMIT,
    DAILY_NAVAL_PVP_LIMIT,
)
from database import crud, models


async def get_or_create_fleet(session: AsyncSession, user_id: int) -> models.UserFleet:
    res = await session.execute(
        select(models.UserFleet).where(models.UserFleet.user_id == user_id)
    )
    fleet = res.scalar_one_or_none()
    if not fleet:
        fleet = models.UserFleet(user_id=user_id)
        session.add(fleet)
        await session.flush()
    return fleet


def calc_fleet_stats(fleet: Optional[models.UserFleet]) -> Dict[str, Any]:
    if not fleet:
        return {"power": 0, "defense": 0, "total_ships": 0, "flagship_bonus": False}
    sloops = fleet.sloops or 0
    galleys = fleet.galleys or 0
    warships = fleet.warships or 0
    flagships = fleet.flagships or 0
    total = sloops + galleys + warships + flagships
    raw_power = (
        sloops * SHIP_TYPES["sloops"]["power"]
        + galleys * SHIP_TYPES["galleys"]["power"]
        + warships * SHIP_TYPES["warships"]["power"]
        + flagships * SHIP_TYPES["flagships"]["power"]
    )
    raw_def = (
        sloops * SHIP_TYPES["sloops"]["defense"]
        + galleys * SHIP_TYPES["galleys"]["defense"]
        + warships * SHIP_TYPES["warships"]["defense"]
        + flagships * SHIP_TYPES["flagships"]["defense"]
    )
    has_flagship = flagships >= 1
    if has_flagship:
        raw_power = int(raw_power * 1.15)
        raw_def = int(raw_def * 1.15)
    return {
        "power": raw_power,
        "defense": raw_def,
        "total_ships": total,
        "flagship_bonus": has_flagship,
    }


def _apply_ship_losses(fleet: models.UserFleet, loss_ratio: float) -> Dict[str, int]:
    lost: Dict[str, int] = {}
    for key in ("sloops", "galleys", "warships", "flagships"):
        cur = getattr(fleet, key, 0) or 0
        if cur <= 0:
            continue
        # Flagships are more resilient
        eff_ratio = loss_ratio * (0.4 if key == "flagships" else 1.0)
        n_lost = int(round(cur * eff_ratio))
        if cur >= 2 and n_lost == 0 and random.random() < eff_ratio:
            n_lost = 1
        n_lost = min(cur, max(0, n_lost))
        if n_lost > 0:
            setattr(fleet, key, cur - n_lost)
            lost[key] = n_lost
    return lost


async def build_ships(
    session: AsyncSession, tg_id: int, ship_key: str, count: int = 1
) -> Tuple[bool, str]:
    if ship_key not in SHIP_TYPES:
        return False, "❌ Bunday kema turi topilmadi."
    if count <= 0 or count > 20:
        return False, "❌ Bir martada 1 dan 20 tagacha kema qurish mumkin."

    user = await crud.get_user_by_telegram_id(session, tg_id)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."

    spec = SHIP_TYPES[ship_key]
    cost_g = spec["gold"] * count
    cost_i = spec["iron"] * count
    cost_f = spec["food"] * count

    if (user.gold or 0) < cost_g or (user.iron or 0) < cost_i or (user.food or 0) < cost_f:
        return (
            False,
            f"❌ Yetarli resurs yo'q! Kerak: {cost_g:,}🪙, {cost_i:,}⛓️, {cost_f:,}🌾\n"
            f"(Sizda: {user.gold or 0:,}🪙, {user.iron or 0:,}⛓️, {user.food or 0:,}🌾)",
        )

    user.gold -= cost_g
    user.iron -= cost_i
    user.food -= cost_f
    fleet = await get_or_create_fleet(session, user.id)
    setattr(fleet, ship_key, (getattr(fleet, ship_key, 0) or 0) + count)
    fleet.updated_at = datetime.utcnow()
    await session.commit()

    return (
        True,
        f"⚓ **{count} ta {spec['icon']} {spec['name']}** muvaffaqiyatli qurildi!\n"
        f"Sarflandi: -{cost_g:,}🪙, -{cost_i:,}⛓️, -{cost_f:,}🌾",
    )


def _refresh_daily_naval_counters(fleet: models.UserFleet) -> str:
    today = crud.get_game_today_str()
    if fleet.daily_pve_date != today:
        fleet.daily_pve_date = today
        fleet.daily_pve_count = 0
    if fleet.daily_pvp_date != today:
        fleet.daily_pvp_date = today
        fleet.daily_pvp_count = 0
    return today


async def raid_sea_zone(
    session: AsyncSession, tg_id: int, zone_key: str
) -> Tuple[bool, str]:
    zone = SEA_ZONES.get(zone_key)
    if not zone:
        return False, "❌ Dengiz hududi topilmadi."

    user = await crud.get_user_by_telegram_id(session, tg_id)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."

    fleet = await get_or_create_fleet(session, user.id)
    _refresh_daily_naval_counters(fleet)
    if (fleet.daily_pve_count or 0) >= DAILY_NAVAL_PVE_LIMIT:
        return False, f"⏳ Bugungi qaroqchilarga qarshi dengiz yurishlari limiti ({DAILY_NAVAL_PVE_LIMIT}/{DAILY_NAVAL_PVE_LIMIT}) tugadi!"

    stats = calc_fleet_stats(fleet)
    if stats["total_ships"] <= 0:
        return False, "⚓ Sizda hali birorta ham kema yo'q! Avval kemasozlik bo'limidan kema quring."
    if stats["power"] < zone["min_power"]:
        return (
            False,
            f"⚠️ Bu hududga suzish uchun flot quvvati kam!\n"
            f"Kerak: kamida **{zone['min_power']}** kuch (Sizda: **{stats['power']}**)",
        )

    fleet.daily_pve_count = (fleet.daily_pve_count or 0) + 1
    atk_roll = stats["power"] * random.uniform(0.88, 1.18)
    def_roll = zone["enemy_power"] * random.uniform(0.85, 1.15)
    won = atk_roll >= def_roll

    if won:
        gold = random.randint(zone["gold_min"], zone["gold_max"])
        food = random.randint(zone["food_min"], zone["food_max"])
        iron = random.randint(zone["iron_min"], zone["iron_max"])
        xp = zone["xp"]
        prestige = zone["prestige"]

        user.gold = (user.gold or 0) + gold
        user.food = (user.food or 0) + food
        user.iron = (user.iron or 0) + iron
        user.xp = (user.xp or 0) + xp
        user.prestige = (user.prestige or 0) + prestige
        crud.track_user_gold_gain(user, gold)
        crud.track_user_prestige_gain(user, prestige)
        check_user_level_up(user)

        lost = _apply_ship_losses(fleet, random.uniform(0.04, 0.12))
        fleet.pirate_wins = (fleet.pirate_wins or 0) + 1
        fleet.sea_plunder_gold = (fleet.sea_plunder_gold or 0) + gold
        outcome = "win"
        lost_str = ", ".join(f"{SHIP_TYPES[k]['icon']} {v}" for k, v in lost.items()) or "Yo'qotish yo'q"
        msg = (
            f"🏴‍☠️ **DENGIZ G'ALABASI — {zone['name']}!**\n\n"
            f"Raqib: _{zone['enemy_name']}_\n"
            f"🎁 **O'lja:** +{gold:,} 🪙 Oltin, +{food:,} 🌾 Bug'doy, +{iron:,} ⛓️ Temir\n"
            f"✨ **Tajriba:** +{xp} XP | +{prestige} ⭐ Nufuz\n"
            f"💥 **Talofat:** {lost_str}"
        )
    else:
        lost = _apply_ship_losses(fleet, random.uniform(0.15, 0.28))
        fleet.naval_losses = (fleet.naval_losses or 0) + 1
        gold = food = iron = 0
        outcome = "loss"
        lost_str = ", ".join(f"{SHIP_TYPES[k]['icon']} {v}" for k, v in lost.items()) or "Yo'qotish yo'q"
        msg = (
            f"🌊 **DENGIZ MAG'LUBIYATI — {zone['name']}**\n\n"
            f"_{zone['enemy_name']}_ flotingizni chekinishga majbur qildi!\n"
            f"💥 **Talofat:** {lost_str}\n"
            f"💡 Flotingizni kuchaytirib, qayta urinib ko'ring."
        )

    fleet.updated_at = datetime.utcnow()
    session.add(
        models.NavalBattleReport(
            attacker_id=user.id,
            defender_id=None,
            sea_zone=zone["name"],
            battle_type="pve",
            outcome=outcome,
            gold_looted=gold,
            food_looted=food,
            iron_looted=iron,
            ships_lost_json=json.dumps(lost),
            summary=msg,
        )
    )
    await session.commit()
    return True, msg


async def get_pvp_targets(
    session: AsyncSession, user: models.User, limit: int = 8
) -> List[Dict[str, Any]]:
    now = datetime.utcnow()
    res = await session.execute(
        select(models.UserFleet, models.User)
        .join(models.User, models.User.id == models.UserFleet.user_id)
        .where(
            models.UserFleet.user_id != user.id,
            (models.UserFleet.sloops + models.UserFleet.galleys + models.UserFleet.warships + models.UserFleet.flagships) > 0,
        )
        .order_by(desc(models.UserFleet.naval_wins + models.UserFleet.pirate_wins))
        .limit(limit * 2)
    )
    targets: List[Dict[str, Any]] = []
    for fl, u in res.all():
        if user.house_id and u.house_id == user.house_id:
            continue
        if u.peace_shield_until and u.peace_shield_until > now:
            continue
        st = calc_fleet_stats(fl)
        if st["total_ships"] <= 0:
            continue
        targets.append({
            "user_id": u.id,
            "name": u.full_name or u.username or f"Lord #{u.id}",
            "power": st["power"],
            "ships": st["total_ships"],
            "wins": (fl.naval_wins or 0) + (fl.pirate_wins or 0),
        })
        if len(targets) >= limit:
            break
    return targets


async def attack_player_fleet(
    session: AsyncSession, attacker_tg_id: int, target_user_id: int
) -> Tuple[bool, str]:
    attacker = await crud.get_user_by_telegram_id(session, attacker_tg_id)
    defender = await session.get(models.User, target_user_id)
    if not attacker or not defender:
        return False, "❌ O'yinchi topilmadi."
    if attacker.id == defender.id:
        return False, "❌ O'z flotingizga hujum qila olmaysiz."
    if attacker.house_id and attacker.house_id == defender.house_id:
        return False, "❌ O'z xonadondoshingiz flotiga hujum qilib bo'lmaydi!"

    now = datetime.utcnow()
    if defender.peace_shield_until and defender.peace_shield_until > now:
        return False, "🛡️ Raqibda Tinchlik Qalqoni faol!"

    atk_fleet = await get_or_create_fleet(session, attacker.id)
    def_fleet = await get_or_create_fleet(session, defender.id)
    _refresh_daily_naval_counters(atk_fleet)
    if (atk_fleet.daily_pvp_count or 0) >= DAILY_NAVAL_PVP_LIMIT:
        return False, f"⏳ Bugungi PvP dengiz janglari limiti ({DAILY_NAVAL_PVP_LIMIT}/{DAILY_NAVAL_PVP_LIMIT}) tugadi!"

    atk_stats = calc_fleet_stats(atk_fleet)
    def_stats = calc_fleet_stats(def_fleet)
    if atk_stats["total_ships"] <= 0:
        return False, "⚓ Sizda hali kema yo'q!"
    if def_stats["total_ships"] <= 0:
        return False, "⚓ Raqibda kema qolmagan!"

    atk_fleet.daily_pvp_count = (atk_fleet.daily_pvp_count or 0) + 1
    atk_roll = atk_stats["power"] * random.uniform(0.9, 1.15)
    def_roll = max(20, def_stats["defense"]) * random.uniform(0.9, 1.15)
    won = atk_roll >= def_roll

    def_name = escape_md(defender.full_name or defender.username or f"Lord #{defender.id}")
    if won:
        loot_g = min(2500, int((defender.gold or 0) * 0.06))
        loot_f = min(5000, int((defender.food or 0) * 0.06))
        loot_i = min(1800, int((defender.iron or 0) * 0.06))
        defender.gold = max(0, (defender.gold or 0) - loot_g)
        defender.food = max(0, (defender.food or 0) - loot_f)
        defender.iron = max(0, (defender.iron or 0) - loot_i)

        attacker.gold = (attacker.gold or 0) + loot_g
        attacker.food = (attacker.food or 0) + loot_f
        attacker.iron = (attacker.iron or 0) + loot_i
        attacker.xp = (attacker.xp or 0) + 80
        attacker.prestige = (attacker.prestige or 0) + 12
        crud.track_user_gold_gain(attacker, loot_g)
        crud.track_user_prestige_gain(attacker, 12)
        check_user_level_up(attacker)

        atk_lost = _apply_ship_losses(atk_fleet, random.uniform(0.06, 0.14))
        _apply_ship_losses(def_fleet, random.uniform(0.15, 0.25))
        atk_fleet.naval_wins = (atk_fleet.naval_wins or 0) + 1
        def_fleet.naval_losses = (def_fleet.naval_losses or 0) + 1
        atk_fleet.sea_plunder_gold = (atk_fleet.sea_plunder_gold or 0) + loot_g
        outcome = "win"
        lost_str = ", ".join(f"{SHIP_TYPES[k]['icon']} {v}" for k, v in atk_lost.items()) or "Yo'qotish yo'q"
        msg = (
            f"⚔️ **DENGIZ PvP G'ALABASI!**\n\n"
            f"Raqib: *{def_name}* floti tor-mor etildi!\n"
            f"🎁 **O'lja:** +{loot_g:,} 🪙, +{loot_f:,} 🌾, +{loot_i:,} ⛓️\n"
            f"✨ **Bonus:** +80 XP | +12 ⭐ Nufuz\n"
            f"💥 **Sizning talofatingiz:** {lost_str}"
        )
    else:
        atk_lost = _apply_ship_losses(atk_fleet, random.uniform(0.16, 0.28))
        _apply_ship_losses(def_fleet, random.uniform(0.05, 0.12))
        atk_fleet.naval_losses = (atk_fleet.naval_losses or 0) + 1
        def_fleet.naval_wins = (def_fleet.naval_wins or 0) + 1
        loot_g = loot_f = loot_i = 0
        outcome = "loss"
        lost_str = ", ".join(f"{SHIP_TYPES[k]['icon']} {v}" for k, v in atk_lost.items()) or "Yo'qotish yo'q"
        msg = (
            f"🌊 **DENGIZ PvP MAG'LUBIYATI**\n\n"
            f"*{def_name}* floti hujumingizni qaytardi!\n"
            f"💥 **Sizning talofatingiz:** {lost_str}"
        )

    atk_fleet.updated_at = now
    def_fleet.updated_at = now
    session.add(
        models.NavalBattleReport(
            attacker_id=attacker.id,
            defender_id=defender.id,
            sea_zone="PvP Dengiz Jangi",
            battle_type="pvp",
            outcome=outcome,
            gold_looted=loot_g,
            food_looted=loot_f,
            iron_looted=loot_i,
            ships_lost_json=json.dumps(atk_lost),
            summary=msg,
        )
    )
    await session.commit()
    return True, msg


async def get_naval_leaderboard(session: AsyncSession, limit: int = 10) -> List[Dict[str, Any]]:
    res = await session.execute(
        select(models.UserFleet, models.User)
        .join(models.User, models.User.id == models.UserFleet.user_id)
        .order_by(desc(models.UserFleet.naval_wins + models.UserFleet.pirate_wins))
        .limit(limit)
    )
    rows = []
    for fl, u in res.all():
        st = calc_fleet_stats(fl)
        rows.append({
            "name": u.full_name or u.username or f"Lord #{u.id}",
            "wins": (fl.naval_wins or 0) + (fl.pirate_wins or 0),
            "power": st["power"],
            "ships": st["total_ships"],
            "plunder": fl.sea_plunder_gold or 0,
        })
    return rows
