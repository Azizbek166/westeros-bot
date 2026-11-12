"""
The Iron Throne RPG - Centralized Game Balance Configuration Module.
All game numbers, economy rates, unit stats, battle formulas, cooldowns,
leveling curves, and rewards are defined here.
Can be tweaked, reloaded, or overriden via environment / JSON without modifying code.
"""
import os
import json
from typing import Dict, Any, Tuple
from dataclasses import dataclass, field


# ============================================================
# 1. ECONOMY & RESOURCE GENERATION (IQTISODIYOT VA RESURSLAR)
# ============================================================
@dataclass
class EconomyBalance:
    # Boshlang'ich resurslar (yangi o'yinchi)
    starting_gold: int = 500
    starting_food: int = 1000
    starting_iron: int = 300

    # Bazaviy soatlik ishlab chiqarish (Tick daromadlari)
    base_hourly_gold: int = 25
    base_hourly_food: int = 40
    base_hourly_iron: int = 15

    # Don tegirmoni va temir koni soatlik o'sishi (daraja boshiga)
    mill_food_per_level: int = 75
    mine_iron_per_level: int = 50

    # Hudud daromadlarining xonadon a'zolariga bo'linish ulushi (1/N)
    house_territory_share_divisor: int = 4

    # Qal'a darajasi bonusi (har bir qal'a darajasi uchun +25% daromad)
    castle_level_income_bonus_per_tier: float = 0.25

    # Ob-havo iqtisodiy multiplikatorlari
    summer_gold_mult: float = 1.25
    summer_food_mult: float = 1.50
    severe_winter_food_upkeep_mult: float = 1.25

    # Oziq-ovqat tugaganda ochlikdan qochish (desertion) foizi (soatiga)
    starvation_desertion_rate: float = 0.05

    # VIP Sovereign (Imperatorlik) doimiy resurs bonusi
    sovereign_vip_income_mult: float = 1.25


# ============================================================
# 2. UNITS, STATS & UPKEEP (ARMIYA, HARBIY XARAKTERISTIKALAR)
# ============================================================
@dataclass
class UnitBalance:
    name: str
    code: str
    attack: int
    defense: int
    gold_cost: int
    iron_cost: int
    food_upkeep: float
    description: str


UNITS_CONFIG: Dict[str, Dict[str, Any]] = {
    "infantry": {
        "name": "🛡️ Piyoda Askar (Infantry)",
        "code": "infantry",
        "attack": 10,
        "defense": 15,
        "gold_cost": 2,
        "iron_cost": 1,
        "food_upkeep": 0.5,
        "description": "Zirhli qalqonli jangchilar. Nayzachilarga qarshi kuchli.",
    },
    "archers": {
        "name": "🏹 Kamonchi (Archers)",
        "code": "archers",
        "attack": 16,
        "defense": 8,  # Balanslangan: 6 dan 8 ga ko'tarildi (haddan tashqari mo'rtlikdan saqlash uchun)
        "gold_cost": 3,
        "iron_cost": 1,
        "food_upkeep": 0.6,
        "description": "Masofadan zarba beruvchilar. Piyodalarga qarshi ustun.",
    },
    "cavalry": {
        "name": "🐎 Otliq (Cavalry)",
        "code": "cavalry",
        "attack": 24,  # Balanslangan: 22 dan 24 ga oshirildi (yuqori narxga mos kelishi uchun)
        "defense": 12,
        "gold_cost": 6,
        "iron_cost": 3,
        "food_upkeep": 1.2,
        "description": "Tezkor va halokatli zarba. Kamonchilarni tor-mor qiladi.",
    },
    "spearmen": {
        "name": "🗡️ Nayzachi (Spearmen)",
        "code": "spearmen",
        "attack": 12,
        "defense": 16,
        "gold_cost": 2,
        "iron_cost": 2,
        "food_upkeep": 0.5,
        "description": "Uzun nayzalar devori. Otliqlar hujumini qaytaradi.",
    },
    "special_troops": {
        "name": "🔥 Maxsus Xonadon Askari (Special)",
        "code": "special_troops",
        "attack": 32,  # Balanslangan: 30 dan 32 ga oshirildi
        "defense": 26,  # Balanslangan: 25 dan 26 ga oshirildi
        "gold_cost": 12,
        "iron_cost": 6,
        "food_upkeep": 1.5,
        "description": "Har bir xonadonning elita askarlari (Direwolf Guard, Rose Knights va h.k.).",
    },
}

# Tosh-Qaychi-Qog'oz (RPS) jang ustunliklari
RPS_ADVANTAGES: Dict[Tuple[str, str], float] = {
    ("cavalry", "archers"): 1.40,
    ("spearmen", "cavalry"): 1.40,
    ("archers", "infantry"): 1.30,
    ("infantry", "spearmen"): 1.30,
    # Teskari ta'sir (Kamayish)
    ("archers", "cavalry"): 0.70,
    ("cavalry", "spearmen"): 0.70,
    ("infantry", "archers"): 0.80,
    ("spearmen", "infantry"): 0.80,
}

# Boshlang'ich armiya tarkibi
STARTING_ARMY_COMPOSITION = {
    "infantry": 100,
    "archers": 50,
    "cavalry": 25,
    "spearmen": 25,
    "special_troops": 0,
}


# ============================================================
# 3. COMBAT & SIEGE MECHANICS (JANG VA QAMAL MEXANIKASI)
# ============================================================
@dataclass
class BattleBalance:
    max_combat_rounds: int = 3
    base_march_minutes: int = 5
    min_attack_army_size: int = 50

    # Qamal devorlari maksimal zarari va koeffitsiyentlari
    catapult_siege_dmg_min: int = 30
    catapult_siege_dmg_max: int = 45
    catapult_max_wall_damage_percent: float = 0.65

    # Yovvoyi olov (Wildfire) talofati
    wildfire_min_kill_percent: float = 0.15
    wildfire_max_kill_percent: float = 0.25
    wildfire_max_total_kills: int = 150

    # Qamal minoralari piyodalarni himoya qilish ulushi (minora boshiga 5%, max 35%)
    siege_tower_infantry_shield_per_unit: float = 0.05
    siege_tower_max_infantry_shield: float = 0.35

    # Raunddagi maksimal yo'qotish ulushi (0.60 = 60%)
    max_round_casualty_ratio: float = 0.60

    # O'lja (Loot) chegaralari
    loot_gold_min: int = 150
    loot_gold_max: int = 450
    loot_food_min: int = 300
    loot_food_max: int = 900
    loot_iron_min: int = 100
    loot_iron_max: int = 300


# ============================================================
# 4. DRAGON ATTRIBUTES & GROWTH (AJDARLAR BALANSI)
# ============================================================
@dataclass
class DragonBalance:
    # Grade ko'paytuvchilari
    grade_multipliers: Dict[str, float] = field(default_factory=lambda: {
        "A": 1.20,
        "B": 1.10,
        "C": 1.00,
    })

    # Stage ko'paytuvchilari
    stage_multipliers: Dict[str, float] = field(default_factory=lambda: {
        "egg": 0.0,
        "baby": 0.50,
        "young": 1.05,
        "adult": 1.30,
        "ancient": 1.65,
    })

    # Daraja o'sish koeffitsiyenti (daraja boshiga +2.5% quvvat)
    level_growth_rate: float = 0.025

    # Oziqlantirish (Feed) va mashq cooldown'lari (soatlarda)
    feed_cooldown_hours: int = 4
    train_cooldown_hours: int = 6

    # Oziqlantirish narxi (resurs)
    feed_gold_cost: int = 50
    feed_food_cost: int = 250
    feed_power_gain: int = 5


# ============================================================
# 5. DAILY LIMITS & REWARDS (KUNLIK CHEKLOVLAR VA MUKOFOTLAR)
# ============================================================
@dataclass
class DailyLimitsBalance:
    daily_quiz_limit: int = 8
    daily_council_limit: int = 3
    daily_secret_quest_limit: int = 2
    daily_duel_limit: int = 5

    # Duel garov variantlari
    duel_allowed_bets: Tuple[int, ...] = (0, 100, 250, 500)


# 7 kunlik uzluksiz kirish (Streak) mukofotlari
STREAK_REWARDS_CONFIG = {
    1: {"gold": 300, "food": 600, "iron": 200, "prestige": 5, "xp": 20, "troops": {}, "extra_desc": ""},
    2: {"gold": 600, "food": 1200, "iron": 400, "prestige": 10, "xp": 40, "troops": {}, "extra_desc": ""},
    3: {"gold": 1100, "food": 2200, "iron": 700, "prestige": 20, "xp": 60, "troops": {"infantry": 10}, "extra_desc": "🛡️ +10 ta Piyoda saflaringizga qo'shildi!"},
    4: {"gold": 1600, "food": 3200, "iron": 1000, "prestige": 25, "xp": 80, "troops": {"archers": 8}, "extra_desc": "🏹 +8 ta Kamonchi armiyangizga qo'shildi!"},
    5: {"gold": 2400, "food": 4500, "iron": 1500, "prestige": 35, "xp": 100, "troops": {"cavalry": 5}, "extra_desc": "🐎 +5 ta Og'ir Otliq bayrog'ingiz ostida!"},
    6: {"gold": 3500, "food": 6500, "iron": 2200, "prestige": 50, "xp": 140, "troops": {"spearmen": 6, "archers": 4}, "extra_desc": "🗡️ +6 Nayzachi va 🏹 +4 Kamonchi!"},
    7: {"gold": 6000, "food": 12000, "iron": 4000, "prestige": 80, "xp": 200, "troops": {"special_troops": 8}, "dragon_power": 20, "extra_desc": "👑 +8 ta Maxsus Gvardiya va Ajdarga +20 Ozuqa!"},
}


# ============================================================
# 6. NEWBIE PROTECTION & CATCH-UP (YANGI O'YINCHI HIMOYASI)
# ============================================================
@dataclass
class ProtectionBalance:
    # Yangi ro'yxatdan o'tgan o'yinchiga beriladigan tinchlik qalqoni (soatlarda: 72 soat = 3 kun)
    newbie_peace_shield_hours: int = 72

    # Hujum qilish uchun maksimal daraja farqi (Level Gap):
    # Tajribali o'yinchilar o'zidan 5 daraja pastdagi yangi o'yinchilar qal'asiga hujum qila olmaydi
    max_level_gap_for_attack: int = 5

    # Catch-up (Quvib yetish) mexanizmi:
    # O'rtacha server darajasidan 3+ daraja past bo'lgan o'yinchilarga XP va resurs kvestlaridan +35% bonus beriladi
    catchup_level_threshold: int = 3
    catchup_bonus_multiplier: float = 1.35

    # Catch-up faolligi
    enable_catchup_mechanic: bool = True


# ============================================================
# 7. ANTI-CHEAT & MULTI-ACCOUNT DETECTION (XAVFSIZLIK VA CHEAT)
# ============================================================
@dataclass
class AntiCheatBalance:
    # Qisqa vaqt (1 soat) ichida g'ayritabiiy oltin o'sishi chegarasi (ogohlantirish uchun)
    abnormal_gold_spike_1h: int = 100_000

    # Bozor (Market) narxlarining ruxsat etilgan nisbati (sun'iy o'tkazishga qarshi)
    # Masalan, 1 oltin uchun minimal 0.2, maksimal 5.0 resurs so'rash mumkin
    min_trade_rate_ratio: float = 0.20
    max_trade_rate_ratio: float = 5.00

    # 1 kunda bir xil o'yinchi bilan ruxsat etilgan maksimal savdolar soni
    max_trades_between_same_players_per_day: int = 10

    # Harakatlar bo'yicha cheklov (Rate limit): 1 daqiqada ruxsat etilgan maksimal amallar
    max_actions_per_minute: int = 40


# ============================================================
# MARKAZIY BALANS INSTANSIYALARI
# ============================================================
ECONOMY = EconomyBalance()
BATTLE = BattleBalance()
DRAGON = DragonBalance()
DAILY_LIMITS = DailyLimitsBalance()
PROTECTION = ProtectionBalance()
ANTI_CHEAT = AntiCheatBalance()


def get_all_balance_summary() -> Dict[str, Any]:
    """Barcha o'yin raqamlarini bitta JSON-moslug'i formatida qaytaradi"""
    return {
        "economy": ECONOMY.__dict__,
        "units": UNITS_CONFIG,
        "rps_advantages": {f"{k[0]}_vs_{k[1]}": v for k, v in RPS_ADVANTAGES.items()},
        "battle": BATTLE.__dict__,
        "dragon": DRAGON.__dict__,
        "daily_limits": DAILY_LIMITS.__dict__,
        "streak_rewards": STREAK_REWARDS_CONFIG,
        "protection": PROTECTION.__dict__,
        "anti_cheat": ANTI_CHEAT.__dict__,
    }
