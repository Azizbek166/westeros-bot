import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from config import OWNER_ID, ADMIN_IDS, escape_md
from core.notifier import notify_admins
from keyboards.menus import back_to_main_keyboard

logger = logging.getLogger(__name__)

# O'yin ichidagi maxsus interaktiv kiritish holatlari
INTERACTIVE_KEYS = [
    "awaiting_custom_name",
    "awaiting_recruit_input",
    "awaiting_march_input",
    "awaiting_rf_input",
    "awaiting_with_input",
    "awaiting_house_with_input",
    "awaiting_house_donate_input",
    "awaiting_bank_dep_input",
    "awaiting_bank_with_input",
    "awaiting_donate_receipt",
    "awaiting_vip_photo",
    "awaiting_vip_status",
    "awaiting_vip_audio",
    "awaiting_vip_decree",
]

BOTTOM_MENU_TEXTS = {
    "🏠 Bosh Menyu",
    "🏰 Qalalarim",
    "💎 VIP & Donate",
    "📢 Guruh & Kanal",
}


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/murojaat, /support, /yordam, /help, /sorov buyruqlari"""
    text = (
        "✍️ **ADMINISTRATSIYAGA MUROJAAT VA SO'ROV**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Hurmatli Lord! O'yindagi har qanday savol, taklif, shikoyat yoki yordam so'rovingiz bo'lsa, "
        "xabaringizni shu yerga yozib yuborishingiz mumkin.\n\n"
        "⚡ **Har bir yuborgan so'rovingiz darhol barcha administratorlarga yetkaziladi!**\n\n"
        "Iltimos, so'rovingiz mazmunini bitta xabarda batafsil bayon qilib yozing:"
    )
    if update.message:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=back_to_main_keyboard()
        )
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=back_to_main_keyboard()
        )


async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_support callback query"""
    await support_command(update, context)


async def player_text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi erkin matn yuborganda uni barcha adminlarga so'rov sifatida yetkazish (Faqat shaxsiy chatda!)"""
    # Guruhda hech qachon tasodifiy xabarlarga javob bermaydi
    if not update.effective_chat or update.effective_chat.type != "private":
        return

    if not update.effective_message or not update.effective_message.text:
        return

    text = update.effective_message.text.strip()
    if text.startswith("/"):
        return

    if text in BOTTOM_MENU_TEXTS:
        return

    # Agar boshqa modulda biror narsa kiritish kutilyotgan bo'lsa, unga xalaqit bermaymiz
    for k in INTERACTIVE_KEYS:
        if k in context.user_data:
            return

    user = update.effective_user
    if not user:
        return

    user_id = user.id
    admin_set = set([int(OWNER_ID)] + [int(a) for a in ADMIN_IDS])

    # Agar admin o'zi biror narsa yozsa, uni audit qilib o'tirmaymiz
    if user_id in admin_set:
        return

    full_name = user.full_name or "Noma'lum"
    username_str = f"@{user.username}" if user.username else "yo'q"
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # 1. Barcha adminlarga darhol bildirishnoma jo'natish
    admin_text = (
        f"📩 *O'YINCHIDAN YANGI SO'ROV / MUROJAAT!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Kimdan: *{escape_md(full_name)}* (`{user_id}`)\n"
        f"🔗 Username: {username_str}\n"
        f"⏱️ Vaqt: `{now_str}`\n\n"
        f"💬 **Xabar mazmuni:**\n"
        f"_{escape_md(text)}_"
    )

    admin_kb = None
    if user.username:
        admin_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💬 {full_name} ga Javob Berish", url=f"https://t.me/{user.username}")]
        ])

    await notify_admins(context.application, admin_text, reply_markup=admin_kb)

    # 2. O'yinchiga xabar yetkazilgani haqida tasdiq
    reply_text = (
        "📬 **SIZNING SO'ROVINGIZ QABUL QILINDI!**\n\n"
        "Hurmatli Lord, siz yuborgan so'rov va murojaat bot administratorlariga muvaffaqiyatli yetkazildi.\n"
        "Tez orada ko'rib chiqiladi va kerak bo'lsa siz bilan bog'lanishadi.\n\n"
        "🏠 Asosiy menyuga qaytish uchun pastdagi tugmani bosing:"
    )

    await update.effective_message.reply_text(
        reply_text,
        parse_mode="Markdown",
        reply_markup=back_to_main_keyboard()
    )


def register_support_handlers(app):
    app.add_handler(CommandHandler(["murojaat", "support", "yordam", "help", "sorov"], support_command))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="^menu_support$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, player_text_message_handler), group=5)
