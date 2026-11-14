from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple, Set
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models
from core.anti_cheat import can_attack_target
from config import BASE_MARCH_MINUTES


async def get_battle_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Harbiy amaliyotlar markazi: Faol yurishlar, qal'amizga bo'layotgan hujumlar va jang hisobotlari.
    """
    user = await crud.get_user_with_relations(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return None

    now = datetime.utcnow()

    # 1. Faol chiquvchi yurishlar
    marches_res = await session.execute(
        select(models.BattleMarch).where(
            models.BattleMarch.attacker_user_id == user.id,
            models.BattleMarch.status == "marching",
        )
    )
    active_marches = marches_res.scalars().all()
    outbound = []
    for m in active_marches:
        terr = await session.get(models.Territory, m.target_territory_id)
        rem_sec = max(0, int((m.arrival_time - now).total_seconds())) if m.arrival_time else 0
        tot_troops = (
            (m.infantry or 0)
            + (m.archers or 0)
            + (m.cavalry or 0)
            + (m.spearmen or 0)
            + (m.special_troops or 0)
        )
        outbound.append({
            "march_id": m.id,
            "target_territory_id": m.target_territory_id,
            "target_name": terr.name if terr else "Qal'a",
            "target_territory_name": terr.name if terr else "Qal'a",
            "target_castle_name": terr.castle_name if terr else "Qal'a",
            "seconds_remaining": rem_sec,
            "total_troops": tot_troops,
            "infantry": m.infantry or 0,
            "archers": m.archers or 0,
            "cavalry": m.cavalry or 0,
            "spearmen": m.spearmen or 0,
            "has_dragon": m.has_dragon,
            "dragon_tactic": m.dragon_tactic,
            "arrival_time": m.arrival_time.isoformat() if m.arrival_time else None,
        })

    # 2. Qal'alarimizga kelayotgan dushman hujumlari (incoming attacks)
    incoming = []
    if user.house_id:
        relevant_house_ids = [user.house_id]
        allies = await crud.get_active_alliances_for_house(session, user.house_id)
        for al in allies:
            ally_id = al.house_b_id if al.house_a_id == user.house_id else al.house_a_id
            if ally_id not in relevant_house_ids:
                relevant_house_ids.append(ally_id)

        terr_ids_res = await session.execute(
            select(models.Territory.id).where(models.Territory.owner_house_id.in_(relevant_house_ids))
        )
        house_terr_ids = terr_ids_res.scalars().all()
        if house_terr_ids:
            inc_res = await session.execute(
                select(models.BattleMarch).where(
                    models.BattleMarch.target_territory_id.in_(house_terr_ids),
                    models.BattleMarch.status == "marching",
                )
            )
            for im in inc_res.scalars().all():
                terr = await session.get(models.Territory, im.target_territory_id)
                att_user = await session.get(models.User, im.attacker_user_id)
                rem_sec = max(0, int((im.arrival_time - now).total_seconds())) if im.arrival_time else 0
                incoming.append({
                    "march_id": im.id,
                    "target_territory_id": im.target_territory_id,
                    "target_name": terr.name if terr else "Qal'a",
                    "target_castle_name": terr.castle_name if terr else "Qal'a",
                    "is_allied_castle": bool(terr and terr.owner_house_id != user.house_id),
                    "seconds_remaining": rem_sec,
                    "has_dragon": im.has_dragon,
                    "attacker_name": att_user.full_name if att_user else "Dushman",
                })

    # 3. So'nggi jang hisobotlari
    reports_res = await session.execute(
        select(models.BattleReport)
        .where(
            (models.BattleReport.attacker_user_id == user.id) |
            (models.BattleReport.defender_user_id == user.id)
        )
        .order_by(desc(models.BattleReport.id))
        .limit(5)
    )
    reports = []
    for r in reports_res.scalars().all():
        terr = await session.get(models.Territory, r.territory_id) if r.territory_id else None
        reports.append({
            "report_id": r.id,
            "territory_name": terr.name if terr else "Qal'a",
            "result": r.result,
            "is_attacker": (r.attacker_user_id == user.id),
            "gold_looted": r.loot_gold or 0,
            "food_looted": r.loot_food or 0,
            "iron_looted": r.loot_iron or 0,
            "occurred_at": r.timestamp.isoformat() if r.timestamp else None,
        })

    return {
        "user_id": user.id,
        "active_marches": outbound,
        "active_outbound_marches": outbound,
        "incoming_attacks": incoming,
        "recent_reports": reports,
    }


async def validate_march_target(
    session: AsyncSession,
    user: models.User,
    terr: models.Territory
) -> Tuple[bool, str]:
    """
    Harbiy yurish boshlash qoidalari va cheklovlarini qat'iy tekshirish.
    """
    # 1. Urush rejimi faolligi
    war_status = await crud.get_war_status(session)
    if not war_status["is_active"]:
        return False, "🕊️ Hozirda Vesterosda sulh davri! Urush rejimi yopiq. Hujum jo'natib bo'lmaydi."

    # 2. Qonuniy nishon (o'z qal'asiga emas, kamida 50 askar)
    is_allowed, err_msg = can_attack_target(user, terr)
    if not is_allowed:
        return False, err_msg

    # 3. Tinchlik Qalqoni (Peace Shield)
    is_shielded, shield_until, defender_name = await crud.get_territory_shield_status(session, terr)
    if is_shielded and shield_until:
        diff = shield_until - datetime.utcnow()
        hours_left = max(1, int(diff.total_seconds() // 3600))
        return False, f"🛡️ Ushbu qal'a egasi Tinchlik Qalqoni himoyasida ({hours_left} soat qoldi)! Unga hujum qilib bo'lmaydi."

    # 4. Rasmiy ittifoqdosh qal'asi
    if user.house_id and terr.owner_house_id and user.house_id != terr.owner_house_id:
        allies = await crud.get_active_alliances_for_house(session, user.house_id)
        allied_ids = {a.house_a_id if a.house_b_id == user.house_id else a.house_b_id for a in allies}
        if terr.owner_house_id in allied_ids:
            return False, "❌ Ushbu qal'a rasmiy ittifoqchingizga qarashli!"

    # 5. 5 ta qal'a limiti
    if user.house_id and terr.owner_house_id != user.house_id:
        h_castles = await crud.get_house_castle_count(session, user.house_id)
        if h_castles >= crud.MAX_HOUSE_CASTLES:
            return False, f"❌ Xonadoningiz allaqachon {h_castles}/{crud.MAX_HOUSE_CASTLES} ta qal'aga ega (Limit: {crud.MAX_HOUSE_CASTLES} ta)!"

    return True, "OK"


async def dispatch_march_service(
    session: AsyncSession,
    identifier: int,
    territory_id: int,
    percent: int = 50,
    dragon_tactic: str = "none",
    explicit_troops: Optional[Dict[str, int]] = None,
    has_dragon_flag: Optional[bool] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]], Set[int]]:
    """
    Harbiy yurishni jo'natish xizmati.
    Qaytaradi: (success, message, march_dict, defender_telegram_ids)
    """
    user = await crud.get_user_with_relations(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", None, set()

    terr = await crud.get_territory_by_id(session, territory_id)
    if not terr:
        return False, "Qal'a topilmadi.", None, set()

    is_valid, err_msg = await validate_march_target(session, user, terr)
    if not is_valid:
        return False, err_msg, None, set()

    user_army = await crud.get_user_army(session, user.id)
    if not user_army:
        return False, "Sizda armiya mavjud emas.", None, set()

    if explicit_troops is not None and sum(max(0, int(v or 0)) for v in explicit_troops.values()) > 0:
        infantry = min(user_army.infantry or 0, max(0, int(explicit_troops.get("infantry", 0) or 0)))
        archers = min(user_army.archers or 0, max(0, int(explicit_troops.get("archers", 0) or 0)))
        cavalry = min(user_army.cavalry or 0, max(0, int(explicit_troops.get("cavalry", 0) or 0)))
        spearmen = min(user_army.spearmen or 0, max(0, int(explicit_troops.get("spearmen", 0) or 0)))
        special = min(user_army.special_troops or 0, max(0, int(explicit_troops.get("special_troops", 0) or 0)))
        catapults = min(getattr(user_army, "catapults", 0) or 0, max(0, int(explicit_troops.get("catapults", 0) or 0)))
        siege_towers = min(getattr(user_army, "siege_towers", 0) or 0, max(0, int(explicit_troops.get("siege_towers", 0) or 0)))
    else:
        ratio = max(0.1, min(1.0, (percent or 50) / 100.0))
        infantry = int((user_army.infantry or 0) * ratio)
        archers = int((user_army.archers or 0) * ratio)
        cavalry = int((user_army.cavalry or 0) * ratio)
        spearmen = int((user_army.spearmen or 0) * ratio)
        special = int((user_army.special_troops or 0) * ratio)
        catapults = int((getattr(user_army, "catapults", 0) or 0) * ratio)
        siege_towers = int((getattr(user_army, "siege_towers", 0) or 0) * ratio)

    total_sent = infantry + archers + cavalry + spearmen + special
    if total_sent <= 0:
        return False, "❌ Yuborish uchun askarlar soni yetarli emas.", None, set()

    # O'z tinchlik qalqonini bekor qilish
    user.peace_shield_until = None

    has_dragon = bool(has_dragon_flag) if has_dragon_flag is not None else (dragon_tactic != "none")
    if has_dragon and dragon_tactic == "none":
        dragon_tactic = "balanced"
    dragon_id_to_send = None
    if has_dragon:
        from config import DRAGON_BALANCE_CONFIG
        min_hunger = DRAGON_BALANCE_CONFIG.get("min_hunger_for_battle", 30)
        free_dragons = [
            d for d in await crud.get_user_available_dragons(session, user.id)
            if (getattr(d, "hunger", 100) or 0) >= min_hunger and getattr(d, "stage", "") != "egg"
        ]
        if free_dragons:
            dragon_id_to_send = free_dragons[0].id
        else:
            has_dragon = False
            dragon_tactic = "none"

    user_chars = await crud.get_user_characters(session, user.id)
    char_id = user_chars[0].id if user_chars else None

    march = await crud.create_battle_march(
        session=session,
        attacker_user_id=user.id,
        source_territory_id=terr.id,
        target_territory_id=terr.id,
        infantry=infantry,
        archers=archers,
        cavalry=cavalry,
        spearmen=spearmen,
        special_troops=special,
        catapults=catapults,
        siege_towers=siege_towers,
        character_id=char_id,
        duration_minutes=BASE_MARCH_MINUTES,
        has_dragon=has_dragon,
        dragon_tactic=dragon_tactic,
        dragon_id=dragon_id_to_send,
    )

    # Himoyachi o'yinchilar Telegram ID larini yig'ish (xabarnoma uchun)
    defender_tg_ids: Set[int] = set()
    if terr.owner_house_id and terr.owner_house_id != user.house_id:
        target_house = await session.get(models.House, terr.owner_house_id)
        if getattr(terr, "conquered_by_user_id", None):
            c_user = await session.get(models.User, terr.conquered_by_user_id)
            if c_user and c_user.telegram_id and c_user.telegram_id != user.telegram_id:
                defender_tg_ids.add(c_user.telegram_id)
        if target_house and target_house.lord_user_id and target_house.lord_user_id != user.telegram_id:
            defender_tg_ids.add(target_house.lord_user_id)
        h_members_res = await session.execute(
            select(models.User.telegram_id).where(models.User.house_id == terr.owner_house_id)
        )
        for (mid,) in h_members_res.all():
            if mid and mid != user.telegram_id:
                defender_tg_ids.add(mid)

    return True, f"🚩 {total_sent:,} kishilik qo'shin «{terr.name}» sari yo'lga chiqdi!", {
        "march_id": march.id,
        "target_territory_id": terr.id,
        "target_name": terr.name,
        "total_troops": total_sent,
        "has_dragon": has_dragon,
        "arrival_time": march.arrival_time.isoformat() if march.arrival_time else None,
        "duration_minutes": BASE_MARCH_MINUTES,
        "travel_seconds": BASE_MARCH_MINUTES * 60,
    }, defender_tg_ids
