"""
Profil Studiyasi (Bezaklar) Servisi — 0 Pay-To-Win.
Temalar, gerb emoji, qal'a nomi, g'alaba xabari, doimiy nishonlar va admin moderatsiyasi.
"""
import json
import re
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import DONATE_TIERS, escape_md
from core.sanitizer import sanitize_sensitive_data
from database import models, crud

logger = logging.getLogger(__name__)

VIP_TIER_ORDER = {
    "free": 0,
    "noble": 1,
    "knight": 2,
    "lord": 3,
    "dragonlord": 4,
    "sovereign": 5,
}

PROFILE_THEMES: Dict[str, Dict[str, Any]] = {
    "fire": {
        "key": "fire",
        "name": "🔥 Olov",
        "min_tier": "knight",
        "border": "🔥━━━━━━━━━━━━━━━━━━🔥",
        "badge": "🔥",
    },
    "ice": {
        "key": "ice",
        "name": "❄️ Muz",
        "min_tier": "lord",
        "border": "❄️━━━━━━━━━━━━━━━━━━❄️",
        "badge": "❄️",
    },
    "valyrian": {
        "key": "valyrian",
        "name": "🐉 Valyriya",
        "min_tier": "dragonlord",
        "border": "🐉━━━━━━━━━━━━━━━━━━🐉",
        "badge": "🐉",
    },
    "gold": {
        "key": "gold",
        "name": "👑 Oltin",
        "min_tier": "sovereign",
        "border": "👑━━━━━━━━━━━━━━━━━━👑",
        "badge": "👑",
    },
    "shadow": {
        "key": "shadow",
        "name": "🌑 Soya",
        "min_tier": "sovereign",
        "border": "🌑━━━━━━━━━━━━━━━━━━🌑",
        "badge": "🌑",
    },
}

CREST_EMOJIS: List[str] = ["🐺", "🦁", "🐉", "🦅", "🦌", "🐙", "⚔️", "🛡️", "🔥", "❄️", "👑", "🌑"]

PERMANENT_BADGES: Dict[str, str] = {
    "royal_patron": "👑 Qirollik Homiysi",
}

_URL_OR_MENTION_RE = re.compile(r"(https?://|t\.me/|www\.|@[\w_]+)", re.IGNORECASE)


def get_active_vip_tier(user: Optional[models.User]) -> str:
    """Foydalanuvchining joriy faol VIP darajasini qaytaradi ('free' agar muddati tugagan yoki yo'q bo'lsa)."""
    if not user:
        return "free"
    tier = (getattr(user, "vip_tier", None) or "free").lower()
    if tier not in VIP_TIER_ORDER or tier == "free":
        return "free"
    vip_until = getattr(user, "vip_until", None)
    if not vip_until or vip_until <= datetime.utcnow():
        return "free"
    return tier


def has_min_vip_tier(user: Optional[models.User], min_tier: str) -> bool:
    """VIP darajasi ketma-ketlik bo'yicha (noble < knight < lord < dragonlord < sovereign) yetarlimi?"""
    cur = get_active_vip_tier(user)
    return VIP_TIER_ORDER.get(cur, 0) >= VIP_TIER_ORDER.get(min_tier, 99)


def sanitize_profile_text(raw: Optional[str], max_len: int) -> Tuple[bool, str]:
    """
    Foydalanuvchi kiritgan bezak matnini tozalash:
    - core/sanitizer.py dan o'tkazish
    - havolalar (http/https/t.me/www) va @ eslatmalarni taqiqlash
    - uzunlik cheklovini tekshirish
    """
    if raw is None:
        return False, "Matn bo'sh bo'lishi mumkin emas."
    cleaned = sanitize_sensitive_data(str(raw)).strip()
    cleaned = " ".join(cleaned.splitlines()).strip()
    if not cleaned:
        return False, "Matn bo'sh bo'lishi mumkin emas."
    if _URL_OR_MENTION_RE.search(cleaned):
        return False, "❌ Havolalar va @eslatmalar kiritish taqiqlangan!"
    if len(cleaned) > max_len:
        return False, f"❌ Matn juda uzun! Maksimal {max_len} ta belgi (sizda: {len(cleaned)})."
    return True, cleaned


async def get_or_create_extras(session: AsyncSession, user_db_id: int) -> models.UserProfileExtra:
    res = await session.execute(
        select(models.UserProfileExtra).where(models.UserProfileExtra.user_id == user_db_id)
    )
    row = res.scalar_one_or_none()
    if not row:
        row = models.UserProfileExtra(user_id=user_db_id, badges="[]")
        session.add(row)
        await session.flush()
    return row


async def get_profile_extras_view(session: AsyncSession, user: models.User) -> Dict[str, Any]:
    """Profil kartasi va reyting uchun xavfsiz bezak ma'lumotlari."""
    active_tier = get_active_vip_tier(user)
    res = await session.execute(
        select(models.UserProfileExtra).where(models.UserProfileExtra.user_id == user.id)
    )
    row = res.scalar_one_or_none()
    if not row:
        return {
            "active_tier": active_tier,
            "theme": None,
            "crest": None,
            "castle_name": None,
            "victory_message": None,
            "badges": [],
        }

    try:
        raw_badges = json.loads(row.badges or "[]")
        badge_labels = [PERMANENT_BADGES[b] for b in raw_badges if b in PERMANENT_BADGES]
    except Exception:
        badge_labels = []

    # VIP tugagach tema, gerb, qal'a nomi va g'alaba xabari o'chadi; doimiy nishonlar qoladi
    is_vip_active = active_tier != "free"
    theme_info = PROFILE_THEMES.get(row.theme) if (is_vip_active and row.theme) else None
    return {
        "active_tier": active_tier,
        "theme": theme_info,
        "crest": row.crest if (is_vip_active and has_min_vip_tier(user, "lord")) else None,
        "castle_name": row.castle_name if (is_vip_active and has_min_vip_tier(user, "sovereign")) else None,
        "victory_message": row.victory_message if (is_vip_active and has_min_vip_tier(user, "dragonlord")) else None,
        "badges": badge_labels,
    }


async def set_profile_theme(session: AsyncSession, telegram_id: int, theme_key: str) -> Tuple[bool, str]:
    user = await crud.get_user_any(session, telegram_id, load_relations=False)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."
    if theme_key == "none":
        ex = await get_or_create_extras(session, user.id)
        ex.theme = None
        ex.updated_at = datetime.utcnow()
        await session.commit()
        return True, "✅ Profil temasi olib tashlandi."
    theme = PROFILE_THEMES.get(theme_key)
    if not theme:
        return False, "❌ Noma'lum tema."
    if not has_min_vip_tier(user, theme["min_tier"]):
        req_name = DONATE_TIERS.get(theme["min_tier"], {}).get("name", theme["min_tier"])
        return False, f"❌ Ushbu tema uchun kamida {req_name} kerak."
    ex = await get_or_create_extras(session, user.id)
    ex.theme = theme_key
    ex.updated_at = datetime.utcnow()
    await session.commit()
    return True, f"✅ Profil temasi o'rnatildi: {theme['name']}"


async def set_profile_crest(session: AsyncSession, telegram_id: int, crest: Optional[str]) -> Tuple[bool, str]:
    user = await crud.get_user_any(session, telegram_id, load_relations=False)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."
    if crest is None:
        ex = await get_or_create_extras(session, user.id)
        ex.crest = None
        ex.updated_at = datetime.utcnow()
        await session.commit()
        return True, "✅ Gerb emoji olib tashlandi."
    if not has_min_vip_tier(user, "lord"):
        req_name = DONATE_TIERS.get("lord", {}).get("name", "Lord Homiy")
        return False, f"❌ Gerb emoji uchun kamida {req_name} kerak."
    if crest not in CREST_EMOJIS:
        return False, "❌ Noto'g'ri gerb emoji."
    ex = await get_or_create_extras(session, user.id)
    ex.crest = crest
    ex.updated_at = datetime.utcnow()
    await session.commit()
    return True, f"✅ Gerb emoji o'rnatildi: {crest}"


async def set_castle_name(session: AsyncSession, telegram_id: int, raw_name: Optional[str]) -> Tuple[bool, str]:
    user = await crud.get_user_any(session, telegram_id, load_relations=False)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."
    if raw_name is None:
        ex = await get_or_create_extras(session, user.id)
        ex.castle_name = None
        ex.updated_at = datetime.utcnow()
        await session.commit()
        return True, "✅ Qal'a nomi olib tashlandi."
    if not has_min_vip_tier(user, "sovereign"):
        req_name = DONATE_TIERS.get("sovereign", {}).get("name", "Qirollik Homiy")
        return False, f"❌ Qal'a nomi uchun {req_name} kerak."
    ok, cleaned_or_err = sanitize_profile_text(raw_name, max_len=24)
    if not ok:
        return False, cleaned_or_err
    ex = await get_or_create_extras(session, user.id)
    ex.castle_name = cleaned_or_err
    ex.updated_at = datetime.utcnow()
    await session.commit()
    return True, f"✅ Qal'a nomi o'rnatildi: {escape_md(cleaned_or_err)}"


async def set_victory_message(session: AsyncSession, telegram_id: int, raw_msg: Optional[str]) -> Tuple[bool, str]:
    user = await crud.get_user_any(session, telegram_id, load_relations=False)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."
    if raw_msg is None:
        ex = await get_or_create_extras(session, user.id)
        ex.victory_message = None
        ex.updated_at = datetime.utcnow()
        await session.commit()
        return True, "✅ G'alaba xabari olib tashlandi."
    if not has_min_vip_tier(user, "dragonlord"):
        req_name = DONATE_TIERS.get("dragonlord", {}).get("name", "Valyriya Homiy")
        return False, f"❌ G'alaba xabari uchun kamida {req_name} kerak."
    ok, cleaned_or_err = sanitize_profile_text(raw_msg, max_len=80)
    if not ok:
        return False, cleaned_or_err
    ex = await get_or_create_extras(session, user.id)
    ex.victory_message = cleaned_or_err
    ex.updated_at = datetime.utcnow()
    await session.commit()
    return True, f"✅ G'alaba xabari o'rnatildi: {escape_md(cleaned_or_err)}"


async def admin_get_user_profile_extras(session: AsyncSession, target_user_id: int) -> Dict[str, Any]:
    user = await crud.get_user_any(session, target_user_id, load_relations=False)
    if not user:
        return {"found": False}
    res = await session.execute(
        select(models.UserProfileExtra).where(models.UserProfileExtra.user_id == user.id)
    )
    ex = res.scalar_one_or_none()
    return {
        "found": True,
        "user": user,
        "custom_status": user.custom_status,
        "castle_name": ex.castle_name if ex else None,
        "victory_message": ex.victory_message if ex else None,
    }


async def admin_clear_user_profile_text(session: AsyncSession, target_user_id: int, field: str) -> Tuple[bool, str]:
    user = await crud.get_user_any(session, target_user_id, load_relations=False)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."
    if field in ("status", "all"):
        user.custom_status = None
    res = await session.execute(
        select(models.UserProfileExtra).where(models.UserProfileExtra.user_id == user.id)
    )
    ex = res.scalar_one_or_none()
    if ex:
        if field in ("castle_name", "all"):
            ex.castle_name = None
        if field in ("victory_message", "all"):
            ex.victory_message = None
        ex.updated_at = datetime.utcnow()
    await session.commit()
    return True, "✅ Tanlangan matnlar tozalandi."
