"""
VIP & Donate Manual Approval Service for Telegram Bot and Mini App.
Barcha donat paketlar (Premium Season Pass, Noble VIP, Starter Pack, Kosmetikalar)
faqat to'lov cheki (skrinshot) yuborilib, admin tomonidan qo'lda tasdiqlangandan keyin beriladi.
"""
import os
import uuid
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from config import (
    DONATE_TIERS,
    PREMIUM_PASS_CONFIG,
    ADMIN_IDS,
    OWNER_ID,
    BOT_TOKEN,
    is_admin,
)
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

logger = logging.getLogger(__name__)


VIP_TIERS_INFO = {
    "noble": {
        "name": "👑 Oliyjanob Lord (Noble VIP)",
        "badge": "👑 NOBLE VIP",
        "price_stars": 75,
        "price_uzs": "15,000 so'm",
        "price_uzs_num": 15000,
        "duration_days": 30,
        "perks": [
            "⚡ Barcha qal'alardan bir marta bosishda soliq yig'ish (1-Click Tax)",
            "🎥 Profilga dumaloq video xabar yoki jonli video yuklash huquqi",
            "👑 Chat va Mini Appda zarhal oltin [VIP] nishoni",
            "🎁 Kunlik qo'shimcha bonus (+300 Oltin, +600 Bug'doy, +200 Temir)",
            "📊 Kengaytirilgan jang statistikasi va harakatlar tarixi filtri",
        ],
    },
}


def is_authorized_admin(telegram_id: Optional[int]) -> bool:
    """Server tomonida foydalanuvchi admin ekanligini qat'iy tekshirish."""
    if not telegram_id:
        return False
    return bool(is_admin(int(telegram_id)) or (OWNER_ID and int(telegram_id) == int(OWNER_ID)))


def resolve_package_info(package_id: str) -> Optional[Dict[str, Any]]:
    """Paket yoki kosmetika identifikatori bo'yicha narx va ma'lumotlarni aniqlash."""
    if not package_id:
        return None
    pkg_key = str(package_id).strip()
    if pkg_key in DONATE_TIERS:
        t = DONATE_TIERS[pkg_key]
        return {
            "package_id": pkg_key,
            "name": t["name"],
            "price_uzs": int(t["price_uzs"]),
            "price_label": t.get("price_label") or f"{int(t['price_uzs']):,} so'm",
            "description": t.get("description", ""),
            "duration_days": int(t.get("duration_days", 30)),
            "gold": int(t.get("gold", 0)),
            "food": int(t.get("food", 0)),
            "iron": int(t.get("iron", 0)),
            "prestige": int(t.get("prestige", 0)),
            "daily_bonus": t.get("daily_bonus", {}),
        }
    if pkg_key in COSMETICS_CATALOG:
        c = COSMETICS_CATALOG[pkg_key]
        p_uzs = int(c.get("price_uzs", 15000))
        return {
            "package_id": pkg_key,
            "name": f"{c.get('icon', '✨')} {c.get('name', pkg_key)}",
            "price_uzs": p_uzs,
            "price_label": c.get("price_label") or f"{p_uzs:,} so'm",
            "description": c.get("description", ""),
            "duration_days": int(c.get("duration_days", 30)) if not c.get("is_permanent", True) else 0,
            "gold": 0,
            "food": 0,
            "iron": 0,
            "prestige": 0,
            "daily_bonus": {},
        }
    return None


async def get_payment_requisites_service(session: AsyncSession) -> Dict[str, Any]:
    """Karta raqami, karta egasi va mavjud donat paketlar ro'yxatini qaytarish."""
    settings = await crud.get_payment_settings(session)
    packages = []
    for k in ("premium_pass", "vip_noble", "starter_pack", "knight", "lord", "dragonlord", "sovereign"):
        if k in DONATE_TIERS:
            info = resolve_package_info(k)
            if info:
                packages.append(info)
    return {
        "card_number": settings["card_number"],
        "card_holder": settings["card_holder"],
        "updated_at": settings.get("updated_at"),
        "packages": packages,
        "premium_pass": PREMIUM_PASS_CONFIG,
    }


async def update_payment_requisites_service(
    session: AsyncSession,
    admin_telegram_id: int,
    card_number: str,
    card_holder: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Admin tomonidan karta raqami va karta egasi ismini yangilash (Server tekshiruvi bilan)."""
    if not is_authorized_admin(admin_telegram_id):
        return False, "❌ Ruxsat rad etildi! Karta ma'lumotlarini faqat admin o'zgartira oladi.", {}

    return await crud.update_payment_settings(
        session=session,
        card_number=card_number,
        card_holder=card_holder,
        admin_id=admin_telegram_id,
    )


async def _notify_admins_new_donation(
    req: models.DonationRequest,
    bot=None,
    local_photo_path: Optional[str] = None,
) -> None:
    """Yangi donat so'rovi tushganda barcha adminlarga chek rasmi va Tasdiqlash/Rad etish tugmalarini yuborish."""
    admin_targets = list(set((ADMIN_IDS or []) + ([OWNER_ID] if OWNER_ID else [])))
    if not admin_targets:
        return

    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"admin_donate_approve:{req.id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"admin_donate_reject:{req.id}"),
            ],
            [
                InlineKeyboardButton("📋 Admin Panelda Ko'rish", callback_data=f"admin_donate_view:{req.id}"),
            ]
        ])
        uname_str = f"@{req.user_username}" if req.user_username else "Mavjud emas"
        caption = (
            f"🔔 <b>YANGI DONAT SO'ROVI #{req.id}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>O'yinchi:</b> {req.user_full_name} ({uname_str})\n"
            f"🆔 <b>Telegram ID:</b> <code>{req.telegram_id}</code>\n"
            f"📦 <b>Paket:</b> {req.tier_name} (<code>{req.tier_id}</code>)\n"
            f"💵 <b>Summa:</b> {req.price_label or f'{req.price_uzs:,} so`m'}\n"
            f"📅 <b>Vaqt:</b> {req.created_at.strftime('%Y-%m-%d %H:%M:%S') if req.created_at else '-'}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Chekni tekshirib, quyidagi tugmalardan birini bosing:"
        )

        async def _send_to_admins(active_bot):
            for admin_id in admin_targets:
                try:
                    if local_photo_path and os.path.isfile(local_photo_path):
                        with open(local_photo_path, "rb") as photo_file:
                            await active_bot.send_photo(
                                chat_id=admin_id,
                                photo=photo_file,
                                caption=caption,
                                parse_mode="HTML",
                                reply_markup=kb,
                            )
                    elif req.receipt_file_id and not str(req.receipt_file_id).startswith("/static/"):
                        await active_bot.send_photo(
                            chat_id=admin_id,
                            photo=req.receipt_file_id,
                            caption=caption,
                            parse_mode="HTML",
                            reply_markup=kb,
                        )
                    else:
                        await active_bot.send_message(
                            chat_id=admin_id,
                            text=caption,
                            parse_mode="HTML",
                            reply_markup=kb,
                        )
                except Exception as e:
                    logger.warning(f"Admin {admin_id} ga donat xabarini yuborishda xatolik: {e}")

        if bot is not None:
            await _send_to_admins(bot)
        elif BOT_TOKEN and ":" in BOT_TOKEN and local_photo_path and os.path.isfile(local_photo_path):
            async with Bot(token=BOT_TOKEN) as temp_bot:
                await _send_to_admins(temp_bot)
    except Exception as e:
        logger.warning(f"_notify_admins_new_donation error: {e}")


async def _notify_user_donation_result(
    telegram_id: int,
    text: str,
    bot=None,
) -> None:
    """Donat tasdiqlanganda yoki rad etilganda foydalanuvchiga bildirishnoma yuborish."""
    if not telegram_id:
        return
    try:
        from telegram import Bot
        if bot is not None:
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML",
            )
        elif BOT_TOKEN and ":" in BOT_TOKEN and not (900000 <= int(telegram_id) <= 9999999):
            async with Bot(token=BOT_TOKEN) as temp_bot:
                await temp_bot.send_message(
                    chat_id=telegram_id,
                    text=text,
                    parse_mode="HTML",
                )
    except Exception as e:
        logger.warning(f"Foydalanuvchi {telegram_id} ga donat natijasini yuborishda xatolik: {e}")


async def submit_donation_request_service(
    session: AsyncSession,
    user: models.User,
    package_id: str,
    receipt_file_id: str,
    bot=None,
    request_type: str = "tier",
    troop_type: Optional[str] = None,
    troop_count: int = 0,
    custom_price_uzs: Optional[int] = None,
    custom_tier_name: Optional[str] = None,
    local_photo_path: Optional[str] = None,
) -> Tuple[bool, str, Optional[models.DonationRequest]]:
    """
    Foydalanuvchi tomonidan yangi to'lov cheki (skrinshot) bilan donat so'rovi yaratish.
    Bot va Mini App uchun yagona markaziy funksiya.
    """
    if not user:
        return False, "❌ Foydalanuvchi topilmadi.", None

    clean_receipt = (receipt_file_id or "").strip()
    if not clean_receipt:
        return False, "❌ To'lov cheki (skrinshot rasmi) yuborilishi majburiy!", None

    # Spam oldini olish: foydalanuvchida allaqachon pending so'rov bor-yo'qligini tekshirish
    existing_pending = await crud.get_user_pending_donation_request(
        session,
        telegram_id=user.telegram_id,
        user_id=user.id,
    )
    if existing_pending:
        return False, (
            f"⏳ Sizda allaqachon ko'rib chiqilayotgan so'rov mavjud (#{existing_pending.id} — {existing_pending.tier_name}).\n"
            f"Iltimos, admin tasdiqlashini kuting. Yangi so'rovni joriy so'rov ko'rib chiqilgach yuborishingiz mumkin."
        ), existing_pending

    if request_type != "troops":
        pkg_info = resolve_package_info(package_id)
        if not pkg_info and custom_price_uzs is None:
            return False, "❌ Tanlangan paket topilmadi.", None
        tier_name = custom_tier_name or (pkg_info["name"] if pkg_info else package_id)
        price_uzs = custom_price_uzs if custom_price_uzs is not None else (pkg_info["price_uzs"] if pkg_info else 0)
        price_label = f"{price_uzs:,} so'm"
    else:
        tier_name = custom_tier_name or f"Qo'shin: {troop_count:,} ta"
        price_uzs = custom_price_uzs or 0
        price_label = f"{price_uzs:,} so'm"

    req = await crud.create_donation_request(
        session=session,
        user_id=user.id,
        telegram_id=user.telegram_id,
        user_full_name=user.full_name or "Noma'lum Lord",
        user_username=user.username or "",
        tier_id=package_id,
        receipt_file_id=clean_receipt,
        request_type=request_type,
        troop_type=troop_type,
        troop_count=troop_count,
        price_uzs=price_uzs,
        price_label=price_label,
        tier_name=tier_name,
    )
    if not req:
        return False, "❌ So'rovni bazaga saqlashda xatolik yuz berdi.", None

    await _notify_admins_new_donation(req, bot=bot, local_photo_path=local_photo_path)

    return True, (
        f"✅ To'lov chekingiz qabul qilindi! (So'rov #{req.id})\n"
        f"📦 Paket: {req.tier_name} ({req.price_label})\n"
        f"⏳ Adminlarimiz to'lovni tekshirib tasdiqlagach, paket va barcha bonus resurslar hisobingizga tushadi."
    ), req


async def approve_donation_request_service(
    session: AsyncSession,
    request_id: int,
    admin_telegram_id: int,
    bot=None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Admin tomonidan donat so'rovini tasdiqlash (Serverda admin ID va pending status tekshiruvi bilan).
    """
    if not is_authorized_admin(admin_telegram_id):
        return False, "❌ Ruxsat rad etildi! So'rovni faqat admin tasdiqlay oladi.", {}

    req = await crud.get_donation_request_by_id(session, request_id)
    if not req:
        return False, f"❌ #{request_id} raqamli so'rov topilmadi.", {}

    if req.status != "pending":
        return False, f"⚠️ Ushbu so'rov allaqachon ko'rib chiqilgan (Holati: {req.status}). Ikki marta tasdiqlash mumkin emas!", {}

    target_tg_id = req.telegram_id
    ok, msg, details = await crud.approve_donation_request(
        session=session,
        request_id=request_id,
        admin_telegram_id=admin_telegram_id,
    )
    if not ok:
        return False, msg, details

    # Foydalanuvchiga bildirishnoma yuborish
    if details.get("is_troops"):
        user_notif = (
            f"🎉 <b>TO'LOVINGIZ TASDIQLANDI! (So'rov #{request_id})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Xarid:</b> {details.get('tier_name')}\n"
            f"⚔️ <b>Qo'shildi:</b> +{details.get('troop_count', 0):,} ta {details.get('troop_name', '')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Qo'shiningiz jangga shay, Oliy hazratlari!"
        )
    elif details.get("is_cosmetic_only"):
        user_notif = (
            f"🎉 <b>TO'LOVINGIZ TASDIQLANDI! (So'rov #{request_id})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✨ <b>Xarid:</b> {details.get('tier_name')}\n"
            f"{details.get('grant_msg', '')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Xaridingiz uchun tashakkur!"
        )
    else:
        bonus_lines = []
        if details.get("gold", 0) > 0:
            bonus_lines.append(f"🪙 +{details['gold']:,} Oltin")
        if details.get("food", 0) > 0:
            bonus_lines.append(f"🌾 +{details['food']:,} Bug'doy")
        if details.get("iron", 0) > 0:
            bonus_lines.append(f"⚒️ +{details['iron']:,} Temir")
        if details.get("prestige", 0) > 0:
            bonus_lines.append(f"👑 +{details['prestige']:,} Nufuz")
        if details.get("premium_pass_activated"):
            bonus_lines.append("🏆 Mavsumiy Premium Pass (30 kun) + Kunlik qo'shimcha bonuslar")
        bonus_text = "\n".join(bonus_lines) if bonus_lines else "Maxsus unvon va imtiyozlar faollashtirildi"

        user_notif = (
            f"🎉 <b>TO'LOVINGIZ TASDIQLANDI! (So'rov #{request_id})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Paket:</b> {details.get('tier_name')}\n"
            f"🎁 <b>Taqdim etilgan mukofotlar:</b>\n{bonus_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Vesteros ravnaqi yo'lidagi hissangiz uchun rahmat!"
        )

    await _notify_user_donation_result(target_tg_id, user_notif, bot=bot)
    return True, msg, details


async def reject_donation_request_service(
    session: AsyncSession,
    request_id: int,
    admin_telegram_id: int,
    reason: Optional[str] = None,
    bot=None,
) -> Tuple[bool, str, Optional[models.DonationRequest]]:
    """
    Admin tomonidan donat so'rovini sababi bilan rad etish.
    """
    if not is_authorized_admin(admin_telegram_id):
        return False, "❌ Ruxsat rad etildi! So'rovni faqat admin rad eta oladi.", None

    clean_reason = (reason or "To'lov cheki tasdiqlanmadi yoki ma'lumotlar mos kelmadi.").strip()
    ok, msg, req = await crud.reject_donation_request(
        session=session,
        request_id=request_id,
        admin_telegram_id=admin_telegram_id,
        reason=clean_reason,
    )
    if not ok or not req:
        return False, msg, req

    user_notif = (
        f"❌ <b>TO'LOV SO'ROVINGIZ RAD ETILDI (#{request_id})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Paket:</b> {req.tier_name} ({req.price_label})\n"
        f"📝 <b>Sabab:</b> {clean_reason}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Agar xatolik bo'lsa, to'g'ri to'lov cheki (skrinshot) bilan qaytadan so'rov yuborishingiz mumkin."
    )
    await _notify_user_donation_result(req.telegram_id, user_notif, bot=bot)
    return True, f"So'rov #{request_id} rad etildi.", req


async def get_admin_donation_requests_service(
    session: AsyncSession,
    admin_telegram_id: int,
    status_filter: Optional[str] = "pending",
    limit: int = 30,
    offset: int = 0,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Admin Panel uchun donat so'rovlari ro'yxati (pending/approved/rejected) va statistika."""
    if not is_authorized_admin(admin_telegram_id):
        return False, "❌ Ruxsat rad etildi!", {}

    norm_status = None if status_filter in (None, "", "all") else str(status_filter).strip().lower()
    reqs = await crud.get_donation_requests(session, status=norm_status, limit=limit, offset=offset)

    # Counts per status
    counts = {"pending": 0, "approved": 0, "rejected": 0}
    try:
        for st in ("pending", "approved", "rejected"):
            c_res = await session.execute(
                select(func.count(models.DonationRequest.id)).where(models.DonationRequest.status == st)
            )
            counts[st] = c_res.scalar() or 0
    except Exception:
        pass

    requisites = await crud.get_payment_settings(session)

    items = []
    for r in reqs:
        items.append({
            "id": r.id,
            "user_id": r.user_id,
            "telegram_id": r.telegram_id,
            "user_full_name": r.user_full_name,
            "user_username": r.user_username,
            "package": r.tier_id,
            "tier_id": r.tier_id,
            "tier_name": r.tier_name,
            "amount": r.price_uzs,
            "price_uzs": r.price_uzs,
            "price_label": r.price_label,
            "receipt_file_id": r.receipt_file_id,
            "status": r.status,
            "admin_notes": r.admin_notes,
            "reviewed_by": r.reviewed_by_admin_id,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "-",
            "reviewed_at": r.reviewed_at.strftime("%Y-%m-%d %H:%M") if r.reviewed_at else None,
        })

    return True, "OK", {
        "requests": items,
        "counts": counts,
        "status_filter": norm_status or "all",
        "payment_requisites": requisites,
    }


async def get_donate_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Kosmetika va Donat do'koni ma'lumotlari, karta rekvizitlari, kutilayotgan so'rov va paketlar.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        return None

    # Check and migrate legacy VIP if present
    if user.vip_tier and user.vip_tier in ("lord", "knight", "dragonlord", "sovereign"):
        await apply_legacy_vip_compensation(session, user)

    now = datetime.utcnow()
    if user.vip_until and user.vip_until <= now:
        if user.vip_tier in ("premium_pass", "noble"):
            user.vip_tier = "free"
        user.vip_until = None
        await session.commit()

    # Owned cosmetics
    owned_records = await get_user_cosmetics(session, user.id)
    owned_ids = [c.item_id for c in owned_records]

    # Grouped catalog
    catalog_grouped = get_all_cosmetics_grouped()

    is_vip_active = bool(user.vip_until and user.vip_until > now)

    equipped_map = {
        "avatar_frame": user.avatar_frame,
        "castle_skin": user.castle_skin,
        "dragon_skin": user.dragon_skin,
        "message_effect": user.message_effect,
        "title": user.title,
    }

    requisites_data = await get_payment_requisites_service(session)
    pending_req = await crud.get_user_pending_donation_request(
        session,
        telegram_id=user.telegram_id,
        user_id=user.id,
    )

    return {
        "user_id": user.id,
        "telegram_id": user.telegram_id,
        "current_vip_tier": user.vip_tier or "free",
        "vip_until": user.vip_until.isoformat() if user.vip_until else None,
        "is_vip_active": is_vip_active,
        "equipped": equipped_map,
        "owned_items": owned_ids,
        "has_starter_pack": bool(getattr(user, "has_starter_pack", False)),
        "catalog": catalog_grouped,
        "vip_info": VIP_TIERS_INFO["noble"],
        "premium_pass_info": PREMIUM_PASS_CONFIG,
        "payment_requisites": {
            "card_number": requisites_data["card_number"],
            "card_holder": requisites_data["card_holder"],
        },
        "packages": requisites_data["packages"],
        "pending_request": {
            "id": pending_req.id,
            "package": pending_req.tier_id,
            "tier_name": pending_req.tier_name,
            "amount": pending_req.price_uzs,
            "price_label": pending_req.price_label,
            "status": pending_req.status,
            "created_at": pending_req.created_at.strftime("%Y-%m-%d %H:%M") if pending_req.created_at else "-",
        } if pending_req else None,
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
    payment_provider: str = "manual_uzs",
    idempotency_key: Optional[str] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    XAVFSIZLIK QOIDASI: Barcha donat va kosmetik buyumlar darhol berilmaydi!
    Foydalanuvchi to'lov cheki (skrinshot) yuborishi va admin tasdiqlashi shart.
    """
    pkg = resolve_package_info(item_id)
    if not pkg:
        return False, "Bunday paket yoki kosmetik buyum topilmadi.", {}

    return False, (
        f"🔒 «{pkg['name']}» ({pkg['price_label']}) to'lovsiz darhol berilmaydi!\n"
        f"Iltimos, karta raqamiga to'lov qilib, to'lov cheki skrinshotini yuboring. "
        f"Admin tasdiqlagach, buyum va bonuslar hisobingizga o'tkaziladi."
    ), {
        "requires_receipt": True,
        "package": pkg,
    }


async def gift_cosmetic_service(
    session: AsyncSession,
    sender: models.User,
    recipient_telegram_id: int,
    item_id: str,
    payment_provider: str = "manual_uzs",
    idempotency_key: Optional[str] = None,
) -> Tuple[bool, str]:
    """Sovg'a qilish ham faqat admin tasdiqlovi orqali amalga oshiriladi."""
    return False, (
        "🔒 Kosmetika va paketlar to'lovsiz darhol berilmaydi! "
        "Avval to'lov chekini yuborib, admin tasdiqlashini kuting."
    )


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
    if not is_authorized_admin(admin_telegram_id):
        return False, "❌ Ruxsat rad etildi!"

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
