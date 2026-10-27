import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import logging
from datetime import datetime, time as dt_time, timezone, timedelta
from telegram import (
    Update,
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeAllGroupChats,
)
from telegram.ext import Application, ContextTypes, TypeHandler, ApplicationHandlerStop
from config import BOT_TOKEN, ADMIN_IDS, OWNER_ID, escape_md
from core.notifier import notify_owner, notify_admins
from database import init_db, AsyncSessionLocal
from core.tick_engine import (
    process_due_marches,
    process_due_trade_caravans,
    process_npc_growth_and_raids,
    check_house_election_expiration,
    check_war_mode_expiration,
    execute_daily_2100_war_and_npc_raids,
    check_and_trigger_daily_war_failsafe,
)
from core.economy_engine import process_hourly_tick
from handlers import register_all_handlers
from database import crud

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
    """Har 10 soniyada manziliga yetgan harbiy yurishlar va savdo karvonlarini hisoblash, urush muddati tugashini tekshirish"""
    try:
        await process_due_marches(bot_app=context.application)
        await process_due_trade_caravans(bot_app=context.application)
        await check_war_mode_expiration(bot_app=context.application)
    except Exception as e:
        logger.error(f"March / caravan / war job xatosi: {e}")


async def hourly_economy_job(context: ContextTypes.DEFAULT_TYPE):
    """Har 1 soatda resurslar, oziq-ovqat iste'moli, Lordlik muddati, mavsumlar, ob-havo va turnirni tekshirish"""
    try:
        async with AsyncSessionLocal() as session:
            await process_hourly_tick(session)
            await crud.check_and_conclude_season(session, bot_app=context.application)
            await crud.check_and_rotate_weather(session, bot_app=context.application)
            await crud.check_and_resolve_weekly_tournament(session, bot_app=context.application)
        logger.info("💰 Soatlik iqtisodiyot, ob-havo va turnir hisoblandi.")
        await check_house_election_expiration(bot_app=context.application)
        # Failsafe: Agar 21:00-22:59 oralig'ida bot restart bo'lsa yoki o'chib qolsa, kunlik urushni o'tkazish
        await check_and_trigger_daily_war_failsafe(bot_app=context.application)

        # Haftalik avtomatik TOP Reytinglarni rasmiy kanal va guruhga e'lon qilish (Har yakshanba 20:00+ UTC+5)
        now_utc = datetime.utcnow()
        uz_now = now_utc + timedelta(hours=5)
        if uz_now.weekday() == 6 and uz_now.hour >= 20:
            try:
                from core.leaderboard_engine import broadcast_weekly_leaderboard
                ok, b_msg = await broadcast_weekly_leaderboard(bot_app=context.application, force=False)
                if ok:
                    logger.info(f"📢 Haftalik reyting muvaffaqiyatli kanalga post qilindi: {b_msg}")
            except Exception as le:
                logger.warning(f"Haftalik reyting e'lon qilish xatosi: {le}")
    except Exception as e:
        logger.error(f"Economy / election / season tick xatosi: {e}")


async def daily_war_and_npc_job(context: ContextTypes.DEFAULT_TYPE):
    """Har kuni soat 21:00 (O'zbekiston vaqti UTC+5) da urushni ochish va 10 ta NPC bosqinlarini o'tkazish"""
    try:
        await execute_daily_2100_war_and_npc_raids(bot_app=context.application, force=False)
    except Exception as e:
        logger.error(f"Daily 21:00 war job xatosi: {e}")


async def npc_tick_job(context: ContextTypes.DEFAULT_TYPE):
    """Har 15 daqiqada 5 ta tirik NPC xonadonlar garnizoni o'sishi va davriy bosqinlar"""
    try:
        await process_npc_growth_and_raids(bot_app=context.application)
    except Exception as e:
        logger.error(f"NPC tick xatosi: {e}")



# ============================================================
# HEALTHCHECK HTTP SERVER VA KEEP-ALIVE (RENDER.COM 24/7)
# ============================================================

import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.end_headers()
        resp = {
            "status": "online",
            "bot": "@ironthrone_rpgbot",
            "version": "v2.3 (Diplomacy & 24/7 Keep-Alive)",
            "server_time_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        self.wfile.write(json.dumps(resp, indent=2).encode("utf-8"))

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


async def render_keepalive_job(context: ContextTypes.DEFAULT_TYPE):
    """Render.com bepul tarifida bot 15 daqiqada uxlab qolmasligi uchun o'ziga har 5 daqiqada so'rov yuborish"""
    render_url = os.getenv("RENDER_EXTERNAL_URL", "https://westeros-bot.onrender.com")
    if render_url:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(render_url)
                logger.info(f"💓 Render Keep-Alive ping muvaffaqiyatli: {resp.status_code}")
        except Exception as e:
            logger.debug(f"Render keepalive xatosi: {e}")


async def on_startup(app: Application):
    """Bot qayta ishga tushganda yoki start berganda buyruqlarni o'rnatish va bosh egaga xabar berish"""
    try:
        private_commands = [
            BotCommand("start", "👑 Asosiy Menyu / Boshlash"),
            BotCommand("profile", "👤 Lord Profili & Armiya"),
            BotCommand("castles", "🏰 Qal'alarim & O'lpon"),
            BotCommand("house", "🏛️ Xonadon Boshqaruvi"),
            BotCommand("army", "⚔️ Askar Yollash & Garnizon"),
            BotCommand("map", "🗺️ Westeros Xaritasi & Fath"),
            BotCommand("dragons", "🐉 Ajdarlar Maskani"),
            BotCommand("battle", "🛡️ Harbiy Yurishlar"),
            BotCommand("donate", "💎 VIP & Donate (Homiylik)"),
            BotCommand("community", "📢 Rasmiy Guruh & Kanal"),
            BotCommand("daily", "🎁 Kunlik Tuhfalar"),
            BotCommand("quests", "📜 Vazifalar & Topshiriqlar"),
            BotCommand("duel", "⚔️ 1v1 Duellar"),
            BotCommand("support", "✍️ Adminlarga Murojaat"),
            BotCommand("bank", "🏦 Braavos Temir Banki"),
            BotCommand("rank", "🏆 Qirollik Reytingi"),
        ]
        group_commands = [
            BotCommand("profile", "👤 Lord profilini ko'rish (o'zingiz yoki reply qilib)"),
            BotCommand("rank", "🏆 Vesteros TOP Reytinglarini ko'rish"),
        ]
        try:
            await app.bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
            await app.bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
            logger.info("✅ Telegram guruh va shaxsiy buyruqlar menyulari o'rnatildi.")
        except Exception:
            await app.bot.set_my_commands(private_commands)
            logger.info("✅ Telegram umumiy buyruqlar menyusi o'rnatildi.")
    except Exception as e:
        logger.warning(f"set_my_commands xatosi: {e}")

    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    await notify_admins(
        app,
        f"🚀 *SERVER: BOT ISHGA TUSHDI / RESTART BERILDI!*\n\n"
        f"🛡️ Holat: Faol va himoyalangan\n"
        f"⏱️ Vaqt: `{now_str}`\n"
        f"💎 VIP & Donate tizimi, rasmiy guruh va kanal ulandi!\n"
        f"👑 Barcha yangi qoidalar to'liq amalda!"
    )



async def ban_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bloklangan (banned) foydalanuvchilarning harakatlarini butunlay to'xtatish"""
    user = update.effective_user
    if not user:
        return

    try:
        uid = int(user.id)
        if uid in [int(x) for x in ADMIN_IDS] or uid == int(OWNER_ID):
            return
    except Exception:
        pass

    async with AsyncSessionLocal() as session:
        is_banned = await crud.is_user_banned(session, user.id)

    if is_banned:
        if update.callback_query:
            try:
                await update.callback_query.answer(
                    "🚫 Sizning hisobingiz bloklangan! Botdan foydalana olmaysiz.",
                    show_alert=True
                )
            except Exception:
                pass
        elif update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "🚫 **SIZNING PROFILINGIZ BLOKLANGAN!**\n\n"
                    "Administrator tomonidan botdan foydalanish huquqingiz cheklangan.\n"
                    "Savollar yoki murojaat uchun administrator bilan bog'laning.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        raise ApplicationHandlerStop


async def command_audit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchilar tomonidan botga berilgan buyruqlarni xavfsiz server logiga yozish (Telegram API ni spam qilib botni qotirmaslik uchun)"""
    if not update.effective_message or not update.effective_message.text:
        return

    text = update.effective_message.text.strip()
    if not text.startswith("/"):
        return

    user = update.effective_user
    if not user:
        return

    user_id = user.id
    admin_set = set([int(OWNER_ID)] + [int(a) for a in ADMIN_IDS])
    if user_id in admin_set:
        return

    full_name = user.full_name or "Noma'lum"
    username_str = f"@{user.username}" if user.username else "yo'q"
    logger.info(f"AUDIT CMD: [{user_id}] {full_name} ({username_str}) -> {text}")


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Barcha kutilmagan bot xatolarini to'liq traceback bilan logger ga yozish"""
    logger.error("⚠️ Telegram botda xatolik yuz berdi:", exc_info=context.error)


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
        .post_init(on_startup)
        .build()
    )

    # Global error handler
    app.add_error_handler(global_error_handler)

    # Bloklangan (banned) foydalanuvchilarni barcha handlerlardan oldin to'xtatish
    app.add_handler(TypeHandler(Update, ban_check_callback), group=-2)

    # Buyruqlar auditi (har qanday buyruq bosh egaga yuboriladi)
    app.add_handler(TypeHandler(Update, command_audit_callback), group=-1)

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

    # NPC xonadonlar va avtomatik bosqinlar foydalanuvchi talabi bilan butunlay to'xtatilgan
    # app.job_queue.run_repeating(
    #     npc_tick_job,
    #     interval=900,
    #     first=60,
    # )

    # Render.com bepul tarifida bot 15 daqiqada uxlab qolmasligi uchun har 5 daqiqada (300 soniya) keep-alive
    app.job_queue.run_repeating(
        render_keepalive_job,
        interval=300,
        first=60,
    )

    # Kunlik urush va NPC hujumlari - ADMIN BOSHQARUVI:
    # Foydalanuvchi talabi: Urush va NPC bosqinlari avtomatik boshlanmaydi, admin qo'lda boshlaydi (/dailywar yoki Admin Panel)
    # va boshlangandan so'ng 1 soat davom etadi.
    # uzbekistan_tz = timezone(timedelta(hours=5))
    # app.job_queue.run_daily(
    #     daily_war_and_npc_job,
    #     time=dt_time(hour=21, minute=0, second=0, tzinfo=uzbekistan_tz),
    #     name="daily_2100_war_job",
    # )

    print("==================================================")
    print("👑 THE IRON THRONE — 500+ PLAYER MMORPG ISHGA TUSHDI")
    print("🏰 50 ta Xonadon | 60 ta Qal'a (10 ta NPC) | 21:00 Urush")
    print("==================================================")

    # Polling rejimida ishga tushirish
    app.run_polling()


if __name__ == "__main__":
    main()