from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    Application,
)
from database import AsyncSessionLocal, crud, models
from config import ADMIN_IDS, OWNER_ID


def is_admin(user_id: int) -> bool:
    try:
        uid = int(user_id)
        return uid in [int(x) for x in ADMIN_IDS] or uid == int(OWNER_ID)
    except Exception:
        return False


async def daily_event_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchining kunlik eventda qatnashishi"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 2:
        return

    try:
        event_id = int(parts[1])
    except ValueError:
        return

    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            await query.answer("Iltimos, avval /start ni bosing.", show_alert=True)
            return

        ok, msg = await crud.join_daily_scheduled_event(
            session=session,
            event_id=event_id,
            user_id=user_db.id,
            telegram_id=user.id
        )

    await query.answer(msg, show_alert=True)
    if ok and query.message:
        try:
            await query.message.reply_text(
                f"✅ **Siz ro'yxatga olindingiz!**\n\n{msg}",
                parse_mode="Markdown"
            )
        except Exception:
            pass


async def menu_daily_events_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kunlik voqealar markazi menyusi"""
    query = update.callback_query
    if query:
        await query.answer()

    user = update.effective_user
    now_uzb = datetime.utcnow() + timedelta(hours=5)
    today_str = now_uzb.strftime("%Y-%m-%d")

    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return

        # Bugungi barcha eventlarni olish
        events_res = await session.execute(
            models.DailyScheduledEvent.__table__.select().where(
                models.DailyScheduledEvent.event_date == today_str
            ).order_by(models.DailyScheduledEvent.id.desc())
        )
        today_events = events_res.fetchall()

        # Foydalanuvchi qatnashgan eventlar
        my_parts_res = await session.execute(
            models.DailyEventParticipant.__table__.select().where(
                models.DailyEventParticipant.user_id == user_db.id
            )
        )
        my_joined_event_ids = {r.event_id for r in my_parts_res.fetchall()}

    text = (
        f"🌟 **WESTEROS KUNLIK VOQEALARI (DAILY EVENTS)**\n\n"
        f"📅 Sana: **{today_str}** (Toshkent vaqti)\n\n"
        f"Har kuni 4 ta ajoyib voqea avtomatik ravishda bo'lib o'tadi:\n"
        f"• 🐉 **04:00** — Ajdarlar Parvozi (Barchaga 5 000 oltin)\n"
        f"• 💰 **12:00** — Qirollik Xazinasi (Oltin xazinasi)\n"
        f"• 🐫 **16:00** — Savdogarlar Karvoni (Resurslar va oltin)\n"
        f"• ❄️ **21:00** — Shimoldan Xavf (Oq Yuruvchilar jangi)\n\n"
    )

    buttons = []
    if today_events:
        text += "📋 **Bugungi voqealar holati:**\n\n"
        for ev in today_events:
            st_icon = "🟢 Faol" if ev.status == "active" else "🏁 Yakunlangan"
            is_joined = ev.id in my_joined_event_ids
            joined_str = " (Siz qatnashdingiz ✅)" if is_joined else ""

            text += (
                f"**{ev.title}**\n"
                f"Holati: {st_icon}{joined_str}\n"
                f"Ishtirokchilar: {ev.participants_count or 0} ta lord\n\n"
            )

            if ev.status == "active" and not is_joined:
                buttons.append([
                    InlineKeyboardButton(f"⚔️ {ev.title} — Qatnashish", callback_data=f"daily_event_join:{ev.id}")
                ])
    else:
        text += "ℹ️ *Bugun hali faol voqea boshlanmadi. Voqea boshlanganda barcha lordlarga xabar yuboriladi!*"

    buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

    kb = InlineKeyboardMarkup(buttons)
    if query and query.message:
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    elif update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def admin_trigger_daily_event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin buyrug'i: Eventni qo'lda boshlash (/trigger_event dragons_flight)"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Faqat Administratorlar uchun!")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Iltimos, event kodini kiriting:\n"
            "`/trigger_event dragons_flight`\n"
            "`/trigger_event royal_treasury`\n"
            "`/trigger_event merchant_caravan`\n"
            "`/trigger_event northern_threat`",
            parse_mode="Markdown"
        )
        return

    code = args[0].strip().lower()
    from core.daily_events_engine import start_event_by_code
    await start_event_by_code(context.application, code)
    await update.message.reply_text(f"✅ Event «{code}» muvaffaqiyatli boshlandi va xabar tarqatildi!")


async def admin_resolve_daily_event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin buyrug'i: Eventni qo'lda yakunlash va mukofotlarni berish (/resolve_event dragons_flight)"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Faqat Administratorlar uchun!")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Iltimos, event kodini kiriting: `/resolve_event dragons_flight`", parse_mode="Markdown")
        return

    code = args[0].strip().lower()
    from core.daily_events_engine import resolve_event_by_code
    await resolve_event_by_code(context.application, code)
    await update.message.reply_text(f"✅ Event «{code}» muvaffaqiyatli yakunlandi va mukofotlar tarqatildi!")


async def admin_resolve_dragon_tourney_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin buyrug'i: Kunlik ajdarlar turnirini hozir yakunlash (/resolve_dragon_tourney)"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Faqat Administratorlar uchun!")
        return

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.resolve_daily_dragon_tourney(session, bot_app=context.application)

    await update.message.reply_text(f"✅ Kunlik ajdarlar turniri natijasi:\n\n{msg}", parse_mode="Markdown")


def register_daily_events_handlers(app: Application):
    """Kunlik voqealar handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["daily_events", "voqealar", "events_daily"], menu_daily_events_callback))
    app.add_handler(CommandHandler("trigger_event", admin_trigger_daily_event_command))
    app.add_handler(CommandHandler("resolve_event", admin_resolve_daily_event_command))
    app.add_handler(CommandHandler("resolve_dragon_tourney", admin_resolve_dragon_tourney_command))
    app.add_handler(CallbackQueryHandler(menu_daily_events_callback, pattern="^menu_daily_events$"))
    app.add_handler(CallbackQueryHandler(daily_event_join_callback, pattern="^daily_event_join:"))
