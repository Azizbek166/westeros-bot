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


async def get_user_with_relations(session: AsyncSession, telegram_id: int) -> Optional[models.User]:
    """O'yinchini xonadoni, armiyasi va personajlari bilan birga olish"""
    result = await session.execute(
        select(models.User).where(models.User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        # Aloqalarni yuklash
        await session.refresh(user, ["house", "army", "characters"])
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
    """O'yinchi xonadondan chiqishi"""
    user = await session.get(models.User, user_id)
    if not user or not user.house_id:
        return False, "❌ Siz biron xonadonga a'zo emassiz."

    house = await session.get(models.House, user.house_id)
    if house and house.lord_user_id == user.telegram_id:
        house.lord_user_id = None
        house.lord_elected_at = datetime.utcnow()

    # Ovozlarini tozalash
    await session.execute(
        delete(models.HouseVote).where(
            (models.HouseVote.voter_user_id == user.id) | (models.HouseVote.candidate_user_id == user.id)
        )
    )

    # HouseMember dan o'chirish
    await session.execute(
        delete(models.HouseMember).where(models.HouseMember.user_id == user.id)
    )

    # Foydalanuvchini xonadondan ozod qilish
    user.house_id = None
    user.rank = "member"

    # Eski personajni tozalash (yangi xonadonga kirganda yangi qahramon tanlanadi)
    await session.execute(
        delete(models.Character).where(models.Character.user_id == user.id)
    )

    await session.commit()
    return True, "✅ Siz xonadondan chiqdingiz. Endi yangi xonadon tanlashingiz mumkin!"


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
        await session.refresh(territory, ["owner_house"])
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
    user = await session.get(models.User, user_id)
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
    return True


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
) -> models.BattleMarch:
    """Yangi harbiy yurishni ro'yxatga olish"""
    # O'yinchining armiyasidan yuborilgan qismini ayirish
    army_res = await session.execute(select(models.Army).where(models.Army.user_id == attacker_user_id))
    army = army_res.scalar_one_or_none()
    if army:
        army.infantry = max(0, army.infantry - infantry)
        army.archers = max(0, army.archers - archers)
        army.cavalry = max(0, army.cavalry - cavalry)
        army.spearmen = max(0, army.spearmen - spearmen)
        army.special_troops = max(0, army.special_troops - special_troops)

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
        dragon_tactic=dragon_tactic,
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
    user = await session.get(models.User, user_id)
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
        cand = await session.get(models.User, candidate_user_id)
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
    user = await session.get(models.User, user_id)
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
    user = await session.get(models.User, user_id)
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
    sender = await session.get(models.User, sender_user_id)
    lord = await session.get(models.User, lord_user_id)
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

    target_user = await session.get(models.User, target_user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
    territory = await session.get(models.Territory, target_territory_id)
    if not user or not territory:
        return False, "Foydalanuvchi yoki qal'a topilmadi.", {}

    if not user.house_id:
        return False, "❌ Qal'ani himoya qilish uchun avval biror xonadonga a'zo bo'ling!", {}

    is_own = (territory.owner_house_id == user.house_id)
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

    if not is_own and not is_ally:
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

    army.infantry -= s_inf
    army.archers -= s_arc
    army.cavalry -= s_cav
    army.spearmen -= s_sp

    territory.garrison_infantry = (territory.garrison_infantry or 0) + s_inf
    territory.garrison_archers = (territory.garrison_archers or 0) + s_arc
    territory.garrison_cavalry = (territory.garrison_cavalry or 0) + s_cav
    territory.garrison_spearmen = (territory.garrison_spearmen or 0) + s_sp

    user.prestige = (user.prestige or 0) + max(10, tot_s // 5)
    await session.commit()
    sent_dict = {
        "infantry": s_inf,
        "archers": s_arc,
        "cavalry": s_cav,
        "spearmen": s_sp,
        "total": tot_s,
    }
    return True, f"✅ Qal'a mudofaasiga +{tot_s:,} askar joylashtirildi! (+{max(10, tot_s // 5)} Prestige)", sent_dict


async def withdraw_castle_reinforcements(
    session: AsyncSession,
    user_id: int,
    territory_id: int,
    count: Optional[int] = None,
    withdraw_all: bool = False,
) -> Tuple[bool, str, Dict[str, int]]:
    """Qal'a garnizonidan askarlarni mutanosib ravishda o'yinchining shaxsiy armiyasiga qaytarib olish"""
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
    territory = await session.get(models.Territory, territory_id)
    if not user or not territory:
        return False, "Foydalanuvchi yoki qal'a topilmadi.", {}

    if territory.owner_house_id != user.house_id:
        return False, "❌ Siz faqat o'z xonadoningizga tegishli qal'alar garnizonidan askar qaytara olasiz!", {}

    army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
    army = army_res.scalar_one_or_none()
    if not army:
        return False, "Armiya topilmadi.", {}

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

    territory.garrison_infantry -= w_inf
    territory.garrison_archers -= w_arc
    territory.garrison_cavalry -= w_cav
    territory.garrison_spearmen -= w_sp

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


async def station_dragon_in_castle(session: AsyncSession, user_id: int, territory_id: int) -> Tuple[bool, str]:
    """Ajdarni qal'a mudofaasiga joylashtirish"""
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
    territory = await session.get(models.Territory, territory_id)
    if not user or not territory:
        return False, "Foydalanuvchi yoki qal'a topilmadi."

    if not user.house_id or territory.owner_house_id != user.house_id:
        return False, "❌ Faqat o'z xonadoningiz nazoratidagi qal'aga ajdar joylashtira olasiz!"

    dragons = await get_user_dragons(session, user.id)
    combat_dragons = [d for d in dragons if d.stage in ["baby", "adult"]]
    if not combat_dragons:
        if any(d.stage == "egg" for d in dragons):
            return False, "❌ Sizdagi ajdar hali tuxum holatida! Qal'ani himoya qilish uchun avval tuxumni ochiring (/dragons)."
        return False, "❌ Sizda ajdar yo'q! Avval /dragons bo'limidan ajdar sotib oling."

    dragon = max(combat_dragons, key=lambda d: d.power)

    reinf_data = {}
    if territory.reinforcements_json:
        try:
            reinf_data = json.loads(territory.reinforcements_json)
        except Exception:
            reinf_data = {}

    current_stationed = reinf_data.get("stationed_dragon")
    if current_stationed and current_stationed.get("dragon_id") == dragon.id:
        return False, f"⚠️ Ajdaringiz ({dragon.name}) allaqachon ushbu qal'a osmonida qo'riqchilik qilmoqda!"

    char_res = await session.execute(select(models.Character.name).where(models.Character.user_id == user.id).limit(1))
    char_name = char_res.scalar_one_or_none() or user.full_name
    reinf_data["stationed_dragon"] = {
        "user_id": user.id,
        "user_name": char_name,
        "dragon_id": dragon.id,
        "dragon_name": dragon.name,
        "power": dragon.power,
        "stationed_at": datetime.utcnow().isoformat(),
    }
    territory.reinforcements_json = json.dumps(reinf_data)
    user.prestige += 50
    await session.commit()
    return True, f"🐉🔥 Ulug'vor {dragon.name} (Kuch: {dragon.power}) {territory.name} qal'asi mudofaasiga joylashtirildi! (+50 Prestige)"


async def recall_dragon_from_castle(session: AsyncSession, user_id: int, territory_id: int) -> Tuple[bool, str]:
    """Ajdarni qal'a mudofaasidan o'z uyasiga qaytarish"""
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
    territory = await session.get(models.Territory, territory_id)
    if not user or not territory:
        return False, "Foydalanuvchi yoki qal'a topilmadi."

    if not territory.reinforcements_json:
        return False, "Qal'ada joylashtirilgan ajdar yo'q."

    try:
        reinf_data = json.loads(territory.reinforcements_json)
    except Exception:
        reinf_data = {}

    stationed = reinf_data.get("stationed_dragon")
    if not stationed:
        return False, "Qal'ada joylashtirilgan ajdar topilmadi."

    house = await session.get(models.House, user.house_id) if user.house_id else None
    is_lord = house and house.lord_user_id == user.telegram_id
    if stationed.get("user_id") != user.id and not is_lord:
        return False, "❌ Bu ajdar sizga tegishli emas!"

    dragon_name = stationed.get("dragon_name", "Ajdar")
    del reinf_data["stationed_dragon"]
    territory.reinforcements_json = json.dumps(reinf_data)
    await session.commit()
    return True, f"🐉 {dragon_name} qal'a mudofaasidan o'z uyasiga eson-omon qaytarildi."


def get_stationed_dragon_info(territory: models.Territory) -> Optional[Dict[str, Any]]:
    """Qal'ada joylashtirilgan ajdar haqida ma'lumot"""
    if not territory or not territory.reinforcements_json:
        return None
    try:
        data = json.loads(territory.reinforcements_json)
        return data.get("stationed_dragon")
    except Exception:
        return None


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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
    if not user or not user.house_id:
        return False, "Siz hali xonadonga a'zo emassiz."

    await check_and_reset_daily_limits(session, user)
    if user.daily_donation_count >= 2:
        return False, "❌ Siz bugungi 2 ta ehson limitingizdan foydalanib bo'ldingiz! Ertaga yana xazinaga ehson qilishingiz mumkin."

    if user.gold < gold or user.food < food or user.iron < iron:
        return False, "Xazinaga topshirish uchun resurslaringiz yetarli emas!"

    house = await session.get(models.House, user.house_id)
    if not house:
        return False, "Xonadon topilmadi."

    # Foydalanuvchidan yechish
    user.gold -= gold
    user.food -= food
    user.iron -= iron
    user.daily_donation_count += 1

    # Xonadon xazinasiga qo'shish
    house.gold += gold
    house.food += food
    house.iron += iron

    # Nufuz (Prestige) hisoblash (har 100 tanga/temir yoki 200 oziq-ovqat uchun +2 prestige)
    prestige_gain = (gold // 50) + (iron // 50) + (food // 100) + 5
    user.prestige += prestige_gain
    house.prestige += (prestige_gain // 2)

    # HouseMember dagi hissani yangilash
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
    return True, f"✅ Xonadon g'aznasiga ehson qabul qilindi ({user.daily_donation_count}/2)! (+{prestige_gain}🏆 Prestige berildi)"


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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
    actual_user_id = user.id if user else user_id

    res = await session.execute(
        select(models.Dragon).where(models.Dragon.user_id == actual_user_id).order_by(models.Dragon.id)
    )
    return res.scalars().all()


async def get_user_dragon(session: AsyncSession, user_id: int, dragon_id: Optional[int] = None) -> Optional[models.Dragon]:
    """Foydalanuvchining asosiy yoki tanlangan ajdarini olish"""
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
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
    user = await session.get(models.User, user_id)
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
    user = await session.get(models.User, user_id)
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
        u = await session.get(models.User, c.user_id)
        if u:
            char_res = await session.execute(select(models.Character.name).where(models.Character.user_id == u.id))
            char_name = char_res.scalar_one_or_none() or u.full_name
            h = await session.get(models.House, u.house_id) if u.house_id else None
            h_name = f"{h.emoji} {h.name}" if h else "Vesteros"
            results.append((char_name, h_name, c.damage_dealt, c.attacks_count))
    return results


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
    user = await session.get(models.User, user_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_id)
    if not user:
        return {"success": False, "error": "Foydalanuvchi topilmadi."}

    if bet_gold > 0 and user.gold < bet_gold:
        return {"success": False, "error": f"Duel uchun kamida {bet_gold}🪙 oltin kerak!"}

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
        "Bronn": {"atk": 50, "def": 45, "tactic": "parry"},          # Boshlang'ich raqib (1-3 level yuta oladi)
        "Sandor Clegane": {"atk": 65, "def": 60, "tactic": "heavy"}, # O'rta darajali jangchi
        "Oberyn Martell": {"atk": 78, "def": 68, "tactic": "agile"}, # Kuchli mahoratli jangchi
        "Gregor Clegane": {"atk": 90, "def": 80, "tactic": "heavy"}, # Boss darajadagi Tog'
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
        if bet_gold > 0:
            user.gold += bet_gold
            outcome = f"🏆 **G'ALABA!** Sizning qilich zarbangiz {champion_name}ning mudofaasini teshib o'tdi!"
            user.prestige += 30
            user.xp += 150
        else:
            user.gold += 50
            outcome = f"🏆 **G'ALABA!** Bepul mashg'ulot jangida {champion_name} ustidan ustun keldingiz! (+50🪙 Rag'batlantiruvchi mukofot)"
            user.prestige += 15
            user.xp += 100
    else:
        if bet_gold > 0:
            user.gold = max(0, user.gold - bet_gold)
            outcome = f"💀 **MAG'LUBIYAT!** {champion_name} chaqqonlik bilan ustun keldi."
            user.xp += 40
        else:
            outcome = f"💀 **MAG'LUBIYAT!** Mashg'ulot jangida {champion_name} tajribasi ustun keldi. Oltin yo'qotilmadi!"
            user.xp += 25

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
    }


async def create_pvp_duel(
    session: AsyncSession,
    challenger_tg_or_id: int,
    opponent_target: str,
    bet_gold: int,
    tactic: str,
) -> Tuple[bool, str, Optional[models.Duel], Optional[int]]:
    """O'yinchi boshqa o'yinchiga duel taklif qiladi"""
    challenger = await session.get(models.User, challenger_tg_or_id)
    if not challenger:
        challenger = await get_user_by_telegram_id(session, challenger_tg_or_id)
    if not challenger:
        return False, "Foydalanuvchi topilmadi.", None, None

    if bet_gold > 0 and challenger.gold < bet_gold:
        return False, f"Duel uchun sizda kamida {bet_gold}🪙 oltin bo'lishi kerak!", None, None

    opponent = None
    if opponent_target.isdigit():
        target_int = int(opponent_target)
        opponent = await session.get(models.User, target_int)
        if not opponent:
            opponent = await get_user_by_telegram_id(session, target_int)
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
    user = await session.get(models.User, user_tg_or_id)
    if not user:
        user = await get_user_by_telegram_id(session, user_tg_or_id)
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

    challenger = await session.get(models.User, duel.challenger_id)
    opponent = await session.get(models.User, duel.opponent_id)
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

    challenger = await session.get(models.User, duel.challenger_id)
    duel.status = "rejected"
    await session.commit()
    return True, "Duel chaqirig'i rad etildi.", challenger.telegram_id if challenger else None


# ============================================================
# RAVEN MAIL CRUD
# ============================================================

async def send_raven(
    session: AsyncSession,
    sender_id: int,
    recipient_username_or_id: str,
    text: str,
    gold: int = 0,
) -> Tuple[bool, str, Optional[int]]:
    """Qarg'a orqali xat va oltin jo'natish"""
    sender = await session.get(models.User, sender_id)
    if not sender:
        return False, "Foydalanuvchi topilmadi.", None

    if gold > 0 and sender.gold < gold:
        return False, "Xatga biriktirish uchun yetarli oltiningiz yo'q!", None

    # Qabul qiluvchini qidirish
    recipient = None
    if recipient_username_or_id.isdigit():
        recipient = await session.get(models.User, int(recipient_username_or_id))
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

async def claim_daily_bonus(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Kunlik 24 soatlik xazina bonusi"""
    user = await session.get(models.User, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    now = datetime.utcnow()
    if user.last_daily_bonus:
        diff = (now - user.last_daily_bonus).total_seconds()
        if diff < 86400:
            remaining_hours = int((86400 - diff) // 3600)
            remaining_mins = int(((86400 - diff) % 3600) // 60)
            return False, f"⏳ Kunlik bonusni oldingiz! Yangi sovg'a {remaining_hours} soat {remaining_mins} daqiqadan so'ng beriladi."

    user.gold += 500
    user.food += 1000
    user.iron += 200
    user.prestige += 25
    user.last_daily_bonus = now
    await session.commit()
    return True, "🎁 **KUNLIK QIROL TUHFASI QABUL QILINDI!**\n\n+500🪙 Oltin\n+1,000🌾 Oziq-ovqat\n+200⛓️ Temir\n+25🏆 Prestige"


# ============================================================
# IRON MINE & MARKET CRUD
# ============================================================

IRON_MARKET_PACKS = {
    "pack_1": {"gold": 500, "iron": 300, "title": "📦 Kichik Savdo Qopi (300 temir)"},
    "pack_2": {"gold": 1000, "iron": 700, "title": "🐎 Savdo Karvoni (700 temir, +100 bonus)"},
    "pack_3": {"gold": 2500, "iron": 1900, "title": "🚢 Dengiz Savdo Kemasi (1,900 temir, +400 bonus)"},
    "pack_4": {"gold": 5000, "iron": 4200, "title": "👑 Qirollik Savdo Floti (4,200 temir, +1,200 bonus)"},
}


async def upgrade_iron_mine(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Temir konini keyingi darajaga ko'tarish"""
    user = await session.get(models.User, user_id)
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
    user = await session.get(models.User, user_id)
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



