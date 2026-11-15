import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# .env faylini yuklash
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ============================================================
# ASOSIY SOZLAMALAR
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# PostgreSQL yoki SQLite (PostgreSQL o'rnatilmagan bo'lsa aiosqlite ishlaydi)
DEFAULT_DB_PATH = BASE_DIR / "got_mmorpg.db"
if os.path.exists("/var/data"):
    DEFAULT_DB_PATH = Path("/var/data/got_mmorpg.db")
elif os.path.exists("/data"):
    DEFAULT_DB_PATH = Path("/data/got_mmorpg.db")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}")

# Render, Supabase, Neon va boshqa bulutli provayderlar taqdim etadigan postgres:// havolasini asinxron asyncpg ga moslash
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Neon / asyncpg SSL moslashuvlari (asyncpg sslmode va channel_binding parametrlarini to'g'irlash)
if "asyncpg" in DATABASE_URL:
    if "sslmode=require" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("sslmode=require", "ssl=require")
    if "&channel_binding=require" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("&channel_binding=require", "")
    if "?channel_binding=require&" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("?channel_binding=require&", "?")
    if "?channel_binding=require" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("?channel_binding=require", "")

# Bosh Administrator / Bot Egasi Telegram ID si (o'zgarmas)
OWNER_ID = 7689627859

# Admin Telegram ID lari - .env dagi ADMIN_IDS dan o'qiladi (config.py ga qayta yozilmaydi)
def _load_admin_ids_from_env() -> list:
    raw = os.getenv("ADMIN_IDS", "")
    ids = [int(OWNER_ID)]
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                val = int(part)
                if val not in ids:
                    ids.append(val)
    return ids

ADMIN_IDS = _load_admin_ids_from_env()


def is_admin(user_id: Optional[int]) -> bool:
    """Foydalanuvchi ID si adminlar ro'yxatida bor-yo'qligini tekshirish."""
    try:
        if user_id is None:
            return False
        uid = int(user_id)
        return uid in [int(x) for x in ADMIN_IDS] or uid == int(OWNER_ID)
    except Exception:
        return False

# Xatolar, baglar va tizim signallari yuboriladigan yopiq guruh chat ID si
ERROR_CHAT_ID: Optional[int] = None
_raw_error_chat = os.getenv("ERROR_CHAT_ID", "").strip()
if _raw_error_chat:
    try:
        ERROR_CHAT_ID = int(_raw_error_chat)
    except ValueError:
        pass

# ============================================================
# TELEGRAM MINI APP & API SOZLAMALARI
# ============================================================
MINI_APP_URL = os.getenv("MINI_APP_URL", os.getenv("RENDER_EXTERNAL_URL", "https://westeros-bot.onrender.com"))
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))
# 2-QADAM: Mini App yoqilganlik bayrog'i (False bo'lsa uvicorn ishga tushmaydi, menyuda faqat bot tugmalari chiqadi)
ENABLE_MINIAPP = os.getenv("ENABLE_MINIAPP", "false").strip().lower() in ("true", "1", "yes")

# Mini App asosiy interfeys holati (Agar ENABLE_MINIAPP=False bo'lsa qat'iy False)
MINIAPP_PRIMARY_INTERFACE = False if not ENABLE_MINIAPP else (os.getenv("MINIAPP_PRIMARY_INTERFACE", "true").lower() in ("true", "1", "yes"))


def get_miniapp_url(startapp: Optional[str] = None) -> str:
    """Telegram Mini App havolasi va parametrli deep-link generatori"""
    base = (MINI_APP_URL or "https://westeros-bot.onrender.com").rstrip("/")
    if startapp:
        return f"{base}?startapp={startapp}"
    return base



def save_admin_id(telegram_id: int):
    """Yangi admin qo'shish va saqlash"""
    if telegram_id not in ADMIN_IDS:
        ADMIN_IDS.append(telegram_id)
        _persist_admins()


def remove_admin_id(telegram_id: int):
    """Adminni ro'yxatdan o'chirish (Bosh egasi o'chirilmaydi)"""
    if telegram_id in ADMIN_IDS and telegram_id != OWNER_ID:
        ADMIN_IDS.remove(telegram_id)
        _persist_admins()


def _persist_admins():
    """ADMIN_IDS ni .env fayliga xavfsiz saqlash (config.py fayliga qayta yozilmaydi)"""
    try:
        env_file = BASE_DIR / ".env"
        admin_str = ",".join(str(x) for x in ADMIN_IDS)
        if env_file.exists():
            text = env_file.read_text(encoding="utf-8")
            import re
            if re.search(r"^ADMIN_IDS=", text, flags=re.MULTILINE):
                new_text = re.sub(r"^ADMIN_IDS=.*", f"ADMIN_IDS={admin_str}", text, flags=re.MULTILINE)
            else:
                new_text = text.rstrip() + f"\nADMIN_IDS={admin_str}\n"
            env_file.write_text(new_text, encoding="utf-8")
        os.environ["ADMIN_IDS"] = admin_str
    except Exception as e:
        print(f"Error persisting admins to .env: {e}")

# ============================================================
# KUNLIK LIMITLAR & BALANS (core/balance.py orqali markazlashtirilgan)
# ============================================================
from core.balance import (
    ECONOMY,
    DAILY_LIMITS,
    PROTECTION,
    UNITS_CONFIG,
    STREAK_REWARDS_CONFIG,
)

DAILY_QUIZ_LIMIT = int(os.getenv("DAILY_QUIZ_LIMIT", str(DAILY_LIMITS.daily_quiz_limit)))
DAILY_COUNCIL_LIMIT = int(os.getenv("DAILY_COUNCIL_LIMIT", str(DAILY_LIMITS.daily_council_limit)))
DAILY_SECRET_QUEST_LIMIT = int(os.getenv("DAILY_SECRET_QUEST_LIMIT", str(DAILY_LIMITS.daily_secret_quest_limit)))
DAILY_DUEL_LIMIT = int(os.getenv("DAILY_DUEL_LIMIT", str(DAILY_LIMITS.daily_duel_limit)))

# ============================================================
# O'YIN IQTISODIYOTI VA BALANS
# ============================================================

# Yangi o'yinchi boshlang'ich resurslari
STARTING_GOLD = ECONOMY.starting_gold
STARTING_FOOD = ECONOMY.starting_food
STARTING_IRON = ECONOMY.starting_iron

# Boshlang'ich Tinchlik Qalqoni (soatlarda: 72 soat = 3 kun)
PEACE_SHIELD_HOURS = PROTECTION.newbie_peace_shield_hours

# Boshlang'ich armiya
STARTING_INFANTRY = 100
STARTING_ARCHERS = 50
STARTING_CAVALRY = 25
STARTING_SPEARMEN = 25

# Askarlarning oziq-ovqat iste'moli (soatiga 1 ta askar uchun)
UPKEEP_FOOD_PER_INFANTRY = UNITS_CONFIG["infantry"]["food_upkeep"]
UPKEEP_FOOD_PER_ARCHER = UNITS_CONFIG["archers"]["food_upkeep"]
UPKEEP_FOOD_PER_CAVALRY = UNITS_CONFIG["cavalry"]["food_upkeep"]
UPKEEP_FOOD_PER_SPEARMAN = UNITS_CONFIG["spearmen"]["food_upkeep"]
UPKEEP_FOOD_PER_SPECIAL = UNITS_CONFIG["special_troops"]["food_upkeep"]

# Yurish tezligi (hududlar orasidagi bazaviy daqiqa - mudofaa reaksiyasi uchun)
BASE_MARCH_MINUTES = int(os.getenv("BASE_MARCH_MINUTES", "5"))

# ============================================================
# LAVOZIMLAR VA ROLLARI
# ============================================================

RANKS = {
    "king": {"name": "👑 King / Lord", "level_req": 1, "power": 100},
    "commander": {"name": "⚔️ Harbiy Qo‘mondon", "level_req": 1, "power": 80},
    "knight": {"name": "🛡️ Ritsar", "level_req": 1, "power": 60},
    "captain": {"name": "🏹 Kapitan", "level_req": 1, "power": 40},
    "member": {"name": "👤 A’zo", "level_req": 1, "power": 20},
}

# ============================================================
# YORDAMCHI FUNKSIYALAR
# ============================================================

def escape_md(text: str) -> str:
    """Telegram Markdown formatida maxsus belgilarni tozalash"""
    if not text:
        return ""
    for ch in ("\\", "_", "*", "`", "[", "]", "(", ")", "~", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        text = str(text).replace(ch, "\\" + ch)
    return text


# ============================================================
# DONATE & VIP TIZIMI REKVIZITLARI
# Standart qiymatlar olib tashlandi: faqat .env yoki Admin Panel sozlamasidan o'qiladi
# ============================================================
DONATE_CARD_NUMBER = os.getenv("DONATE_CARD_NUMBER", "")
DONATE_CARD_HOLDER = os.getenv("DONATE_CARD_HOLDER", "")

# ============================================================
# RASMIY HAMJAMIYAT (KANAL & GURUH)
# ============================================================
COMMUNITY_CHANNEL_URL = os.getenv("COMMUNITY_CHANNEL_URL", "https://t.me/northremembers1")
COMMUNITY_GROUP_URL = os.getenv("COMMUNITY_GROUP_URL", "https://t.me/northremember2")
COMMUNITY_CHANNEL_ID = os.getenv("COMMUNITY_CHANNEL_ID", "@northremembers1")
COMMUNITY_GROUP_ID = os.getenv("COMMUNITY_GROUP_ID", "@northremember2")

# ============================================================
# DONAT BONUSLARI SOZLAMALARI (Markazlashtirilgan)
# ============================================================
DONATE_BONUSES_CONFIG = {
    "first_donate_bonus_pct": 20,  # Birinchi tasdiqlangan donatga +20% qo'shimcha resurs bonusi
    "bulk_package_bonus_pct": {
        "lord": 10,
        "dragonlord": 15,
        "sovereign": 25,
    },
}

# ============================================================
# AFSONAVIY DONATE / VIP TARIFLARI (0 Pay-To-Win: 5 ta rasmiy Homiy paketi)
# ============================================================
ACTIVE_DONATE_TIERS = ["noble", "knight", "lord", "dragonlord", "sovereign"]

DONATE_TIERS = {
    "noble": {
        "id": "noble",
        "name": "🛡️ Noble Homiy (30 kun)",
        "subtitle": "Profil fotosurati, Noble nishoni va bir martalik resurs",
        "category": "vip_pass",
        "price_uzs": 10000,
        "price_label": "10,000 so'm",
        "gold": 6000,
        "food": 15000,
        "iron": 6000,
        "infantry": 0,
        "archers": 0,
        "cavalry": 0,
        "spearmen": 0,
        "special_troops": 0,
        "catapults": 0,
        "siege_towers": 0,
        "shield_hours": 0,
        "prestige": 0,
        "wildfire": 0,
        "duration_days": 30,
        "daily_bonus_gold": 400,
        "daily_bonus_food": 900,
        "daily_bonus_iron": 300,
        "vip_tier": "noble",
        "avatar_frame": "frame_iron",
        "title": "Qirol Qo'riqchisi",
        "cosmetics": ["frame_iron", "title_kingsguard"],
        "studio_perks": ["photo", "badge_noble"],
        "description": (
            "• 🛡️ **30 kunlik Noble VIP:** Profil fotosurati va Noble nishoni\n"
            "• 🖼️ **Umrbod kosmetika:** Temir Taxt ramkasi va Qirol Qo'riqchisi unvoni\n"
            "• 🎁 **Darhol xazina:** +6,000 🪙 Oltin, +15,000 🌾 Bug'doy, +6,000 ⛓️ Temir\n"
            "• 📅 **30 kunlik Kunlik VIP Sovg'a:** Har kuni +400 🪙, +900 🌾, +300 ⛓️\n"
            "• ⚖️ *0 Pay-To-Win: askar, ajdaho, prestige yoki doimiy daromad bonusi yo'q*"
        ),
    },
    "premium_pass": {
        "id": "premium_pass",
        "name": "👑 Premium Season Pass (30 kun)",
        "subtitle": "Mavsumiy Premium Chipta + Yoqimli Resurs va Kunlik Bonuslar",
        "category": "vip_pass",
        "price_uzs": 20000,
        "price_label": "20,000 so'm",
        "gold": 2500,
        "food": 5000,
        "iron": 1500,
        "infantry": 0,
        "archers": 0,
        "cavalry": 0,
        "spearmen": 0,
        "special_troops": 0,
        "catapults": 0,
        "siege_towers": 0,
        "shield_hours": 0,
        "prestige": 50,
        "wildfire": 0,
        "duration_days": 30,
        "daily_bonus_gold": 300,
        "daily_bonus_food": 600,
        "daily_bonus_iron": 200,
        "vip_tier": "noble",
        "avatar_frame": "frame_valyrian",
        "title": "Mavsum Aslzodasi",
        "is_season_pass": True,
        "description": (
            "• 👑 **Premium Status (30 kun):** Maxsus ramka («Valyriya Po'lati»), nishon va «Mavsum Aslzodasi» unvoni\n"
            "• 🎁 **Darhol beriladigan yoqimli bonus:** +2,500 🪙 Oltin, +5,000 🌾 Bug'doy, +1,500 ⛓️ Temir, +50 ⭐ Nufuz\n"
            "• 📅 **Kunlik Qo'shimcha Bonus (30 kun):** Har kuni kirganda +300 🪙 Oltin, +600 🌾 Bug'doy, +200 ⛓️ Temir\n"
            "• 🏆 **Season Pass:** Barcha 20 ta pullik (Premium) pog'ona mukofotlarini ochish huquqi!"
        ),
    },
    "vip_noble": {
        "id": "vip_noble",
        "name": "💎 Noble VIP (30 kun)",
        "subtitle": "Zodagonlar imtiyozi va kunlik qulayliklar",
        "category": "vip_pass",
        "price_uzs": 15000,
        "price_label": "15,000 so'm",
        "gold": 1500,
        "food": 3000,
        "iron": 1000,
        "infantry": 0,
        "archers": 0,
        "cavalry": 0,
        "spearmen": 0,
        "special_troops": 0,
        "catapults": 0,
        "siege_towers": 0,
        "shield_hours": 0,
        "prestige": 30,
        "wildfire": 0,
        "duration_days": 30,
        "daily_bonus_gold": 200,
        "daily_bonus_food": 400,
        "daily_bonus_iron": 100,
        "vip_tier": "noble",
        "avatar_frame": "frame_royal_gold",
        "title": "Vesteros Zodagoni",
        "description": (
            "• 💎 **Noble VIP Statusi (30 kun):** 1-bosishda barcha soliqlarni yig'ish, zarhal profil nishoni\n"
            "• 🎁 **Darhol beriladigan bonus:** +1,500 🪙 Oltin, +3,000 🌾 Bug'doy, +1,000 ⛓️ Temir, +30 ⭐ Nufuz\n"
            "• 📅 **Kunlik Qo'shimcha Bonus (30 kun):** Har kuni +200 🪙 Oltin, +400 🌾 Bug'doy, +100 ⛓️ Temir\n"
            "• 👑 **Faxriy Unvon:** «Vesteros Zodagoni» va Qirollik Oltin ramkasi"
        ),
    },
    "starter_pack": {
        "id": "starter_pack",
        "name": "🎁 Starter Pack (Boshlang'ich)",
        "subtitle": "Yangi Lordlar uchun foydali start va 7 kunlik VIP",
        "category": "resources",
        "price_uzs": 5000,
        "price_label": "5,000 so'm",
        "gold": 1000,
        "food": 2000,
        "iron": 500,
        "infantry": 0,
        "archers": 0,
        "cavalry": 0,
        "spearmen": 0,
        "special_troops": 0,
        "catapults": 0,
        "siege_towers": 0,
        "shield_hours": 0,
        "prestige": 20,
        "wildfire": 0,
        "duration_days": 7,
        "daily_bonus_gold": 150,
        "daily_bonus_food": 300,
        "daily_bonus_iron": 100,
        "vip_tier": "noble",
        "avatar_frame": "frame_valyrian",
        "title": "Valyriya Ritsari",
        "is_starter_pack": True,
        "description": (
            "• 🎁 **Darhol beriladigan bonus:** +1,000 🪙 Oltin, +2,000 🌾 Bug'doy, +500 ⛓️ Temir, +20 ⭐ Nufuz\n"
            "• 👑 **7 kunlik VIP Status:** Kunlik qo'shimcha bonuslar va qulayliklar\n"
            "• 🖼️ **Eksklyuziv Kosmetika:** «Valyriya Po'lati» ramkasi va «Valyriya Ritsari» unvoni"
        ),
    },
    "knight": {
        "id": "knight",
        "name": "🗡️ Ritsar Homiy (30 kun)",
        "subtitle": "Olov temasi, effekt va 1 kunlik resurs zaxirasi",
        "category": "vip_pass",
        "price_uzs": 25000,
        "price_label": "25,000 so'm",
        "gold": 12000,
        "food": 30000,
        "iron": 12000,
        "infantry": 0,
        "archers": 0,
        "cavalry": 0,
        "spearmen": 0,
        "special_troops": 0,
        "catapults": 0,
        "siege_towers": 0,
        "shield_hours": 0,
        "prestige": 0,
        "wildfire": 0,
        "duration_days": 30,
        "daily_bonus_gold": 800,
        "daily_bonus_food": 1800,
        "daily_bonus_iron": 600,
        "vip_tier": "knight",
        "avatar_frame": "frame_flame",
        "title": "Qirol Qo'riqchisi",
        "cosmetics": ["frame_iron", "title_kingsguard", "frame_flame", "effect_fire"],
        "studio_perks": ["photo", "badge_noble", "theme_fire"],
        "description": (
            "• 🗡️ **30 kunlik Ritsar VIP:** Noble imtiyozlari + Olov profil temasi\n"
            "• 🖼️ **Umrbod kosmetika:** Olov ramkasi, Olov effekti va oldingi kosmetikalar\n"
            "• 🎁 **Darhol xazina:** +12,000 🪙 Oltin, +30,000 🌾 Bug'doy, +12,000 ⛓️ Temir\n"
            "• 📅 **30 kunlik Kunlik VIP Sovg'a:** Har kuni +800 🪙, +1,800 🌾, +600 ⛓️\n"
            "• ⚖️ *0 Pay-To-Win: askar, ajdaho, prestige yoki doimiy daromad bonusi yo'q*"
        ),
    },
    "speedup_pack": {
        "id": "speedup_pack",
        "name": "⚡ Tezlashtirish Paketi (Qurilish va Parvarish)",
        "subtitle": "Qurilish, tuxum ochirish va ajdar tiklanishini tezlashtirish",
        "category": "speedup",
        "price_uzs": 15000,
        "price_label": "15,000 so'm",
        "gold": 6000,
        "food": 18000,
        "iron": 8000,
        "infantry": 0,
        "archers": 0,
        "cavalry": 0,
        "spearmen": 0,
        "special_troops": 0,
        "catapults": 0,
        "siege_towers": 0,
        "shield_hours": 0,
        "prestige": 60,
        "wildfire": 0,
        "instant_dragon_heal": True,
        "instant_egg_hatch_boost": True,
        "description": (
            "• ⚡ **Ajdar Tezlashtirish:** Tuxumdagi ajdarni darhol ochirish va barcha ajdarlarning to'qlik/charchog'ini 100% tiklash\n"
            "• 🏗️ **Qurilish Zaxirasi:** +6,000 🪙 Oltin, +8,000 ⛓️ Temir (Kon va Tegirmonni darhol ko'tarish uchun)\n"
            "• 🥩 **Parvarish Ozuqasi:** +18,000 🌾 Bug'doy\n"
            "• ⭐ Prestige: +60 shon-sharaf"
        ),
    },
    "lord": {
        "id": "lord",
        "name": "🏰 Lord Homiy (30 kun)",
        "subtitle": "Video/GIF, shior, gimn, gerb emoji, Muz & Olov temalari",
        "category": "vip_pass",
        "price_uzs": 45000,
        "price_label": "45,000 so'm",
        "gold": 18000,
        "food": 45000,
        "iron": 18000,
        "infantry": 0,
        "archers": 0,
        "cavalry": 0,
        "spearmen": 0,
        "special_troops": 0,
        "catapults": 0,
        "siege_towers": 0,
        "shield_hours": 0,
        "prestige": 0,
        "wildfire": 0,
        "duration_days": 30,
        "daily_bonus_gold": 1200,
        "daily_bonus_food": 2700,
        "daily_bonus_iron": 900,
        "vip_tier": "lord",
        "avatar_frame": "frame_flame",
        "title": "Qirol Qo'riqchisi",
        "cosmetics": ["frame_iron", "title_kingsguard", "frame_flame", "effect_fire", "castle_ice", "effect_ice"],
        "studio_perks": ["photo", "badge_noble", "theme_fire", "theme_ice", "video", "status", "audio", "crest"],
        "description": (
            "• 🏰 **30 kunlik Lord VIP:** Video/GIF profil, shaxsiy shior, fon musiqasi/gimn, gerb emoji\n"
            "• 🎨 **Umrbod kosmetika va temalar:** Muz & Olov temalari, Muz Qasri, Muz effekti\n"
            "• 🎁 **Darhol xazina:** +18,000 🪙 Oltin, +45,000 🌾 Bug'doy, +18,000 ⛓️ Temir\n"
            "• 📅 **30 kunlik Kunlik VIP Sovg'a:** Har kuni +1,200 🪙, +2,700 🌾, +900 ⛓️\n"
            "• ⚖️ *0 Pay-To-Win: askar, ajdaho, prestige yoki doimiy daromad bonusi yo'q*"
        ),
    },
    "dragonlord": {
        "id": "dragonlord",
        "name": "🐉 Valyriya Homiy (30 kun)",
        "subtitle": "Valyriya temasi, shaxsiy g'alaba xabari va ajdar/qal'a terilari",
        "category": "vip_pass",
        "price_uzs": 70000,
        "price_label": "70,000 so'm",
        "gold": 24000,
        "food": 60000,
        "iron": 24000,
        "infantry": 0,
        "archers": 0,
        "cavalry": 0,
        "spearmen": 0,
        "special_troops": 0,
        "catapults": 0,
        "siege_towers": 0,
        "shield_hours": 0,
        "prestige": 0,
        "wildfire": 0,
        "duration_days": 30,
        "daily_bonus_gold": 1600,
        "daily_bonus_food": 3600,
        "daily_bonus_iron": 1200,
        "vip_tier": "dragonlord",
        "avatar_frame": "frame_flame",
        "title": "Ajdar Chavandozi",
        "cosmetics": [
            "frame_iron", "title_kingsguard", "frame_flame", "effect_fire",
            "castle_ice", "effect_ice", "dragon_crimson", "castle_valyrian", "title_dragonrider",
        ],
        "studio_perks": ["photo", "badge_noble", "theme_fire", "theme_ice", "theme_valyrian", "video", "status", "audio", "crest", "victory_message"],
        "description": (
            "• 🐉 **30 kunlik Valyriya VIP:** Lord imtiyozlari + Valyriya temasi + Shaxsiy g'alaba xabari\n"
            "• 🖼️ **Umrbod kosmetika:** Qonli Ajdar terisi, Valiriya Qora Bazalt qasri, Ajdar Chavandozi unvoni\n"
            "• 🎁 **Darhol xazina:** +24,000 🪙 Oltin, +60,000 🌾 Bug'doy, +24,000 ⛓️ Temir\n"
            "• 📅 **30 kunlik Kunlik VIP Sovg'a:** Har kuni +1,600 🪙, +3,600 🌾, +1,200 ⛓️\n"
            "• ⚖️ *0 Pay-To-Win: askar, ajdaho, prestige yoki doimiy daromad bonusi yo'q*"
        ),
    },
    "sovereign": {
        "id": "sovereign",
        "name": "👑 Qirollik Homiy (30 kun)",
        "subtitle": "Barcha bezaklar, Qal'a nomi, Qirollik Farmoni va doimiy nishon",
        "category": "vip_pass",
        "price_uzs": 100000,
        "price_label": "100,000 so'm",
        "gold": 36000,
        "food": 90000,
        "iron": 36000,
        "infantry": 0,
        "archers": 0,
        "cavalry": 0,
        "spearmen": 0,
        "special_troops": 0,
        "catapults": 0,
        "siege_towers": 0,
        "shield_hours": 0,
        "prestige": 0,
        "wildfire": 0,
        "duration_days": 30,
        "daily_bonus_gold": 2400,
        "daily_bonus_food": 5400,
        "daily_bonus_iron": 1800,
        "vip_tier": "sovereign",
        "avatar_frame": "frame_sovereign",
        "title": "Temir Taxt Egasi",
        "cosmetics": [
            "frame_iron", "title_kingsguard", "frame_flame", "effect_fire",
            "castle_ice", "effect_ice", "dragon_crimson", "castle_valyrian", "title_dragonrider",
            "frame_sovereign", "title_ironthrone", "castle_golden", "dragon_golden",
        ],
        "permanent_badges": ["royal_patron"],
        "studio_perks": [
            "photo", "badge_noble", "theme_fire", "theme_ice", "theme_gold", "theme_shadow", "theme_valyrian",
            "video", "status", "audio", "crest", "victory_message", "castle_name", "royal_decree",
        ],
        "description": (
            "• 👑 **30 kunlik Qirollik VIP:** Barcha studiya imkoniyatlari, barcha 5 ta tema, Qal'a nomi, Qirollik Farmoni (haftada 1 marta)\n"
            "• 🏅 **Doimiy Nishon:** «Qirollik Homiysi» nishoni VIP tugagach ham profilida qoladi\n"
            "• 🖼️ **Barcha Umrbod Kosmetikalar:** Oltin Saroy, Oltin Ajdar, Sovereign ramkasi va Temir Taxt Egasi unvoni\n"
            "• 🎁 **Darhol xazina:** +36,000 🪙 Oltin, +90,000 🌾 Bug'doy, +36,000 ⛓️ Temir\n"
            "• 📅 **30 kunlik Kunlik VIP Sovg'a:** Har kuni +2,400 🪙, +5,400 🌾, +1,800 ⛓️\n"
            "• ⚖️ *0 Pay-To-Win: askar, ajdaho, prestige yoki doimiy daromad bonusi yo'q*"
        ),
    },
}

# ============================================================
# MARKAZLASHTIRILGAN PREMIUM PASS MUKOFOTLARI SOZLAMASI
# ============================================================
PREMIUM_PASS_CONFIG = DONATE_TIERS["premium_pass"]

# ============================================================
# 5-QADAM: AJDARLAR KONFIGURATSIYASI (6 XIL AJDAR VA BALANS)
# ============================================================
DRAGON_SPECIES_CONFIG = {
    "Arrax": {
        "name": "Arrax",
        "grade": "C",
        "title": "🤍 Arrax — Marvarid Chaqqon Ajdar",
        "lore": "Yosh va chaqqon osmon razvedkachisi, yuqori tezlikda olov purkaydi.",
        "price_gold": 15000,
        "price_iron": 10000,
        "price_food": 20000,
        "attack": 650,
        "defense": 450,
        "hp": 2500,
        "base_power": 1200,
        "max_level_power": 5200,
        "req_player_level": 3,
        "req_castle_level": 2,      # Qal'a (Ajdarlar uyasi) 2-daraja
        "req_iron_mine_level": 2,
        "req_grain_mill_level": 2,
        "hatch_hours": 2,
        "hatch_cost_gold": 3000,
        "hatch_cost_iron": 2500,
        "hatch_cost_food": 5000,
    },
    "Syrax": {
        "name": "Syrax",
        "grade": "B",
        "title": "💛 Syrax — Oltin Qirollik Ajdari",
        "lore": "Qirolicha Reyniraning zarhal qanotli, intizomli va sodiq jangovar ajdari.",
        "price_gold": 30000,
        "price_iron": 20000,
        "price_food": 40000,
        "attack": 1100,
        "defense": 800,
        "hp": 4200,
        "base_power": 2000,
        "max_level_power": 7800,
        "req_player_level": 5,
        "req_castle_level": 3,      # Qal'a (Ajdarlar uyasi) 3-daraja
        "req_iron_mine_level": 3,
        "req_grain_mill_level": 3,
        "hatch_hours": 4,
        "hatch_cost_gold": 5000,
        "hatch_cost_iron": 4000,
        "hatch_cost_food": 8000,
    },
    "Meleys": {
        "name": "Meleys",
        "grade": "B+",
        "title": "❤️ Meleys — Qizil Qirolicha",
        "lore": "Vesteros osmonidagi eng tezkor va shiddatli olov bo'roni.",
        "price_gold": 50000,
        "price_iron": 35000,
        "price_food": 65000,
        "attack": 1650,
        "defense": 1200,
        "hp": 6000,
        "base_power": 3000,
        "max_level_power": 10500,
        "req_player_level": 7,
        "req_castle_level": 3,      # Qal'a (Ajdarlar uyasi) 3-daraja
        "req_iron_mine_level": 4,
        "req_grain_mill_level": 4,
        "hatch_hours": 6,
        "hatch_cost_gold": 8000,
        "hatch_cost_iron": 6500,
        "hatch_cost_food": 12000,
    },
    "Caraxes": {
        "name": "Caraxes",
        "grade": "A",
        "title": "🩸 Caraxes — Qonli Bo'ron",
        "lore": "Shahzoda Deymonning janglarda chiniqqan, shafqatsiz va tajovuzkor ajdari.",
        "price_gold": 80000,
        "price_iron": 55000,
        "price_food": 100000,
        "attack": 2400,
        "defense": 1750,
        "hp": 8500,
        "base_power": 4400,
        "max_level_power": 14000,
        "req_player_level": 10,
        "req_castle_level": 4,      # Qal'a (Ajdarlar uyasi) 4-daraja
        "req_iron_mine_level": 5,
        "req_grain_mill_level": 5,
        "hatch_hours": 8,
        "hatch_cost_gold": 12000,
        "hatch_cost_iron": 10000,
        "hatch_cost_food": 18000,
    },
    "Vhagar": {
        "name": "Vhagar",
        "grade": "A+",
        "title": "⚡ Vhagar — Qadimgi Urushlar Afsonasi",
        "lore": "Yuzlab janglarni ko'rgan ulkan qanotli qal'a yemiruvchi ajdar.",
        "price_gold": 120000,
        "price_iron": 85000,
        "price_food": 150000,
        "attack": 3300,
        "defense": 2500,
        "hp": 12000,
        "base_power": 6200,
        "max_level_power": 18500,
        "req_player_level": 12,
        "req_castle_level": 4,      # Qal'a (Ajdarlar uyasi) 4-daraja
        "req_iron_mine_level": 6,
        "req_grain_mill_level": 6,
        "hatch_hours": 12,
        "hatch_cost_gold": 18000,
        "hatch_cost_iron": 15000,
        "hatch_cost_food": 28000,
    },
    "Balerion": {
        "name": "Balerion",
        "grade": "S",
        "title": "🖤 Balerion — Qora Qo'rqinch",
        "lore": "Eygon Fotihning qora olov purkovchi, Vesteros tarixidagi eng bahaybat ajdari.",
        "price_gold": 180000,
        "price_iron": 130000,
        "price_food": 220000,
        "attack": 4500,
        "defense": 3500,
        "hp": 16000,
        "base_power": 8500,
        "max_level_power": 25000,
        "req_player_level": 15,
        "req_castle_level": 5,      # Qal'a (Ajdarlar uyasi) 5-daraja
        "req_iron_mine_level": 8,
        "req_grain_mill_level": 8,
        "hatch_hours": 24,
        "hatch_cost_gold": 25000,
        "hatch_cost_iron": 20000,
        "hatch_cost_food": 40000,
    },
}

DRAGON_BALANCE_CONFIG = {
    "max_dragons_per_player": 2,        # Oddiy xarid orqali maksimal 2 ta (nasl bilan 3 ta)
    "max_dragons_with_breeding": 3,
    "max_level": 20,
    "min_hunger_for_battle": 30,        # 30% dan past bo'lsa yarador/och hisoblanadi, jangga kirmaydi
    "min_hunger_for_train": 40,         # Mashq uchun kamida 40% to'qlik kerak
    "battle_fatigue_hunger_loss": 25,   # Har bir urushdan so'ng -25% to'qlik/quvvat yo'qotadi
    "feed_base_food": 600,
    "feed_food_per_level": 150,
    "feed_hunger_restore": 35,
    "feed_power_gain_base": 40,
    "feed_power_gain_per_level": 10,
    "train_base_gold": 1200,
    "train_gold_per_level": 650,
    "train_base_iron": 900,
    "train_iron_per_level": 500,
    "train_base_food": 1500,
    "train_food_per_level": 800,
    "train_hunger_cost": 25,
    # Ajdarsiz o'yinchilar uchun qarshi taktika (Qal'a Chayonlari / Scorpion Ballista + Nayzador/Kamonchi):
    "scorpion_defense_per_castle_level": 0.08,   # Qal'a har darajasi ajdar zararini 8% kamaytiradi (5-darajada -40%)
    "spearmen_anti_dragon_factor": 0.00015,      # Har 1000 nayzador/kamonchi ajdar zararini qo'shimcha -15% qisqartiradi
    "max_anti_dragon_damage_reduction": 0.60,    # Maksimal 60% gacha ajdar zarbasini qaytarish mumkin!
}

BUILDINGS_CONFIG = {
    "iron_mine": {
        "id": "iron_mine",
        "name": "⛏️ Temir Koni",
        "max_level": 10,
        "gold_per_level": 400,
        "food_per_level": 250,
        "hourly_iron_per_level": 50,
        "description": "Soatlik temir qazib olishni oshiradi va yuqori toifali ajdarlarni ochadi.",
    },
    "grain_mill": {
        "id": "grain_mill",
        "name": "🌾 Don Tegirmoni",
        "max_level": 10,
        "gold_per_level": 350,
        "iron_per_level": 200,
        "hourly_food_per_level": 75,
        "description": "Soatlik bug'doy hosilini oshiradi va qo'shin/ajdarlarni oziqlantiradi.",
    },
    "castle_keep": {
        "id": "castle_keep",
        "name": "🏰 Qal'a Istehkomi, Ajdarlar Uyasi va Chayon Minoralari",
        "max_level": 5,
        "gold_per_level": 1000,
        "iron_per_level": 750,
        "defense_per_level": 300,
        "description": "Qal'a mudofaasini (+300), Ajdarlar uyasi sig'imini va ajdarga qarshi Chayon (Scorpion) ballistalarini kuchaytiradi (-8% ajdar zarari/daraja).",
    },
}

# ============================================================
# AI ASSISTANT ("KENGASH MASLAHATCHISI") CONFIGURATION
# ============================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("AI_API_KEY", "")).strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
AI_USER_DAILY_LIMIT = int(os.getenv("AI_USER_DAILY_LIMIT", "10"))
AI_VIP_DAILY_LIMIT = int(os.getenv("AI_VIP_DAILY_LIMIT", "20"))
AI_GLOBAL_DAILY_LIMIT = int(os.getenv("AI_GLOBAL_DAILY_LIMIT", "500"))
AI_MAX_RESPONSE_TOKENS = int(os.getenv("AI_MAX_RESPONSE_TOKENS", "450"))
AI_CACHE_TTL_SECONDS = int(os.getenv("AI_CACHE_TTL_SECONDS", "3600"))

# ============================================================
# 5-QADAM: REFERRAL CONFIGURATION
# ============================================================
REFERRAL_REWARD_REFERRER = {
    "gold": 1000,
    "food": 2000,
    "iron": 500,
    "prestige": 50,
}
REFERRAL_REWARD_NEW_PLAYER = {
    "gold": 500,
    "food": 1000,
    "iron": 250,
    "prestige": 20,
}

# ============================================================
# 5-QADAM: ACHIEVEMENTS CONFIGURATION (YUTUQLAR)
# ============================================================
ACHIEVEMENTS_CONFIG = {
    "first_win": {
        "code": "first_win",
        "title": "⚔️ Birinchi Qon",
        "desc": "Jang maydonida ilk bor dushmanni mag'lub eting",
        "gold": 500,
        "food": 1000,
        "iron": 200,
        "prestige": 30,
    },
    "dragon_hatch": {
        "code": "dragon_hatch",
        "title": "🐉 Ajdarlar Parvarishchisi",
        "desc": "Ilk bor ajdar tuxumini muvaffaqiyatli oching",
        "gold": 2000,
        "food": 3000,
        "iron": 1000,
        "prestige": 100,
    },
    "castle_lord": {
        "code": "castle_lord",
        "title": "🏰 Qal'a Hukmdori",
        "desc": "Westeros xaritasidagi birinchi qal'ani zabt eting",
        "gold": 1500,
        "food": 2500,
        "iron": 800,
        "prestige": 60,
    },
    "citadel_scholar": {
        "code": "citadel_scholar",
        "title": "📜 Sitadel Allomasi",
        "desc": "Viktorina savollariga 10 marta to'g'ri javob bering",
        "gold": 600,
        "food": 1000,
        "iron": 300,
        "prestige": 40,
    },
    "iron_banker": {
        "code": "iron_banker",
        "title": "🏦 Temir Sarmoyador",
        "desc": "Temir Bankka 1,000 dan ortiq oltin omonat qo'ying",
        "gold": 800,
        "food": 1200,
        "iron": 400,
        "prestige": 35,
    },
    "duel_master": {
        "code": "duel_master",
        "title": "🤺 Qilichbozlik Chempioni",
        "desc": "1v1 duellarda 5 marta g'alabaga erishing",
        "gold": 1200,
        "food": 1500,
        "iron": 600,
        "prestige": 70,
    },
    "guild_brother": {
        "code": "guild_brother",
        "title": "🛡️ Qardoshlik Qasamyodi",
        "desc": "Gildiyaga qo'shiling yoki yangi ittifoq tuzing",
        "gold": 500,
        "food": 1000,
        "iron": 250,
        "prestige": 25,
    },
    "referral_pioneer": {
        "code": "referral_pioneer",
        "title": "👥 Shonli Sarkarda",
        "desc": "Kamida bitta do'stingizni jangga taklif qiling",
        "gold": 1000,
        "food": 2000,
        "iron": 500,
        "prestige": 50,
    },
}

# ============================================================
# 6-QADAM: 1-MAVSUM G'OLIBLARI VA 2-MAVSUM SOZLAMALARI
# ============================================================
SEASON_1_LEGACY_WINNERS = {
    "winner_house_id": 15,
    "winner_house_name": "🐉 House Blackfyre",
    "king_name": "Liar (@NiclausMikaelson)",
    "top_warrior_name": "kozmunchoq 🐾 (@shaxnoza_0901)",
    "top_warrior_prestige": 62514,
    "top3": [
        {"rank": 1, "telegram_id": 5381961263, "name": "Liar (@NiclausMikaelson)", "house": "House Blackfyre", "prestige": 62514, "level": 10},
        {"rank": 2, "telegram_id": 8838680114, "name": "Bexruz (@Bexruz)", "house": "House Stark", "prestige": 750, "level": 5},
        {"rank": 3, "telegram_id": 8161647993, "name": "Abdulloh Askarov (@Abdulloh_askarov6)", "house": "House Bolton", "prestige": 457, "level": 6},
    ]
}



