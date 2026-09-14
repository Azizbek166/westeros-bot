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
        user.daily_limit_date = today_str
        await session.commit()


async def get_taken_character_names(session: AsyncSession, house_id: int) -> set:
    """Xonadonda allaqachon tirik o'yinchilar tomonidan tanlangan qahramonlar"""
    res = await session.execute(
        select(models.Character.name).where(
            models.Character.house_id == house_id,
            models.Character.is_alive == True,
        )
    )
    return set(res.scalars().all())


async def create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str],
    full_name: str,
    house_id: int,
    character_name: str,
) -> models.User:
    """Yangi o'yinchini ro'yxatdan o'tkazish"""
    shield_expiry = datetime.utcnow() + timedelta(hours=PEACE_SHIELD_HOURS)
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    # Xonadonda Lord bormi? Agar bo'lmasa, birinchi o'yinchi Lord (King) bo'ladi
    house = await session.get(models.House, house_id)
    is_first_lord = False
    if house and (house.lord_user_id is None or house.lord_user_id == 0):
        is_first_lord = True

    user_rank = "king" if is_first_lord else "member"

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
        name=character_name,
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
            outcome = f"🎉 Tabriklaymiz! {cand.full_name} ko'pchilik ovoz bilan xonadon Lordi (King) deb e'lon qilindi!"

    await session.commit()
    return outcome


# ============================================================
# ALLIANCE CRUD
# ============================================================

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


async def propose_alliance(session: AsyncSession, from_house_id: int, to_house_id: int) -> Tuple[bool, str]:
    """Boshqa xonadonga ittifoq taklif qilish"""
    if from_house_id == to_house_id:
        return False, "O'z xonadoningizga ittifoq taklif qila olmaysiz!"

    # Mavjud ittifoqni tekshirish
    res = await session.execute(
        select(models.Alliance).where(
            ((models.Alliance.house_a_id == from_house_id) & (models.Alliance.house_b_id == to_house_id)) |
            ((models.Alliance.house_a_id == to_house_id) & (models.Alliance.house_b_id == from_house_id))
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        if existing.status == "active":
            return False, "Ushbu xonadon bilan allaqachon faol ittifoq mavjud!"
        elif existing.status == "pending":
            return False, "Ittifoq taklifi allaqachon yuborilgan, javob kutilmoqda."
        else:
            existing.status = "pending"
            existing.house_a_id = from_house_id
            existing.house_b_id = to_house_id
            existing.created_at = datetime.utcnow()
            await session.commit()
            return True, "Ittifoq taklifi qaytadan yuborildi!"

    new_alliance = models.Alliance(
        house_a_id=from_house_id,
        house_b_id=to_house_id,
        type="alliance",
        status="pending",
    )
    session.add(new_alliance)
    await session.commit()
    return True, "Ittifoq taklifi muvaffaqiyatli yuborildi!"


async def respond_to_alliance(session: AsyncSession, alliance_id: int, accept: bool) -> bool:
    """Ittifoq taklifini qabul qilish yoki rad etish"""
    alliance = await session.get(models.Alliance, alliance_id)
    if not alliance:
        return False
    alliance.status = "active" if accept else "rejected"
    await session.commit()
    return True


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
    territory = await session.get(models.Territory, target_territory_id)
    if not user or not territory:
        return False, "Foydalanuvchi yoki qal'a topilmadi."

    army_res = await session.execute(select(models.Army).where(models.Army.user_id == user_id))
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
    return True, f"✅ Xonadon g'aznasiga ehson qabul qilindi! (+{prestige_gain}🏆 Prestige berildi)"


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


# ============================================================
# DRAGONS CRUD
# ============================================================

async def get_user_dragon(session: AsyncSession, user_id: int) -> Optional[models.Dragon]:
    """Foydalanuvchining ajdarini olish"""
    res = await session.execute(select(models.Dragon).where(models.Dragon.user_id == user_id))
    return res.scalar_one_or_none()


async def claim_dragon_egg(session: AsyncSession, user_id: int, name: str, grade: str = "B") -> Tuple[bool, str, Optional[models.Dragon]]:
    """Yangi ajdar tuxumini xarid qilish (A: 3000🪙 1500⛓️, B: 2000🪙 1000⛓️, C: 1200🪙 600⛓️)"""
    user = await session.get(models.User, user_id)
    if not user:
        return False, "Foydalanuvchi topilmadi.", None

    existing = await get_user_dragon(session, user_id)
    if existing:
        return False, "Sizda allaqachon ajdar mavjud!", None

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
        user_id=user_id,
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
    return True, f"🎉 Siz {name} ({grade} Toifa) ajdari tuxumini {cost['gold']:,}🪙 oltin va {cost['iron']:,}⛓️ temirga xarid qildingiz!", dragon


async def hatch_dragon(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Ajdar tuxumini ochirish (1,500 oziq-ovqat, 800 temir, 500 oltin talab etiladi)"""
    user = await session.get(models.User, user_id)
    dragon = await get_user_dragon(session, user_id)
    if not user or not dragon:
        return False, "Ajdar topilmadi."

    if dragon.stage != "egg":
        return False, "Sizning ajdaringiz allaqachon tuxumdan chiqqan!"

    if user.food < 1500 or user.iron < 800 or user.gold < 500:
        return False, (
            f"Tuxumni isitib ochirish marosimi uchun quyidagi resurslar kerak:\n"
            f"• 🌾 Oziq-ovqat: 1,500 (sizda: {user.food:,})\n"
            f"• ⛓️ Temir: 800 (sizda: {user.iron:,})\n"
            f"• 🪙 Oltin: 500 (sizda: {user.gold:,})"
        )

    user.food -= 1500
    user.iron -= 800
    user.gold -= 500
    dragon.stage = "baby"
    dragon.power += 50
    user.prestige += 100
    user.xp += 300

    await session.commit()
    return True, f"🔥 AJOYIB MO'JIZA! {dragon.name} buyuk marosimdan so'ng olov bag'rida tuxumdan chiqdi! (+100 Prestige)"


async def feed_dragon(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Ajdarni boqish (350 oziq-ovqat talab etiladi)"""
    user = await session.get(models.User, user_id)
    dragon = await get_user_dragon(session, user_id)
    if not user or not dragon:
        return False, "Ajdar topilmadi."

    if dragon.stage == "egg":
        return False, "Tuxumni boqib bo'lmaydi, avval uni ochiring!"

    if user.food < 350:
        return False, "Ajdarni to'ydirish uchun kamida 350🌾 oziq-ovqat kerak!"

    user.food -= 350
    dragon.hunger = min(100, dragon.hunger + 25)
    dragon.power += 10
    dragon.last_fed = datetime.utcnow()
    await session.commit()
    return True, f"🍗 {dragon.name} to'yib ovqatlandi! Quvvat: {dragon.power} (To'qlik: {dragon.hunger}%)"


async def train_dragon(session: AsyncSession, user_id: int) -> Tuple[bool, str]:
    """Ajdarni parvoz va olovga mashq qildirish (300 temir, 200 oltin)"""
    user = await session.get(models.User, user_id)
    dragon = await get_user_dragon(session, user_id)
    if not user or not dragon:
        return False, "Ajdar topilmadi."

    if dragon.stage == "egg":
        return False, "Tuxumni mashq qildirib bo'lmaydi!"

    if user.iron < 300 or user.gold < 200:
        return False, "Mashg'ulotlar uchun 300⛓️ temir va 200🪙 oltin kerak!"

    user.iron -= 300
    user.gold -= 200
    dragon.level += 1
    dragon.power += 25
    if dragon.level >= 5 and dragon.stage == "baby":
        dragon.stage = "adult"
        await session.commit()
        return True, f"🦅 TABRIKLAYMIZ! {dragon.name} balog'atga yetib, bahaybat jangovar ajdarga aylandi! (Daraja: {dragon.level})"

    await session.commit()
    return True, f"🔥 Dracarys! {dragon.name} olov purkashni o'rgandi: Daraja {dragon.level}, Kuch: {dragon.power}"


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

    # Chempion statistikasi
    champions = {
        "Gregor Clegane": {"atk": 85, "def": 75, "tactic": "heavy"},
        "Oberyn Martell": {"atk": 80, "def": 65, "tactic": "agile"},
        "Bronn": {"atk": 70, "def": 70, "tactic": "parry"},
        "Sandor Clegane": {"atk": 80, "def": 70, "tactic": "heavy"},
    }
    champ = champions.get(champion_name, {"atk": 70, "def": 70, "tactic": "agile"})
    champ_tactic = champ["tactic"]

    # Taktika ustunligi: heavy > agile > parry > heavy
    tactics_win = {"heavy": "agile", "agile": "parry", "parry": "heavy"}
    tactic_bonus = 1.0
    if tactics_win.get(player_tactic) == champ_tactic:
        tactic_bonus = 1.35
    elif tactics_win.get(champ_tactic) == player_tactic:
        tactic_bonus = 0.75

    player_score = (hero_atk * 1.2 + hero_def * 0.8) * tactic_bonus * random.uniform(0.85, 1.25)
    champ_score = (champ["atk"] * 1.2 + champ["def"] * 0.8) * random.uniform(0.85, 1.25)

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

    c_score = (c_atk * 1.2 + c_def * 0.8) * c_bonus * random.uniform(0.85, 1.25)
    o_score = (o_atk * 1.2 + o_def * 0.8) * o_bonus * random.uniform(0.85, 1.25)

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


