import os
from pathlib import Path
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

# Bosh Administrator / Bot Egasi Telegram ID si
OWNER_ID = 7689627859

# Admin Telegram ID lari (Admin panelga kirish huquqi)
ADMIN_IDS = [7689627859]


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
    """ADMIN_IDS ni config.py fayliga yozib saqlash"""
    try:
        cfg_file = BASE_DIR / "config.py"
        text = cfg_file.read_text(encoding="utf-8")
        import re
        new_text = re.sub(r"ADMIN_IDS\s*=\s*\[.*?\]", f"ADMIN_IDS = {ADMIN_IDS}", text)
        cfg_file.write_text(new_text, encoding="utf-8")
    except Exception as e:
        print(f"Error persisting admins: {e}")

# ============================================================
# KUNLIK LIMITLAR
# ============================================================
DAILY_QUIZ_LIMIT = 8
DAILY_COUNCIL_LIMIT = 3
DAILY_SECRET_QUEST_LIMIT = 2
DAILY_DUEL_LIMIT = int(os.getenv("DAILY_DUEL_LIMIT", "5"))

# ============================================================
# O'YIN IQTISODIYOTI VA BALANS
# ============================================================

# Yangi o'yinchi boshlang'ich resurslari
STARTING_GOLD = 500
STARTING_FOOD = 1000
STARTING_IRON = 300

# Boshlang'ich Tinchlik Qalqoni (soatlarda, masalan 72 soat = 3 kun)
PEACE_SHIELD_HOURS = 72

# Boshlang'ich armiya
STARTING_INFANTRY = 100
STARTING_ARCHERS = 50
STARTING_CAVALRY = 25
STARTING_SPEARMEN = 25

# Askarlarning oziq-ovqat iste'moli (soatiga 1 ta askar uchun)
UPKEEP_FOOD_PER_INFANTRY = 0.5
UPKEEP_FOOD_PER_ARCHER = 0.6
UPKEEP_FOOD_PER_CAVALRY = 1.2
UPKEEP_FOOD_PER_SPEARMAN = 0.5
UPKEEP_FOOD_PER_SPECIAL = 1.5

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
# ============================================================
DONATE_CARD_NUMBER = os.getenv("DONATE_CARD_NUMBER", "5614688804228251")
DONATE_CARD_HOLDER = os.getenv("DONATE_CARD_HOLDER", "Shavkatov Azizbek")

# ============================================================
# RASMIY HAMJAMIYAT (KANAL & GURUH)
# ============================================================
COMMUNITY_CHANNEL_URL = os.getenv("COMMUNITY_CHANNEL_URL", "https://t.me/northremembers1")
COMMUNITY_GROUP_URL = os.getenv("COMMUNITY_GROUP_URL", "https://t.me/northremember2")

# ============================================================
# AFSONAVIY DONATE / VIP TARIFLARI
# ============================================================
DONATE_TIERS = {
    "knight": {
        "id": "knight",
        "name": "🗡️ Ritsar To'plami",
        "subtitle": "Boshlang'ich jangchi to'plami (Ajoyib start)",
        "price_uzs": 10000,
        "price_label": "10,000 so'm",
        "gold": 10000,
        "food": 30000,
        "iron": 15000,
        "infantry": 500,
        "archers": 300,
        "cavalry": 100,
        "spearmen": 100,
        "special_troops": 0,
        "catapults": 0,
        "siege_towers": 0,
        "shield_hours": 0,
        "prestige": 150,
        "wildfire": 0,
        "dragon": {
            "name": "Arrax",
            "grade": "C",
            "stage": "baby",
            "level": 3,
            "power": 350,
            "hunger": 100,
        },
        "title": "Jasur Ritsar",
        "description": (
            "• 🪙 Oltin: +10,000\n"
            "• 🌾 Oziq-ovqat: +30,000\n"
            "• ⛓️ Temir: +15,000\n"
            "• 🛡️ Armiya: +500 Piyoda, +300 Kamonchi, +100 Otliq, +100 Nayzador\n"
            "• 🐉 Jangovar Ajdaho: «Arrax» (3-daraja, 350 quvvat!)\n"
            "• 👑 Faxriy unvon: «Jasur Ritsar»\n"
            "• ⭐ Prestige: +150 shon-sharaf"
        ),
    },
    "lord": {
        "id": "lord",
        "name": "🏰 Lordlar Xazinasi",
        "subtitle": "Hukmdorlar tanlovi (Eng ommabop)",
        "price_uzs": 25000,
        "price_label": "25,000 so'm",
        "gold": 35000,
        "food": 100000,
        "iron": 50000,
        "infantry": 1200,
        "archers": 800,
        "cavalry": 500,
        "spearmen": 500,
        "special_troops": 100,
        "catapults": 2,
        "siege_towers": 1,
        "shield_hours": 0,
        "prestige": 400,
        "wildfire": 3,
        "dragon": {
            "name": "Syrax",
            "grade": "B",
            "stage": "adult",
            "level": 8,
            "power": 1200,
            "hunger": 100,
        },
        "title": "Saxiy Lord",
        "description": (
            "• 🪙 Oltin: +35,000\n"
            "• 🌾 Oziq-ovqat: +100,000\n"
            "• ⛓️ Temir: +50,000\n"
            "• 🛡️ Kuchli Armiya: +1,200 Piyoda, +800 Kamonchi, +500 Otliq, +500 Nayzador, +100 Maxsus!\n"
            "• 🏹 Qamal qurollari: +2 Katapulta, +1 Qamal minorasi\n"
            "• 🐉 Afsonaviy Ajdaho: 8-darajali (1,200 quvvat!)\n"
            "• 💚 Yovvoyi Olov (Wildfire): +3 bochka (Qal'a mudofaasiga)\n"
            "• 👑 Maxsus unvon: «Saxiy Lord»\n"
            "• ⭐ Prestige: +400 shon-sharaf"
        ),
    },
    "dragonlord": {
        "id": "dragonlord",
        "name": "🐉 Valyriya Merosi",
        "subtitle": "Ajdaho Hukmdori (Kuchli Imperiya)",
        "price_uzs": 50000,
        "price_label": "50,000 so'm",
        "gold": 100000,
        "food": 300000,
        "iron": 150000,
        "infantry": 3000,
        "archers": 2000,
        "cavalry": 1500,
        "spearmen": 1500,
        "special_troops": 500,
        "catapults": 10,
        "siege_towers": 5,
        "shield_hours": 0,
        "prestige": 1000,
        "wildfire": 5,
        "dragon": {
            "name": "Drogon",
            "grade": "A",
            "stage": "adult",
            "level": 12,
            "power": 2500,
            "hunger": 100,
        },
        "title": "Ajdaho Hukmdori",
        "description": (
            "• 🪙 Oltin: +100,000\n"
            "• 🌾 Oziq-ovqat: +300,000\n"
            "• ⛓️ Temir: +150,000\n"
            "• 🛡️ Qudratli Armiya: +3,000 Piyoda, +2,000 Kamonchi, +1,500 Otliq, +1,500 Nayzador, +500 Maxsus!\n"
            "• 🏹 Qamal qurollari: +10 Katapulta, +5 Qamal minorasi\n"
            "• 🐉 Qora Ajdaho: Drogon 12-darajali (2,500 quvvat!)\n"
            "• 💚 Yovvoyi Olov (Wildfire): +5 bochka (Maksimal)\n"
            "• 👑 Maxsus unvon: «Ajdaho Hukmdori»\n"
            "• ⭐ Prestige: +1,000 shon-sharaf"
        ),
    },
    "sovereign": {
        "id": "sovereign",
        "name": "👑 Temir Taxt Sohibi",
        "subtitle": "Vesteros Imperatori (Mutlaq Hukmronlik)",
        "price_uzs": 99000,
        "price_label": "99,000 so'm",
        "gold": 300000,
        "food": 1000000,
        "iron": 500000,
        "infantry": 8000,
        "archers": 5000,
        "cavalry": 3000,
        "spearmen": 3000,
        "special_troops": 1500,
        "catapults": 20,
        "siege_towers": 10,
        "shield_hours": 0,
        "prestige": 3000,
        "wildfire": 5,
        "dragon": {
            "name": "Balerion",
            "grade": "A",
            "stage": "adult",
            "level": 15,
            "power": 5000,
            "hunger": 100,
        },
        "title": "Vesteros Himoyachisi",
        "broadcast": True,
        "description": (
            "• 🪙 Oltin: +300,000\n"
            "• 🌾 Oziq-ovqat: +1000,000 (1 Million!)\n"
            "• ⛓️ Temir: +500,000\n"
            "• 🛡️ Bahaybat Armiya: +8,000 Piyoda, +5,000 Kamonchi, +3,000 Otliq, +3,000 Nayzador, +1,500 Maxsus!\n"
            "• 🏹 Qamal qurollari: +20 Katapulta (Maks), +10 Qamal minorasi (Maks)!\n"
            "• 🐉 Afsonaviy Qora Ajdar: Balerion (5,000 quvvat!)\n"
            "• 💚 Yovvoyi Olov (Wildfire): +5 bochka (Maksimal)\n"
            "• 👑 Maxsus unvon: «Vesteros Himoyachisi»\n"
            "• ⭐ Prestige: +3,000 shon-sharaf\n"
            "• 📣 Butun Vesteros bo'ylab Qirollik tantanali e'loni!"
        ),
    },
}


