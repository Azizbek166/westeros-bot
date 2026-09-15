import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import logging
from telegram.ext import Application, ContextTypes
from config import BOT_TOKEN
from database import init_db, AsyncSessionLocal
from core.tick_engine import process_due_marches, process_npc_growth_and_raids, check_house_election_expiration
from core.economy_engine import process_hourly_tick
from handlers import register_all_handlers

# Logging sozlamalari
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ============================================================
# BACKGROUND TICK JOBS
# ============================================================

async def march_resolution_job(context: ContextTypes.DEFAULT_TYPE):
    """Har 10 soniyada manziliga yetgan harbiy yurishlarni hisoblash"""
    try:
        await process_due_marches(bot_app=context.application)
    except Exception as e:
        logger.error(f"March job xatosi: {e}")


async def hourly_economy_job(context: ContextTypes.DEFAULT_TYPE):
    """Har 1 soatda resurslar, oziq-ovqat iste'moli va 10 kunlik Lordlik muddatini tekshirish"""
    try:
        async with AsyncSessionLocal() as session:
            await process_hourly_tick(session)
        logger.info("💰 Soatlik iqtisodiyot va oziq-ovqat iste'moli hisoblandi.")
        await check_house_election_expiration(bot_app=context.application)
    except Exception as e:
        logger.error(f"Economy / election tick xatosi: {e}")


async def npc_tick_job(context: ContextTypes.DEFAULT_TYPE):
    """Har 15 daqiqada 5 ta tirik NPC xonadonlar garnizoni o'sishi va davriy bosqinlar"""
    try:
        await process_npc_growth_and_raids(bot_app=context.application)
    except Exception as e:
        logger.error(f"NPC tick xatosi: {e}")



# ============================================================
# HEALTHCHECK HTTP SERVER (RENDER.COM 24/7 UCHUN)
# ============================================================

import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Westeros Bot v2.2 - Live and updated!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Render loglarini to'ldirmaslik uchun

def start_health_server():
    port = int(os.getenv("PORT", 0))
    if port > 0:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"🌐 Render Web Service port {port} da ishga tushdi.")


# ============================================================
# ASOSIY ISHGA TUSHIRISH (MAIN)
# ============================================================

def main():
    if not BOT_TOKEN:
        print("❌ XATOLIK: BOT_TOKEN topilmadi! config.py yoki .env faylini tekshiring.")
        return

    # Render.com yoki bulutli port bo'lsa healthcheck serverni yoqish
    start_health_server()

    # 1. Ma'lumotlar bazasini initsializatsiya qilish
    logger.info("📦 Ma'lumotlar bazasi initsializatsiya qilinmoqda...")
    asyncio.run(init_db())
    logger.info("✅ Baza tayyor.")

    # 2. Telegram Bot Application
    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # 3. Barcha modulli handlerlarni ulash
    register_all_handlers(app)

    # 4. Background Game Tick dvigatellarini ishga tushirish
    # Har 10 soniyada yurishlarni tekshirish
    app.job_queue.run_repeating(
        march_resolution_job,
        interval=10,
        first=10,
    )

    # Har 1 soatda (3600 soniya) iqtisodiy tick va saylov tekshiruvi
    app.job_queue.run_repeating(
        hourly_economy_job,
        interval=3600,
        first=60,
    )

    # Har 15 daqiqada (900 soniya) 5 ta NPC xonadon harakati va bosqinlari
    app.job_queue.run_repeating(
        npc_tick_job,
        interval=900,
        first=60,
    )

    print("==================================================")
    print("👑 THE IRON THRONE — 500+ PLAYER MMORPG ISHGA TUSHDI")
    print("🏰 50 ta Xonadon | 21 ta Qal'a | Tosh-Qaychi-Qog'oz Janglar")
    print("==================================================")

    # Polling rejimida ishga tushirish
    app.run_polling()


if __name__ == "__main__":
    main()