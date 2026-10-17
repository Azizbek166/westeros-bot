import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from keyboards.menus import back_to_main_keyboard

logger = logging.getLogger(__name__)


async def show_trade_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadonlararo savdo bozori (yopilganligi haqida bildirishnoma)"""
    query = update.callback_query
    text = (
        "⚖️ **SAVDO BOZORI FAOLIYATI TO'XTATILGAN**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Qirollik farmoyishiga binoan, savdo bozori va xonadonlararo birja paneli olib tashlangan.\n\n"
        "Barcha resurslarni o'z xonadoningiz qal'alaridan hamda kon va tegirmonlardan olishingiz mumkin."
    )
    keyboard = back_to_main_keyboard()

    if query:
        await query.answer("Bozor paneli yopilgan!", show_alert=True)
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def trade_create_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bozor yopilganligi haqida ogohlantirish"""
    query = update.callback_query
    await query.answer("Savdo bozori yopilgan!", show_alert=True)
    await show_trade_hub(update, context)


async def trade_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Savdo bozori to'xtatilgan!", show_alert=True)


async def trade_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Savdo bozori to'xtatilgan!", show_alert=True)


async def trade_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Savdo bozori to'xtatilgan!", show_alert=True)


async def create_trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "⚖️ **Savdo bozori faoliyati to'xtatilgan!**\nYangi e'lonlar qabul qilinmaydi.",
            parse_mode="Markdown"
        )


def register_trade_handlers(app):
    app.add_handler(CommandHandler("trade", show_trade_hub))
    app.add_handler(CommandHandler("bozor", show_trade_hub))
    app.add_handler(CommandHandler("createtrade", create_trade_command))
    app.add_handler(CallbackQueryHandler(show_trade_hub, pattern="^menu_trade$"))
    app.add_handler(CallbackQueryHandler(trade_create_menu_callback, pattern="^trade_create_menu$"))
    app.add_handler(CallbackQueryHandler(trade_add_callback, pattern="^trade_add:"))
    app.add_handler(CallbackQueryHandler(trade_buy_callback, pattern="^trade_buy:"))
    app.add_handler(CallbackQueryHandler(trade_cancel_callback, pattern="^trade_cancel:"))
