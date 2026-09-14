import os
from pathlib import Path
from dotenv import load_dotenv

# .env faylini yuklash
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ============================================================
# ASOSIY SOZLAMALAR
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8732408293:AAG_7xYlNL44_yjmQXsxdeIzXAYdFZYs8Cg")

# PostgreSQL yoki SQLite (PostgreSQL o'rnatilmagan bo'lsa aiosqlite ishlaydi)
DEFAULT_DB_PATH = BASE_DIR / "got_mmorpg.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}")

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

# ============================================================
# O'YIN IQTISODIYOTI VA BALANS
# ============================================================

# Yangi o'yinchi boshlang'ich resurslari
STARTING_GOLD = 1000
STARTING_FOOD = 2000
STARTING_IRON = 500

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

# Yurish tezligi (hududlar orasidagi bazaviy daqiqa)
BASE_MARCH_MINUTES = 3

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
