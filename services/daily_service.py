from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models


async def get_daily_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Kunlik tuhfalar, 7 kunlik streak va 4 ta faollik vazifalari holati to'liq ko'rinishi.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return None

    await crud.check_and_reset_daily_limits(session, user)

    today_str = crud.get_game_today_str()
    streak_count = user.streak_count or 1
    is_streak_claimed = (user.last_streak_date == today_str)

    # 4 ta kunlik kvestlar holati
    q_data = await crud.get_daily_quests_data(session, user)

    # 7 kunlik taqvim konfiguratsiyasi
    calendar_rewards = []
    for day in range(1, 8):
        rew = crud.STREAK_REWARDS.get(day, {})
        calendar_rewards.append({
            "day": day,
            "title": rew.get("title", f"{day}-Kun"),
            "gold": rew.get("gold", 0),
            "food": rew.get("food", 0),
            "iron": rew.get("iron", 0),
            "prestige": rew.get("prestige", 0),
            "xp": rew.get("xp", 0),
            "extra_desc": rew.get("extra_desc", ""),
            "is_current": (day == streak_count),
            "is_completed": (day < streak_count or (day == streak_count and is_streak_claimed)),
        })

    return {
        "user_id": user.id,
        "streak": {
            "current_day": streak_count,
            "is_claimed_today": is_streak_claimed,
            "last_streak_date": user.last_streak_date,
            "calendar": calendar_rewards,
        },
        "daily_quests": q_data["quests"],
        "done_quests_count": q_data["done_count"],
        "total_quests_count": q_data["total_count"],
        "grand_done": q_data["grand_done"],
        "grand_claimed": q_data["grand_claimed"],
    }


async def claim_daily_streak_service(
    session: AsyncSession,
    identifier: int
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    7 kunlik kirish (streak) mukofotini qabul qilish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    ok, msg = await crud.claim_daily_bonus(session, user.id)
    return ok, msg, {
        "user_id": user.id,
        "streak_count": user.streak_count,
        "gold": user.gold,
        "food": user.food,
        "iron": user.iron,
        "prestige": user.prestige,
        "xp": user.xp,
    }


async def claim_daily_quest_service(
    session: AsyncSession,
    identifier: int,
    quest_key: str
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Kunlik faollik vazifasi (yoki grand chest) mukofotini qabul qilish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    ok, msg = await crud.claim_daily_quest_reward(session, user.id, quest_key)
    return ok, msg, {
        "user_id": user.id,
        "quest_key": quest_key,
        "gold": user.gold,
        "food": user.food,
        "iron": user.iron,
        "prestige": user.prestige,
    }
