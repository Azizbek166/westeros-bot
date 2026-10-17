from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from config import COMMUNITY_CHANNEL_URL, COMMUNITY_GROUP_URL, escape_md
from keyboards.menus import back_to_main_keyboard


def community_keyboard() -> InlineKeyboardMarkup:
    """Kanal va guruhga o'tish tugmalari"""
    buttons = [
        [
            InlineKeyboardButton("📢 Rasmiy Kanalga A'zo Bo'lish", url=COMMUNITY_CHANNEL_URL),
        ],
        [
            InlineKeyboardButton("💬 Rasmiy Guruhga Qo'shilish", url=COMMUNITY_GROUP_URL),
        ],
        [
            InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


async def community_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/community, /channel, /group buyruqlari"""
    text = (
        "📢 **WESTEROS RASMIY HAMJAMIYATI**\n\n"
        "Vesteros olamining rasmiy axborot manbasi va jangovar ittifoq maydoniga xush kelibsiz!\n\n"
        "👑 **Hamjamiyatda sizni nimalar kutmoqda?**\n"
        "• 📰 Yangi yangilanishlar, patchnotlar va tadbirlar;\n"
        "• ⚔️ Boshqa lordlar bilan muzokaralar, urush e'lonlari va savdo;\n"
        "• 🏆 Maxsus turnirlar, viktorinalar va qimmatbaho yutuqlar;\n"
        "• 💬 Savollaringizga tezkor javob va o'yin yordami.\n\n"
        "Quyidagi tugmalar orqali kanal va guruhimizga ulaning:"
    )
    if update.message:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=community_keyboard(),
            disable_web_page_preview=True
        )


async def community_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_community callback query"""
    query = update.callback_query
    await query.answer()

    text = (
        "📢 **WESTEROS RASMIY HAMJAMIYATI**\n\n"
        "Vesteros olamining rasmiy axborot manbasi va jangovar ittifoq maydoniga xush kelibsiz!\n\n"
        "👑 **Hamjamiyatda sizni nimalar kutmoqda?**\n"
        "• 📰 Yangi yangilanishlar, patchnotlar va tadbirlar;\n"
        "• ⚔️ Boshqa lordlar bilan muzokaralar, urush e'lonlari va savdo;\n"
        "• 🏆 Maxsus turnirlar, viktorinalar va qimmatbaho yutuqlar;\n"
        "• 💬 Savollaringizga tezkor javob va o'yin yordami.\n\n"
        "Quyidagi tugmalar orqali kanal va guruhimizga ulaning:"
    )
    try:
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=community_keyboard(),
            disable_web_page_preview=True
        )
    except Exception:
        await query.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=community_keyboard(),
            disable_web_page_preview=True
        )


def register_community_handlers(app):
    """Hamjamiyat handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["community", "channel", "group", "kanal", "guruh"], community_command))
    app.add_handler(CallbackQueryHandler(community_callback, pattern="^menu_community$"))
