"""
PROMO CODE HANDLER FOR THE IRON THRONE RPG
Foydalanuvchilar uchun /promo <code> (yoki matn orqali kiritish) va Admin Panel uchun to'liq "Promo-kodlar" boshqaruvi.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ApplicationHandlerStop,
)
from sqlalchemy import select
from database import AsyncSessionLocal, models
from services.promo_service import redeem_promo_code_service, create_promo_code_service, list_active_promo_codes
from config import is_admin


async def promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/promo <code> buyrug'i"""
    if not update.message:
        return

    user_id = update.effective_user.id
    args = context.args or []

    if not args:
        context.user_data["user_awaiting_promo_code"] = True
        await update.message.reply_text(
            "🎟 *PROMO-KOD ISHLATISH*\n\n"
            "Promo-kodni yozib yuboring (masalan: `DRAGON2026`) yoki `/promo KODINGIZ` buyrug'idan foydalaning.",
            parse_mode="Markdown"
        )
        return

    code_str = args[0].strip()
    context.user_data.pop("user_awaiting_promo_code", None)
    async with AsyncSessionLocal() as session:
        ok, msg, data = await redeem_promo_code_service(session, user_id, code_str)

    try:
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(msg.replace("*", ""))


async def promo_input_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_promo_input callback query"""
    query = update.callback_query
    await query.answer()
    context.user_data["user_awaiting_promo_code"] = True

    text = (
        "🎟 *PROMO-KOD KIRITISH*\n\n"
        "Sizda maxsus aksiya yoki sovg'a promo-kodi bormi?\n\n"
        "Promo-kodni shunchaki xabar qilib yozib yuboring (yoki `/promo KODINGIZ` deb yozing):"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ])
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        try:
            await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await query.message.reply_text(text.replace("*", "").replace("`", ""), reply_markup=kb)


# ============================================================
# ADMIN PANEL: PROMO-KODLAR BOSHQARUVI
# ============================================================
async def _render_admin_promos_menu(query, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as session:
        promos = await list_active_promo_codes(session)

    lines = [
        "🎟 *ADMIN: PROMO-KODLAR BOSHQARUVI*\n",
        f"Jami mavjud kodlar: *{len(promos)} ta*\n",
        "━━━━━━━━━━━━━━━━━━━━\n",
    ]

    kb_rows = [
        [InlineKeyboardButton("✍️ Maxsus Promo Yaratish", callback_data="admin_promo_create_custom")],
        [InlineKeyboardButton("⚡ Tezkor Promo Yaratish (VALYRIA)", callback_data="admin_promo_create_quick")],
    ]

    for p in promos[:10]:
        status_ico = "🟢" if p["is_active"] else "🔴"
        lines.append(f"{status_ico} `{p['code']}` | Ishlatildi: {p['uses']} | Mukofot: {p['rewards']}")
        toggle_lbl = f"🔴 O'chirish: {p['code']}" if p["is_active"] else f"🟢 Yoqish: {p['code']}"
        kb_rows.append([InlineKeyboardButton(toggle_lbl, callback_data=f"admin_promo_toggle:{p['id']}")])

    if not promos:
        lines.append("Hozircha hech qanday promo-kod yaratilmagan.")

    kb_rows.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(kb_rows)

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        try:
            await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await query.message.reply_text(text.replace("*", "").replace("`", ""), reply_markup=kb)


async def admin_promos_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panelidagi '🎟 Promo-kodlar' bo'limi"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    context.user_data.pop("admin_awaiting_promo_create", None)
    await _render_admin_promos_menu(query, context)


async def admin_promo_create_quick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tezkor namunaviy promo-kod yaratish (+1000 Oltin, +2000 Bug'doy, 100 limit)"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
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

    await query.answer(f"✅ {code} yaratildi!" if ok else f"❌ {msg}", show_alert=True)
    await _render_admin_promos_menu(query, context)


async def admin_promo_create_custom_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin maxsus promo-kod kiritishi uchun so'rov"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()

    context.user_data["admin_awaiting_promo_create"] = True
    text = (
        "✍️ *MAXSUS PROMO-KOD YARATISH*\n\n"
        "Quyidagi formatlardan birida xabar yuboring:\n"
        "1️⃣ Qisqa: `KOD OLTIN LIMIT`\n"
        "   Misol: `WINTER2026 1500 50`\n\n"
        "2️⃣ To'liq: `KOD OLTIN BUGDOY TEMIR NUFUZ LIMIT`\n"
        "   Misol: `STARK500 1000 2000 500 30 100`\n\n"
        "_(Bekor qilish uchun `bekor` deb yozing)_"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bekor qilish", callback_data="admin_promos_menu")]])
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await query.message.reply_text(text.replace("*", "").replace("`", ""), reply_markup=kb)


async def admin_promo_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promo-kodni faollashtirish yoki o'chirish"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    try:
        promo_id = int(query.data.split(":")[1])
    except Exception:
        await query.answer("❌ Noto'g'ri ID", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        promo = await session.get(models.PromoCode, promo_id)
        if not promo:
            await query.answer("❌ Promo-kod topilmadi!", show_alert=True)
            return
        promo.is_active = not promo.is_active
        await session.commit()
        status_txt = "faollashtirildi 🟢" if promo.is_active else "o'chirildi 🔴"

    await query.answer(f"Kod {status_txt}", show_alert=True)
    await _render_admin_promos_menu(query, context)


async def promo_text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin maxsus promo yaratish yoki o'yinchi promo-kod kiritish matnini ushlash"""
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    raw_text = update.message.text.strip()

    # 1. Admin maxsus promo yaratmoqda
    if context.user_data.get("admin_awaiting_promo_create") and is_admin(user_id):
        if raw_text.lower() in ("bekor", "cancel", "otmen"):
            context.user_data.pop("admin_awaiting_promo_create", None)
            await update.message.reply_text("❌ Promo-kod yaratish bekor qilindi.")
            raise ApplicationHandlerStop

        parts = raw_text.split()
        if len(parts) not in (3, 6):
            await update.message.reply_text(
                "❌ Format noto'g'ri!\n"
                "Qisqa: `KOD OLTIN LIMIT` (masalan `WINTER 1000 50`)\n"
                "Yoki to'liq: `KOD OLTIN BUGDOY TEMIR NUFUZ LIMIT`",
                parse_mode="Markdown"
            )
            raise ApplicationHandlerStop

        try:
            code = parts[0].strip().upper()
            if len(parts) == 3:
                gold, max_uses = int(parts[1]), int(parts[2])
                food, iron, prestige = 0, 0, 0
            else:
                gold, food, iron, prestige, max_uses = (
                    int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
                )
        except ValueError:
            await update.message.reply_text("❌ Raqamlar noto'g'ri kiritildi! Qaytadan urinib ko'ring.")
            raise ApplicationHandlerStop

        context.user_data.pop("admin_awaiting_promo_create", None)
        async with AsyncSessionLocal() as session:
            ok, msg, promo = await create_promo_code_service(
                session=session,
                code=code,
                gold=max(0, gold),
                food=max(0, food),
                iron=max(0, iron),
                prestige=max(0, prestige),
                max_uses=max(1, max_uses),
            )

        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎟 Promo-kodlar Menyu", callback_data="admin_promos_menu")]])
        await update.message.reply_text(f"{'✅' if ok else '❌'} {msg}", reply_markup=kb)
        raise ApplicationHandlerStop

    # 2. O'yinchi promo-kod kiritmoqda
    if context.user_data.get("user_awaiting_promo_code"):
        context.user_data.pop("user_awaiting_promo_code", None)
        if raw_text.lower() in ("bekor", "cancel"):
            await update.message.reply_text("❌ Bekor qilindi.")
            raise ApplicationHandlerStop

        code_str = raw_text.split()[0].strip()
        async with AsyncSessionLocal() as session:
            ok, msg, _ = await redeem_promo_code_service(session, user_id, code_str)

        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")]])
        try:
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await update.message.reply_text(msg.replace("*", ""), reply_markup=kb)
        raise ApplicationHandlerStop


def register_promo_handlers(app: Application):
    """Promo handlerlarini ulash"""
    app.add_handler(CommandHandler("promo", promo_command))
    app.add_handler(CallbackQueryHandler(promo_input_menu_callback, pattern="^menu_promo_input$"))
    app.add_handler(CallbackQueryHandler(admin_promos_menu_callback, pattern="^admin_promos_menu$"))
    app.add_handler(CallbackQueryHandler(admin_promo_create_quick_callback, pattern="^admin_promo_create_quick$"))
    app.add_handler(CallbackQueryHandler(admin_promo_create_custom_callback, pattern="^admin_promo_create_custom$"))
    app.add_handler(CallbackQueryHandler(admin_promo_toggle_callback, pattern="^admin_promo_toggle:[0-9]+$"))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, promo_text_input_handler),
        group=1,
    )
