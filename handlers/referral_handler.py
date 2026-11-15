"""
REFERRAL HANDLER FOR THE IRON THRONE RPG
Foydalanuvchilarga o'z taklif havolasini olish va referal statistikasini ko'rish imkonini beradi.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal
from services.referral_service import get_referral_info
from keyboards.menus import back_to_main_keyboard


async def referral_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_referral callback query"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    bot_username = context.bot.username if context.bot and context.bot.username else "iron_throne_rpg_bot"

    async with AsyncSessionLocal() as session:
        info = await get_referral_info(session, user_id)

    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    text = (
        f"👥 **DO'STLARNI TAKLIF QILISH (REFERAL TIZIMI)**\n\n"
        f"Do'stlaringizni Vesteros taxti uchun kurashga chaqiring va qimmatbaho resurslarga ega bo'ling!\n\n"
        f"🔗 **Sizning shaxsiy taklif havolangiz:**\n"
        f"`{ref_link}`\n\n"
        f"📊 **Sizning Referal Statistikangiz:**\n"
        f"• Jami taklif etilganlar: **{info.get('total_invited', 0)} ta**\n"
        f"• Qasamyod qilgan lordlar: **{info.get('active_recruits', 0)} ta**\n"
        f"• Ishlangan oltin: **+{info.get('total_gold_earned', 0):,} 🪙**\n"
        f"• Ishlangan nufuz: **+{info.get('total_prestige_earned', 0):,} ⭐**\n\n"
        f"📜 **Qoidalar:**\n"
        f"1. Faqat yangi o'yinchilar hisobga olinadi.\n"
        f"2. O'zini o'zi taklif qilish taqiqlangan.\n"
        f"3. Do'stingiz botga kirib **xonadon tanlagach**, har ikkingizga mukofot avtomatik beriladi!"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Havolani Ulashish", url=f"https://t.me/share/url?url={ref_link}&text=Vesterosda+Temir+Taxt+uchun+urush+boshlandi!+Qasamyod+qil+va+o'z+xonadoningni+boshqar!")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ])

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ref yoki /referral buyrug'i"""
    user_id = update.effective_user.id
    bot_username = context.bot.username if context.bot and context.bot.username else "iron_throne_rpg_bot"

    async with AsyncSessionLocal() as session:
        info = await get_referral_info(session, user_id)

    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    text = (
        f"👥 **DO'STLARNI TAKLIF QILISH (REFERAL TIZIMI)**\n\n"
        f"🔗 **Sizning shaxsiy taklif havolangiz:**\n"
        f"`{ref_link}`\n\n"
        f"📊 Taklif etilganlar: **{info.get('total_invited', 0)} ta**\n"
        f"⭐ Ishlangan nufuz: **+{info.get('total_prestige_earned', 0):,}**\n\n"
        f"Do'stingiz xonadon tanlagan zahoti mukofot hisobingizga tushadi!"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Havolani Ulashish", url=f"https://t.me/share/url?url={ref_link}&text=Vesterosda+Temir+Taxt+uchun+urush+boshlandi!+Qasamyod+qil+va+o'z+xonadoningni+boshqar!")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ])

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


def register_referral_handlers(app: Application):
    """Referral handlerlarini ulash"""
    app.add_handler(CommandHandler(["ref", "referral"], referral_command))
    app.add_handler(CallbackQueryHandler(referral_menu_callback, pattern="^menu_referral$"))
