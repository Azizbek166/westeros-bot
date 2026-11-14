"""
Hero & Artifacts Service for Telegram Mini App.
Independent service layer for Hero stats, leveling, and Valyrian artifacts.
"""
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models


async def get_hero_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Qahramon va uning anjomlari/artefaktlari bosh sahifasi.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        return None

    hero = user.characters[0] if user.characters else None
    equipped_art = await crud.get_equipped_artifact(session, user.id)
    all_arts = await crud.get_user_artifacts(session, user.id)

    artifacts_list = []
    for a in all_arts:
        artifacts_list.append({
            "id": a.id,
            "name": a.name,
            "description": a.description or "",
            "bonus_attack": a.bonus_attack or 0,
            "bonus_defense": a.bonus_defense or 0,
            "attack_bonus": a.bonus_attack or 0,
            "defense_bonus": a.bonus_defense or 0,
            "bonus_income": a.bonus_income or 0,
            "is_equipped": a.is_equipped,
            "tier": getattr(a, "tier", "rare") or "rare",
        })

    return {
        "user_id": user.id,
        "hero_name": hero.name if hero else (user.full_name or "Lord"),
        "level": user.level or 1,
        "xp": user.xp or 0,
        "attack": getattr(hero, "attack", 50) if hero else 50,
        "defense": getattr(hero, "defense", 50) if hero else 50,
        "health": getattr(hero, "health", 100) if hero else 100,
        "equipped_artifact": {
            "id": equipped_art.id,
            "name": equipped_art.name,
            "description": equipped_art.description or "",
            "bonus_attack": equipped_art.bonus_attack or 0,
            "bonus_defense": equipped_art.bonus_defense or 0,
            "attack_bonus": equipped_art.bonus_attack or 0,
            "defense_bonus": equipped_art.bonus_defense or 0,
            "bonus_income": equipped_art.bonus_income or 0,
        } if equipped_art else None,
        "artifacts_count": len(artifacts_list),
        "inventory": artifacts_list,
    }


async def equip_artifact_service(session: AsyncSession, identifier: int, artifact_id: int) -> Tuple[bool, str]:
    """Valiriya artefaktini qahramonga taqish"""
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi."
    return await crud.equip_artifact(session, user.id, artifact_id)


async def unequip_artifact_service(session: AsyncSession, identifier: int, artifact_id: Optional[int] = None) -> Tuple[bool, str]:
    """Artefaktni yechish"""
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi."
    if artifact_id is None:
        eq = await crud.get_equipped_artifact(session, user.id)
        if not eq:
            return False, "Hozirda taqilgan artefakt topilmadi."
        artifact_id = eq.id
    return await crud.unequip_artifact(session, user.id, artifact_id)
