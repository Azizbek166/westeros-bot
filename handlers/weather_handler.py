import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud
from config import ADMIN_IDS

logger = logging.getLogger(__name__)


async def weather_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ob-havo va dinamik fasllar menyusi"""
    query = update.callback_query
    if query:
        await query.answer()

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        weather = await crud.get_current_weather(session)

        exp_str = weather.get("expires_at", "")
        rem_text = "Noma'lum"
        if exp_str:
            try:
                exp_dt = datetime.fromisoformat(exp_str)
                now = datetime.utcnow()
                diff = exp_dt - now
                days = max(0, diff.days)
                hours = max(0, diff.seconds // 3600)
                rem_text = f"{days} kun, {hours} soat"
            except Exception:
                rem_text = "7 kun"

        text = (
            f"🌤️📜 **WESTEROS FASLLARI VA DINAMIK OB-HAVO**\n\n"
            f"Hozirgi hukmron fasl:\n"
            f"{weather.get('emoji', '🌤️')} **{weather.get('name', 'Noma''lum')}**\n\n"
            f"📖 **Faslning Saltanatga Ta'siri:**\n"
            f"_{weather.get('description', '')}_\n\n"
            f"⏱️ **Mavsum tugash muddati:** {rem_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌍 **Barcha Fasllar Sikli (Har 7 kunda aylanadi):**\n"
            f"• ❄️ **Qattiq Qish:** Shimolda qal'alar mudofaasi +15%, ammo qahraton ayoz askarlarning oziq-ovqat sarfini +25% oshiradi.\n"
            f"• ☀️ **Yozgi Mo'l-ko'llik:** Hosildorlik +50%, qal'a va shaharlardan tushadigan o'lpon solig'i +25% oshadi.\n"
            f"• ⛈️ **Bo'ron Fasli:** Bo'ron kamonchilar zarbini -15% pasaytiradi, yurishlar +20% sekinlashadi, lekin trebushet toshlari qal'a devorlariga +10% kuchliroq uriladi.\n"
            f"• 🌪️ **Vahshiy Shamollar:** Drakarys alangasi va ajdarlarning parvoz kuchi +25% ga ortadi!"
        )

        buttons = []
        buttons.append([InlineKeyboardButton("🔄 Yangilash", callback_data="menu_weather")])

        if tg_user and tg_user.id in ADMIN_IDS:
            buttons.append([InlineKeyboardButton("⚙️ Faslni O'zgartirish (Admin)", callback_data="admin_weather_pick")])

        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        keyboard = InlineKeyboardMarkup(buttons)
        if query:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.effective_message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def admin_weather_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: fasl tanlash"""
    query = update.callback_query
    await query.answer()

    tg_user = update.effective_user
    if tg_user.id not in ADMIN_IDS:
        return

    text = "⚙️🌤️ **WESTEROS UZRA FASLNI TANLANG (ADMIN):**\n\nQaysi ob-havo darhol butun Westerosda o'rnatilsin?"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❄️ Qattiq Qish (Severe Winter)", callback_data="admin_weather_set:severe_winter")],
        [InlineKeyboardButton("☀️ Yozgi Mo'l-ko'llik (Summer Abundance)", callback_data="admin_weather_set:summer_abundance")],
        [InlineKeyboardButton("⛈️ Bo'ron Fasli (Storm Season)", callback_data="admin_weather_set:storm_season")],
        [InlineKeyboardButton("🌪️ Vahshiy Shamollar (Wild Winds)", callback_data="admin_weather_set:wild_winds")],
        [InlineKeyboardButton("🔙 Ob-havo menyusi", callback_data="menu_weather")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def admin_weather_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: faslni qo'lda o'rnatish"""
    query = update.callback_query
    await query.answer("Fasl o'rnatilmoqda...")

    tg_user = update.effective_user
    if tg_user.id not in ADMIN_IDS:
        return

    w_type = query.data.split(":")[1]
    async with AsyncSessionLocal() as session:
        await crud.rotate_world_weather(session, new_weather_type=w_type, bot_app=context.application)

    await weather_menu_callback(update, context)


def register_weather_handlers(app: Application):
    """Ob-havo handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["weather", "season_weather"], weather_menu_callback))
    app.add_handler(CallbackQueryHandler(weather_menu_callback, pattern="^menu_weather$"))
    app.add_handler(CallbackQueryHandler(admin_weather_pick_callback, pattern="^admin_weather_pick$"))
    app.add_handler(CallbackQueryHandler(admin_weather_set_callback, pattern="^admin_weather_set:(severe_winter|summer_abundance|storm_season|wild_winds)$"))
