from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.orm import relationship
from database.db import Base


# ============================================================
# 1. USER (PLAYER)
# ============================================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=False)

    house_id = Column(Integer, ForeignKey("houses.id"), nullable=True, index=True)
    rank = Column(String(50), default="member")  # king, commander, knight, captain, member
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)

    # Shaxsiy resurslar
    gold = Column(BigInteger, default=1000)
    food = Column(BigInteger, default=2000)
    iron = Column(BigInteger, default=500)
    prestige = Column(Integer, default=10)

    # Tinchlik qalqoni (yangi o'yinchilarni himoya qilish)
    peace_shield_until = Column(DateTime, nullable=True)

    # Kunlik limitlar
    daily_quiz_count = Column(Integer, default=0)
    daily_council_count = Column(Integer, default=0)
    daily_secret_quest_count = Column(Integer, default=0)
    daily_donation_count = Column(Integer, default=0)      # Kunlik ehson (max 2)
    daily_story_quest_count = Column(Integer, default=0)   # Kunlik ssenariy (max 3)
    daily_rank_quest_count = Column(Integer, default=0)    # Kunlik lavozim (max 2)
    daily_ww_attack_count = Column(Integer, default=0)     # Oq yuruvchilarga hujum (max 3)
    daily_bandit_count = Column(Integer, default=0)        # Qaroqchilar pistirmasiga hujum (max 3)
    daily_plague_count = Column(Integer, default=0)        # Kunlik vabo chorasi (max 2)
    equipped_artifact_id = Column(Integer, nullable=True)
    iron_mine_level = Column(Integer, default=1)           # Temir koni darajasi (1-10)
    daily_limit_date = Column(String(10), default="")  # YYYY-MM-DD

    # Kunlik bonus va taklif (Referral)
    last_daily_bonus = Column(DateTime, nullable=True)
    referred_by_id = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)

    # Aloqalar
    house = relationship("House", back_populates="members")
    army = relationship("Army", back_populates="user", uselist=False, cascade="all, delete-orphan")
    characters = relationship("Character", back_populates="user", cascade="all, delete-orphan")
    dragons = relationship("Dragon", back_populates="user", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="user", cascade="all, delete-orphan")
    quest_progress = relationship("QuestProgress", back_populates="user", cascade="all, delete-orphan")


# ============================================================
# 2. HOUSE (XONADON)
# ============================================================
class House(Base):
    __tablename__ = "houses"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)  # masalan: stark, lannister
    name = Column(String(100), nullable=False)
    emoji = Column(String(10), default="🏰")
    region = Column(String(100), nullable=False)  # The North, Westerlands, etc.
    description = Column(Text, default="")

    lord_user_id = Column(BigInteger, nullable=True)  # Xonadon yetakchisi
    gold = Column(BigInteger, default=5000)
    food = Column(BigInteger, default=10000)
    iron = Column(BigInteger, default=2000)
    prestige = Column(Integer, default=100)

    defense_bonus = Column(Float, default=1.0)
    special_troop_name = Column(String(100), default="Special Guard")
    is_npc = Column(Boolean, default=False)

    # Aloqalar
    members = relationship("User", back_populates="house")
    territories = relationship("Territory", back_populates="owner_house")


# ============================================================
# 3. HOUSE MEMBER (QO'SHIMCHA A'ZOLIK TARIXI)
# ============================================================
class HouseMember(Base):
    __tablename__ = "house_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    house_id = Column(Integer, ForeignKey("houses.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rank = Column(String(50), default="member")
    contribution_gold = Column(BigInteger, default=0)
    contribution_food = Column(BigInteger, default=0)
    contribution_iron = Column(BigInteger, default=0)
    joined_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 4. ARMY (HAR BIR O'YINCHI ARMIYASI)
# ============================================================
class Army(Base):
    __tablename__ = "armies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Tosh-Qaychi-Qog'oz askarlar
    infantry = Column(Integer, default=100)      # Piyodalar
    archers = Column(Integer, default=50)        # Kamonchilar
    cavalry = Column(Integer, default=25)        # Otliqlar
    spearmen = Column(Integer, default=25)       # Nayzachilar
    special_troops = Column(Integer, default=0)  # Xonadon maxsus askari

    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="army")


# ============================================================
# 5. CHARACTER / HERO (QAHRAMONLAR)
# ============================================================
class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    house_id = Column(Integer, ForeignKey("houses.id"), nullable=False)

    name = Column(String(100), nullable=False)  # Masalan: Jon Snow, Jaime Lannister
    level = Column(Integer, default=1)
    attack = Column(Integer, default=50)
    defense = Column(Integer, default=50)
    leadership = Column(Integer, default=50)  # Qo'shinga bonus beradi (%)
    special_ability = Column(String(200), default="Jasorat")
    loyalty = Column(Integer, default=100)
    is_alive = Column(Boolean, default=True)

    user = relationship("User", back_populates="characters")


# ============================================================
# 6. TERRITORY (WESTEROS HUDUDLARI VA QAL'ALARI)
# ============================================================
class Territory(Base):
    __tablename__ = "territories"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    region = Column(String(100), nullable=False)
    castle_name = Column(String(100), nullable=False)

    owner_house_id = Column(Integer, ForeignKey("houses.id"), nullable=True)
    population = Column(Integer, default=50000)

    # Soatlik daromadlar
    gold_income = Column(Integer, default=200)
    food_income = Column(Integer, default=500)
    iron_income = Column(Integer, default=100)

    defense = Column(Integer, default=500)  # Qal'a mustahkamligi
    garrison_infantry = Column(Integer, default=200)
    garrison_archers = Column(Integer, default=100)
    garrison_cavalry = Column(Integer, default=50)
    garrison_spearmen = Column(Integer, default=50)

    is_capital = Column(Boolean, default=False)  # King's Landing, Winterfell va h.k.
    last_tax_collected_at = Column(DateTime, default=datetime.utcnow)  # Oxirgi o'lpon yig'ilgan vaqt
    reinforcements_json = Column(Text, default="{}")  # Ittifoqchilar mudofaasi: {house_name: {infantry: N, ...}}

    owner_house = relationship("House", back_populates="territories")
    buildings = relationship("Building", back_populates="territory", cascade="all, delete-orphan")


# ============================================================
# 7. BUILDING (QAL'A ICHIDAGI BINOLAR)
# ============================================================
class Building(Base):
    __tablename__ = "buildings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    territory_id = Column(Integer, ForeignKey("territories.id"), nullable=False)
    type = Column(String(50), nullable=False)  # farm, mine, barracks, walls, market
    level = Column(Integer, default=1)

    territory = relationship("Territory", back_populates="buildings")


# ============================================================
# 8. BATTLE MARCH (YURISH VAQTI VA ARMIYA HARAKATI)
# ============================================================
class BattleMarch(Base):
    __tablename__ = "battle_marches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    attacker_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source_territory_id = Column(Integer, ForeignKey("territories.id"), nullable=False)
    target_territory_id = Column(Integer, ForeignKey("territories.id"), nullable=False)

    # Yuborilgan qo'shin
    infantry = Column(Integer, default=0)
    archers = Column(Integer, default=0)
    cavalry = Column(Integer, default=0)
    spearmen = Column(Integer, default=0)
    special_troops = Column(Integer, default=0)
    character_id = Column(Integer, nullable=True)
    has_dragon = Column(Boolean, default=False)
    dragon_tactic = Column(String(50), default="none")  # none, walls, ranged, frontline, balanced

    departure_time = Column(DateTime, default=datetime.utcnow)
    arrival_time = Column(DateTime, nullable=False, index=True)
    status = Column(String(30), default="marching")  # marching, resolved, recalled


# ============================================================
# 9. BATTLE REPORT (JANG HISOBOTLARI)
# ============================================================
class BattleReport(Base):
    __tablename__ = "battle_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    attacker_user_id = Column(Integer, nullable=False)
    defender_user_id = Column(Integer, nullable=True)
    territory_id = Column(Integer, nullable=False)

    attacker_house_name = Column(String(100), default="")
    defender_house_name = Column(String(100), default="")

    attacker_losses_json = Column(Text, default="{}")
    defender_losses_json = Column(Text, default="{}")
    loot_gold = Column(BigInteger, default=0)
    loot_food = Column(BigInteger, default=0)
    loot_iron = Column(BigInteger, default=0)

    result = Column(String(50), default="attacker_won")  # attacker_won, defender_won
    details = Column(Text, default="")
    timestamp = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 10. QUEST PROGRESS (VAZIFALAR VA TANLOVLAR)
# ============================================================
class QuestProgress(Base):
    __tablename__ = "quest_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quest_code = Column(String(100), nullable=False)
    quest_type = Column(String(50), default="main")  # main, house, daily, secret
    step = Column(Integer, default=0)
    status = Column(String(30), default="active")  # active, completed, failed
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="quest_progress")


# ============================================================
# 11. ALLIANCE & DIPLOMACY (ITTIFOQ VA SULHLAR)
# ============================================================
class Alliance(Base):
    __tablename__ = "alliances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    house_a_id = Column(Integer, ForeignKey("houses.id"), nullable=False)
    house_b_id = Column(Integer, ForeignKey("houses.id"), nullable=False)
    type = Column(String(50), default="alliance")  # alliance, non_aggression, vassal
    status = Column(String(30), default="pending")  # pending, active, broken
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 12. WAR (URUSHLAR)
# ============================================================
class War(Base):
    __tablename__ = "wars"

    id = Column(Integer, primary_key=True, autoincrement=True)
    attacker_house_id = Column(Integer, ForeignKey("houses.id"), nullable=False)
    defender_house_id = Column(Integer, ForeignKey("houses.id"), nullable=False)
    status = Column(String(30), default="active")  # active, peace, surrendered
    declared_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)


# ============================================================
# 13. EVENT STATE (WHITE WALKERS & IRON THRONE)
# ============================================================
class EventState(Base):
    __tablename__ = "event_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_name = Column(String(100), unique=True, nullable=False)  # white_walkers, iron_throne
    data_json = Column(Text, default="{}")
    is_active = Column(Boolean, default=True)
    started_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 14. TRANSACTION / LOGS (AUDIT VA ANTI-CHEAT)
# ============================================================
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    amount_gold = Column(BigInteger, default=0)
    amount_food = Column(BigInteger, default=0)
    amount_iron = Column(BigInteger, default=0)
    action_type = Column(String(100), nullable=False)
    details = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 15. HOUSE VOTE / ELECTION (XONADON LORDI SAYLOVI)
# ============================================================
class HouseVote(Base):
    __tablename__ = "house_votes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    house_id = Column(Integer, ForeignKey("houses.id"), nullable=False, index=True)
    voter_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    candidate_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    voted_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 16. DRAGON (AFSONAVIY AJDARLAR)
# ============================================================
class Dragon(Base):
    __tablename__ = "dragons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    grade = Column(String(10), default="C")  # A (Qora), B (Yashil), C (Oltin)
    stage = Column(String(30), default="egg")  # egg, baby, adult
    level = Column(Integer, default=1)
    hunger = Column(Integer, default=50)  # 0 to 100 (100 is full)
    power = Column(Integer, default=100)
    artifact_code = Column(String(50), nullable=True)  # Ajdarga taqilgan artefakt
    has_laid_egg = Column(Boolean, default=False)
    last_fed = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="dragons")


# ============================================================
# 17. DUEL (QAHRAMONLARARO 1V1 DUEL)
# ============================================================
class Duel(Base):
    __tablename__ = "duels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    challenger_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    opponent_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    bet_gold = Column(Integer, default=100)  # 100, 250, 500
    challenger_tactic = Column(String(50), default="heavy")  # heavy, parry, agile
    opponent_tactic = Column(String(50), nullable=True)
    status = Column(String(30), default="pending")  # pending, completed, cancelled
    winner_id = Column(Integer, nullable=True)
    details = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 18. RAVEN MESSAGE (QARG'ALAR POCHTASI)
# ============================================================
class RavenMessage(Base):
    __tablename__ = "raven_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    message_text = Column(Text, nullable=False)
    gold_attached = Column(Integer, default=0)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 19. ARTIFACT (AFSONAVIY VALYRIA QUROLLARI VA RELIKLARI)
# ============================================================
class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(String(30), default="weapon")
    is_equipped = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="artifacts")


# ============================================================
# 20. NIGHT KING RAID CONTRIBUTION (ZIYON REYTINGI)
# ============================================================
class NightKingContribution(Base):
    __tablename__ = "night_king_contributions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    damage_dealt = Column(BigInteger, default=0)
    attacks_count = Column(Integer, default=0)
    last_attack = Column(DateTime, default=datetime.utcnow)


