"""
The Iron Throne RPG — AI Council Advisor ("Kengash Maslahatchisi") Telegram Bot Handler.
Handles /maslahat, /ai, /advisor commands and interactive counsel callback queries.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from config import escape_md
from database.db import AsyncSessionLocal
from database import crud, models
import services

logger = logging.getLogger(__name__)


def get_advisor_menu_keyboard(remaining: int, daily_limit: int) -> InlineKeyboardMarkup:
    """Kengash maslahatchisi interaktiv inline tugmalari"""
    buttons = [
        [
            InlineKeyboardButton("🎯 Hozir nima qilay?", callback_data="ai_prompt_todo"),
            InlineKeyboardButton("⚔️ Armiya sirlari", callback_data="ai_prompt_army"),
        ],
        [
            InlineKeyboardButton("🐉 Ajdaho parvarishi", callback_data="ai_prompt_dragon"),
            InlineKeyboardButton("💰 Xazina va Bank", callback_data="ai_prompt_economy"),
        ],
        [
            InlineKeyboardButton("🌟 Season & Pass qoidalari", callback_data="ai_prompt_season"),
        ],
        [
            InlineKeyboardButton("👑 Mini App'da Meyster bilan Suhbat", callback_data="menu_open_miniapp"),
        ],
        [
            InlineKeyboardButton("🔙 Bosh Menyu", callback_data="main_menu"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


async def ai_advisor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /maslahat, /ai, /advisor buyruqlari.
    Agar argument berilsa (masalan: /maslahat Hozir nima qilay?), darhol javob beradi.
    Argument berilmasa, interaktiv maslahat menyusini chiqaradi.
    """
    user_tg = update.effective_user
    if not user_tg:
        return

    # Foydalanuvchi yozgan savol matnini ajratish
    args = context.args
    user_query = " ".join(args).strip() if args else ""

    chat_id = update.effective_chat.id if update.effective_chat else user_tg.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_tg.id)
        if not user:
            if update.message:
                await update.message.reply_text(
                    "❌ Siz hali ro'yxatdan o'tmagansiz. Avval /start buyrug'ini yuboring."
                )
            return

        # 1. Agar foydalanuvchi aniq savol yozgan bo'lsa
        if user_query:
            if update.message:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

            ok, answer, meta = await services.ask_council_advisor(session, user, user_query)
            rem = meta.get("remaining", 0)

            footer = f"\n\n──────────────\n📊 *Kunlik savollar limitingiz:* {rem} ta qoldi."
            full_reply = f"{answer}{footer}"

            if update.message:
                await update.message.reply_text(
                    full_reply,
                    parse_mode="Markdown",
                    reply_markup=get_advisor_menu_keyboard(rem, meta.get("daily_limit", 10)),
                )
            return

        # 2. Agar argument bo'lmasa, umumiy Kengash menyusini ko'rsatish
        status_info = await services.get_ai_advisor_status(session, user)
        rem = status_info.get("remaining_today", 0)
        limit = status_info.get("daily_limit", 10)
        vip_badge = "💎 VIP Zodagon" if status_info.get("is_vip") else "🛡️ Zodagon"

        text = (
            "🧙‍♂️ **QIROLLIK KENGASHI VA BUYUK MEYSTER MASLAHATI**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Assalomu alaykum, muhtaram Lord!\n\n"
            "Men Qirollik Kengashining Bosh Meysteriman. Sizga Vesteros qonun-qoidalari, "
            "harbiy yurishlar, armiya muvozanati, ajdaholarni boqish, xazinani boyitish va "
            "qal'alarni himoyalash bo'yicha yo'l ko'rsatishga doim tayyorman.\n\n"
            f"👤 Maqomingiz: *{vip_badge}*\n"
            f"📊 Bugungi savollar limitingiz: *{rem}/{limit} ta qoldi*\n\n"
            "Savolingizni to'g'ridan-to'g'ri quyidagicha yuborishingiz mumkin:\n"
            "👉 `/maslahat <savolingiz>` (masalan: `/maslahat Hozir nima qilay?`)\n\n"
            "Yoki quyidagi tayyor mavzulardan birini tanlang:"
        )

        kb = get_advisor_menu_keyboard(rem, limit)
        if update.message:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        elif update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def ai_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tayyor tezkor savol tugmalari bosilganda"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    prompt_map = {
        "ai_prompt_todo": "Hozir nima qilay? Keyingi eng muhim qadamim nima?",
        "ai_prompt_army": "Armiyada qaysi askarni ko'proq yollash kerak va jang taktikasi qanday?",
        "ai_prompt_dragon": "Ajdahoni qanday parvarishlash, boqish va kuchaytirish kerak?",
        "ai_prompt_economy": "Ko'proq oltin topish va Temir Bankdan foydalanish sirlari qanday?",
        "ai_prompt_season": "Mavsum va Season Pass qoidalari qanday ishlaydi?",
    }

    user_query = prompt_map.get(data, "Hozir nima qilay?")

    user_tg = update.effective_user
    if not user_tg:
        return

    chat_id = update.effective_chat.id if update.effective_chat else user_tg.id
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_tg.id)
        if not user:
            await query.edit_message_text("❌ Foydalanuvchi topilmadi.")
            return

        ok, answer, meta = await services.ask_council_advisor(session, user, user_query)
        rem = meta.get("remaining", 0)
        limit = meta.get("daily_limit", 10)

        footer = f"\n\n──────────────\n📊 *Kunlik limitingiz:* {rem}/{limit} ta qoldi."
        full_reply = f"{answer}{footer}"

        await query.edit_message_text(
            full_reply,
            parse_mode="Markdown",
            reply_markup=get_advisor_menu_keyboard(rem, limit),
        )


def register_ai_handlers(app):
    """AI Maslahatchi handlerlarini Telegram bot ilovasiga ulash"""
    app.add_handler(CommandHandler(["maslahat", "ai", "advisor"], ai_advisor_command))
    app.add_handler(CallbackQueryHandler(ai_advisor_command, pattern="^menu_ai_advisor$"))
    app.add_handler(CallbackQueryHandler(ai_topic_callback, pattern="^ai_prompt_"))
