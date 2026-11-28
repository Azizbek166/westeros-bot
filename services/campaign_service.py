"""
Campaign Mission & Pacing Service (Vaqt limitli kampaniya tizimi — 0 Pay-To-Win).
- Barcha vaqtlar bazada UTC (naive UTC) da saqlanadi, ko'rsatish va yarim tun reseti Asia/Tashkent (UTC+5) da.
- Cooldown va Calendar ochilish rejimlari.
- Kunlik urinishlar limiti (Toshkent yarim tunida yangilanadi) va variantli missiyalarda noto'g'ri tanlovdan keyin qisqa kutish.
- Double-click va eski tugma himoyasi (asyncio.Lock + DB server-side tekshiruv).
- Qayta ishga tushganda ham saqlanadigan unlock_at va qayta yuborilmaydigan bildirishnomalar.
"""
import asyncio
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import models

logger = logging.getLogger(__name__)

# O'zbekiston (Asia/Tashkent) yil davomida qat'iy UTC+5 (DST yo'q)
TASHKENT_TZ = timezone(timedelta(hours=5))

# Per-(user_id, campaign_id) concurrency locks (double-click / multi-device protection)
_PROGRESS_LOCKS: Dict[Tuple[int, int], asyncio.Lock] = {}


def _get_progress_lock(user_id: int, campaign_id: int) -> asyncio.Lock:
    key = (int(user_id), int(campaign_id))
    lock = _PROGRESS_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _PROGRESS_LOCKS[key] = lock
    return lock


def utc_now() -> datetime:
    """Joriy UTC vaqtni naive datetime sifatida qaytaradi (DB TIMESTAMP ustunlariga mos)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_tashkent(dt_utc: datetime) -> datetime:
    """Naive UTC datetime -> Asia/Tashkent aware datetime."""
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ)


def tashkent_today_str(now_utc: Optional[datetime] = None) -> str:
    """Asia/Tashkent bo'yicha YYYY-MM-DD sana."""
    now_u = now_utc or utc_now()
    return to_tashkent(now_u).strftime("%Y-%m-%d")


def seconds_until_tashkent_midnight(now_utc: Optional[datetime] = None) -> int:
    """Keyingi Asia/Tashkent yarim tunigacha (00:00) qolgan soniyalar."""
    now_u = now_utc or utc_now()
    now_t = to_tashkent(now_u)
    next_mid = (now_t + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((next_mid - now_t).total_seconds()))


def format_tashkent_dt(dt_utc: Optional[datetime]) -> str:
    if not dt_utc:
        return "Belgilanmagan"
    return to_tashkent(dt_utc).strftime("%Y-%m-%d %H:%M") + " (Toshkent)"


def parse_tashkent_dt(raw: str) -> Optional[datetime]:
    """
    Admin kiritgan 'YYYY-MM-DD HH:MM' yoki 'YYYY-MM-DD' (Asia/Tashkent) matnini
    bazada saqlash uchun naive UTC datetime ga aylantiradi.
    """
    text = (raw or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt_local = datetime.strptime(text, fmt).replace(tzinfo=TASHKENT_TZ)
            return dt_local.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def format_duration_uz(seconds: int) -> str:
    """Soniyalarni tushunarli o'zbekcha ko'rinishga o'tkazadi (masalan: '5 soat 20 daqiqa')."""
    secs = max(0, int(seconds))
    if secs < 60:
        return "1 daqiqadan kam"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days} kun")
    if hours:
        parts.append(f"{hours} soat")
    if minutes and not days:
        parts.append(f"{minutes} daqiqa")
    elif minutes and days and not hours:
        parts.append(f"{minutes} daqiqa")
    return " ".join(parts) if parts else "1 daqiqadan kam"


# ============================================================
# PACING HELPERS
# ============================================================

def get_mission_cooldown_hours(campaign: models.Campaign, mission: models.CampaignMission) -> int:
    if mission.cooldown_hours_override is not None:
        return max(0, int(mission.cooldown_hours_override))
    return max(0, int(campaign.default_cooldown_hours if campaign.default_cooldown_hours is not None else 24))


def get_mission_daily_attempts(campaign: models.Campaign, mission: models.CampaignMission) -> int:
    if mission.daily_attempts_override is not None:
        return max(1, int(mission.daily_attempts_override))
    return max(1, int(campaign.default_daily_attempts if campaign.default_daily_attempts is not None else 3))


def get_mission_choice_cooldown_minutes(campaign: models.Campaign, mission: models.CampaignMission) -> int:
    if mission.choice_cooldown_minutes_override is not None:
        return max(0, int(mission.choice_cooldown_minutes_override))
    return max(0, int(campaign.default_choice_cooldown_minutes if campaign.default_choice_cooldown_minutes is not None else 30))


def calculate_campaign_min_duration_hours(
    campaign: models.Campaign,
    missions: List[models.CampaignMission],
) -> int:
    """
    Kampaniyaning minimal davomiyligi (soatlarda):
    - Cooldown rejimida: 2-missiyadan oxirgi missiyagacha bo'lgan kutish soatlari yig'indisi.
    - Calendar rejimida: birinchi va oxirgi missiya sanalari orasidagi farq (soatlarda).
    """
    if not missions or len(missions) <= 1:
        return 0
    ordered = sorted(missions, key=lambda m: m.order_index)
    if (campaign.unlock_mode or "cooldown") == "calendar":
        dates = [m.calendar_unlock_at for m in ordered if m.calendar_unlock_at is not None]
        if len(dates) >= 2:
            span = (max(dates) - min(dates)).total_seconds()
            return max(0, int(math.ceil(span / 3600.0)))
        return 0

    total_h = 0
    for m in ordered[1:]:
        total_h += get_mission_cooldown_hours(campaign, m)
    return total_h


def format_campaign_min_duration(
    campaign: models.Campaign,
    missions: List[models.CampaignMission],
) -> str:
    cnt = len(missions)
    if cnt == 0:
        return "0 missiya (0 kun)"
    min_h = calculate_campaign_min_duration_hours(campaign, missions)
    if min_h <= 0:
        return f"{cnt} missiya (kutishsiz)"
    days = min_h / 24.0
    if days >= 1 and abs(days - round(days)) < 1e-6:
        return f"{cnt} missiya — kamida {int(round(days))} kun ({min_h} soat)"
    return f"{cnt} missiya — kamida {format_duration_uz(min_h * 3600)}"


def compute_effective_unlock_at(
    campaign: models.Campaign,
    mission: Optional[models.CampaignMission],
    progress: models.UserCampaignProgress,
) -> Optional[datetime]:
    """
    Serverdagi haqiqiy ochilish vaqtini (UTC) qaytaradi.
    - Calendar rejimida missiyaning calendar_unlock_at maydoni ustuvor.
    - Cooldown rejimida progress.unlock_at ishlatiladi.
    """
    if not mission:
        return None
    if (campaign.unlock_mode or "cooldown") == "calendar":
        return mission.calendar_unlock_at
    return progress.unlock_at


def is_mission_unlocked(
    campaign: models.Campaign,
    mission: Optional[models.CampaignMission],
    progress: models.UserCampaignProgress,
    now_utc: Optional[datetime] = None,
) -> Tuple[bool, int, Optional[datetime]]:
    """Qaytaradi: (ochiqmi, qolgan_soniyalar, effective_unlock_at_utc)"""
    now_u = now_utc or utc_now()
    eff_unlock = compute_effective_unlock_at(campaign, mission, progress)
    if eff_unlock is None or now_u >= eff_unlock:
        return True, 0, eff_unlock
    rem = max(1, int((eff_unlock - now_u).total_seconds()))
    return False, rem, eff_unlock


def estimate_remaining_days(
    campaign: models.Campaign,
    missions: List[models.CampaignMission],
    progress: models.UserCampaignProgress,
    now_utc: Optional[datetime] = None,
) -> int:
    """Progress ko'rsatkichi uchun taxminiy qolgan kunlar soni."""
    if progress.is_completed or not missions:
        return 0
    now_u = now_utc or utc_now()
    ordered = sorted(missions, key=lambda m: m.order_index)
    remaining_missions = [m for m in ordered if m.order_index >= progress.current_mission_order]
    if not remaining_missions:
        return 0

    if (campaign.unlock_mode or "cooldown") == "calendar":
        last_dt = remaining_missions[-1].calendar_unlock_at
        if last_dt and last_dt > now_u:
            return max(1, int(math.ceil((last_dt - now_u).total_seconds() / 86400.0)))
        return 0

    cur_mission = remaining_missions[0]
    _, cur_rem_secs, _ = is_mission_unlocked(campaign, cur_mission, progress, now_u)
    future_hours = sum(get_mission_cooldown_hours(campaign, m) for m in remaining_missions[1:])
    total_secs = cur_rem_secs + future_hours * 3600
    if total_secs <= 0:
        return 0
    return max(1, int(math.ceil(total_secs / 86400.0)))


def refresh_daily_attempts(progress: models.UserCampaignProgress, now_utc: Optional[datetime] = None) -> bool:
    """Asia/Tashkent yarim tunidan keyin kunlik urinishlar hisoblagichini nolga tushiradi."""
    today = tashkent_today_str(now_utc)
    if progress.daily_attempts_date != today:
        progress.daily_attempts_date = today
        progress.daily_wrong_attempts = 0
        return True
    return False


def parse_mission_options(mission: models.CampaignMission) -> List[Dict[str, Any]]:
    try:
        data = json.loads(mission.options_json or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []


def parse_json_dict(raw: Optional[str]) -> Dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def parse_completion_rewards(campaign: models.Campaign) -> Dict[str, Any]:
    return parse_json_dict(getattr(campaign, "completion_rewards_json", "{}"))


def parse_task_data(mission: models.CampaignMission) -> Dict[str, Any]:
    return parse_json_dict(getattr(mission, "task_data_json", "{}"))


def format_completion_rewards_preview(campaign: models.Campaign) -> str:
    r = parse_completion_rewards(campaign)
    parts = []
    if r.get("gold"):
        parts.append(f"{int(r['gold']):,} 🪙 Oltin")
    if r.get("food"):
        parts.append(f"{int(r['food']):,} 🌾 Bug'doy")
    if r.get("iron"):
        parts.append(f"{int(r['iron']):,} ⛓️ Temir")
    if r.get("xp"):
        parts.append(f"{int(r['xp']):,} ✨ XP")
    if r.get("title"):
        parts.append(f"👑 Unvon: «{r['title']}»")
    if r.get("achievement_name"):
        parts.append(f"🏅 Yutuq: «{r['achievement_name']}»")
    return ", ".join(parts) if parts else "Har bosqich mukofotlari + shon-sharaf"


async def compute_player_campaign_power(session: AsyncSession, user: models.User) -> int:
    """O'yinchining mavjud RPG statistikasi (Daraja, Armiya, Ajdar) asosida kampaniya jang quvvatini hisoblaydi."""
    lvl = max(1, int(getattr(user, "level", 1) or 1))
    power = lvl * 150

    army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
    army = army_res.scalar_one_or_none()
    if army:
        army_power = (
            (army.infantry or 0) * 2
            + (army.archers or 0) * 3
            + (army.cavalry or 0) * 4
            + (army.spearmen or 0) * 3
            + (army.special_troops or 0) * 6
        )
        power += min(army_power, 20000)

    drg_res = await session.execute(
        select(func.max(models.Dragon.power)).where(models.Dragon.user_id == user.id)
    )
    max_drg = drg_res.scalar() or 0
    if max_drg > 0:
        power += min(int(max_drg // 2), 5000)

    return max(100, int(power))


# ============================================================
# QUERY & PLAYER PROGRESS SERVICES
# ============================================================

async def list_campaigns(
    session: AsyncSession,
    include_drafts: bool = False,
) -> List[models.Campaign]:
    stmt = select(models.Campaign).options(selectinload(models.Campaign.missions)).order_by(models.Campaign.id.asc())
    if not include_drafts:
        stmt = stmt.where(models.Campaign.status == "published")
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_campaign_with_missions(
    session: AsyncSession,
    campaign_id: int,
) -> Optional[models.Campaign]:
    res = await session.execute(
        select(models.Campaign)
        .where(models.Campaign.id == campaign_id)
        .options(selectinload(models.Campaign.missions))
        .execution_options(populate_existing=True)
    )
    return res.scalar_one_or_none()


async def get_or_create_progress(
    session: AsyncSession,
    user: models.User,
    campaign: models.Campaign,
    now_utc: Optional[datetime] = None,
) -> models.UserCampaignProgress:
    now_u = now_utc or utc_now()
    res = await session.execute(
        select(models.UserCampaignProgress).where(
            models.UserCampaignProgress.user_id == user.id,
            models.UserCampaignProgress.campaign_id == campaign.id,
        )
    )
    prog = res.scalar_one_or_none()
    if prog:
        if refresh_daily_attempts(prog, now_u):
            prog.updated_at = now_u
            await session.commit()
        return prog

    missions = sorted(campaign.missions or [], key=lambda m: m.order_index)
    first_unlock = None
    if (campaign.unlock_mode or "cooldown") == "calendar" and missions:
        first_unlock = missions[0].calendar_unlock_at

    prog = models.UserCampaignProgress(
        user_id=user.id,
        telegram_id=user.telegram_id,
        campaign_id=campaign.id,
        current_mission_order=1,
        completed_missions_count=0,
        is_completed=len(missions) == 0,
        unlock_at=first_unlock,
        unlock_notified_for_order=1 if (first_unlock is None or first_unlock <= now_u) else 0,
        daily_wrong_attempts=0,
        daily_attempts_date=tashkent_today_str(now_u),
        choice_cooldown_until=None,
        branch_choices_json="{}",
        notify_enabled=True,
        started_at=now_u,
        updated_at=now_u,
    )
    session.add(prog)
    await session.commit()
    await session.refresh(prog)
    return prog


async def get_campaign_player_state(
    session: AsyncSession,
    user: models.User,
    campaign_id: int,
    now_utc: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    now_u = now_utc or utc_now()
    campaign = await get_campaign_with_missions(session, campaign_id)
    if not campaign:
        return None
    missions = sorted(campaign.missions or [], key=lambda m: m.order_index)
    prog = await get_or_create_progress(session, user, campaign, now_u)

    cur_mission = next((m for m in missions if m.order_index == prog.current_mission_order), None)
    unlocked, rem_secs, eff_unlock = is_mission_unlocked(campaign, cur_mission, prog, now_u)
    rem_days = estimate_remaining_days(campaign, missions, prog, now_u)

    max_attempts = get_mission_daily_attempts(campaign, cur_mission) if cur_mission else 3
    attempts_left = max(0, max_attempts - (prog.daily_wrong_attempts or 0))
    choice_cd_secs = 0
    if prog.choice_cooldown_until and prog.choice_cooldown_until > now_u:
        choice_cd_secs = max(1, int((prog.choice_cooldown_until - now_u).total_seconds()))

    return {
        "campaign": campaign,
        "missions": missions,
        "total_missions": len(missions),
        "progress": prog,
        "current_mission": cur_mission,
        "unlocked": unlocked,
        "remaining_unlock_seconds": rem_secs,
        "effective_unlock_at": eff_unlock,
        "remaining_days_estimate": rem_days,
        "max_daily_attempts": max_attempts,
        "attempts_left": attempts_left,
        "choice_cooldown_seconds": choice_cd_secs,
        "midnight_reset_seconds": seconds_until_tashkent_midnight(now_u),
    }


async def toggle_campaign_notifications(
    session: AsyncSession,
    user: models.User,
    campaign_id: int,
) -> Tuple[bool, bool]:
    """O'yinchi uchun kampaniya ochilish bildirishnomasini yoqish/o'chirish."""
    campaign = await get_campaign_with_missions(session, campaign_id)
    if not campaign:
        return False, False
    prog = await get_or_create_progress(session, user, campaign)
    prog.notify_enabled = not bool(prog.notify_enabled)
    prog.updated_at = utc_now()
    await session.commit()
    return True, bool(prog.notify_enabled)


# ============================================================
# SERVER-ENFORCED, CONCURRENCY-SAFE MISSION SUBMISSION
# ============================================================

async def submit_campaign_mission_action(
    session: AsyncSession,
    user_id: int,
    campaign_id: int,
    mission_order: int,
    action_value: Optional[str] = None,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    O'yinchi javobini / harakatini serverda qat'iy tekshiradi va bajaradi.
    - Double-click va bir nechta qurilmadan bir vaqtda yuborishga qarshi asyncio.Lock + DB tekshiruv.
    - Eski xabardagi tugma orqali kutishni aylanib o'tishga yo'l qo'ymaydi.
    - Donat/resurs orqali kutishni o'tkazib yuborish yo'q (0 P2W).
    """
    lock = _get_progress_lock(user_id, campaign_id)
    async with lock:
        now_u = now_utc or utc_now()

        # Foydalanuvchi va kampaniyani qayta o'qish
        user = (await session.execute(select(models.User).where(models.User.id == user_id))).scalar_one_or_none()
        if not user:
            return {"ok": False, "code": "user_not_found", "message": "❌ Foydalanuvchi topilmadi."}

        campaign = await get_campaign_with_missions(session, campaign_id)
        if not campaign or campaign.status != "published":
            return {"ok": False, "code": "campaign_unavailable", "message": "❌ Ushbu kampaniya hozirda mavjud emas."}

        min_lvl = max(1, int(getattr(campaign, "min_level", 1) or 1))
        user_lvl = max(1, int(getattr(user, "level", 1) or 1))
        if user_lvl < min_lvl:
            return {
                "ok": False,
                "code": "level_too_low",
                "message": f"🔒 Ushbu kampaniya uchun kamida **{min_lvl}-daraja** talab qilinadi (sizda: {user_lvl}-daraja).",
            }

        missions = sorted(campaign.missions or [], key=lambda m: m.order_index)
        if not missions:
            return {"ok": False, "code": "no_missions", "message": "❌ Kampaniyada missiyalar yo'q."}

        prog = await get_or_create_progress(session, user, campaign, now_u)
        # SQLite/Postgres da progress satrini yangilab olish
        await session.refresh(prog)

        if prog.is_completed:
            return {
                "ok": False,
                "code": "already_completed",
                "message": "🏆 Siz ushbu kampaniyani allaqachon to'liq yakunlagansiz!",
            }

        # Eski tugma yoki double-click himoyasi
        if int(mission_order) != int(prog.current_mission_order):
            return {
                "ok": False,
                "code": "stale_mission",
                "message": "⚠️ Ushbu missiya allaqachon bajarilgan yoki hali navbati kelmagan. Kampaniya sahifasini yangilang.",
            }

        mission = next((m for m in missions if m.order_index == prog.current_mission_order), None)
        if not mission:
            return {"ok": False, "code": "mission_not_found", "message": "❌ Missiya topilmadi."}

        # 1. Serverda ochilish vaqtini (unlock_at / calendar) tekshirish
        unlocked, rem_secs, eff_unlock = is_mission_unlocked(campaign, mission, prog, now_u)
        if not unlocked:
            rem_str = format_duration_uz(rem_secs)
            extra = f"\n📅 Ochilish vaqti: {format_tashkent_dt(eff_unlock)}" if eff_unlock else ""
            return {
                "ok": False,
                "code": "locked",
                "remaining_seconds": rem_secs,
                "message": f"⏳ Ushbu missiya hali ochilmagan!\nKeyingi missiya: {rem_str}dan keyin ochiladi.{extra}",
            }

        # 2. Kunlik urinishlar limitini (Toshkent yarim tunida reset) tekshirish
        refresh_daily_attempts(prog, now_u)
        max_attempts = get_mission_daily_attempts(campaign, mission)
        mtype = (mission.mission_type or "story").lower()

        if mtype in ("quiz", "narrative_choice", "riddle", "riddle_investigation", "combat", "combat_encounter"):
            if (prog.daily_wrong_attempts or 0) >= max_attempts:
                mid_secs = seconds_until_tashkent_midnight(now_u)
                return {
                    "ok": False,
                    "code": "daily_limit_reached",
                    "remaining_seconds": mid_secs,
                    "message": (
                        f"🚫 Urinishlar tugadi, ertaga qayta urinib ko'ring!\n"
                        f"⏳ Yangilanishigacha: {format_duration_uz(mid_secs)} (Toshkent vaqti bilan 00:00 da)."
                    ),
                }

        # 3. Variantli (quiz / narrative_choice) missiyalarda qisqa kutish (masalan 30 daqiqa) tekshiruvi
        if mtype in ("quiz", "narrative_choice") and prog.choice_cooldown_until and prog.choice_cooldown_until > now_u:
            cd_secs = max(1, int((prog.choice_cooldown_until - now_u).total_seconds()))
            return {
                "ok": False,
                "code": "choice_cooldown",
                "remaining_seconds": cd_secs,
                "message": (
                    f"⏳ Noto'g'ri tanlovdan keyin qisqa kutish faol!\n"
                    f"Qayta urinish: {format_duration_uz(cd_secs)}dan keyin."
                ),
            }

        # 4. Missiya turiga qarab tekshirish
        outcome_text = ""
        task_data = parse_task_data(mission)
        if mtype == "story":
            outcome_text = mission.success_text or "✅ Hikoya bosqichi yakunlandi!"
        elif mtype == "branch":
            options = parse_mission_options(mission)
            chosen = next((o for o in options if str(o.get("key")) == str(action_value)), None)
            if not chosen:
                return {"ok": False, "code": "invalid_option", "message": "❌ Noto'g'ri tanlov."}
            try:
                branches = json.loads(prog.branch_choices_json or "{}")
            except Exception:
                branches = {}
            if str(mission.order_index) in branches:
                return {
                    "ok": False,
                    "code": "branch_already_chosen",
                    "message": "⚠️ Bu hikoya tanlovi yakuniy va allaqachon qabul qilingan.",
                }
            branches[str(mission.order_index)] = str(chosen.get("key"))
            prog.branch_choices_json = json.dumps(branches, ensure_ascii=False)
            outcome_text = chosen.get("outcome") or mission.success_text or f"✅ Tanlovingiz qabul qilindi: {chosen.get('text', '')}"
        elif mtype in ("quiz", "narrative_choice"):
            options = parse_mission_options(mission)
            chosen = next((o for o in options if str(o.get("key")) == str(action_value)), None)
            if not chosen:
                return {"ok": False, "code": "invalid_option", "message": "❌ Noto'g'ri variant tanlandi."}
            is_correct = bool(chosen.get("is_correct")) or (
                mission.correct_answer is not None and str(chosen.get("key")) == str(mission.correct_answer)
            )
            if not is_correct:
                prog.daily_wrong_attempts = (prog.daily_wrong_attempts or 0) + 1
                attempts_left = max(0, max_attempts - prog.daily_wrong_attempts)
                cd_min = get_mission_choice_cooldown_minutes(campaign, mission)
                if attempts_left > 0 and cd_min > 0:
                    prog.choice_cooldown_until = now_u + timedelta(minutes=cd_min)
                penalty_gold = max(0, int(chosen.get("gold_penalty", 0) or 0))
                penalty_note = ""
                if penalty_gold > 0:
                    deducted = min(int(user.gold or 0), penalty_gold)
                    user.gold = max(0, int(user.gold or 0) - deducted)
                    if deducted > 0:
                        penalty_note = f"\n💸 Jarima: -{deducted:,} 🪙 Oltin."
                prog.updated_at = now_u
                await session.commit()

                wrong_story = chosen.get("outcome") or "❌ Noto'g'ri javob!"
                if attempts_left <= 0:
                    mid_secs = seconds_until_tashkent_midnight(now_u)
                    return {
                        "ok": False,
                        "code": "wrong_and_limit_reached",
                        "attempts_left": 0,
                        "remaining_seconds": mid_secs,
                        "message": (
                            f"{wrong_story}{penalty_note}\n"
                            f"🚫 Urinishlar tugadi, ertaga qayta urinib ko'ring.\n"
                            f"⏳ Yangilanishigacha: {format_duration_uz(mid_secs)}."
                        ),
                    }
                cd_note = f"\n⏳ Keyingi urinish: {cd_min} daqiqadan keyin." if cd_min > 0 else ""
                return {
                    "ok": False,
                    "code": "wrong_answer",
                    "attempts_left": attempts_left,
                    "message": f"{wrong_story}{penalty_note}\nQolgan bugungi urinishlar: {attempts_left}/{max_attempts}.{cd_note}",
                }
            outcome_text = chosen.get("outcome") or mission.success_text or "✅ To'g'ri javob!"
        elif mtype in ("riddle", "riddle_investigation"):
            ans_raw = (action_value or "").strip().lower()
            if not ans_raw:
                return {"ok": False, "code": "empty_answer", "message": "⚠️ Iltimos, javob matnini yuboring."}
            valid_answers = [
                a.strip().lower()
                for a in (mission.correct_answer or "").split("|")
                if a.strip()
            ]
            if ans_raw not in valid_answers:
                prog.daily_wrong_attempts = (prog.daily_wrong_attempts or 0) + 1
                attempts_left = max(0, max_attempts - prog.daily_wrong_attempts)
                prog.updated_at = now_u
                await session.commit()

                if attempts_left <= 0:
                    mid_secs = seconds_until_tashkent_midnight(now_u)
                    return {
                        "ok": False,
                        "code": "wrong_and_limit_reached",
                        "attempts_left": 0,
                        "remaining_seconds": mid_secs,
                        "message": (
                            f"❌ Noto'g'ri javob!\n"
                            f"🚫 Urinishlar tugadi, ertaga qayta urinib ko'ring.\n"
                            f"⏳ Yangilanishigacha: {format_duration_uz(mid_secs)}."
                        ),
                    }
                return {
                    "ok": False,
                    "code": "wrong_answer",
                    "attempts_left": attempts_left,
                    "message": f"❌ Noto'g'ri javob! Bugungi qolgan urinishlar: {attempts_left}/{max_attempts}.",
                }
            outcome_text = mission.success_text or "✅ Jumboq to'g'ri topildi!"
        elif mtype in ("combat", "combat_encounter"):
            enemy_name = task_data.get("enemy_name") or "Qaroqchilar Boshlig'i"
            enemy_hp = int(task_data.get("enemy_hp", 200) or 200)
            enemy_atk = int(task_data.get("enemy_attack", 40) or 40)
            enemy_power = int(task_data.get("enemy_power", enemy_hp + enemy_atk * 5) or (enemy_hp + enemy_atk * 5))
            player_power = await compute_player_campaign_power(session, user)

            if player_power < enemy_power:
                prog.daily_wrong_attempts = (prog.daily_wrong_attempts or 0) + 1
                attempts_left = max(0, max_attempts - prog.daily_wrong_attempts)
                defeat_pen = max(0, int(task_data.get("defeat_gold_penalty", 0) or 0))
                pen_note = ""
                if defeat_pen > 0:
                    deducted = min(int(user.gold or 0), defeat_pen)
                    user.gold = max(0, int(user.gold or 0) - deducted)
                    if deducted > 0:
                        pen_note = f"\n💸 Chekinish talafoti: -{deducted:,} 🪙 Oltin."
                prog.updated_at = now_u
                await session.commit()

                return {
                    "ok": False,
                    "code": "combat_defeat",
                    "player_power": player_power,
                    "enemy_power": enemy_power,
                    "attempts_left": attempts_left,
                    "message": (
                        f"⚔️ **JANGDA MAG'LUBIYAT!**\n"
                        f"Raqib: **{enemy_name}** (Quvvat: `{enemy_power:,}`)\n"
                        f"Sizning quvvatingiz: `{player_power:,}`{pen_note}\n\n"
                        f"💡 Qo'shiningizni yoki darajangizni kuchaytirib qayta urining! "
                        f"(Bugungi qolgan urinishlar: {attempts_left}/{max_attempts})"
                    ),
                }
            outcome_text = (
                f"⚔️ **G'ALABA!** Siz **{enemy_name}** ustidan g'alaba qozondingiz "
                f"(Quvvat: `{player_power:,}` vs `{enemy_power:,}`)!"
            )
            if mission.success_text:
                outcome_text += f"\n\n{mission.success_text}"
        elif mtype in ("tribute", "resource_tribute"):
            req_gold = max(0, int(task_data.get("cost_gold", 0) or 0))
            req_food = max(0, int(task_data.get("cost_food", 0) or 0))
            req_iron = max(0, int(task_data.get("cost_iron", 0) or 0))
            if (user.gold or 0) < req_gold or (user.food or 0) < req_food or (user.iron or 0) < req_iron:
                need_parts = []
                if req_gold:
                    need_parts.append(f"{req_gold:,} 🪙 (sizda: {int(user.gold or 0):,})")
                if req_food:
                    need_parts.append(f"{req_food:,} 🌾 (sizda: {int(user.food or 0):,})")
                if req_iron:
                    need_parts.append(f"{req_iron:,} ⛓️ (sizda: {int(user.iron or 0):,})")
                return {
                    "ok": False,
                    "code": "insufficient_resources",
                    "message": f"❌ Ushbu bosqich uchun resurs yetarli emas!\nKerak: {', '.join(need_parts)}",
                }
            user.gold = int(user.gold or 0) - req_gold
            user.food = int(user.food or 0) - req_food
            user.iron = int(user.iron or 0) - req_iron
            outcome_text = mission.success_text or "💰 To'lov qabul qilindi va muhim ma'lumot qo'lga kiritildi!"
        else:
            outcome_text = mission.success_text or "✅ Missiya bajarildi!"

        # 5. Missiya muvaffaqiyatli yakunlandi — mukofot berish va keyingi missiya uchun unlock_at hisoblash
        if mission.reward_gold:
            user.gold = (user.gold or 0) + int(mission.reward_gold)
        if mission.reward_food:
            user.food = (user.food or 0) + int(mission.reward_food)
        if mission.reward_iron:
            user.iron = (user.iron or 0) + int(mission.reward_iron)
        if mission.reward_xp:
            user.xp = (user.xp or 0) + int(mission.reward_xp)

        prog.completed_missions_count = (prog.completed_missions_count or 0) + 1
        prog.last_completed_at = now_u
        prog.choice_cooldown_until = None
        prog.daily_wrong_attempts = 0
        prog.daily_attempts_date = tashkent_today_str(now_u)

        next_order = prog.current_mission_order + 1
        next_mission = next((m for m in missions if m.order_index == next_order), None)

        grand_rewards_granted: Dict[str, Any] = {}
        next_unlock_at: Optional[datetime] = None
        if next_mission is None:
            prog.current_mission_order = next_order
            prog.is_completed = True
            prog.unlock_at = None

            # Grand Finale completion rewards (faqat 1 marta beriladi — anti-duplicate guard!)
            if not getattr(prog, "completion_reward_claimed", False):
                prog.completion_reward_claimed = True
                crewards = parse_completion_rewards(campaign)
                if crewards.get("gold"):
                    g = int(crewards["gold"])
                    user.gold = (user.gold or 0) + g
                    grand_rewards_granted["gold"] = g
                if crewards.get("food"):
                    f = int(crewards["food"])
                    user.food = (user.food or 0) + f
                    grand_rewards_granted["food"] = f
                if crewards.get("iron"):
                    ir = int(crewards["iron"])
                    user.iron = (user.iron or 0) + ir
                    grand_rewards_granted["iron"] = ir
                if crewards.get("xp"):
                    xp = int(crewards["xp"])
                    user.xp = (user.xp or 0) + xp
                    grand_rewards_granted["xp"] = xp
                if crewards.get("title"):
                    user.title = str(crewards["title"])[:100]
                    grand_rewards_granted["title"] = user.title
                ach_code = crewards.get("achievement_code")
                if ach_code:
                    ach_name = crewards.get("achievement_name") or f"{campaign.title} G'olibi"
                    ex_ach = (
                        await session.execute(
                            select(models.UserAchievement).where(
                                models.UserAchievement.user_id == user.id,
                                models.UserAchievement.achievement_code == str(ach_code),
                            )
                        )
                    ).scalar_one_or_none()
                    if not ex_ach:
                        session.add(
                            models.UserAchievement(
                                user_id=user.id,
                                telegram_id=user.telegram_id,
                                achievement_code=str(ach_code)[:50],
                                title=str(ach_name)[:100],
                                reward_gold=0,
                                reward_iron=0,
                                reward_food=0,
                                reward_prestige=0,
                            )
                        )
                        grand_rewards_granted["achievement"] = ach_name
        else:
            prog.current_mission_order = next_order
            if (campaign.unlock_mode or "cooldown") == "calendar":
                next_unlock_at = next_mission.calendar_unlock_at
            else:
                cd_hours = get_mission_cooldown_hours(campaign, next_mission)
                next_unlock_at = (now_u + timedelta(hours=cd_hours)) if cd_hours > 0 else now_u
            prog.unlock_at = next_unlock_at
            # Agar darhol ochiq bo'lsa, qayta bildirishnoma yuborilmasin
            if next_unlock_at is None or next_unlock_at <= now_u:
                prog.unlock_notified_for_order = next_order

        prog.updated_at = now_u
        await session.commit()

        reward_parts = []
        if mission.reward_gold:
            reward_parts.append(f"+{mission.reward_gold:,} 🪙")
        if mission.reward_food:
            reward_parts.append(f"+{mission.reward_food:,} 🌾")
        if mission.reward_iron:
            reward_parts.append(f"+{mission.reward_iron:,} ⛓️")
        if mission.reward_xp:
            reward_parts.append(f"+{mission.reward_xp:,} ✨ XP")
        reward_str = ", ".join(reward_parts)

        next_info = ""
        if prog.is_completed:
            grand_lines = []
            if grand_rewards_granted.get("gold"):
                grand_lines.append(f"🪙 +{grand_rewards_granted['gold']:,} Oltin")
            if grand_rewards_granted.get("food"):
                grand_lines.append(f"🌾 +{grand_rewards_granted['food']:,} Bug'doy")
            if grand_rewards_granted.get("iron"):
                grand_lines.append(f"⛓️ +{grand_rewards_granted['iron']:,} Temir")
            if grand_rewards_granted.get("xp"):
                grand_lines.append(f"✨ +{grand_rewards_granted['xp']:,} XP")
            if grand_rewards_granted.get("title"):
                grand_lines.append(f"👑 Yangi Unvon: **«{grand_rewards_granted['title']}»**")
            if grand_rewards_granted.get("achievement"):
                grand_lines.append(f"🏅 Yutuq ochildi: **«{grand_rewards_granted['achievement']}»**")
            grand_block = ("\n\n🎁 **FINAL MUKOFOTLARI:**\n" + "\n".join(grand_lines)) if grand_lines else ""
            next_info = f"\n\n🏆 **TABRIKLAYMIZ!** Siz «**{campaign.title}**» kampaniyasini to'liq yakunladingiz!{grand_block}"
        elif next_unlock_at and next_unlock_at > now_u:
            wait_str = format_duration_uz(int((next_unlock_at - now_u).total_seconds()))
            next_info = (
                f"\n\n⏳ Keyingi missiya ({next_order}/{len(missions)}): "
                f"**{wait_str}**dan keyin ochiladi ({format_tashkent_dt(next_unlock_at)})."
            )
        else:
            next_info = f"\n\n🔓 Keyingi missiya ({next_order}/{len(missions)}) hozir ochiq!"

        full_msg = outcome_text
        if reward_str:
            full_msg += f"\n🎁 Bosqich mukofoti: {reward_str}"
        full_msg += next_info

        return {
            "ok": True,
            "code": "completed",
            "completed_campaign": bool(prog.is_completed),
            "grand_rewards_granted": grand_rewards_granted,
            "next_mission_order": prog.current_mission_order,
            "next_unlock_at": next_unlock_at,
            "message": full_msg,
        }


# ============================================================
# BACKGROUND NOTIFICATION SCHEDULER (RATE-LIMITED, IDEMPOTENT)
# ============================================================

async def process_campaign_unlock_notifications(
    session: AsyncSession,
    bot=None,
    now_utc: Optional[datetime] = None,
    rate_limit_delay: float = 0.04,
) -> Dict[str, int]:
    """
    Ochilish vaqti yetgan missiyalar uchun o'yinchilarga 1 marta bildirishnoma yuboradi.
    - Server restartdan keyin o'tkazib yuborilgan bildirishnomalarni qayta tiklaydi.
    - unlock_notified_for_order orqali ikki marta yuborilishining oldini oladi.
    - Telegram ~30 msg/sec limitiga rioya qilish uchun rate_limit_delay (~0.04s) bilan yuboradi.
    """
    now_u = now_utc or utc_now()
    res = await session.execute(
        select(models.UserCampaignProgress).where(
            models.UserCampaignProgress.is_completed == False,
            models.UserCampaignProgress.notify_enabled == True,
            models.UserCampaignProgress.unlock_notified_for_order < models.UserCampaignProgress.current_mission_order,
        )
    )
    candidates = list(res.scalars().all())
    if not candidates:
        return {"checked": 0, "notified": 0, "errors": 0}

    # Kampaniyalarni keshlab olish
    camp_ids = {p.campaign_id for p in candidates}
    camps_res = await session.execute(
        select(models.Campaign)
        .where(models.Campaign.id.in_(camp_ids), models.Campaign.status == "published")
        .options(selectinload(models.Campaign.missions))
    )
    camp_map = {c.id: c for c in camps_res.scalars().all()}

    notified = 0
    errors = 0
    for prog in candidates:
        camp = camp_map.get(prog.campaign_id)
        if not camp:
            continue
        mission = next((m for m in (camp.missions or []) if m.order_index == prog.current_mission_order), None)
        if not mission:
            continue

        eff_unlock = compute_effective_unlock_at(camp, mission, prog)
        if eff_unlock is None or eff_unlock > now_u:
            continue

        # Idempotent belgilash (ikki marta ketmasligi uchun oldin bazada belgilaymiz)
        prog.unlock_notified_for_order = prog.current_mission_order
        prog.updated_at = now_u
        await session.commit()

        if bot is not None:
            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗺️ Missiyani Ochish", callback_data=f"camp_view:{camp.id}")],
                    [InlineKeyboardButton("🔕 Bildirishnomani O'chirish", callback_data=f"camp_notify_toggle:{camp.id}")],
                ])
                await bot.send_message(
                    chat_id=prog.telegram_id,
                    text=(
                        f"🔔 **Yangi missiya ochildi!**\n\n"
                        f"🗺️ Kampaniya: **{camp.title}**\n"
                        f"📜 {mission.order_index}-missiya: **{mission.title}**\n\n"
                        f"Sarguzashtni davom ettirish uchun quyidagi tugmani bosing!"
                    ),
                    parse_mode="Markdown",
                    reply_markup=kb,
                )
                notified += 1
                if rate_limit_delay > 0:
                    await asyncio.sleep(rate_limit_delay)
            except Exception as send_err:
                logger.warning(f"Campaign unlock notify error (tg={prog.telegram_id}): {send_err}")
                errors += 1
        else:
            notified += 1

    return {"checked": len(candidates), "notified": notified, "errors": errors}


# ============================================================
# ADMIN SERVICES (CREATE, EDIT, STATS, TEST MODE, SEED)
# ============================================================

async def create_campaign(
    session: AsyncSession,
    title: str,
    description: str = "",
    unlock_mode: str = "cooldown",
    default_cooldown_hours: int = 24,
    default_daily_attempts: int = 3,
    default_choice_cooldown_minutes: int = 30,
    status: str = "draft",
    created_by: Optional[int] = None,
    slug: Optional[str] = None,
    banner_image: Optional[str] = None,
    min_level: int = 1,
    order_index: int = 0,
    completion_rewards: Optional[Dict[str, Any]] = None,
) -> models.Campaign:
    now_u = utc_now()
    camp = models.Campaign(
        slug=slug,
        title=title.strip(),
        description=description.strip(),
        banner_image=banner_image,
        min_level=max(1, int(min_level or 1)),
        order_index=int(order_index or 0),
        completion_rewards_json=json.dumps(completion_rewards or {}, ensure_ascii=False),
        status=status,
        unlock_mode=unlock_mode if unlock_mode in ("cooldown", "calendar") else "cooldown",
        default_cooldown_hours=max(0, int(default_cooldown_hours)),
        default_daily_attempts=max(1, int(default_daily_attempts)),
        default_choice_cooldown_minutes=max(0, int(default_choice_cooldown_minutes)),
        created_by=created_by,
        created_at=now_u,
        updated_at=now_u,
    )
    session.add(camp)
    await session.commit()
    await session.refresh(camp)
    return camp


ALLOWED_MISSION_TYPES = {
    "story", "quiz", "narrative_choice", "branch", "riddle", "riddle_investigation", "combat", "combat_encounter", "tribute", "resource_tribute"
}


async def add_campaign_mission(
    session: AsyncSession,
    campaign_id: int,
    order_index: int,
    title: str,
    story_text: str,
    mission_type: str = "story",
    options: Optional[List[Dict[str, Any]]] = None,
    correct_answer: Optional[str] = None,
    task_data: Optional[Dict[str, Any]] = None,
    success_text: str = "",
    cooldown_hours_override: Optional[int] = None,
    calendar_unlock_at: Optional[datetime] = None,
    daily_attempts_override: Optional[int] = None,
    choice_cooldown_minutes_override: Optional[int] = None,
    reward_gold: int = 0,
    reward_food: int = 0,
    reward_iron: int = 0,
    reward_xp: int = 0,
) -> models.CampaignMission:
    mtype = (mission_type or "story").lower()
    m = models.CampaignMission(
        campaign_id=campaign_id,
        order_index=int(order_index),
        title=title.strip(),
        story_text=story_text.strip(),
        mission_type=mtype if mtype in ALLOWED_MISSION_TYPES else "story",
        options_json=json.dumps(options or [], ensure_ascii=False),
        task_data_json=json.dumps(task_data or {}, ensure_ascii=False),
        success_text=(success_text or "").strip(),
        correct_answer=correct_answer,
        cooldown_hours_override=cooldown_hours_override,
        calendar_unlock_at=calendar_unlock_at,
        daily_attempts_override=daily_attempts_override,
        choice_cooldown_minutes_override=choice_cooldown_minutes_override,
        reward_gold=int(reward_gold or 0),
        reward_food=int(reward_food or 0),
        reward_iron=int(reward_iron or 0),
        reward_xp=int(reward_xp or 0),
        created_at=utc_now(),
    )
    session.add(m)
    await session.commit()
    await session.refresh(m)
    return m


async def delete_campaign_mission(session: AsyncSession, mission_id: int) -> Tuple[bool, str]:
    """Missiya bosqichini o'chiradi va qolgan bosqichlarni 1..N tartibda qayta raqamlaydi."""
    res = await session.execute(select(models.CampaignMission).where(models.CampaignMission.id == mission_id))
    target = res.scalar_one_or_none()
    if not target:
        return False, "❌ Missiya topilmadi."
    camp_id = target.campaign_id
    await session.delete(target)
    await session.flush()

    rem_res = await session.execute(
        select(models.CampaignMission)
        .where(models.CampaignMission.campaign_id == camp_id)
        .order_by(models.CampaignMission.order_index.asc())
    )
    remaining = list(rem_res.scalars().all())
    # Vaqtinchalik katta qiymatga o'tkazib, so'ng 1..N qilib yozamiz (UniqueConstraint to'qnashmasligi uchun)
    for idx, m in enumerate(remaining, 1):
        m.order_index = 10000 + idx
    await session.flush()
    for idx, m in enumerate(remaining, 1):
        m.order_index = idx
    await session.commit()
    return True, "🗑️ Missiya o'chirildi va bosqichlar qayta tartiblandi."


async def update_campaign_settings(
    session: AsyncSession,
    campaign_id: int,
    *,
    status: Optional[str] = None,
    unlock_mode: Optional[str] = None,
    default_cooldown_hours: Optional[int] = None,
    default_daily_attempts: Optional[int] = None,
    default_choice_cooldown_minutes: Optional[int] = None,
) -> Tuple[bool, str, Optional[models.Campaign]]:
    """
    Nashr qilingan kampaniya sozlamalarini xavfsiz yangilaydi:
    allaqachon o'tilgan progressga tegmaydi, yangi o'yinchilar va hali ochilmagan missiyalarga qo'llanadi.
    """
    camp = await get_campaign_with_missions(session, campaign_id)
    if not camp:
        return False, "❌ Kampaniya topilmadi.", None

    if status in ("draft", "published", "archived"):
        camp.status = status
    if unlock_mode in ("cooldown", "calendar"):
        camp.unlock_mode = unlock_mode
    if default_cooldown_hours is not None:
        camp.default_cooldown_hours = max(0, int(default_cooldown_hours))
    if default_daily_attempts is not None:
        camp.default_daily_attempts = max(1, int(default_daily_attempts))
    if default_choice_cooldown_minutes is not None:
        camp.default_choice_cooldown_minutes = max(0, int(default_choice_cooldown_minutes))

    camp.updated_at = utc_now()
    await session.commit()
    await session.refresh(camp)
    return True, "✅ Kampaniya sozlamalari yangilandi (mavjud progress saqlandi).", camp


async def update_mission_settings(
    session: AsyncSession,
    mission_id: int,
    *,
    cooldown_hours_override: Any = ...,
    calendar_unlock_at: Any = ...,
    daily_attempts_override: Any = ...,
    choice_cooldown_minutes_override: Any = ...,
) -> Tuple[bool, str, Optional[models.CampaignMission]]:
    res = await session.execute(select(models.CampaignMission).where(models.CampaignMission.id == mission_id))
    m = res.scalar_one_or_none()
    if not m:
        return False, "❌ Missiya topilmadi.", None
    if cooldown_hours_override is not ...:
        m.cooldown_hours_override = None if cooldown_hours_override is None else max(0, int(cooldown_hours_override))
    if calendar_unlock_at is not ...:
        m.calendar_unlock_at = calendar_unlock_at
    if daily_attempts_override is not ...:
        m.daily_attempts_override = None if daily_attempts_override is None else max(1, int(daily_attempts_override))
    if choice_cooldown_minutes_override is not ...:
        m.choice_cooldown_minutes_override = None if choice_cooldown_minutes_override is None else max(0, int(choice_cooldown_minutes_override))
    await session.commit()
    await session.refresh(m)
    return True, "✅ Missiya sozlamalari yangilandi.", m


async def get_campaign_stats(
    session: AsyncSession,
    campaign_id: int,
    now_utc: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Admin uchun statistika: minimal davomiylik, jami o'yinchilar va har missiyada kutayotganlar soni."""
    now_u = now_utc or utc_now()
    camp = await get_campaign_with_missions(session, campaign_id)
    if not camp:
        return None
    missions = sorted(camp.missions or [], key=lambda m: m.order_index)

    progs_res = await session.execute(
        select(models.UserCampaignProgress).where(models.UserCampaignProgress.campaign_id == campaign_id)
    )
    progs = list(progs_res.scalars().all())

    waiting_by_mission: Dict[int, int] = {m.order_index: 0 for m in missions}
    active_by_mission: Dict[int, int] = {m.order_index: 0 for m in missions}
    completed_count = 0

    mission_map = {m.order_index: m for m in missions}
    for p in progs:
        if p.is_completed:
            completed_count += 1
            continue
        m = mission_map.get(p.current_mission_order)
        if not m:
            continue
        unlocked, _, _ = is_mission_unlocked(camp, m, p, now_u)
        if unlocked:
            active_by_mission[m.order_index] = active_by_mission.get(m.order_index, 0) + 1
        else:
            waiting_by_mission[m.order_index] = waiting_by_mission.get(m.order_index, 0) + 1

    return {
        "campaign": camp,
        "missions": missions,
        "total_players": len(progs),
        "completed_players": completed_count,
        "min_duration_hours": calculate_campaign_min_duration_hours(camp, missions),
        "min_duration_label": format_campaign_min_duration(camp, missions),
        "waiting_by_mission": waiting_by_mission,
        "active_by_mission": active_by_mission,
    }


async def simulate_admin_test_step(
    session: AsyncSession,
    campaign_id: int,
    mission_order: int,
    action_value: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Admin sinov rejimi (READ-ONLY):
    - Kutish vaqtlari (cooldown / calendar) ni o'tkazib yuboradi.
    - Haqiqiy UserCampaignProgress jadvaliga HECH NARSA yozmaydi!
    """
    camp = await get_campaign_with_missions(session, campaign_id)
    if not camp:
        return {"ok": False, "message": "❌ Kampaniya topilmadi."}
    missions = sorted(camp.missions or [], key=lambda m: m.order_index)
    mission = next((m for m in missions if m.order_index == int(mission_order)), None)
    if not mission:
        return {"ok": False, "message": "❌ Missiya topilmadi."}

    mtype = (mission.mission_type or "story").lower()
    if mtype == "quiz" and action_value is not None:
        options = parse_mission_options(mission)
        chosen = next((o for o in options if str(o.get("key")) == str(action_value)), None)
        if not chosen:
            return {"ok": False, "message": "❌ [SINOV] Noto'g'ri variant."}
        is_correct = bool(chosen.get("is_correct")) or (
            mission.correct_answer is not None and str(chosen.get("key")) == str(mission.correct_answer)
        )
        if not is_correct:
            return {"ok": False, "message": "❌ [SINOV] Noto'g'ri javob (sinov rejimida kutish yo'q, qayta urining)."}
    elif mtype == "riddle" and action_value is not None:
        valid = [a.strip().lower() for a in (mission.correct_answer or "").split("|") if a.strip()]
        if action_value.strip().lower() not in valid:
            return {"ok": False, "message": f"❌ [SINOV] Noto'g'ri javob. (To'g'ri javob: {mission.correct_answer})"}

    next_order = mission.order_index + 1
    has_next = any(m.order_index == next_order for m in missions)
    return {
        "ok": True,
        "test_mode": True,
        "completed_campaign": not has_next,
        "next_mission_order": next_order if has_next else None,
        "message": (
            f"🧪 **[ADMIN SINOV REJIMI]** {mission.order_index}-missiya o'tildi (kutish vaqti o'tkazib yuborildi, bazaga yozilmadi)."
        ),
    }


async def seed_sample_campaign(session: AsyncSession) -> models.Campaign:
    """
    Namuna kampaniya: 'The Mystery of the Missing Lord'
    5 ta missiya, har biri orasida 24 soat kutish (cooldown=24h, daily_attempts=3, choice_cooldown=30m).
    Idempotent: mavjud bo'lsa qayta yaratmaydi.
    """
    sample_completion_rewards = {
        "gold": 10000,
        "food": 10000,
        "iron": 5000,
        "xp": 400,
        "title": "Tergov Qo'li",
        "achievement_code": "camp_missing_lord",
        "achievement_name": "Yo'qolgan Lord Qutqaruvchisi",
    }

    res = await session.execute(
        select(models.Campaign)
        .where(models.Campaign.slug == "mystery_missing_lord")
        .options(selectinload(models.Campaign.missions))
    )
    existing = res.scalar_one_or_none()
    if existing:
        if not parse_completion_rewards(existing):
            existing.completion_rewards_json = json.dumps(sample_completion_rewards, ensure_ascii=False)
            await session.commit()
        return existing

    camp = await create_campaign(
        session=session,
        slug="mystery_missing_lord",
        title="The Mystery of the Missing Lord",
        description=(
            "Shimoliy qal'adan sirli ravishda g'oyib bo'lgan Lordning izini toping. "
            "5 bosqichli tergov kampaniyasi (har missiya orasida 24 soat kutish)."
        ),
        min_level=1,
        completion_rewards=sample_completion_rewards,
        unlock_mode="cooldown",
        default_cooldown_hours=24,
        default_daily_attempts=3,
        default_choice_cooldown_minutes=30,
        status="published",
    )

    sample_missions = [
        {
            "order_index": 1,
            "title": "Qarg'a Xabari",
            "story_text": (
                "Yarim tunda Qora Qarg'a qal'angizga shoshilinch xat keltirdi: "
                "«Lord Edrik uch kundan beri g'oyib. Uning xonasida faqat yarim yongan xarita va kumush muhr qolgan.»\n\n"
                "Tergovni boshlash uchun davom eting."
            ),
            "mission_type": "story",
            "options": [],
            "reward_gold": 1500,
            "reward_food": 2000,
            "reward_xp": 50,
        },
        {
            "order_index": 2,
            "title": "Qal'a Darvozasidagi Izlar",
            "story_text": (
                "Soqchilar yarim tunda darvozadan bitta arava chiqib ketganini ko'rishgan. "
                "Qorda uch xil iz qolgan. Qaysi iz Lord Edrikning aravasiga tegishli?"
            ),
            "mission_type": "quiz",
            "options": [
                {"key": "a", "text": "🐺 Shimoliy o'rmon tomon ketgan yengil ot izlari", "is_correct": False},
                {"key": "b", "text": "🛞 Janubiy bandargohga ketgan og'ir temir g'ildirak izi", "is_correct": True, "outcome": "✅ Og'ir temir g'ildirak izi sizni qadimiy bandargoh omboriga olib bordi!"},
                {"key": "c", "text": "⚔️ Sharqiy qal'a tomon yurgan piyoda askarlar izi", "is_correct": False},
            ],
            "correct_answer": "b",
            "reward_gold": 2500,
            "reward_iron": 1000,
            "reward_xp": 75,
        },
        {
            "order_index": 3,
            "title": "Gumondorni So'roq Qilish",
            "story_text": (
                "Bandargohda siz savdogar Varenni qo'lga oldingiz. U qo'rqib ketgan, lekin hamma narsani aytishni istamayapti. "
                "Qanday yo'l tutasiz? *(Bu tanlov hikoyani burib yuboradi va yakuniy hisoblanadi!)*"
            ),
            "mission_type": "branch",
            "options": [
                {"key": "mercy", "text": "🤝 Himoya va'da qilib, ishonchini qozonish", "outcome": "🤝 Varen sizga ishondi va maxfiy kodlangan maktubni topshirdi!"},
                {"key": "force", "text": "⚔️ Qattiq bosim o'tkazib, zindonga tashlash bilan qo'rqitish", "outcome": "⚔️ Qo'rquv ostida Varen qochish yo'lini va muhrlangan xatni oshkor qildi!"},
            ],
            "reward_gold": 3000,
            "reward_food": 3000,
            "reward_xp": 100,
        },
        {
            "order_index": 4,
            "title": "Muhrlangan Maktub Jumboqi",
            "story_text": (
                "Maktubda qisqa jumboq yozilgan:\n"
                "«Menda qanot yo'q, lekin xabar tashiyman; qishda qor ustida qora soya tashlayman. Men nimaman?»\n\n"
                "Javobni bitta so'z bilan yozib yuboring (masalan: qarg'a / raven)."
            ),
            "mission_type": "riddle",
            "options": [],
            "correct_answer": "qarg'a|qarga|raven|ворон",
            "reward_gold": 4000,
            "reward_iron": 2000,
            "reward_xp": 125,
        },
        {
            "order_index": 5,
            "title": "Yo'qolgan Lordning Siri (Final)",
            "story_text": (
                "Qarg'a minorasida siz Lord Edrikni tirik topdingiz! U xoin maslahatchidan yashirinib, "
                "muhim dalillarni to'playotgan ekan. Xoin kim ekanini tasdiqlang:"
            ),
            "mission_type": "quiz",
            "options": [
                {"key": "a", "text": "📜 Qal'a Meysteri (soxta muhr yasagan)", "is_correct": True, "outcome": "👑 To'g'ri! Xoin Meyster fosh qilindi va Lord Edrik o'z taxtiga qaytdi!"},
                {"key": "b", "text": "🛡️ Darvoza Boshlig'i", "is_correct": False},
                {"key": "c", "text": "⚓ Kema Kapitani", "is_correct": False},
            ],
            "correct_answer": "a",
            "reward_gold": 8000,
            "reward_food": 10000,
            "reward_iron": 5000,
            "reward_xp": 250,
        },
    ]

    for mdata in sample_missions:
        await add_campaign_mission(session=session, campaign_id=camp.id, **mdata)

    return await get_campaign_with_missions(session, camp.id)
