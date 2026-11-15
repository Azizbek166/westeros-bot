"""
REFERRAL SERVICE FOR THE IRON THRONE RPG
Boshqaruv: t.me/<bot>?start=ref_<id>
Faqat yangi o'yinchi, o'zini o'zi taklif qila olmaydi.
Mukofot taklif etilgan o'yinchi xonadon tanlagandan KEYIN tranzaksiyada beriladi.
"""
from typing import Optional, Tuple, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import models
from config import REFERRAL_REWARD_REFERRER, REFERRAL_REWARD_NEW_PLAYER


async def process_referral_on_registration(
    session: AsyncSession,
    new_user: models.User,
    referrer_tg_id: int,
) -> Tuple[bool, str]:
    """
    Yangi o'yinchi /start ref_<id> orqali kelganda taklif qiluvchini belgilash.
    Mukofot bu yerda berilmaydi (xonadon tanlagandan keyin beriladi).
    """
    if not referrer_tg_id or referrer_tg_id == new_user.telegram_id:
        return False, "O'zini o'zi taklif qilish mumkin emas."

    # Referrer bazada bormi?
    res = await session.execute(
        select(models.User).where(models.User.telegram_id == referrer_tg_id)
    )
    referrer = res.scalar_one_or_none()
    if not referrer:
        return False, "Taklif qilgan Lord topilmadi."

    new_user.referred_by_id = referrer.id
    return True, f"Taklif qiluvchi Lord #{referrer.id} biriktirildi."


async def award_referral_reward_after_house_selection(
    session: AsyncSession,
    user_id: int,
    bot_app=None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Yangi o'yinchi xonadon tanlagandan keyin taklif qiluvchiga va yangi o'yinchiga mukofot berish.
    """
    user = await session.get(models.User, user_id)
    if not user:
        res_u = await session.execute(select(models.User).where(models.User.telegram_id == user_id))
        user = res_u.scalar_one_or_none()

    if not user or not user.referred_by_id:
        return False, "Referral mavjud emas.", {}

    referrer = await session.get(models.User, user.referred_by_id)
    if not referrer:
        return False, "Taklif qiluvchi topilmadi.", {}

    # Mukofot allaqachon berilganini tekshirish (uq_user_achievement yoki event_state orqali)
    res_claim = await session.execute(
        select(models.EventState).where(
            models.EventState.event_name == f"ref_reward_u{user.id}"
        )
    )
    if res_claim.scalar_one_or_none():
        return False, "Referral mukofoti allaqachon berilgan.", {}

    # Referrer mukofoti
    referrer.gold = (referrer.gold or 0) + REFERRAL_REWARD_REFERRER["gold"]
    referrer.food = (referrer.food or 0) + REFERRAL_REWARD_REFERRER["food"]
    referrer.iron = (referrer.iron or 0) + REFERRAL_REWARD_REFERRER["iron"]
    referrer.prestige = (referrer.prestige or 0) + REFERRAL_REWARD_REFERRER["prestige"]

    # Yangi o'yinchi mukofoti
    user.gold = (user.gold or 0) + REFERRAL_REWARD_NEW_PLAYER["gold"]
    user.food = (user.food or 0) + REFERRAL_REWARD_NEW_PLAYER["food"]
    user.iron = (user.iron or 0) + REFERRAL_REWARD_NEW_PLAYER["iron"]
    user.prestige = (user.prestige or 0) + REFERRAL_REWARD_NEW_PLAYER["prestige"]

    # Mark record
    session.add(models.EventState(
        event_name=f"ref_reward_u{user.id}",
        data_json=f'{{"referrer_id": {referrer.id}, "invited_id": {user.id}}}',
        is_active=True,
    ))

    # Yutuqni tekshirish
    try:
        from services.achievement_service import unlock_achievement
        await unlock_achievement(session, referrer.id, "referral_pioneer", bot_app=bot_app)
    except Exception:
        pass

    # Xabarnoma yuborish
    if bot_app and referrer.telegram_id:
        try:
            msg = (
                f"🎉 **DO'STINGIZ XONADON TANLADI! REFERAL MUKOFOTI!**\n\n"
                f"Siz taklif qilgan Lord **{user.full_name}** Westeros qasamyodini qabul qildi!\n\n"
                f"🎁 **Sizga topshirilgan mukofot:**\n"
                f"• 🪙 +{REFERRAL_REWARD_REFERRER['gold']:,} Oltin\n"
                f"• 🌾 +{REFERRAL_REWARD_REFERRER['food']:,} Bug'doy\n"
                f"• ⛓️ +{REFERRAL_REWARD_REFERRER['iron']:,} Temir\n"
                f"• ⭐ +{REFERRAL_REWARD_REFERRER['prestige']} Nufuz"
            )
            await bot_app.bot.send_message(chat_id=referrer.telegram_id, text=msg, parse_mode="Markdown")
        except Exception:
            pass

    return True, "Referal mukofotlari berildi!", {
        "referrer_id": referrer.id,
        "new_player_id": user.id,
        "referrer_rewards": REFERRAL_REWARD_REFERRER,
        "new_player_rewards": REFERRAL_REWARD_NEW_PLAYER,
    }


async def get_referral_info(session: AsyncSession, user_id: int) -> Dict[str, Any]:
    """O'yinchining referal statistikasi va taklif havolasi"""
    user = await session.get(models.User, user_id)
    if not user:
        res_u = await session.execute(select(models.User).where(models.User.telegram_id == user_id))
        user = res_u.scalar_one_or_none()

    if not user:
        return {}

    # Taklif qilingan o'yinchilar
    res = await session.execute(
        select(models.User).where(models.User.referred_by_id == user.id)
    )
    invited = list(res.scalars().all())
    active_count = sum(1 for u in invited if u.house_id is not None)

    return {
        "telegram_id": user.telegram_id,
        "total_invited": len(invited),
        "active_recruits": active_count,
        "total_gold_earned": active_count * REFERRAL_REWARD_REFERRER["gold"],
        "total_prestige_earned": active_count * REFERRAL_REWARD_REFERRER["prestige"],
    }
