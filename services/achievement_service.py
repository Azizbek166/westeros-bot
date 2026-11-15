"""
ACHIEVEMENT SERVICE FOR THE IRON THRONE RPG
Barcha yutuqlar, mukofotlar va tekshiruvlar markazlashtirilgan.
"""
from typing import Optional, Tuple, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import models
from config import ACHIEVEMENTS_CONFIG


async def unlock_achievement(
    session: AsyncSession,
    user_id: int,
    achievement_code: str,
    bot_app=None,
) -> Tuple[bool, str, Optional[models.UserAchievement]]:
    """
    Yutuqni ochish va mukofotni berish (idempotent, bir yutuq faqat 1 marta ochiladi).
    Mavjud handlerlardan faqat try/except ichida bitta chaqiruv bilan ishlatiladi.
    """
    cfg = ACHIEVEMENTS_CONFIG.get(achievement_code)
    if not cfg:
        return False, "Noma'lum yutuq kodi.", None

    user = await session.get(models.User, user_id)
    if not user:
        res_u = await session.execute(select(models.User).where(models.User.telegram_id == user_id))
        user = res_u.scalar_one_or_none()

    if not user:
        return False, "Foydalanuvchi topilmadi.", None

    real_user_id = user.id

    # Allaqachon ochilganini tekshirish
    res = await session.execute(
        select(models.UserAchievement).where(
            models.UserAchievement.user_id == real_user_id,
            models.UserAchievement.achievement_code == achievement_code,
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        return False, "Yutuq allaqachon ochilgan.", existing

    # Yangi yutuq yaratish
    ach = models.UserAchievement(
        user_id=user.id,
        telegram_id=user.telegram_id,
        achievement_code=achievement_code,
        title=cfg["title"],
        reward_gold=cfg.get("gold", 0),
        reward_iron=cfg.get("iron", 0),
        reward_food=cfg.get("food", 0),
        reward_prestige=cfg.get("prestige", 0),
    )
    session.add(ach)

    # Mukofotlarni berish
    user.gold = (user.gold or 0) + cfg.get("gold", 0)
    user.iron = (user.iron or 0) + cfg.get("iron", 0)
    user.food = (user.food or 0) + cfg.get("food", 0)
    user.prestige = (user.prestige or 0) + cfg.get("prestige", 0)

    # Xabarnoma yuborish
    if bot_app and user.telegram_id:
        try:
            msg = (
                f"🏆 **YANGI YUTUQ OCHILDI!**\n\n"
                f"**{cfg['title']}**\n"
                f"_{cfg['desc']}_\n\n"
                f"🎁 **Mukofot:** +{cfg.get('gold', 0):,} 🪙 Oltin, +{cfg.get('food', 0):,} 🌾 Bug'doy, +{cfg.get('iron', 0):,} ⛓️ Temir, +{cfg.get('prestige', 0)} ⭐ Nufuz!"
            )
            await bot_app.bot.send_message(chat_id=user.telegram_id, text=msg, parse_mode="Markdown")
        except Exception:
            pass

    return True, f"Yutuq ochildi: {cfg['title']}", ach


async def get_user_achievements(
    session: AsyncSession,
    user_id: int,
) -> Dict[str, Any]:
    """Foydalanuvchining barcha yutuqlari holati (ochilgan va qulflangan)"""
    user = await session.get(models.User, user_id)
    if not user:
        res_u = await session.execute(select(models.User).where(models.User.telegram_id == user_id))
        user = res_u.scalar_one_or_none()

    real_user_id = user.id if user else user_id

    res = await session.execute(
        select(models.UserAchievement).where(models.UserAchievement.user_id == real_user_id)
    )
    unlocked = {a.achievement_code: a for a in res.scalars().all()}

    achievements_list = []
    total_unlocked = len(unlocked)
    total_count = len(ACHIEVEMENTS_CONFIG)

    for code, cfg in ACHIEVEMENTS_CONFIG.items():
        is_done = code in unlocked
        ach_item = {
            "code": code,
            "title": cfg["title"],
            "desc": cfg["desc"],
            "gold": cfg["gold"],
            "food": cfg["food"],
            "iron": cfg["iron"],
            "prestige": cfg["prestige"],
            "is_unlocked": is_done,
            "unlocked_at": unlocked[code].unlocked_at.strftime("%Y-%m-%d %H:%M") if is_done else None,
        }
        achievements_list.append(ach_item)

    return {
        "user_id": user_id,
        "total_count": total_count,
        "unlocked_count": total_unlocked,
        "progress_pct": int((total_unlocked / max(1, total_count)) * 100),
        "achievements": achievements_list,
    }
