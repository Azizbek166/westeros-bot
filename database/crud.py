import json
import random
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy import select, update, delete, desc, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from database import models
from config import (
    STARTING_GOLD,
    STARTING_FOOD,
    STARTING_IRON,
    PEACE_SHIELD_HOURS,
    STARTING_INFANTRY,
    STARTING_ARCHERS,
    STARTING_CAVALRY,
    STARTING_SPEARMEN,
)


# ============================================================
# USER / PLAYER CRUD
# ============================================================

async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[models.User]:
    """Telegram ID orqali o'yinchini olish"""
    result = await session.execute(
        select(models.User).where(models.User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_user_with_relations(session: AsyncSession, identifier: int) -> Optional[models.User]:
    """O'yinchini xonadoni, armiyasi va personajlari bilan birga olish (id yoki telegram_id qabul qiladi)"""
    return await get_user_any(session, identifier, load_relations=True)


async def get_user_any(session: AsyncSession, identifier: int, load_relations: bool = True) -> Optional[models.User]:
    """Foydalanuvchini id yoki telegram_id orqali xavfsiz qidirish (PostgreSQL 32-bit int chegarasi xatolaridan himoyalangan)"""
    if not identifier:
        return None
    try:
        ident_int = int(identifier)
    except Exception:
        return None

    # Agar 32-bit int chegarasidan (2,147,483,647) katta bo'lsa, bu 100% telegram_id!
    # Uni session.get(models.User) ga berish PostgreSQL da "integer out of range" beradi.
    user = None
    if ident_int > 2147483647:
        user = await get_user_by_telegram_id(session, ident_int)
    else:
        user = await session.get(models.User, ident_int)
        if not user:
            user = await get_user_by_telegram_id(session, ident_int)

    if user and load_relations:
        try:
            await session.refresh(user, ["house", "army", "characters"])
        except Exception:
            pass

    return user


async def check_and_reset_daily_limits(session: AsyncSession, user: models.User) -> None:
    """Kunlik limitlarni yangi kunda 0 ga tushirish"""
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    if user.daily_limit_date != today_str:
        user.daily_quiz_count = 0
        user.daily_council_count = 0
        user.daily_secret_quest_count = 0
        user.daily_donation_count = 0
        user.daily_story_quest_count = 0
        user.daily_rank_quest_count = 0
        user.daily_ww_attack_count = 0
        user.daily_bandit_count = 0
        user.daily_duel_count = 0
        user.daily_recruit_count = 0
        user.daily_caravan_send_count = 0
        user.daily_caravan_raid_count = 0
        user.daily_limit_date = today_str
        await session.commit()


async def get_taken_character_names(session: AsyncSession, house_id: int) -> set:
    """Xonadonda allaqachon tirik o'yinchilar tomonidan tanlangan qahramonlar"""
    res = await session.execute(
        select(models.Character.name).join(
            models.User, models.Character.user_id == models.User.id
        ).where(
            models.Character.house_id == house_id,
            models.Character.is_alive == True,
            models.User.house_id == house_id,
        )
    )
    return set(res.scalars().all())


def get_rank_for_member_index(member_count: int) -> str:
    """Xonadonga qo'shilish tartibiga ko'ra lavozim (0->king, 1->commander, 2->knight, 3->captain, 4->member)"""
    ranks = ["king", "commander", "knight", "captain", "member"]
    if 0 <= member_count < len(ranks):
        return ranks[member_count]
    return "member"


async def is_character_name_taken(session: AsyncSession, name: str, exclude_user_id: Optional[int] = None) -> bool:
    """Qahramon nomi butun o'yin bo'ylab allaqachon olinganligini tekshirish (katta-kichik harfga befarq)"""
    clean_name = name.strip()
    if not clean_name:
        return True
    stmt = select(models.Character.id).where(
        func.lower(models.Character.name) == clean_name.lower(),
        models.Character.is_alive == True,
    )
    if exclude_user_id:
        stmt = stmt.where(models.Character.user_id != exclude_user_id)
    res = await session.execute(stmt)
    return res.scalar_one_or_none() is not None


async def create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str],
    full_name: str,
    house_id: int,
    character_name: str,
) -> models.User:
    """Yangi o'yinchini ro'yxatdan o'tkazish"""
    clean_name = character_name.strip()
    if await is_character_name_taken(session, clean_name):
        raise ValueError(f"'{clean_name}' nomi allaqachon band qilingan!")

    members_count = await get_house_members_count(session, house_id)
    if members_count >= 5:
        raise ValueError("Bu xonadon to'lgan! Maksimal 5 nafar o'yinchi bo'lishi mumkin.")

    shield_expiry = datetime.utcnow() + timedelta(hours=PEACE_SHIELD_HOURS)
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    # Xonadonda Lord bormi? Agar bo'lmasa, birinchi o'yinchi Lord (King) bo'ladi
    house = await session.get(models.House, house_id)
    is_first_lord = False
    if house and (house.lord_user_id is None or house.lord_user_id == 0 or members_count == 0):
        is_first_lord = True

    user_rank = "king" if is_first_lord else get_rank_for_member_index(members_count)

    user = models.User(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        house_id=house_id,
        rank=user_rank,
        level=1,
        xp=0,
        gold=STARTING_GOLD,
        food=STARTING_FOOD,
        iron=STARTING_IRON,
        prestige=10,
        peace_shield_until=shield_expiry,
        daily_quiz_count=0,
        daily_council_count=0,
        daily_secret_quest_count=0,
        daily_limit_date=today_str,
    )
    session.add(user)
    await session.flush()

    if is_first_lord and house:
        house.lord_user_id = telegram_id
        house.lord_elected_at = datetime.utcnow()

    # Boshlang'ich armiyani biriktirish
    army = models.Army(
        user_id=user.id,
        infantry=STARTING_INFANTRY,
        archers=STARTING_ARCHERS,
        cavalry=STARTING_CAVALRY,
        spearmen=STARTING_SPEARMEN,
        special_troops=0,
    )
    session.add(army)

    # Tanlangan boshlang'ich qahramon
    hero = models.Character(
        user_id=user.id,
        house_id=house_id,
        name=clean_name,
        level=1,
        attack=50,
        defense=50,
        leadership=50,
        special_ability="Jasorat",
        loyalty=100,
        is_alive=True,
    )
    session.add(hero)

    # Xonadon a'zoligi
    member = models.HouseMember(
        house_id=house_id,
        user_id=user.id,
        rank=user_rank,
    )
    session.add(member)

    await session.commit()
    await session.refresh(user, ["house", "army", "characters"])
    return user


async def join_house(
    session: AsyncSession,
    user: models.User,
    house_id: int,
    character_name: str,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
) -> models.User:
    """Mavjud o'yinchini xonadonga a'zo qilish va qasamyod qildirish"""
    if user.house_id:
        raise ValueError("Siz allaqachon xonadonga a'zosiz! Xonadonni almashtirish taqiqlangan.")

    house = await session.get(models.House, house_id)
    if not house:
        raise ValueError(f"House with id {house_id} not found")

    members_count = await get_house_members_count(session, house_id)
    if members_count >= 5:
        raise ValueError("Bu xonadon to'lgan! Maksimal 5 nafar o'yinchi bo'lishi mumkin.")

    clean_name = character_name.strip()
    if await is_character_name_taken(session, clean_name, exclude_user_id=user.id):
        raise ValueError(f"'{clean_name}' nomi allaqachon band qilingan!")

    is_first_lord = (house.lord_user_id is None or house.lord_user_id == 0 or members_count == 0)
    user_rank = "king" if is_first_lord else get_rank_for_member_index(members_count)

    user.house_id = house_id
    user.rank = user_rank
    if username:
        user.username = username
    if full_name:
        user.full_name = full_name

    now = datetime.utcnow()
    if not user.peace_shield_until or user.peace_shield_until < now:
        user.peace_shield_until = now + timedelta(hours=PEACE_SHIELD_HOURS)

    if is_first_lord:
        house.lord_user_id = user.telegram_id
        house.lord_elected_at = now

    # Armiya mavjudligini tekshirish
    army_res = await session.execute(
        select(models.Army).where(models.Army.user_id == user.id)
    )
    army = army_res.scalar_one_or_none()
    if not army:
        army = models.Army(
            user_id=user.id,
            infantry=STARTING_INFANTRY,
            archers=STARTING_ARCHERS,
            cavalry=STARTING_CAVALRY,
            spearmen=STARTING_SPEARMEN,
            special_troops=0,
        )
        session.add(army)

    # Qahramonni yangilash yoki yaratish
    char_res = await session.execute(
        select(models.Character).where(
            models.Character.user_id == user.id,
            models.Character.is_alive == True,
        )
    )
    char = char_res.scalar_one_or_none()
    if char:
        char.house_id = house_id
        char.name = clean_name
    else:
        char = models.Character(
            user_id=user.id,
            house_id=house_id,
            name=clean_name,
            level=1,
            attack=50,
            defense=50,
            leadership=50,
            special_ability="Jasorat",
            loyalty=100,
            is_alive=True,
        )
        session.add(char)

    # Xonadon a'zoligi
    hm_res = await session.execute(
        select(models.HouseMember).where(models.HouseMember.user_id == user.id)
    )
    hm = hm_res.scalar_one_or_none()
    if hm:
        hm.house_id = house_id
        hm.rank = user_rank
    else:
        hm = models.HouseMember(
            house_id=house_id,
            user_id=user.id,
            rank=user_rank,
        )
        session.add(hm)

    await session.commit()
    await session.refresh(user, ["house", "army", "characters"])
    return user


async def leave_house(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """O'yinchi xonadondan chiqishi (Westeros qonunlariga ko'ra qasamyod umrboddir)"""
    return False, "❌ Westeros qonunlariga ko'ra, xonadonga berilgan qasamyod umrboddir! Xonadonni tark etish yoki almashtirish taqiqlanadi."


# ============================================================
# HOUSE CRUD
# ============================================================

async def get_all_houses(session: AsyncSession) -> List[models.House]:
    """Barcha 50 ta xonadon ro'yxatini olish"""
    result = await session.execute(select(models.House).order_by(models.House.region, models.House.name))
    return list(result.scalars().all())


async def get_house_by_id(session: AsyncSession, house_id: int) -> Optional[models.House]:
    """Xonadonni ID orqali olish"""
    return await session.get(models.House, house_id)


async def get_house_members_count(session: AsyncSession, house_id: int) -> int:
    """Xonadondagi jonli a'zolar soni"""
    result = await session.execute(
        select(func.count(models.User.id)).where(models.User.house_id == house_id)
    )
    return result.scalar() or 0


async def get_all_houses_member_counts(session: AsyncSession) -> Dict[int, int]:
    """Barcha xonadonlardagi faol a'zolar sonini qaytarish {house_id: count}"""
    result = await session.execute(
        select(models.User.house_id, func.count(models.User.id))
        .where(models.User.house_id.isnot(None))
        .group_by(models.User.house_id)
    )
    return {row[0]: row[1] for row in result.all()}


# ============================================================
# TERRITORY & MAP CRUD
# ============================================================

async def get_all_territories(session: AsyncSession) -> List[models.Territory]:
    """Barcha Westeros hududlarini olish"""
    result = await session.execute(
        select(models.Territory).order_by(models.Territory.region, models.Territory.name)
    )
    return list(result.scalars().all())


async def get_territory_by_id(session: AsyncSession, territory_id: int) -> Optional[models.Territory]:
    """Hududni ID orqali olish"""
    result = await session.execute(
        select(models.Territory).where(models.Territory.id == territory_id)
    )
    territory = result.scalar_one_or_none()
    if territory:
        if territory.owner_house_id:
            try:
                await session.refresh(territory, ["owner_house"])
            except Exception:
                pass
        else:
            territory.owner_house = None
    return territory


async def get_house_territories(session: AsyncSession, house_id: int) -> List[models.Territory]:
    """Muayyan xonadonga tegishli hududlar"""
    result = await session.execute(
        select(models.Territory).where(models.Territory.owner_house_id == house_id)
    )
    return list(result.scalars().all())


# ============================================================
# ARMY & RECRUITMENT CRUD
# ============================================================

async def recruit_troops(
    session: AsyncSession,
    user_id: int,
    unit_type: str,
    amount: int,
    gold_cost: int,
    iron_cost: int,
) -> bool:
    """Yangi askarlarni yollash va resurslarni yechish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False

    if user.gold < gold_cost or user.iron < iron_cost:
        return False

    army_res = await session.execute(select(models.Army).where(models.Army.user_id == user_id))
    army = army_res.scalar_one_or_none()
    if not army:
        return False

    # Resurslarni yechish
    user.gold -= gold_cost
    user.iron -= iron_cost

    # Armiyani ko'paytirish
    current = getattr(army, unit_type, 0)
    setattr(army, unit_type, current + amount)
    army.updated_at = datetime.utcnow()

    # Kunlik yollash hisobi va vazifa tekshiruvi
    await check_and_reset_daily_limits(session, user)
    old_cnt = getattr(user, "daily_recruit_count", 0) or 0
    user.daily_recruit_count = old_cnt + amount
    quest_completed = False
    if old_cnt < 100 <= user.daily_recruit_count:
        user.gold += 500
        user.food += 1000
        user.xp += 80
        quest_completed = True

    # Tranzaksiyani yozish
    tx = models.Transaction(
        user_id=user_id,
        amount_gold=-gold_cost,
        amount_iron=-iron_cost,
        action_type="recruit_troops",
        details=f"Yollangan: +{amount} {unit_type}",
    )
    session.add(tx)

    await session.commit()
    return True, quest_completed


# ============================================================
# MARCH & BATTLE CRUD
# ============================================================

async def create_battle_march(
    session: AsyncSession,
    attacker_user_id: int,
    source_territory_id: int,
    target_territory_id: int,
    infantry: int,
    archers: int,
    cavalry: int,
    spearmen: int,
    special_troops: int,
    character_id: Optional[int],
    duration_minutes: int,
    has_dragon: bool = False,
    dragon_tactic: str = "none",
    dragon_id: Optional[int] = None,
    catapults: int = 0,
    siege_towers: int = 0,
    champion: Optional[str] = None,
) -> models.BattleMarch:
    """Yangi harbiy yurishni ro'yxatga olish"""
    # O'yinchining armiyasidan yuborilgan qismini ayirish
    army_res = await session.execute(select(models.Army).where(models.Army.user_id == attacker_user_id))
    army = army_res.scalar_one_or_none()
    march_champ = champion
    if army:
        army.infantry = max(0, army.infantry - infantry)
        army.archers = max(0, army.archers - archers)
        army.cavalry = max(0, army.cavalry - cavalry)
        army.spearmen = max(0, army.spearmen - spearmen)
        army.special_troops = max(0, army.special_troops - special_troops)
        army.catapults = max(0, (army.catapults or 0) - catapults)
        army.siege_towers = max(0, (army.siege_towers or 0) - siege_towers)
        if not march_champ:
            march_champ = army.champion

    arrival_time = datetime.utcnow() + timedelta(minutes=duration_minutes)

    march = models.BattleMarch(
        attacker_user_id=attacker_user_id,
        source_territory_id=source_territory_id,
        target_territory_id=target_territory_id,
        infantry=infantry,
        archers=archers,
        cavalry=cavalry,
        spearmen=spearmen,
        special_troops=special_troops,
        character_id=character_id,
        has_dragon=has_dragon,
        dragon_id=dragon_id,
        dragon_tactic=dragon_tactic,
        catapults=catapults,
        siege_towers=siege_towers,
        champion=march_champ,
        departure_time=datetime.utcnow(),
        arrival_time=arrival_time,
        status="marching",
    )
    session.add(march)
    await session.commit()
    return march


async def get_due_marches(session: AsyncSession) -> List[models.BattleMarch]:
    """Manziliga yetib borgan (resolved qilinishi kerak bo'lgan) yurishlar"""
    now = datetime.utcnow()
    result = await session.execute(
        select(models.BattleMarch).where(
            models.BattleMarch.status == "marching",
            models.BattleMarch.arrival_time <= now,
        )
    )
    return list(result.scalars().all())


# ============================================================
# RANKING CRUD
# ============================================================

async def get_top_houses(session: AsyncSession, limit: int = 10) -> List[models.House]:
    """Prestige bo'yicha eng kuchli xonadonlar"""
    result = await session.execute(
        select(models.House).order_by(desc(models.House.prestige)).limit(limit)
    )
    return list(result.scalars().all())


async def get_top_players(session: AsyncSession, limit: int = 10) -> List[models.User]:
    """Daraja va prestige bo'yicha top o'yinchilar"""
    result = await session.execute(
        select(models.User)
        .options(selectinload(models.User.house), selectinload(models.User.characters))
        .order_by(desc(models.User.level), desc(models.User.prestige))
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_top_wealthy(session: AsyncSession, limit: int = 10) -> List[models.User]:
    """Oltin boyligi bo'yicha eng boy Lordlar"""
    result = await session.execute(
        select(models.User)
        .options(selectinload(models.User.house))
        .order_by(desc(models.User.gold))
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_top_armies(session: AsyncSession, limit: int = 10) -> List[Tuple[models.User, int]]:
    """Armiya soni bo'yicha eng qudratli sarkardalar"""
    result = await session.execute(
        select(
            models.User,
            (models.Army.infantry + models.Army.archers + models.Army.cavalry + models.Army.spearmen + models.Army.special_troops).label("total_army")
        )
        .join(models.Army, models.Army.user_id == models.User.id)
        .options(selectinload(models.User.house))
        .order_by(desc("total_army"))
        .limit(limit)
    )
    return list(result.all())


# ============================================================
# HOUSE GOVERNANCE & VOTING CRUD
# ============================================================

async def get_house_members_with_characters(session: AsyncSession, house_id: int) -> List[models.User]:
    """Xonadondagi barcha a'zolarni personajlari bilan olish"""
    result = await session.execute(
        select(models.User)
        .options(selectinload(models.User.characters))
        .where(models.User.house_id == house_id)
        .order_by(models.User.rank, desc(models.User.level))
    )
    return list(result.scalars().all())


async def set_user_rank(session: AsyncSession, user_id: int, new_rank: str) -> bool:
    """O'yinchining xonadondagi lavozimini o'zgartirish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False
    user.rank = new_rank
    await session.commit()
    return True


async def cast_house_vote(session: AsyncSession, house_id: int, voter_user_id: int, candidate_user_id: int) -> str:
    """Lord sayloviga ovoz berish yoki yangilash"""
    # Tekshiramiz: avval ovoz berganmi
    res = await session.execute(
        select(models.HouseVote).where(
            models.HouseVote.house_id == house_id,
            models.HouseVote.voter_user_id == voter_user_id,
        )
    )
    vote = res.scalar_one_or_none()
    if vote:
        vote.candidate_user_id = candidate_user_id
        vote.voted_at = datetime.utcnow()
    else:
        new_vote = models.HouseVote(
            house_id=house_id,
            voter_user_id=voter_user_id,
            candidate_user_id=candidate_user_id,
        )
        session.add(new_vote)
    await session.flush()

    # Ovozlar hisobi: agar kimdir 50% dan ortiq ovoz olsa, Lord bo'ladi
    total_members_res = await session.execute(
        select(func.count(models.User.id)).where(models.User.house_id == house_id)
    )
    total_members = total_members_res.scalar() or 1

    votes_for_cand_res = await session.execute(
        select(func.count(models.HouseVote.id)).where(
            models.HouseVote.house_id == house_id,
            models.HouseVote.candidate_user_id == candidate_user_id,
        )
    )
    votes_for_cand = votes_for_cand_res.scalar() or 0

    outcome = f"Ovozingiz qabul qilindi ({votes_for_cand}/{total_members} ovoz)."
    # Agar 50% dan ko'p ovoz to'plansa (yoki xonadonda 1-2 kishi bo'lsa)
    if votes_for_cand > (total_members / 2):
        house = await session.get(models.House, house_id)
        cand = await get_user_any(session, candidate_user_id)
        if house and cand:
            # Eski lordni knight darajasiga tushiramiz
            old_lord_res = await session.execute(
                select(models.User).where(models.User.house_id == house_id, models.User.rank == "king")
            )
            for old_lord in old_lord_res.scalars().all():
                old_lord.rank = "knight"

            cand.rank = "king"
            house.lord_user_id = cand.telegram_id
            house.lord_elected_at = datetime.utcnow()
            outcome = f"🎉 Tabriklaymiz! {cand.full_name} ko'pchilik ovoz bilan xonadon Lordi (King) deb e'lon qilindi!"

    await session.commit()
    return outcome


async def get_house_election_stats(session: AsyncSession, house_id: int, current_user_id: int) -> Dict[str, Any]:
    """Xonadon saylovi tafsilotlari va ovozlar statistikasi"""
    house = await session.get(models.House, house_id)
    members = await get_house_members_with_characters(session, house_id)
    total_members = len(members)
    needed_votes = (total_members // 2) + 1 if total_members > 2 else 1

    votes_res = await session.execute(
        select(models.HouseVote).where(models.HouseVote.house_id == house_id)
    )
    all_votes = votes_res.scalars().all()

    my_vote_cand_id = None
    vote_counts = {m.id: 0 for m in members}
    for v in all_votes:
        if v.voter_user_id == current_user_id:
            my_vote_cand_id = v.candidate_user_id
        if v.candidate_user_id in vote_counts:
            vote_counts[v.candidate_user_id] += 1

    candidates = []
    for m in members:
        char_name = m.characters[0].name if m.characters else m.full_name
        v_count = vote_counts.get(m.id, 0)
        pct = int((v_count / total_members) * 100) if total_members > 0 else 0
        is_lord = (house and house.lord_user_id == m.telegram_id) or m.rank == "king"
        candidates.append({
            "id": m.id,
            "telegram_id": m.telegram_id,
            "name": char_name,
            "full_name": m.full_name,
            "rank": m.rank,
            "level": m.level,
            "votes": v_count,
            "pct": pct,
            "is_lord": is_lord,
        })

    candidates.sort(key=lambda c: (c["votes"], c["level"]), reverse=True)

    current_lord = None
    if house and house.lord_user_id:
        current_lord = await get_user_by_telegram_id(session, house.lord_user_id)

    # 10 kunlik muddat hisobi
    remaining_days = 10
    if house and house.lord_user_id and house.lord_elected_at:
        elapsed = max(0, (datetime.utcnow() - house.lord_elected_at).total_seconds())
        remaining_days = max(0, int(10 - (elapsed // 86400)))
    elif not house or not house.lord_user_id:
        remaining_days = 0

    return {
        "house": house,
        "total_members": total_members,
        "needed_votes": needed_votes,
        "candidates": candidates,
        "my_vote_cand_id": my_vote_cand_id,
        "current_lord": current_lord,
        "remaining_days": remaining_days,
        "term_expired": (remaining_days == 0 and house and house.lord_user_id is not None),
    }


async def claim_vacant_house_lord(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Bo'sh xonadon Lordligini egallash"""
    user = await get_user_any(session, user_id)
    if not user or not user.house_id:
        return False, "Foydalanuvchi yoki xonadon topilmadi."

    house = await session.get(models.House, user.house_id)
    if not house:
        return False, "Xonadon topilmadi."

    if house.lord_user_id:
        existing_lord = await get_user_by_telegram_id(session, house.lord_user_id)
        if existing_lord and existing_lord.id != user.id:
            return False, f"❌ Xonadonning allaqachon Lordi mavjud: {existing_lord.full_name}. Saylovda ovoz to'plang!"

    house.lord_user_id = user.telegram_id
    house.lord_elected_at = datetime.utcnow()
    user.rank = "king"
    user.prestige += 100
    await session.commit()
    return True, f"👑 Qasamyod qabul qilindi! Siz {house.name} xonadoni Lordi (King) etib tayinlandingiz! (+100 Prestige)"


async def abdicate_house_lord(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Xonadon Lordi o'z xohishi bilan iste'foga chiqishi (voz kechishi)"""
    user = await get_user_any(session, user_id)
    if not user or not user.house_id:
        return False, "❌ Foydalanuvchi yoki xonadon topilmadi."

    house = await session.get(models.House, user.house_id)
    if not house:
        return False, "❌ Xonadon topilmadi."

    is_lord = (house.lord_user_id == user.telegram_id) or (user.rank == "king")
    if not is_lord:
        return False, "❌ Siz xonadon Lordi emassiz!"

    # 1. Lord unvonini oddiy a'zoga tushiramiz
    user.rank = "member"

    # 2. Xonadon Lordligini vakant qilamiz
    house.lord_user_id = None
    house.lord_elected_at = datetime.utcnow()

    # 3. Saylov ovozlarini tozalaymiz
    await session.execute(
        delete(models.HouseVote).where(models.HouseVote.house_id == house.id)
    )

    await session.commit()
    return True, f"👑 Siz muvaffaqiyatli {house.name} xonadoni Lordligidan voz kechdingiz. Lavozim endi vakant!"


async def transfer_troops_to_lord(
    session: AsyncSession,
    sender_user_id: int,
    lord_user_id: int,
    infantry: int = 0,
    archers: int = 0,
    cavalry: int = 0,
    spearmen: int = 0,
) -> Tuple[bool, str]:
    """A'zolarning xonadon Lordi armiyasiga safarbarlik doirasida askar jo'natishi"""
    sender = await get_user_any(session, sender_user_id)
    lord = await get_user_any(session, lord_user_id)
    if not sender or not lord:
        return False, "O'yinchi topilmadi."

    if sender.house_id != lord.house_id:
        return False, "Faqat o'z xonadoningiz Lordiga askar yuborishingiz mumkin!"

    sender_army_res = await session.execute(select(models.Army).where(models.Army.user_id == sender.id))
    sender_army = sender_army_res.scalar_one_or_none()
    lord_army_res = await session.execute(select(models.Army).where(models.Army.user_id == lord.id))
    lord_army = lord_army_res.scalar_one_or_none()

    if not sender_army or not lord_army:
        return False, "Armiya ma'lumotlari topilmadi."

    if (sender_army.infantry < infantry or sender_army.archers < archers or 
        sender_army.cavalry < cavalry or sender_army.spearmen < spearmen):
        return False, "Yetarli askar mavjud emas!"

    tot = infantry + archers + cavalry + spearmen
    if tot <= 0:
        return False, "Kamida bitta askar yuborishingiz kerak."

    sender_army.infantry -= infantry
    sender_army.archers -= archers
    sender_army.cavalry -= cavalry
    sender_army.spearmen -= spearmen

    lord_army.infantry += infantry
    lord_army.archers += archers
    lord_army.cavalry += cavalry
    lord_army.spearmen += spearmen

    prestige_gain = max(10, tot // 4)
    sender.prestige += prestige_gain
    await session.commit()
    return True, f"✅ Lord armiyasiga +{tot} askar safarbar qilindi! (+{prestige_gain} Prestige)"


async def admin_appoint_house_lord(session: AsyncSession, house_id: int, target_user_id: int) -> Tuple[bool, str]:
    """Admin tomonidan xonadonga Lord tayinlash"""
    house = await session.get(models.House, house_id)
    if not house:
        return False, "❌ Xonadon topilmadi."

    target_user = await get_user_any(session, target_user_id)
    if not target_user:
        return False, "❌ Foydalanuvchi topilmadi."

    # Agar xonadonning amaldagi boshqa Lordi bo'lsa, uni ritsarga tushiramiz
    if house.lord_user_id and house.lord_user_id != target_user.telegram_id:
        old_lord = await get_user_by_telegram_id(session, house.lord_user_id)
        if old_lord:
            if old_lord.rank == "king":
                old_lord.rank = "knight"
            old_hm_res = await session.execute(
                select(models.HouseMember).where(models.HouseMember.user_id == old_lord.id)
            )
            old_hm = old_hm_res.scalar_one_or_none()
            if old_hm:
                old_hm.rank = "knight"

    # Yangi lordni tayinlaymiz
    target_user.house_id = house.id
    target_user.rank = "king"
    target_user.prestige = (target_user.prestige or 0) + 150
    house.lord_user_id = target_user.telegram_id
    house.lord_elected_at = datetime.utcnow()

    # HouseMember va Character ni sinxron yangilash
    hm_res = await session.execute(
        select(models.HouseMember).where(models.HouseMember.user_id == target_user.id)
    )
    hm = hm_res.scalar_one_or_none()
    if hm:
        hm.house_id = house.id
        hm.rank = "king"
    else:
        hm = models.HouseMember(house_id=house.id, user_id=target_user.id, rank="king")
        session.add(hm)

    char_res = await session.execute(
        select(models.Character).where(models.Character.user_id == target_user.id)
    )
    char = char_res.scalar_one_or_none()
    if char:
        char.house_id = house.id

    await session.commit()
    name = target_user.full_name or target_user.username or f"User {target_user.id}"
    return True, f"👑 {name} muvaffaqiyatli {house.emoji} {house.name} xonadoni Lordi (King) etib tayinlandi!"


async def admin_transfer_user_house(session: AsyncSession, user_id: int, new_house_id: int) -> Tuple[bool, str]:
    """Admin tomonidan o'yinchini boshqa xonadonga ko'chirish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."

    new_house = await session.get(models.House, new_house_id)
    if not new_house:
        return False, "❌ Yangi xonadon topilmadi."

    # Agar eski xonadoni lordi bo'lsa, lordlikni bo'shatamiz
    if user.house_id:
        old_house = await session.get(models.House, user.house_id)
        if old_house and old_house.lord_user_id == user.telegram_id:
            old_house.lord_user_id = None

    user.house_id = new_house.id
    user.rank = "member"

    # HouseMember
    hm_res = await session.execute(
        select(models.HouseMember).where(models.HouseMember.user_id == user.id)
    )
    hm = hm_res.scalar_one_or_none()
    if hm:
        hm.house_id = new_house.id
        hm.rank = "member"
    else:
        hm = models.HouseMember(house_id=new_house.id, user_id=user.id, rank="member")
        session.add(hm)

    # Character
    char_res = await session.execute(
        select(models.Character).where(models.Character.user_id == user.id)
    )
    char = char_res.scalar_one_or_none()
    if char:
        char.house_id = new_house.id

    await session.commit()
    name = user.full_name or user.username or f"User {user.id}"
    return True, f"✅ {name} {new_house.emoji} {new_house.name} xonadoniga muvaffaqiyatli ko'chirildi!"


async def admin_remove_user_from_house(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Admin tomonidan o'yinchini xonadondan chiqarish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."

    if not user.house_id:
        return False, "Foydalanuvchi allaqachon xonadonsiz."

    old_house = await session.get(models.House, user.house_id)
    if old_house and old_house.lord_user_id == user.telegram_id:
        old_house.lord_user_id = None

    user.house_id = None
    user.rank = "member"

    await session.execute(
        delete(models.HouseMember).where(models.HouseMember.user_id == user.id)
    )
    await session.commit()
    name = user.full_name or user.username or f"User {user.id}"
    return True, f"✅ {name} xonadondan chiqarildi!"


async def get_user_army(session: AsyncSession, user_id: int) -> models.Army:
    """Foydalanuvchi armiyasini olish yoki yangisini yaratish"""
    res = await session.execute(select(models.Army).where(models.Army.user_id == user_id))
    army = res.scalar_one_or_none()
    if not army:
        army = models.Army(user_id=user_id, infantry=0, archers=0, cavalry=0, spearmen=0, special_troops=0)
        session.add(army)
        await session.commit()
    return army


async def admin_set_user_army(
    session: AsyncSession,
    user_id: int,
    infantry: Optional[int] = None,
    archers: Optional[int] = None,
    cavalry: Optional[int] = None,
    spearmen: Optional[int] = None,
    special_troops: Optional[int] = None,
    add_mode: bool = False,
) -> Tuple[bool, str]:
    """Admin tomonidan o'yinchi armiyasini belgilash yoki qo'shish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."

    army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
    army = army_res.scalar_one_or_none()
    if not army:
        army = models.Army(user_id=user.id)
        session.add(army)

    if add_mode:
        if infantry is not None: army.infantry = max(0, (army.infantry or 0) + infantry)
        if archers is not None: army.archers = max(0, (army.archers or 0) + archers)
        if cavalry is not None: army.cavalry = max(0, (army.cavalry or 0) + cavalry)
        if spearmen is not None: army.spearmen = max(0, (army.spearmen or 0) + spearmen)
        if special_troops is not None: army.special_troops = max(0, (army.special_troops or 0) + special_troops)
    else:
        if infantry is not None: army.infantry = max(0, infantry)
        if archers is not None: army.archers = max(0, archers)
        if cavalry is not None: army.cavalry = max(0, cavalry)
        if spearmen is not None: army.spearmen = max(0, spearmen)
        if special_troops is not None: army.special_troops = max(0, special_troops)

    await session.commit()
    return True, f"⚔️ {user.full_name} armiyasi yangilandi: 🛡️{army.infantry} 🏹{army.archers} 🐎{army.cavalry} 🗡️{army.spearmen}"


async def admin_dismiss_house_lord(session: AsyncSession, house_id: int) -> Tuple[bool, str]:
    """Admin tomonidan xonadon Lordini lavozimidan ozod etish (Vakant qilish)"""
    house = await session.get(models.House, house_id)
    if not house:
        return False, "❌ Xonadon topilmadi."

    if not house.lord_user_id:
        return False, f"❌ {house.name} xonadonida allaqachon Lord yo'q (Vakant)."

    old_lord = await get_user_by_telegram_id(session, house.lord_user_id)
    if old_lord and old_lord.rank == "king":
        old_lord.rank = "knight"

    house.lord_user_id = None
    house.lord_elected_at = datetime.utcnow()
    await session.commit()
    return True, f"🚫 {house.emoji} {house.name} xonadonining Lord lavozimi bo'shatildi (Vakant)!"


async def admin_reset_house_election_votes(session: AsyncSession, house_id: int) -> Tuple[bool, str]:
    """Xonadon saylov ovozlarini tozalash"""
    house = await session.get(models.House, house_id)
    if not house:
        return False, "❌ Xonadon topilmadi."

    await session.execute(
        delete(models.HouseVote).where(models.HouseVote.house_id == house_id)
    )
    await session.commit()
    return True, f"🗳️ {house.emoji} {house.name} xonadoni saylov ovozlari muvaffaqiyatli tozalandi (0 ga tushirildi)!"


# ============================================================
# ALLIANCE CRUD (1 TA HARBIY VA 1 TA TO'Y ITTIFOQI)
# ============================================================

# NPC xonadonlar ID lari (ittifoq tuzish taqiqlanadi)
NPC_HOUSE_IDS = {47, 48, 49, 50}


async def get_active_alliances_for_house(session: AsyncSession, house_id: int) -> List[models.Alliance]:
    """Xonadonning barcha faol ittifoqlari"""
    res = await session.execute(
        select(models.Alliance).where(
            (models.Alliance.house_a_id == house_id) | (models.Alliance.house_b_id == house_id),
            models.Alliance.status == "active",
        )
    )
    return list(res.scalars().all())


async def get_pending_alliances_for_house(session: AsyncSession, house_id: int) -> List[models.Alliance]:
    """Xonadonga kelgan kutish holatidagi ittifoq takliflari"""
    res = await session.execute(
        select(models.Alliance).where(
            models.Alliance.house_b_id == house_id,
            models.Alliance.status == "pending",
        )
    )
    return list(res.scalars().all())


async def propose_alliance(
    session: AsyncSession,
    from_house_id: int,
    to_house_id: int,
    alliance_type: str = "military",
) -> Tuple[bool, str]:
    """Boshqa xonadonga ittifoq taklif qilish (1 ta Harbiy, 1 ta To'y ittifoqi)"""
    if from_house_id == to_house_id:
        return False, "O'z xonadoningizga ittifoq taklif qila olmaysiz!"

    if to_house_id in NPC_HOUSE_IDS or from_house_id in NPC_HOUSE_IDS:
        return False, "❌ White Walkers, Free Folk, Night's Watch yoki boshqa NPC xonadonlar bilan ittifoq tuzib bo'lmaydi!"

    to_house = await session.get(models.House, to_house_id)
    if not to_house or getattr(to_house, "is_npc", False):
        return False, "❌ Ushbu xonadon bilan ittifoq tuzish imkoni yo'q!"

    from_house = await session.get(models.House, from_house_id)
    if not from_house:
        return False, "Xonadon topilmadi."

    type_name_uz = "Harbiy Ittifoq" if alliance_type == "military" else "To'y Ittifoqi"

    # 1 ta harbiy va 1 ta to'y ittifoqi cheklovi (From house)
    from_existing = await session.execute(
        select(models.Alliance).where(
            ((models.Alliance.house_a_id == from_house_id) | (models.Alliance.house_b_id == from_house_id)),
            models.Alliance.type == alliance_type,
            models.Alliance.status == "active",
        )
    )
    if from_existing.scalars().first():
        return False, f"❌ Xonadoningizda allaqachon 1 ta faol {type_name_uz} mavjud! (Maksimal 1 ta ruxsat berilgan)"

    # To house uchun ham shu toifadagi faol ittifoqni tekshirish
    to_existing = await session.execute(
        select(models.Alliance).where(
            ((models.Alliance.house_a_id == to_house_id) | (models.Alliance.house_b_id == to_house_id)),
            models.Alliance.type == alliance_type,
            models.Alliance.status == "active",
        )
    )
    if to_existing.scalars().first():
        return False, f"❌ {to_house.name} xonadonida allaqachon 1 ta faol {type_name_uz} mavjud!"

    # Ushbu ikki xonadon o'rtasidagi mavjud aloqani tekshirish
    res = await session.execute(
        select(models.Alliance).where(
            ((models.Alliance.house_a_id == from_house_id) & (models.Alliance.house_b_id == to_house_id)) |
            ((models.Alliance.house_a_id == to_house_id) & (models.Alliance.house_b_id == from_house_id))
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        if existing.status == "active":
            return False, f"Ushbu xonadon bilan allaqachon faol ittifoq mavjud ({existing.type})!"
        elif existing.status == "pending":
            return False, "Ittifoq taklifi allaqachon yuborilgan, javob kutilmoqda."
        else:
            existing.status = "pending"
            existing.type = alliance_type
            existing.house_a_id = from_house_id
            existing.house_b_id = to_house_id
            existing.created_at = datetime.utcnow()
            await session.commit()
            return True, f"💍 {type_name_uz} taklifi qaytadan yuborildi!"

    new_alliance = models.Alliance(
        house_a_id=from_house_id,
        house_b_id=to_house_id,
        type=alliance_type,
        status="pending",
    )
    session.add(new_alliance)
    await session.commit()
    return True, f"🤝 {to_house.name} xonadoniga {type_name_uz} taklifi muvaffaqiyatli yuborildi!"


async def respond_to_alliance(session: AsyncSession, alliance_id: int, accept: bool) -> Tuple[bool, str]:
    """Ittifoq taklifini qabul qilish yoki rad etish"""
    alliance = await session.get(models.Alliance, alliance_id)
    if not alliance:
        return False, "Taklif topilmadi."

    if not accept:
        alliance.status = "rejected"
        await session.commit()
        return True, "Ittifoq taklifi rad etildi."

    # Qabul qilishda ham 1 ta harbiy / 1 ta to'y limiti buzilmaganini tekshirish
    type_name_uz = "Harbiy Ittifoq" if alliance.type == "military" else "To'y Ittifoqi"
    for h_id in [alliance.house_a_id, alliance.house_b_id]:
        active_check = await session.execute(
            select(models.Alliance).where(
                ((models.Alliance.house_a_id == h_id) | (models.Alliance.house_b_id == h_id)),
                models.Alliance.type == alliance.type,
                models.Alliance.status == "active",
                models.Alliance.id != alliance.id,
            )
        )
        if active_check.scalars().first():
            h_obj = await session.get(models.House, h_id)
            h_name = h_obj.name if h_obj else "Xonadon"
            return False, f"❌ {h_name} allaqachon boshqa xonadon bilan {type_name_uz} tuzgan!"

    alliance.status = "active"
    await session.commit()
    return True, f"🎉 {type_name_uz} rasman kuchga kirdi!"


async def break_alliance(
    session: AsyncSession,
    alliance_id: int,
    broken_by_house_id: int
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Ittifoqni bir tomonlama uzish va qasamyod buzilgani uchun -10% jarima qo'llash"""
    alliance = await session.get(models.Alliance, alliance_id)
    if not alliance or alliance.status != "active":
        return False, "❌ Faol ittifoq topilmadi.", None

    if broken_by_house_id not in [alliance.house_a_id, alliance.house_b_id]:
        return False, "❌ Sizning xonadoningiz ushbu ittifoq a'zosi emas.", None

    other_house_id = alliance.house_b_id if broken_by_house_id == alliance.house_a_id else alliance.house_a_id

    breaker_house = await session.get(models.House, broken_by_house_id)
    other_house = await session.get(models.House, other_house_id)
    if not breaker_house or not other_house:
        return False, "❌ Xonadon ma'lumotlari topilmadi.", None

    # Ittifoq statusini 'broken' ga o'tkazamiz
    alliance.status = "broken"

    # 1. Xonadon nufuzi (Prestige) dan -10%
    house_old_prestige = breaker_house.prestige or 0
    house_loss = int(house_old_prestige * 0.10)
    breaker_house.prestige = max(0, house_old_prestige - house_loss)

    # 2. Xonadondagi barcha lordlarning XP va Prestige ballaridan -10%
    members_res = await session.execute(
        select(models.User).where(models.User.house_id == broken_by_house_id)
    )
    members = members_res.scalars().all()
    for m in members:
        if m.prestige:
            m.prestige = max(0, int(m.prestige * 0.90))
        if m.xp:
            m.xp = max(0, int(m.xp * 0.90))

    await session.commit()

    type_name_uz = "Harbiy Ittifoq" if alliance.type == "military" else "To'y Ittifoqi"
    info = {
        "alliance_type": alliance.type,
        "type_name": type_name_uz,
        "breaker_house": breaker_house,
        "other_house": other_house,
        "other_lord_id": other_house.lord_user_id,
        "prestige_lost": house_loss,
        "members_affected": len(members),
    }
    return True, f"💔 {other_house.name} bilan tuzilgan {type_name_uz} bekor qilindi!\nQasamyod buzilgani sababli xonadoningiz va barcha a'zolardan -10% XP hamda -10% Prestige chegirildi.", info


async def send_castle_reinforcements(
    session: AsyncSession,
    user_id: int,
    target_territory_id: int,
    infantry: int,
    archers: int,
    cavalry: int,
    spearmen: int,
) -> Tuple[bool, str]:
    """Ittifoqchi qal'aga mudofaa uchun qo'shin (garnizon) yordami yuborish"""
    user = await get_user_any(session, user_id)
    territory = await session.get(models.Territory, target_territory_id)
    if not user or not territory:
        return False, "Foydalanuvchi yoki qal'a topilmadi."

    army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
    army = army_res.scalar_one_or_none()
    if not army:
        return False, "Armiya topilmadi."

    if (army.infantry < infantry or army.archers < archers or 
        army.cavalry < cavalry or army.spearmen < spearmen):
        return False, "Yetarli askar mavjud emas!"

    total_sent = infantry + archers + cavalry + spearmen
    if total_sent <= 0:
        return False, "Kamida bitta askar yuborishingiz kerak."

    # Askarlarni shaxsiy armiyadan ayirish
    army.infantry -= infantry
    army.archers -= archers
    army.cavalry -= cavalry
    army.spearmen -= spearmen

    # Qal'a mudofaasini to'g'ridan-to'g'ri kuchaytirish
    territory.garrison_infantry += infantry
    territory.garrison_archers += archers
    territory.garrison_cavalry += cavalry
    territory.garrison_spearmen += spearmen

    # Yordamchi hisobi
    user.prestige += 30
    await session.commit()
    return True, f"✅ Qal'a mudofaasiga +{total_sent} askar safarbar qilindi! (+30 Prestige)"


async def send_castle_reinforcements_proportional(
    session: AsyncSession,
    user_id: int,
    target_territory_id: int,
    count: Optional[int] = None,
    send_all: bool = False,
) -> Tuple[bool, str, Dict[str, int]]:
    """O'yinchi armiyasidan mutanosib ravishda qal'a garnizoniga askar joylashtirish"""
    user = await get_user_any(session, user_id)
    territory = await session.get(models.Territory, target_territory_id)
    if not user or not territory:
        return False, "Foydalanuvchi yoki qal'a topilmadi.", {}

    if not user.house_id:
        return False, "❌ Qal'ani himoya qilish uchun avval biror xonadonga a'zo bo'ling!", {}

    is_own = (territory.owner_house_id == user.house_id) or (territory.owner_house_id is None)
    is_ally = False
    if not is_own and territory.owner_house_id:
        al_res = await session.execute(
            select(models.Alliance).where(
                models.Alliance.status == "active",
                ((models.Alliance.house_a_id == user.house_id) & (models.Alliance.house_b_id == territory.owner_house_id)) |
                ((models.Alliance.house_a_id == territory.owner_house_id) & (models.Alliance.house_b_id == user.house_id))
            )
        )
        is_ally = al_res.scalar_one_or_none() is not None

    if not is_own and not is_ally and territory.owner_house_id is not None:
        return False, "❌ Siz faqat o'z xonadoningiz yoki rasmiy ittifoqchingiz qal'asiga mudofaa askarlarini joylashtira olasiz!", {}

    army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
    army = army_res.scalar_one_or_none()
    if not army:
        return False, "Armiya topilmadi.", {}

    u_inf = army.infantry or 0
    u_arc = army.archers or 0
    u_cav = army.cavalry or 0
    u_sp = army.spearmen or 0
    total_army = u_inf + u_arc + u_cav + u_sp

    if total_army <= 0:
        return False, "❌ Sizda qal'aga joylashtirish uchun askar yo'q!", {}

    if send_all or (count is not None and count >= total_army):
        s_inf, s_arc, s_cav, s_sp = u_inf, u_arc, u_cav, u_sp
    else:
        req_count = count if (count is not None and count > 0) else 1
        req_count = min(req_count, total_army)
        ratio = req_count / float(total_army)

        s_inf = min(u_inf, int(u_inf * ratio))
        s_arc = min(u_arc, int(u_arc * ratio))
        s_cav = min(u_cav, int(u_cav * ratio))
        s_sp = min(u_sp, int(u_sp * ratio))

        rem = req_count - (s_inf + s_arc + s_cav + s_sp)
        for _ in range(rem):
            if (u_inf - s_inf) > 0:
                s_inf += 1
            elif (u_arc - s_arc) > 0:
                s_arc += 1
            elif (u_cav - s_cav) > 0:
                s_cav += 1
            elif (u_sp - s_sp) > 0:
                s_sp += 1

    tot_s = s_inf + s_arc + s_cav + s_sp
    if tot_s <= 0:
        return False, "Yuboriladigan askarlar soni 0 ga teng.", {}

    army.infantry = max(0, (army.infantry or 0) - s_inf)
    army.archers = max(0, (army.archers or 0) - s_arc)
    army.cavalry = max(0, (army.cavalry or 0) - s_cav)
    army.spearmen = max(0, (army.spearmen or 0) - s_sp)

    territory.garrison_infantry = (territory.garrison_infantry or 0) + s_inf
    territory.garrison_archers = (territory.garrison_archers or 0) + s_arc
    territory.garrison_cavalry = (territory.garrison_cavalry or 0) + s_cav
    territory.garrison_spearmen = (territory.garrison_spearmen or 0) + s_sp

    user.prestige = (user.prestige or 0) + 2
    await session.commit()
    sent_dict = {
        "infantry": s_inf,
        "archers": s_arc,
        "cavalry": s_cav,
        "spearmen": s_sp,
        "total": tot_s,
    }
    return True, f"✅ Qal'a mudofaasiga +{tot_s:,} askar joylashtirildi! (+2 Prestige)", sent_dict


async def withdraw_castle_reinforcements(
    session: AsyncSession,
    user_id: int,
    territory_id: int,
    count: Optional[int] = None,
    withdraw_all: bool = False,
) -> Tuple[bool, str, Dict[str, int]]:
    """Qal'a garnizonidan askarlarni mutanosib ravishda o'yinchining shaxsiy armiyasiga qaytarib olish"""
    user = await get_user_any(session, user_id)
    territory = await session.get(models.Territory, territory_id)
    if not user or not territory:
        return False, "Foydalanuvchi yoki qal'a topilmadi.", {}

    if not user.house_id or territory.owner_house_id != user.house_id:
        return False, "❌ Siz faqat o'z xonadoningiz qal'asi garnizonidan askar qaytara olasiz!", {}

    house = await session.get(models.House, user.house_id)
    is_lord = house and ((house.lord_user_id == user.telegram_id) or (user.rank == "king"))
    if not is_lord:
        return False, "❌ Qal'a garnizonidan askarlarni qaytarib olish huquqi faqat Xonadon Lordiga tegishli!", {}

    army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
    army = army_res.scalar_one_or_none()
    if not army:
        army = models.Army(
            user_id=user.id,
            infantry=0,
            archers=0,
            cavalry=0,
            spearmen=0,
            special_troops=0
        )
        session.add(army)
        await session.flush()

    g_inf = territory.garrison_infantry or 0
    g_arc = territory.garrison_archers or 0
    g_cav = territory.garrison_cavalry or 0
    g_sp = territory.garrison_spearmen or 0
    tot_g = g_inf + g_arc + g_cav + g_sp

    if tot_g <= 0:
        return False, "❌ Qal'a garnizonida qaytarib olish uchun askarlar mavjud emas!", {}

    if withdraw_all or (count is not None and count >= tot_g):
        w_inf, w_arc, w_cav, w_sp = g_inf, g_arc, g_cav, g_sp
    else:
        req_count = count if (count is not None and count > 0) else 1
        req_count = min(req_count, tot_g)
        ratio = req_count / float(tot_g)

        w_inf = min(g_inf, int(g_inf * ratio))
        w_arc = min(g_arc, int(g_arc * ratio))
        w_cav = min(g_cav, int(g_cav * ratio))
        w_sp = min(g_sp, int(g_sp * ratio))

        rem = req_count - (w_inf + w_arc + w_cav + w_sp)
        for _ in range(rem):
            if (g_inf - w_inf) > 0:
                w_inf += 1
            elif (g_arc - w_arc) > 0:
                w_arc += 1
            elif (g_cav - w_cav) > 0:
                w_cav += 1
            elif (g_sp - w_sp) > 0:
                w_sp += 1

    tot_w = w_inf + w_arc + w_cav + w_sp
    if tot_w <= 0:
        return False, "Qaytarib olinadigan askar miqdori 0 ga teng.", {}

    territory.garrison_infantry = max(0, (territory.garrison_infantry or 0) - w_inf)
    territory.garrison_archers = max(0, (territory.garrison_archers or 0) - w_arc)
    territory.garrison_cavalry = max(0, (territory.garrison_cavalry or 0) - w_cav)
    territory.garrison_spearmen = max(0, (territory.garrison_spearmen or 0) - w_sp)

    army.infantry = (army.infantry or 0) + w_inf
    army.archers = (army.archers or 0) + w_arc
    army.cavalry = (army.cavalry or 0) + w_cav
    army.spearmen = (army.spearmen or 0) + w_sp

    await session.commit()
    withdrawn_dict = {
        "infantry": w_inf,
        "archers": w_arc,
        "cavalry": w_cav,
        "spearmen": w_sp,
        "total": tot_w,
    }
    return True, f"✅ Qal'adan +{tot_w:,} askar shaxsiy armiyangizga qaytarildi!", withdrawn_dict


async def station_dragon_in_castle(session: AsyncSession, user_id: int, territory_id: int, dragon_id: Optional[int] = None) -> Tuple[bool, str]:
    """Ajdarni qal'a mudofaasiga joylashtirish"""
    user = await get_user_any(session, user_id)
    territory = await session.get(models.Territory, territory_id)
    if not user or not territory:
        return False, "Foydalanuvchi yoki qal'a topilmadi."

    if not user.house_id or territory.owner_house_id != user.house_id:
        active_alliances = await get_active_alliances_for_house(session, user.house_id) if user.house_id else []
        is_ally = any(
            (a.house_a_id == territory.owner_house_id or a.house_b_id == territory.owner_house_id)
            for a in active_alliances
        )
        if not is_ally:
            return False, "❌ Faqat o'z xonadoningiz yoki rasmiy ittifoqchingiz qal'asiga ajdar joylashtira olasiz!"

    # Ajdarni aniqlash
    if dragon_id:
        dragon = await session.get(models.Dragon, dragon_id)
        if not dragon or dragon.user_id != user.id:
            return False, "❌ Ushbu ajdar sizga tegishli emas!"
    else:
        available = await get_user_available_dragons(session, user.id)
        if not available:
            all_dragons = await get_user_dragons(session, user.id)
            if not all_dragons:
                return False, "❌ Sizda ajdar yo'q! Avval /dragons bo'limidan ajdar xarid qiling."
            combat = [d for d in all_dragons if d.stage in ["baby", "adult"]]
            if not combat:
                return False, "❌ Sizdagi ajdar hali tuxum holatida! Avval tuxumni ochiring (/dragons)."
            if any(d.hunger < 20 for d in combat):
                return False, "❌ Ajdaringiz juda och (to'qlik < 20%)! Avval uni boqing (/dragons)."
            return False, "❌ Barcha jangovar ajdarlaringiz band (qal'alarda yoki yurishda)!"
        dragon = max(available, key=lambda d: d.power)

    if dragon.stage not in ["baby", "adult"]:
        return False, "❌ Ajdar hali tuxum holatida! Qal'ani himoya qilish uchun avval uni ochiring."

    if dragon.hunger < 20:
        return False, f"❌ {dragon.name} juda och (to'qlik: {dragon.hunger}%)! Mudofaa uchun to'qlik kamida 20% bo'lishi kerak."

    cur_status = await get_dragon_deployment_status(session, dragon.id)
    if cur_status["type"] == "stationed":
        t_name = cur_status.get("territory_name", "boshqa qal'a")
        return False, f"⚠️ {dragon.name} allaqachon **{t_name}** qal'asi mudofaasida xizmat qilmoqda! Avval uni u yerdan qaytaring."
    elif cur_status["type"] == "marching":
        return False, f"⚠️ {dragon.name} hozirda dushmanga qarshi harbiy yurishda/jangda qatnashmoqda!"

    reinf_data = {}
    if territory.reinforcements_json:
        try:
            reinf_data = json.loads(territory.reinforcements_json)
        except Exception:
            reinf_data = {}

    stationed_list = reinf_data.get("stationed_dragons", [])
    if not stationed_list and "stationed_dragon" in reinf_data and isinstance(reinf_data["stationed_dragon"], dict):
        stationed_list.append(reinf_data["stationed_dragon"])

    if any(st.get("dragon_id") == dragon.id for st in stationed_list):
        return False, f"⚠️ {dragon.name} allaqachon ushbu qal'a osmonida qo'riqchilik qilmoqda!"

    char_res = await session.execute(select(models.Character.name).where(models.Character.user_id == user.id).limit(1))
    char_name = char_res.scalar_one_or_none() or user.full_name

    new_st = {
        "user_id": user.id,
        "user_name": char_name,
        "dragon_id": dragon.id,
        "dragon_name": dragon.name,
        "power": dragon.power,
        "stationed_at": datetime.utcnow().isoformat(),
    }
    stationed_list.append(new_st)
    reinf_data["stationed_dragons"] = stationed_list

    best_dr = max(stationed_list, key=lambda d: d.get("power", 0))
    reinf_data["stationed_dragon"] = best_dr

    territory.reinforcements_json = json.dumps(reinf_data)
    user.prestige += 50
    await session.commit()
    return True, f"🐉🔥 Ulug'vor {dragon.name} (Kuch: {dragon.power}⚡) {territory.name} qal'asi mudofaasiga joylashtirildi! (+50 Prestige)"


async def recall_dragon_from_castle(session: AsyncSession, user_id: int, territory_id: int, dragon_id: Optional[int] = None) -> Tuple[bool, str]:
    """Ajdarni qal'a mudofaasidan o'z uyasiga qaytarish (aniq ajdar yoki foydalanuvchi ajdari)"""
    user = await get_user_any(session, user_id)
    territory = await session.get(models.Territory, territory_id)
    if not user or not territory:
        return False, "Foydalanuvchi yoki qal'a topilmadi."

    if not territory.reinforcements_json:
        return False, "Qal'ada joylashtirilgan ajdar yo'q."

    try:
        reinf_data = json.loads(territory.reinforcements_json)
    except Exception:
        reinf_data = {}

    stationed_list = reinf_data.get("stationed_dragons", [])
    if not stationed_list and "stationed_dragon" in reinf_data and isinstance(reinf_data["stationed_dragon"], dict):
        stationed_list.append(reinf_data["stationed_dragon"])

    if not stationed_list:
        return False, "Qal'ada joylashtirilgan ajdar topilmadi."

    house = await session.get(models.House, user.house_id) if user.house_id else None
    is_lord = house and (house.lord_user_id == user.telegram_id or user.rank == "king")

    target_idx = None
    target_st = None
    for i, st in enumerate(stationed_list):
        if dragon_id and st.get("dragon_id") == dragon_id:
            if st.get("user_id") == user.id or is_lord:
                target_idx = i
                target_st = st
                break
        elif not dragon_id and st.get("user_id") == user.id:
            target_idx = i
            target_st = st
            break

    if target_idx is None:
        if is_lord and stationed_list:
            target_idx = 0
            target_st = stationed_list[0]
        else:
            return False, "❌ Ushbu qal'ada sizga tegishli ajdar topilmadi!"

    dragon_name = target_st.get("dragon_name", "Ajdar")
    stationed_list.pop(target_idx)
    reinf_data["stationed_dragons"] = stationed_list

    if stationed_list:
        best_dr = max(stationed_list, key=lambda d: d.get("power", 0))
        reinf_data["stationed_dragon"] = best_dr
    else:
        if "stationed_dragon" in reinf_data:
            del reinf_data["stationed_dragon"]

    territory.reinforcements_json = json.dumps(reinf_data)
    await session.commit()
    return True, f"🐉 {dragon_name} qal'a mudofaasidan o'z uyasiga eson-omon qaytarildi."


def get_stationed_dragon_info(territory: models.Territory) -> Optional[Dict[str, Any]]:
    """Qal'ada joylashtirilgan asosiy/eng kuchli ajdar haqida ma'lumot"""
    if not territory or not territory.reinforcements_json:
        return None
    try:
        data = json.loads(territory.reinforcements_json)
        return data.get("stationed_dragon")
    except Exception:
        return None


def get_stationed_dragons_list(territory: models.Territory) -> List[Dict[str, Any]]:
    """Qal'ada joylashtirilgan barcha ajdarlar ro'yxati"""
    if not territory or not territory.reinforcements_json:
        return []
    try:
        data = json.loads(territory.reinforcements_json)
        s_list = data.get("stationed_dragons", [])
        if not s_list and "stationed_dragon" in data and isinstance(data["stationed_dragon"], dict):
            s_list = [data["stationed_dragon"]]
        return s_list
    except Exception:
        return []


async def get_dragon_deployment_status(session: AsyncSession, dragon_id: int) -> Dict[str, Any]:
    """Ajdarning joriy joylashuvini aniqlash:
    - type: 'stationed' (qal'ada mudofaada), territory_id, territory_name
    - type: 'marching' (harbiy yurishda), march_id, target_name
    - type: 'resting' (uyada, erkin)
    """
    march_res = await session.execute(
        select(models.BattleMarch).where(
            models.BattleMarch.dragon_id == dragon_id,
            models.BattleMarch.status == "marching",
        ).limit(1)
    )
    march = march_res.scalar_one_or_none()
    if march:
        target_t = await session.get(models.Territory, march.target_territory_id)
        t_name = target_t.name if target_t else "Dushman qal'asi"
        return {"type": "marching", "march_id": march.id, "target_name": t_name}

    terr_res = await session.execute(select(models.Territory))
    for terr in terr_res.scalars().all():
        if terr.reinforcements_json:
            try:
                data = json.loads(terr.reinforcements_json)
                st_list = data.get("stationed_dragons", [])
                for st in st_list:
                    if st.get("dragon_id") == dragon_id:
                        return {"type": "stationed", "territory_id": terr.id, "territory_name": terr.name}
                single_st = data.get("stationed_dragon")
                if single_st and single_st.get("dragon_id") == dragon_id:
                    return {"type": "stationed", "territory_id": terr.id, "territory_name": terr.name}
            except Exception:
                pass

    return {"type": "resting"}


async def get_user_available_dragons(session: AsyncSession, user_id: int) -> List[models.Dragon]:
    """Faqat uyada bo'sh turgan, jangovar va to'qligi yetarli ajdarlar ro'yxati"""
    dragons = await get_user_dragons(session, user_id)
    available = []
    for d in dragons:
        if d.stage in ["baby", "adult"] and d.hunger >= 20:
            st = await get_dragon_deployment_status(session, d.id)
            if st["type"] == "resting":
                available.append(d)
    return available


# ============================================================
# HOUSE TREASURY & CONTRIBUTIONS CRUD
# ============================================================

async def donate_to_house_treasury(
    session: AsyncSession,
    user_id: int,
    gold: int = 0,
    food: int = 0,
    iron: int = 0,
) -> Tuple[bool, str]:
    """Xonadon umumiy g'aznasiga shaxsiy resurslarni ehson qilish"""
    user = await get_user_any(session, user_id)
    if not user or not user.house_id:
        return False, "Siz hali xonadonga a'zo emassiz."

    if user.gold < gold or user.food < food or user.iron < iron:
        return False, "Xazinaga topshirish uchun resurslaringiz yetarli emas!"

    house = await session.get(models.House, user.house_id)
    if not house:
        return False, "Xonadon topilmadi."

    # Foydalanuvchidan yechish
    user.gold -= gold
    user.food -= food
    user.iron -= iron

    # Xonadon xazinasiga qo'shish
    house.gold += gold
    house.food += food
    house.iron += iron

    # HouseMember dagi hissani yangilash (Eng saxiy a'zolar reytingi uchun)
    hm_res = await session.execute(
        select(models.HouseMember).where(
            models.HouseMember.user_id == user.id,
            models.HouseMember.house_id == house.id,
        )
    )
    hm = hm_res.scalar_one_or_none()
    if hm:
        hm.contribution_gold += gold
        hm.contribution_food += food
        hm.contribution_iron += iron

    await session.commit()
    parts_desc = []
    if gold > 0:
        parts_desc.append(f"{gold:,}🪙")
    if food > 0:
        parts_desc.append(f"{food:,}🌾")
    if iron > 0:
        parts_desc.append(f"{iron:,}⛓️")
    don_str = " + ".join(parts_desc) if parts_desc else "resurslar"
    return True, f"✅ Xonadon g'aznasiga ehson qabul qilindi ({don_str})!"


async def get_top_house_contributors(session: AsyncSession, house_id: int, limit: int = 5) -> List[Tuple[str, str, int]]:
    """Xonadonning eng saxiy homiylari ro'yxati"""
    res = await session.execute(
        select(
            models.User.full_name,
            models.User.rank,
            (models.HouseMember.contribution_gold + models.HouseMember.contribution_iron).label("total_contrib")
        )
        .join(models.HouseMember, models.HouseMember.user_id == models.User.id)
        .where(models.HouseMember.house_id == house_id)
        .order_by(desc("total_contrib"))
        .limit(limit)
    )
    return list(res.all())


async def withdraw_house_treasury(
    session: AsyncSession,
    house_id: int,
    user_id: int,
    gold: int = 0,
    food: int = 0,
    iron: int = 0,
) -> Tuple[bool, str]:
    """Lord xonadon umumiy g'aznasidan shaxsiy hisobiga mablag' yechib olishi"""
    user = await get_user_any(session, user_id)
    house = await session.get(models.House, house_id)
    if not user or not house:
        return False, "Foydalanuvchi yoki xonadon topilmadi."

    is_lord = (house.lord_user_id == user.telegram_id) or user.rank == "king"
    if not is_lord:
        return False, "❌ Faqat Xonadon Lordi g'aznadan foydalanish huquqiga ega!"

    if gold < 0 or food < 0 or iron < 0:
        return False, "Miqdor manfiy bo'lishi mumkin emas!"

    if gold > house.gold:
        return False, f"❌ Xonadon g'aznasida yetarli oltin yo'q! (G'aznada: {house.gold:,}🪙)"
    if food > house.food:
        return False, f"❌ Xonadon g'aznasida yetarli oziq yo'q! (G'aznada: {house.food:,}🌾)"
    if iron > house.iron:
        return False, f"❌ Xonadon g'aznasida yetarli temir yo'q! (G'aznada: {house.iron:,}⛓️)"

    house.gold -= gold
    house.food -= food
    house.iron -= iron

    user.gold += gold
    user.food += food
    user.iron += iron

    await session.commit()
    msg_parts = []
    if gold > 0: msg_parts.append(f"+{gold:,}🪙 oltin")
    if food > 0: msg_parts.append(f"+{food:,}🌾 oziq-ovqat")
    if iron > 0: msg_parts.append(f"+{iron:,}⛓️ temir")
    return True, f"✅ G'aznadan muvaffaqiyatli shaxsiy hisobingizga olindi:\n" + "\n".join(msg_parts)


async def distribute_house_treasury(
    session: AsyncSession,
    house_id: int,
    user_id: int,
    gold: int = 0,
    food: int = 0,
    iron: int = 0,
) -> Tuple[bool, str, int]:
    """Lord xonadon umumiy g'aznasidan barcha a'zolarga teng miqdorda ulashishi"""
    user = await get_user_any(session, user_id)
    house = await session.get(models.House, house_id)
    if not user or not house:
        return False, "Foydalanuvchi yoki xonadon topilmadi.", 0

    is_lord = (house.lord_user_id == user.telegram_id) or user.rank == "king"
    if not is_lord:
        return False, "❌ Faqat Xonadon Lordi g'aznani a'zolarga ulasha oladi!", 0

    members = await get_house_members_with_characters(session, house_id)
    if not members:
        return False, "Xonadonda birorta ham a'zo topilmadi.", 0

    count = len(members)
    tot_gold = gold * count
    tot_food = food * count
    tot_iron = iron * count

    if tot_gold > house.gold:
        return False, f"❌ G'aznada yetarli oltin yo'q! {count} a'zoga jami {tot_gold:,}🪙 kerak (G'aznada: {house.gold:,}🪙).", 0
    if tot_food > house.food:
        return False, f"❌ G'aznada yetarli oziq yo'q! {count} a'zoga jami {tot_food:,}🌾 kerak (G'aznada: {house.food:,}🌾).", 0
    if tot_iron > house.iron:
        return False, f"❌ G'aznada yetarli temir yo'q! {count} a'zoga jami {tot_iron:,}⛓️ kerak (G'aznada: {house.iron:,}⛓️).", 0

    house.gold -= tot_gold
    house.food -= tot_food
    house.iron -= tot_iron

    for m in members:
        m.gold += gold
        m.food += food
        m.iron += iron

    await session.commit()
    return True, f"🎉 {count} nafar xonadon a'zosining har biriga +{gold:,}🪙, +{food:,}🌾, +{iron:,}⛓️ ulashildi!", count


# ============================================================
# DRAGONS CRUD (MAX 2 DRAGONS, 20-LEVEL CAP, EGG LAYING)
# ============================================================

async def get_user_dragons(session: AsyncSession, user_id: int) -> List[models.Dragon]:
    """Foydalanuvchining barcha ajdarlarini olish (maksimal 3 ta)"""
    user = await get_user_any(session, user_id)
    actual_user_id = user.id if user else user_id

    res = await session.execute(
        select(models.Dragon).where(models.Dragon.user_id == actual_user_id).order_by(models.Dragon.id)
    )
    return res.scalars().all()


async def get_user_dragon(session: AsyncSession, user_id: int, dragon_id: Optional[int] = None) -> Optional[models.Dragon]:
    """Foydalanuvchining asosiy yoki tanlangan ajdarini olish"""
    user = await get_user_any(session, user_id)
    actual_user_id = user.id if user else user_id

    if dragon_id:
        res = await session.execute(
            select(models.Dragon).where(models.Dragon.id == dragon_id, models.Dragon.user_id == actual_user_id)
        )
        return res.scalar_one_or_none()

    dragons = await get_user_dragons(session, actual_user_id)
    if not dragons:
        return None
    # Agar jangovar (baby yoki adult) ajdar bo'lsa, eng yuqori quvvatlisini tanlash
    combat_dragons = [d for d in dragons if d.stage in ["baby", "adult"]]
    if combat_dragons:
        return max(combat_dragons, key=lambda d: d.power)
    return dragons[0]


async def claim_dragon_egg(session: AsyncSession, user_id: int, name: str, grade: str = "B") -> Tuple[bool, str, Optional[models.Dragon]]:
    """Yangi ajdar tuxumini xarid qilish (Maksimal 3 ta ajdar)"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi.", None

    existing = await get_user_dragons(session, user.id)
    if len(existing) >= 3:
        return False, "Sizda allaqachon maksimal 3 ta ajdar mavjud!", None

    costs = {
        "A": {"gold": 3000, "iron": 1500},
        "B": {"gold": 2000, "iron": 1000},
        "C": {"gold": 1200, "iron": 600},
    }
    cost = costs.get(grade, {"gold": 2000, "iron": 1000})
    if user.gold < cost["gold"] or user.iron < cost["iron"]:
        return False, f"Ajdar tuxumini xarid qilish uchun {cost['gold']:,}🪙 oltin va {cost['iron']:,}⛓️ temir kerak!\nSizda: {user.gold:,}🪙 oltin, {user.iron:,}⛓️ temir bor.", None

    user.gold -= cost["gold"]
    user.iron -= cost["iron"]

    dragon = models.Dragon(
        user_id=user.id,
        name=name,
        grade=grade,
        stage="egg",
        level=1,
        hunger=50,
        power=60 if grade == "C" else (90 if grade == "B" else 120),
        last_fed=datetime.utcnow(),
    )
    session.add(dragon)
    await session.commit()
    return True, f"🎉 Siz {name} ({grade} Toifa) ajdari tuxumini xarid qildingiz!", dragon


async def hatch_dragon(session: AsyncSession, user_id: int, dragon_id: Optional[int] = None) -> Tuple[bool, str]:
    """Ajdar tuxumini ochirish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    dragon = await get_user_dragon(session, user.id, dragon_id)
    if not dragon:
        return False, "Ajdar topilmadi."

    if dragon.stage != "egg":
        return False, "Ushbu ajdar allaqachon tuxumdan chiqqan!"

    if user.food < 2500 or user.iron < 1500 or user.gold < 1000:
        return False, (
            f"Tuxumni isitib ochirish marosimi uchun quyidagi resurslar kerak:\n"
            f"• 🌾 Oziq-ovqat: 2,500 (sizda: {user.food:,})\n"
            f"• ⛓️ Temir: 1,500 (sizda: {user.iron:,})\n"
            f"• 🪙 Oltin: 1,000 (sizda: {user.gold:,})"
        )

    user.food -= 2500
    user.iron -= 1500
    user.gold -= 1000
    dragon.stage = "baby"
    dragon.power += 80
    user.prestige += 150
    user.xp += 400

    await session.commit()
    return True, f"🔥 AJOYIB MO'JIZA! {dragon.name} olov bag'rida tuxumdan chiqdi! (+150 Prestige)"


async def feed_dragon(session: AsyncSession, user_id: int, dragon_id: Optional[int] = None) -> Tuple[bool, str]:
    """Ajdarni boqish (350 oziq-ovqat talab etiladi)"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    dragon = await get_user_dragon(session, user.id, dragon_id)
    if not dragon:
        return False, "Ajdar topilmadi."

    if dragon.stage == "egg":
        return False, "Tuxumni boqib bo'lmaydi, avval uni ochiring!"

    if user.food < 350:
        return False, "Ajdarni to'ydirish uchun kamida 350🌾 oziq-ovqat kerak!"

    feed_cost = 250 + (dragon.level * 40)
    if user.food < feed_cost:
        return False, f"❌ Ajdarni to'ydirish uchun kamida {feed_cost:,}🌾 oziq-ovqat kerak!"

    user.food -= feed_cost
    dragon.hunger = min(100, dragon.hunger + 30)
    dragon.power += 15
    dragon.last_fed = datetime.utcnow()
    await session.commit()
    return True, f"🍗 {dragon.name} to'yib ovqatlandi! Quvvat: {dragon.power} (To'qlik: {dragon.hunger}%)"


def get_dragon_upgrade_cost(dragon: models.Dragon) -> Dict[str, int]:
    """Ajdar darajasini ko'tarish uchun kerakli resurslar (qimmat va qiyin balans)"""
    lvl = dragon.level
    return {
        "food": 500 + (lvl * 450),
        "iron": 300 + (lvl * 350),
        "gold": 200 + (lvl * 300),
        "min_hunger": 30,
    }


async def train_dragon(session: AsyncSession, user_id: int, dragon_id: Optional[int] = None) -> Tuple[bool, str]:
    """Ajdarni parvoz va olovga mashq qildirish (Maksimal 20-daraja, qiyin va qimmat)"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    dragon = await get_user_dragon(session, user.id, dragon_id)
    if not dragon:
        return False, "Ajdar topilmadi."

    if dragon.stage == "egg":
        return False, "Tuxumni mashq qildirib bo'lmaydi! Avval uni ochiring."

    if dragon.level >= 20:
        return False, f"❌ {dragon.name} maksimal 20-darajaga yetgan! U o'zining cho'qqisida turibdi."

    costs = get_dragon_upgrade_cost(dragon)
    if dragon.hunger < costs["min_hunger"]:
        return False, f"❌ {dragon.name} och (to'qlik: {dragon.hunger}%). Uni avval boqing (kamida {costs['min_hunger']}% kerak)!"

    if user.food < costs["food"] or user.iron < costs["iron"] or user.gold < costs["gold"]:
        return False, (
            f"❌ Ajdarni {dragon.level+1}-darajaga ko'tarish uchun resurslar yetarli emas!\n\n"
            f"Kerak:\n"
            f"• 🌾 Oziq: {costs['food']:,} (sizda: {user.food:,})\n"
            f"• ⛓️ Temir: {costs['iron']:,} (sizda: {user.iron:,})\n"
            f"• 🪙 Oltin: {costs['gold']:,} (sizda: {user.gold:,})\n"
            f"• 🍗 To'qlik: {costs['min_hunger']}%+"
        )

    user.food -= costs["food"]
    user.iron -= costs["iron"]
    user.gold -= costs["gold"]
    dragon.hunger = max(0, dragon.hunger - 20)
    dragon.level += 1
    pwr_gain = 35 + (dragon.level * 5)
    dragon.power += pwr_gain
    user.xp += 150 + (dragon.level * 10)

    if dragon.level >= 5 and dragon.stage == "baby":
        dragon.stage = "adult"
        await session.commit()
        return True, f"🦅 TABRIKLAYMIZ! {dragon.name} balog'atga yetib, bahaybat jangovar ajdarga aylandi! (Daraja: {dragon.level}, Quvvat: {dragon.power})"

    await session.commit()
    return True, f"🔥 Dracarys! {dragon.name} kuchaytirildi: Daraja {dragon.level}/20, Jang Quvvati: +{pwr_gain} ({dragon.power})!"


async def dragon_lay_egg(session: AsyncSession, user_id: int, dragon_id: int) -> Tuple[bool, str]:
    """Ulg'aygan 10-darajali ajdarning tuxum qo'yishi va ikkinchi ajdarga ega bo'lish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    dragon = await session.get(models.Dragon, dragon_id)
    if not dragon or dragon.user_id != user.id:
        return False, "Ajdar topilmadi."

    dragons = await get_user_dragons(session, user.id)
    if len(dragons) >= 3:
        return False, "❌ Sizda allaqachon maksimal 3 ta ajdar mavjud!"

    if dragon.stage != "adult" or dragon.level < 10:
        return False, "❌ Faqat ulg'aygan (Adult) va kamida 10-darajaga yetgan ajdar tuxum qo'ya oladi!"

    if dragon.has_laid_egg:
        return False, "❌ Ushbu ajdar allaqachon nasl qoldirgan."

    if user.gold < 3000 or user.food < 4000 or user.iron < 2000:
        return False, (
            f"Tuxumni parvarishlash va nasl qoldirish marosimi uchun quyidagi resurslar kerak:\n"
            f"• 🪙 Oltin: 3,000 (sizda: {user.gold:,})\n"
            f"• 🌾 Oziq: 4,000 (sizda: {user.food:,})\n"
            f"• ⛓️ Temir: 2,000 (sizda: {user.iron:,})"
        )

    user.gold -= 3000
    user.food -= 4000
    user.iron -= 2000
    dragon.has_laid_egg = True

    new_name = f"{dragon.name} Nasli"
    new_egg = models.Dragon(
        user_id=user.id,
        name=new_name,
        grade=dragon.grade,
        stage="egg",
        level=1,
        hunger=60,
        power=100,
        last_fed=datetime.utcnow(),
    )
    session.add(new_egg)
    user.prestige += 200
    user.xp += 600
    await session.commit()
    return True, f"🥚 AJOYIB MO'JIZA! {dragon.name} yangi ajdar tuxumini qo'ydi! Endi sizda 2 ta ajdar bo'ladi! (+200 Prestige)"


async def equip_dragon_artifact(session: AsyncSession, user_id: int, dragon_id: int, artifact_code: str) -> Tuple[bool, str]:
    """Ajdarga maxsus artefakt sotib olib taqish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    dragon = await session.get(models.Dragon, dragon_id)
    if not dragon or dragon.user_id != user.id:
        return False, "Ajdar topilmadi."

    from data.artifacts_data import ARTIFACTS_DATA
    if artifact_code not in ARTIFACTS_DATA:
        return False, "Artefakt topilmadi."

    art_info = ARTIFACTS_DATA[artifact_code]
    p_gold = art_info.get("price_gold", 6000)
    p_iron = art_info.get("price_iron", 3000)

    if user.gold < p_gold or user.iron < p_iron:
        return False, f"❌ {art_info['name']} uchun {p_gold:,}🪙 oltin va {p_iron:,}⛓️ temir kerak! (Sizda: {user.gold:,}🪙, {user.iron:,}⛓️)"

    user.gold -= p_gold
    user.iron -= p_iron
    dragon.artifact_code = artifact_code
    pwr_bonus = int(dragon.power * art_info.get("dragon_bonus", 0.35))
    dragon.power += pwr_bonus
    user.prestige += 120

    await session.commit()
    return True, f"✨ {dragon.name} ga {art_info['name']} taqildi! Ajdarning quvvati +{pwr_bonus} ga oshdi! (+120 Prestige)"


async def collect_castle_tax(session: AsyncSession, user_id: int, territory_id: int) -> Tuple[bool, str, Dict[str, int]]:
    """Qal'adan 4 soatlik to'plangan o'lponni yig'ib olish"""
    user = await get_user_any(session, user_id)
    terr = await session.get(models.Territory, territory_id)
    if not user or not terr:
        return False, "Ma'lumot topilmadi.", {}

    if not user.house_id or terr.owner_house_id != user.house_id:
        return False, "Bu qal'a sizning xonadoningizga tegishli emas!", {}

    now = datetime.utcnow()
    last_tax = terr.last_tax_collected_at or (now - timedelta(hours=4))
    elapsed_seconds = max(0, (now - last_tax).total_seconds())
    hours = int(elapsed_seconds // 3600)
    if hours < 1:
        remaining_mins = max(1, int((3600 - elapsed_seconds) // 60))
        return False, f"⏳ O'lpon yig'ishga hali erta! Kamida 1 soat o'tishi kerak ({remaining_mins} daqiqa qoldi).", {}

    hours = min(4, hours)  # Ko'pi bilan 4 soatlik jamlanadi
    g_inc = terr.gold_income * hours
    f_inc = terr.food_income * hours
    i_inc = terr.iron_income * hours

    user.gold += g_inc
    user.food += f_inc
    user.iron += i_inc
    terr.last_tax_collected_at = now
    await session.commit()

    return True, (
        f"💰 **{terr.name.upper()} QAL'ASIDAN O'LPON OLINDI!**\n\n"
        f"⏱️ To'plangan vaqt: **{hours} soatlik** o'lpon\n"
        f"• 🪙 Oltin: **+{g_inc:,}**\n"
        f"• 🌾 Oziq-ovqat: **+{f_inc:,}**\n"
        f"• ⛓️ Temir: **+{i_inc:,}**\n\n"
        f"Resurslar sizning shaxsiy xazinangizga qo'shildi!"
    ), {"gold": g_inc, "food": f_inc, "iron": i_inc, "hours": hours}


# ============================================================
# ARTIFACTS CRUD
# ============================================================

async def get_user_artifacts(session: AsyncSession, user_id: int) -> List[models.Artifact]:
    """Foydalanuvchining artefaktlari ro'yxati"""
    res = await session.execute(
        select(models.Artifact).where(models.Artifact.user_id == user_id)
    )
    return res.scalars().all()


async def get_equipped_artifact(session: AsyncSession, user_id: int) -> Optional[models.Artifact]:
    """Hozir taqilgan artefakt"""
    res = await session.execute(
        select(models.Artifact).where(models.Artifact.user_id == user_id, models.Artifact.is_equipped == True)
    )
    return res.scalar_one_or_none()


async def equip_artifact(session: AsyncSession, user_id: int, artifact_id: int) -> Tuple[bool, str]:
    """Artefaktni taqish"""
    arts = await get_user_artifacts(session, user_id)
    target_art = None
    for a in arts:
        if a.id == artifact_id:
            target_art = a
        a.is_equipped = False

    if not target_art:
        return False, "Artefakt topilmadi."

    target_art.is_equipped = True
    user = await get_user_any(session, user_id)
    if user:
        user.equipped_artifact_id = target_art.id
    await session.commit()
    return True, f"⚔️ {target_art.name} muvaffaqiyatli taqildi!"


async def buy_artifact(session: AsyncSession, user_id: int, code: str) -> Tuple[bool, str]:
    """Artefaktni xarid qilish"""
    from data.artifacts_data import ARTIFACTS_DATA
    if code not in ARTIFACTS_DATA:
        return False, "Noto'g'ri artefakt."

    art_info = ARTIFACTS_DATA[code]
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    existing = await session.execute(
        select(models.Artifact).where(models.Artifact.user_id == user_id, models.Artifact.code == code)
    )
    if existing.scalar_one_or_none():
        return False, "Sizda ushbu afsonaviy artefakt allaqachon mavjud!"

    if user.gold < art_info["price_gold"] or user.iron < art_info["price_iron"]:
        return False, f"Yetarli resurs yo'q! Kerak: {art_info['price_gold']:,}🪙 oltin, {art_info['price_iron']:,}⛓️ temir."

    user.gold -= art_info["price_gold"]
    user.iron -= art_info["price_iron"]

    new_art = models.Artifact(
        user_id=user.id,
        code=code,
        name=art_info["name"],
        type=art_info["type"],
        is_equipped=True,
    )
    # Boshqa artefaktlarni yechish
    other_arts = await get_user_artifacts(session, user_id)
    for a in other_arts:
        a.is_equipped = False

    session.add(new_art)
    user.equipped_artifact_id = new_art.id
    user.prestige += 100
    user.xp += 300
    await session.commit()
    return True, f"🏆 TABRIKLAYMIZ! Siz {art_info['name']} sohibigalandingiz! (+100 Prestige)"


# ============================================================
# NIGHT KING RAID CONTRIBUTION CRUD
# ============================================================

async def record_night_king_damage(session: AsyncSession, user_id: int, damage: int) -> models.NightKingContribution:
    """Tun Qiroliga yetkazilgan ziyonni hisoblash"""
    res = await session.execute(
        select(models.NightKingContribution).where(models.NightKingContribution.user_id == user_id)
    )
    contrib = res.scalar_one_or_none()
    if not contrib:
        contrib = models.NightKingContribution(
            user_id=user_id,
            damage_dealt=damage,
            attacks_count=1,
            last_attack=datetime.utcnow(),
        )
        session.add(contrib)
    else:
        contrib.damage_dealt += damage
        contrib.attacks_count += 1
        contrib.last_attack = datetime.utcnow()
    await session.commit()
    return contrib


async def get_night_king_leaderboard(session: AsyncSession, limit: int = 10) -> List[Tuple[str, str, int, int]]:
    """Tun Qiroliga eng ko'p ziyon yetkazgan o'yinchilar ro'yxati"""
    res = await session.execute(
        select(models.NightKingContribution)
        .order_by(models.NightKingContribution.damage_dealt.desc())
        .limit(limit)
    )
    contribs = res.scalars().all()
    results = []
    for c in contribs:
        u = await get_user_any(session, c.user_id)
        if u:
            char_res = await session.execute(select(models.Character.name).where(models.Character.user_id == u.id))
            char_name = char_res.scalar_one_or_none() or u.full_name
            h = await session.get(models.House, u.house_id) if u.house_id else None
            h_name = f"{h.emoji} {h.name}" if h else "Vesteros"
            results.append((char_name, h_name, c.damage_dealt, c.attacks_count))
    return results


async def award_night_king_victory(session: AsyncSession, bot_app=None) -> Dict[str, Any]:
    """Tun Qiroli yengilganda Top 1 o'yinchiga 'Shimol Najotkori' unvoni va +500 Prestige berish"""
    res = await session.execute(
        select(models.NightKingContribution)
        .order_by(models.NightKingContribution.damage_dealt.desc())
        .limit(10)
    )
    contribs = res.scalars().all()
    if not contribs:
        return {"awarded": False, "reason": "No contributions found"}

    top1 = contribs[0]
    winner = await get_user_any(session, top1.user_id)
    if not winner:
        return {"awarded": False, "reason": "Winner not found"}

    # Top 1 ga "Shimol Najotkori" unvoni, +500 Prestige, +3000 Gold
    winner.title = "Shimol Najotkori"
    winner.prestige = (winner.prestige or 0) + 500
    winner.gold = (winner.gold or 0) + 3000
    winner.xp = (winner.xp or 0) + 1000

    # Top 2 va Top 3 ga ham sovrinlar
    if len(contribs) > 1:
        top2_user = await get_user_any(session, contribs[1].user_id)
        if top2_user:
            top2_user.prestige = (top2_user.prestige or 0) + 300
            top2_user.gold = (top2_user.gold or 0) + 1800

    if len(contribs) > 2:
        top3_user = await get_user_any(session, contribs[2].user_id)
        if top3_user:
            top3_user.prestige = (top3_user.prestige or 0) + 200
            top3_user.gold = (top3_user.gold or 0) + 1000

    await session.commit()

    winner_name = winner.full_name or winner.username or f"Lord {winner.id}"
    # Winner ga shaxsiy tabrik xabari
    if bot_app and winner.telegram_id:
        try:
            win_msg = (
                f"❄️👑 **TABRIKLAYMIZ, VESTEROS XALOSKORI!**\n\n"
                f"Siz Tun Qiroli va Oq Yuruvchilar armiyasiga eng katta zarba (**{top1.damage_dealt:,}** ziyon) yetkazdingiz va reyd g'olibi bo'ldingiz!\n\n"
                f"🎖️ **MUKOFOTLARINGIZ:**\n"
                f"• 👑 Faxriy Unvon: **Shimol Najotkori**\n"
                f"• 🏆 Nufuz: **+500 Prestige**\n"
                f"• 🪙 Xazina: **+3,000 Oltin**\n"
                f"• ⭐ Tajriba: **+1,000 XP**\n\n"
                f"Bu unvon endi sizning profilingiz va butun Vesteros reytingida mangu aks etadi!"
            )
            await bot_app.bot.send_message(chat_id=winner.telegram_id, text=win_msg, parse_mode="Markdown")
        except Exception:
            pass

    return {
        "awarded": True,
        "winner_id": winner.id,
        "winner_name": winner_name,
        "damage": top1.damage_dealt,
    }


async def set_user_title(session: AsyncSession, user_id: int, title: Optional[str]) -> bool:
    """O'yinchiga maxsus faxriy unvon biriktirish yoki olib tashlash"""
    user = await get_user_any(session, user_id)
    if not user:
        return False
    user.title = title.strip() if title else None
    await session.commit()
    return True


# ============================================================
# DUEL CRUD
# ============================================================

async def fight_ai_champion(
    session: AsyncSession,
    user_id: int,
    champion_name: str,
    bet_gold: int,
    player_tactic: str,
) -> Dict[str, Any]:
    """AI chempioni bilan 1v1 duel"""
    user = await get_user_any(session, user_id)
    if not user:
        return {"success": False, "error": "Foydalanuvchi topilmadi."}

    if bet_gold > 0 and user.gold < bet_gold:
        return {"success": False, "error": f"Duel uchun kamida {bet_gold}🪙 oltin kerak!"}

    await check_and_reset_daily_limits(session, user)
    duel_cnt = getattr(user, "daily_duel_count", 0) or 0
    if duel_cnt >= 10:
        return {"success": False, "error": "❌ Bugungi 10 ta duel limitingiz tugagan! Ertaga yana maydonga tushishingiz mumkin."}

    user.daily_duel_count = duel_cnt + 1

    # Qahramon ko'rsatkichlari
    char_res = await session.execute(select(models.Character).where(models.Character.user_id == user.id))
    hero = char_res.scalars().first()
    hero_name = hero.name if hero else "Lord"
    hero_atk = hero.attack if hero else 50
    hero_def = hero.defense if hero else 50

    # Daraja (level) o'sishi bilan qahramonning jismoniy kuchi oshishi (+4 Atk, +4 Def har bir darajaga)
    hero_lvl = user.level or 1
    eff_atk = hero_atk + (hero_lvl * 4)
    eff_def = hero_def + (hero_lvl * 4)

    # Chempion statistikasi (adolatli darajalar bo'yicha)
    champions = {
        "Bronn": {"atk": 50, "def": 45, "tactic": "parry"},
        "Sandor Clegane": {"atk": 65, "def": 60, "tactic": "heavy"},
        "Brienne of Tarth": {"atk": 70, "def": 75, "tactic": "parry"},
        "Oberyn Martell": {"atk": 78, "def": 68, "tactic": "agile"},
        "Jaime Lannister": {"atk": 82, "def": 72, "tactic": "agile"},
        "Barristan Selmy": {"atk": 85, "def": 78, "tactic": "parry"},
        "Daemon Targaryen": {"atk": 88, "def": 75, "tactic": "agile"},
        "Gregor Clegane": {"atk": 92, "def": 82, "tactic": "heavy"},
        "Arthur Dayne": {"atk": 95, "def": 85, "tactic": "heavy"},
    }
    champ = champions.get(champion_name, {"atk": 60, "def": 55, "tactic": "agile"})
    champ_tactic = champ["tactic"]

    # Taktika ustunligi: heavy > agile > parry > heavy
    tactics_win = {"heavy": "agile", "agile": "parry", "parry": "heavy"}
    tactic_bonus = 1.0
    if tactics_win.get(player_tactic) == champ_tactic:
        tactic_bonus = 1.45  # To'g'ri taktika uchun +45% kuchli ustunlik
    elif tactics_win.get(champ_tactic) == player_tactic:
        tactic_bonus = 0.80

    art_bonus = 0.0
    equipped = await get_equipped_artifact(session, user.id)
    if equipped:
        from data.artifacts_data import ARTIFACTS_DATA
        art_bonus = ARTIFACTS_DATA.get(equipped.code, {}).get("duel_bonus", 0.0)

    player_score = (eff_atk * 1.2 + eff_def * 0.8) * tactic_bonus * (1.0 + art_bonus) * random.uniform(0.90, 1.25)
    champ_score = (champ["atk"] * 1.2 + champ["def"] * 0.8) * random.uniform(0.85, 1.15)

    won = player_score >= champ_score
    if won:
        user.gold += 500
        user.prestige += 3
        user.xp += 15
        outcome = (
            f"🏆 **G'ALABA!** Sizning qilich zarbangiz {champion_name}ning mudofaasini teshib o'tdi!\n"
            f"🎁 Mukofot: **+500🪙 Oltin, +3 Prestige, +15 XP** ({user.daily_duel_count}/10)"
        )
    else:
        if bet_gold > 0:
            user.gold = max(0, user.gold - bet_gold)
            outcome = f"💀 **MAG'LUBIYAT!** {champion_name} chaqqonlik bilan ustun keldi. (-{bet_gold}🪙 Garov yo'qotildi)"
        else:
            outcome = f"💀 **MAG'LUBIYAT!** Mashg'ulot jangida {champion_name} tajribasi ustun keldi."
        user.xp += 5

    from core.leveling import check_user_level_up
    check_user_level_up(user)

    await session.commit()
    return {
        "success": True,
        "won": won,
        "hero_name": hero_name,
        "champion_name": champion_name,
        "bet_gold": bet_gold,
        "outcome": outcome,
        "player_tactic": player_tactic,
        "champ_tactic": champ_tactic,
        "daily_duels": user.daily_duel_count,
        "reward_gold": 500 if won else 0,
        "reward_prestige": 3 if won else 0,
        "reward_xp": 15 if won else 5,
    }


async def create_pvp_duel(
    session: AsyncSession,
    challenger_tg_or_id: int,
    opponent_target: str,
    bet_gold: int,
    tactic: str,
) -> Tuple[bool, str, Optional[models.Duel], Optional[int]]:
    """O'yinchi boshqa o'yinchiga duel taklif qiladi"""
    challenger = await get_user_any(session, challenger_tg_or_id)
    if not challenger:
        return False, "Foydalanuvchi topilmadi.", None, None

    if bet_gold > 0 and challenger.gold < bet_gold:
        return False, f"Duel uchun sizda kamida {bet_gold}🪙 oltin bo'lishi kerak!", None, None

    opponent = None
    if opponent_target.isdigit():
        target_int = int(opponent_target)
        opponent = await get_user_any(session, target_int)
    else:
        clean_user = opponent_target.lstrip("@").lower()
        res = await session.execute(select(models.User).where(func.lower(models.User.username) == clean_user))
        opponent = res.scalar_one_or_none()

    if not opponent:
        return False, f"'{opponent_target}' nomli lord topilmadi!", None, None

    if opponent.id == challenger.id:
        return False, "O'zingizga qarshi duel e'lon qila olmaysiz!", None, None

    if bet_gold > 0 and opponent.gold < bet_gold:
        return False, f"{opponent.full_name} da garov uchun yetarli oltin ({bet_gold}🪙) yo'q!", None, None

    duel = models.Duel(
        challenger_id=challenger.id,
        opponent_id=opponent.id,
        bet_gold=bet_gold,
        challenger_tactic=tactic,
        status="pending",
    )
    session.add(duel)
    await session.commit()
    return True, f"⚔️ {opponent.full_name}ga duel chaqirig'i yuborildi!", duel, opponent.telegram_id


async def get_pending_duels_for_user(session: AsyncSession, user_tg_or_id: int) -> List[Tuple[models.Duel, str]]:
    """Foydalanuvchiga kelgan kutilayotgan duel takliflari"""
    user = await get_user_any(session, user_tg_or_id)
    if not user:
        return []

    res = await session.execute(
        select(models.Duel, models.User.full_name)
        .join(models.User, models.User.id == models.Duel.challenger_id)
        .where(models.Duel.opponent_id == user.id, models.Duel.status == "pending")
        .order_by(desc(models.Duel.created_at))
    )
    return list(res.all())


async def resolve_pvp_duel(
    session: AsyncSession,
    duel_id: int,
    opponent_tg_or_id: int,
    opponent_tactic: str,
) -> Dict[str, Any]:
    """PvP duelini hisoblash va yakunlash"""
    duel = await session.get(models.Duel, duel_id)
    if not duel or duel.status != "pending":
        return {"success": False, "error": "Duel topilmadi yoki allaqachon yakunlangan."}

    challenger = await get_user_any(session, duel.challenger_id)
    opponent = await get_user_any(session, duel.opponent_id)
    if not challenger or not opponent:
        return {"success": False, "error": "Jang ishtirokchilaridan biri topilmadi."}

    bet_gold = duel.bet_gold
    if bet_gold > 0:
        if challenger.gold < bet_gold:
            duel.status = "cancelled"
            await session.commit()
            return {"success": False, "error": f"{challenger.full_name}da garov uchun yetarli oltin qolmagan!"}
        if opponent.gold < bet_gold:
            duel.status = "cancelled"
            await session.commit()
            return {"success": False, "error": f"{opponent.full_name}da garov uchun yetarli oltin qolmagan!"}

    c_char_res = await session.execute(select(models.Character).where(models.Character.user_id == challenger.id))
    c_hero = c_char_res.scalars().first()
    c_atk = c_hero.attack if c_hero else 50
    c_def = c_hero.defense if c_hero else 50
    c_name = c_hero.name if c_hero else challenger.full_name

    o_char_res = await session.execute(select(models.Character).where(models.Character.user_id == opponent.id))
    o_hero = o_char_res.scalars().first()
    o_atk = o_hero.attack if o_hero else 50
    o_def = o_hero.defense if o_hero else 50
    o_name = o_hero.name if o_hero else opponent.full_name

    tactics_win = {"heavy": "agile", "agile": "parry", "parry": "heavy"}
    c_bonus = 1.0
    o_bonus = 1.0
    if tactics_win.get(duel.challenger_tactic) == opponent_tactic:
        c_bonus = 1.35
    elif tactics_win.get(opponent_tactic) == duel.challenger_tactic:
        o_bonus = 1.35

    c_art_bonus = 0.0
    c_equipped = await get_equipped_artifact(session, challenger.id)
    if c_equipped:
        from data.artifacts_data import ARTIFACTS_DATA
        c_art_bonus = ARTIFACTS_DATA.get(c_equipped.code, {}).get("duel_bonus", 0.0)

    o_art_bonus = 0.0
    o_equipped = await get_equipped_artifact(session, opponent.id)
    if o_equipped:
        from data.artifacts_data import ARTIFACTS_DATA
        o_art_bonus = ARTIFACTS_DATA.get(o_equipped.code, {}).get("duel_bonus", 0.0)

    c_score = (c_atk * 1.2 + c_def * 0.8) * c_bonus * (1.0 + c_art_bonus) * random.uniform(0.85, 1.25)
    o_score = (o_atk * 1.2 + o_def * 0.8) * o_bonus * (1.0 + o_art_bonus) * random.uniform(0.85, 1.25)

    challenger_won = c_score >= o_score
    duel.opponent_tactic = opponent_tactic
    duel.status = "completed"

    if challenger_won:
        winner = challenger
        loser = opponent
        winner_name = c_name
        loser_name = o_name
        duel.winner_id = challenger.id
    else:
        winner = opponent
        loser = challenger
        winner_name = o_name
        loser_name = c_name
        duel.winner_id = opponent.id

    if bet_gold > 0:
        loser.gold = max(0, loser.gold - bet_gold)
        winner.gold += bet_gold
    else:
        winner.gold += 50

    winner.prestige += 35
    winner.xp += 150
    loser.prestige = max(0, loser.prestige - 5)
    loser.xp += 50

    from core.leveling import check_user_level_up
    check_user_level_up(winner)
    check_user_level_up(loser)

    tactic_names = {"heavy": "🗡️ Og'ir Zarba", "parry": "🛡️ Qalqonli Mudofaa", "agile": "⚡ Epchil Hamla"}
    outcome = (
        f"⚔️ **LORDLARARO QONLI DUEL YAKUNLANDI!**\n\n"
        f"🏆 G'olib: **{winner.full_name}** ({winner_name}) — {tactic_names.get(duel.challenger_tactic if challenger_won else opponent_tactic)}\n"
        f"💀 Mag'lub: **{loser.full_name}** ({loser_name}) — {tactic_names.get(opponent_tactic if challenger_won else duel.challenger_tactic)}\n\n"
        f"📊 **MUKOFOTLAR:**\n"
        f"• G'olib ({winner.full_name}): +{bet_gold if bet_gold > 0 else 50}🪙 oltin, +35🏆 Prestige, +150 XP\n"
        f"• Mag'lub ({loser.full_name}): -{bet_gold if bet_gold > 0 else 0}🪙 oltin, +50 XP"
    )
    duel.details = outcome
    await session.commit()

    return {
        "success": True,
        "challenger_won": challenger_won,
        "winner_tg_id": winner.telegram_id,
        "loser_tg_id": loser.telegram_id,
        "challenger_tg_id": challenger.telegram_id,
        "opponent_tg_id": opponent.telegram_id,
        "outcome": outcome,
    }


async def reject_pvp_duel(session: AsyncSession, duel_id: int, user_tg_or_id: int) -> Tuple[bool, str, Optional[int]]:
    """Duelni rad etish"""
    duel = await session.get(models.Duel, duel_id)
    if not duel or duel.status != "pending":
        return False, "Duel topilmadi yoki muddati o'tgan.", None

    challenger = await get_user_any(session, duel.challenger_id)
    duel.status = "rejected"
    await session.commit()
    return True, "Duel chaqirig'i rad etildi.", challenger.telegram_id if challenger else None


# ============================================================
# RAVEN MAIL CRUD
# ============================================================

MAX_DAILY_RAVEN_GOLD = 5000


async def get_daily_raven_gold_sent(session: AsyncSession, user_id: int) -> int:
    """Foydalanuvchining bugun qarg'alar orqali yuborgan jami oltini"""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    res = await session.execute(
        select(func.sum(models.RavenMessage.gold_attached)).where(
            models.RavenMessage.sender_id == user_id,
            models.RavenMessage.created_at >= today_start,
        )
    )
    return res.scalar() or 0


async def send_raven(
    session: AsyncSession,
    sender_id: int,
    recipient_username_or_id: str,
    text: str,
    gold: int = 0,
) -> Tuple[bool, str, Optional[int]]:
    """Qarg'a orqali xat va oltin jo'natish (kunlik max 5,000 oltin limiti bilan)"""
    sender = await get_user_any(session, sender_id)
    if not sender:
        return False, "Foydalanuvchi topilmadi.", None

    if gold < 0:
        return False, "Oltin miqdori musbat bo'lishi kerak!", None

    if gold > 0:
        if sender.gold < gold:
            return False, "Xatga biriktirish uchun yetarli oltiningiz yo'q!", None

        already_sent = await get_daily_raven_gold_sent(session, sender.id)
        if already_sent + gold > MAX_DAILY_RAVEN_GOLD:
            remaining = max(0, MAX_DAILY_RAVEN_GOLD - already_sent)
            return (
                False,
                f"❌ Kunlik qarg'a orqali oltin jo'natish limiti: {MAX_DAILY_RAVEN_GOLD:,}🪙 oltin!\n"
                f"Bugun jo'natilgan: {already_sent:,}🪙\n"
                f"Siz yana ko'pi bilan {remaining:,}🪙 yuborishingiz mumkin.",
                None,
            )

    # Qabul qiluvchini qidirish
    recipient = None
    if recipient_username_or_id.isdigit():
        recipient = await get_user_any(session, int(recipient_username_or_id))
        if not recipient:
            recipient = await get_user_by_telegram_id(session, int(recipient_username_or_id))
    else:
        clean_user = recipient_username_or_id.lstrip("@").lower()
        res = await session.execute(select(models.User).where(func.lower(models.User.username) == clean_user))
        recipient = res.scalar_one_or_none()

    if not recipient:
        return False, "Qabul qiluvchi lord topilmadi!", None

    if recipient.id == sender.id:
        return False, "O'zingizga qarg'a xabari yubora olmaysiz!", None

    if gold > 0:
        sender.gold -= gold
        recipient.gold += gold

    msg = models.RavenMessage(
        sender_id=sender.id,
        recipient_id=recipient.id,
        message_text=text,
        gold_attached=gold,
        is_read=False,
    )
    session.add(msg)
    await session.commit()
    return True, f"🐦 Qarg'a parvoz qildi! Xabar {recipient.full_name}ga yetkazildi.", recipient.telegram_id


async def get_inbox_ravens(session: AsyncSession, user_id: int, limit: int = 5) -> List[Tuple[models.RavenMessage, str]]:
    """Foydalanuvchining so'nggi xabarlari"""
    res = await session.execute(
        select(models.RavenMessage, models.User.full_name)
        .join(models.User, models.User.id == models.RavenMessage.sender_id)
        .where(models.RavenMessage.recipient_id == user_id)
        .order_by(desc(models.RavenMessage.created_at))
        .limit(limit)
    )
    return list(res.all())


# ============================================================
# DAILY BONUS & REFERRAL CRUD
# ============================================================
# 7-DAY DAILY STREAK RETENTION SYSTEM
# ============================================================

STREAK_REWARDS = {
    1: {
        "title": "1-Kun: Boshlang'ich Safarbarlik",
        "gold": 500, "food": 1000, "iron": 200, "prestige": 25, "xp": 50,
        "troops": {},
        "extra_desc": ""
    },
    2: {
        "title": "2-Kun: Xonadon Zaxirasi",
        "gold": 750, "food": 1500, "iron": 350, "prestige": 35, "xp": 75,
        "troops": {},
        "extra_desc": ""
    },
    3: {
        "title": "3-Kun: Qalqonbardorlar Kelishi",
        "gold": 1000, "food": 2000, "iron": 500, "prestige": 50, "xp": 100,
        "troops": {"infantry": 25},
        "extra_desc": "🛡️ +25 ta Piyoda saflaringizga qo'shildi!"
    },
    4: {
        "title": "4-Kun: Mohir Merganlar",
        "gold": 1500, "food": 2500, "iron": 700, "prestige": 70, "xp": 150,
        "troops": {"archers": 15},
        "extra_desc": "🏹 +15 ta Kamonchi armiyangizga qo'shildi!"
    },
    5: {
        "title": "5-Kun: Ritsarlar Hamlasi",
        "gold": 2000, "food": 3000, "iron": 900, "prestige": 90, "xp": 200,
        "troops": {"cavalry": 10},
        "extra_desc": "🐎 +10 ta Og'ir Otliq bayrog'ingiz ostida!"
    },
    6: {
        "title": "6-Kun: Nayzadorlar Qal'asi",
        "gold": 2500, "food": 4000, "iron": 1200, "prestige": 120, "xp": 250,
        "troops": {"spearmen": 10},
        "extra_desc": "🗡️ +10 ta Safarbar Nayzachi armiyangizda!"
    },
    7: {
        "title": "7-Kun: 👑 SUPER VALIRIYA TUHFASI",
        "gold": 4000, "food": 6000, "iron": 2000, "prestige": 200, "xp": 400,
        "troops": {"special_troops": 15},
        "dragon_power": 50,
        "extra_desc": "🔥 +15 ta Maxsus Gvardiya va Ajdaringizga +50 Quvvat (Ozuqa)!"
    },
}


def format_streak_calendar(current_streak: int, claimed_today: bool) -> str:
    """7 kunlik kirish taqvimini chiroyli vizual ko'rinishda shakllantirish"""
    lines = []
    for day in range(1, 8):
        info = STREAK_REWARDS[day]
        if day < current_streak or (day == current_streak and claimed_today):
            status = "✅ [Olingan]"
        elif day == current_streak and not claimed_today:
            status = "🎁 [Bugun oling!]"
        elif claimed_today and day == ((current_streak % 7) + 1):
            status = "⏳ [Ertaga]"
        else:
            status = "🔒 [Kutilmoqda]"

        bonus_summary = f"{info['gold']}🪙 {info['food']}🌾 {info['iron']}⛓️"
        if info.get("troops"):
            t_name = list(info["troops"].keys())[0]
            t_cnt = list(info["troops"].values())[0]
            bonus_summary += f" +{t_cnt} askar"
        if info.get("dragon_power"):
            bonus_summary += " +🔥Ajdar ozuqasi"

        lines.append(f"• **{day}-kun:** {status} — _{bonus_summary}_")
    return "\n".join(lines)


async def claim_daily_bonus(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """7 kunlik uzluksiz kirish (Streak) tizimi"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    now = datetime.utcnow()
    today_str = now.strftime("%Y-%m-%d")
    today_date = now.date()

    # 1. Bugun allaqachon olinganmi?
    if user.last_streak_date == today_str:
        remaining_hours = 23 - now.hour
        remaining_mins = 59 - now.minute
        cal = format_streak_calendar(user.streak_count or 1, claimed_today=True)
        msg = (
            f"⏳ **BUGUNGI TUHFA ALLAQACHON QABUL QILINGAN!**\n\n"
            f"🔥 Sizning ketma-ket kirish ko'rsatkichingiz: **{user.streak_count}-kun**\n"
            f"Yangi sovg'a {remaining_hours} soat {remaining_mins} daqiqadan so'ng (ertaga) ochiladi.\n\n"
            f"📅 **7 KUNLIK TUHFALAR TAQVIMI:**\n{cal}\n\n"
            f"💡 _Har kuni botga kiring va 7-kunda Katta Ajdar Tuhfasini qo'lga kiriting!_"
        )
        return False, msg

    # 2. Yangi streak hisoblash
    streak_reset = False
    if user.last_streak_date:
        try:
            last_date = datetime.strptime(user.last_streak_date, "%Y-%m-%d").date()
            diff_days = (today_date - last_date).days
            if diff_days == 1:
                # Uzluksiz davom etmoqda
                new_streak = (user.streak_count or 0) + 1
                if new_streak > 7:
                    new_streak = 1  # 7-kundan so'ng yangi davr boshlanadi
            else:
                # Orada kun o'tkazib yuborilgan - qayta boshlanadi
                new_streak = 1
                streak_reset = True
        except Exception:
            new_streak = 1
    else:
        new_streak = 1

    reward = STREAK_REWARDS.get(new_streak, STREAK_REWARDS[1])

    # 3. Resurslar va sovrinlarni taqsimlash
    user.streak_count = new_streak
    user.last_streak_date = today_str
    user.last_daily_bonus = now

    user.gold = (user.gold or 0) + reward["gold"]
    user.food = (user.food or 0) + reward["food"]
    user.iron = (user.iron or 0) + reward["iron"]
    user.prestige = (user.prestige or 0) + reward["prestige"]
    user.xp = (user.xp or 0) + reward["xp"]

    # Askarlarni qo'shish
    troops_msg = ""
    if reward.get("troops"):
        army = await get_user_army(session, user.id)
        if army:
            for t_type, count in reward["troops"].items():
                if hasattr(army, t_type):
                    setattr(army, t_type, (getattr(army, t_type) or 0) + count)
            troops_msg = f"\n{reward.get('extra_desc', '')}"

    # Ajdar quvvati
    dragon_msg = ""
    if reward.get("dragon_power"):
        dragons = await get_user_dragons(session, user.id)
        if dragons:
            best_dragon = max(dragons, key=lambda d: d.power)
            best_dragon.power += reward["dragon_power"]
            best_dragon.hunger = min(100, (best_dragon.hunger or 50) + 40)
            dragon_msg = f"\n🐉 Ajdaringiz ({best_dragon.name}) to'yintirildi: +{reward['dragon_power']} quvvat!"

    # Level up tekshirish
    from core.leveling import check_user_level_up
    lvl_up, new_lvl, lvl_msg = check_user_level_up(user)
    extra_lvl = f"\n\n{lvl_msg}" if lvl_up else ""

    await session.commit()

    cal = format_streak_calendar(new_streak, claimed_today=True)

    reset_note = "⚠️ _Kechagi kun o'tkazib yuborilgani sababli streak 1-kundan qayta boshlandi._\n\n" if streak_reset else ""

    success_msg = (
        f"🎁 **KUNLIK QIROL TUHFASI QABUL QILINDI!**\n\n"
        f"{reset_note}"
        f"🔥 **{reward['title']}** (Streak: {new_streak}/7)\n\n"
        f"• 🪙 Oltin: **+{reward['gold']:,}**\n"
        f"• 🌾 Oziq-ovqat: **+{reward['food']:,}**\n"
        f"• ⛓️ Temir: **+{reward['iron']:,}**\n"
        f"• 🏆 Nufuz: **+{reward['prestige']:,}**\n"
        f"• ⭐ Tajriba: **+{reward['xp']:,} XP**"
        f"{troops_msg}"
        f"{dragon_msg}"
        f"{extra_lvl}\n\n"
        f"📅 **7 KUNLIK TAQVIM:**\n{cal}\n\n"
        f"💡 _Ertaga kirib navbatdagi sovg'ani olishni unutmang!_"
    )
    return True, success_msg


async def set_house_group_chat(session: AsyncSession, house_id: int, chat_id: int, chat_title: str) -> bool:
    """Xonadon rasmiy Telegram guruhini biriktirish"""
    house = await session.get(models.House, house_id)
    if not house:
        return False
    house.group_chat_id = chat_id
    house.group_title = chat_title
    await session.commit()
    return True


async def get_house_by_group_chat_id(session: AsyncSession, chat_id: int) -> Optional[models.House]:
    """Guruh chat ID si bo'yicha xonadonni topish"""
    res = await session.execute(select(models.House).where(models.House.group_chat_id == chat_id))
    return res.scalar_one_or_none()

# RESOURCE MARKET (IRON & FOOD) CRUD
# ============================================================

IRON_MARKET_PACKS = {
    "pack_1": {"gold": 500, "iron": 300, "title": "📦 Kichik Savdo Qopi (300 temir)"},
    "pack_2": {"gold": 1000, "iron": 700, "title": "🐎 Savdo Karvoni (700 temir, +100 bonus)"},
    "pack_3": {"gold": 2500, "iron": 1900, "title": "🚢 Dengiz Savdo Kemasi (1,900 temir, +400 bonus)"},
    "pack_4": {"gold": 5000, "iron": 4200, "title": "👑 Qirollik Savdo Floti (4,200 temir, +1,200 bonus)"},
}

FOOD_MARKET_PACKS = {
    "food_1": {"gold": 300, "food": 390, "title": "🌾 Kichik Don Qopi (390 oziq)"},
    "food_2": {"gold": 500, "food": 700, "title": "🌾 Savdo Karvoni (700 oziq, +50 bonus)"},
    "food_3": {"gold": 1000, "food": 1500, "title": "🌾 Don Ombri Zaxirasi (1,500 oziq, +200 bonus)"},
    "food_4": {"gold": 2500, "food": 4000, "title": "🌾 Savdo Kemasi (4,000 oziq, +750 bonus)"},
    "food_5": {"gold": 5000, "food": 9000, "title": "🌾 Qirollik Zaxirasi (9,000 oziq, +2,500 bonus)"},
}


async def upgrade_iron_mine(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Temir konini keyingi darajaga ko'tarish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    current_lvl = getattr(user, "iron_mine_level", 1) or 1
    if current_lvl >= 10:
        return False, "❌ Temir koningiz maksimal 10-darajaga yetgan! Tog'ning eng chuqur qatlamlarigacha qazilgan."

    next_lvl = current_lvl + 1
    gold_cost = current_lvl * 1500
    food_cost = current_lvl * 800

    if user.gold < gold_cost or user.food < food_cost:
        return False, f"❌ Konni kuchaytirish uchun {gold_cost:,}🪙 oltin va {food_cost:,}🌾 oziq-ovqat kerak! (Sizda: {user.gold:,}🪙 / {user.food:,}🌾)"

    user.gold -= gold_cost
    user.food -= food_cost
    user.iron_mine_level = next_lvl
    user.prestige += next_lvl * 10
    user.xp += next_lvl * 50

    from core.leveling import check_user_level_up
    check_user_level_up(user)

    await session.commit()
    return True, f"🎉 TABRIKLAYMIZ! Temir koni {next_lvl}-darajaga ko'tarildi! (+{next_lvl*50}⛓️ temir/soat ishlab chiqariladi)"


async def buy_iron_with_gold(session: AsyncSession, user_id: int, pack_code: str) -> Tuple[bool, str]:
    """Bozordan oltin evaziga tayyor temir xarid qilish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    pack = IRON_MARKET_PACKS.get(pack_code)
    if not pack:
        return False, "Noto'g'ri tovar tanlandi."

    if user.gold < pack["gold"]:
        return False, f"❌ Xarid uchun yetarli oltin yo'q! Kerak: {pack['gold']:,}🪙 (Sizda: {user.gold:,}🪙)"

    user.gold -= pack["gold"]
    user.iron += pack["iron"]
    await session.commit()
    return True, f"✅ Bitim muvaffaqiyatli! +{pack['iron']:,}⛓️ temir omboringizga yetkazildi."


async def buy_food_with_gold(session: AsyncSession, user_id: int, pack_code_or_gold: Any) -> Tuple[bool, str]:
    """Bozordan oltin evaziga tayyor oziq-ovqat (don) xarid qilish (muvozanatli narxda)"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    # 1. Agar to'plam kodi uzatilgan bo'lsa (masalan, food_1, food_2...)
    if isinstance(pack_code_or_gold, str) and pack_code_or_gold in FOOD_MARKET_PACKS:
        pack = FOOD_MARKET_PACKS[pack_code_or_gold]
        gold_cost = pack["gold"]
        food_amount = pack["food"]
    else:
        # 2. Agar foydalanuvchi ixtiyoriy oltin miqdorini kiritgan bo'lsa
        try:
            gold_cost = int(pack_code_or_gold)
        except (ValueError, TypeError):
            return False, "Noto'g'ri tovar yoki oltin miqdori tanlandi."

        if gold_cost < 50:
            return False, "❌ Minimal xarid miqdori — 50🪙 oltin!"

        # Muvozanatli progressiv stavkalar (1.2x dan 1.8x gacha)
        if gold_cost >= 5000:
            multiplier = 1.8
        elif gold_cost >= 2500:
            multiplier = 1.6
        elif gold_cost >= 1000:
            multiplier = 1.5
        elif gold_cost >= 500:
            multiplier = 1.4
        elif gold_cost >= 300:
            multiplier = 1.3
        else:
            multiplier = 1.2

        food_amount = int(gold_cost * multiplier)

    if (user.gold or 0) < gold_cost:
        return False, f"❌ Xarid uchun yetarli oltin yo'q!\nKerak: {gold_cost:,}🪙 (Sizda: {user.gold:,}🪙)"

    user.gold -= gold_cost
    user.food = (user.food or 0) + food_amount
    await session.commit()
    return True, f"✅ Bitim muvaffaqiyatli!\n\n💰 Sarflandi: -{gold_cost:,}🪙 Oltin\n🌾 Olingan: +{food_amount:,}🌾 Oziq-ovqat\n📦 Yangi zaxirangiz: {user.food:,}🌾 oziq, {user.gold:,}🪙 oltin."


async def upgrade_grain_mill(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Don tegirmonini (Grain Mill) keyingi darajaga ko'tarish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    current_lvl = getattr(user, "grain_mill_level", 1) or 1
    if current_lvl >= 10:
        return False, "❌ Don tegirmoni maksimal 10-darajaga yetgan! Butun vodiy donlari sizning tegirmoningizda yanchilmoqda."

    next_lvl = current_lvl + 1
    gold_cost = current_lvl * 1200
    iron_cost = current_lvl * 600

    if (user.gold or 0) < gold_cost or (user.iron or 0) < iron_cost:
        return False, f"❌ Tegirmonni kuchaytirish uchun {gold_cost:,}🪙 oltin va {iron_cost:,}⛓️ temir kerak! (Sizda: {user.gold:,}🪙 / {user.iron:,}⛓️)"

    user.gold -= gold_cost
    user.iron -= iron_cost
    user.grain_mill_level = next_lvl
    user.prestige = (user.prestige or 0) + 3
    user.xp = (user.xp or 0) + next_lvl * 25

    from core.leveling import check_user_level_up
    check_user_level_up(user)

    await session.commit()
    return True, f"🎉 TABRIKLAYMIZ! Don tegirmoni {next_lvl}-darajaga ko'tarildi! (+{next_lvl*75}🌾 oziq-ovqat/soat ishlab chiqariladi)"


async def upgrade_castle_keep(session: AsyncSession, user_id: int, territory_id: int) -> Tuple[bool, str]:
    """Qal'a qasrini (Keep Tier) 1 dan 5 gacha ko'tarish"""
    user = await get_user_any(session, user_id)
    territory = await session.get(models.Territory, territory_id)
    if not user or not territory:
        return False, "Foydalanuvchi yoki qal'a topilmadi."

    if territory.owner_house_id != user.house_id:
        return False, "❌ Siz faqat o'z xonadoningizga tegishli qal'alarni kengaytira olasiz!"

    current_lvl = getattr(territory, "castle_level", 1) or 1
    if current_lvl >= 5:
        return False, "❌ Qal'a maksimal 5-darajaga (Afsonaviy Istehkom) yetgan!"

    next_lvl = current_lvl + 1
    gold_cost = current_lvl * 3000
    iron_cost = current_lvl * 2500

    if (user.gold or 0) < gold_cost or (user.iron or 0) < iron_cost:
        return False, f"❌ Qal'ani {next_lvl}-bosqichga ko'tarish uchun {gold_cost:,}🪙 oltin va {iron_cost:,}⛓️ temir kerak! (Sizda: {user.gold:,}🪙 / {user.iron:,}⛓️)"

    user.gold -= gold_cost
    user.iron -= iron_cost
    territory.castle_level = next_lvl
    territory.defense = (territory.defense or 0) + 300
    territory.gold_income = int((territory.gold_income or 200) * 1.25)
    territory.food_income = int((territory.food_income or 500) * 1.25)
    territory.iron_income = int((territory.iron_income or 100) * 1.25)
    user.prestige = (user.prestige or 0) + 5
    user.xp = (user.xp or 0) + next_lvl * 30

    from core.leveling import check_user_level_up
    check_user_level_up(user)

    await session.commit()
    return True, f"🏰 TABRIKLAYMIZ! {territory.name} qal'asi {next_lvl}-bosqichga (Tier {next_lvl}) ko'tarildi!\n🛡️ Mudofaa: +300\n💰 Soatlik daromad: +25%"


async def release_user_dragon(session: AsyncSession, user_id: int, dragon_id: int) -> Tuple[bool, str]:
    """Ajdardan voz kechish (tashlash) va uyani bo'shatish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    dragon = await session.get(models.Dragon, dragon_id) if (dragon_id and dragon_id <= 2147483647) else None
    if not dragon or dragon.user_id != user.id:
        u_dragons = await get_user_dragons(session, user.id)
        if u_dragons:
            dragon = u_dragons[0]
        else:
            return False, "❌ Ajdar topilmadi yoki u allaqachon tashlangan."

    # Qal'alardagi qo'riqchilik ro'yxatidan tozalash
    t_res = await session.execute(select(models.Territory))
    for terr in t_res.scalars().all():
        if terr.reinforcements_json:
            try:
                r_data = json.loads(terr.reinforcements_json)
                changed = False
                if "stationed_dragons" in r_data and isinstance(r_data["stationed_dragons"], list):
                    orig_len = len(r_data["stationed_dragons"])
                    r_data["stationed_dragons"] = [st for st in r_data["stationed_dragons"] if st.get("dragon_id") != dragon.id]
                    if len(r_data["stationed_dragons"]) != orig_len:
                        changed = True
                if "stationed_dragon" in r_data and r_data["stationed_dragon"].get("dragon_id") == dragon.id:
                    if r_data.get("stationed_dragons"):
                        r_data["stationed_dragon"] = max(r_data["stationed_dragons"], key=lambda d: d.get("power", 0))
                    else:
                        del r_data["stationed_dragon"]
                    changed = True
                if changed:
                    terr.reinforcements_json = json.dumps(r_data)
            except Exception:
                pass

    dragon_name = dragon.name
    await session.delete(dragon)
    await session.commit()
    return True, f"🗑️ **{dragon_name}** tashlandi (ozod qilindi)! Bo'shagan o'ringa yangi ajdar xarid qilishingiz mumkin."


async def reset_entire_game(session: AsyncSession) -> None:
    """Butun o'yin ma'lumotlarini 0 ga tushirish (yangi mavsum / to'liq restart)"""
    from data.houses_data import HOUSES_DATA
    from data.map_data import TERRITORIES_DATA

    # 1. Barcha o'yinchilar va ularga tegishli yozuvlarni tozalash
    table_models = [
        models.RavenMessage,
        models.Duel,
        models.Dragon,
        models.HouseVote,
        models.Transaction,
        models.War,
        models.Alliance,
        models.QuestProgress,
        models.BattleReport,
        models.BattleMarch,
        models.Building,
        models.Artifact,
        models.NightKingContribution,
        models.Character,
        models.Army,
        models.HouseMember,
        models.User,
    ]
    for tm in table_models:
        try:
            await session.execute(delete(tm))
        except Exception:
            pass

    # 2. Xonadonlarni boshlang'ich holatiga qaytarish
    houses_res = await session.execute(select(models.House))
    all_houses = houses_res.scalars().all()
    for h in all_houses:
        h.lord_user_id = None
        h.lord_elected_at = None
        h_info = HOUSES_DATA.get(h.code, {})
        h.gold = h_info.get("starting_gold", 5000)
        h.food = h_info.get("starting_food", 10000)
        h.iron = h_info.get("starting_iron", 2000)
        h.prestige = h_info.get("prestige", 100)

    # 3. Hududlarni (qal'alarni) boshlang'ich holatiga qaytarish
    terrs_res = await session.execute(select(models.Territory))
    all_terrs = terrs_res.scalars().all()
    for t in all_terrs:
        t_info = TERRITORIES_DATA.get(t.code, {})
        t.owner_house_id = t_info.get("initial_owner_id", 1)
        t.garrison_infantry = t_info.get("garrison_infantry", 200)
        t.garrison_archers = t_info.get("garrison_archers", 100)
        t.garrison_cavalry = t_info.get("garrison_cavalry", 50)
        t.garrison_spearmen = t_info.get("garrison_spearmen", 50)
        t.defense = t_info.get("defense", 500)
        t.castle_level = 1
        t.last_tax_collected_at = None
        t.reinforcements_json = None
        t.conquered_by_user_id = None

    await session.commit()


async def get_player_conquered_castles_summary(session: AsyncSession) -> Dict[str, Any]:
    """Admin paneli uchun: qaysi o'yinchi nechta va qaysi qalalarni egallaganligi to'liq hisoboti"""
    # 1. Barcha hududlar (qalalar)
    terrs_res = await session.execute(
        select(models.Territory).order_by(models.Territory.name)
    )
    all_terrs = terrs_res.scalars().all()

    # 2. Barcha foydalanuvchilar
    users_res = await session.execute(
        select(models.User)
    )
    all_users = {u.id: u for u in users_res.scalars().all()}
    users_by_tg = {u.telegram_id: u for u in all_users.values()}

    # 3. Barcha xonadonlar
    houses_res = await session.execute(
        select(models.House)
    )
    all_houses = {h.id: h for h in houses_res.scalars().all()}

    # 4. G'olib bo'lingan so'nggi jang hisobotlari
    reports_res = await session.execute(
        select(models.BattleReport)
        .where(models.BattleReport.result == "attacker_won")
        .order_by(desc(models.BattleReport.id))
    )
    battle_reports = reports_res.scalars().all()
    latest_conqueror_by_terr: Dict[int, int] = {}
    for r in battle_reports:
        if r.territory_id not in latest_conqueror_by_terr:
            latest_conqueror_by_terr[r.territory_id] = r.attacker_user_id

    # 5. O'yinchilar ro'yxatini shakllantirish
    player_stats: Dict[int, Dict[str, Any]] = {}

    def ensure_player_entry(usr: models.User) -> Dict[str, Any]:
        if usr.id not in player_stats:
            h = all_houses.get(usr.house_id)
            player_stats[usr.id] = {
                "user_id": usr.id,
                "telegram_id": usr.telegram_id,
                "name": usr.full_name or usr.username or f"Lord {usr.id}",
                "username": usr.username or "",
                "rank": usr.rank or "member",
                "house_name": h.name if h else "Xonadonsiz",
                "house_emoji": h.emoji if h else "🏰",
                "is_lord": bool(h and h.lord_user_id == usr.telegram_id),
                "total_castles": 0,
                "direct_conquests": 0,
                "conquered_castles": [],
                "house_castles": [],
                "castles": [],
            }
        return player_stats[usr.id]

    # Avval barcha ro'yxatdan o'tgan o'yinchilarni ro'yxatga kiritamiz
    for u in all_users.values():
        ensure_player_entry(u)

    npc_castles_count = 0
    player_castles_count = 0
    neutral_castles_count = 0
    all_castles_overview = []

    for t in all_terrs:
        tot_garrison = (
            (t.garrison_infantry or 0)
            + (t.garrison_archers or 0)
            + (t.garrison_cavalry or 0)
            + (t.garrison_spearmen or 0)
        )
        terr_dict = {
            "id": t.id,
            "code": t.code,
            "name": t.name,
            "castle_name": t.castle_name or "Qal'a",
            "region": t.region,
            "is_capital": bool(t.is_capital),
            "castle_level": t.castle_level or 1,
            "defense": t.defense or 0,
            "garrison_total": tot_garrison,
            "is_direct_conquest": False,
        }

        # Egalikni tekshirish
        conqueror_user = all_users.get(t.conquered_by_user_id) if getattr(t, "conquered_by_user_id", None) else None

        if not conqueror_user and t.id in latest_conqueror_by_terr:
            rep_uid = latest_conqueror_by_terr[t.id]
            rep_user = all_users.get(rep_uid)
            if rep_user and rep_user.house_id == t.owner_house_id:
                conqueror_user = rep_user

        owner_house = all_houses.get(t.owner_house_id) if t.owner_house_id else None

        holder_name = "Hech kim"
        holder_user_id = None
        is_direct = False

        if conqueror_user:
            terr_dict["is_direct_conquest"] = True
            is_direct = True
            entry = ensure_player_entry(conqueror_user)
            entry["total_castles"] += 1
            entry["direct_conquests"] += 1
            entry["conquered_castles"].append(terr_dict)
            entry["castles"].append(terr_dict)
            player_castles_count += 1
            holder_name = f"{conqueror_user.full_name} (⚔️ Fath etilgan)"
            holder_user_id = conqueror_user.id
        elif owner_house and not owner_house.is_npc:
            lord_user = users_by_tg.get(owner_house.lord_user_id) if owner_house.lord_user_id else None
            if not lord_user:
                for u in all_users.values():
                    if u.house_id == owner_house.id:
                        lord_user = u
                        break

            if lord_user:
                entry = ensure_player_entry(lord_user)
                entry["total_castles"] += 1
                entry["house_castles"].append(terr_dict)
                entry["castles"].append(terr_dict)
                player_castles_count += 1
                holder_name = f"{owner_house.emoji} {owner_house.name} ({lord_user.full_name})"
                holder_user_id = lord_user.id
            else:
                npc_castles_count += 1
                holder_name = f"{owner_house.emoji} {owner_house.name} (Bo'sh)"
        elif owner_house and owner_house.is_npc:
            npc_castles_count += 1
            holder_name = f"{owner_house.emoji} {owner_house.name} (NPC)"
        else:
            neutral_castles_count += 1
            holder_name = "Egasi yo'q"

        all_castles_overview.append({
            "id": t.id,
            "name": t.name,
            "castle_name": t.castle_name or "Qal'a",
            "region": t.region,
            "owner_house_name": owner_house.name if owner_house else "Egasi yo'q",
            "owner_house_emoji": owner_house.emoji if owner_house else "🏰",
            "holder_name": holder_name,
            "holder_user_id": holder_user_id,
            "is_direct_conquest": is_direct,
            "garrison_total": tot_garrison,
            "defense": t.defense or 0,
        })

    sorted_players = sorted(
        player_stats.values(),
        key=lambda x: (x["direct_conquests"], x["total_castles"], len(x["castles"])),
        reverse=True
    )
    conquerors_list = [p for p in sorted_players if p["direct_conquests"] > 0]

    return {
        "total_territories": len(all_terrs),
        "player_controlled": player_castles_count,
        "npc_controlled": npc_castles_count,
        "neutral_controlled": neutral_castles_count,
        "players": sorted_players,
        "conquerors": conquerors_list,
        "direct_conquests_total": sum(p["direct_conquests"] for p in conquerors_list),
        "castles_overview": all_castles_overview,
    }


# ============================================================
# WAR MODE / HARBIY HOLAT CRUD
# ============================================================

async def get_or_create_war_event(session: AsyncSession) -> models.EventState:
    """'war_mode' EventState yozuvini olish yoki yaratish"""
    res = await session.execute(
        select(models.EventState).where(models.EventState.event_name == "war_mode")
    )
    ev = res.scalar_one_or_none()
    if not ev:
        ev = models.EventState(
            event_name="war_mode",
            data_json=json.dumps({
                "auto_close_at": None,
                "duration_hours": None,
                "opened_by": None,
                "opened_at": None,
                "closed_at": None,
            }),
            is_active=False,  # Standart holat: Sulh (Urush yopiq)
            started_at=datetime.utcnow(),
        )
        session.add(ev)
        await session.commit()
    return ev


async def get_war_status(session: AsyncSession) -> Dict[str, Any]:
    """Joriy urush holatini olish (muddati o'tgan bo'lsa avto-yopish)"""
    ev = await get_or_create_war_event(session)
    data = {}
    try:
        data = json.loads(ev.data_json or "{}")
    except Exception:
        data = {}

    is_active = bool(ev.is_active)
    auto_close_str = data.get("auto_close_at")
    auto_close_at = None
    remaining_seconds = None

    if auto_close_str:
        try:
            auto_close_at = datetime.fromisoformat(auto_close_str)
            now = datetime.utcnow()
            diff = (auto_close_at - now).total_seconds()
            if diff <= 0 and is_active:
                # Muddat o'tgan, urushni yopamiz
                ev.is_active = False
                data["closed_at"] = now.isoformat()
                data["auto_close_at"] = None
                ev.data_json = json.dumps(data)
                await session.commit()
                is_active = False
                remaining_seconds = 0
            else:
                remaining_seconds = max(0, int(diff))
        except Exception:
            auto_close_at = None

    return {
        "is_active": is_active,
        "auto_close_at": auto_close_at,
        "remaining_seconds": remaining_seconds,
        "duration_hours": data.get("duration_hours"),
        "opened_by": data.get("opened_by"),
        "opened_at": data.get("opened_at"),
        "closed_at": data.get("closed_at"),
        "started_at": ev.started_at,
    }


async def set_war_status(
    session: AsyncSession,
    is_active: bool,
    duration_hours: Optional[float] = None,
    opened_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Urush holatini yoqish yoki o'chirish"""
    ev = await get_or_create_war_event(session)
    now = datetime.utcnow()
    data = {}
    try:
        data = json.loads(ev.data_json or "{}")
    except Exception:
        data = {}

    if is_active:
        ev.is_active = True
        ev.started_at = now
        data["opened_by"] = opened_by
        data["opened_at"] = now.isoformat()
        data["closed_at"] = None
        if duration_hours and duration_hours > 0:
            auto_close = now + timedelta(hours=duration_hours)
            data["auto_close_at"] = auto_close.isoformat()
            data["duration_hours"] = duration_hours
        else:
            data["auto_close_at"] = None
            data["duration_hours"] = None
    else:
        ev.is_active = False
        data["closed_at"] = now.isoformat()
        data["auto_close_at"] = None
        data["duration_hours"] = None

    ev.data_json = json.dumps(data)
    await session.commit()
    return await get_war_status(session)


async def extend_war_duration(
    session: AsyncSession,
    additional_hours: float = 1.0,
) -> Dict[str, Any]:
    """Ochiq urush vaqtini uzaytirish"""
    ev = await get_or_create_war_event(session)
    if not ev.is_active:
        return await get_war_status(session)

    now = datetime.utcnow()
    data = {}
    try:
        data = json.loads(ev.data_json or "{}")
    except Exception:
        data = {}

    current_close_str = data.get("auto_close_at")
    base_time = now
    if current_close_str:
        try:
            cur_dt = datetime.fromisoformat(current_close_str)
            if cur_dt > now:
                base_time = cur_dt
        except Exception:
            base_time = now

    new_close = base_time + timedelta(hours=additional_hours)
    data["auto_close_at"] = new_close.isoformat()
    ev.data_json = json.dumps(data)
    await session.commit()
    return await get_war_status(session)


# ============================================================
# RESOURCE EXCHANGE (FOOD / IRON ➡️ GOLD) CRUD
# ============================================================

async def sell_food_for_gold(session: AsyncSession, user_id: int, food_amount: int) -> Tuple[bool, str]:
    """Donni (oziq-ovqat) oltinga almashtirish (2 Don = 1 Oltin)"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    if food_amount < 100:
        return False, "❌ Minimal sotish miqdori — 100🌾 don!"

    if (user.food or 0) < food_amount:
        return False, f"❌ Sizda buncha don yo'q!\nSizda: {(user.food or 0):,}🌾 | So'ralgan: {food_amount:,}🌾"

    gold_earned = food_amount // 2
    user.food = (user.food or 0) - food_amount
    user.gold = (user.gold or 0) + gold_earned
    await session.commit()
    return True, f"✅ Bitim muvaffaqiyatli!\n\n🌾 Sotildi: -{food_amount:,}🌾 Don\n🪙 Qabul qilindi: +{gold_earned:,}🪙 Oltin\n💰 Yangi xazinangiz: {user.food:,}🌾 don, {user.gold:,}🪙 oltin."


async def sell_iron_for_gold(session: AsyncSession, user_id: int, iron_amount: int) -> Tuple[bool, str]:
    """Temirni oltinga almashtirish (1 Temir = 1 Oltin)"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    if iron_amount < 50:
        return False, "❌ Minimal sotish miqdori — 50⛓️ temir!"

    if (user.iron or 0) < iron_amount:
        return False, f"❌ Sizda buncha temir yo'q!\nSizda: {(user.iron or 0):,}⛓️ | So'ralgan: {iron_amount:,}⛓️"

    gold_earned = iron_amount
    user.iron = (user.iron or 0) - iron_amount
    user.gold = (user.gold or 0) + gold_earned
    await session.commit()
    return True, f"✅ Bitim muvaffaqiyatli!\n\n⛓️ Sotildi: -{iron_amount:,}⛓️ Temir\n🪙 Qabul qilindi: +{gold_earned:,}🪙 Oltin\n💰 Yangi xazinangiz: {user.iron:,}⛓️ temir, {user.gold:,}🪙 oltin."


# ============================================================
# HOUSE TRADES (XONADONLARARO SAVDO BIRJASI) CRUD
# ============================================================

async def create_house_trade(
    session: AsyncSession,
    user_id: int,
    offer_resource: str,
    offer_amount: int,
    request_resource: str,
    request_amount: int,
) -> Tuple[bool, str, Optional[models.HouseTrade]]:
    """Xonadonlararo savdo loti yaratish (taklif qilingan tovar zaxiraga/escrow olinadi)"""
    user = await get_user_with_relations(session, user_id)
    if not user or not user.house_id:
        return False, "❌ Siz biror xonadonga a'zo bo'lishingiz kerak!", None

    valid_res = ["food", "iron", "gold"]
    if offer_resource not in valid_res or request_resource not in valid_res:
        return False, "❌ Noto'g'ri resurs turi tanlandi! (food, iron, gold)", None

    if offer_resource == request_resource:
        return False, "❌ Bir xil resursni bir-biriga almashtirib bo'lmaydi!", None

    if offer_amount <= 0 or request_amount <= 0:
        return False, "❌ Resurs miqdori 0 dan katta bo'lishi kerak!", None

    res_names = {"food": "🌾 Don", "iron": "⛓️ Temir", "gold": "🪙 Oltin"}
    cur_val = getattr(user, offer_resource, 0) or 0
    if cur_val < offer_amount:
        return False, f"❌ Sizda yetarli {res_names[offer_resource]} yo'q!\nKerak: {offer_amount:,} (Sizda: {cur_val:,})", None

    # Zaxiraga olish
    setattr(user, offer_resource, cur_val - offer_amount)

    trade = models.HouseTrade(
        seller_user_id=user.id,
        seller_house_id=user.house_id,
        offer_resource=offer_resource,
        offer_amount=offer_amount,
        request_resource=request_resource,
        request_amount=request_amount,
        status="active",
        created_at=datetime.utcnow(),
    )
    session.add(trade)
    await session.commit()
    return True, f"⚖️ **SAVDO LOTI BIRJAGA JOYLASHDIRILDI!**\n\nTaklif: **{offer_amount:,}** {res_names[offer_resource]}\nTalab: **{request_amount:,}** {res_names[request_resource]}\n\nBoshqa xonadon a'zolari ushbu lotni xarid qilishi mumkin.", trade


async def get_active_house_trades(session: AsyncSession) -> List[models.HouseTrade]:
    """Barcha faol savdo takliflarini olish"""
    stmt = (
        select(models.HouseTrade)
        .options(
            selectinload(models.HouseTrade.seller),
            selectinload(models.HouseTrade.seller_house),
        )
        .where(models.HouseTrade.status == "active")
        .order_by(models.HouseTrade.created_at.desc())
        .limit(40)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


async def get_user_active_trades(session: AsyncSession, user_id: int) -> List[models.HouseTrade]:
    """Foydalanuvchining o'zi joylashtirgan faol takliflari"""
    user = await get_user_any(session, user_id)
    if not user:
        return []
    res = await session.execute(
        select(models.HouseTrade)
        .where(models.HouseTrade.seller_user_id == user.id, models.HouseTrade.status == "active")
        .order_by(models.HouseTrade.created_at.desc())
    )
    return res.scalars().all()


async def cancel_house_trade(session: AsyncSession, user_id: int, trade_id: int) -> Tuple[bool, str]:
    """Savdo taklifini bekor qilish va zaxirani qaytarish"""
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    trade = await session.get(models.HouseTrade, trade_id)
    if not trade or trade.status != "active":
        return False, "❌ Savdo taklifi topilmadi yoki allaqachon yakunlangan."

    if trade.seller_user_id != user.id:
        return False, "❌ Bu savdo taklifi sizga tegishli emas!"

    curr = getattr(user, trade.offer_resource, 0) or 0
    setattr(user, trade.offer_resource, curr + trade.offer_amount)
    trade.status = "cancelled"
    trade.completed_at = datetime.utcnow()
    await session.commit()
    res_names = {"food": "🌾 Don", "iron": "⛓️ Temir", "gold": "🪙 Oltin"}
    return True, f"✅ Savdo loti bekor qilindi. +{trade.offer_amount:,} {res_names.get(trade.offer_resource, '')} hamyoningizga qaytarildi."


async def fulfill_house_trade(session: AsyncSession, buyer_user_id: int, trade_id: int) -> Tuple[bool, str]:
    """Boshqa xonadon savdo lotini xarid qilish"""
    buyer = await get_user_with_relations(session, buyer_user_id)
    if not buyer or not buyer.house_id:
        return False, "❌ Bitim tuzish uchun avval biror xonadonga a'zo bo'lishingiz kerak."

    trade = await session.get(models.HouseTrade, trade_id)
    if not trade or trade.status != "active":
        return False, "❌ Ushbu savdo loti faol emas yoki allaqachon sotib olingan."

    if trade.seller_house_id == buyer.house_id:
        return False, "❌ Xonadonlararo savdoda o'z xonadoningiz taklifini xarid qila olmaysiz!\nBoshqa xonadonlar bilan savdo qiling."

    buyer_res = getattr(buyer, trade.request_resource, 0) or 0
    res_names = {"food": "🌾 Don", "iron": "⛓️ Temir", "gold": "🪙 Oltin"}
    if buyer_res < trade.request_amount:
        return False, f"❌ Sizda yetarli {res_names.get(trade.request_resource, '')} yo'q!\nKerak: {trade.request_amount:,} (Sizda: {buyer_res:,})"

    seller = await session.get(models.User, trade.seller_user_id)
    if not seller:
        return False, "Sotuvchi topilmadi."

    # Resurslar o'tkazmasi
    setattr(buyer, trade.request_resource, buyer_res - trade.request_amount)
    buyer_get = getattr(buyer, trade.offer_resource, 0) or 0
    setattr(buyer, trade.offer_resource, buyer_get + trade.offer_amount)

    seller_get = getattr(seller, trade.request_resource, 0) or 0
    setattr(seller, trade.request_resource, seller_get + trade.request_amount)

    # Ikkala xonadonga ham savdo rivoji uchun +10 Prestige
    seller_house = await session.get(models.House, trade.seller_house_id)
    buyer_house = await session.get(models.House, buyer.house_id)
    if seller_house:
        seller_house.prestige = (seller_house.prestige or 0) + 10
    if buyer_house:
        buyer_house.prestige = (buyer_house.prestige or 0) + 10

    trade.buyer_user_id = buyer.id
    trade.buyer_house_id = buyer.house_id
    trade.status = "completed"
    trade.completed_at = datetime.utcnow()

    # Sotuvchiga Qarg'a xabarnomasi yuborish
    seller_h_name = seller_house.name if seller_house else "Xonadon"
    buyer_h_name = buyer_house.name if buyer_house else "Xonadon"
    raven_msg = models.RavenMessage(
        sender_id=buyer.id,
        recipient_id=seller.id,
        message_text=(
            f"🤝 **SAVDO BITIMI MUVAFFAQIShLI YAKUNLANDI!**\n\n"
            f"**{buyer_h_name}** xonadonidan {buyer.full_name} sizning savdo lotingizni xarid qildi:\n"
            f"• Berildi: -{trade.offer_amount:,} {res_names.get(trade.offer_resource, '')}\n"
            f"• Qabul qilindi: +{trade.request_amount:,} {res_names.get(trade.request_resource, '')}\n\n"
            f"Xonadoningizga savdo qudrati uchun +10 Prestige berildi! ⚖️"
        ),
        gold_attached=0,
        is_read=False,
    )
    session.add(raven_msg)

    await session.commit()
    return True, f"🎉 Bitim muvaffaqiyatli!\n\n+{trade.offer_amount:,} {res_names.get(trade.offer_resource, '')} qabul qildingiz.\n-{trade.request_amount:,} {res_names.get(trade.request_resource, '')} to'landi.\nXonadoningizga +10 Prestige! ⚖️"


# ============================================================
# SIEGE WEAPONS WORKSHOP CRUD
# ============================================================

SIEGE_WEAPON_CONFIG = {
    "catapult": {
        "name": "Qamal Trebusheti (Katapulta)",
        "gold": 400, "iron": 600, "food": 100,
        "max": 20,
        "field": "catapults",
        "desc": "Qal'a devorlarini uzoqdan yemirib tashlaydi (-35 mudofaa/dona)."
    },
    "siege_tower": {
        "name": "Qamal Minorasi",
        "gold": 300, "iron": 500, "food": 50,
        "max": 10,
        "field": "siege_towers",
        "desc": "Piyodalarni devor kamonchilari o'qlaridan himoya qiladi (-35% yo'qotish)."
    }
}


async def build_siege_weapon(session: AsyncSession, user_id: int, weapon_type: str, amount: int = 1) -> Tuple[bool, str]:
    """Qamal qurolini ustaxonada yasash"""
    if weapon_type not in SIEGE_WEAPON_CONFIG or amount <= 0:
        return False, "Noto'g'ri qurol turi yoki miqdor."

    conf = SIEGE_WEAPON_CONFIG[weapon_type]
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    army = await get_user_army(session, user.id)
    if not army:
        return False, "Armiya topilmadi."

    current_val = getattr(army, conf["field"], 0) or 0
    if current_val + amount > conf["max"]:
        return False, f"❌ Siz ko'pi bilan {conf['max']} ta {conf['name']} yasashingiz mumkin! Hozirda sizda: {current_val} ta bor."

    tot_gold = conf["gold"] * amount
    tot_iron = conf["iron"] * amount
    tot_food = conf["food"] * amount

    if user.gold < tot_gold or user.iron < tot_iron or user.food < tot_food:
        return False, (
            f"❌ Resurslar yetarli emas!\n\n"
            f"{amount} ta {conf['name']} yasash uchun kerak:\n"
            f"• 🪙 {tot_gold:,} Oltin (sizda: {user.gold:,})\n"
            f"• ⛓️ {tot_iron:,} Temir (sizda: {user.iron:,})\n"
            f"• 🌾 {tot_food:,} Oziq-ovqat (sizda: {user.food:,})"
        )

    user.gold -= tot_gold
    user.iron -= tot_iron
    user.food -= tot_food
    setattr(army, conf["field"], current_val + amount)

    await session.commit()
    return True, (
        f"✅ **QAMAL QUROLI MUVAFFAQIYATLI YASALDI!**\n\n"
        f"+{amount} ta **{conf['name']}** armiyangiz safiga qo'shildi!\n"
        f"Mavjud zaxira: **{current_val + amount} / {conf['max']} ta**\n"
        f"💡 _{conf['desc']}_"
    )


async def buy_wildfire_defense(session: AsyncSession, user_id: int, territory_id: int, amount: int = 1) -> Tuple[bool, str]:
    """Qal'aga Alkimyogarlar Yovvoyi Olovini o'rnatish (Har bir qal'ada max 5 ta)"""
    user = await get_user_with_relations(session, user_id)
    terr = await get_territory_by_id(session, territory_id)
    if not user or not terr:
        return False, "Ma'lumot topilmadi."

    is_lord = (user.house and user.house.lord_user_id == user.telegram_id) or (user.rank == "king")
    if not is_lord or terr.owner_house_id != user.house_id:
        return False, "❌ Faqat qal'a tegishli bo'lgan xonadon Lordi Yovvoyi Olov o'rnata oladi!"

    curr_wf = getattr(terr, "wildfire_count", 0) or 0
    if curr_wf + amount > 5:
        return False, f"❌ Ushbu qal'ada maksimal 5 ta Yovvoyi Olov saqlanishi mumkin! Hozirda: {curr_wf}/5 ta."

    cost_gold = 1500 * amount
    cost_iron = 800 * amount

    if user.gold < cost_gold or user.iron < cost_iron:
        return False, f"❌ Yovvoyi Olov tayyorlash uchun {cost_gold:,}🪙 Oltin va {cost_iron:,}⛓️ Temir kerak!"

    user.gold -= cost_gold
    user.iron -= cost_iron
    terr.wildfire_count = curr_wf + amount
    await session.commit()

    return True, (
        f"💚🔥 **YOVVOYI OLOV (WILDFIRE) O'RNATILDI!**\n\n"
        f"🏰 **{terr.name}** qal'asi xandaqlariga +{amount} ta Yovvoyi Olov joylashtirildi!\n"
        f"Mavjud zaxira: **{curr_wf + amount} / 5 ta**\n\n"
        f"Dushman qal'aga hujum qilgan zahoti yashil olov avtomatik portlab, dushmanning ulkan qo'shinini yoqib yuboradi!"
    )


# ============================================================
# BRAAVOS TEMIR BANKI (IRON BANK) CRUD
# ============================================================

MAX_BANK_DEPOSIT = 50000
DAILY_INTEREST_RATE = 0.015  # 1.5% kunlik daromad
LOAN_INTEREST_RATE = 0.10    # 10% kredit foizi
LOAN_DAYS = 5                # 5 kunlik muddat


async def get_or_create_iron_bank(session: AsyncSession, user_id: int) -> models.IronBank:
    """Foydalanuvchining Temir Bank hisobini olish yoki yaratish"""
    res = await session.execute(select(models.IronBank).where(models.IronBank.user_id == user_id))
    bank = res.scalar_one_or_none()
    if not bank:
        bank = models.IronBank(
            user_id=user_id,
            deposit_gold=0,
            deposit_updated_at=datetime.utcnow(),
            last_interest_claimed_at=datetime.utcnow(),
            loan_gold=0,
            is_defaulted=False,
        )
        session.add(bank)
        await session.commit()
    return bank


async def deposit_to_iron_bank(session: AsyncSession, user_id: int, amount: int) -> Tuple[bool, str]:
    """Temir bankka omonat qo'yish"""
    if amount <= 0:
        return False, "Noto'g'ri summa."

    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    if user.gold < amount:
        return False, f"❌ Sizda yetarli oltin yo'q (mavjud: {user.gold:,}🪙)."

    bank = await get_or_create_iron_bank(session, user.id)
    if bank.is_defaulted:
        return False, "❌ Sizning qarz muddati o'tib ketgan! Avval qarzni to'lang."

    if (bank.deposit_gold or 0) + amount > MAX_BANK_DEPOSIT:
        rem_allow = max(0, MAX_BANK_DEPOSIT - (bank.deposit_gold or 0))
        return False, f"❌ Maksimal omonat limiti: {MAX_BANK_DEPOSIT:,}🪙. Siz yana eng ko'pi bilan {rem_allow:,}🪙 qo'ya olasiz."

    user.gold -= amount
    bank.deposit_gold = (bank.deposit_gold or 0) + amount
    bank.deposit_updated_at = datetime.utcnow()
    await session.commit()

    return True, (
        f"🏦 **OMONAT QABUL QILINDI!**\n\n"
        f"Braavos Temir Bankiga **+{amount:,}🪙 Oltin** topshirdingiz.\n"
        f"Jami depozitingiz: **{bank.deposit_gold:,}🪙**\n"
        f"Kunlik daromad: **+{int(bank.deposit_gold * DAILY_INTEREST_RATE):,}🪙** (kuniga +1.5%)"
    )


async def withdraw_from_iron_bank(session: AsyncSession, user_id: int, amount: int) -> Tuple[bool, str]:
    """Temir bankdan omonatni yechish"""
    if amount <= 0:
        return False, "Noto'g'ri summa."

    user = await get_user_any(session, user_id)
    bank = await get_or_create_iron_bank(session, user_id)

    curr_dep = bank.deposit_gold or 0
    if curr_dep < amount:
        return False, f"❌ Depozitingizda buncha oltin yo'q! (Mavjud: {curr_dep:,}🪙)"

    bank.deposit_gold = curr_dep - amount
    user.gold = (user.gold or 0) + amount
    bank.deposit_updated_at = datetime.utcnow()
    await session.commit()

    return True, (
        f"🏦 **MABLAG' YECHILDI!**\n\n"
        f"Temir Bankdan **-{amount:,}🪙 Oltin** yechib oldingiz.\n"
        f"Qolgan omonat: **{bank.deposit_gold:,}🪙**"
    )


async def claim_iron_bank_interest(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Omonat bo'yicha to'plangan kunlik foizni yechib olish"""
    user = await get_user_any(session, user_id)
    bank = await get_or_create_iron_bank(session, user_id)

    curr_dep = bank.deposit_gold or 0
    if curr_dep <= 0:
        return False, "❌ Sizda faol omonat mavjud emas."

    now = datetime.utcnow()
    last_claim = bank.last_interest_claimed_at or bank.deposit_updated_at or now
    elapsed_seconds = (now - last_claim).total_seconds()
    days_elapsed = int(elapsed_seconds // 86400)

    if days_elapsed < 1:
        rem_hours = int((86400 - (elapsed_seconds % 86400)) // 3600)
        rem_mins = int(((86400 - (elapsed_seconds % 86400)) % 3600) // 60)
        return False, f"⏳ Foizlar har 24 soatda hisoblanadi. Keyingi foiz olishga: {rem_hours} soat {rem_mins} daqiqa qoldi."

    profit = int(curr_dep * DAILY_INTEREST_RATE * days_elapsed)
    user.gold = (user.gold or 0) + profit
    bank.last_interest_claimed_at = now
    await session.commit()

    return True, (
        f"🪙 **BANK FOIZI MUVAFFAQIYATLI OLINDI!**\n\n"
        f"Braavos Temir Banki omonatingizdan **+{profit:,}🪙 Oltin** sof foyda berdi! ({days_elapsed} kunlik 1.5% daromad)\n"
        f"Jami oltiningiz: **{user.gold:,}🪙**"
    )


async def take_iron_bank_loan(session: AsyncSession, user_id: int, amount: int) -> Tuple[bool, str]:
    """Temir Bankdan kredit (qarz) olish"""
    user = await get_user_with_relations(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    is_lord = (user.house and user.house.lord_user_id == user.telegram_id) or (user.rank == "king")
    if (user.level or 1) < 3 and not is_lord:
        return False, "❌ Temir Bank faqat 3-darajadan yuqori ritsarlar yoki Xonadon Lordlariga qarz beradi!"

    bank = await get_or_create_iron_bank(session, user.id)
    if (bank.loan_gold or 0) > 0:
        return False, f"❌ Sizda allaqachon to'lanmagan qarz mavjud: {bank.loan_gold:,}🪙. Yangi qarz olishdan oldin eskisini to'lang!"

    max_loan = 30000 if is_lord else 10000
    if amount <= 0 or amount > max_loan:
        return False, f"❌ Siz ko'pi bilan {max_loan:,}🪙 qarz ola olasiz!"

    now = datetime.utcnow()
    bank.loan_gold = amount
    bank.loan_due_at = now + timedelta(days=LOAN_DAYS)
    bank.loan_interest_rate = LOAN_INTEREST_RATE
    bank.is_defaulted = False

    user.gold = (user.gold or 0) + amount
    await session.commit()

    repay_total = int(amount * (1.0 + LOAN_INTEREST_RATE))
    due_str = bank.loan_due_at.strftime("%Y-%m-%d %H:%M UTC")

    return True, (
        f"🏦📜 **BRAAVOS TEMIR BANKI QARZ SHARTNOMASI IMZOLANDI!**\n\n"
        f"Sizga **+{amount:,}🪙 Oltin** berildi.\n\n"
        f"⚠️ **Qaytarish shartlari:**\n"
        f"• Qaytariladigan summa: **{repay_total:,}🪙** (+10% foiz bilan)\n"
        f"• Qaytarish muddati: **5 kun** ({due_str} gacha)\n\n"
        f"☠️ _Qoida: 'Temir Bank o'z hisob-kitobini hech qachon unutmaydi!' Agar muddatida qaytarmasangiz, bank sizga qarshi 'Oltin Gala' yollanma armiyasini yuboradi!_"
    )


async def repay_iron_bank_loan(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Kreditni foizi bilan to'liq qaytarish"""
    user = await get_user_any(session, user_id)
    bank = await get_or_create_iron_bank(session, user_id)

    if (bank.loan_gold or 0) <= 0:
        return False, "❌ Sizda to'lanishi kerak bo'lgan qarz yo'q."

    total_due = int(bank.loan_gold * (1.0 + (bank.loan_interest_rate or LOAN_INTEREST_RATE)))
    if user.gold < total_due:
        return False, f"❌ Qarzni to'lash uchun {total_due:,}🪙 Oltin kerak! (Sizda: {user.gold:,}🪙)"

    user.gold -= total_due
    bank.loan_gold = 0
    bank.loan_due_at = None
    bank.is_defaulted = False
    await session.commit()

    return True, (
        f"✅ **QARZ TO'LIQ QAYTARILDI!**\n\n"
        f"Temir Bankka {total_due:,}🪙 Oltin to'landi va shartnoma bekor qilindi.\n"
        f"Endi sizning bank oldidagi obro'yingiz toza! 🏛️"
    )


# ============================================================
# 23. MAVSUMLAR VA SHON-SHARAF ZALI (SEASONS & HALL OF FAME)
# ============================================================
async def get_active_season(session: AsyncSession) -> Optional[models.SeasonState]:
    """Faol 30 kunlik mavsum holatini olish"""
    res = await session.execute(
        select(models.SeasonState).where(models.SeasonState.is_active == True).order_by(models.SeasonState.season_number.desc())
    )
    season = res.scalar_one_or_none()
    if not season:
        now = datetime.utcnow()
        season = models.SeasonState(
            season_number=1,
            start_date=now,
            end_date=now + timedelta(days=30),
            is_active=True,
        )
        session.add(season)
        await session.commit()
        await session.refresh(season)
    return season


async def get_hall_of_fame(session: AsyncSession, limit: int = 10) -> List[models.HallOfFame]:
    """Shon-sharaf zalidagi g'oliblar ro'yxati"""
    res = await session.execute(
        select(models.HallOfFame).order_by(models.HallOfFame.season_number.desc()).limit(limit)
    )
    return list(res.scalars().all())


async def check_and_conclude_season(session: AsyncSession, bot_app=None) -> Tuple[bool, Optional[str]]:
    """
    30 kunlik mavsum vaqti tugaganligini tekshirish va yangi mavsumga o'tish (Soft-Reset).
    G'oliblarni Shon-sharaf zaliga yozadi va barcha xonadon guruhlariga xabar beradi.
    """
    season = await get_active_season(session)
    if not season:
        return False, None

    now = datetime.utcnow()
    if now < season.end_date:
        return False, None  # Mavsum hali davom etmoqda

    # 1. G'olib xonadon va Qirolni aniqlash
    # King's Landing qal'asini egallab turgan xonadon yoki eng ko'p nufuzga ega xonadon
    kl_res = await session.execute(
        select(models.Territory).where(models.Territory.code == "kings_landing")
    )
    kl_terr = kl_res.scalar_one_or_none()

    winner_house = None
    if kl_terr and kl_terr.owner_house_id:
        winner_house = await session.get(models.House, kl_terr.owner_house_id)

    if not winner_house:
        top_h_res = await session.execute(
            select(models.House).order_by(models.House.prestige.desc()).limit(1)
        )
        winner_house = top_h_res.scalar_one_or_none()

    winner_house_name = winner_house.name if winner_house else "Vesteros Ittifoqi"
    winner_house_id = winner_house.id if winner_house else None

    # Qirol
    king_user = None
    if winner_house and winner_house.lord_user_id:
        king_user = await get_user_by_telegram_id(session, winner_house.lord_user_id)
    king_name = king_user.full_name if king_user else (winner_house_name + " Lordi")
    king_uid = king_user.id if king_user else None

    # Eng kuchli jangchi (Mavsum bo'yicha eng yuqori prestige)
    top_w_res = await session.execute(
        select(models.User).order_by(models.User.prestige.desc()).limit(1)
    )
    top_warrior = top_w_res.scalar_one_or_none()
    top_warrior_name = top_warrior.full_name if top_warrior else "Noma'lum Botir"
    top_warrior_prestige = top_warrior.prestige if top_warrior else 0

    # 2. Shon-sharaf zaliga yozish
    hof_entry = models.HallOfFame(
        season_number=season.season_number,
        winner_house_id=winner_house_id,
        winner_house_name=winner_house_name,
        king_user_id=king_uid,
        king_name=king_name,
        top_warrior_name=top_warrior_name,
        top_warrior_prestige=top_warrior_prestige,
        concluded_at=now,
    )
    session.add(hof_entry)

    # 3. Mavsumni yopish va yangi mavsum ochish
    season.is_active = False
    next_season = models.SeasonState(
        season_number=season.season_number + 1,
        start_date=now,
        end_date=now + timedelta(days=30),
        is_active=True,
    )
    session.add(next_season)

    # 4. Soft-reset
    # Qal'alarni dastlabki egalariga qaytarish, devor va olovlarni reset qilish
    from data.map_data import TERRITORIES_DATA
    terr_all = await session.execute(select(models.Territory))
    for t in terr_all.scalars().all():
        init_info = TERRITORIES_DATA.get(t.code, {})
        t.owner_house_id = init_info.get("initial_owner_id", t.owner_house_id)
        t.conquered_by_user_id = None
        t.defense = 500
        t.castle_level = 1
        t.wildfire_count = 0
        t.reinforcements_json = None

    # Armiyalarni qisman yangilash (veteran bonus saqlanadi, progress yo'qolmaydi)
    armies_all = await session.execute(select(models.Army))
    for a in armies_all.scalars().all():
        a.infantry = max(100, int(a.infantry * 0.1))
        a.archers = max(50, int(a.archers * 0.1))
        a.cavalry = max(25, int(a.cavalry * 0.1))
        a.spearmen = max(25, int(a.spearmen * 0.1))
        a.special_troops = 0
        a.catapults = 0
        a.siege_towers = 0

    await session.commit()

    announcement = (
        f"👑🏆 **VESTEROSDA YANGI DAVR: {season.season_number}-MAVSUM YAKUNLANDI!** 🏆👑\n\n"
        f"🏛️ **TEMIR TAXT G'OLIBI:** **{winner_house_name}** xonadoni!\n"
        f"👑 **Yetti Qirollik Qiroli:** **{king_name}**\n"
        f"⚔️ **Mavsumning Eng Buyuk Jangchisi:** **{top_warrior_name}** ({top_warrior_prestige:,} nufuz)\n\n"
        f"📜 G'oliblar nomi abadiy **Shon-sharaf Zali (Hall of Fame)** solnomalariga oltin harflar bilan muhrlandi!\n\n"
        f"🌟 **{next_season.season_number}-MAVSUM BOSHLANDI!** (30 kunlik yangi kurash)\n"
        f"Vesteros qal'alari qayta taqsimlandi, armiyalar yangi g'alabalar uchun saflanmoqda!"
    )

    if bot_app:
        from core.notifier import notify_house_group
        h_res = await session.execute(select(models.House).where(models.House.group_chat_id.isnot(None)))
        for h in h_res.scalars().all():
            try:
                await notify_house_group(bot_app, h.id, announcement)
            except Exception:
                pass

    return True, announcement


# ============================================================
# 24. AFSONAVIY QAHRAMONLAR (LEGENDARY CHAMPIONS)
# ============================================================
from data.champions_data import LEGENDARY_CHAMPIONS

async def get_user_champion(session: AsyncSession, user_id: int) -> Optional[dict]:
    """Foydalanuvchi armiyasidagi faol qahramon ma'lumotlarini olish"""
    res = await session.execute(select(models.Army).where(models.Army.user_id == user_id))
    army = res.scalar_one_or_none()
    if army and army.champion and army.champion in LEGENDARY_CHAMPIONS:
        return LEGENDARY_CHAMPIONS[army.champion]
    return None


async def recruit_champion(session: AsyncSession, user_id: int, champion_id: str) -> Tuple[bool, str]:
    """Afsonaviy sarkardani xizmatga tayinlash"""
    if champion_id not in LEGENDARY_CHAMPIONS:
        return False, "❌ Noma'lum qahramon."

    champ = LEGENDARY_CHAMPIONS[champion_id]
    user = await get_user_any(session, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    res = await session.execute(select(models.Army).where(models.Army.user_id == user_id))
    army = res.scalar_one_or_none()
    if not army:
        return False, "Armiya topilmadi."

    if army.champion == champion_id:
        return False, f"❌ {champ['name']} allaqachon armiyangiz bosh qo'mondoni!"

    cost_gold = champ.get("cost_gold", 10000)
    cost_prestige = champ.get("cost_prestige", 200)

    if (user.gold or 0) < cost_gold:
        return False, f"❌ Qahramonni yollash uchun {cost_gold:,}🪙 Oltin kerak! (Sizda: {user.gold:,}🪙)"
    if (user.prestige or 0) < cost_prestige:
        return False, f"❌ Qahramonni yollash uchun {cost_prestige:,}🎖️ Nufuz kerak! (Sizda: {user.prestige:,}🎖️)"

    user.gold -= cost_gold
    user.prestige -= cost_prestige
    army.champion = champion_id
    await session.commit()

    return True, (
        f"⚔️🎖️ **QAHRAMON TAYINLANDI!**\n\n"
        f"{champ['emoji']} **{champ['name']}** endi armiyangiz Bosh Sarkardasi!\n"
        f"📜 _'{champ['description']}'_\n\n"
        f"Janglarda ushbu qahramon qo'shiningizga xos ustunlik beradi!"
    )


async def dismiss_champion(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Qahramonni vazifasidan ozod qilish"""
    res = await session.execute(select(models.Army).where(models.Army.user_id == user_id))
    army = res.scalar_one_or_none()
    if not army or not army.champion:
        return False, "❌ Sizda faol bosh sarkarda tayinlanmagan."

    old_champ = LEGENDARY_CHAMPIONS.get(army.champion, {}).get("name", "Qahramon")
    army.champion = None
    await session.commit()

    return True, f"✅ **{old_champ}** sarkardalik vazifasidan ozod etildi."


# ============================================================
# 25. JOSUSLIK VA QIZIL TO'Y (ESPIONAGE & SABOTAGE CRUD)
# ============================================================

SPY_MISSION_COSTS = {
    "scout": 1000,
    "sabotage": 3000,
    "open_gates": 5000,
}

async def send_spy_mission(
    session: AsyncSession,
    user_id: int,
    target_territory_id: int,
    mission_type: str,
    bot_app=None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Qal'aga josus yuborish (Razvedka, Sabotaj, Darvozalarni ochish).
    """
    if mission_type not in SPY_MISSION_COSTS:
        return False, "❌ Noma'lum josuslik topshirig'i.", {}

    cost = SPY_MISSION_COSTS[mission_type]

    user_res = await session.execute(select(models.User).where(models.User.id == user_id))
    user = user_res.scalar_one_or_none()
    if not user:
        return False, "❌ O'yinchi topilmadi.", {}

    if user.gold < cost:
        return False, f"❌ Josus yollash uchun {cost:,}💰 Oltin kerak! (Sizda: {user.gold:,}💰)", {}

    terr_res = await session.execute(
        select(models.Territory).where(models.Territory.id == target_territory_id)
    )
    territory = terr_res.scalar_one_or_none()
    if not territory:
        return False, "❌ Maqsadli hudud/qal'a topilmadi.", {}

    if getattr(territory, "conquered_by_user_id", None) == user.id:
        return False, "❌ O'zingiz egallagan qal'aga josus yubora olmaysiz!", {}

    if user.house_id and territory.owner_house_id == user.house_id:
        return False, "❌ O'z xonadoningiz qal'asiga josus yubora olmaysiz!", {}

    # Oltinni yechish
    user.gold -= cost

    # Ehtimolliklar:
    # scout: 85% success, 15% caught
    # sabotage: 65% success, 35% caught
    # open_gates: 55% success, 45% caught
    success_rates = {
        "scout": 0.85,
        "sabotage": 0.65,
        "open_gates": 0.55,
    }

    roll = random.random()
    is_success = roll <= success_rates[mission_type]

    report_data = {}
    now = datetime.utcnow()

    # Himoyachi qal'a sohibini yoki xonadon lordini topish
    defender_lord = None
    if getattr(territory, "conquered_by_user_id", None):
        defender_lord = await session.get(models.User, territory.conquered_by_user_id)
    elif territory.owner_house_id:
        h_obj = await session.get(models.House, territory.owner_house_id)
        if h_obj and h_obj.lord_user_id:
            defender_lord = await session.get(models.User, h_obj.lord_user_id)

    if not is_success:
        # Josus fosh bo'ldi va qatl etildi
        penalties = {"scout": 5, "sabotage": 15, "open_gates": 25}
        pen = penalties.get(mission_type, 10)
        user.prestige = max(0, user.prestige - pen)

        report_text = (
            f"🕵️🚨 **JOSUS QO'LGA OLINDI VA QATL ETILDI!**\n\n"
            f"🏰 Qal'a: **{territory.name}**\n"
            f"Siz yuborgan ayg'oqchi devordan oshib o'tayotganda sergak soqchilar tomonidan ushlandi.\n"
            f"Qiynoqlardan so'ng josus omma oldida dorga osildi!\n\n"
            f"📉 Yo'qotish: -{cost:,}💰 Oltin, -{pen}🎖️ Nufuz."
        )

        mission = models.SpyMission(
            user_id=user.id,
            target_territory_id=territory.id,
            mission_type=mission_type,
            cost_gold=cost,
            status="caught",
            report_text=report_text,
            created_at=now,
        )
        session.add(mission)
        await session.commit()

        # Himoyachiga ogohlantirish yuborish
        if bot_app and defender_lord and defender_lord.telegram_id:
            try:
                await bot_app.bot.send_message(
                    chat_id=defender_lord.telegram_id,
                    text=(
                        f"🛡️🚨 **QAL'ADA DUSHMAN JOSUSI USHLANDI!**\n\n"
                        f"🏰 **{territory.name}** qal'angizga yashirincha suqilib kirmoqchi bo'lgan noma'lum josus qo'riqchilar tomonidan qo'lga olindi va qatl etildi!"
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        return False, report_text, {"status": "caught"}

    # MUVAFFAQIYATLI TOPSHIRIQ
    if mission_type == "scout":
        # Razvedka
        user.prestige += 10
        # Ajdar bormi?
        dr_info = get_stationed_dragon_info(territory)
        dr_text = "🐉 Ajdar: *Qal'ada ajdar yo'q*"
        if dr_info and isinstance(dr_info, dict):
            dr_name = dr_info.get("name", "Noma'lum Ajdar")
            dr_pow = dr_info.get("power", 0)
            dr_text = f"🐉 Ajdar: **{dr_name}** (⚡ {dr_pow} quvvat)"

        report_text = (
            f"🕵️📜 **JOSUSLIK RAZVEDKA HISOBOTI**\n\n"
            f"🏰 Qal'a: **{territory.name}** ({territory.castle_name})\n"
            f"🛡️ Devor mudofaasi: **{territory.defense}** | Istehkom Tier: **{territory.castle_level}**\n"
            f"💚 Wildfire bochkalari: **{territory.wildfire_count}** ta\n"
            f"{dr_text}\n\n"
            f"👥 **GARNIZON KUCHLARI:**\n"
            f"• 🗡️ Piyodalar: **{territory.garrison_infantry:,}**\n"
            f"• 🏹 Kamonchilar: **{territory.garrison_archers:,}**\n"
            f"• 🐎 Otliqlar: **{territory.garrison_cavalry:,}**\n"
            f"• 🔱 Nayzadorlar: **{territory.garrison_spearmen:,}**\n\n"
            f"🎖️ Nufuz: +10 ball qo'shildi."
        )
        report_data = {
            "infantry": territory.garrison_infantry,
            "archers": territory.garrison_archers,
            "cavalry": territory.garrison_cavalry,
            "spearmen": territory.garrison_spearmen,
            "defense": territory.defense,
            "wildfire": territory.wildfire_count,
        }

    elif mission_type == "sabotage":
        # Sabotaj
        user.prestige += 20
        sabotage_effect = ""
        if territory.wildfire_count > 0:
            destroyed_wf = min(territory.wildfire_count, random.randint(1, 2))
            territory.wildfire_count -= destroyed_wf
            sabotage_effect = f"💚🔥 Josus yashirincha kirib, **{destroyed_wf}** bochka Yovvoyi Olovni (Wildfire) xandaqqa to'kib yoqib yubordi!"
        else:
            dmg = random.randint(60, 140)
            territory.defense = max(50, territory.defense - dmg)
            sabotage_effect = f"🏰💥 Josuslar qal'a yog'och konstruksiyalari va mudofaa moslamalariga o't qo'ydi: devor mustahkamligi **-{dmg}** ballga tushirildi! (Hozirgi devor: **{territory.defense}**)"

        report_text = (
            f"🔥🕵️ **SABOTAJ MUVAFFAQIYATLI AMALGA OSHIRILDI!**\n\n"
            f"🏰 Qal'a: **{territory.name}**\n"
            f"{sabotage_effect}\n\n"
            f"🎖️ Jasorat uchun +20 Nufuz berildi."
        )
        report_data = {
            "status": "success",
            "type": "sabotage",
            "defense": territory.defense,
            "wildfire": territory.wildfire_count,
        }

        if bot_app and defender_lord and defender_lord.telegram_id:
            try:
                await bot_app.bot.send_message(
                    chat_id=defender_lord.telegram_id,
                    text=(
                        f"🔥🚨 **DIQQAT! QAL'ANGIZDA SABOTAJ SODIR ETILDI!**\n\n"
                        f"🏰 **{territory.name}** qal'asiga suqilib kirgan sabotajchilar mudofaaga zarba berib, qochib ketishga ulgurdi!"
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    elif mission_type == "open_gates":
        # Darvozalarni ochish
        user.prestige += 30
        territory.gates_compromised_until = now + timedelta(hours=2)
        report_text = (
            f"🚪🔓 **DARVOZALAR OCHILDI (QIZIL TO'Y NIFOG'I)!**\n\n"
            f"🏰 Qal'a: **{territory.name}**\n"
            f"Siz yuborgan josus soqchilarni chalg'itib, qal'aning temir darvoza zanjirini buzdi va ichkaridan ochib qo'ydi!\n\n"
            f"⏱️ Muddat: **2 soat** davomida ushbu qal'aga qilingan har qanday hujumda devor himoyasi **-30%** ga pasayadi!\n"
            f"🎖️ Nufuz: +30 ball qo'shildi."
        )
        report_data = {
            "status": "success",
            "type": "open_gates",
            "gates_compromised_until": str(territory.gates_compromised_until),
        }

        if bot_app and defender_lord and defender_lord.telegram_id:
            try:
                await bot_app.bot.send_message(
                    chat_id=defender_lord.telegram_id,
                    text=(
                        f"🚪⚠️ **XAVF: DARVOZALAR BUZIB OCHILDI!**\n\n"
                        f"🏰 **{territory.name}** qal'angiz darvozalari dushman josusi tomonidan buzib ochildi! Keyingi 2 soat ichida qal'a devor himoyasi -30% zaif holatda bo'ladi!"
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    mission = models.SpyMission(
        user_id=user.id,
        target_territory_id=territory.id,
        mission_type=mission_type,
        cost_gold=cost,
        status="success",
        report_text=report_text,
        created_at=now,
    )
    session.add(mission)
    await session.commit()

    return True, report_text, report_data


async def get_user_spy_reports(session: AsyncSession, user_id: int, limit: int = 5) -> List[models.SpyMission]:
    """Foydalanuvchining oxirgi josuslik hisobotlari"""
    try:
        res = await session.execute(
            select(models.SpyMission)
            .where(models.SpyMission.user_id == user_id)
            .options(selectinload(models.SpyMission.target_territory))
            .order_by(desc(models.SpyMission.created_at))
            .limit(limit)
        )
        return res.scalars().all()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"get_user_spy_reports xatosi: {e}")
        return []


# ============================================================
# 26. RITSARLAR TURNIRI VA STAVKALAR (TOURNAMENT & BETS CRUD)
# ============================================================

async def get_active_tournament(session: AsyncSession) -> Optional[models.Tournament]:
    """Faol turnirni ishtirokchilari va stavkalari bilan olish"""
    res = await session.execute(
        select(models.Tournament)
        .where(models.Tournament.status == "active")
        .options(
            selectinload(models.Tournament.participants),
            selectinload(models.Tournament.bets),
        )
        .order_by(desc(models.Tournament.id))
        .execution_options(populate_existing=True)
    )
    return res.scalar_one_or_none()


async def get_or_create_active_tournament(session: AsyncSession) -> models.Tournament:
    """Faol turnirni olish, agar yo'q bo'lsa avtomatik yangi turnir ochish"""
    tourney = await get_active_tournament(session)
    if not tourney:
        count_res = await session.execute(select(func.count(models.Tournament.id)))
        total = count_res.scalar() or 0
        tourney = models.Tournament(
            name=f"Qirol Qo'li Turniri #{total + 1}",
            status="active",
            prize_pool=25000,
            details="Qirollikning eng qudratli ritsarlari jangi! G'olibga 70% xazina va 'Qirollik Chempioni' sharafli unvoni beriladi.",
            created_at=datetime.utcnow(),
        )
        session.add(tourney)
        await session.commit()
        tourney = await get_active_tournament(session)
    return tourney


async def enter_tournament(
    session: AsyncSession,
    user_id: int,
    use_champion: bool = False,
) -> Tuple[bool, str]:
    """Turnirga qatnashish (Kirish to'lovi: 2,000 Oltin)"""
    tourney = await get_or_create_active_tournament(session)
    if not tourney:
        return False, "❌ Ayni paytda faol ritsarlar turniri mavjud emas."

    user_res = await session.execute(select(models.User).where(models.User.id == user_id))
    user = user_res.scalar_one_or_none()
    if not user:
        return False, "❌ O'yinchi topilmadi."

    # Allaqachon qatnashayotganini tekshirish
    part_res = await session.execute(
        select(models.TournamentParticipant).where(
            models.TournamentParticipant.tournament_id == tourney.id,
            models.TournamentParticipant.user_id == user.id,
        )
    )
    if part_res.scalar_one_or_none():
        return False, "❌ Siz allaqachon ushbu turnirga qatnashgansiz!"

    fee = 2000
    if user.gold < fee:
        return False, f"❌ Turnirga kirish to'lovi uchun {fee:,}💰 Oltin kerak! (Sizda: {user.gold:,}💰)"

    user.gold -= fee
    tourney.prize_pool += fee

    # Jangchi nomi va kuchi
    fighter_name = user.username or user.full_name or f"Ritsar #{user.id}"
    fighter_power = 120 + min(80, (user.prestige // 25))

    if use_champion:
        army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
        army = army_res.scalar_one_or_none()
        if army and army.champion and army.champion in LEGENDARY_CHAMPIONS:
            champ_data = LEGENDARY_CHAMPIONS[army.champion]
            fighter_name = f"{champ_data['emoji']} {champ_data['name']} (Sarkarda)"
            champ_powers = {
                "jaime_lannister": 240,
                "oberyn_martell": 235,
                "arya_stark": 230,
                "jon_snow": 225,
                "brienne_tarth": 220,
            }
            fighter_power = champ_powers.get(army.champion, 210)

    part = models.TournamentParticipant(
        tournament_id=tourney.id,
        user_id=user.id,
        fighter_name=fighter_name,
        fighter_power=fighter_power,
        joined_at=datetime.utcnow(),
    )
    session.add(part)
    await session.commit()

    return True, (
        f"🏇⚔️ **TURNIRGA QO'SHILDINGIZ!**\n\n"
        f"Jangchi: **{fighter_name}**\n"
        f"Jang kuchi: **{fighter_power}** quvvat\n"
        f"💰 Xazinaga +{fee:,} Oltin qo'shildi. Umumiy Jamg'arma: **{tourney.prize_pool:,}** Oltin!\n\n"
        f"G'oliblik sari omad yor bo'lsin!"
    )


async def place_tournament_bet(
    session: AsyncSession,
    user_id: int,
    participant_id: int,
    bet_gold: int,
) -> Tuple[bool, str]:
    """Turnir ishtirokchisiga stavka tikish (500 - 5,000 Oltin)"""
    if bet_gold < 500 or bet_gold > 5000:
        return False, "❌ Stavka miqdori 500 dan 5,000 Oltin oralig'ida bo'lishi kerak."

    tourney = await get_or_create_active_tournament(session)
    if not tourney:
        return False, "❌ Faol turnir topilmadi."

    user_res = await session.execute(select(models.User).where(models.User.id == user_id))
    user = user_res.scalar_one_or_none()
    if not user:
        return False, "❌ O'yinchi topilmadi."

    if user.gold < bet_gold:
        return False, f"❌ Stavka uchun {bet_gold:,}💰 Oltin kerak! (Sizda: {user.gold:,}💰)"

    # Ishtirokchini tekshirish
    part = await session.get(models.TournamentParticipant, participant_id)
    if not part or part.tournament_id != tourney.id:
        return False, "❌ Bunday ishtirokchi mavjud emas."

    # Avvalgi stavka bormi?
    existing_bet = await session.execute(
        select(models.TournamentBet).where(
            models.TournamentBet.tournament_id == tourney.id,
            models.TournamentBet.user_id == user.id,
            models.TournamentBet.participant_id == participant_id,
        )
    )
    if existing_bet.scalar_one_or_none():
        return False, "❌ Siz ushbu jangchiga allaqachon stavka tikgansiz!"

    user.gold -= bet_gold
    tourney.prize_pool += bet_gold

    new_bet = models.TournamentBet(
        tournament_id=tourney.id,
        user_id=user.id,
        participant_id=participant_id,
        bet_gold=bet_gold,
        status="placed",
        created_at=datetime.utcnow(),
    )
    session.add(new_bet)
    await session.commit()

    return True, (
        f"💰🎯 **STAVKA QABUL QILINDI!**\n\n"
        f"Jangchi: **{part.fighter_name}**\n"
        f"Tikilgan miqdor: **{bet_gold:,}** Oltin\n"
        f"Kutilayotgan yutuq: **{int(bet_gold * 1.8):,}** Oltin (1.8x)\n"
        f"Turnir jamg'armasi: **{tourney.prize_pool:,}** Oltin!"
    )


async def resolve_tournament(session: AsyncSession, bot_app=None) -> Tuple[bool, str]:
    """Turnirni yakunlash va g'oliblarni taqdirlash"""
    from core.battle_engine import resolve_tourney_duel

    tourney = await get_active_tournament(session)
    if not tourney:
        return False, "❌ Faol turnir topilmadi."

    parts = list(tourney.participants)

    # Agar kamida 2 ishtirokchi bo'lmasa, turnirga afsonaviy NPC ritsarlar qo'shiladi
    npc_knights = [
        {"name": "🛡️ Ser Barristan Selmy (Jasur)", "power": 230},
        {"name": "⚔️ Ser Gregor Clegane (Tog')", "power": 240},
        {"name": "🗡️ Ser Arthur Dayne (Tong Qilichi)", "power": 250},
        {"name": "🐎 Ser Loras Tyrell (Gullar Ritsari)", "power": 215},
    ]
    while len(parts) < 2:
        npc = npc_knights.pop(0)
        npc_part = models.TournamentParticipant(
            tournament_id=tourney.id,
            user_id=tourney.winner_user_id or 1,  # Tizim ishtirokchisi
            fighter_name=npc["name"],
            fighter_power=npc["power"],
        )
        session.add(npc_part)
        tourney.prize_pool += 2000
        parts.append(npc_part)

    # Turnir duellari: barcha ishtirokchilarni juftlab saralash
    duel_chronicle = []
    current_round_fighters = [
        {"id": p.id, "user_id": p.user_id, "name": p.fighter_name, "power": p.fighter_power, "obj": p}
        for p in parts
    ]

    round_num = 1
    while len(current_round_fighters) > 1:
        next_round_fighters = []
        random.shuffle(current_round_fighters)
        duel_chronicle.append(f"\n🏆 **{round_num}-BOSQICH JANGILARI:**")

        for i in range(0, len(current_round_fighters), 2):
            if i + 1 < len(current_round_fighters):
                f1 = current_round_fighters[i]
                f2 = current_round_fighters[i + 1]
                duel_res = resolve_tourney_duel(f1, f2)
                winner = duel_res["winner"]
                loser = duel_res["loser"]
                duel_chronicle.append(
                    f"⚔️ **{f1['name']}** VS **{f2['name']}**\n"
                    f"{duel_res['log']}\n"
                    f"🏅 G'olib: **{winner['name']}** ({duel_res['score_winner']}:{duel_res['score_loser']})\n"
                )
                next_round_fighters.append(winner)
            else:
                # Toq ishtirokchi keyingi bosqichga o'tadi
                next_round_fighters.append(current_round_fighters[i])
                duel_chronicle.append(f"• **{current_round_fighters[i]['name']}** qur'a bo'yicha to'g'ridan-to'g'ri o'tdi.")

        current_round_fighters = next_round_fighters
        round_num += 1

    champion = current_round_fighters[0]
    first_prize = int(tourney.prize_pool * 0.70)
    second_prize = int(tourney.prize_pool * 0.30)

    tourney.status = "completed"
    tourney.concluded_at = datetime.utcnow()
    tourney.winner_user_id = champion["user_id"]
    tourney.winner_name = champion["name"]

    # Chempion o'yinchiga mukofot
    champ_user = await session.get(models.User, champion["user_id"])
    if champ_user:
        champ_user.gold += first_prize
        champ_user.prestige += 100
        champ_user.title = "Qirollik Chempioni"

    # Stavkalarni to'lash
    bets_res = await session.execute(
        select(models.TournamentBet).where(models.TournamentBet.tournament_id == tourney.id)
    )
    all_bets = bets_res.scalars().all()
    payout_summary = []
    for bet in all_bets:
        if bet.participant_id == champion["id"]:
            bet.status = "won"
            payout = int(bet.bet_gold * 1.8)
            bet.payout_gold = payout
            bet_user = await session.get(models.User, bet.user_id)
            if bet_user:
                bet_user.gold += payout
                payout_summary.append(f"• {bet_user.username or bet_user.full_name}: +{payout:,}💰")
        else:
            bet.status = "lost"

    payout_text = "\n".join(payout_summary) if payout_summary else "• Hech kim stavka yutib olmadi."

    full_report = (
        f"👑🏆 **QIROL QO'LI RITSARLAR TURNIRI YAKUNLANDI!**\n\n"
        f"🥇 **QIROLLIK CHEMPIONI:** {champion['name']}\n"
        f"💰 1-O'rin mukofoti: **+{first_prize:,}** Oltin va **+100** Nufuz!\n"
        f"👑 Sharafli unvon: **Qirollik Chempioni**\n\n"
        f"{''.join(duel_chronicle)}\n\n"
        f"🎰 **YUTUQLI STAVKALAR TO'LOVI (1.8x):**\n"
        f"{payout_text}\n\n"
        f"🏁 Turnir yakunlandi! Barcha mukofotlar va stavkalar topshirildi.\n"
        f"Yangi navbatdagi ritsarlar turniri ochildi — buyruq /tourney orqali kirishingiz mumkin!"
    )
    tourney.details = full_report

    # Navbatdagi faol turnirni darhol ochish
    count_res = await session.execute(select(func.count(models.Tournament.id)))
    total_tourneys = count_res.scalar() or 0
    next_tourney = models.Tournament(
        name=f"Qirol Qo'li Turniri #{total_tourneys + 1}",
        status="active",
        prize_pool=25000,
        details="Yangi ritsarlar turniri boshlandi! Ritsarlaringizni maydonga tushiring yoki omadingizni sinab stavka tiking!",
        created_at=datetime.utcnow(),
    )
    session.add(next_tourney)
    await session.commit()

    if bot_app:
        users_res = await session.execute(select(models.User.telegram_id))
        all_ids = users_res.scalars().all()
        for tg_id in all_ids:
            try:
                await bot_app.bot.send_message(
                    chat_id=tg_id,
                    text=full_report,
                    parse_mode="Markdown"
                )
            except Exception:
                try:
                    await bot_app.bot.send_message(chat_id=tg_id, text=full_report)
                except Exception:
                    pass

    return True, full_report


async def admin_start_tournament(
    session: AsyncSession,
    name: Optional[str] = None,
    prize_pool: int = 25000,
    bot_app=None,
) -> Tuple[bool, str]:
    """Admin tomonidan yangi ritsarlar turnirini e'lon qilish va boshlash"""
    active = await get_active_tournament(session)
    if active:
        return False, f"❌ Ayni paytda allaqachon faol turnir mavjud: '{active.name}'! Avval uni yakunlash lozim."

    count_res = await session.execute(select(func.count(models.Tournament.id)))
    total_tourneys = count_res.scalar() or 0
    t_name = name or f"Qirol Qo'li Turniri #{total_tourneys + 1}"

    new_tourney = models.Tournament(
        name=t_name,
        status="active",
        prize_pool=prize_pool,
        details="Yangi ritsarlar turniri boshlandi! Ritsarlaringizni maydonga tushiring yoki omadingizni sinab stavka tiking!",
        created_at=datetime.utcnow(),
    )
    session.add(new_tourney)
    await session.commit()

    broadcast_msg = (
        f"🏇🏆 **QIROLNING FARMONI: YANGI RITSARLAR TURNIRI BOSHLANDI!**\n\n"
        f"Arena: **{t_name}**\n"
        f"💰 Boshlang'ich Jamg'arma: **{prize_pool:,}** Oltin\n\n"
        f"Vesterosning barcha dovyurak ritsarlari va jangchilari arena maydoniga chorlanadi! Shon-sharaf, nufuz va boylik uchun kurashing!\n\n"
        f"👉 /tourney buyrug'i orqali arenaga kiring va o'z omadingizni sinang!"
    )

    if bot_app:
        users_res = await session.execute(select(models.User.telegram_id))
        all_ids = users_res.scalars().all()
        for tg_id in all_ids:
            try:
                await bot_app.bot.send_message(
                    chat_id=tg_id,
                    text=broadcast_msg,
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    return True, f"✅ Yangi turnir muvaffaqiyatli boshlandi: **{t_name}** (Jamg'arma: {prize_pool:,}💰) va barcha o'yinchilarga e'lon qilindi!"


async def check_and_resolve_weekly_tournament(session: AsyncSession, bot_app=None) -> None:
    """Turnir vaqti tugashini tekshirish (Turnir boshlanishi va yakuni faqat admin tomonidan boshqariladi)"""
    pass


# ============================================================
# 27. SAVDO KARVONLARI VA PISTIRMALAR (TRADE CARAVANS CRUD)
# ============================================================

async def dispatch_trade_caravan(
    session: AsyncSession,
    user_id: int,
    origin_territory_id: int,
    destination_territory_id: int,
    resource_type: str,
    amount: int,
    escort_cav: int,
    escort_inf: int,
) -> Tuple[bool, str]:
    """Savdo karvonini yo'lga chiqarish (3 daqiqalik marshrut)"""
    if resource_type not in ["food", "iron"]:
        return False, "❌ Karvon faqat Oziq-ovqat (food) yoki Temir (iron) tashiydi."

    valid_tiers = {
        5000: 2500,
        10000: 5500,
        20000: 12000,
    }
    if amount not in valid_tiers:
        return False, "❌ Karvon yuki miqdori 5,000, 10,000 yoki 20,000 bo'lishi kerak."

    user_res = await session.execute(select(models.User).where(models.User.id == user_id))
    user = user_res.scalar_one_or_none()
    if not user:
        return False, "❌ O'yinchi topilmadi."

    await check_and_reset_daily_limits(session, user)

    # Kunlik karvon jo'natish limiti (kuniga 2 ta)
    if getattr(user, "daily_caravan_send_count", 0) >= 2:
        return False, "❌ Kunlik karvon jo'natish limitingiz (2/2) tugagan! Ertaga yana karvon jo'natishingiz mumkin."

    # Resurs yetarliligini tekshirish
    user_res_val = getattr(user, resource_type, 0)
    if user_res_val < amount:
        return False, f"❌ Sizda {amount:,} ta {resource_type.capitalize()} yetarli emas! (Mavjud: {user_res_val:,})"

    # Soqchilar yetarliligini tekshirish
    army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
    army = army_res.scalar_one_or_none()
    if not army or army.cavalry < escort_cav or army.infantry < escort_inf:
        return False, "❌ Karvonni himoya qilish uchun armiyangizda yetarli askarlar mavjud emas."

    # Faol harakatdagi karvonlar soni limiti (max 2)
    active_res = await session.execute(
        select(models.TradeCaravan).where(
            models.TradeCaravan.owner_user_id == user.id,
            models.TradeCaravan.status == "moving",
        )
    )
    if len(active_res.scalars().all()) >= 2:
        return False, "❌ Sizda ayni paytda yo'lda bo'lgan 2 ta faol karvon mavjud. Yangisini chiqarishdan oldin ularning yetib borishini kuting!"

    # Resurs va askarlarni yechish
    if resource_type == "food":
        user.food -= amount
    else:
        user.iron -= amount

    army.cavalry -= escort_cav
    army.infantry -= escort_inf
    user.daily_caravan_send_count = getattr(user, "daily_caravan_send_count", 0) + 1

    now = datetime.utcnow()
    # 30 daqiqa yo'l vaqti (1800 soniya)
    arrival = now + timedelta(minutes=30)
    reward_gold = valid_tiers[amount]

    caravan = models.TradeCaravan(
        owner_user_id=user.id,
        owner_house_id=user.house_id or 1,
        origin_territory_id=origin_territory_id,
        destination_territory_id=destination_territory_id,
        resource_type=resource_type,
        resource_amount=amount,
        expected_gold_reward=reward_gold,
        escort_cavalry=escort_cav,
        escort_infantry=escort_inf,
        departure_time=now,
        arrival_time=arrival,
        status="moving",
    )
    session.add(caravan)
    await session.commit()

    return True, (
        f"🐪📦 **SAVDO KARVONI YO'LGA CHIQDI!**\n\n"
        f"📦 Yuk: **{amount:,}** {resource_type.capitalize()}\n"
        f"🛡️ Soqchilar: **{escort_cav}** Otliq, **{escort_inf}** Piyoda\n"
        f"💰 Manzilga yetgach kutilayotgan foyda: **+{reward_gold:,}** Oltin\n"
        f"⏱️ Yetib borish vaqti: **30 daqiqa**\n"
        f"📊 Bugungi karvonlaringiz: **{user.daily_caravan_send_count}/2** ta\n\n"
        f"⚠️ Eslatma: Karvoningiz yo'lda raqiblar tomonidan talanishi mumkin! Kuchli soqchilar xavfsizlik kafolatidir."
    )


async def get_active_trade_caravans(
    session: AsyncSession,
    user_id: Optional[int] = None,
) -> List[models.TradeCaravan]:
    """Yo'ldagi barcha faol karvonlarni olish"""
    stmt = (
        select(models.TradeCaravan)
        .where(models.TradeCaravan.status == "moving")
        .options(
            selectinload(models.TradeCaravan.owner),
            selectinload(models.TradeCaravan.owner_house),
            selectinload(models.TradeCaravan.origin_territory),
            selectinload(models.TradeCaravan.destination_territory),
        )
        .order_by(models.TradeCaravan.arrival_time.asc())
    )
    if user_id:
        stmt = stmt.where(models.TradeCaravan.owner_user_id == user_id)
    res = await session.execute(stmt)
    return res.scalars().all()


async def raid_trade_caravan(
    session: AsyncSession,
    user_id: int,
    caravan_id: int,
    raid_inf: int,
    raid_cav: int,
    bot_app=None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Karvonga qaroqchilik pistirmasi uyushtirish"""
    from core.battle_engine import calculate_caravan_raid

    raider_res = await session.execute(select(models.User).where(models.User.id == user_id))
    raider = raider_res.scalar_one_or_none()
    if not raider:
        return False, "❌ Qaroqchi o'yinchi topilmadi.", {}

    await check_and_reset_daily_limits(session, raider)

    # Kunlik qaroqchilik/pistirma limiti (kuniga 2 ta)
    if getattr(raider, "daily_caravan_raid_count", 0) >= 2:
        return False, "❌ Kunlik qaroqchilik/pistirma limitingiz (2/2) tugagan! Ertaga yana urinib ko'rishingiz mumkin.", {}

    if raid_inf < 10 and raid_cav < 10:
        return False, "❌ Pistirma uchun kamida 10 ta piyoda yoki 10 ta otliq kerak!", {}

    caravan = await session.get(models.TradeCaravan, caravan_id)
    if not caravan or caravan.status != "moving":
        return False, "❌ Ushbu karvon allaqachon manzilga yetgan yoki talangan!", {}

    if caravan.owner_user_id == user_id:
        return False, "❌ O'z karvoningizga qaroqchilik qila olmaysiz!", {}

    if raider.house_id and raider.house_id == caravan.owner_house_id:
        return False, "❌ O'z xonadoningiz karvoniga hujum qila olmaysiz!", {}

    army_res = await session.execute(select(models.Army).where(models.Army.user_id == raider.id))
    army = army_res.scalar_one_or_none()
    if not army or army.infantry < raid_inf or army.cavalry < raid_cav:
        return False, "❌ Armiyangizda pistirma uchun yetarli askarlar yo'q!", {}

    # Pistirma limitini oshirish
    raider.daily_caravan_raid_count = getattr(raider, "daily_caravan_raid_count", 0) + 1

    # Jangni hisoblash
    raider_troops = {"infantry": raid_inf, "cavalry": raid_cav}
    escort_troops = {"infantry": caravan.escort_infantry, "cavalry": caravan.escort_cavalry}
    raider_champion = getattr(army, "champion", None)

    battle_res = calculate_caravan_raid(raider_troops, escort_troops, raider_champion)

    # Qaroqchi yo'qotishlari
    army.infantry -= battle_res["raider_losses"]["infantry"]
    army.cavalry -= battle_res["raider_losses"]["cavalry"]

    # Karvon soqchilari yo'qotishlari
    caravan.escort_infantry = battle_res["remaining_escort"]["infantry"]
    caravan.escort_cavalry = battle_res["remaining_escort"]["cavalry"]

    owner_res = await session.execute(select(models.User).where(models.User.id == caravan.owner_user_id))
    owner = owner_res.scalar_one_or_none()

    if battle_res["winner"] == "raiders":
        # Qaroqchilar g'olib - karvon talandi
        caravan.status = "looted"
        caravan.raider_user_id = raider.id
        caravan.raid_report = battle_res["details"]

        stolen_res = int(caravan.resource_amount * 0.70)
        bounty_gold = 1000

        if caravan.resource_type == "food":
            raider.food += stolen_res
        else:
            raider.iron += stolen_res

        raider.gold += bounty_gold
        raider.prestige += 20

        msg = (
            f"⚔️💰 **PISTIRMA MUVAFFAQIYATLI BO'LDI!**\n\n"
            f"Siz savdo karvonini tor-mor keltirib, yuklarni talon-toroj qildingiz!\n\n"
            f"📦 O'lja: **+{stolen_res:,}** {caravan.resource_type.capitalize()}\n"
            f"💰 O'lja Oltin: **+{bounty_gold:,}** Oltin\n"
            f"🎖️ Nufuz: **+20** ball\n"
            f"📉 Yo'qotishlaringiz: -{battle_res['raider_losses']['infantry']} Piyoda, -{battle_res['raider_losses']['cavalry']} Otliq.\n"
            f"📊 Bugungi pistirma limitingiz: **{raider.daily_caravan_raid_count}/2** ta"
        )

        if bot_app and owner and owner.telegram_id:
            try:
                await bot_app.bot.send_message(
                    chat_id=owner.telegram_id,
                    text=(
                        f"🚨🐪 **QAROQCHILIK! SAVDO KARVONINGIZ TALANDI!**\n\n"
                        f"Vesteros yo'llarida pistirmaga tushgan karvoningiz dushman qaroqchilari tomonidan talandi!\n"
                        f"Soqchilar halok bo'ldi yoki tarqaldi, yuklarning katta qismi o'g'irlab ketildi!"
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                pass
    else:
        # Soqchilar hujumni qaytardi
        msg = (
            f"🛡️❌ **PISTIRMA MUVAFFAQIYATSIZ TUGADI!**\n\n"
            f"Karvon soqchilari mohirona mudofaa tashkil qilib, hujumingizni qaytardi!\n\n"
            f"📉 Yo'qotishlaringiz: -{battle_res['raider_losses']['infantry']} Piyoda, -{battle_res['raider_losses']['cavalry']} Otliq.\n"
            f"📊 Bugungi pistirma limitingiz: **{raider.daily_caravan_raid_count}/2** ta"
        )

    await session.commit()
    return True, msg, battle_res


# ============================================================
# 28. DINAMIK FASLLAR VA OB-HAVO (DYNAMIC WEATHER CRUD)
# ============================================================

WEATHER_TYPES = {
    "severe_winter": {
        "name": "Qattiq Qish (Severe Winter)",
        "emoji": "❄️",
        "description": "Shimol qal'alari mudofaasi +15%, ammo qattiq ayoz tufayli armiyalarning oziq-ovqat sarfi +25% oshadi.",
    },
    "summer_abundance": {
        "name": "Yozgi Mo'l-ko'llik (Summer Abundance)",
        "emoji": "☀️",
        "description": "Westeros bo'ylab serquyosh issiq. Hosildorlik +50%, shaharlar va qal'alardan tushadigan o'lpon +25% oshadi.",
    },
    "storm_season": {
        "name": "Bo'ron Fasli (Storm Season)",
        "emoji": "⛈️",
        "description": "Kuchli yomg'ir va shiddatli shamol kamonchilar aniqligini -15% ga pasaytiradi, yurishlar +20% sekinlashadi, ammo qamal trebushetlari devorlarga +10% kuchliroq zarba beradi.",
    },
    "wild_winds": {
        "name": "Vahshiy Shamollar (Wild Winds)",
        "emoji": "🌪️",
        "description": "Tog'lardan qadimiy qudratli bo'ron shamollari esmoqda. Ajdarlarning drakarys alangasi va parvoz quvvati +25% ga kuchayadi!",
    },
}

async def get_current_weather(session: AsyncSession) -> Dict[str, Any]:
    """Hozirgi Westeros ob-havosi ma'lumotlarini olish"""
    res = await session.execute(
        select(models.EventState).where(models.EventState.event_name == "world_weather")
    )
    ev = res.scalar_one_or_none()
    if not ev or not ev.data_json:
        return {
            "weather_type": "severe_winter",
            "name": "Qattiq Qish (Severe Winter)",
            "emoji": "❄️",
            "description": "Shimolda mudofaa +15%, oziq-ovqat sarfi +25%.",
            "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat(),
        }

    try:
        data = json.loads(ev.data_json)
        w_type = data.get("weather_type", "severe_winter")
        info = WEATHER_TYPES.get(w_type, WEATHER_TYPES["severe_winter"])
        data["name"] = info["name"]
        data["emoji"] = info["emoji"]
        data["description"] = info["description"]
        return data
    except Exception:
        return {
            "weather_type": "severe_winter",
            "name": "Qattiq Qish (Severe Winter)",
            "emoji": "❄️",
            "description": "Shimolda mudofaa +15%, oziq-ovqat sarfi +25%.",
            "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat(),
        }


async def rotate_world_weather(
    session: AsyncSession,
    new_weather_type: Optional[str] = None,
    bot_app=None,
) -> Dict[str, Any]:
    """Westeros ob-havosini yangilash / aylantirish"""
    types_list = list(WEATHER_TYPES.keys())
    if not new_weather_type or new_weather_type not in WEATHER_TYPES:
        new_weather_type = random.choice(types_list)

    now = datetime.utcnow()
    expires = now + timedelta(days=7)
    weather_info = WEATHER_TYPES[new_weather_type]

    res = await session.execute(
        select(models.EventState).where(models.EventState.event_name == "world_weather")
    )
    ev = res.scalar_one_or_none()
    new_data = {
        "weather_type": new_weather_type,
        "name": weather_info["name"],
        "description": weather_info["description"],
        "updated_at": now.isoformat(),
        "expires_at": expires.isoformat(),
    }

    if not ev:
        ev = models.EventState(
            event_name="world_weather",
            data_json=json.dumps(new_data),
            is_active=True,
        )
        session.add(ev)
    else:
        ev.data_json = json.dumps(new_data)
        ev.is_active = True

    await session.commit()

    if bot_app:
        announcement = (
            f"🌤️📜 **WESTEROS OB-HAVO VA FASLI O'ZGARDI!**\n\n"
            f"{weather_info['emoji']} Yangi Fasl: **{weather_info['name']}**\n\n"
            f"📖 *Ta'siri:* {weather_info['description']}\n\n"
            f"⏱️ Ushbu fasl keyingi **7 kun** davomida butun qit'a uzra hukm suradi!"
        )
        users_res = await session.execute(select(models.User.telegram_id))
        all_ids = users_res.scalars().all()
        for tg_id in all_ids:
            try:
                await bot_app.bot.send_message(
                    chat_id=tg_id,
                    text=announcement,
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    return new_data


async def check_and_rotate_weather(session: AsyncSession, bot_app=None) -> None:
    """Agar ob-havo muddati (7 kun) o'tgan bo'lsa avtomatik aylantirish"""
    weather = await get_current_weather(session)
    exp_str = weather.get("expires_at")
    if not exp_str:
        return

    try:
        exp_dt = datetime.fromisoformat(exp_str)
        if datetime.utcnow() >= exp_dt:
            await rotate_world_weather(session, bot_app=bot_app)
    except Exception:
        pass










