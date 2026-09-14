from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud
from data.houses_data import HOUSES_DATA
from data.characters_data import HOUSE_CHARACTERS
from keyboards.menus import main_menu_keyboard, regions_keyboard, houses_in_region_keyboard, back_to_main_keyboard
from config import escape_md


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start buyrug'i"""
    user_id = update.effective_user.id
    full_name = update.effective_user.full_name

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)

        if user and user.house:
            h_emoji = user.house.emoji
            h_name = user.house.name
            hero_name = user.characters[0].name if user.characters else "Lord"

            text = (
                f"👑 **THE IRON THRONE — MMORPG**\n\n"
                f"Xush kelibsiz, **{escape_md(hero_name)}** ({escape_md(full_name)})!\n\n"
                f"🏰 Xonadon: **{h_emoji} {h_name}**\n"
                f"🎖️ Lavozim: **{user.rank.title()}** | Daraja: **{user.level}**\n\n"
                f"🪙 Oltin: **{user.gold:,}** | 🌾 Oziq-ovqat: **{user.food:,}** | ⛓️ Temir: **{user.iron:,}**\n"
                f"🛡️ Armiya: **{(user.army.infantry + user.army.archers + user.army.cavalry + user.army.spearmen + user.army.special_troops):,}** askar\n\n"
                f"Westerosda yangi kun boshlandi. Buyruqni tanlang:"
            )
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))
            return

    # Yangi o'yinchi uchun mintaqa tanlash
    text = (
        "👑 **THE IRON THRONE — WESTEROS MMORPG**\n\n"
        "Qirol Robert Baratheon vafot etdi! Temir Taxt bo'shab qoldi.\n"
        "Westerosda 50 ta xonadon taxt uchun jangga kirishmoqda.\n\n"
        "🛡️ Yangi o'yinchilarga **3 kunlik Tinchlik Qalqoni (Peace Shield)** beriladi.\n\n"
        "Boshlash uchun o'z mintaqangizni tanlang:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=regions_keyboard())


async def region_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mintaqa tanlanganda xonadonlar ro'yxatini chiqarish"""
    query = update.callback_query
    await query.answer()

    region_name = query.data.split(":", 1)[1]
    context.user_data["selected_region"] = region_name

    text = f"📍 **{region_name}** mintaqasidagi xonadonlar:\n\nQaysi xonadonga xizmat qilishni xohlaysiz?"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=houses_in_region_keyboard(region_name))


async def house_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadon tanlanganda personajlar ro'yxatini chiqarish"""
    query = update.callback_query
    await query.answer()

    house_code = query.data.split(":", 1)[1]
    context.user_data["selected_house"] = house_code
    house_info = HOUSES_DATA.get(house_code, {})
    house_id = house_info.get("id", 1)

    async with AsyncSessionLocal() as session:
        taken_heroes = await crud.get_taken_character_names(session, house_id)

    characters = HOUSE_CHARACTERS.get(house_code, ["Xonadon Yetakchisi"])

    buttons = []
    all_taken = True
    for hero in characters:
        if hero in taken_heroes:
            buttons.append([InlineKeyboardButton(f"❌ {hero} (Band)", callback_data="hero_taken")])
        else:
            all_taken = False
            buttons.append([InlineKeyboardButton(f"👤 {hero}", callback_data=f"sel_hero:{hero}")])

    if all_taken:
        buttons.append([InlineKeyboardButton(f"🛡️ {house_info.get('name', 'Xonadon')} Ritsari", callback_data=f"sel_hero:{house_info.get('name', 'Xonadon')} Ritsari")])

    buttons.append([InlineKeyboardButton("🔙 Xonadonlarga Qaytish", callback_data=f"sel_reg:{house_info.get('region', 'The North')}")])

    text = (
        f"{house_info.get('emoji', '🏰')} **{house_info.get('name', 'Xonadon')}**\n\n"
        f"📜 {house_info.get('description', '')}\n\n"
        f"🔥 Maxsus Qo'shin: **{house_info.get('special_troop', '')}**\n\n"
        f"O'z qahramoningizni tanlang (band bo'lmaganini):"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def hero_taken_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Band qilingan qahramon bosilganda ogohlantirish"""
    query = update.callback_query
    await query.answer("❌ Bu afsonaviy qahramon allaqachon boshqa o'yinchi tomonidan tanlangan! Bo'sh turgan personajni tanlang.", show_alert=True)


async def hero_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qahramon tanlanganda ro'yxatdan o'tishni yakunlash"""
    query = update.callback_query
    await query.answer()

    hero_name = query.data.split(":", 1)[1]
    house_code = context.user_data.get("selected_house", "stark")
    house_info = HOUSES_DATA.get(house_code, HOUSES_DATA["stark"])
    house_id = house_info.get("id", 1)

    user_id = query.from_user.id
    username = query.from_user.username
    full_name = query.from_user.full_name

    async with AsyncSessionLocal() as session:
        # Tekshiramiz: agar avval ro'yxatdan o'tgan bo'lsa
        existing = await crud.get_user_by_telegram_id(session, user_id)
        if existing:
            await query.edit_message_text("❌ Siz allaqachon xonadon tanlagansiz!", reply_markup=main_menu_keyboard(user_id))
            return

        # Tekshiramiz: bu personaj shu orada boshqa birov tomonidan band qilinmadimi?
        taken = await crud.get_taken_character_names(session, house_id)
        if hero_name in taken:
            await query.answer("❌ Kechirasiz! Bu qahramon hozirgina boshqa lord tomonidan tanlandi. Iltimos, boshqasini tanlang.", show_alert=True)
            return

        user = await crud.create_user(
            session=session,
            telegram_id=user_id,
            username=username,
            full_name=full_name,
            house_id=house_info["id"],
            character_name=hero_name,
        )

    text = (
        f"🎉 **QASAMYOD QABUL QILINDI!**\n\n"
        f"👤 Siz endi **{house_info['emoji']} {house_info['name']}** xonadonida **{hero_name}** sifatida qasamyod qildingiz!\n\n"
        f"💰 Boshlang'ich Resurslar:\n"
        f"🪙 Oltin: **{user.gold:,}** | 🌾 Oziq-ovqat: **{user.food:,}** | ⛓️ Temir: **{user.iron:,}**\n"
        f"🛡️ Armiya: **{user.army.infantry + user.army.archers + user.army.cavalry + user.army.spearmen}** askar\n"
        f"🔰 3 kunlik Tinchlik Qalqoni (Peace Shield) faollashtirildi.\n\n"
        f"Boshqaruv menyusidan foydalanishingiz mumkin:"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asosiy menyuga qaytish"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            await query.edit_message_text("Iltimos, avval /start ni bosing.")
            return

        hero_name = user.characters[0].name if user.characters else "Lord"
        text = (
            f"👑 **THE IRON THRONE — ASOSIY DASHBOARD**\n\n"
            f"👤 Hukmdor: **{escape_md(hero_name)}**\n"
            f"🏰 Xonadon: **{user.house.emoji} {user.house.name}**\n\n"
            f"🪙 Oltin: **{user.gold:,}** | 🌾 Oziq-ovqat: **{user.food:,}** | ⛓️ Temir: **{user.iron:,}**\n"
            f"🛡️ Armiya: **{(user.army.infantry + user.army.archers + user.army.cavalry + user.army.spearmen + user.army.special_troops):,}** askar\n\n"
            f"Kerakli bo'limni tanlang:"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))


def register_start_handlers(app):
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(region_selected_callback, pattern="^sel_reg:"))
    app.add_handler(CallbackQueryHandler(house_selected_callback, pattern="^sel_house:"))
    app.add_handler(CallbackQueryHandler(hero_selected_callback, pattern="^sel_hero:"))
    app.add_handler(CallbackQueryHandler(hero_taken_callback, pattern="^hero_taken$"))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^menu_main$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text("Mintaqangizni tanlang:", reply_markup=regions_keyboard()), pattern="^back_to_regions$"))
