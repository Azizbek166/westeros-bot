"""
ACHIEVEMENT HANDLER FOR THE IRON THRONE RPG
Foydalanuvchiga barcha yutuqlar holati va mukofotlarni ko'rsatish bo'limi ("🏅 Yutuqlar").
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal
from services.achievement_service import get_user_achievements


async def achievements_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_achievements callback query"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        data = await get_user_achievements(session, user_id)

    total = data.get("total_count", 0)
    unlocked_cnt = data.get("unlocked_count", 0)
    pct = data.get("progress_pct", 0)
    progress_bar = "🟩" * (pct // 10) + "⬜" * (10 - (pct // 10))

    lines = [
        f"🏅 **QIROLLIK SHON-SHARAF YUTUQLARI**\n",
        f"🏆 Jarayon: **{unlocked_cnt}/{total}** ({pct}%)\n{progress_bar}\n",
        f"━━━━━━━━━━━━━━━━━━━━\n",
    ]

    for item in data.get("achievements", []):
        if item["is_unlocked"]:
            lines.append(f"✅ **{item['title']}**\n   _{item['desc']}_\n   📅 _Ochilgan: {item['unlocked_at']}_\n")
        else:
            reward_txt = f"+{item['gold']:,}🪙 +{item['iron']:,}⛓️ +{item['prestige']}⭐"
            lines.append(f"🔒 **{item['title']}**\n   _{item['desc']}_\n   🎁 Mukofot: {reward_txt}\n")

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="menu_achievements")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ])

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/achievements yoki /yutuqlar buyrug'i"""
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        data = await get_user_achievements(session, user_id)

    total = data.get("total_count", 0)
    unlocked_cnt = data.get("unlocked_count", 0)
    pct = data.get("progress_pct", 0)

    lines = [
        f"🏅 **QIROLLIK SHON-SHARAF YUTUQLARI**\n",
        f"🏆 Jarayon: **{unlocked_cnt}/{total}** ({pct}%)\n",
        f"━━━━━━━━━━━━━━━━━━━━\n",
    ]

    for item in data.get("achievements", []):
        status_icon = "✅" if item["is_unlocked"] else "🔒"
        lines.append(f"{status_icon} **{item['title']}** — _{item['desc']}_")

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏅 To'liq Ko'rish", callback_data="menu_achievements")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ])

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


def register_achievement_handlers(app: Application):
    """Achievement handlerlarini ulash"""
    app.add_handler(CommandHandler(["achievements", "yutuqlar"], achievements_command))
    app.add_handler(CallbackQueryHandler(achievements_menu_callback, pattern="^menu_achievements$"))
