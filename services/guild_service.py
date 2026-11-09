from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models


async def get_guild_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Gildiya markazi: Foydalanuvchi a'zo bo'lsa Mening Gildiyam, bo'lmasa Gildiyalar Portali ma'lumotlari.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return None

    guild, member = await crud.get_user_guild_membership(session, user.id)

    if guild and member:
        # 1. Mening Gildiyam
        leader_name = guild.leader.full_name if guild.leader else "Noma'lum"
        role_title = crud.ROLE_LABELS.get(member.role, member.role)
        from sqlalchemy import select
        m_res = await session.execute(select(models.GuildMember).where(models.GuildMember.guild_id == guild.id))
        members = m_res.scalars().all()

        # Buff holati
        buff_info = None
        now = datetime.utcnow()
        if guild.active_buff_type and guild.active_buff_expires_at and guild.active_buff_expires_at > now:
            b_cfg = crud.GUILD_BUFFS_CONFIG.get(guild.active_buff_type, {})
            time_left = guild.active_buff_expires_at - now
            buff_info = {
                "buff_type": guild.active_buff_type,
                "name": b_cfg.get("name", guild.active_buff_type),
                "desc": b_cfg.get("desc", ""),
                "expires_at": guild.active_buff_expires_at.isoformat(),
                "hours_remaining": int(time_left.total_seconds() // 3600),
                "minutes_remaining": int((time_left.total_seconds() % 3600) // 60),
            }

        # Kvestlar
        q_result = await crud.get_guild_quests_data(session, guild.id, user.id)
        quests_data = q_result.get("quests", [])

        return {
            "in_guild": True,
            "guild": {
                "id": guild.id,
                "name": guild.name,
                "tag": guild.tag,
                "description": guild.description or "Vesteros birodarligi",
                "banner": guild.banner,
                "level": guild.level,
                "xp": guild.xp,
                "prestige": guild.prestige,
                "leader_id": guild.leader_id,
                "leader_name": leader_name,
                "members_count": len(members),
                "max_members": guild.max_members,
                "recruiting_type": guild.recruiting_type,
                "treasury": {
                    "gold": guild.treasury_gold or 0,
                    "iron": guild.treasury_iron or 0,
                },
                "active_buff": buff_info,
            },
            "my_membership": {
                "role": member.role,
                "role_title": role_title,
                "total_deposited_gold": member.total_deposited_gold or 0,
                "total_deposited_iron": member.total_deposited_iron or 0,
                "total_xp_contributed": member.total_xp_contributed or 0,
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
            },
            "quests": quests_data,
        }
    else:
        # 2. Gildiyalar Portali
        has_cd, exp_at, rem_sec = await crud.check_guild_cooldown(session, user.id)
        top_guilds = await crud.get_guild_rankings(session, offset=0, limit=5)
        rankings_preview = [
            {
                "id": g.id,
                "name": g.name,
                "tag": g.tag,
                "banner": g.banner,
                "level": g.level,
                "prestige": g.prestige,
                "members_count": len(g.members or []),
                "max_members": g.max_members,
            }
            for g in top_guilds
        ]

        return {
            "in_guild": False,
            "user_gold": user.gold or 0,
            "user_level": user.level or 1,
            "creation_cost": crud.GUILD_CREATION_GOLD_COST,
            "min_level_req": crud.GUILD_CREATION_MIN_LEVEL,
            "anti_hopping_cooldown": {
                "has_cooldown": has_cd,
                "hours_remaining": (rem_sec // 3600) if has_cd else 0,
                "minutes_remaining": ((rem_sec % 3600) // 60) if has_cd else 0,
            },
            "top_guilds_preview": rankings_preview,
        }


async def create_guild_service(
    session: AsyncSession,
    identifier: int,
    name: str,
    tag: str,
    description: str = "",
    banner: str = "🛡️",
    recruiting_type: str = "open"
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Yangi gildiya yaratish xizmati.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", None

    if (user.level or 1) < crud.GUILD_CREATION_MIN_LEVEL:
        return False, f"❌ Gildiya yaratish uchun kamida {crud.GUILD_CREATION_MIN_LEVEL}-daraja kerak!", None

    if (user.gold or 0) < crud.GUILD_CREATION_GOLD_COST:
        return False, f"❌ Oltin yetarli emas! Kerak: {crud.GUILD_CREATION_GOLD_COST:,}🪙, mavjud: {user.gold:,}🪙", None

    guild, err = await crud.create_guild(
        session=session,
        leader_user_id=user.id,
        name=name.strip(),
        tag=tag.strip(),
        description=description.strip(),
        banner=banner.strip(),
        recruiting_type=recruiting_type.strip(),
    )
    if err:
        return False, err, None

    return True, f"🎉 «{guild.name} {guild.tag}» gildiyasi muvaffaqiyatli tashkil etildi!", {
        "guild_id": guild.id,
        "name": guild.name,
        "tag": guild.tag,
    }


async def deposit_guild_treasury_service(
    session: AsyncSession,
    identifier: int,
    resource_type: str,
    amount: int
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Gildiya xazinasiga oltin yoki temir topshirish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    guild, member = await crud.get_user_guild_membership(session, user.id)
    if not guild or not member:
        return False, "Siz hech qaysi gildiyada emassiz.", {}

    gold_amt = amount if resource_type == "gold" else 0
    iron_amt = amount if resource_type == "iron" else 0
    ok, msg = await crud.deposit_to_guild_treasury(
        session=session,
        telegram_id=user.telegram_id,
        gold_amount=gold_amt,
        iron_amount=iron_amt
    )
    if ok:
        await session.refresh(user)
        await session.refresh(guild)

    return ok, msg, {
        "user_gold": user.gold,
        "user_iron": user.iron,
        "guild_treasury_gold": guild.treasury_gold or 0,
        "guild_treasury_iron": guild.treasury_iron or 0,
    }


async def activate_guild_buff_service(
    session: AsyncSession,
    identifier: int,
    buff_type: str
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Gildiya xazinasidan 24 soatlik harbiy/iqtisodiy buffni yoqish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    guild, member = await crud.get_user_guild_membership(session, user.id)
    if not guild or not member:
        return False, "Siz gildiyada emassiz.", {}

    ok, msg = await crud.spend_guild_treasury_buff(
        session=session,
        telegram_id=user.telegram_id,
        buff_code=buff_type
    )
    if ok:
        await session.refresh(guild)

    return ok, msg, {
        "active_buff_type": guild.active_buff_type,
        "expires_at": guild.active_buff_expires_at.isoformat() if guild.active_buff_expires_at else None,
    }
