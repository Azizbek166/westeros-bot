import random
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models
from data.quiz_data import CITADEL_QUIZ_QUESTIONS
from data.council_data import COUNCIL_DILEMMAS
from config import DAILY_QUIZ_LIMIT, DAILY_COUNCIL_LIMIT, DAILY_SECRET_QUEST_LIMIT


# ============================================================
# CITADEL QUIZ SERVICE
# ============================================================

async def get_citadel_quiz_question(
    session: AsyncSession,
    identifier: int
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Sitadel Maester viktorinasi uchun tasodifiy savol va variantlarni olish.
    Savol indeksi (question_id) qaytariladi, shuning uchun sessiya / context xotirasiga ehtiyoj qolmaydi.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", None

    await crud.check_and_reset_daily_limits(session, user)

    if (user.daily_quiz_count or 0) >= DAILY_QUIZ_LIMIT:
        return False, f"⛔ Bugungi viktorina limitingiz ({DAILY_QUIZ_LIMIT}/{DAILY_QUIZ_LIMIT}) tugadi!\nErtaga yangi saboqlar ochiladi.", None

    rem = DAILY_QUIZ_LIMIT - (user.daily_quiz_count or 0)
    q_idx = random.randrange(len(CITADEL_QUIZ_QUESTIONS))
    question, options, _ = CITADEL_QUIZ_QUESTIONS[q_idx]

    return True, "OK", {
        "question_id": q_idx,
        "question": question,
        "options": options,
        "attempts_remaining": rem,
        "daily_limit": DAILY_QUIZ_LIMIT,
        "rewards_info": {
            "gold": 60,
            "iron": 35,
            "xp": 40,
            "penalty_gold": 12,
            "completion_bonus": {"gold": 350, "iron": 200, "xp": 120},
        },
    }


async def submit_citadel_quiz_answer(
    session: AsyncSession,
    identifier: int,
    question_id: int,
    user_answer: int
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Sitadel Maester viktorinasi javobini tekshirish, hisob-kitob qilish va mukofot/jarimani qo'llash.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    await crud.check_and_reset_daily_limits(session, user)

    if (user.daily_quiz_count or 0) >= DAILY_QUIZ_LIMIT:
        return False, "Bugungi viktorina limitingiz tugagan.", {}

    if question_id < 0 or question_id >= len(CITADEL_QUIZ_QUESTIONS):
        return False, "Noto'g'ri savol indeksi.", {}

    question, options, correct_idx = CITADEL_QUIZ_QUESTIONS[question_id]
    is_correct = (user_answer == correct_idx)

    user.daily_quiz_count = (user.daily_quiz_count or 0) + 1
    try:
        await crud.record_guild_quest_activity(session, user.id, "quiz", 1)
    except Exception:
        pass

    gold_change = 0
    iron_change = 0
    xp_change = 0
    completed_all = False

    if is_correct:
        gold_change += 60
        iron_change += 35
        xp_change += 40
        user.gold = (user.gold or 0) + 60
        user.iron = (user.iron or 0) + 35
        user.xp = (user.xp or 0) + 40
        crud.track_user_gold_gain(user, 60)
        msg = (
            "✅ **TO'G'RI JAVOB!**\n\n"
            "Maesterlar bilimingizni yuqori baholashdi.\n"
            f"💰 Mukofot: **+60🪙 oltin, +35⛓️ temir, +40 XP**\n"
            f"📊 Qolgan viktorinalar: **{max(0, DAILY_QUIZ_LIMIT - user.daily_quiz_count)}/{DAILY_QUIZ_LIMIT}**"
        )
    else:
        penalty = min(user.gold or 0, 12)
        user.gold = max(0, (user.gold or 0) - 12)
        gold_change -= penalty
        correct_text = options[correct_idx]
        msg = (
            f"❌ **NOTO'G'RI JAVOB!**\n\n"
            f"To'g'ri javob: **{correct_text}** edi.\n"
            f"💰 Jarima: -12🪙 oltin\n"
            f"📊 Qolgan viktorinalar: **{max(0, DAILY_QUIZ_LIMIT - user.daily_quiz_count)}/{DAILY_QUIZ_LIMIT}**"
        )

    if user.daily_quiz_count == DAILY_QUIZ_LIMIT:
        completed_all = True
        user.gold = (user.gold or 0) + 350
        user.iron = (user.iron or 0) + 200
        user.xp = (user.xp or 0) + 120
        crud.track_user_gold_gain(user, 350)
        gold_change += 350
        iron_change += 200
        xp_change += 120
        msg += (
            f"\n\n🎉 **TABRIKLAYMIZ! KUNLIK VAZIFA BAJARILDI: Maester Saboqlari ({DAILY_QUIZ_LIMIT}/{DAILY_QUIZ_LIMIT})!**\n"
            "🎁 Katta mukofot: **+350🪙 Oltin, +200⛓️ Temir, +120 XP**"
        )

    await session.commit()

    return True, msg, {
        "is_correct": is_correct,
        "correct_option_index": correct_idx,
        "correct_option_text": options[correct_idx],
        "gold_change": gold_change,
        "iron_change": iron_change,
        "xp_change": xp_change,
        "completed_all_daily": completed_all,
        "attempts_remaining": max(0, DAILY_QUIZ_LIMIT - user.daily_quiz_count),
        "user_gold": user.gold,
        "user_iron": user.iron,
        "user_xp": user.xp,
    }


# ============================================================
# ROYAL COUNCIL SERVICE
# ============================================================

async def get_council_question(
    session: AsyncSession,
    identifier: int
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Qirollik Kengashi masalasini olish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", None

    await crud.check_and_reset_daily_limits(session, user)

    if (user.daily_council_count or 0) >= DAILY_COUNCIL_LIMIT:
        return False, f"⛔ Bugungi Kengash masalalari limitingiz ({DAILY_COUNCIL_LIMIT}/{DAILY_COUNCIL_LIMIT}) tugadi!\nYangi masalalar ertaga ko'rib chiqiladi.", None

    rem = DAILY_COUNCIL_LIMIT - (user.daily_council_count or 0)
    c_idx = random.randrange(len(COUNCIL_DILEMMAS))
    q_text, options, _, reward = COUNCIL_DILEMMAS[c_idx]

    return True, "OK", {
        "council_id": c_idx,
        "situation": q_text,
        "options": options,
        "reward_gold": reward,
        "attempts_remaining": rem,
        "daily_limit": DAILY_COUNCIL_LIMIT,
    }


async def submit_council_choice(
    session: AsyncSession,
    identifier: int,
    council_id: int,
    user_choice: int
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Kengash qarorini tekshirish va mukofotni berish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    await crud.check_and_reset_daily_limits(session, user)

    if (user.daily_council_count or 0) >= DAILY_COUNCIL_LIMIT:
        return False, "Bugungi Kengash limitingiz tugagan.", {}

    if council_id < 0 or council_id >= len(COUNCIL_DILEMMAS):
        return False, "Noto'g'ri masala indeksi.", {}

    q_text, options, correct_idx, reward = COUNCIL_DILEMMAS[council_id]
    is_correct = (user_choice == correct_idx)

    user.daily_council_count = (user.daily_council_count or 0) + 1
    gold_gained = 0
    prestige_gained = 0
    completed_all = False

    if is_correct:
        gold_gained = reward
        prestige_gained = 5
        user.gold = (user.gold or 0) + reward
        user.prestige = (user.prestige or 0) + 5
        crud.track_user_gold_gain(user, reward)
        crud.track_user_prestige_gain(user, 5)
        msg = (
            f"✅ **DONO QAROR!**\n\n"
            f"Lordlar sizning tadbirkorligingizga qoyil qolishdi.\n"
            f"💰 Xazinaga: **+{reward}🪙 oltin, +5 Prestige**\n"
            f"📊 Qolgan masalalar: **{max(0, DAILY_COUNCIL_LIMIT - user.daily_council_count)}/{DAILY_COUNCIL_LIMIT}**"
        )
    else:
        msg = (
            "❌ **NOTO'G'RI QAROR!**\n\n"
            "Bu qaror aholi orasida norozilikka sabab bo'ldi. Mukofot berilmadi.\n"
            f"📊 Qolgan masalalar: **{max(0, DAILY_COUNCIL_LIMIT - user.daily_council_count)}/{DAILY_COUNCIL_LIMIT}**"
        )

    if user.daily_council_count == DAILY_COUNCIL_LIMIT:
        completed_all = True
        user.gold = (user.gold or 0) + 350
        user.food = (user.food or 0) + 600
        user.xp = (user.xp or 0) + 120
        crud.track_user_gold_gain(user, 350)
        msg += (
            f"\n\n🎉 **TABRIKLAYMIZ! KUNLIK VAZIFA BAJARILDI: Kengash Maslahati ({DAILY_COUNCIL_LIMIT}/{DAILY_COUNCIL_LIMIT})!**\n"
            "🎁 Mukofot: **+350🪙 Oltin, +600🌾 Oziq-ovqat, +120 XP**"
        )

    await session.commit()

    return True, msg, {
        "is_correct": is_correct,
        "gold_gained": gold_gained,
        "prestige_gained": prestige_gained,
        "completed_all_daily": completed_all,
        "attempts_remaining": max(0, DAILY_COUNCIL_LIMIT - user.daily_council_count),
        "user_gold": user.gold,
        "user_prestige": user.prestige,
    }
