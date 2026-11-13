"""
The Iron Throne RPG — AI Council Advisor Service Layer.
Manages player quotas, DB state extraction, moderation logging,
and invokes the dual-mode advisor engine.
"""
import logging
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    AI_USER_DAILY_LIMIT,
    AI_VIP_DAILY_LIMIT,
    AI_GLOBAL_DAILY_LIMIT,
)
from database import models, crud
from core.ai_advisor import (
    moderate_user_input,
    check_and_increment_global_limit,
    get_cached_answer,
    store_cached_answer,
    call_gemini_advisor_api,
    generate_heuristic_advice,
)
from services.season_service import get_or_create_active_season, get_or_create_player_season_state

logger = logging.getLogger(__name__)

QUICK_PROMPT_SUGGESTIONS = [
    "🎯 Hozir nima qilay?",
    "⚔️ Armiyani qanday muvozanatlashtiray?",
    "🐉 Ajdahoni qanday kuchaytiraman?",
    "💰 Xazinani ko'paytirish sirlari qanday?",
    "🏰 Qal'a egallash va mudofaa taktikasi",
    "🌟 Season Pass va ochkolar qanday yig'iladi?",
]


def _get_player_ai_limit(user: models.User) -> int:
    """O'yinchining VIP maqomiga qarab kunlik AI limitini aniqlash"""
    has_vip = False
    if getattr(user, "vip_tier", None):
        vip_until = getattr(user, "vip_until", None)
        if vip_until and vip_until > datetime.utcnow():
            has_vip = True
    return AI_VIP_DAILY_LIMIT if has_vip else AI_USER_DAILY_LIMIT


async def get_ai_advisor_status(
    session: AsyncSession,
    user: models.User,
) -> Dict[str, Any]:
    """Mini App va Bot uchun AI maslahatchisi statusi va limitlari"""
    await crud.check_and_reset_daily_limits(session, user)

    daily_limit = _get_player_ai_limit(user)
    used_today = getattr(user, "daily_ai_requests_count", 0) or 0
    remaining = max(0, daily_limit - used_today)

    return {
        "success": True,
        "daily_limit": daily_limit,
        "used_today": used_today,
        "remaining_today": remaining,
        "is_vip": daily_limit > AI_USER_DAILY_LIMIT,
        "quick_prompts": QUICK_PROMPT_SUGGESTIONS,
    }


async def _extract_player_state(
    session: AsyncSession,
    user: models.User,
) -> Dict[str, Any]:
    """Server ma'lumotlar bazasidan o'yinchining to'liq va xavfsiz holatini yig'ish"""
    # 1. Xonadon
    house_name = "Xonadonsiz"
    house_power = 0
    try:
        if user.house_id:
            house = await session.get(models.House, user.house_id)
            if house:
                house_name = getattr(house, "name", "Xonadonsiz")
                house_power = getattr(house, "prestige", 0) or getattr(house, "power", 0) or 0
    except Exception as e:
        logger.warning(f"AI state extract house error: {e}")

    # 2. Armiya
    army = None
    try:
        army_res = await session.execute(
            select(models.Army).where(models.Army.user_id == user.id)
        )
        army = army_res.scalar_one_or_none()
    except Exception as e:
        logger.warning(f"AI state extract army error: {e}")

    # 3. Qal'alar soni
    castles_count = 0
    try:
        terr_count_res = await session.execute(
            select(func.count(models.Territory.id)).where(
                models.Territory.conquered_by_user_id == user.id
            )
        )
        castles_count = terr_count_res.scalar() or 0
    except Exception as e:
        logger.warning(f"AI state extract castles error: {e}")

    # 4. Ajdaho
    dragon_name = "Mavjud emas"
    dragon_level = 0
    dragon_hunger = 0
    try:
        dragon_res = await session.execute(
            select(models.Dragon).where(models.Dragon.user_id == user.id)
        )
        dragon = dragon_res.scalar_one_or_none()
        if dragon:
            dragon_name = dragon.name or "Ajdaho"
            dragon_level = dragon.level or 1
            dragon_hunger = getattr(dragon, "hunger", 50) or 50
    except Exception as e:
        logger.warning(f"AI state extract dragon error: {e}")

    # 5. Mavsum holati
    season_number = 1
    season_points = 0
    try:
        active_season = await get_or_create_active_season(session)
        season_number = active_season.season_number if active_season else 1
        tracker = await get_or_create_player_season_state(session, user.id, season_number)
        season_points = tracker.season_points if tracker else 0
    except Exception as e:
        logger.warning(f"AI state extract season error: {e}")

    # 6. Tinchlik qalqoni
    shield_status = "Yo'q"
    if user.peace_shield_until and user.peace_shield_until > datetime.utcnow():
        rem_min = int((user.peace_shield_until - datetime.utcnow()).total_seconds() / 60)
        shield_status = f"Faol ({rem_min} daqiqa qoldi)"

    return {
        "user_id": user.id,
        "username": user.username or getattr(user, "full_name", None) or f"Lord #{user.id}",
        "house_name": house_name,
        "house_power": house_power,
        "level": user.level or 1,
        "title": getattr(user, "title", "Zodagon") or "Zodagon",
        "gold": user.gold or 0,
        "food": user.food or 0,
        "iron": user.iron or 0,
        "prestige": user.prestige or 0,
        "infantry": army.infantry if army else 0,
        "archers": army.archers if army else 0,
        "cavalry": army.cavalry if army else 0,
        "spearmen": army.spearmen if army else 0,
        "catapults": getattr(army, "catapults", 0) if army else 0,
        "siege_towers": getattr(army, "siege_towers", 0) if army else 0,
        "castles_count": castles_count,
        "dragon_name": dragon_name,
        "dragon_level": dragon_level,
        "dragon_hunger": dragon_hunger,
        "shield_status": shield_status,
        "season_number": season_number,
        "season_points": season_points,
        "daily_duel_count": getattr(user, "daily_duel_count", 0) or 0,
        "daily_quiz_count": getattr(user, "daily_quiz_count", 0) or 0,
        "daily_caravan_count": getattr(user, "daily_caravan_send_count", 0) or 0,
    }


async def ask_council_advisor(
    session: AsyncSession,
    user: models.User,
    query: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Kengash Maslahatchisiga savol berish asosiy xizmati.
    Qaytaradi: (ok, answer, metadata)
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return False, "Lordim, maslahatchiga bermoqchi bo'lgan savolingizni yozing.", {}

    if len(clean_q) > 300:
        return False, "Lordim, savolingiz juda uzun (maksimal 300 ta belgi). Iltimos, qisqaroq bayon qiling.", {}

    # Kunlik limitlarni yangilash
    await crud.check_and_reset_daily_limits(session, user)

    daily_limit = _get_player_ai_limit(user)
    used_today = getattr(user, "daily_ai_requests_count", 0) or 0
    if used_today >= daily_limit:
        msg = (
            f"❌ **Kunlik limitingiz tugagan!**\n\n"
            f"Siz bugun Kengash Meysteriga ajratilgan {daily_limit} ta bepul savol limitingizdan to'liq foydalandingiz.\n"
            f"Ertaga yana yangi savollar bilan murojaat qilishingiz mumkin, Lordim!"
        )
        return False, msg, {"daily_limit": daily_limit, "used_today": used_today, "remaining": 0}

    # Moderatsiya va Prompt Injection himoyasi
    is_safe, refusal, mod_cat = moderate_user_input(clean_q)
    if not is_safe:
        # Xavfsizlik jurnaliga yozish
        try:
            log_entry = models.AIModerationLog(
                user_id=user.id,
                telegram_id=user.telegram_id,
                query_text=clean_q[:500],
                category=mod_cat or "abuse",
                created_at=datetime.utcnow(),
            )
            session.add(log_entry)
            await session.commit()
        except Exception as e:
            logger.warning(f"AIModerationLog yozishda xatolik: {e}")

        return False, refusal, {"daily_limit": daily_limit, "used_today": used_today, "remaining": daily_limit - used_today}

    # Umumiy server byudjeti tekshiruvi
    if not check_and_increment_global_limit():
        busy_msg = (
            "🏛️ **Buyuk Meyster Kengashi dam olmoqda:**\n"
            "Bugun butun Vesteros bo'ylab Qirollik Kengashiga juda ko'p murojaatlar kelib tushdi. "
            "Kengash meysterlari charchashdi va yangi kunga qadar xizmatni to'xtatishdi. Ertaga tongda qayta murojaat qiling, Lordim!"
        )
        return False, busy_msg, {"daily_limit": daily_limit, "used_today": used_today, "remaining": daily_limit - used_today}

    # Keshni tekshirish
    cached_ans = get_cached_answer(clean_q)
    if cached_ans:
        # Keshdan olinganda ham o'yinchining kunlik hisoblagichini oshiramiz
        user.daily_ai_requests_count = used_today + 1
        await session.commit()
        return True, cached_ans, {
            "daily_limit": daily_limit,
            "used_today": user.daily_ai_requests_count,
            "remaining": max(0, daily_limit - user.daily_ai_requests_count),
            "cached": True,
        }

    try:
        # O'yinchining serverdagi joriy ko'rsatkichlarini olish
        player_state = await _extract_player_state(session, user)

        # 1. Google Gemini API ga so'rov jo'natishga urinish
        ai_answer = await call_gemini_advisor_api(clean_q, player_state)

        # 2. Agar API ishlamasa yoki sozlanmagan bo'lsa, ichki Westeros Maslahatchisidan foydalanish
        if not ai_answer:
            ai_answer = generate_heuristic_advice(clean_q, player_state)
    except Exception as e:
        logger.error(f"AI maslahatchisi hisoblashda kutilmagan xatolik: {e}")
        ai_answer = generate_heuristic_advice(clean_q, {"level": user.level or 1, "gold": user.gold or 0})

    # Keshga saqlash
    store_cached_answer(clean_q, ai_answer)

    # O'yinchining so'rov hisobini oshirish
    user.daily_ai_requests_count = used_today + 1
    await session.commit()

    return True, ai_answer, {
        "daily_limit": daily_limit,
        "used_today": user.daily_ai_requests_count,
        "remaining": max(0, daily_limit - user.daily_ai_requests_count),
        "cached": False,
    }
