from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from database import AsyncSessionLocal, crud, models
from keyboards.menus import back_to_main_keyboard
from config import escape_md
import html


async def raven_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/raven va /xat buyrug'i"""
    if context.args and len(context.args) >= 2:
        # Tezkor jo'natish: /xat <user> [gold] <text>
        await handle_quick_send_raven(update, context)
        return

    user_id = update.effective_user.id
    await show_raven_hub(update, user_id, is_message=True)


async def raven_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_raven callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_raven_hub(query, user_id, is_message=False)


async def show_raven_hub(target, user_id: int, is_message: bool):
    """Qarg'a pochtasi markazi"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            msg = "❌ Avval /start bosing."
            if is_message:
                await target.message.reply_text(msg)
            else:
                await target.edit_message_text(msg)
            return

        text = (
            "🐦 **QORA QARG'ALAR QAL'ASI (XAT TIZIMI)**\n\n"
            "Vesterosning eng ishonchli pochtasi! Qarg'alar orqali boshqa lordlarga "
            "sirli maktublar va oltin xazinalarini jo'natishingiz mumkin.\n\n"
            "📜 **Qanday yuboriladi?**\n"
            "Buyruq orqali oson yuborish:\n"
            "• Oddiy xat:\n`/xat @username Salom ittifoqdosh!`\n"
            "• Oltin bilan xat:\n`/xat @username 200 Bizga qo'shin yordami bering!`\n\n"
            f"💰 Hamyoningiz: **{user.gold:,}**🪙 oltin\n"
        )

        buttons = [
            [InlineKeyboardButton("📥 Kiruvchi Qarg'alar (Maktublar)", callback_data="raven_inbox")],
            [InlineKeyboardButton("✍️ Qanday yuborish bo'yicha qo'llanma", callback_data="raven_help")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ]
        keyboard = InlineKeyboardMarkup(buttons)

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def raven_inbox_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kiruvchi qarg'alarni ko'rish"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        inbox = await crud.get_inbox_ravens(session, user.id, limit=6)

        if not inbox:
            text = (
                "📥 **KIRUVCHI QARG'ALAR**\n\n"
                "📭 Hozircha sizga hech qanday qarg'a maktub keltirmadi.\n"
                "Boshqa lordlarga birinchi bo'lib yozing!"
            )
        else:
            text = "📥 **KIRUVCHI QARG'ALAR (So'nggi maktublar)**\n\n"
            for msg, sender_name in inbox:
                time_str = msg.created_at.strftime("%d.%m %H:%M") if msg.created_at else ""
                gold_str = f" (+{msg.gold_attached}🪙 oltin)" if msg.gold_attached > 0 else ""
                text += (
                    f"📨 **Kimdan:** {sender_name}{gold_str}\n"
                    f"⏰ *{time_str}*\n"
                    f"💬 *\"{html.escape(msg.message_text)}\"*\n"
                    "───────────────\n"
                )

        buttons = [
            [InlineKeyboardButton("🔄 Yangilash", callback_data="raven_inbox")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="menu_raven")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def raven_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qarg'a jo'natish yo'riqnomasi"""
    query = update.callback_query
    await query.answer()

    text = (
        "✍️ **QARG'A YUBORISH YO'RIQNOMASI**\n\n"
        "Boshqa lordga xat va oltin yuborish uchun chatga quyidagicha yozing:\n\n"
        "1️⃣ **Faqat xat:**\n"
        "`/xat @foydalanuvchi_nomi Xabaringiz matni...`\n\n"
        "2️⃣ **Xat + Oltin biriktirish:**\n"
        "`/xat @foydalanuvchi_nomi 150 Qal'angizni mustahkamlash uchun sovg'a!`\n\n"
        "💡 *Telegram ID orqali ham yuborish mumkin, masalan:*\n"
        "`/xat 123456789 Salom!`"
    )

    buttons = [
        [InlineKeyboardButton("🔙 Orqaga", callback_data="menu_raven")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def handle_quick_send_raven(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/xat @username [gold] text orqali tezkor jo'natish"""
    sender_tg_id = update.effective_user.id
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "❌ Xatolik! Foydalanish: `/xat @username [oltin] matn`\n"
            "Masalan: `/xat @lord_stark 100 Qal'amizga xush kelibsiz!`",
            parse_mode="Markdown"
        )
        return

    recipient_target = args[0]
    gold = 0
    message_start_idx = 1

    # Agar 2-argument son bo'lsa, oltin deb hisoblaymiz
    if args[1].isdigit() and len(args) >= 3:
        gold = int(args[1])
        message_start_idx = 2

    message_text = " ".join(args[message_start_idx:]).strip()
    if not message_text:
        await update.message.reply_text("❌ Maktub matnini yozishingiz kerak!")
        return

    async with AsyncSessionLocal() as session:
        sender = await crud.get_user_with_relations(session, sender_tg_id)
        if not sender:
            await update.message.reply_text("❌ Avval /start bosing.")
            return

        ok, msg, recipient_tg_id = await crud.send_raven(
            session=session,
            sender_id=sender.id,
            recipient_username_or_id=recipient_target,
            text=message_text,
            gold=gold
        )

        if not ok:
            await update.message.reply_text(f"❌ {msg}")
            return

        # Yuboruvchiga muvaffaqiyat xabari
        await update.message.reply_text(
            f"🐦 **QARG'A UCHIB KETDI!**\n\n{msg}\n"
            f"🪙 Biriktirilgan oltin: **{gold}**\n"
            f"📜 Matn: *\"{html.escape(message_text)}\"*",
            parse_mode="Markdown"
        )

        # Qabul qiluvchiga bildirishnoma yuborish
        if recipient_tg_id and recipient_tg_id != sender_tg_id:
            try:
                alert_text = (
                    "🐦 **QAL'ANGIZGA QORA QARG'A KELIB QO'NDI!**\n\n"
                    f"Kimdan: **{sender.full_name}** ({sender.house.name if sender.house else 'Xonadonsiz'})\n"
                )
                if gold > 0:
                    alert_text += f"💰 Xatga **+{gold:,}**🪙 oltin biriktirilgan va xazinangizga qo'shildi!\n"
                alert_text += f"\n📜 **Xat matni:**\n_{html.escape(message_text)}_\n\n"
                alert_text += f"✍️ Javob yozish: `/xat {sender.telegram_id} javob matni`"
                
                await context.bot.send_message(chat_id=recipient_tg_id, text=alert_text, parse_mode="Markdown")
            except Exception as e:
                # Bloklangan yoki bot chat ochilmagan bo'lishi mumkin
                pass


def register_raven_handlers(app):
    """Qarg'a pochtasi handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["raven", "xat", "pochta"], raven_command))
    app.add_handler(CallbackQueryHandler(raven_callback, pattern="^menu_raven$"))
    app.add_handler(CallbackQueryHandler(raven_inbox_callback, pattern="^raven_inbox$"))
    app.add_handler(CallbackQueryHandler(raven_help_callback, pattern="^raven_help$"))
