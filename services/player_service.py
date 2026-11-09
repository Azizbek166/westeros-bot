from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models
from core.leveling import get_level_info, check_user_level_up
from core.economy_engine import calculate_army_upkeep, calculate_hourly_income


async def get_player_profile(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    O'yinchi profil ma'lumotlarini (statistika, resurslar, daraja, armiya, xonadon, gildiya)
    Telegramdan to'liq mustaqil (pure dict) formatda qaytarish.
    identifier: user.id (internal) yoki telegram_id bo'lishi mumkin.
    """
    user = await crud.get_user_with_relations(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return None

    # Level up tekshirish
    leveled_up, new_lvl, lvl_msg = check_user_level_up(user)
    if leveled_up:
        await session.commit()

    lvl, lvl_title, curr_req, next_req, progress = get_level_info(user.xp or 0)

    # Armiya va daromad
    upkeep = calculate_army_upkeep(user.army) if user.army else 0
    income = await calculate_hourly_income(session, user)
    hero = user.characters[0] if user.characters else None

    # Qalqon holati
    is_shield_active = False
    shield_hours_left = 0
    now = datetime.utcnow()
    if user.peace_shield_until and user.peace_shield_until > now:
        is_shield_active = True
        shield_hours_left = int((user.peace_shield_until - now).total_seconds() // 3600)

    # Artefakt
    equipped_art = await crud.get_equipped_artifact(session, user.id)

    # Ajdarlar
    dragons = await crud.get_user_dragons(session, user.id)
    best_dragon = None
    if dragons:
        best_d = max(dragons, key=lambda d: getattr(d, "power", 0) or 0)
        best_dragon = {
            "id": best_d.id,
            "name": best_d.name,
            "level": best_d.level,
            "power": best_d.power,
            "stage": getattr(best_d, "stage", "baby"),
            "hunger": getattr(best_d, "hunger", 100),
        }

    # Gildiya
    guild, member = await crud.get_user_guild_membership(session, user.id)

    # Armiya yig'indisi
    army_data = None
    if user.army:
        inf = user.army.infantry or 0
        arc = user.army.archers or 0
        cav = user.army.cavalry or 0
        spm = user.army.spearmen or 0
        spc = user.army.special_troops or 0
        cats = getattr(user.army, "catapults", 0) or 0
        twrs = getattr(user.army, "siege_towers", 0) or 0
        wfire = getattr(user.army, "wildfire", 0) or 0
        army_data = {
            "infantry": inf,
            "archers": arc,
            "cavalry": cav,
            "spearmen": spm,
            "special_troops": spc,
            "catapults": cats,
            "siege_towers": twrs,
            "wildfire": wfire,
            "total_troops": inf + arc + cav + spm + spc,
            "upkeep_food_hourly": int(upkeep),
        }

    return {
        "user_id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "full_name": user.full_name,
        "hero_name": hero.name if hero else (user.full_name or "Lord"),
        "hero_attack": getattr(hero, "attack", 50) if hero else 50,
        "hero_defense": getattr(hero, "defense", 50) if hero else 50,
        "level": lvl,
        "level_title": lvl_title,
        "xp": user.xp or 0,
        "xp_current_req": curr_req,
        "xp_next_req": next_req,
        "xp_progress_pct": round(progress, 1),
        "gold": user.gold or 0,
        "food": user.food or 0,
        "iron": user.iron or 0,
        "prestige": user.prestige or 0,
        "vip_tier": user.vip_tier,
        "title": user.title,
        "custom_status": user.custom_status,
        "custom_audio_title": user.custom_audio_title,
        "custom_audio_file_id": user.custom_audio_file_id,
        "custom_photo_file_id": user.custom_photo_file_id,
        "custom_video_file_id": user.custom_video_file_id,
        "house": {
            "id": user.house.id,
            "name": user.house.name,
            "emoji": user.house.emoji,
            "region": user.house.region,
            "rank": user.rank or "member",
            "special_troop_name": getattr(user.house, "special_troop_name", "Maxsus Qo'shin"),
        } if user.house else None,
        "army": army_data,
        "income_hourly": income,
        "peace_shield": {
            "is_active": is_shield_active,
            "hours_left": shield_hours_left,
            "expires_at": user.peace_shield_until.isoformat() if (is_shield_active and user.peace_shield_until) else None,
        },
        "dragons_count": len(dragons),
        "best_dragon": best_dragon,
        "equipped_artifact": {
            "id": equipped_art.id,
            "name": equipped_art.name,
        } if equipped_art else None,
        "guild": {
            "id": guild.id,
            "name": guild.name,
            "tag": guild.tag,
            "role": member.role,
            "role_title": crud.ROLE_LABELS.get(member.role, member.role),
            "level": guild.level,
        } if (guild and member) else None,
    }
