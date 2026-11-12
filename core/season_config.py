"""
THE IRON THRONE RPG - SEASON & SEASON PASS CONFIGURATION MODULE
Mavsum davomiyligi, Season Ochkolari (SO) formulasi, Season Pass tierlari,
mukofotlar va Yumshoq Reset (Soft-Reset) qoidalari.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any


# ============================================================
# 1. MAVSUM VAQT CHEGARALARI VA ASOSIY SOZLAMALAR
# ============================================================
DEFAULT_SEASON_WEEKS: int = 6           # Standart 6 hafta
DEFAULT_SEASON_DAYS: int = 42           # 42 kun
SEASON_NOTIFICATION_HOURS: List[int] = [72, 24, 6]  # 3 kun, 1 kun va 6 soat qolganda eslatma


# ============================================================
# 2. SEASON OCHKOLARI (SO) HISOBLASH FORMULASI
# Faqat mahorat, strategiya va faollik uchun ochko beriladi (NO P2W).
# Resurs boyligi yoki donat uchun ochko BERILMAYDI.
# ============================================================
@dataclass
class SeasonPointsWeights:
    duel_win: int = 15                  # Har bir yutilgan duel uchun
    march_victory: int = 30             # Har bir zabt etilgan qal'a/yurish uchun
    daily_quest_completed: int = 10     # Kunlik vazifa uchun
    citadel_quiz_correct: int = 8       # Maester viktorinasi to'g'ri javobi
    active_day_streak: int = 12         # Kunlik uzluksiz kirish uchun
    guild_contribution_per_100: int = 5 # Gildiyaga qo'shilgan har 100 hissa uchun
    held_castle_per_tick: int = 2       # Har soatda ushlab turilgan har bir qal'a uchun
    tournament_round_win: int = 25      # Turnir bosqichi g'alabasi uchun


# ============================================================
# 3. YUMSHOQ RESET (SOFT-RESET) FOIZLARI VA CHEGARALARI
# Iqtisodiy tahlil va balans asosida belgilangan:
# - Eski o'yinchilarning ulkan zaxiralari yangi o'yinchilarni ezib qo'ymasligi uchun
#   15-20% saqlanadi va qat'iy yuqori chegara (Hard Cap) qo'yiladi.
# - Profil, kosmetika, unvonlar, ajdarlar va qahramonlar 100% tegilmaydi.
# ============================================================
@dataclass
class SoftResetRules:
    # Oltin (Gold): 15% saqlanadi, maksimal 15,000 oltin
    gold_preserve_pct: float = 0.15
    gold_hard_cap: int = 15_000

    # Bug'doy (Food): 20% saqlanadi, maksimal 30,000 bug'doy (ochlikka tushmaslik uchun)
    food_preserve_pct: float = 0.20
    food_hard_cap: int = 30_000

    # Temir (Iron): 15% saqlanadi, maksimal 10,000 temir
    iron_preserve_pct: float = 0.15
    iron_hard_cap: int = 10_000

    # Qal'a darajasi (Castle Level): 1 darajaga kamaytiriladi (min 1)
    # Masalan: 3-darajali qal'a -> 2-darajaga, 2 -> 1, 1 -> 1
    castle_level_reduction: int = 1

    # Armiya: Dastlabki garnizon holatiga qaytariladi (Piyoda: 100, Kamonchi: 50, Otliq: 25, Nayzador: 25)
    base_infantry: int = 100
    base_archers: int = 50
    base_cavalry: int = 25
    base_spearmen: int = 25


# ============================================================
# 4. SEASON PASS: XP CHEGARALARI VA HARAKATLAR
# ============================================================
SEASON_PASS_XP_PER_TIER: int = 100      # Har bir tier uchun 100 Season XP kerak
TOTAL_SEASON_PASS_TIERS: int = 20       # Jami 20 ta tier (2,000 XP)
PREMIUM_PASS_PRICE_STARS: int = 250     # 250 Telegram Stars
PREMIUM_PASS_PRICE_UZS: int = 25_000    # 25,000 so'm

# Harakatlar uchun beriladigan Season Pass XP miqdori:
PASS_XP_REWARDS = {
    "login_streak": 25,                 # Kunlik kirish
    "daily_quest": 15,                  # Bitta kunlik kvest
    "duel_win": 10,                     # Duelda g'alaba
    "march_win": 20,                    # Qal'aga muvaffaqiyatli yurish
    "citadel_quiz": 10,                 # Viktorina
    "caravan_complete": 15,             # Karvon yetib borishi
    "guild_deposit": 10,                # Gildiya xazinasiga yordam
}


# ============================================================
# 5. SEASON PASS: 20 TA TIER MUKOFOROTLARI (KATALOG)
# DIQQAT: Faqat kosmetika va zararsiz qulaylik!
# Jangda ustunlik, ko'p sonli qo'shin yoki kuch berilmaydi.
# ============================================================
SEASON_PASS_TIERS_CONFIG: List[Dict[str, Any]] = [
    {
        "tier": 1,
        "xp_required": 100,
        "free": {
            "type": "title",
            "item_id": "title_pass_recruit",
            "name": "«Mavsum Sayyohi» Unvoni",
            "icon": "🎖️",
            "desc": "Yangi mavsumga qadam qo'ygan Lord ramzi."
        },
        "premium": {
            "type": "frame",
            "item_id": "frame_valyrian_bronze",
            "name": "Valiriya Bronza Ramkasi",
            "icon": "🖼️",
            "desc": "Eksklyuziv profil bronza hoshiyasi."
        }
    },
    {
        "tier": 2,
        "xp_required": 200,
        "free": {
            "type": "convenience",
            "item_id": "conv_raven_free",
            "name": "5 ta Bepul Chopar Qarg'asi",
            "icon": "📬",
            "desc": "Qo'shni lordlar bilan xat yozish uchun choparlar."
        },
        "premium": {
            "type": "cosmetic_dragon",
            "item_id": "skin_dragon_horn_gold",
            "name": "Ajdaho Zarrin Shoxi Skini",
            "icon": "🐉",
            "desc": "Ajdaho portretiga jilvakor oltin nur bag'ishlaydi."
        }
    },
    {
        "tier": 3,
        "xp_required": 300,
        "free": {
            "type": "convenience",
            "item_id": "conv_instant_scout",
            "name": "2 ta Tezkor Razvedka Xaritasi",
            "icon": "🗺️",
            "desc": "Yaqin oradagi 2 ta qal'a mudofaasini zudlik bilan ochadi."
        },
        "premium": {
            "type": "title",
            "item_id": "title_iron_will",
            "name": "«Po'lat Iroda» Unvoni",
            "icon": "⚔️",
            "desc": "Maydonda hech qachon ortga chekinmaydigan qahramon."
        }
    },
    {
        "tier": 4,
        "xp_required": 400,
        "free": {
            "type": "badge",
            "item_id": "badge_faithful_lord",
            "name": "«Sodiq Vassal» Nishoni",
            "icon": "🛡️",
            "desc": "Xonadon bayrog'iga sodiqlik belgisi."
        },
        "premium": {
            "type": "effect",
            "item_id": "effect_gold_sparks",
            "name": "Xabarlarda Oltin Uchqunlar",
            "icon": "✨",
            "desc": "Xonadon chatida xabaringiz oltin nur bilan ajralib turadi."
        }
    },
    {
        "tier": 5,
        "xp_required": 500,
        "free": {
            "type": "cosmetic_castle",
            "item_id": "skin_banner_direwolf",
            "name": "Shimol Bo'risi Qal'a Bayrog'i",
            "icon": "🚩",
            "desc": "Qal'a minorasiga ilinadigan gotik bayroq."
        },
        "premium": {
            "type": "frame",
            "item_id": "frame_runic_iron",
            "name": "Runa Temir Ramkasi",
            "icon": "🖼️",
            "desc": "Qadimiy birinchi insonlar runalari o'yilgan ramka."
        }
    },
    {
        "tier": 6,
        "xp_required": 600,
        "free": {
            "type": "convenience",
            "item_id": "conv_hospital_bandages",
            "name": "Qirollik Tabiblari Zaxirasi",
            "icon": "🩹",
            "desc": "Yarador askarlarning davolanish vaqtini 15 daqiqa qisqartiradi."
        },
        "premium": {
            "type": "vip_days",
            "item_id": "vip_noble_7d",
            "name": "7 Kunlik Noble VIP Obunasi",
            "icon": "👑",
            "desc": "Barcha interfeys qulayliklari va qora ro'yxat filtrlari."
        }
    },
    {
        "tier": 7,
        "xp_required": 700,
        "free": {
            "type": "title",
            "item_id": "title_vigilant",
            "name": "«Hushyor Soqchi» Unvoni",
            "icon": "👁️",
            "desc": "Qal'a devorlarida mudroq bilmas sardor."
        },
        "premium": {
            "type": "cosmetic_castle",
            "item_id": "skin_torch_blue_fire",
            "name": "Moviy Mash'alalar Qal'a Skini",
            "icon": "🔥",
            "desc": "Qal'a darchalari sirli moviy olovda charog'on bo'ladi."
        }
    },
    {
        "tier": 8,
        "xp_required": 800,
        "free": {
            "type": "badge",
            "item_id": "badge_brave_shield",
            "name": "«Matonat Qalqoni» Nishoni",
            "icon": "🛡️",
            "desc": "Mavsumiy yutuqlar profilida ko'rinadi."
        },
        "premium": {
            "type": "frame",
            "item_id": "frame_emerald_scales",
            "name": "Zumrad Ajdar Tangalari Ramkasi",
            "icon": "🐉",
            "desc": "Zumrad rangli yaltiroq ajdaho terisi ramkasi."
        }
    },
    {
        "tier": 9,
        "xp_required": 900,
        "free": {
            "type": "convenience",
            "item_id": "conv_citadel_scrolls",
            "name": "Sitadel Qadimiy Bitiklari",
            "icon": "📜",
            "desc": "Viktorinada 1 marta xato qilishdan sug'urta qiladi."
        },
        "premium": {
            "type": "title",
            "item_id": "title_dragon_whisperer",
            "name": "«Ajdarlar Sirri Donishmandi»",
            "icon": "🔮",
            "desc": "Valiriya tilsimlarini tushunuvchi lord unvoni."
        }
    },
    {
        "tier": 10,
        "xp_required": 1000,
        "free": {
            "type": "frame",
            "item_id": "frame_silver_vanguard",
            "name": "Kumush Avangard Ramkasi",
            "icon": "🖼️",
            "desc": "O'rta mavsumga yetib kelgan barcha faol lordlarga bepul!"
        },
        "premium": {
            "type": "cosmetic_castle",
            "item_id": "castle_ice",
            "name": "❄️ Shimoliy Muz Qasri Skini",
            "icon": "🏰",
            "desc": "Abadiy qor va muz kristallari bilan qoplangan muazzam qasr!"
        }
    },
    {
        "tier": 11,
        "xp_required": 1100,
        "free": {
            "type": "convenience",
            "item_id": "conv_bank_safe_pass",
            "name": "Temir Bank Omonat Imtiyozi",
            "icon": "🏦",
            "desc": "Depozit foizidan olinadigan komissiyani 0% ga tushiradi."
        },
        "premium": {
            "type": "effect",
            "item_id": "effect_frost_mist",
            "name": "Muzli Tuman Xabar Effekti",
            "icon": "❄️",
            "desc": "Xabarlaringiz ortidan oppoq sovuq tuman seli ergashadi."
        }
    },
    {
        "tier": 12,
        "xp_required": 1200,
        "free": {
            "type": "title",
            "item_id": "title_storm_born_fighter",
            "name": "«Bo'ronlar Yengilmasi» Unvoni",
            "icon": "⛈️",
            "desc": "Qattiq to'fon faslida ham sharaf bilan kurashgan lord."
        },
        "premium": {
            "type": "badge",
            "item_id": "badge_golden_lion_crest",
            "name": "Qadimiy Oltin Arslon Gerbi",
            "icon": "🦁",
            "desc": "Profil tepasida porlab turuvchi qadimiy shohona gerb."
        }
    },
    {
        "tier": 13,
        "xp_required": 1300,
        "free": {
            "type": "convenience",
            "item_id": "conv_market_courier",
            "name": "Bozor Savdo Elchisi",
            "icon": "🐫",
            "desc": "Savdo e'lonini 1 kun davomida eng yuqori qatorda ushlab turadi."
        },
        "premium": {
            "type": "frame",
            "item_id": "frame_crimson_fury",
            "name": "Qonli Qahr Ramkasi",
            "icon": "🔥",
            "desc": "Olovli Caraxes rangidagi qizil naqshli ramka."
        }
    },
    {
        "tier": 14,
        "xp_required": 1400,
        "free": {
            "type": "badge",
            "item_id": "badge_council_advisor",
            "name": "«Kengash Maslahatchisi» Nishoni",
            "icon": "🏛️",
            "desc": "Qirollik maslahatlarida faol ishtirok etgan lord belgisi."
        },
        "premium": {
            "type": "vip_days",
            "item_id": "vip_noble_14d",
            "name": "14 Kunlik Noble VIP Obunasi",
            "icon": "👑",
            "desc": "Ikki haftalik barcha qulayliklar va premium profil imkoniyati."
        }
    },
    {
        "tier": 15,
        "xp_required": 1500,
        "free": {
            "type": "cosmetic_castle",
            "item_id": "skin_gates_iron_spikes",
            "name": "Temir Tikanli Darvoza Skini",
            "icon": "🚪",
            "desc": "Qal'a bosh darvozasiga temir tikanlar va mustahkam zanjirlar."
        },
        "premium": {
            "type": "cosmetic_dragon",
            "item_id": "dragon_adult_crimson",
            "name": "🔥 Qizil Qon (Caraxes) Ajdaho Skini",
            "icon": "🐉",
            "desc": "Ajdahongizni olovrang qizil qahrli ko'rinishga almashtiradi!"
        }
    },
    {
        "tier": 16,
        "xp_required": 1600,
        "free": {
            "type": "convenience",
            "item_id": "conv_spy_cloak",
            "name": "Qora Tungi Plash",
            "icon": "🥷",
            "desc": "1 ta josuslik amaliyotida ushlanish xavfini 50% ga kamaytiradi."
        },
        "premium": {
            "type": "title",
            "item_id": "title_shadow_king",
            "name": "«Soyalar Hukmdori» Unvoni",
            "icon": "🌑",
            "desc": "Xufiya strategiyalar ustasi bo'lgan oliy lord unvoni."
        }
    },
    {
        "tier": 17,
        "xp_required": 1700,
        "free": {
            "type": "convenience",
            "item_id": "conv_citadel_compass",
            "name": "Meyster Sayyoh Kompasi",
            "icon": "🧭",
            "desc": "Vesteros xaritasidagi barcha hududlar daromadini taqqoslash qulayligi."
        },
        "premium": {
            "type": "effect",
            "item_id": "effect_dragon_smoke",
            "name": "Ajdaho Tutuni Xabar Effekti",
            "icon": "💨",
            "desc": "Xabarlaringiz ustida ajdaho nafasi tutuni hilpiraydi."
        }
    },
    {
        "tier": 18,
        "xp_required": 1800,
        "free": {
            "type": "badge",
            "item_id": "badge_high_veteran",
            "name": "«Oliy Faxriy Lord» Nishoni",
            "icon": "🎖️",
            "desc": "Mavsumning so'nggi bosqichigacha mardonavor kurashgan jangchi."
        },
        "premium": {
            "type": "frame",
            "item_id": "frame_dragon_gold_crown",
            "name": "Ajdaho Shohona Toj Ramkasi",
            "icon": "👑",
            "desc": "Toza oltindan ishlangan, ajdaho panjalari ushlab turgan shohona ramka."
        }
    },
    {
        "tier": 19,
        "xp_required": 1900,
        "free": {
            "type": "title",
            "item_id": "title_westeros_legend",
            "name": "«Vesteros Afsonasi» Unvoni",
            "icon": "🌟",
            "desc": "Barcha bepul tierlarni bosib o'tgan fidoyi lord unvoni!"
        },
        "premium": {
            "type": "cosmetic_castle",
            "item_id": "castle_golden",
            "name": "🏰 Kasterli Qoyasi Oltin Saroyi Skini",
            "icon": "👑",
            "desc": "Zarhal gumbazlar va marmar ustunli afsonaviy boylik saroyi!"
        }
    },
    {
        "tier": 20,
        "xp_required": 2000,
        "free": {
            "type": "frame",
            "item_id": "frame_iron_throne_conqueror",
            "name": "🏆 20-Tier G'alaba Ramkasi",
            "icon": "⚔️",
            "desc": "Mavsum chiptasini to'liq yakunlagan har bir o'yinchiga oliy mukofot!"
        },
        "premium": {
            "type": "cosmetic_dragon",
            "item_id": "dragon_adult_golden",
            "name": "🌟 Quyosh Nuri (Sunfyre) Oltin Ajdaho Skini",
            "icon": "🐉",
            "desc": "Butun Vesterosda tengi yo'q, nurlanuvchi oltin ajdar terisi!"
        }
    }
]


# ============================================================
# 6. MAVSUM OXIRIDAGI NATIJA MUKOFOROTLARI (TOP LORDS & GUILDS)
# Idempotent (takrorlanmasdan bir marta beriladi)
# ============================================================
SEASON_END_RANK_REWARDS = {
    "rank_1": {
        "title": "👑 Temir Taxt Sohibi (Mavsum Chempioni)",
        "frame": "frame_sovereign",
        "castle_skin": "castle_valyrian",
        "dragon_skin": "dragon_adult_golden",
        "gold_starter": 20_000,
        "vip_days": 60,
    },
    "top_3": {
        "title": "⚔️ Buyuk Qirollik Gersogi",
        "frame": "frame_dragon_gold_crown",
        "castle_skin": "castle_golden",
        "gold_starter": 10_000,
        "vip_days": 30,
    },
    "top_10": {
        "title": "🛡️ Vesteros Oliy Ritsari",
        "frame": "frame_silver_vanguard",
        "gold_starter": 5_000,
        "vip_days": 15,
    },
    "top_100": {
        "title": "🎖️ Mavsum Faxriysi",
        "frame": "frame_valyrian_bronze",
        "gold_starter": 2_500,
        "vip_days": 7,
    },
    "participant": {
        "title": "🗡️ Mavsum Qahramoni",
        "gold_starter": 1_000,
        "vip_days": 0,
    }
}

POINTS_WEIGHTS = SeasonPointsWeights()
SOFT_RESET = SoftResetRules()
