from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from database import AsyncSessionLocal, crud, models
from sqlalchemy import select
from data.houses_data import HOUSES_DATA
from data.characters_data import HOUSE_CHARACTERS
from keyboards.menus import (
    main_menu_keyboard,
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

        # Agar yangi o'yinchiga xonadon allaqachon random tushgan bo'lsa, o'shani saqlab qolamiz (faqat 1 marta)
        saved_house_code = context.user_data.get("selected_house")
        if saved_house_code and saved_house_code in HOUSES_DATA:
            house_code = saved_house_code
            house_info = HOUSES_DATA[house_code]
            house_id = house_info.get("id", 1)
        else:
            # Yangi o'yinchi uchun bot avtomatik random xonadon tanlaydi (faqat 1 marta!)
            assigned_house = await crud.get_random_available_house(session)
            if not assigned_house:
                house_code = "stark"
                house_info = HOUSES_DATA.get("stark", {})
                house_id = 1
            else:
                house_code = assigned_house.code
                house_id = assigned_house.id
                house_info = HOUSES_DATA.get(house_code) or {
                    "id": assigned_house.id,
                    "name": assigned_house.name,
                    "emoji": assigned_house.emoji,
                    "region": assigned_house.region,
                    "description": assigned_house.description,
                    "special_troop": assigned_house.special_troop_name,
                }
            context.user_data["selected_house"] = house_code

        member_count = await crud.get_house_members_count(session, house_id)

    context.user_data["awaiting_custom_name"] = True

    text = (
        "👑 *THE IRON THRONE — WESTEROS MMORPG*\n\n"
        "Qirol Robert Baratheon vafot etdi! Temir Taxt bo'shab qoldi.\n"
        "Westerosda 50 ta xonadon taxt uchun jangga kirishmoqda.\n\n"
        "🎲 *Taqdir sizni quyidagi xonadon safiga yo'lladi (Faqat 1 marta):*\n\n"
        f"{house_info.get('emoji', '🏰')} *{house_info.get('name', 'Xonadon')}*\n"
        f"📍 Mintaqa: *{house_info.get('region', 'Westeros')}*\n"
        f"📜 {house_info.get('description', '')}\n"
        f"🔥 Maxsus Qo'shin: *{house_info.get('special_troop', '')}*\n"
        f"👥 Hozirgi a'zolar: *{member_count}/5*\n\n"
        "🛡️ Yangi o'yinchilarga *3 kunlik Tinchlik Qalqoni (Peace Shield)* beriladi.\n\n"
        "✍️ *Qahramoningiz nomini yozing:*\n"
        "O'zingiz uchun qahramon ismini chatga matn sifatida yuboring (masalan: *Aegon*, *Zafar*, *Shadowblade*).\n\n"
        "⚠️ _Qoida: Nom 2-30 belgidan iborat bo'lishi va butun Westeros bo'ylab takrorlanmasligi shart!_"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def random_house_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tasodifiy xonadon faqat 1 marta beriladi"""
    query = update.callback_query
    await query.answer("❌ Xonadon faqat 1 marta tasodifiy belgilanadi va uni o'zgartirib bo'lmaydi!", show_alert=True)


async def region_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mintaqa tanlash taqiqlangan"""
    query = update.callback_query
    await query.answer("❌ Xonadon faqat 1 marta tasodifiy belgilanadi va uni o'zgartirib bo'lmaydi!", show_alert=True)


async def house_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadon tanlash taqiqlangan"""
    query = update.callback_query
    await query.answer("❌ Xonadon faqat 1 marta tasodifiy belgilanadi va uni o'zgartirib bo'lmaydi!", show_alert=True)



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

    house_code = context.user_data.get("selected_house")

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

        # Bo'sh va to'lmagan xonadonni aniqlash
        house_obj = None
        if house_code:
            h_res = await session.execute(
                select(models.House).where(models.House.code == house_code)
            )
            found_h = h_res.scalar_one_or_none()
            if found_h:
                cnt = await crud.get_house_members_count(session, found_h.id)
                if cnt < 5:
                    house_obj = found_h

        reassigned_notice = ""
        if not house_obj:
            house_obj = await crud.get_random_available_house(session)
            if not house_obj:
                await update.effective_message.reply_text(
                    "❌ Hozirda bo'sh xonadonlar mavjud emas. Iltimos, keyinroq qayta urinib ko'ring."
                )
                return
            if house_code and house_code != house_obj.code:
                reassigned_notice = f"\n\n*(Eslatma: Avvalgi xonadon to'lgani sababli, bot sizni tasodifiy **{house_obj.emoji} {house_obj.name}** safiga qabul qildi)*"
            house_code = house_obj.code
            context.user_data["selected_house"] = house_code

        house_id = house_obj.id
        current_members = await crud.get_house_members_count(session, house_id)
        house_info = HOUSES_DATA.get(house_code) or {
            "id": house_id,
            "name": house_obj.name,
            "emoji": house_obj.emoji,
            "region": house_obj.region,
            "description": house_obj.description,
            "special_troop": house_obj.special_troop_name,
        }

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

            # Oldingi mavsum TOP-3 g'olibi bo'lsa, bonusni avtomatik biriktirish
            pending_bonus = await crud.get_pending_season_bonus(session, user_id)
            season_bonus_msg = ""
            if pending_bonus:
                _, season_bonus_msg = await crud.apply_season_top_bonus(session, user, pending_bonus)
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
        f"👤 Siz endi **{house_info['emoji']} {house_info['name']}** xonadonida **{escape_md(raw_name)}** sifatida qasamyod qildingiz!{reassigned_notice}{season_bonus_msg}\n\n"
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
    app.add_handler(CallbackQueryHandler(random_house_pick_callback, pattern="^random_house_pick$"))
    app.add_handler(CallbackQueryHandler(region_selected_callback, pattern="^sel_reg:"))
    app.add_handler(CallbackQueryHandler(house_selected_callback, pattern="^sel_house:"))
    app.add_handler(CallbackQueryHandler(hero_selected_callback, pattern="^sel_hero:"))
    app.add_handler(CallbackQueryHandler(hero_taken_callback, pattern="^hero_taken$"))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^menu_main$"))
    app.add_handler(CallbackQueryHandler(random_house_pick_callback, pattern="^back_to_regions$"))

