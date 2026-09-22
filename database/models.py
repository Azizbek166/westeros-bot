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
    title = Column(String(100), nullable=True)  # Faxriy / sharafli unvon (masalan: Shimol Najotkori, Qirol Qo'li)
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)

    # Shaxsiy resurslar
    gold = Column(BigInteger, default=250)
    food = Column(BigInteger, default=500)
    iron = Column(BigInteger, default=125)
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
    daily_duel_count = Column(Integer, default=0)          # Kunlik duel jangi (max 10)
    daily_recruit_count = Column(Integer, default=0)       # Kunlik yollangan askarlar soni
    daily_caravan_send_count = Column(Integer, default=0)  # Kunlik karvon jo'natish (max 2)
    daily_caravan_raid_count = Column(Integer, default=0)  # Kunlik karvonga pistirma/raid (max 2)
    daily_spy_scout_count = Column(Integer, default=0)     # Kunlik josuslik: Razvedka (max 2)
    daily_spy_sabotage_count = Column(Integer, default=0)  # Kunlik josuslik: Sabotaj (max 2)
    daily_spy_gates_count = Column(Integer, default=0)     # Kunlik josuslik: Darvoza ochish (max 2)
    equipped_artifact_id = Column(Integer, nullable=True)
    iron_mine_level = Column(Integer, default=1)           # Temir koni darajasi (1-10)
    grain_mill_level = Column(Integer, default=1)          # Don tegirmoni darajasi (1-10)
    castle_taxes_json = Column(Text, default="{}")         # Shaxsiy soliq olingan vaqtlar: {territory_id: iso_timestamp}
    daily_limit_date = Column(String(10), default="")  # YYYY-MM-DD

    # Kunlik bonus va taklif (Referral)
    last_daily_bonus = Column(DateTime, nullable=True)
    streak_count = Column(Integer, default=0)              # 7 kunlik uzluksiz kirish (1-7)
    last_streak_date = Column(String(10), default="")      # YYYY-MM-DD
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
    lord_elected_at = Column(DateTime, nullable=True)  # Lord saylangan vaqt (har 10 kunda saylov yangilanadi)
    group_chat_id = Column(BigInteger, nullable=True)  # Xonadonning Telegram guruh chat ID si
    group_title = Column(String(200), nullable=True)   # Telegram guruh nomi
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
    catapults = Column(Integer, default=0)       # Qamal katapultalari (devor yemiruvchi, max 20)
    siege_towers = Column(Integer, default=0)    # Qamal minoralari (piyodalarni asrovchi, max 10)
    champion = Column(String(50), nullable=True) # Afsonaviy qahramon (jon_snow, jaime, arya, oberyn, brienne)

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
    conquered_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    population = Column(Integer, default=50000)

    # Soatlik daromadlar
    gold_income = Column(Integer, default=50)
    food_income = Column(Integer, default=125)
    iron_income = Column(Integer, default=25)

    defense = Column(Integer, default=500)  # Qal'a mustahkamligi
    garrison_infantry = Column(Integer, default=200)
    garrison_archers = Column(Integer, default=100)
    garrison_cavalry = Column(Integer, default=50)
    garrison_spearmen = Column(Integer, default=50)

    is_capital = Column(Boolean, default=False)  # King's Landing, Winterfell va h.k.
    castle_level = Column(Integer, default=1)  # Qal'a istehkom darajasi (Tier 1-5)
    wildfire_count = Column(Integer, default=0) # Alkimyogarlar Yovvoyi Olovi (Wildfire, max 5)
    gates_compromised_until = Column(DateTime, nullable=True) # Josus tomonidan darvoza ochilgan vaqt muddati
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
    catapults = Column(Integer, default=0)
    siege_towers = Column(Integer, default=0)
    champion = Column(String(50), nullable=True) # Hujumga yetakchilik qilayotgan qahramon
    character_id = Column(Integer, nullable=True)
    has_dragon = Column(Boolean, default=False)
    dragon_id = Column(Integer, nullable=True)  # Hujumda ishtirok etayotgan aniq ajdar ID si
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
    type = Column(String(50), default="military")  # military, marriage
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


# ============================================================
# 21. HOUSE TRADE (XONADONLARARO SAVDO-SOTIQ BIRJASI)
# ============================================================
class HouseTrade(Base):
    __tablename__ = "house_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seller_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    seller_house_id = Column(Integer, ForeignKey("houses.id"), nullable=False, index=True)

    offer_resource = Column(String(20), nullable=False)    # "food", "iron", "gold"
    offer_amount = Column(BigInteger, nullable=False)

    request_resource = Column(String(20), nullable=False)  # "gold", "food", "iron"
    request_amount = Column(BigInteger, nullable=False)

    buyer_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    buyer_house_id = Column(Integer, ForeignKey("houses.id"), nullable=True)

    status = Column(String(20), default="active", index=True)  # "active", "completed", "cancelled"
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    seller = relationship("User", foreign_keys=[seller_user_id])
    seller_house = relationship("House", foreign_keys=[seller_house_id])
    buyer = relationship("User", foreign_keys=[buyer_user_id])
    buyer_house = relationship("House", foreign_keys=[buyer_house_id])


# ============================================================
# 22. BRAAVOS TEMIR BANKI (IRON BANK OF BRAAVOS)
# ============================================================
class IronBank(Base):
    __tablename__ = "iron_bank"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)

    # Omonat (Deposit)
    deposit_gold = Column(BigInteger, default=0)
    deposit_updated_at = Column(DateTime, default=datetime.utcnow)
    last_interest_claimed_at = Column(DateTime, default=datetime.utcnow)

    # Qarz (Loan)
    loan_gold = Column(BigInteger, default=0)              # Asosiy qarz miqdori
    loan_due_at = Column(DateTime, nullable=True)          # Qarz qaytarish oxirgi muddati (5 kun)
    loan_interest_rate = Column(Float, default=0.10)       # 10% foiz
    is_defaulted = Column(Boolean, default=False)          # Qarz muddati o'tib ketgan

    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User")


# ============================================================
# 23. MAVSUMLAR TIZIMI (30-DAY SEASONS)
# ============================================================
class SeasonState(Base):
    __tablename__ = "season_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_number = Column(Integer, default=1, unique=True)
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 24. SHON-SHARAF ZALI (HALL OF FAME)
# ============================================================
class HallOfFame(Base):
    __tablename__ = "hall_of_fame"

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_number = Column(Integer, nullable=False)
    winner_house_id = Column(Integer, ForeignKey("houses.id"), nullable=True)
    winner_house_name = Column(String(100), nullable=False)
    king_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    king_name = Column(String(100), nullable=True)
    top_warrior_name = Column(String(100), nullable=True)
    top_warrior_prestige = Column(Integer, default=0)
    concluded_at = Column(DateTime, default=datetime.utcnow)

    winner_house = relationship("House", foreign_keys=[winner_house_id])
    king = relationship("User", foreign_keys=[king_user_id])


# ============================================================
# 24.1 MAVSUMIY TOP-3 BONUSLARI (SEASON TOP BONUSES)
# ============================================================
class SeasonTopBonus(Base):
    __tablename__ = "season_top_bonuses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_number = Column(Integer, nullable=False, index=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    character_name = Column(String(100), nullable=True)
    rank_position = Column(Integer, nullable=False)  # 1, 2, 3
    prestige = Column(Integer, default=0)
    is_claimed = Column(Boolean, default=False)
    claimed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 25. JOSUSLIK VA QIZIL TO'Y (ESPIONAGE & INFILTRATION)
# ============================================================
class SpyMission(Base):
    __tablename__ = "spy_missions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    target_territory_id = Column(Integer, ForeignKey("territories.id"), nullable=False, index=True)
    mission_type = Column(String(50), nullable=False)  # scout, sabotage, open_gates
    cost_gold = Column(Integer, default=1000)
    status = Column(String(30), default="success")    # success, caught
    report_text = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    target_territory = relationship("Territory")


# ============================================================
# 26. RITSARLAR TURNIRI VA STAVKALAR (TOURNAMENT & BETS)
# ============================================================
class Tournament(Base):
    __tablename__ = "tournaments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), default="Qirol Qo'li Turniri")
    status = Column(String(30), default="active", index=True)  # active, completed
    prize_pool = Column(BigInteger, default=2500)
    winner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    winner_name = Column(String(100), nullable=True)
    details = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    concluded_at = Column(DateTime, nullable=True)

    winner = relationship("User", foreign_keys=[winner_user_id])
    participants = relationship("TournamentParticipant", back_populates="tournament", cascade="all, delete-orphan")
    bets = relationship("TournamentBet", back_populates="tournament", cascade="all, delete-orphan")


class TournamentParticipant(Base):
    __tablename__ = "tournament_participants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    fighter_name = Column(String(100), nullable=False)
    fighter_power = Column(Integer, default=100)
    score = Column(Integer, default=0)
    is_eliminated = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    tournament = relationship("Tournament", back_populates="participants")
    user = relationship("User")


class TournamentBet(Base):
    __tablename__ = "tournament_bets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    participant_id = Column(Integer, ForeignKey("tournament_participants.id"), nullable=False, index=True)
    bet_gold = Column(Integer, nullable=False)
    payout_gold = Column(Integer, default=0)
    status = Column(String(30), default="placed")  # placed, won, lost
    created_at = Column(DateTime, default=datetime.utcnow)

    tournament = relationship("Tournament", back_populates="bets")
    user = relationship("User")
    participant = relationship("TournamentParticipant")


# ============================================================
# 27. SAVDO KARVONLARI VA PISTIRMALAR (TRADE CARAVANS & RAIDS)
# ============================================================
class TradeCaravan(Base):
    __tablename__ = "trade_caravans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    owner_house_id = Column(Integer, ForeignKey("houses.id"), nullable=False, index=True)
    origin_territory_id = Column(Integer, ForeignKey("territories.id"), nullable=False)
    destination_territory_id = Column(Integer, ForeignKey("territories.id"), nullable=False)

    resource_type = Column(String(20), nullable=False)      # food, iron
    resource_amount = Column(Integer, nullable=False)      # e.g. 5000, 10000, 20000
    expected_gold_reward = Column(Integer, default=0)

    escort_cavalry = Column(Integer, default=0)
    escort_infantry = Column(Integer, default=0)

    departure_time = Column(DateTime, default=datetime.utcnow)
    arrival_time = Column(DateTime, nullable=False, index=True)
    status = Column(String(30), default="moving", index=True)  # moving, arrived, raided, looted

    raider_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    raid_report = Column(Text, default="")

    owner = relationship("User", foreign_keys=[owner_user_id])
    owner_house = relationship("House", foreign_keys=[owner_house_id])
    origin_territory = relationship("Territory", foreign_keys=[origin_territory_id])
    destination_territory = relationship("Territory", foreign_keys=[destination_territory_id])
    raider = relationship("User", foreign_keys=[raider_user_id])




