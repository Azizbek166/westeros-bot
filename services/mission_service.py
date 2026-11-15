"""
Haftalik va Ajdaho Missiyalari Servisi.
- Davr (period_key): Dushanba sanasi (UTC+5, check_and_reset_daily_limits bilan bir xil).
- Progress: Duel, BattleReport, TradeCaravan, SpyMission, DragonDuel jadvallaridan + mission_progress jadvalidan olinadi.
- Mukofot olish: bitta tranzaksiyada mission_claims (UNIQUE) orqali himoyalangan.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import models, crud
from database.db import AsyncSessionLocal
from data.missions_data import (
    WEEKLY_MISSIONS,
    WEEKLY_ALL_BONUS,
    MISSIONS_BY_CODE,
    EVENT_TO_MISSION,
)

logger = logging.getLogger(__name__)


def get_current_week_bounds() -> Tuple[str, datetime, datetime, str]:
    """
    UTC+5 bo'yicha joriy haftaning Dushanba 00:00 dan keyingi Dushanba 00:00 gacha oralig'i.
    Qaytaradi: (period_key 'YYYY-MM-DD', week_start_utc, week_end_utc, remaining_str)
    """
    now_utc = datetime.utcnow()
    now_local = now_utc + timedelta(hours=5)
    monday_local = (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    next_monday_local = monday_local + timedelta(days=7)

    period_key = monday_local.strftime("%Y-%m-%d")
    week_start_utc = monday_local - timedelta(hours=5)
    week_end_utc = next_monday_local - timedelta(hours=5)

    rem = next_monday_local - now_local
    days = rem.days
    hours = rem.seconds // 3600
    mins = (rem.seconds % 3600) // 60
    rem_str = f"{days} kun {hours} soat {mins} daq"
    return period_key, week_start_utc, week_end_utc, rem_str


async def track_event(
    user_id: int,
    event_type: str,
    amount: int = 1,
    session: Optional[AsyncSession] = None,
) -> None:
    """
    Jadvaldan hisoblab bo'lmaydigan missiya hodisalarini (boqish, mashq, yashirin missiya, yollash, viktorina) yozish.
    try/except bilan himoyalangan: xato bo'lsa ham asosiy o'yin funksiyasi to'xtamaydi.
    """
    try:
        mission_code = EVENT_TO_MISSION.get(event_type)
        if not mission_code or amount <= 0 or not user_id:
            return

        period_key, _, _, _ = get_current_week_bounds()

        async def _apply(s: AsyncSession) -> None:
            user = await crud.get_user_any(s, user_id, load_relations=False)
            if not user:
                return
            res = await s.execute(
                select(models.MissionProgress).where(
                    models.MissionProgress.user_id == user.id,
                    models.MissionProgress.mission_code == mission_code,
                    models.MissionProgress.period_key == period_key,
                )
            )
            row = res.scalar_one_or_none()
            if row:
                row.progress = (row.progress or 0) + int(amount)
            else:
                row = models.MissionProgress(
                    user_id=user.id,
                    mission_code=mission_code,
                    period_key=period_key,
                    progress=int(amount),
                )
                s.add(row)

        if session is not None:
            async with session.begin_nested():
                await _apply(session)
        else:
            async with AsyncSessionLocal() as new_sess:
                await _apply(new_sess)
                await new_sess.commit()
    except Exception as e:
        logger.warning(f"mission_service.track_event xatosi ({event_type}, user={user_id}): {e}")


async def _compute_mission_progress_map(
    session: AsyncSession,
    user_db_id: int,
    period_key: str,
    week_start_utc: datetime,
) -> Dict[str, int]:
    """Barcha haftalik va ajdaho missiyalari uchun joriy progressni hisoblash."""
    progress: Dict[str, int] = {}

    # 1. Duel g'alabalari
    duel_cnt = (
        await session.execute(
            select(func.count(models.Duel.id)).where(
                models.Duel.winner_id == user_db_id,
                models.Duel.status == "completed",
                models.Duel.created_at >= week_start_utc,
            )
        )
    ).scalar() or 0
    progress["wk_duel"] = int(duel_cnt)

    # 2. Karvon yetkazish
    caravan_cnt = (
        await session.execute(
            select(func.count(models.TradeCaravan.id)).where(
                models.TradeCaravan.owner_user_id == user_db_id,
                models.TradeCaravan.status == "arrived",
                models.TradeCaravan.arrival_time >= week_start_utc,
            )
        )
    ).scalar() or 0
    progress["wk_caravan"] = int(caravan_cnt)

    # 3. Josuslik topshiriqlari
    spy_cnt = (
        await session.execute(
            select(func.count(models.SpyMission.id)).where(
                models.SpyMission.user_id == user_db_id,
                models.SpyMission.status == "success",
                models.SpyMission.created_at >= week_start_utc,
            )
        )
    ).scalar() or 0
    progress["wk_spy"] = int(spy_cnt)

    # 4. Harbiy yurish g'alabalari
    march_cnt = (
        await session.execute(
            select(func.count(models.BattleReport.id)).where(
                models.BattleReport.attacker_user_id == user_db_id,
                models.BattleReport.result == "attacker_won",
                models.BattleReport.timestamp >= week_start_utc,
            )
        )
    ).scalar() or 0
    progress["wk_march"] = int(march_cnt)

    # 5. Ajdar dueli g'alabalari
    dd_cnt = (
        await session.execute(
            select(func.count(models.DragonDuel.id)).where(
                models.DragonDuel.winner_user_id == user_db_id,
                models.DragonDuel.status == "completed",
                models.DragonDuel.created_at >= week_start_utc,
            )
        )
    ).scalar() or 0
    progress["dr_duel"] = int(dd_cnt)

    # 6. Event-asosidagi progresslar (mission_progress jadvalidan)
    ev_rows = (
        await session.execute(
            select(models.MissionProgress).where(
                models.MissionProgress.user_id == user_db_id,
                models.MissionProgress.period_key == period_key,
            )
        )
    ).scalars().all()
    for r in ev_rows:
        progress[r.mission_code] = int(r.progress or 0)

    return progress


async def get_missions_overview(session: AsyncSession, telegram_or_user_id: int) -> Dict[str, Any]:
    """Foydalanuvchining haftalik va ajdaho missiyalari ro'yxati hamda holati."""
    user = await crud.get_user_any(session, telegram_or_user_id, load_relations=False)
    period_key, week_start_utc, _, rem_str = get_current_week_bounds()
    if not user:
        return {"found": False, "period_key": period_key, "remaining_str": rem_str, "missions": [], "bonus": None}

    prog_map = await _compute_mission_progress_map(session, user.id, period_key, week_start_utc)

    claims_rows = (
        await session.execute(
            select(models.MissionClaim.mission_code).where(
                models.MissionClaim.user_id == user.id,
                models.MissionClaim.period_key == period_key,
            )
        )
    ).scalars().all()
    claimed_set = set(claims_rows)

    items: List[Dict[str, Any]] = []
    completed_count = 0
    for m in WEEKLY_MISSIONS:
        code = m["code"]
        cur = min(m["target"], prog_map.get(code, 0))
        is_done = cur >= m["target"]
        if is_done:
            completed_count += 1
        is_claimed = code in claimed_set
        status = "claimed" if is_claimed else ("claimable" if is_done else "in_progress")
        items.append({
            **m,
            "current": cur,
            "status": status,
        })

    bonus_claimed = WEEKLY_ALL_BONUS["code"] in claimed_set
    bonus_done = completed_count >= len(WEEKLY_MISSIONS)
    bonus_status = "claimed" if bonus_claimed else ("claimable" if bonus_done else "in_progress")
    bonus_item = {
        **WEEKLY_ALL_BONUS,
        "current": completed_count,
        "status": bonus_status,
    }

    return {
        "found": True,
        "user_id": user.id,
        "period_key": period_key,
        "remaining_str": rem_str,
        "missions": items,
        "bonus": bonus_item,
    }


async def claim_mission_reward(
    session: AsyncSession,
    telegram_or_user_id: int,
    mission_code: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Missiya mukofotini atomik tarzda berish (bir davrda faqat 1 marta)."""
    cfg = MISSIONS_BY_CODE.get(mission_code)
    if not cfg:
        return False, "❌ Noma'lum missiya kodi.", {}

    user = await crud.get_user_any(session, telegram_or_user_id, load_relations=False)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi.", {}

    period_key, week_start_utc, _, _ = get_current_week_bounds()

    # Allaqachon olinganmi?
    existing_claim = (
        await session.execute(
            select(models.MissionClaim).where(
                models.MissionClaim.user_id == user.id,
                models.MissionClaim.mission_code == mission_code,
                models.MissionClaim.period_key == period_key,
            )
        )
    ).scalar_one_or_none()
    if existing_claim:
        return False, "✅ Ushbu missiya mukofoti bu hafta allaqachon olingan!", {}

    # Progress tekshirish
    prog_map = await _compute_mission_progress_map(session, user.id, period_key, week_start_utc)
    if mission_code == WEEKLY_ALL_BONUS["code"]:
        done_cnt = sum(1 for m in WEEKLY_MISSIONS if prog_map.get(m["code"], 0) >= m["target"])
        if done_cnt < len(WEEKLY_MISSIONS):
            return False, f"⏳ Barcha missiyalar bajarilmagan ({done_cnt}/{len(WEEKLY_MISSIONS)}).", {}
    else:
        cur = prog_map.get(mission_code, 0)
        if cur < cfg["target"]:
            return False, f"⏳ Missiya hali bajarilmagan ({cur}/{cfg['target']}).", {}

    # Claim yozish + mukofot berish (bitta tranzaksiya)
    claim_row = models.MissionClaim(
        user_id=user.id,
        mission_code=mission_code,
        period_key=period_key,
        claimed_at=datetime.utcnow(),
    )
    session.add(claim_row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return False, "✅ Ushbu missiya mukofoti allaqachon olingan!", {}

    gold = int(cfg.get("gold", 0))
    food = int(cfg.get("food", 0))
    iron = int(cfg.get("iron", 0))
    xp = int(cfg.get("xp", 0))
    prestige = int(cfg.get("prestige", 0))

    user.gold = (user.gold or 0) + gold
    user.food = (user.food or 0) + food
    user.iron = (user.iron or 0) + iron
    user.xp = (user.xp or 0) + xp
    user.prestige = (user.prestige or 0) + prestige
    crud.track_user_gold_gain(user, gold)
    crud.track_user_prestige_gain(user, prestige)

    await session.commit()

    return True, f"🎉 {cfg['title']} mukofoti olindi!", {
        "gold": gold,
        "food": food,
        "iron": iron,
        "xp": xp,
        "prestige": prestige,
    }
