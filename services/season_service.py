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
# 4. PREMIUM SEASON PASS SOTIB OLISH (RETROAKTIV OCHILISH)
# ============================================================

async def buy_premium_season_pass(
    session: AsyncSession,
    user: models.User,
    payment_method: str = "stars",
    telegram_charge_id: Optional[str] = None
) -> Tuple[bool, str]:
    """
    O'yinchiga Premium Season Pass berish.
    O'yinchining hozirgi tier'igacha bo'lgan barcha oldingi pullik mukofotlar darhol ochiladi (Retroaktiv).
    """
    season = await get_or_create_active_season(session)
    state = await get_or_create_player_season_state(session, user.id, season.season_number)

    if state.has_premium_pass:
        return False, "Sizda ushbu mavsum uchun Premium Pass allaqachon faollashtirilgan!"

    # To'lov jurnaliga yozish
    tx_hash = telegram_charge_id or f"pass_s{season.season_number}_{user.id}_{int(datetime.utcnow().timestamp())}"
    tx = models.PaymentTransaction(
        telegram_id=user.telegram_id,
        user_id=user.id,
        item_id=f"season_pass_s{season.season_number}",
        item_name=f"Premium Season Pass ({season.season_number}-Mavsum)",
        amount_stars=PREMIUM_PASS_PRICE_STARS,
        amount_uzs=PREMIUM_PASS_PRICE_UZS,
        provider="telegram_stars" if payment_method == "stars" else "manual_uzs",
        idempotency_key=tx_hash,
        status="completed",
        created_at=datetime.utcnow(),
    )
    session.add(tx)

    # Passni yoqish
    state.has_premium_pass = True
    await session.commit()

    # O'yinchining yetib kelgan barcha o'tgan tier'larini avtomatik claim qilish (retroaktiv)
    auto_claimed_count, auto_items = await claim_all_available_pass_tiers(session, user)

    bonus_msg = ""
    if auto_claimed_count > 0:
        bonus_msg = f"\n\n🎁 Siz avval bosib o'tgan {auto_claimed_count} ta tier mukofotlari hisobingizga avtomatik qo'shildi!"

    return True, (
        f"👑 **PREMIUM SEASON PASS FAQLLASHTIRILDI!**\n\n"
        f"Hurmatli {user.full_name}, {season.season_number}-Mavsum Premium Chiptasi muvaffaqiyatli rasmiylashtirildi.{bonus_msg}\n"
        f"Barcha eksklyuziv ajdaho terilari, saroylar va unvonlar maydoni siz uchun ochiq!"
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
        select(models.HallOfFame).order_by(models.HallOfFame.season_number.desc()).limit(5)
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
        }
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
    Idempotent mukofotlarni taqsimlash va Yumshoq Reset (Soft-Reset) o'tkazish.
    """
    season = await get_or_create_active_season(session)
    now = datetime.utcnow()

    if not force and now < season.end_date:
        return False, f"Mavsum hali yakunlanmagan. Qolgan vaqt: {season.end_date - now}", {}

    if season.is_concluded:
        return False, "Ushbu mavsum allaqachon yakunlangan va muzlatilgan.", {}

    logger.info(f"{season.season_number}-Mavsum yakunlanmoqda (force={force}). Snapshot olinmoqda...")

    # 1. SNAPSHOT: Barcha o'yinchilarni Season Ochkolari (SO) bo'yicha saralash
    res_players = await session.execute(
        select(models.SeasonPlayerState, models.User)
        .join(models.User, models.SeasonPlayerState.user_id == models.User.id)
        .where(models.SeasonPlayerState.season_number == season.season_number)
        .order_by(models.SeasonPlayerState.season_points.desc())
    )
    all_players = res_players.all()

    # G'oliblar snapshot ro'yxatini shakllantirish
    snapshot_top_list = []
    top_1_player = None
    top_warrior_player = None
    highest_prestige = -1

    for rank_idx, (st, usr) in enumerate(all_players, start=1):
        st.final_rank = rank_idx
        if rank_idx == 1:
            top_1_player = (st, usr)

        if (usr.prestige or 0) > highest_prestige:
            highest_prestige = usr.prestige or 0
            top_warrior_player = usr

        if rank_idx <= 100:
            snapshot_top_list.append({
                "rank": rank_idx,
                "user_id": usr.id,
                "telegram_id": usr.telegram_id,
                "name": usr.full_name,
                "house_id": usr.house_id,
                "season_points": st.season_points,
                "pass_tier": st.pass_tier,
                "has_premium": st.has_premium_pass,
            })

    # G'olib Xonadonni aniqlash (King's Landing egasi yoki eng yuqori nufuzli xonadon)
    kl_res = await session.execute(select(models.Territory).where(models.Territory.code == "kings_landing"))
    kl_terr = kl_res.scalar_one_or_none()
    winner_house = None
    if kl_terr and kl_terr.owner_house_id:
        winner_house = await session.get(models.House, kl_terr.owner_house_id)
    if not winner_house:
        top_h = await session.execute(select(models.House).order_by(models.House.prestige.desc()).limit(1))
        winner_house = top_h.scalar_one_or_none()

    winner_house_name = winner_house.name if winner_house else "Vesteros Ittifoqi"
    winner_house_id = winner_house.id if winner_house else None

    # Eng faol Gildiyani aniqlash
    top_g_res = await session.execute(select(models.Guild).order_by(models.Guild.level.desc(), models.Guild.treasury_gold.desc()).limit(1))
    top_guild = top_g_res.scalar_one_or_none()
    top_guild_name = top_guild.name if top_guild else None

    king_name = top_1_player[1].full_name if top_1_player else "Noma'lum Hukmdor"
    king_uid = top_1_player[1].id if top_1_player else None
    top_so_pts = top_1_player[0].season_points if top_1_player else 0

    top_w_name = top_warrior_player.full_name if top_warrior_player else "Noma'lum Jangchi"
    top_w_prestige = highest_prestige if highest_prestige > 0 else 0

    # 2. MUKOFOTLARNI IDEMPOTENT TARZDA TOPSHIRISH
    # Har bir toifa uchun SeasonRewardClaim yoziladi, takroriy berishning oldi olinadi
    rewards_granted_count = 0

    async def _safe_grant_reward(user_to_reward: models.User, r_type: str, details: Dict[str, Any]):
        nonlocal rewards_granted_count
        chk = await session.execute(
            select(models.SeasonRewardClaim).where(
                and_(
                    models.SeasonRewardClaim.season_number == season.season_number,
                    models.SeasonRewardClaim.user_id == user_to_reward.id,
                    models.SeasonRewardClaim.reward_type == r_type
                )
            )
        )
        if chk.scalar_one_or_none():
            return  # Allaqachon berilgan!

        claim_rec = models.SeasonRewardClaim(
            season_number=season.season_number,
            user_id=user_to_reward.id,
            reward_type=r_type,
            reward_details_json=json.dumps(details),
            granted_at=datetime.utcnow()
        )
        session.add(claim_rec)

        # Mukofotlarni qo'llash
        if "title" in details:
            await grant_cosmetic_item(session, user_to_reward, details["title"])
            user_to_reward.title = details["title"]
        if "frame" in details:
            await grant_cosmetic_item(session, user_to_reward, details["frame"])
            user_to_reward.avatar_frame = details["frame"]
        if "castle_skin" in details:
            await grant_cosmetic_item(session, user_to_reward, details["castle_skin"])
            user_to_reward.castle_skin = details["castle_skin"]
        if "dragon_skin" in details:
            await grant_cosmetic_item(session, user_to_reward, details["dragon_skin"])
            user_to_reward.dragon_skin = details["dragon_skin"]
        if "gold_starter" in details:
            user_to_reward.gold = (user_to_reward.gold or 0) + details["gold_starter"]
        if "vip_days" in details and details["vip_days"] > 0:
            cur_vip = user_to_reward.vip_until if (user_to_reward.vip_until and user_to_reward.vip_until > now) else now
            user_to_reward.vip_until = cur_vip + timedelta(days=details["vip_days"])
            user_to_reward.vip_tier = "noble"

        rewards_granted_count += 1

    # Toifalarga qarab taqsimlash
    for rank_pos, (st, usr) in enumerate(all_players, start=1):
        # 1. Avval Season Pass bo'yicha yetib kelgan, lekin olinmagan mukofotlarni avtomatik hisobga qo'shish
        await claim_all_available_pass_tiers(session, usr)
        st.rewards_granted = True

        # 2. Keyin yakuniy mavsum reytingi mukofotlarini berish (Chempion unvoni eng ustuvor bo'lishi uchun)
        if rank_pos == 1:
            await _safe_grant_reward(usr, "season_top1", SEASON_END_RANK_REWARDS["rank_1"])
        elif rank_pos in (2, 3):
            await _safe_grant_reward(usr, "season_top3", SEASON_END_RANK_REWARDS["top_3"])
        elif 4 <= rank_pos <= 10:
            await _safe_grant_reward(usr, "season_top10", SEASON_END_RANK_REWARDS["top_10"])
        elif 11 <= rank_pos <= 100:
            await _safe_grant_reward(usr, "season_top100", SEASON_END_RANK_REWARDS["top_100"])
        elif (st.season_points or 0) > 0:
            # Boshqa barcha qatnashganlar uchun
            await _safe_grant_reward(usr, "season_participant", SEASON_END_RANK_REWARDS["participant"])

    # 3. SHON-SHARAF ZALIGA (HALL OF FAME) YOZISH
    hof_entry = models.HallOfFame(
        season_number=season.season_number,
        winner_house_id=winner_house_id,
        winner_house_name=winner_house_name,
        king_user_id=king_uid,
        king_name=king_name,
        top_warrior_name=top_w_name,
        top_warrior_prestige=top_w_prestige,
        top_so_user_id=king_uid,
        top_so_player_name=king_name,
        top_so_points=top_so_pts,
        top_guild_name=top_guild_name,
        snapshot_json=json.dumps(snapshot_top_list[:20]),
        concluded_at=now,
    )
    session.add(hof_entry)

    # 4. MAVSUM HOLATINI MUZLATISH
    season.is_active = False
    season.is_concluded = True
    season.snapshot_data = json.dumps({
        "total_participants": len(all_players),
        "winner_house": winner_house_name,
        "king_name": king_name,
        "top_so_points": top_so_pts,
        "concluded_at": now.isoformat(),
        "top_10": snapshot_top_list[:10],
    })

    # 5. YUMSHOQ RESET (SOFT-RESET) NI AMALGA OSHIRISH
    # Qoidalar:
    # - Resurslar foizda saqlanadi (Gold max 15k, Food max 30k, Iron max 10k)
    # - Qal'alar dastlabki holatga qaytariladi, darajasi (level - 1, min 1)
    # - Armiyalar dastlabki garnizonga qaytadi
    # - Profil, kosmetika, unvonlar va qahramonlar butunlay saqlanadi!
    all_users = await session.execute(select(models.User))
    for u in all_users.scalars().all():
        u.gold = min(SOFT_RESET.gold_hard_cap, max(0, int((u.gold or 0) * SOFT_RESET.gold_preserve_pct)))
        u.food = min(SOFT_RESET.food_hard_cap, max(0, int((u.food or 0) * SOFT_RESET.food_preserve_pct)))
        u.iron = min(SOFT_RESET.iron_hard_cap, max(0, int((u.iron or 0) * SOFT_RESET.iron_preserve_pct)))

    # Armiyalarni boshlang'ich garnizonga tushirish
    all_armies = await session.execute(select(models.Army))
    for a in all_armies.scalars().all():
        a.infantry = SOFT_RESET.base_infantry
        a.archers = SOFT_RESET.base_archers
        a.cavalry = SOFT_RESET.base_cavalry
        a.spearmen = SOFT_RESET.base_spearmen
        a.special_troops = 0
        a.catapults = 0
        a.siege_towers = 0

    # Qal'alar (Territories) ni dastlabki xonadonlariga qaytarish
    from data.map_data import TERRITORIES_DATA
    all_terrs = await session.execute(select(models.Territory))
    for t in all_terrs.scalars().all():
        init_info = TERRITORIES_DATA.get(t.code, {})
        t.owner_house_id = init_info.get("initial_owner_id", t.owner_house_id)
        t.castle_level = max(1, (getattr(t, "castle_level", 1) or 1) - SOFT_RESET.castle_level_reduction)
        t.conquered_by_user_id = None
        t.defense = init_info.get("defense", 500)
        t.wildfire_count = 0
        t.gates_compromised_until = None

    # 6. YANGI MAVSUMNI YARATISH (N + 1)
    next_season_num = season.season_number + 1
    next_season = models.SeasonState(
        season_number=next_season_num,
        title=f"{next_season_num}-Mavsum: Ajdarlar Raqsi",
        theme_description="Yangi mavsum boshlandi! Qal'alar qayta taqsimlandi, armiyalar yangi shon-sharaf uchun saf tortmoqda.",
        start_date=now,
        end_date=now + timedelta(weeks=DEFAULT_SEASON_WEEKS),
        is_active=True,
        is_concluded=False,
        snapshot_data="{}",
    )
    session.add(next_season)

    await session.commit()
    logger.info(f"Yangi {next_season_num}-Mavsum muvaffaqiyatli boshlandi! Soft-Reset yakunlandi.")

    announcement = (
        f"👑🏆 **VESTEROSDA YANGI DAVR: {season.season_number}-MAVSUM YAKUNLANDI!** 🏆👑\n\n"
        f"🏛️ **TEMIR TAXT G'OLIBI:** **{winner_house_name}** xonadoni!\n"
        f"👑 **Mavsum Chempioni (Eng ko'p SO):** **{king_name}** ({top_so_pts:,} ochko)\n"
        f"⚔️ **Mavsumning Oliy Jangchisi:** **{top_w_name}** ({top_w_prestige:,} nufuz)\n\n"
        f"📜 Barcha g'oliblar nomi abadiy **Shon-sharaf Zali (Hall of Fame)** solnomalariga muhrlandi!\n"
        f"🎁 Mavsum Passi bo'yicha erishilgan barcha olinmagan mukofotlar hisobingizga topshirildi.\n\n"
        f"🌟 **{next_season_num}-MAVSUM RASMAN BOSHLANDI!** (6 haftalik yangi shonli davr)\n"
        f"Qal'alar yangilandi, Yumshoq Reset (Soft-Reset) amalga oshirildi. Yetti Qirollik yangi qahramonlarni kutmoqda!"
    )

    if bot_app:
        from core.notifier import notify_house_group
        h_res = await session.execute(select(models.House).where(models.House.group_chat_id.isnot(None)))
        for h in h_res.scalars().all():
            try:
                await notify_house_group(bot_app, h.id, announcement)
            except Exception:
                pass

    summary = {
        "concluded_season_number": season.season_number,
        "next_season_number": next_season_num,
        "king_name": king_name,
        "winner_house": winner_house_name,
        "total_participants": len(all_players),
        "rewards_granted_count": rewards_granted_count,
    }
    return True, announcement, summary


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
