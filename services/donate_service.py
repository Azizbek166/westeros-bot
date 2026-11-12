"""
VIP & Premium Cosmetics Service for Telegram Mini App and Bot.
STRICT RULE: Zero Pay-To-Win. No purchased item may grant troop counts,
combat stats, damage boosts, or core resource advantages.
All offerings are strictly aesthetic (skins, frames, titles, effects) or
non-combat quality-of-life (e.g. 1-click tax collection, live profile video).
"""
import uuid
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import crud, models
from core.cosmetics import (
    COSMETICS_CATALOG,
    get_cosmetic_item,
    get_all_cosmetics_grouped,
    get_user_cosmetics,
    equip_cosmetic,
    grant_cosmetic_item,
    record_payment_transaction,
    apply_legacy_vip_compensation,
)


VIP_TIERS_INFO = {
    "noble": {
        "name": "👑 Oliyjanob Lord (Noble VIP)",
        "badge": "👑 NOBLE VIP",
        "price_stars": 75,
        "price_uzs": "15,000 so'm",
        "duration_days": 30,
        "perks": [
            "⚡ Barcha qal'alardan bir marta bosishda soliq yig'ish (1-Click Tax)",
            "🎥 Profilga dumaloq video xabar yoki jonli video yuklash huquqi",
            "👑 Chat va Mini Appda zarhal oltin [VIP] nishoni",
            "📊 Kengaytirilgan jang statistikasi va harakatlar tarixi filtri",
            "🚫 Jangda HECH QANDAY armiya, kuch yoki resurs ustunligi bermaydi (100% Halol)!",
        ],
    },
}


async def get_donate_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Kosmetika do'koni ma'lumotlari, sotib olingan va taqilgan buyumlar.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        return None

    # Check and migrate legacy VIP if present
    if user.vip_tier and user.vip_tier in ("lord", "knight", "dragonlord", "sovereign"):
        await apply_legacy_vip_compensation(session, user)

    # Owned cosmetics
    owned_records = await get_user_cosmetics(session, user.id)
    owned_ids = [c.item_id for c in owned_records]

    # Grouped catalog
    catalog_grouped = get_all_cosmetics_grouped()

    now = datetime.utcnow()
    is_vip_active = bool(user.vip_until and user.vip_until > now)

    equipped_map = {
        "avatar_frame": user.avatar_frame,
        "castle_skin": user.castle_skin,
        "dragon_skin": user.dragon_skin,
        "message_effect": user.message_effect,
        "title": user.title,
    }

    return {
        "user_id": user.id,
        "current_vip_tier": user.vip_tier or "free",
        "vip_until": user.vip_until.isoformat() if user.vip_until else None,
        "is_vip_active": is_vip_active,
        "equipped": equipped_map,
        "owned_items": owned_ids,
        "has_starter_pack": bool(getattr(user, "has_starter_pack", False)),
        "catalog": catalog_grouped,
        "vip_info": VIP_TIERS_INFO["noble"],
    }


async def equip_user_cosmetic_service(
    session: AsyncSession,
    user: models.User,
    item_id: str,
) -> Tuple[bool, str]:
    """Kosmetik buyumni taqish yoki yechish"""
    return await equip_cosmetic(session, user, item_id)


async def buy_cosmetic_service(
    session: AsyncSession,
    user: models.User,
    item_id: str,
    payment_provider: str = "telegram_stars",
    idempotency_key: Optional[str] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Kosmetik buyumni sotib olish va darhol biriktirish"""
    item = get_cosmetic_item(item_id)
    if not item:
        return False, "Bunday kosmetik buyum topilmadi.", {}

    if not idempotency_key:
        idempotency_key = f"tx_{user.id}_{item_id}_{uuid.uuid4().hex[:12]}"

    # Already owned check (for permanent single items)
    if item.get("is_permanent") and item.get("category") != "starter_pack":
        owned = await get_user_cosmetics(session, user.id)
        if any(c.item_id == item_id for c in owned):
            return False, "Sizda ushbu kosmetik buyum allaqachon mavjud.", {}

    if item.get("category") == "starter_pack" and getattr(user, "has_starter_pack", False):
        return False, "Siz allaqachon Starter Pack to'plamini xarid qilgansiz.", {}

    # Record payment transaction (Idempotent)
    ok, tx_msg, tx = await record_payment_transaction(
        session=session,
        telegram_id=user.telegram_id,
        item_id=item_id,
        provider=payment_provider,
        idempotency_key=idempotency_key,
        amount_stars=item.get("price_stars", 0),
        amount_uzs=item.get("price_uzs", 0),
        user_id=user.id,
    )
    if not ok:
        return False, tx_msg, {}

    # Grant cosmetic item
    grant_ok, grant_msg = await grant_cosmetic_item(session, user, item_id)
    return grant_ok, grant_msg, {
        "item_id": item_id,
        "item_name": item["name"],
        "category": item["category"],
        "idempotency_key": idempotency_key,
    }


async def gift_cosmetic_service(
    session: AsyncSession,
    sender: models.User,
    recipient_telegram_id: int,
    item_id: str,
    payment_provider: str = "telegram_stars",
    idempotency_key: Optional[str] = None,
) -> Tuple[bool, str]:
    """Do'stga yoki xonadon a'zosiga kosmetika sovg'a qilish"""
    item = get_cosmetic_item(item_id)
    if not item:
        return False, "Bunday kosmetik buyum topilmadi."

    # Find recipient
    recipient = await crud.get_user_by_telegram_id(session, recipient_telegram_id)
    if not recipient:
        return False, "Sovg'a qabul qiluvchi Lord topilmadi. U avval botdan ro'yxatdan o'tgan bo'lishi kerak."

    if recipient.id == sender.id:
        return False, "O'zingizga sovg'a qila olmaysiz. To'g'ridan-to'g'ri xarid qiling."

    if not idempotency_key:
        idempotency_key = f"gift_{sender.id}_{recipient.id}_{item_id}_{uuid.uuid4().hex[:12]}"

    # Record transaction
    ok, tx_msg, _ = await record_payment_transaction(
        session=session,
        telegram_id=sender.telegram_id,
        item_id=item_id,
        provider=payment_provider,
        idempotency_key=idempotency_key,
        amount_stars=item.get("price_stars", 0),
        amount_uzs=item.get("price_uzs", 0),
        is_gift=True,
        recipient_telegram_id=recipient_telegram_id,
        user_id=sender.id,
    )
    if not ok:
        return False, tx_msg

    # Grant to recipient
    grant_ok, grant_msg = await grant_cosmetic_item(
        session,
        recipient,
        item_id,
        is_gift=True,
        gifted_by_telegram_id=sender.telegram_id,
    )
    return grant_ok, f"Sovg'a Lord {recipient.full_name or recipient.username} ga muvaffaqiyatli yetkazildi!"


async def get_payment_transactions_history(
    session: AsyncSession,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Admin panel uchun so'nggi xaridlar jurnali"""
    res = await session.execute(
        select(models.PaymentTransaction).order_by(models.PaymentTransaction.id.desc()).limit(limit)
    )
    txs = res.scalars().all()
    result = []
    for t in txs:
        result.append({
            "id": t.id,
            "user_id": t.user_id,
            "telegram_id": t.telegram_id,
            "item_id": t.item_id,
            "item_name": t.item_name,
            "provider": t.provider,
            "amount_stars": t.amount_stars,
            "amount_uzs": t.amount_uzs,
            "status": t.status,
            "is_gift": t.is_gift,
            "recipient_telegram_id": t.recipient_telegram_id,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else "-",
            "refunded_at": t.refunded_at.strftime("%Y-%m-%d %H:%M:%S") if t.refunded_at else None,
        })
    return result


async def refund_payment_transaction(
    session: AsyncSession,
    tx_id: int,
    admin_telegram_id: int,
) -> Tuple[bool, str]:
    """Xaridni bekor qilish va qaytarilgan deb belgilash (Admin)"""
    tx = await session.get(models.PaymentTransaction, tx_id)
    if not tx:
        return False, "Tranzaksiya topilmadi."

    if tx.status == "refunded":
        return False, "Ushbu tranzaksiya allaqachon qaytarilgan."

    tx.status = "refunded"
    tx.refunded_at = datetime.utcnow()
    tx.admin_notes = f"Refunded by admin {admin_telegram_id} at {datetime.utcnow().isoformat()}"

    # Remove user cosmetic if applicable
    if tx.user_id:
        res = await session.execute(
            select(models.UserCosmetic).where(
                models.UserCosmetic.user_id == tx.user_id,
                models.UserCosmetic.item_id == tx.item_id,
            )
        )
        cosm = res.scalar_one_or_none()
        if cosm:
            await session.delete(cosm)

    await session.commit()
    return True, f"Tranzaksiya #{tx_id} muvaffaqiyatli bekor qilindi (Refund)."
