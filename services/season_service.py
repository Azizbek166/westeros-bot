"""
THE IRON THRONE RPG - SEASON & SEASON PASS SERVICE LAYER
Mavsum boshqaruvi, Season Ochkolari (SO), Season Pass tierlari,
Mavsum yakunlanishi (Snapshot), Idempotent mukofotlar va Yumshoq Reset (Soft-Reset).
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import models
from core.season_config import (
    DEFAULT_SEASON_WEEKS,
    DEFAULT_SEASON_DAYS,
    SEASON_PASS_XP_PER_TIER,
    TOTAL_SEASON_PASS_TIERS,
    PREMIUM_PASS_PRICE_STARS,
    PREMIUM_PASS_PRICE_UZS,
    PASS_XP_REWARDS,
    SEASON_PASS_TIERS_CONFIG,
    SEASON_END_RANK_REWARDS,
    POINTS_WEIGHTS,
    SOFT_RESET,
)
from core.cosmetics import grant_cosmetic_item

logger = logging.getLogger(__name__)


# ============================================================
# 1. MAVSUMLARNI OLISH VA ISHGA TUSHIRISH
# ============================================================

async def get_or_create_active_season(session: AsyncSession) -> models.SeasonState:
    """
    Faol mavsumni oladi yoki mavjud bo'lmasa 6 haftalik 1-mavsumni yaratadi.
    """
    res = await session.execute(
        select(models.SeasonState)
        .where(models.SeasonState.is_active == True)
        .order_by(models.SeasonState.season_number.desc())
    )
    season = res.scalar_one_or_none()
    now = datetime.utcnow()

    if not season:
        season = models.SeasonState(
            season_number=1,
            title="1-Mavsum: Temir Taxt Qadami",
            theme_description="Vesterosda hukmronlik uchun yangi kurash davri boshlandi! Barcha buyuk xonadonlar Temir Taxt sari saflanmoqda.",
            start_date=now,
            end_date=now + timedelta(weeks=DEFAULT_SEASON_WEEKS),
            is_active=True,
            is_concluded=False,
            snapshot_data="{}",
        )
        session.add(season)
        await session.commit()
        await session.refresh(season)
        logger.info(f"Yangi 1-Mavsum muvaffaqiyatli ishga tushirildi (tugash sanasi: {season.end_date})")

    return season


async def get_or_create_player_season_state(
    session: AsyncSession,
    user_id: int,
    season_number: Optional[int] = None
) -> models.SeasonPlayerState:
    """
    O'yinchining joriy mavsumdagi holatini oladi yoki yangisini yaratadi.
    """
    if season_number is None:
        active_season = await get_or_create_active_season(session)
        season_number = active_season.season_number

    res = await session.execute(
        select(models.SeasonPlayerState)
        .where(
            and_(
                models.SeasonPlayerState.season_number == season_number,
                models.SeasonPlayerState.user_id == user_id
            )
        )
    )
    state = res.scalar_one_or_none()

    if not state:
        state = models.SeasonPlayerState(
            season_number=season_number,
            user_id=user_id,
            season_points=0,
            season_xp=0,
            pass_tier=1,
            has_premium_pass=False,
            claimed_free_tiers_json="[]",
            claimed_premium_tiers_json="[]",
            duels_won=0,
            marches_won=0,
            quests_completed=0,
            guild_contribution_points=0,
            active_days_count=1,
            rewards_granted=False,
        )
        session.add(state)
        await session.commit()
        await session.refresh(state)

    return state


# ============================================================
# 2. FAOLIYAT VA SEASON OCHKOLARI (SO) + PASS XP QO'SHISH
# ============================================================

async def record_season_activity(
    session: AsyncSession,
    user_id: int,
    activity_type: str,
    count: int = 1
) -> Tuple[int, int]:
    """
    O'yinchi faoliyati bo'yicha Season Ochkolari (SO) va Season Pass XP qo'shadi.
    Returns: (added_so, added_xp)
    """
    season = await get_or_create_active_season(session)
    state = await get_or_create_player_season_state(session, user_id, season.season_number)

    so_delta = 0
    xp_delta = 0

    if activity_type == "duel_win":
        so_delta = POINTS_WEIGHTS.duel_win * count
        xp_delta = PASS_XP_REWARDS["duel_win"] * count
        state.duels_won = (state.duels_won or 0) + count

    elif activity_type == "march_win":
        so_delta = POINTS_WEIGHTS.march_victory * count
        xp_delta = PASS_XP_REWARDS["march_win"] * count
        state.marches_won = (state.marches_won or 0) + count

    elif activity_type == "daily_quest":
        so_delta = POINTS_WEIGHTS.daily_quest_completed * count
        xp_delta = PASS_XP_REWARDS["daily_quest"] * count
        state.quests_completed = (state.quests_completed or 0) + count

    elif activity_type == "citadel_quiz":
        so_delta = POINTS_WEIGHTS.citadel_quiz_correct * count
        xp_delta = PASS_XP_REWARDS["citadel_quiz"] * count

    elif activity_type == "active_day_streak":
        so_delta = POINTS_WEIGHTS.active_day_streak * count
        xp_delta = PASS_XP_REWARDS["login_streak"] * count
        state.active_days_count = (state.active_days_count or 0) + count

    elif activity_type == "guild_contribution":
        so_delta = (count * POINTS_WEIGHTS.guild_contribution_per_100) // 100
        xp_delta = PASS_XP_REWARDS["guild_deposit"]
        state.guild_contribution_points = (state.guild_contribution_points or 0) + count

    elif activity_type == "castle_held_tick":
        so_delta = POINTS_WEIGHTS.held_castle_per_tick * count
        xp_delta = 5 * count

    elif activity_type == "tournament_win":
        so_delta = POINTS_WEIGHTS.tournament_round_win * count
        xp_delta = 25 * count

    else:
        so_delta = 5 * count
        xp_delta = 10 * count

    state.season_points = (state.season_points or 0) + so_delta
    state.season_xp = (state.season_xp or 0) + xp_delta

    # Tier hisoblash (har 100 XP bitta yangi tier ochadi, maksimal 20)
    calculated_tier = 1 + (state.season_xp // SEASON_PASS_XP_PER_TIER)
    state.pass_tier = min(TOTAL_SEASON_PASS_TIERS, max(1, calculated_tier))
    state.updated_at = datetime.utcnow()

    await session.commit()
    return so_delta, xp_delta


# ============================================================
# 3. SEASON PASS TIER MUKOFOROTLARINI DA'VO QILISH (CLAIM)
# ============================================================

async def claim_season_pass_tier(
    session: AsyncSession,
    user: models.User,
    tier: int,
    track: str = "free"
) -> Tuple[bool, str]:
    """
    Bitta aniq tier mukofotini o'yinchiga berish.
    track: "free" yoki "premium"
    """
    if tier < 1 or tier > TOTAL_SEASON_PASS_TIERS:
        return False, "Bunday tier mavjud emas."

    season = await get_or_create_active_season(session)
    state = await get_or_create_player_season_state(session, user.id, season.season_number)

    if state.pass_tier < tier:
        return False, f"{tier}-Tierga yetib borilmagan (Sizning tiyeringiz: {state.pass_tier})."

    # Claim qilingan tierlar ro'yxatini yuklash
    claimed_free = json.loads(state.claimed_free_tiers_json or "[]")
    claimed_premium = json.loads(state.claimed_premium_tiers_json or "[]")

    if track == "free":
        if tier in claimed_free:
            return False, f"{tier}-Tier Bepul mukofoti allaqachon olingan."
    elif track == "premium":
        if not state.has_premium_pass:
            return False, "Ushbu mukofotni olish uchun Premium Season Pass xarid qilingan bo'lishi kerak."
        if tier in claimed_premium:
            return False, f"{tier}-Tier Premium mukofoti allaqachon olingan."
    else:
        return False, "Noto'g'ri yo'l (track) ko'rsatildi."

    # Mukofot konfiguratsiyasini topish
    tier_cfg = next((t for t in SEASON_PASS_TIERS_CONFIG if t["tier"] == tier), None)
    if not tier_cfg:
        return False, "Tier konfiguratsiyasi topilmadi."

    reward = tier_cfg["free"] if track == "free" else tier_cfg["premium"]
    reward_type = reward.get("type")
    item_id = reward.get("item_id")
    item_name = reward.get("name", "Mukofot")

    # Mukofotni profilga qo'llash
    if reward_type == "title":
        await grant_cosmetic_item(session, user, item_id)
        user.title = item_name

    elif reward_type == "frame":
        await grant_cosmetic_item(session, user, item_id)
        user.avatar_frame = item_id

    elif reward_type in ("cosmetic_castle", "castle_ice", "castle_golden"):
        await grant_cosmetic_item(session, user, item_id)
        user.castle_skin = item_id

    elif reward_type in ("cosmetic_dragon", "dragon_adult_crimson", "dragon_adult_golden"):
        await grant_cosmetic_item(session, user, item_id)
        user.dragon_skin = item_id

    elif reward_type == "effect":
        await grant_cosmetic_item(session, user, item_id)
        user.message_effect = item_id

    elif reward_type == "badge":
        await grant_cosmetic_item(session, user, item_id)

    elif reward_type == "vip_days":
        now = datetime.utcnow()
        current_vip = user.vip_until if (user.vip_until and user.vip_until > now) else now
        days = 14 if "14d" in item_id else 7
        user.vip_until = current_vip + timedelta(days=days)
        user.vip_tier = "noble"

    # Ro'yxatni yangilash
    if track == "free":
        claimed_free.append(tier)
        state.claimed_free_tiers_json = json.dumps(sorted(claimed_free))
    else:
        claimed_premium.append(tier)
        state.claimed_premium_tiers_json = json.dumps(sorted(claimed_premium))

    await session.commit()
    return True, f"Tabriklaymiz! {tier}-Tier mukofoti ({item_name}) qabul qilindi!"


async def claim_all_available_pass_tiers(
    session: AsyncSession,
    user: models.User
) -> Tuple[int, List[str]]:
    """
    O'yinchi erishgan barcha ochiq (lekin olinmagan) tier mukofotlarini bir zumda oladi.
    Returns: (claimed_count, list_of_names)
    """
    season = await get_or_create_active_season(session)
    state = await get_or_create_player_season_state(session, user.id, season.season_number)

    claimed_names = []
    current_tier = state.pass_tier

    for t in range(1, current_tier + 1):
        # Bepul yo'lni tekshirish
        ok, msg = await claim_season_pass_tier(session, user, t, "free")
        if ok:
            claimed_names.append(f"Tier {t} (Bepul)")

        # Premium yo'lni tekshirish (agar pass olingan bo'lsa)
        if state.has_premium_pass:
            ok_p, msg_p = await claim_season_pass_tier(session, user, t, "premium")
            if ok_p:
                claimed_names.append(f"Tier {t} (Premium)")

    return len(claimed_names), claimed_names


# ============================================================
# 4. PREMIUM SEASON PASS FAOLLASHTIRISH (FAQAT ADMIN TASDIQLAGACH)
# ============================================================

async def activate_premium_season_pass_after_approval(
    session: AsyncSession,
    user: models.User,
    telegram_charge_id: Optional[str] = None,
) -> Tuple[bool, str, int]:
    """
    Admin to'lov chekini tasdiqlagandan so'ng o'yinchiga Premium Season Pass berish.
    O'yinchining hozirgi tier'igacha bo'lgan barcha oldingi pullik mukofotlar darhol ochiladi (Retroaktiv).
    """
    season = await get_or_create_active_season(session)
    state = await get_or_create_player_season_state(session, user.id, season.season_number)

    already_active = bool(state.has_premium_pass)

    tx_hash = telegram_charge_id or f"pass_s{season.season_number}_{user.id}_{int(datetime.utcnow().timestamp())}"
    tx = models.PaymentTransaction(
        telegram_id=user.telegram_id,
        user_id=user.id,
        item_id=f"season_pass_s{season.season_number}",
        item_name=f"Premium Season Pass ({season.season_number}-Mavsum)",
        amount_stars=PREMIUM_PASS_PRICE_STARS,
        amount_uzs=PREMIUM_PASS_PRICE_UZS,
        provider="manual_uzs_approved",
        idempotency_key=tx_hash,
        status="completed",
        created_at=datetime.utcnow(),
    )
    session.add(tx)

    state.has_premium_pass = True
    await session.flush()

    auto_claimed_count, _ = await claim_all_available_pass_tiers(session, user)
    bonus_msg = ""
    if auto_claimed_count > 0:
        bonus_msg = f"\n🎁 Bosib o'tilgan {auto_claimed_count} ta tier mukofotlari hisobingizga avtomatik qo'shildi!"
    elif already_active:
        bonus_msg = "\n✨ Premium Season Pass muddati uzaytirildi!"

    return True, (
        f"👑 **PREMIUM SEASON PASS FAOLLASHTIRILDI!**\n\n"
        f"Hurmatli {user.full_name}, {season.season_number}-Mavsum Premium Chiptasi admin tomonidan tasdiqlandi.{bonus_msg}"
    ), auto_claimed_count


async def buy_premium_season_pass(
    session: AsyncSession,
    user: models.User,
    payment_method: str = "manual_uzs",
    telegram_charge_id: Optional[str] = None
) -> Tuple[bool, str]:
    """
    XAVFSIZLIK QOIDASI: Premium Season Pass to'lovsiz yoki cheksiz darhol berilmaydi!
    Faqat to'lov cheki (skrinshot) yuborilib, admin tasdiqlagandan keyin faollashadi.
    """
    return False, (
        "🔒 Premium Season Pass to'lovsiz darhol berilmaydi!\n"
        "Iltimos, ko'rsatilgan karta raqamiga to'lov qilib, to'lov cheki (skrinshot) rasmini yuboring. "
        "Admin tasdiqlagach, Premium Pass va barcha bonus resurslar avtomatik beriladi."
    )


# ============================================================
# 5. MINI APP UCHUN TO'LIQ MAVSUM HUB MA'LUMOTLARI
# ============================================================

async def get_season_hub_data(session: AsyncSession, user_id: int) -> Dict[str, Any]:
    """
    Mini App'dagi Mavsum & Season Pass bo'limi uchun to'liq ma'lumotlarni qaytaradi.
    """
    season = await get_or_create_active_season(session)
    state = await get_or_create_player_season_state(session, user_id, season.season_number)

    now = datetime.utcnow()
    rem_seconds = max(0, int((season.end_date - now).total_seconds()))
    days_left = rem_seconds // 86400
    hours_left = (rem_seconds % 86400) // 3600
    minutes_left = (rem_seconds % 3600) // 60

    claimed_free = json.loads(state.claimed_free_tiers_json or "[]")
    claimed_premium = json.loads(state.claimed_premium_tiers_json or "[]")

    # Joriy tier va XP progressi
    current_tier = state.pass_tier or 1
    xp_in_current_tier = (state.season_xp or 0) % SEASON_PASS_XP_PER_TIER
    if current_tier >= TOTAL_SEASON_PASS_TIERS:
        xp_in_current_tier = SEASON_PASS_XP_PER_TIER

    # 20 ta tierning holati
    tiers_display = []
    for t_cfg in SEASON_PASS_TIERS_CONFIG:
        tier_num = t_cfg["tier"]
        is_reached = current_tier >= tier_num

        # Bepul yo'l holati
        free_status = "locked"
        if is_reached:
            free_status = "claimed" if tier_num in claimed_free else "claimable"

        # Premium yo'l holati
        premium_status = "locked"
        if is_reached:
            if not state.has_premium_pass:
                premium_status = "requires_premium"
            else:
                premium_status = "claimed" if tier_num in claimed_premium else "claimable"

        tiers_display.append({
            "tier": tier_num,
            "xp_required": t_cfg["xp_required"],
            "is_reached": is_reached,
            "free": {
                **t_cfg["free"],
                "status": free_status,
            },
            "premium": {
                **t_cfg["premium"],
                "status": premium_status,
            }
        })

    # O'yinchining mavsumdagi reyting o'rni
    rank_res = await session.execute(
        select(func.count(models.SeasonPlayerState.id))
        .where(
            and_(
                models.SeasonPlayerState.season_number == season.season_number,
                models.SeasonPlayerState.season_points > state.season_points
            )
        )
    )
    my_rank = (rank_res.scalar() or 0) + 1

    # TOP 10 Mavsum yetakchilari (SO bo'yicha)
    top_leaders_res = await session.execute(
        select(models.SeasonPlayerState, models.User)
        .join(models.User, models.SeasonPlayerState.user_id == models.User.id)
        .where(models.SeasonPlayerState.season_number == season.season_number)
        .order_by(models.SeasonPlayerState.season_points.desc())
        .limit(10)
    )
    leaderboard = []
    for rank_idx, (st, usr) in enumerate(top_leaders_res.all(), start=1):
        leaderboard.append({
            "rank": rank_idx,
            "user_id": usr.id,
            "name": usr.full_name,
            "title": usr.title or "Lord",
            "house_id": usr.house_id,
            "season_points": st.season_points,
            "pass_tier": st.pass_tier,
            "has_premium": st.has_premium_pass,
        })

    # O'tgan mavsumlar arxivi (Hall of Fame)
    hof_res = await session.execute(
        select(models.HallOfFame)
        .where(
            models.HallOfFame.winner_house_name != "The White Walkers",
            models.HallOfFame.king_name != "Lord Alpha (Champion)",
        )
        .order_by(models.HallOfFame.season_number.desc())
        .limit(5)
    )
    hall_of_fame = []
    for h in hof_res.scalars().all():
        hall_of_fame.append({
            "season_number": h.season_number,
            "winner_house_name": h.winner_house_name,
            "king_name": h.king_name or "Noma'lum",
            "top_warrior_name": h.top_warrior_name or "Noma'lum",
            "top_so_player_name": h.top_so_player_name or h.king_name or "Noma'lum",
            "top_so_points": h.top_so_points or 0,
            "top_guild_name": h.top_guild_name or "Mavjud emas",
            "concluded_at": h.concluded_at.strftime("%Y-%m-%d") if h.concluded_at else "",
        })

    from config import PREMIUM_PASS_CONFIG
    from database import crud
    payment_requisites = await crud.get_payment_settings(session)
    pending_req = await crud.get_user_pending_donation_request(session, user_id=user_id)

    return {
        "season": {
            "season_number": season.season_number,
            "title": season.title or f"{season.season_number}-Mavsum",
            "theme_description": season.theme_description or "",
            "is_active": season.is_active,
            "days_left": days_left,
            "hours_left": hours_left,
            "minutes_left": minutes_left,
            "start_date": season.start_date.isoformat() if season.start_date else None,
            "end_date": season.end_date.isoformat() if season.end_date else None,
        },
        "player_state": {
            "season_points": state.season_points or 0,
            "season_xp": state.season_xp or 0,
            "pass_tier": current_tier,
            "xp_in_current_tier": xp_in_current_tier,
            "xp_needed_per_tier": SEASON_PASS_XP_PER_TIER,
            "has_premium_pass": state.has_premium_pass or False,
            "my_rank": my_rank,
            "duels_won": state.duels_won or 0,
            "marches_won": state.marches_won or 0,
            "quests_completed": state.quests_completed or 0,
            "active_days_count": state.active_days_count or 0,
        },
        "tiers": tiers_display,
        "leaderboard": leaderboard,
        "hall_of_fame": hall_of_fame,
        "pricing": {
            "stars": PREMIUM_PASS_PRICE_STARS,
            "uzs": PREMIUM_PASS_PRICE_UZS,
            "price_label": PREMIUM_PASS_CONFIG.get("price_label", "25,000 so'm"),
        },
        "premium_pass_config": PREMIUM_PASS_CONFIG,
        "payment_requisites": payment_requisites,
        "pending_request": {
            "id": pending_req.id,
            "package": pending_req.tier_id,
            "tier_name": pending_req.tier_name,
            "amount": pending_req.price_uzs,
            "status": pending_req.status,
            "created_at": pending_req.created_at.isoformat() if pending_req.created_at else None,
        } if pending_req else None,
    }


# ============================================================
# 6. MAVSUMNI YAKUNLASH, SNAPSHOT, MUKOFOTLAR VA YUMSHOQ RESET
# ============================================================

async def conclude_and_rollover_season(
    session: AsyncSession,
    bot_app=None,
    force: bool = False
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Mavsumni yakunlash (Conclude Season), Natijalarni muzlatish (Snapshot),
    Idempotent mukofotlarni taqsimlash va yangi mavsum boshlash (crud.admin_conclude_and_restart_season bilan 100% bir xil).
    """
    from database import crud
    return await crud.admin_conclude_and_restart_season(session, bot_app=bot_app)


async def admin_update_season_config(
    session: AsyncSession,
    title: Optional[str] = None,
    theme_description: Optional[str] = None,
    extend_days: Optional[int] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Administrator tomonidan mavsum mavzusi, sarlavhasi va muddatini o'zgartirish.
    """
    season = await get_or_create_active_season(session)

    if title:
        season.title = title
    if theme_description:
        season.theme_description = theme_description
    if extend_days and extend_days != 0:
        season.end_date = season.end_date + timedelta(days=extend_days)

    await session.commit()
    await session.refresh(season)

    return True, f"{season.season_number}-Mavsum sozlamalari muvaffaqiyatli yangilandi.", {
        "season_number": season.season_number,
        "title": season.title,
        "end_date": season.end_date.isoformat(),
    }
