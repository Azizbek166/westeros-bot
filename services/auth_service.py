"""
Auth & Registration Service for Telegram Mini App.
Allows new players to choose a house, name their hero, and take the oath
directly inside the Mini App with 100% database parity with the Telegram bot.
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from database import crud, models
from data.houses_data import HOUSES_DATA
from config import STARTING_GOLD, STARTING_FOOD, STARTING_IRON


async def get_registration_houses_catalog(session: AsyncSession) -> List[Dict[str, Any]]:
    """
    Ro'yxatdan o'tish uchun mavjud xonadonlar ro'yxatini qaytaradi.
    Bo'sh xonadonlar (0 a'zoli) va ularning mintaqalari, qahramonlik tavsifi.
    """
    member_counts = await crud.get_all_houses_member_counts(session)
    
    # 50 ta asosiy xonadon
    all_houses = await crud.get_all_houses(session)
    available_houses = []
    
    for h in all_houses:
        if h.id > 50 or getattr(h, "is_npc", False):
            continue
        
        m_count = member_counts.get(h.id, 0)
        h_data = HOUSES_DATA.get(h.code, {})
        
        available_houses.append({
            "id": h.id,
            "code": h.code or f"house_{h.id}",
            "name": h.name,
            "emoji": h.emoji or "🛡️",
            "region": h.region or "Vesteros",
            "description": h_data.get("description", h.description or "Buyuk Vesteros xonadoni."),
            "special_troop": h_data.get("special_troop", h.special_troop_name or "Maxsus Qo'shin"),
            "is_available": (m_count < 1),
            "members_count": m_count,
        })
        
    return available_houses


async def register_player_service(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str],
    full_name: str,
    hero_name: str,
    house_code: Optional[str] = None,
    custom_house_name: Optional[str] = None,
    custom_house_region: Optional[str] = None,
    custom_house_emoji: Optional[str] = None,
    custom_castle_name: Optional[str] = None,
) -> Tuple[bool, str, Optional[models.User]]:
    """
    Yangi o'yinchini ro'yxatdan o'tkazish xizmati.
    Mavjud xonadonga Yagona Lord sifatida yoki yangi maxsus sulola/qal'a asoschisi sifatida biriktiradi.
    """
    # 1. Foydalanuvchi allaqachon mavjudligini tekshirish
    existing = await crud.get_user_by_telegram_id(session, telegram_id)
    if existing and existing.house_id:
        return False, "Siz allaqachon xonadonga egasiz va ro'yxatdan o'tgansiz!", existing

    clean_hero = hero_name.strip()
    if len(clean_hero) < 2 or len(clean_hero) > 32:
        return False, "Qahramon nomi 2 tadan 32 tagacha belgidan iborat bo'lishi kerak.", None

    exclude_id = existing.id if existing else None
    if await crud.is_character_name_taken(session, clean_hero, exclude_user_id=exclude_id):
        return False, f"«{clean_hero}» nomi allaqachon boshqa Lord tomonidan band qilingan! Boshqa nom tanlang.", None

    # 2. Xonadonni aniqlash
    # A) Maxsus yangi xonadon yaratish
    if custom_house_name and custom_house_name.strip():
        h_name = custom_house_name.strip()
        h_reg = (custom_house_region or "The Crownlands").strip()
        h_emoji = (custom_house_emoji or "🛡️").strip()
        c_name = (custom_castle_name or f"{h_name} Qal'asi").strip()

        try:
            user, new_house, new_terr = await crud.create_custom_house_user_and_territory(
                session=session,
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
                house_name=h_name,
                region=h_reg,
                emoji=h_emoji,
                castle_name=c_name,
                hero_name=clean_hero,
            )
            # Mavsum bonusi
            pending = await crud.get_pending_season_bonus(session, telegram_id)
            if pending:
                await crud.apply_season_top_bonus(session, user, pending)

            return True, f"👑 Yangi {h_emoji} {h_name} sulolasi va {c_name} poytaxti asoschisi bo'ldingiz!", user
        except ValueError as ve:
            return False, str(ve), None

    # B) 50 ta asosiy xonadondan birini tanlash
    house_obj = None
    if house_code:
        h_res = await session.execute(
            select(models.House).where(models.House.code == house_code)
        )
        found_h = h_res.scalar_one_or_none()
        if found_h:
            cnt = await crud.get_house_members_count(session, found_h.id)
            if cnt < 1:
                house_obj = found_h

    if not house_obj:
        # Bo'sh xonadon topish
        house_obj = await crud.get_random_available_house(session)

    if not house_obj:
        return False, "Vesterosda bo'sh asosiy xonadon qolmadi. Iltimos, o'zingizning yangi xonadoningiz nomini kiriting!", None

    try:
        if existing:
            user = await crud.join_house(
                session=session,
                user=existing,
                house_id=house_obj.id,
                character_name=clean_hero,
                username=username,
                full_name=full_name,
            )
        else:
            user = await crud.create_user(
                session=session,
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
                house_id=house_obj.id,
                character_name=clean_hero,
            )

        # Mavsum bonusi
        pending = await crud.get_pending_season_bonus(session, telegram_id)
        if pending:
            await crud.apply_season_top_bonus(session, user, pending)

        return True, f"🛡️ {house_obj.emoji} {house_obj.name} xonadonining Yagona Oliy Lordi etib tayinlandingiz!", user
    except ValueError as ve:
        return False, str(ve), None
