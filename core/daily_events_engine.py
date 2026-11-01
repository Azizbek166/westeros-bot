import asyncio
import logging
from datetime import datetime, timedelta, time as dt_time, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import AsyncSessionLocal, crud, models
from config import COMMUNITY_CHANNEL_ID

logger = logging.getLogger(__name__)
UZBEKISTAN_TZ = timezone(timedelta(hours=5))


async def start_event_by_code(app, event_code: str):
    """Eventni boshlash, e'lon qilish va bazaga kiritish"""
    now_uzb = datetime.utcnow() + timedelta(hours=5)
    event_date = now_uzb.strftime("%Y-%m-%d")

    async with AsyncSessionLocal() as session:
        event = await crud.get_or_create_daily_scheduled_event(session, event_code, event_date)
        event_id = event.id
        title = event.title
        cfg = crud.DAILY_EVENTS_CONFIG.get(event_code, {})
        description = cfg.get("description", "Vesterosda yangi voqea boshlandi.")

    announcement_text = (
        f"⚡ **DIQQAT! YANGI KUNLIK VOQEA BOSHLANDI!**\n\n"
        f"👑 **{title}**\n\n"
        f"📜 {description}\n\n"
        f"⏱️ **Voqea davomiyligi:** 1 soat\n"
        f"Har bir lord faqat 1 marta qatnasha oladi. Mukofotlar voqea yakunlangach avtomatik beriladi!\n\n"
        f"👇 *Quyidagi tugmani bosib ishtirok eting:*"
    )

    join_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Qatnashish", callback_data=f"daily_event_join:{event_id}")],
        [InlineKeyboardButton("📊 Voqealar Menyusi", callback_data="menu_daily_events")]
    ])

    # 1. Telegram Kanalga e'lon
    if COMMUNITY_CHANNEL_ID and hasattr(app, "bot"):
        channel_text = (
            f"⚡ **YANGI VOQEA: {title}**\n\n"
            f"📜 {description}\n\n"
            f"⏱️ Boshlandi: {now_uzb.strftime('%H:%M')} (Toshkent vaqti)\n"
            f"Qatnashish uchun botga kiring va «Qatnashish» tugmasini bosing!"
        )
        try:
            await app.bot.send_message(
                chat_id=COMMUNITY_CHANNEL_ID,
                text=channel_text
            )
        except Exception as e:
            logger.error(f"Kanalga event e'lon qilishda xatolik: {e}")

    # 2. Botdagi o'yinchilarga xabar yuborish
    if hasattr(app, "bot"):
        async with AsyncSessionLocal() as session:
            users_res = await session.execute(models.User.__table__.select())
            rows = users_res.fetchall()
            for r in rows:
                tg_id = getattr(r, "telegram_id", None)
                if tg_id:
                    try:
                        await app.bot.send_message(
                            chat_id=tg_id,
                            text=announcement_text,
                            parse_mode="Markdown",
                            reply_markup=join_kb
                        )
                    except Exception:
                        pass


async def resolve_event_by_code(app, event_code: str):
    """Eventni yakunlash va mukofotlarni taqsimlash"""
    now_uzb = datetime.utcnow() + timedelta(hours=5)
    event_date = now_uzb.strftime("%Y-%m-%d")

    async with AsyncSessionLocal() as session:
        stmt = (
            models.DailyScheduledEvent.__table__.select().where(
                models.DailyScheduledEvent.event_code == event_code,
                models.DailyScheduledEvent.event_date == event_date,
                models.DailyScheduledEvent.status == "active"
            )
        )
        res = await session.execute(stmt)
        row = res.first()
        if not row:
            return

        event_id = row.id
        ok, msg = await crud.resolve_daily_scheduled_event(session, event_id, bot_app=app)
        logger.info(f"Daily event #{event_id} resolved: {ok} -> {msg}")


# -------------------------------------------------------------
# Job Queue Callbacks (APScheduler / Telegram JobQueue)
# -------------------------------------------------------------

async def job_event_0400_start(context):
    """04:00 - Ajdarlar Parvozi boshlanishi"""
    await start_event_by_code(context.application, "dragons_flight")


async def job_event_0400_resolve(context):
    """05:00 - Ajdarlar Parvozi yakunlanishi"""
    await resolve_event_by_code(context.application, "dragons_flight")


async def job_event_1200_start(context):
    """12:00 - Qirollik Xazinasi boshlanishi"""
    await start_event_by_code(context.application, "royal_treasury")


async def job_event_1200_resolve(context):
    """13:00 - Qirollik Xazinasi yakunlanishi"""
    await resolve_event_by_code(context.application, "royal_treasury")


async def job_event_1600_start(context):
    """16:00 - Savdogarlar Karvoni boshlanishi"""
    await start_event_by_code(context.application, "merchant_caravan")


async def job_event_1600_resolve(context):
    """17:00 - Savdogarlar Karvoni yakunlanishi"""
    await resolve_event_by_code(context.application, "merchant_caravan")


async def job_event_2100_start(context):
    """21:00 - Shimoldan Xavf boshlanishi"""
    await start_event_by_code(context.application, "northern_threat")


async def job_event_2100_resolve(context):
    """22:00 - Shimoldan Xavf yakunlanishi"""
    await resolve_event_by_code(context.application, "northern_threat")


async def job_daily_dragon_tourney_resolve(context):
    """20:00 - Kunlik Avtomatik Ajdarlar Turniri yakunlanishi"""
    async with AsyncSessionLocal() as session:
        ok, msg = await crud.resolve_daily_dragon_tourney(session, bot_app=context.application)
        logger.info(f"Daily dragon tournament resolved: {ok} -> {msg}")


def register_daily_events_jobs(app):
    """Kunlik avtomatik eventlarni JobQueue ga ulash (Asia/Tashkent vaqti)"""
    if not hasattr(app, "job_queue") or not app.job_queue:
        logger.warning("JobQueue topilmadi, kunlik eventlar scheduleri ulanmadi.")
        return

    jq = app.job_queue

    # Event 1: Ajdarlar Parvozi (04:00 - 05:00)
    jq.run_daily(
        job_event_0400_start,
        time=dt_time(hour=4, minute=0, second=0, tzinfo=UZBEKISTAN_TZ),
        name="daily_event_0400_start"
    )
    jq.run_daily(
        job_event_0400_resolve,
        time=dt_time(hour=5, minute=0, second=0, tzinfo=UZBEKISTAN_TZ),
        name="daily_event_0400_resolve"
    )

    # Event 2: Qirollik Xazinasi (12:00 - 13:00)
    jq.run_daily(
        job_event_1200_start,
        time=dt_time(hour=12, minute=0, second=0, tzinfo=UZBEKISTAN_TZ),
        name="daily_event_1200_start"
    )
    jq.run_daily(
        job_event_1200_resolve,
        time=dt_time(hour=13, minute=0, second=0, tzinfo=UZBEKISTAN_TZ),
        name="daily_event_1200_resolve"
    )

    # Event 3: Savdogarlar Karvoni (16:00 - 17:00)
    jq.run_daily(
        job_event_1600_start,
        time=dt_time(hour=16, minute=0, second=0, tzinfo=UZBEKISTAN_TZ),
        name="daily_event_1600_start"
    )
    jq.run_daily(
        job_event_1600_resolve,
        time=dt_time(hour=17, minute=0, second=0, tzinfo=UZBEKISTAN_TZ),
        name="daily_event_1600_resolve"
    )

    # Kunlik Ajdarlar Turniri (20:00 da avtomatik janglar va chempion aniqlanishi)
    jq.run_daily(
        job_daily_dragon_tourney_resolve,
        time=dt_time(hour=20, minute=0, second=0, tzinfo=UZBEKISTAN_TZ),
        name="daily_dragon_tourney_resolve"
    )

    # Event 4: Shimoldan Xavf (21:00 - 22:00)
    jq.run_daily(
        job_event_2100_start,
        time=dt_time(hour=21, minute=0, second=0, tzinfo=UZBEKISTAN_TZ),
        name="daily_event_2100_start"
    )
    jq.run_daily(
        job_event_2100_resolve,
        time=dt_time(hour=22, minute=0, second=0, tzinfo=UZBEKISTAN_TZ),
        name="daily_event_2100_resolve"
    )

    logger.info("✅ Barcha 4 ta Kunlik Eventlar va Kunlik Ajdarlar Turniri jadvallari (Asia/Tashkent) muvaffaqiyatli ishga tushirildi.")
