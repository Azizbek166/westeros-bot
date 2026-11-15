"""
PROMO CODE HANDLER FOR THE IRON THRONE RPG
Foydalanuvchilar uchun /promo <code> va Admin Panel uchun "Promo-kodlar" boshqaruvi.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from database import AsyncSessionLocal
from services.promo_service import redeem_promo_code_service, create_promo_code_service, list_active_promo_codes
from config import is_admin


async def promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/promo <code> buyrug'i"""
    if not update.message:
        return

    user_id = update.effective_user.id
    args = context.args or []

    if not args:
        await update.message.reply_text(
            "🎟 **PROMO-KOD ISHLATISH**\n\n"
            "Promo-kodni quyidagicha yuboring:\n"
            "👉 `/promo KODINGIZ`\n\n"
            "Misol: `/promo DRAGON2026`",
            parse_mode="Markdown"
        )
        return

    code_str = args[0].strip()
    async with AsyncSessionLocal() as session:
        ok, msg, data = await redeem_promo_code_service(session, user_id, code_str)

    await update.message.reply_text(msg, parse_mode="Markdown")


async def promo_input_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_promo_input callback query"""
    query = update.callback_query
    await query.answer()

    text = (
        "🎟 **PROMO-KOD KIRITISH**\n\n"
        "Sizda maxsus aksiya yoki sovg'a promo-kodi bormi?\n\n"
        "Botga quyidagi buyruqni yuboring:\n"
        "👉 `/promo KODINGIZ`"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ])
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ============================================================
# ADMIN PANEL: PROMO-KODLAR BOSHQARUVI
# ============================================================
async def admin_promos_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panelidagi '🎟 Promo-kodlar' bo'limi"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        promos = await list_active_promo_codes(session)

    lines = [
        "🎟 **ADMIN: PROMO-KODLAR BOSHQARUVI**\n",
        f"Jami mavjud kodlar: **{len(promos)} ta**\n",
        "━━━━━━━━━━━━━━━━━━━━\n",
    ]

    for p in promos[:10]:
        status_ico = "🟢" if p["is_active"] else "🔴"
        lines.append(f"{status_ico} `{p['code']}` | Ishlatildi: {p['uses']} | Mukofot: {p['rewards']}")

    if not promos:
        lines.append("Hozircha hech qanday promo-kod yaratilmagan.")

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Yangi Promo Yaratish (Standart)", callback_data="admin_promo_create_quick")],
        [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
    ])

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def admin_promo_create_quick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tezkor namunaviy promo-kod yaratish (+1000 Oltin, +2000 Bug'doy, 100 limit)"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    import random
    code = f"VALYRIA{random.randint(100, 999)}"

    async with AsyncSessionLocal() as session:
        ok, msg, promo = await create_promo_code_service(
            session=session,
            code=code,
            gold=1000,
            food=2000,
            iron=500,
            prestige=25,
            max_uses=100,
        )

    await query.answer(f"✅ {code} yaratildi!", show_alert=True)
    await admin_promos_menu_callback(update, context)


def register_promo_handlers(app: Application):
    """Promo handlerlarini ulash"""
    app.add_handler(CommandHandler("promo", promo_command))
    app.add_handler(CallbackQueryHandler(promo_input_menu_callback, pattern="^menu_promo_input$"))
    app.add_handler(CallbackQueryHandler(admin_promos_menu_callback, pattern="^admin_promos_menu$"))
    app.add_handler(CallbackQueryHandler(admin_promo_create_quick_callback, pattern="^admin_promo_create_quick$"))
