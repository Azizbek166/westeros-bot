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
from core.daily_events_engine import register_daily_events_jobs
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
            # Temir Bank qarzdorlariga Oltin Gala (Golden Company 50,000 ball) bosqini
            await crud.check_and_trigger_all_golden_company_raids(session, bot_app=context.application)
        logger.info("💰 Soatlik iqtisodiyot, ob-havo, turnir va bank reydlari hisoblandi.")
        await check_house_election_expiration(bot_app=context.application)
        # Failsafe: Agar 21:00-22:59 oralig'ida bot restart bo'lsa yoki o'chib qolsa, kunlik urushni o'tkazish
        await check_and_trigger_daily_war_failsafe(bot_app=context.application)

        # Haftalik avtomatik TOP Reytinglarni rasmiy kanal va guruhga e'lon qilish (Hafta boshida / yakshanba 20:00 - dushanba 10:00 UTC+5)
        now_utc = datetime.utcnow()
        uz_now = now_utc + timedelta(hours=5)
        if (uz_now.weekday() == 6 and uz_now.hour >= 20) or (uz_now.weekday() == 0 and uz_now.hour <= 10):
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

GLOBAL_SERVER_AUDIT = {}

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.end_headers()
        
        resp = {
            "status": "online",
            "bot": "@ironthrone_rpgbot",
            "version": "v2.5 (Live Audit)",
            "server_time_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "audit": GLOBAL_SERVER_AUDIT,
        }
        self.wfile.write(json.dumps(resp, indent=2).encode("utf-8"))

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Render loglarini to'ldirmaslik uchun

def start_health_server():
    pass


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
        # Ma'lumotlar bazasini Telegram botining faol asyncio event loop'i ichida initsializatsiya qilish
        logger.info("📦 Ma'lumotlar bazasi initsializatsiya qilinmoqda...")
        await init_db()
        logger.info("✅ Baza tayyor.")
        
        try:
            from database import models, crud
            from sqlalchemy import select
            async with AsyncSessionLocal() as s_audit:
                res = await s_audit.execute(
                    select(models.User.id, models.User.username, models.User.full_name, models.User.house_id, models.Army.infantry, models.Army.archers, models.Army.cavalry, models.Army.spearmen, models.Army.special_troops)
                    .join(models.Army, models.Army.user_id == models.User.id, isouter=True)
                    .order_by(models.User.id)
                )
                rows = res.fetchall()
                GLOBAL_SERVER_AUDIT["users"] = [
                    {
                        "id": r[0], "username": r[1], "name": r[2], "house_id": r[3],
                        "total_army": (r[4] or 0) + (r[5] or 0) + (r[6] or 0) + (r[7] or 0) + (r[8] or 0),
                        "troops": [r[4] or 0, r[5] or 0, r[6] or 0, r[7] or 0, r[8] or 0]
                    }
                    for r in rows
                ]

                # Top 10 armies
                top10_data = await crud.get_top10_armies_detailed(s_audit)
                GLOBAL_SERVER_AUDIT["top10_armies"] = [
                    {
                        "house_id": entry["house"].id if entry.get("house") else None,
                        "house_name": entry["house"].name if entry.get("house") else "None",
                        "lord_name": entry["user"].full_name if entry.get("user") else "None",
                        "total_troops": entry["total_troops"],
                        "active_troops": entry["active_troops"],
                        "garrison_troops": entry["garrison_troops"],
                        "castles_count": entry["castles_count"],
                        "power": entry["power"],
                    }
                    for entry in top10_data
                ]

                # Territories
                t_res = await s_audit.execute(
                    select(models.Territory.id, models.Territory.name, models.Territory.owner_house_id, models.Territory.garrison_infantry, models.Territory.garrison_archers, models.Territory.garrison_cavalry, models.Territory.garrison_spearmen)
                    .where((models.Territory.owner_house_id.isnot(None)) | (models.Territory.id <= 60))
                    .order_by(models.Territory.id)
                )
                GLOBAL_SERVER_AUDIT["territories"] = [
                    {
                        "id": r[0], "name": r[1], "house_id": r[2],
                        "total_garrison": (r[3] or 0) + (r[4] or 0) + (r[5] or 0) + (r[6] or 0),
                        "troops": [r[3] or 0, r[4] or 0, r[5] or 0, r[6] or 0]
                    }
                    for r in t_res.fetchall()
                ]

                GLOBAL_SERVER_AUDIT["loaded_at"] = datetime.utcnow().isoformat()
        except Exception as e_aud:
            GLOBAL_SERVER_AUDIT["error"] = str(e_aud)

        private_commands = [
            BotCommand("guild", "🛡️ Gildiya (Birodarlik)"),
            BotCommand("gildiya", "🛡️ Gildiya Paneli"),
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
            BotCommand("maslahat", "🧙‍♂️ Meyster Maslahati (AI)"),
            BotCommand("ai", "🧙‍♂️ Kengash Maslahatchisi"),
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

    try:
        from core.notifier import send_armies_audit_report
        await send_armies_audit_report(app, OWNER_ID)
    except Exception as e_audit:
        logger.warning(f"send_armies_audit_report startup xatosi: {e_audit}")

    try:
        from core.error_reporter import set_error_reporter_bot_app
        set_error_reporter_bot_app(app)
    except Exception as e_err:
        logger.warning(f"set_error_reporter_bot_app xatosi: {e_err}")



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
    """Barcha kutilmagan bot xatolarini to'liq traceback bilan logger ga yozish va ERROR_CHAT_ID ga yuborish"""
    logger.error("⚠️ Telegram botda xatolik yuz berdi:", exc_info=context.error)

    try:
        from core.error_reporter import report_system_error
        import traceback

        err = context.error
        err_type = type(err).__name__ if err else "UnknownBotError"
        err_msg = str(err) if err else "Noma'lum xatolik"

        tb_list = traceback.format_exception(None, err, err.__traceback__) if err and err.__traceback__ else []
        tb_str = "".join(tb_list)

        user_id = None
        handler_name = "bot_update"

        if isinstance(update, Update):
            if update.effective_user:
                user_id = update.effective_user.id
            if update.callback_query and update.callback_query.data:
                handler_name = f"callback:{update.callback_query.data[:40]}"
            elif update.effective_message and update.effective_message.text:
                cmd = update.effective_message.text.split()[0][:30]
                handler_name = f"cmd:{cmd}"

        # Oxirgi traceback qatoridan fayl va funksiya nomini topish
        if err and err.__traceback__:
            tb_last = err.__traceback__
            while tb_last.tb_next:
                tb_last = tb_last.tb_next
            func_name = tb_last.tb_frame.f_code.co_name
            raw_fn = tb_last.tb_frame.f_code.co_filename
            file_name = raw_fn.replace("\\", "/").split("/")[-1]
            handler_name = f"{handler_name} -> {file_name}:{func_name}"

        await report_system_error(
            source="bot",
            error_type=err_type,
            error_message=err_msg,
            handler_name=handler_name,
            user_telegram_id=user_id,
            stack_trace=tb_str,
        )
    except Exception as ge:
        logger.error(f"global_error_handler reporting error: {ge}")


# ============================================================
# ASOSIY ISHGA TUSHIRISH (MAIN)
# ============================================================

async def main_async():
    if not BOT_TOKEN:
        print("❌ XATOLIK: BOT_TOKEN topilmadi! config.py yoki .env faylini tekshiring.")
        return

    # 1. Telegram Bot Application
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

    # Buyruqlar auditi
    app.add_handler(TypeHandler(Update, command_audit_callback), group=-1)

    # 3. Barcha modulli handlerlarni ulash
    register_all_handlers(app)

    # 4. Background Game Tick dvigatellarini ishga tushirish
    app.job_queue.run_repeating(
        march_resolution_job,
        interval=10,
        first=10,
    )
    app.job_queue.run_repeating(
        hourly_economy_job,
        interval=3600,
        first=60,
    )
    app.job_queue.run_repeating(
        render_keepalive_job,
        interval=300,
        first=60,
    )
    register_daily_events_jobs(app)

    # 5. Telegram Bot pollingni va Uvicorn serverni BITTA yagona asinxron event loop'da ishga tushirish
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    print("==================================================")
    print("👑 THE IRON THRONE — 500+ PLAYER MMORPG ISHGA TUSHDI")
    print("🏰 50 ta Xonadon | 60 ta Qal'a (10 ta NPC) | 21:00 Urush")
    print("==================================================")

    port = int(os.getenv("PORT", 0))
    if port <= 0:
        port = int(os.getenv("API_PORT", 0))

    if port > 0:
        import uvicorn
        logger.info(f"🌐 FastAPI & Telegram Mini App bitta umumiy asinxron loop'da {port}-portda ishga tushmoqda...")
        config = uvicorn.Config("api.main:app", host="0.0.0.0", port=port, log_level="warning")
        server = uvicorn.Server(config)
        try:
            await server.serve()
        except asyncio.CancelledError:
            pass
    else:
        # Port belgilanmagan bo'lsa (lokal faqat bot rejimi), cheksiz kutish
        try:
            while True:
                await asyncio.sleep(3600)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass

    # Xavfsiz to'xtatish
    try:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
    except Exception as e:
        logger.warning(f"Botni to'xtatishda xatolik: {e}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()