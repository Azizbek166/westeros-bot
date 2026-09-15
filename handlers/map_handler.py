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

        dragon_info_str = "Mavjud emas"
        st_dragon = crud.get_stationed_dragon_info(terr)
        if st_dragon:
            dragon_info_str = f"🔥 **{st_dragon.get('dragon_name')}** (Kuch: {st_dragon.get('power')}, Egasi: {st_dragon.get('user_name')})"

        buttons = []
        if is_own:
            buttons.append([InlineKeyboardButton("🛡️ Askar Joylashtirish (Garnizon)", callback_data=f"def_rf_menu:{terr.id}")])
            if st_dragon:
                if st_dragon.get("user_id") == user.id or (user.house and user.house.lord_user_id == user.telegram_id):
                    buttons.append([InlineKeyboardButton("🚫 Ajdarni Qal'adan Qaytarish", callback_data=f"def_recall_dragon:{terr.id}")])
                else:
                    buttons.append([InlineKeyboardButton("🐉 Ajdar Qo'riqlamoqda", callback_data="terr_dragon_info")])
            else:
                buttons.append([InlineKeyboardButton("🐉 Ajdarni Qal'aga Joylashtirish", callback_data=f"def_station_dragon:{terr.id}")])
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
            f"🐉 **MUDOFAADAGI AJDAR:** {dragon_info_str}\n\n"
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
        "O'z qal'angizga hujum qilib bo'lmaydi. Ushbu qal'aga askar yoki ajdaringizni mudofaaga joylashtirishingiz mumkin.",
        show_alert=True
    )


async def def_station_dragon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarni qal'aga mudofaa uchun joylashtirish"""
    query = update.callback_query
    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        ok, msg = await crud.station_dragon_in_castle(session, user_id, terr_id)

    await query.answer(msg, show_alert=True)
    await view_territory_callback(update, context)


async def def_recall_dragon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarni qal'a mudofaasidan qaytarib olish"""
    query = update.callback_query
    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        ok, msg = await crud.recall_dragon_from_castle(session, user_id, terr_id)

    await query.answer(msg, show_alert=True)
    await view_territory_callback(update, context)


async def terr_dragon_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🐉 Qal'a osmonida ittifoqchi ajdar parvoz qilib, qal'ani dushman zarbalaridan himoya qilmoqda.", show_alert=True)


def register_map_handlers(app):
    app.add_handler(CommandHandler("map", map_command))
    app.add_handler(CommandHandler("territory", map_command))
    app.add_handler(CallbackQueryHandler(map_callback, pattern="^menu_map$"))
    app.add_handler(CallbackQueryHandler(view_territory_callback, pattern="^view_terr:"))
    app.add_handler(CallbackQueryHandler(terr_own_info_callback, pattern="^terr_own_info$"))
    app.add_handler(CallbackQueryHandler(def_station_dragon_callback, pattern="^def_station_dragon:"))
    app.add_handler(CallbackQueryHandler(def_recall_dragon_callback, pattern="^def_recall_dragon:"))
    app.add_handler(CallbackQueryHandler(terr_dragon_info_callback, pattern="^terr_dragon_info$"))
