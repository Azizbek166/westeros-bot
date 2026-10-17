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
STARTING_GOLD = 250
STARTING_FOOD = 500
STARTING_IRON = 125

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
        "subtitle": "Boshlang'ich jangchi to'plami",
        "price_uzs": 15000,
        "price_label": "15,000 so'm",
        "gold": 1500,
        "food": 3000,
        "iron": 1000,
        "infantry": 200,
        "archers": 100,
        "cavalry": 0,
        "spearmen": 0,
        "special_troops": 0,
        "shield_hours": 48,
        "prestige": 50,
        "wildfire": 0,
        "dragon": None,
        "title": None,
        "description": (
            "• 🪙 Oltin: +1,500\n"
            "• 🌾 Oziq-ovqat: +3,000\n"
            "• ⛓️ Temir: +1,000\n"
            "• 🛡️ Piyoda: +200 ta\n"
            "• 🏹 Kamonchi: +100 ta\n"
            "• 🕊️ Tinchlik Qalqoni: 48 soat\n"
            "• ⭐ Prestige: +50 shon-sharaf"
        ),
    },
    "lord": {
        "id": "lord",
        "name": "🏰 Lordlar Xazinasi",
        "subtitle": "Hukmdorlar tanlovi (Mashhur)",
        "price_uzs": 35000,
        "price_label": "35,000 so'm",
        "gold": 4500,
        "food": 10000,
        "iron": 3000,
        "infantry": 0,
        "archers": 0,
        "cavalry": 150,
        "spearmen": 200,
        "special_troops": 0,
        "shield_hours": 72,
        "prestige": 150,
        "wildfire": 3,
        "dragon": None,
        "title": "Saxiy Lord",
        "description": (
            "• 🪙 Oltin: +4,500\n"
            "• 🌾 Oziq-ovqat: +10,000\n"
            "• ⛓️ Temir: +3,000\n"
            "• 🐎 Otliq askar: +150 ta\n"
            "• 🗡️ Nayzador: +200 ta\n"
            "• 💚 Yovvoyi Olov (Wildfire): +3 bochka\n"
            "• 🕊️ Tinchlik Qalqoni: 72 soat (3 kun)\n"
            "• 👑 Maxsus unvon: «Saxiy Lord»\n"
            "• ⭐ Prestige: +150 shon-sharaf"
        ),
    },
    "dragonlord": {
        "id": "dragonlord",
        "name": "🐉 Valyriya Merosi",
        "subtitle": "Ajdaho Hukmdori to'plami",
        "price_uzs": 75000,
        "price_label": "75,000 so'm",
        "gold": 12000,
        "food": 25000,
        "iron": 8000,
        "infantry": 0,
        "archers": 0,
        "cavalry": 0,
        "spearmen": 0,
        "special_troops": 100,
        "shield_hours": 120,
        "prestige": 400,
        "wildfire": 5,
        "dragon": {
            "name": "Syrax",
            "grade": "B",
            "stage": "adult",
            "level": 10,
            "power": 1500,
            "hunger": 100,
        },
        "title": "Ajdaho Hukmdori",
        "description": (
            "• 🪙 Oltin: +12,000\n"
            "• 🌾 Oziq-ovqat: +25,000\n"
            "• ⛓️ Temir: +8,000\n"
            "• 🔥 Xonadon Maxsus Askari: +100 ta\n"
            "• 🐉 Afsonaviy Jangovar Ajdar: 10-darajali (1,500 quvvat!)\n"
            "• 💚 Yovvoyi Olov (Wildfire): +5 bochka (Maksimal)\n"
            "• 🕊️ Tinchlik Qalqoni: 120 soat (5 kun)\n"
            "• 👑 Maxsus unvon: «Ajdaho Hukmdori»\n"
            "• ⭐ Prestige: +400 shon-sharaf"
        ),
    },
    "sovereign": {
        "id": "sovereign",
        "name": "👑 Temir Taxt Sohibi",
        "subtitle": "Eksklyuziv Imperator to'plami",
        "price_uzs": 149000,
        "price_label": "149,000 so'm",
        "gold": 30000,
        "food": 60000,
        "iron": 20000,
        "infantry": 1000,
        "archers": 600,
        "cavalry": 400,
        "spearmen": 400,
        "special_troops": 250,
        "shield_hours": 168,
        "prestige": 1000,
        "wildfire": 5,
        "dragon": {
            "name": "Balerion",
            "grade": "A",
            "stage": "adult",
            "level": 15,
            "power": 2500,
            "hunger": 100,
        },
        "title": "Vesteros Himoyachisi",
        "broadcast": True,
        "description": (
            "• 🪙 Oltin: +30,000\n"
            "• 🌾 Oziq-ovqat: +60,000\n"
            "• ⛓️ Temir: +20,000\n"
            "• 🛡️ Katta Armiya: +1,000 Piyoda, +600 Kamonchi, +400 Otliq, +400 Nayzador, +250 Maxsus!\n"
            "• 🐉 Bahaybat Qora Ajdar: Balerion 15-darajali (2,500 quvvat!)\n"
            "• 💚 Yovvoyi Olov (Wildfire): +5 bochka (Maksimal)\n"
            "• 🕊️ Tinchlik Qalqoni: 168 soat (7 kun daxlsizlik)\n"
            "• 👑 Maxsus unvon: «Vesteros Himoyachisi»\n"
            "• ⭐ Prestige: +1,000 shon-sharaf\n"
            "• 📣 Butun Vesteros bo'ylab Qirollik E'loni!"
        ),
    },
}

