"""
VIP Bo'limlar Mediasi (Ajdarlar, Qal'alar, Armiya, Xonadon uchun shaxsiy rasm/video/GIF).
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import crud, models
from services.profile_extras_service import get_active_vip_tier, has_min_vip_tier

logger = logging.getLogger(__name__)

SECTION_MEDIA_CONFIG: Dict[str, Dict[str, str]] = {
    "dragon": {
        "name": "🐉 Ajdarlar bo'limi",
        "desc": "Ajdarlar bo'limini ochganingizda ajdaringizning maxsus rasmi yoki videosi ko'rinadi.",
    },
    "castle": {
        "name": "🏰 Qal'alar bo'limi",
        "desc": "Qal'a boshqaruviga kirganingizda qal'angizning shaxsiy rasmi yoki videosi ko'rinadi.",
    },
    "army": {
        "name": "⚔️ Armiya bo'limi",
        "desc": "Armiya menyusida qo'shiningizning maxsus rasmi yoki videosi ko'rinadi.",
    },
    "house": {
        "name": "🏛️ Xonadon bo'limi",
        "desc": "Xonadon menyusida sulolangiz bayrog'i/rasmi yoki videosi ko'rinadi.",
    },
}


async def get_user_section_media(
    session: AsyncSession, user: Optional[models.User], section_key: str
) -> Optional[Dict[str, str]]:
    """Faol VIP foydalanuvchi uchun bo'lim mediasini qaytaradi (VIP tugagan bo'lsa None)."""
    if not user or section_key not in SECTION_MEDIA_CONFIG:
        return None
    if get_active_vip_tier(user) == "free":
        return None

    res = await session.execute(
        select(models.UserSectionMedia).where(
            models.UserSectionMedia.user_id == user.id,
            models.UserSectionMedia.section_key == section_key,
        )
    )
    row = res.scalar_one_or_none()
    if not row or not row.file_id:
        return None
    if row.media_type in ("video", "animation") and not has_min_vip_tier(user, "knight"):
        return None
    return {"media_type": row.media_type, "file_id": row.file_id}


async def get_all_user_section_media(
    session: AsyncSession, user: Optional[models.User]
) -> Dict[str, Dict[str, str]]:
    if not user or get_active_vip_tier(user) == "free":
        return {}
    res = await session.execute(
        select(models.UserSectionMedia).where(models.UserSectionMedia.user_id == user.id)
    )
    out: Dict[str, Dict[str, str]] = {}
    for row in res.scalars().all():
        if row.section_key in SECTION_MEDIA_CONFIG and row.file_id:
            if row.media_type in ("video", "animation") and not has_min_vip_tier(user, "knight"):
                continue
            out[row.section_key] = {"media_type": row.media_type, "file_id": row.file_id}
    return out


async def set_user_section_media(
    session: AsyncSession,
    telegram_id: int,
    section_key: str,
    media_type: str,
    file_id: str,
) -> Tuple[bool, str]:
    if section_key not in SECTION_MEDIA_CONFIG:
        return False, "❌ Noto'g'ri bo'lim tanlandi."
    if media_type not in ("photo", "video", "animation"):
        return False, "❌ Faqat rasm, video yoki GIF yuboring."
    clean_fid = (file_id or "").strip()
    if not clean_fid or len(clean_fid) > 256:
        return False, "❌ Media fayl ID yaroqsiz."

    user = await crud.get_user_by_telegram_id(session, telegram_id)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."

    if not has_min_vip_tier(user, "noble"):
        return False, "🔒 Bo'limlarga rasm qo'yish uchun kamida Noble Homiy VIP kerak!"
    if media_type in ("video", "animation") and not has_min_vip_tier(user, "knight"):
        return False, "🔒 Bo'limlarga video yoki GIF qo'yish uchun kamida Ritsar Homiy VIP kerak!"

    res = await session.execute(
        select(models.UserSectionMedia).where(
            models.UserSectionMedia.user_id == user.id,
            models.UserSectionMedia.section_key == section_key,
        )
    )
    row = res.scalar_one_or_none()
    now = datetime.utcnow()
    if row:
        row.media_type = media_type
        row.file_id = clean_fid
        row.updated_at = now
    else:
        session.add(
            models.UserSectionMedia(
                user_id=user.id,
                section_key=section_key,
                media_type=media_type,
                file_id=clean_fid,
                created_at=now,
                updated_at=now,
            )
        )
    await session.commit()
    sec_name = SECTION_MEDIA_CONFIG[section_key]["name"]
    label = "Rasm" if media_type == "photo" else ("GIF" if media_type == "animation" else "Video")
    return True, f"✅ {sec_name} uchun shaxsiy {label} saqlandi!"


async def clear_user_section_media(
    session: AsyncSession, telegram_id: int, section_key: str
) -> Tuple[bool, str]:
    if section_key not in SECTION_MEDIA_CONFIG:
        return False, "❌ Noto'g'ri bo'lim."
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."
    await session.execute(
        delete(models.UserSectionMedia).where(
            models.UserSectionMedia.user_id == user.id,
            models.UserSectionMedia.section_key == section_key,
        )
    )
    await session.commit()
    return True, f"🗑️ {SECTION_MEDIA_CONFIG[section_key]['name']} mediasi olib tashlandi."


async def send_section_media_if_any(
    message_obj: Any,
    session: AsyncSession,
    user: Optional[models.User],
    section_key: str,
) -> bool:
    """Bo'lim ochilganda foydalanuvchining VIP mediasini xavfsiz yuboradi (xato bo'lsa logga yozib davom etadi)."""
    try:
        if not message_obj or not user:
            return False
        media = await get_user_section_media(session, user, section_key)
        if not media:
            return False
        sec_title = SECTION_MEDIA_CONFIG.get(section_key, {}).get("name", "VIP Media")
        mtype = media["media_type"]
        fid = media["file_id"]
        if mtype == "photo" and hasattr(message_obj, "reply_photo"):
            await message_obj.reply_photo(photo=fid, caption=f"✨ {sec_title}")
            return True
        if mtype == "video" and hasattr(message_obj, "reply_video"):
            await message_obj.reply_video(video=fid, caption=f"✨ {sec_title}")
            return True
        if mtype == "animation" and hasattr(message_obj, "reply_animation"):
            await message_obj.reply_animation(animation=fid, caption=f"✨ {sec_title}")
            return True
    except Exception as e:
        logger.warning(f"send_section_media_if_any error ({section_key}): {e}")
    return False
