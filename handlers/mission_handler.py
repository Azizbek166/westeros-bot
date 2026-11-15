"""
Haftalik va Ajdaho Missiyalari Telegram Handler (prefiks: msn_).
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from database import AsyncSessionLocal
from services.mission_service import get_missions_overview, claim_mission_reward

logger = logging.getLogger(__name__)


def _status_icon(status: str) -> str:
    if status == "claimed":
        return "✅"
    if status == "claimable":
        return "🎁"
    return "⏳"


async def _render_missions_view(user_tg_id: int):
    async with AsyncSessionLocal() as session:
        data = await get_missions_overview(session, user_tg_id)

    if not data.get("found"):
        return "❌ Avval /start buyrug'i orqali ro'yxatdan o'ting.", InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")]
        ])

    lines = [
        "🎯 *HAFTALIK VA AJDAHO MISSIYALARI*",
        f"⏳ Hafta tugashigacha: *{data['remaining_str']}*",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    buttons = []
    for m in data["missions"]:
        icon = _status_icon(m["status"])
        lines.append(
            f"{icon} *{m['title']}* ({m['current']}/{m['target']})\n"
            f"   {m['desc']}\n"
            f"   Mukofot: +{m['gold']:,}🪙 +{m['food']:,}🌾 +{m['iron']:,}⛓️ +{m['xp']}XP +{m['prestige']}⭐"
        )
        if m["status"] == "claimable":
            buttons.append([
                InlineKeyboardButton(
                    f"🎁 Mukofotni olish: {m['title'][:22]}",
                    callback_data=f"msn_claim:{m['code']}",
                )
            ])

    bonus = data.get("bonus")
    if bonus:
        b_icon = _status_icon(bonus["status"])
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(
            f"{b_icon} *{bonus['title']}* ({bonus['current']}/{bonus['target']})\n"
            f"   Mukofot: +{bonus['gold']:,}🪙 +{bonus['food']:,}🌾 +{bonus['iron']:,}⛓️ +{bonus['xp']}XP +{bonus['prestige']}⭐"
        )
        if bonus["status"] == "claimable":
            buttons.append([
                InlineKeyboardButton("🏆 Hafta Bonusini Olish!", callback_data=f"msn_claim:{bonus['code']}")
            ])

    buttons.append([InlineKeyboardButton("🔄 Yangilash", callback_data="msn_menu")])
    buttons.append([InlineKeyboardButton("🔙 Questlarga Qaytish", callback_data="menu_quests")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def missions_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text, kb = await _render_missions_view(query.from_user.id)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        try:
            await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=kb)
        except Exception:
            if query.message:
                await query.message.reply_text(text.replace("*", ""), reply_markup=kb)


async def missions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, kb = await _render_missions_view(update.effective_user.id)
    try:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await update.message.reply_text(text.replace("*", ""), reply_markup=kb)


async def mission_claim_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    mission_code = data.split(":", 1)[1] if ":" in data else ""

    async with AsyncSessionLocal() as session:
        ok, msg, rewards = await claim_mission_reward(session, query.from_user.id, mission_code)

    if ok and rewards:
        alert_txt = (
            f"{msg}\n"
            f"+{rewards['gold']:,}🪙 +{rewards['food']:,}🌾 +{rewards['iron']:,}⛓️ "
            f"+{rewards['xp']} XP +{rewards['prestige']}⭐"
        )
    else:
        alert_txt = msg
    await query.answer(alert_txt, show_alert=True)

    text, kb = await _render_missions_view(query.from_user.id)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        try:
            await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=kb)
        except Exception:
            pass


def register_mission_handlers(app: Application):
    app.add_handler(CommandHandler(["missions", "missiyalar"], missions_command))
    app.add_handler(CallbackQueryHandler(missions_menu_callback, pattern="^msn_menu$"))
    app.add_handler(CallbackQueryHandler(mission_claim_callback, pattern="^msn_claim:"))
