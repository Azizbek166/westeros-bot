from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from database import AsyncSessionLocal, crud
from data.houses_data import HOUSES_DATA
from data.characters_data import HOUSE_CHARACTERS
from keyboards.menus import (
    main_menu_keyboard,
    regions_keyboard,
    houses_in_region_keyboard,
    back_to_main_keyboard,
    persistent_reply_keyboard,
)
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
            # Doimiy pastki menyu (emoji bar yonida)
            await update.message.reply_text(
                "⚔️ Westeros dunyosiga xush kelibsiz!",
                reply_markup=persistent_reply_keyboard()
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

    context.user_data.pop("awaiting_custom_name", None)
    region_name = query.data.split(":", 1)[1]
    context.user_data["selected_region"] = region_name

    async with AsyncSessionLocal() as session:
        member_counts = await crud.get_all_houses_member_counts(session)

    text = (
        f"📍 **{region_name}** mintaqasidagi xonadonlar:\n\n"
        f"Qaysi xonadonga xizmat qilishni xohlaysiz?\n"
        f"*(Har bir xonadonga ko'pi bilan 5 nafar lord qo'shila oladi)*"
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=houses_in_region_keyboard(region_name, member_counts=member_counts)
    )


async def house_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadon tanlanganda qahramon nomini yozishni so'rash"""
    query = update.callback_query
    await query.answer()

    house_code = query.data.split(":", 1)[1]
    context.user_data["selected_house"] = house_code
    house_info = HOUSES_DATA.get(house_code, {})
    house_id = house_info.get("id", 1)

    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        existing = await crud.get_user_by_telegram_id(session, user_id)
        if existing and existing.house_id:
            await query.edit_message_text("❌ Siz allaqachon xonadon tanlagansiz!", reply_markup=main_menu_keyboard(user_id))
            return

        member_count = await crud.get_house_members_count(session, house_id)

    if member_count >= 5:
        await query.answer("❌ Bu xonadon to'lgan (5/5)! Iltimos, boshqa bo'sh xonadonni tanlang.", show_alert=True)
        return

    context.user_data["awaiting_custom_name"] = True

    buttons = [
        [InlineKeyboardButton("🔙 Xonadonlarga Qaytish", callback_data=f"sel_reg:{house_info.get('region', 'The North')}")]
    ]

    text = (
        f"{house_info.get('emoji', '🏰')} **{house_info.get('name', 'Xonadon')}**\n\n"
        f"📜 {house_info.get('description', '')}\n\n"
        f"🔥 Maxsus Qo'shin: **{house_info.get('special_troop', '')}**\n"
        f"👥 Hozirgi a'zolar: **{member_count}/5**\n\n"
        f"✍️ **Qahramoningiz nomini yozing:**\n"
        f"O'zingiz uchun qahramon ismini chatga matn sifatida yuboring (masalan: *Aegon*, *Zafar*, *Shadowblade*).\n\n"
        f"⚠️ *Qoida: Nom 2-30 belgidan iborat bo'lishi va butun Westeros bo'ylab takrorlanmasligi shart!*"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def handle_custom_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi yangi qahramon nomini matn sifatida yuborganda tekshirish va ro'yxatdan o'tkazish"""
    if not context.user_data.get("awaiting_custom_name"):
        return

    if not update.effective_message or not update.effective_message.text:
        return

    raw_name = update.effective_message.text.strip()
    if raw_name.startswith("/"):
        return

    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name

    # Uzunlik tekshiruvi
    if len(raw_name) < 2 or len(raw_name) > 30:
        await update.effective_message.reply_text(
            "❌ Qahramon nomi 2 dan 30 tagacha belgidan iborat bo'lishi kerak. Iltimos, qaytadan yozing:"
        )
        return

    if any(c in raw_name for c in ["\n", "\r", "\t", "`"]):
        await update.effective_message.reply_text(
            "❌ Nomda nojo'ya belgilar mavjud. Iltimos, oddiy harflardan iborat nom kiriting:"
        )
        return

    house_code = context.user_data.get("selected_house", "stark")
    house_info = HOUSES_DATA.get(house_code, HOUSES_DATA["stark"])
    house_id = house_info.get("id", 1)

    async with AsyncSessionLocal() as session:
        existing = await crud.get_user_by_telegram_id(session, user_id)
        if existing and existing.house_id:
            context.user_data.pop("awaiting_custom_name", None)
            await update.effective_message.reply_text(
                "❌ Siz allaqachon xonadonga egasiz!",
                reply_markup=main_menu_keyboard(user_id)
            )
            return

        exclude_id = existing.id if existing else None
        if await crud.is_character_name_taken(session, raw_name, exclude_user_id=exclude_id):
            await update.effective_message.reply_text(
                f"❌ **{escape_md(raw_name)}** nomi allaqachon boshqa o'yinchi tomonidan olingan! Iltimos, boshqa nom tanlang:"
            )
            return

        current_members = await crud.get_house_members_count(session, house_id)
        if current_members >= 5:
            context.user_data.pop("awaiting_custom_name", None)
            await update.effective_message.reply_text(
                f"❌ Kechirasiz, **{house_info['name']}** xonadoni hozirgina to'ldi (5/5). Iltimos, boshqa xonadon tanlang.",
                reply_markup=regions_keyboard()
            )
            return

        try:
            if existing:
                user = await crud.join_house(
                    session=session,
                    user=existing,
                    house_id=house_id,
                    character_name=raw_name,
                    username=username,
                    full_name=full_name,
                )
            else:
                user = await crud.create_user(
                    session=session,
                    telegram_id=user_id,
                    username=username,
                    full_name=full_name,
                    house_id=house_id,
                    character_name=raw_name,
                )
        except ValueError as ve:
            await update.effective_message.reply_text(f"❌ {ve}")
            return

    context.user_data.pop("awaiting_custom_name", None)

    # Egaga bildirishnoma
    from core.notifier import notify_owner
    await notify_owner(
        context.application,
        f"🆕 *YANGI O'YINCHI RO'YXATDAN O'TDI!*\n\n"
        f"👤 Qahramon: *{escape_md(raw_name)}*\n"
        f"🆔 Telegram: `{user_id}` (@{username or 'yoq'})\n"
        f"🏰 Xonadon: *{house_info['emoji']} {house_info['name']}*\n"
        f"🎖️ Lavozim: *{user.rank.title()}*\n"
        f"👥 A'zolar soni: *{current_members + 1}/5*"
    )

    rank_titles = {
        "king": "👑 Qirol / Lord (Xonadon yetakchisi)",
        "commander": "⚔️ Qo'mondon (2-o'rin)",
        "knight": "🛡️ Ritsar (3-o'rin)",
        "captain": "🏹 Kapitan (4-o'rin)",
        "member": "🗡️ Xonadon Jangchisi (5-o'rin)",
    }
    user_rank_display = rank_titles.get(user.rank, user.rank.title())

    text = (
        f"🎉 **QASAMYOD QABUL QILINDI!**\n\n"
        f"👤 Siz endi **{house_info['emoji']} {house_info['name']}** xonadonida **{escape_md(raw_name)}** sifatida qasamyod qildingiz!\n"
        f"🎖️ Lavozimingiz: **{user_rank_display}**\n\n"
        f"💰 Boshlang'ich Resurslar:\n"
        f"🪙 Oltin: **{user.gold:,}** | 🌾 Oziq-ovqat: **{user.food:,}** | ⛓️ Temir: **{user.iron:,}**\n"
        f"🛡️ Armiya: **{user.army.infantry + user.army.archers + user.army.cavalry + user.army.spearmen}** askar\n"
        f"🔰 3 kunlik Tinchlik Qalqoni (Peace Shield) faollashtirildi.\n\n"
        f"Boshqaruv menyusidan foydalanishingiz mumkin:"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))
    try:
        await update.effective_message.reply_text(
            "⚔️ Buyruqlar paneli faollashtirildi.",
            reply_markup=persistent_reply_keyboard(),
        )
    except Exception:
        pass


async def hero_taken_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eski qahramon tugmasi bosilganda ogohlantirish"""
    query = update.callback_query
    await query.answer("❌ Iltimos, o'z qahramoningiz nomini chatga yozib yuboring.", show_alert=True)


async def hero_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Orqaga moslik uchun qoldirilgan qahramon tanlovi"""
    query = update.callback_query
    await query.answer("Iltimos, o'z qahramoningiz nomini chatga yozib yuboring.", show_alert=True)


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
        if query.message.photo:
            await query.message.delete()
            await query.message.chat.send_message(text, parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))
        else:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))


async def bottom_menu_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pastki doimiy menyu tugmalari bosilganda (🏠 Bosh Menyu, 🏰 Qalalarim)"""
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    user_id = update.effective_user.id

    if text == "🏠 Bosh Menyu":
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_with_relations(session, user_id)
            if not user:
                await update.message.reply_text("Iltimos, avval /start ni bosing.")
                return

            hero_name = user.characters[0].name if user.characters else "Lord"
            msg = (
                f"👑 **THE IRON THRONE — ASOSIY DASHBOARD**\n\n"
                f"👤 Hukmdor: **{escape_md(hero_name)}**\n"
                f"🏰 Xonadon: **{user.house.emoji} {user.house.name}**\n\n"
                f"🪙 Oltin: **{user.gold:,}** | 🌾 Oziq-ovqat: **{user.food:,}** | ⛓️ Temir: **{user.iron:,}**\n"
                f"🛡️ Armiya: **{(user.army.infantry + user.army.archers + user.army.cavalry + user.army.spearmen + user.army.special_troops):,}** askar\n\n"
                f"Kerakli bo'limni tanlang:"
            )
            await update.message.reply_text(
                msg,
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(user_id)
            )
    elif text == "🏰 Qalalarim":
        from handlers.map_handler import my_castles_command
        await my_castles_command(update, context)


def register_start_handlers(app):
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.Regex("^(🏠 Bosh Menyu|🏰 Qalalarim)$"), bottom_menu_text_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_name_input), group=2)
    app.add_handler(CallbackQueryHandler(region_selected_callback, pattern="^sel_reg:"))
    app.add_handler(CallbackQueryHandler(house_selected_callback, pattern="^sel_house:"))
    app.add_handler(CallbackQueryHandler(hero_selected_callback, pattern="^sel_hero:"))
    app.add_handler(CallbackQueryHandler(hero_taken_callback, pattern="^hero_taken$"))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^menu_main$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text("Mintaqangizni tanlang:", reply_markup=regions_keyboard()), pattern="^back_to_regions$"))

