"""
PROMO CODE SERVICE FOR THE IRON THRONE RPG
Tranzaksiya, limit va muddat tekshiruvlari bilan to'liq himoyalangan.
"""
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import models, crud


async def create_promo_code_service(
    session: AsyncSession,
    code: str,
    gold: int = 0,
    food: int = 0,
    iron: int = 0,
    prestige: int = 0,
    vip_days: int = 0,
    max_uses: int = 100,
    expires_at: Optional[datetime] = None,
) -> Tuple[bool, str, Optional[models.PromoCode]]:
    """Yangi promo-kod yaratish (Admin tomonidan)"""
    clean_code = (code or "").strip().upper()
    if not clean_code or len(clean_code) < 3:
        return False, "Promo-kod kamida 3 ta belgidan iborat bo'lishi kerak.", None

    res = await session.execute(select(models.PromoCode).where(models.PromoCode.code == clean_code))
    if res.scalar_one_or_none():
        return False, "Bu nomdagi promo-kod allaqachon mavjud.", None

    promo = models.PromoCode(
        code=clean_code,
        reward_gold=gold,
        reward_food=food,
        reward_iron=iron,
        reward_prestige=prestige,
        reward_vip_days=vip_days,
        max_uses=max_uses,
        expires_at=expires_at,
        is_active=True,
    )
    session.add(promo)
    await session.commit()
    await session.refresh(promo)
    return True, f"Promo-kod '{clean_code}' muvaffaqiyatli yaratildi!", promo


async def redeem_promo_code_service(
    session: AsyncSession,
    user_id: int,
    code_str: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Promo-kodni ishlatish:
    1. Kod mavjudligi va faolligi.
    2. Muddat tugamaganligi.
    3. Ishlatilish limiti tugamaganligi (max_uses).
    4. Foydalanuvchi bu kodni oldin ishlatmaganligi (bir o'yinchiga faqat bir marta).
    5. Mukofotlarni atomik o'tkazish.
    """
    clean_code = (code_str or "").strip().upper()
    if not clean_code:
        return False, "Promo-kodni kiriting.", {}

    user = await crud.get_user_any(session, user_id, load_relations=False)

    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    # Promo-kodni qidirish
    res = await session.execute(
        select(models.PromoCode).where(models.PromoCode.code == clean_code)
    )
    promo = res.scalar_one_or_none()
    if not promo or not promo.is_active:
        return False, "Bunday promo-kod mavjud emas yoki faol emas.", {}

    # Muddat tekshiruvi
    now = datetime.utcnow()
    if promo.expires_at and promo.expires_at < now:
        return False, "Ushbu promo-kodning amal qilish muddati tugagan.", {}

    # Limit tekshiruvi
    if promo.current_uses >= promo.max_uses:
        return False, "Ushbu promo-koddan foydalanish limiti tugagan.", {}

    # Bir martalik tekshiruv (uq_promo_code_user)
    res_usage = await session.execute(
        select(models.PromoCodeUsage).where(
            models.PromoCodeUsage.promo_code_id == promo.id,
            models.PromoCodeUsage.user_id == user.id,
        )
    )
    if res_usage.scalar_one_or_none():
        return False, "Siz ushbu promo-kodni allaqachon ishlatgansiz!", {}

    # Tranzaksiyada mukofotlarni berish
    user.gold = (user.gold or 0) + (promo.reward_gold or 0)
    user.food = (user.food or 0) + (promo.reward_food or 0)
    user.iron = (user.iron or 0) + (promo.reward_iron or 0)
    user.prestige = (user.prestige or 0) + (promo.reward_prestige or 0)

    if promo.reward_vip_days and promo.reward_vip_days > 0:
        base_vip = user.vip_until if (user.vip_until and user.vip_until > now) else now
        from datetime import timedelta
        user.vip_until = base_vip + timedelta(days=promo.reward_vip_days)
        if not user.vip_tier:
            user.vip_tier = "noble"

    # Foydalanish sonini oshirish
    promo.current_uses += 1

    # Yozuv qoldirish
    usage = models.PromoCodeUsage(
        promo_code_id=promo.id,
        user_id=user.id,
        telegram_id=user.telegram_id,
        used_at=now,
    )
    session.add(usage)
    await session.commit()

    rewards_list = []
    if promo.reward_gold:
        rewards_list.append(f"+{promo.reward_gold:,} 🪙 Oltin")
    if promo.reward_food:
        rewards_list.append(f"+{promo.reward_food:,} 🌾 Bug'doy")
    if promo.reward_iron:
        rewards_list.append(f"+{promo.reward_iron:,} ⛓️ Temir")
    if promo.reward_prestige:
        rewards_list.append(f"+{promo.reward_prestige} ⭐ Nufuz")
    if promo.reward_vip_days:
        rewards_list.append(f"+{promo.reward_vip_days} kunlik 👑 VIP statusi")

    rewards_block = "• " + "\n• ".join(rewards_list) if rewards_list else "• Resurslar o'zgarishsiz"
    return True, (
        f"🎉 *Promo-kod qabul qilindi va hisobingizga qo'shildi!*\n\n"
        f"🎁 *Qo'shilgan mukofotlar:*\n{rewards_block}\n\n"
        f"💰 *Joriy balansingiz:*\n"
        f"• 🪙 Oltin: *{user.gold:,}*\n"
        f"• 🌾 Bug'doy: *{user.food:,}*\n"
        f"• ⛓️ Temir: *{user.iron:,}*\n"
        f"• ⭐ Nufuz: *{user.prestige:,}*"
    ), {
        "gold": promo.reward_gold,
        "food": promo.reward_food,
        "iron": promo.reward_iron,
        "prestige": promo.reward_prestige,
        "new_gold": user.gold,
        "new_food": user.food,
        "new_iron": user.iron,
        "new_prestige": user.prestige,
    }


async def list_active_promo_codes(session: AsyncSession) -> List[Dict[str, Any]]:
    """Admin uchun barcha promo-kodlar ro'yxati"""
    res = await session.execute(
        select(models.PromoCode).order_by(models.PromoCode.created_at.desc())
    )
    promos = res.scalars().all()
    out = []
    for p in promos:
        out.append({
            "id": p.id,
            "code": p.code,
            "uses": f"{p.current_uses}/{p.max_uses}",
            "is_active": p.is_active,
            "rewards": f"🪙{p.reward_gold:,} 🌾{p.reward_food:,} ⛓️{p.reward_iron:,}",
            "expires": p.expires_at.strftime("%Y-%m-%d") if p.expires_at else "Cheksiz",
        })
    return out
