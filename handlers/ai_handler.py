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
    from config import ENABLE_MINIAPP
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
    ]
    if ENABLE_MINIAPP:
        buttons.append([
            InlineKeyboardButton("👑 Mini App'da Meyster bilan Suhbat", callback_data="menu_open_miniapp"),
        ])
    buttons.append([
        InlineKeyboardButton("🔙 Bosh Menyu", callback_data="menu_main"),
    ])
    return InlineKeyboardMarkup(buttons)


async def _send_or_edit_ai_reply(update: Update, text: str, kb: InlineKeyboardMarkup, edit: bool = False) -> None:
    """AI javobini Markdown xatolarisiz xavfsiz yuborish yoki tahrirlash"""
    safe_text = text[:4000] + "..." if len(text) > 4000 else text
    plain_text = safe_text.replace("*", "").replace("_", "").replace("`", "")

    if edit and update.callback_query:
        query = update.callback_query
        try:
            await query.edit_message_text(safe_text, parse_mode="Markdown", reply_markup=kb)
            return
        except Exception:
            try:
                await query.edit_message_text(plain_text, parse_mode=None, reply_markup=kb)
                return
            except Exception:
                pass
        if query.message:
            try:
                await query.message.reply_text(safe_text, parse_mode="Markdown", reply_markup=kb)
                return
            except Exception:
                await query.message.reply_text(plain_text, parse_mode=None, reply_markup=kb)
        return

    msg = update.effective_message
    if msg:
        try:
            await msg.reply_text(safe_text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await msg.reply_text(plain_text, parse_mode=None, reply_markup=kb)


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
    if not user_query and update.effective_message and update.effective_message.text:
        parts = update.effective_message.text.strip().split(None, 1)
        if len(parts) > 1 and not parts[0].lower().startswith("/start"):
            user_query = parts[1].strip()

    # Foydalanuvchi < > yoki « » yoki qo'shtirnoq ichida yozgan bo'lsa tozalash
    if user_query.startswith("<") and user_query.endswith(">") and len(user_query) > 2:
        user_query = user_query[1:-1].strip()
    elif user_query.startswith("«") and user_query.endswith("»") and len(user_query) > 2:
        user_query = user_query[1:-1].strip()
    elif user_query.startswith('"') and user_query.endswith('"') and len(user_query) > 2:
        user_query = user_query[1:-1].strip()
    elif user_query.startswith("'") and user_query.endswith("'") and len(user_query) > 2:
        user_query = user_query[1:-1].strip()

    chat_id = update.effective_chat.id if update.effective_chat else user_tg.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_tg.id)
        if not user:
            err_msg = "❌ Siz hali ro'yxatdan o'tmagansiz. Avval /start buyrug'ini yuboring."
            if update.callback_query:
                await update.callback_query.answer(err_msg, show_alert=True)
            elif update.message:
                await update.message.reply_text(err_msg)
            return

        # 1. Agar foydalanuvchi aniq savol yozgan bo'lsa
        if user_query:
            if update.message:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

            ok, answer, meta = await services.ask_council_advisor(session, user, user_query)
            rem = meta.get("remaining", 0)

            footer = f"\n\n──────────────\n📊 *Kunlik savollar limitingiz:* {rem} ta qoldi."
            full_reply = f"{answer}{footer}"

            await _send_or_edit_ai_reply(
                update,
                full_reply,
                get_advisor_menu_keyboard(rem, meta.get("daily_limit", 10)),
                edit=False,
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
            "👉 `/maslahat savolingiz` (masalan: `/maslahat Ajdahoni qanday kuchaytiraman?`)\n\n"
            "Yoki quyidagi tayyor mavzulardan birini tanlang:"
        )

        kb = get_advisor_menu_keyboard(rem, limit)
        if update.callback_query:
            await update.callback_query.answer()
            await _send_or_edit_ai_reply(update, text, kb, edit=True)
        elif update.message:
            await _send_or_edit_ai_reply(update, text, kb, edit=False)


async def ai_advisor_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi xabarda maslahat yoki maslaxat so'raganda javob berish"""
    msg = update.effective_message
    if not msg or not msg.text:
        return
    text = msg.text.strip()
    parts = text.split(None, 1)
    if len(parts) > 1:
        context.args = parts[1].strip().split()
    else:
        context.args = []
    await ai_advisor_command(update, context)


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

        await _send_or_edit_ai_reply(
            update,
            full_reply,
            get_advisor_menu_keyboard(rem, limit),
            edit=True,
        )


def register_ai_handlers(app):
    """AI Maslahatchi handlerlarini Telegram bot ilovasiga ulash"""
    import re
    from telegram.ext import MessageHandler, filters

    ai_cmds = [
        "maslahat", "maslaxat",
        "ai", "advisor",
        "meyster", "meystr",
        "kengash", "savol",
    ]
    app.add_handler(CommandHandler(ai_cmds, ai_advisor_command))
    app.add_handler(CallbackQueryHandler(ai_advisor_command, pattern="^menu_ai_advisor$"))
    app.add_handler(CallbackQueryHandler(ai_topic_callback, pattern="^ai_prompt_"))
    app.add_handler(
        MessageHandler(
            filters.Regex(re.compile(r"^[/!]?(maslahat|maslaxat|meyster|meystr|kengash)(\s+.*)?$", re.IGNORECASE)) & filters.ChatType.PRIVATE,
            ai_advisor_text_handler,
        )
    )
