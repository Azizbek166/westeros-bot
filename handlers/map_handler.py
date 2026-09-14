from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud
from keyboards.menus import territories_keyboard, back_to_main_keyboard
from config import escape_md


async def map_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/map buyrug'i"""
    user_id = update.effective_user.id
    await show_map(update, user_id, is_message=True)


async def map_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_map callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_map(query, user_id, is_message=False)


async def show_map(target, user_id: int, is_message: bool):
    """Westeros xaritasi hududlarini ko'rsatish"""
    text = (
        "🗺️ **WESTEROS XARITASI VA QAL'ALAR**\n\n"
        "Westerosdagi barcha strategik qal'alar va shahar-portlar.\n"
        "Qal'a haqida ma'lumot olish yoki unga yurish qilish uchun tanlang:"
    )
    if is_message:
        await target.message.reply_text(text, parse_mode="Markdown", reply_markup=territories_keyboard())
    else:
        await target.edit_message_text(text, parse_mode="Markdown", reply_markup=territories_keyboard())


async def view_territory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bitta hudud tafsilotlarini ko'rsatish"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    terr_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        terr = await crud.get_territory_by_id(session, terr_id)
        if not terr:
            await query.answer("Hudud topilmadi.", show_alert=True)
            return

        user = await crud.get_user_with_relations(session, user_id)
        is_own = user and user.house_id and user.house_id == terr.owner_house_id

        owner_name = f"{terr.owner_house.emoji} {terr.owner_house.name}" if terr.owner_house else "Egaliksiz (Qaroqchilar)"

        buttons = []
        if is_own:
            buttons.append([InlineKeyboardButton("🛡️ Sizning Xonadoningiz Qal'asi", callback_data="terr_own_info")])
        else:
            buttons.append([InlineKeyboardButton("⚔️ Ushbu Qal'aga Yurish Qilish", callback_data=f"march_prep:{terr.id}")])
        buttons.append([InlineKeyboardButton("🔙 Xaritaga Qaytish", callback_data="menu_map")])

        text = (
            f"🏰 **{terr.name.upper()} — {terr.castle_name}**\n\n"
            f"📍 Mintaqa: **{terr.region}**\n"
            f"👑 Hukmron Xonadon: **{escape_md(owner_name)}**\n"
            f"👥 Aholi: **{terr.population:,}**\n\n"
            f"💰 **SOATLIK DAROMAD:**\n"
            f"🪙 +{terr.gold_income} oltin | 🌾 +{terr.food_income} oziq-ovqat | ⛓️ +{terr.iron_income} temir\n\n"
            f"🛡️ **QAL'A MUDOFAASI:** {terr.defense} ball\n"
            f"⚔️ **GARNIZON KUCHLARI:**\n"
            f"• 🛡️ Piyoda: {terr.garrison_infantry:,}\n"
            f"• 🏹 Kamonchi: {terr.garrison_archers:,}\n"
            f"• 🐎 Otliq: {terr.garrison_cavalry:,}\n"
            f"• 🗡️ Nayzachi: {terr.garrison_spearmen:,}\n\n"
            f"Ushbu hududni egallash xonadoningizga doimiy daromad va shon-sharaf keltiradi!"
        )

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def terr_own_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'z xonadoni qal'asini bosganda tushuntirish"""
    query = update.callback_query
    await query.answer(
        "🛡️ Bu sizning o'z xonadoningiz qal'asi!\n\n"
        "O'z qal'angizga hujum qilib bo'lmaydi. Xaritadan boshqa dushman qal'alariga (masalan: Casterly Rock, Dreadfort, King's Landing va h.k.) yurish qilishingiz mumkin.",
        show_alert=True
    )


def register_map_handlers(app):
    app.add_handler(CommandHandler("map", map_command))
    app.add_handler(CommandHandler("territory", map_command))
    app.add_handler(CallbackQueryHandler(map_callback, pattern="^menu_map$"))
    app.add_handler(CallbackQueryHandler(view_territory_callback, pattern="^view_terr:"))
    app.add_handler(CallbackQueryHandler(terr_own_info_callback, pattern="^terr_own_info$"))
