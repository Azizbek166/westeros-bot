from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from database import AsyncSessionLocal, crud, models
from sqlalchemy import select, func
from data.houses_data import HOUSES_DATA
from data.map_data import REGIONS_DATA
from data.characters_data import HOUSE_CHARACTERS
from keyboards.menus import (
    main_menu_keyboard,
    back_to_main_keyboard,
    persistent_reply_keyboard,
    custom_house_regions_keyboard,
    custom_house_emojis_keyboard,
)
from config import escape_md


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start buyrug'i"""
    chat = update.effective_chat
    if chat and chat.type in ["group", "supergroup"]:
        bot_username = context.bot.username or "ironthrone_rpgbot"
        await update.effective_message.reply_text(
            "⚔️ **THE IRON THRONE MMORPG**\n\n"
            "O'yin panellari va boshqaruv faqat botning o'zida (shaxsiy chatda) ishlaydi.\n"
            "Guruhda faqat **/profile** (yoki xabarga reply qilib **/profile**) orqali lordlar profilini ko'rishingiz mumkin!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎮 O'yinni Botda O'ynash", url=f"https://t.me/{bot_username}?start=group")]
            ])
        )
        return

    user_id = update.effective_user.id
    full_name = update.effective_user.full_name
    username = update.effective_user.username

    # 1. Telegram username majburiyligi
    if not username:
        await update.message.reply_text(
            "❌ **KECHIRASIZ, O'YINDA QATNASHISH UCHUN TELEGRAM USERNAME BO'LISHI SHART!**\n\n"
            "Vesteros olamida har bir lordning o'z noyob nomi va `@username` nishoni bo'lishi talab etiladi.\n\n"
            "📌 **Nima qilish kerak?**\n"
            "1. Telegram sozlamalariga kiring (`Settings` -> `Edit Profile`).\n"
            "2. O'zingizga foydalanuvchi nomi (`Username`, masalan: `@lord_westeros`) o'rnating.\n"
            "3. Shundan so'ng botga qaytib **/start** buyrug'ini bosing!",
            parse_mode="Markdown",
        )
        return

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)

        # 2. Bloklangan o'yinchi tekshiruvi
        if user and getattr(user, "is_banned", False):
            await update.message.reply_text(
                "🚫 **SIZNING HISOBINGIZ BLOKLANGAN!**\n\n"
                "Qoidabuzarlik sababli bot ma'muriyati tomonidan hisobingiz muzlatilgan.\n"
                "Agar bu xatolik deb hisoblasangiz, bosh administratorga murojaat qiling.",
                parse_mode="Markdown",
            )
            return

        if user and user.house:
            h_emoji = user.house.emoji
            h_name = user.house.name
            hero_name = user.characters[0].name if (getattr(user, "characters", None) and len(user.characters) > 0) else "Lord"

            army = getattr(user, "army", None)
            total_troops = 0
            if army:
                total_troops = (
                    (army.infantry or 0) +
                    (army.archers or 0) +
                    (army.cavalry or 0) +
                    (army.spearmen or 0) +
                    (army.special_troops or 0)
                )

            text = (
                f"👑 **THE IRON THRONE — MMORPG**\n\n"
                f"Xush kelibsiz, **{escape_md(hero_name)}** ({escape_md(full_name)})!\n\n"
                f"🏰 Xonadon: **{h_emoji} {h_name}**\n"
                f"🎖️ Lavozim: **{user.rank.title()}** | Daraja: **{user.level}**\n\n"
                f"🪙 Oltin: **{user.gold:,}** | 🌾 Oziq-ovqat: **{user.food:,}** | ⛓️ Temir: **{user.iron:,}**\n"
                f"🛡️ Armiya: **{total_troops:,}** askar\n\n"
                f"Westerosda yangi kun boshlandi. Buyruqni tanlang:"
            )
            # Doimiy pastki menyu (emoji bar yonida)
            try:
                await update.message.reply_text(
                    "⚔️ Westeros dunyosiga xush kelibsiz!",
                    reply_markup=persistent_reply_keyboard()
                )
            except Exception:
                pass

            try:
                await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))
            except Exception:
                await update.message.reply_text(text, parse_mode=None, reply_markup=main_menu_keyboard(user_id))
            return

        # Agar yangi o'yinchiga xonadon allaqachon random tushgan bo'lsa, bo'shligini tekshiramiz
        saved_house_code = context.user_data.get("selected_house")
        assigned_house = None
        if saved_house_code and saved_house_code in HOUSES_DATA:
            h_res = await session.execute(select(models.House).where(models.House.code == saved_house_code))
            h_candidate = h_res.scalar_one_or_none()
            if h_candidate and await crud.get_house_members_count(session, h_candidate.id) < 1:
                assigned_house = h_candidate

        if not assigned_house:
            # Yangi o'yinchi uchun bot avtomatik bo'sh xonadon tanlaydi (har bir xonadonga faqat 1 kishi!)
            assigned_house = await crud.get_random_available_house(session)
            if not assigned_house:
                # Barcha 50 ta tarixiy xonadon band bo'lsa, o'yinchi o'zining yangi xonadonini yaratadi!
                context.user_data.pop("selected_house", None)
                context.user_data.pop("awaiting_custom_name", None)
                context.user_data.pop("new_house_name", None)
                context.user_data.pop("new_house_region", None)
                context.user_data.pop("new_house_emoji", None)
                context.user_data.pop("new_castle_name", None)
                context.user_data.pop("awaiting_custom_castle_name", None)
                context.user_data.pop("awaiting_custom_hero_name", None)
                context.user_data.pop("awaiting_custom_emoji_input", None)
                context.user_data["awaiting_custom_house_name"] = True

                custom_intro = (
                    "👑 **THE IRON THRONE — WESTEROS MMORPG**\n\n"
                    "⚔️ **WESTEROSDA BARCHA 50 TA ASOSIY XONADONLAR BAND!**\n\n"
                    "Westerosning barcha 50 ta tarixiy sulolasi o'z Lordlariga ega bo'ldi.\n"
                    "Lekin sizning afsonangiz endi boshlanadi! Siz Westerosda o'z shaxsiy sulolangizga asos solishingiz va yangi Qal'a barpo etishingiz mumkin!\n\n"
                    "🏛️ **Sizning imkoniyatlaringiz boshqa lordlar bilan mutlaqo teng:**\n"
                    "• O'z sulolangizga nom va ramz (gerb) berasiz\n"
                    "• Mintaqangizni tanlab, 1 ta strategik Qal'angizni qurasiz\n"
                    "• Qal'angizni kuchaytirasiz (Tier 1-5, devorlar, o'lpon yig'ish)\n"
                    "• Armiya yollaysiz, ajdaho o'stirasiz va Temir Taxt uchun jangga kirasiz!\n\n"
                    "✍️ **1-QADAM: Yangi Xonadoningiz nomini yozing:**\n"
                    "Chatga yangi sulolangiz nomini matn sifatida yuboring *(masalan: `Qora Burgutlar`, `House Shadow`, `Muz Qoplonlari`)*:"
                )
                try:
                    await update.message.reply_text(custom_intro, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(custom_intro, parse_mode=None)
                return

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

    context.user_data["awaiting_custom_name"] = True

    text = (
        "👑 *THE IRON THRONE — WESTEROS MMORPG*\n\n"
        "Qirol Robert Baratheon vafot etdi! Temir Taxt bo'shab qoldi.\n"
        "Westerosda 50 ta xonadon taxt uchun jangga kirishmoqda.\n\n"
        "🎲 *Taqdir sizni quyidagi xonadonning YAGONA LORDI qilib tanladi:*\n\n"
        f"{house_info.get('emoji', '🏰')} *{house_info.get('name', 'Xonadon')}*\n"
        f"📍 Mintaqa: *{house_info.get('region', 'Westeros')}*\n"
        f"📜 {house_info.get('description', '')}\n"
        f"🔥 Maxsus Qo'shin: *{house_info.get('special_troop', '')}*\n"
        f"👑 Xonadon Maqomi: *Yagona Hukmdor (1/1)*\n\n"
        "🛡️ Yangi o'yinchilarga *3 kunlik Tinchlik Qalqoni (Peace Shield)* beriladi.\n\n"
        "✍️ *Qahramoningiz nomini yozing:*\n"
        "O'zingiz uchun qahramon ismini chatga matn sifatida yuboring (masalan: *Aegon*, *Zafar*, *Shadowblade*).\n\n"
        "⚠️ _Qoida: Nom 2-30 belgidan iborat bo'lishi va butun Westeros bo'ylab takrorlanmasligi shart!_"
    )
    try:
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(text, parse_mode=None)


async def random_house_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tasodifiy xonadon faqat 1 marta beriladi"""
    query = update.callback_query
    await query.answer("❌ Xonadon faqat 1 marta tasodifiy belgilanadi va uni o'zgartirib bo'lmaydi!", show_alert=True)


async def region_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mintaqa tanlash taqiqlangan"""
    query = update.callback_query
    await query.answer("❌ Xonadon faqat 1 marta tasodifiy belgilanadi va uni o'zgartirib bo'lmaydi!", show_alert=True)


async def custom_house_region_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mintaqa tanlanganda gerb (ramz) tanlash klaviaturasini chiqarish"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 1)
    if len(parts) < 2:
        return
    region_name = parts[1]
    if region_name not in REGIONS_DATA:
        return

    context.user_data["new_house_region"] = region_name
    context.user_data["awaiting_custom_emoji_input"] = True

    h_name = context.user_data.get("new_house_name", "Yangi Xonadon")
    reg_info = REGIONS_DATA.get(region_name, {})
    reg_emoji = reg_info.get("emoji", "📍")

    text = (
        f"🏰 **Xonadon:** *{escape_md(h_name)}*\n"
        f"📍 **Mintaqa:** {reg_emoji} *{region_name}*\n\n"
        f"🛡️ **3-QADAM: Xonadoningiz gerbini (ramzini) tanlang:**\n"
        f"Bayroqlaringizda qaysi afsonaviy ramz aks etishini xohlaysiz? Quyidagi paneldan tanlang yoki o'zingiz istagan bitta emojini chatga yuboring:"
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=custom_house_emojis_keyboard(page=1)
    )


async def custom_house_emoji_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerblar sahifasini almashtirish (1, 2, 3-sahifalar)"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 1)
    if len(parts) < 2:
        return
    try:
        page = int(parts[1])
    except Exception:
        page = 1

    h_name = context.user_data.get("new_house_name", "Yangi Xonadon")
    region_name = context.user_data.get("new_house_region", "Westeros")
    reg_info = REGIONS_DATA.get(region_name, {})
    reg_emoji = reg_info.get("emoji", "📍")

    text = (
        f"🏰 **Xonadon:** *{escape_md(h_name)}*\n"
        f"📍 **Mintaqa:** {reg_emoji} *{region_name}*\n\n"
        f"🛡️ **3-QADAM: Xonadoningiz gerbini (ramzini) tanlang:**\n"
        f"Bayroqlaringizda qaysi afsonaviy ramz aks etishini xohlaysiz? Quyidagi paneldan tanlang yoki o'zingiz istagan bitta emojini chatga yuboring:"
    )
    try:
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=custom_house_emojis_keyboard(page=page)
        )
    except Exception:
        pass


async def custom_house_emoji_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerb tanlanganda Qal'a nomini so'rashga o'tish"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 1)
    if len(parts) < 2:
        return
    emoji = parts[1]

    context.user_data["new_house_emoji"] = emoji
    context.user_data.pop("awaiting_custom_emoji_input", None)
    context.user_data["awaiting_custom_castle_name"] = True

    h_name = context.user_data.get("new_house_name", "Yangi Xonadon")
    region_name = context.user_data.get("new_house_region", "Westeros")

    text = (
        f"🏰 **Xonadon:** {emoji} *{escape_md(h_name)}*\n"
        f"📍 **Mintaqa:** *{region_name}*\n\n"
        f"🏯 **4-QADAM: Shaxsiy Qal'angiz nomini kiriting:**\n"
        f"Har bir yangi sulolaga uning poytaxti — **faqat 1 ta shaxsiy strategik qal'a** qurish beriladi!\n\n"
        f"*(Uni keyinchalik Tier 1-5 gacha kengaytirish, devorlarini mustahkamlash, yovvoyi olov o'rnatish va daromadlarini oshirish mumkin)*\n\n"
        f"✍️ Qal'angiz nomini chatga yozing *(masalan: `Muz Qasri`, `Oq Qo'rg'on`, `Shadowkeep`)*:"
    )
    await query.edit_message_text(text, parse_mode="Markdown")


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nofaol separator / sahifa raqami tugmalari uchun"""
    query = update.callback_query
    await query.answer()


async def handle_custom_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi matn yuborganda ro'yxatdan o'tish bosqichlarini boshqarish"""
    is_custom_reg = any([
        context.user_data.get("awaiting_custom_house_name"),
        context.user_data.get("awaiting_custom_emoji_input"),
        context.user_data.get("awaiting_custom_castle_name"),
        context.user_data.get("awaiting_custom_hero_name"),
    ])
    if not is_custom_reg and not context.user_data.get("awaiting_custom_name"):
        return

    if not update.effective_message or not update.effective_message.text:
        return

    raw_name = update.effective_message.text.strip()
    if raw_name.startswith("/"):
        return

    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name

    # 1-QADAM: Yangi Xonadon Nomi (Custom House Name)
    if context.user_data.get("awaiting_custom_house_name"):
        if not username:
            await update.effective_message.reply_text(
                "❌ **O'YINDA QATNASHISH UCHUN TELEGRAM USERNAME BO'LISHI SHART!**\n\n"
                "Iltimos, Telegram sozlamalaridan o'zingizga `@username` o'rnating va qaytadan nom yozing!",
                parse_mode="Markdown"
            )
            return

        if len(raw_name) < 2 or len(raw_name) > 35:
            await update.effective_message.reply_text(
                "❌ Xonadon nomi 2 dan 35 tagacha belgidan iborat bo'lishi kerak. Iltimos, qaytadan yozing:"
            )
            return

        if any(c in raw_name for c in ["\n", "\r", "\t", "`", "/", "\\"]):
            await update.effective_message.reply_text(
                "❌ Nomda nojo'ya belgilar mavjud. Iltimos, oddiy harflardan iborat nom kiriting:"
            )
            return

        async with AsyncSessionLocal() as session:
            existing_h = await session.execute(
                select(models.House).where(func.lower(models.House.name) == raw_name.lower())
            )
            if existing_h.scalar_one_or_none():
                await update.effective_message.reply_text(
                    f"❌ **{escape_md(raw_name)}** nomli xonadon allaqachon mavjud! Iltimos, boshqa nom kiriting:"
                )
                return

        context.user_data["new_house_name"] = raw_name
        context.user_data.pop("awaiting_custom_house_name", None)

        text = (
            f"🏰 **Xonadon nomi:** *{escape_md(raw_name)}*\n\n"
            f"📍 **2-QADAM: Mintaqangizni tanlang:**\n"
            f"Sulolangiz Westerosning qaysi buyuk o'lkasida joylashishini xohlaysiz? Quyidagi mintaqalardan birini tanlang:"
        )
        await update.effective_message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=custom_house_regions_keyboard()
        )
        return

    # 2/3-QADAM (Chat orqali ixtiyoriy emoji yuborish)
    if context.user_data.get("awaiting_custom_emoji_input"):
        emoji = raw_name[:4].strip()
        context.user_data["new_house_emoji"] = emoji
        context.user_data.pop("awaiting_custom_emoji_input", None)
        context.user_data["awaiting_custom_castle_name"] = True

        h_name = context.user_data.get("new_house_name", "Yangi Xonadon")
        region_name = context.user_data.get("new_house_region", "Westeros")

        text = (
            f"🏰 **Xonadon:** {emoji} *{escape_md(h_name)}*\n"
            f"📍 **Mintaqa:** *{region_name}*\n\n"
            f"🏯 **4-QADAM: Shaxsiy Qal'angiz nomini kiriting:**\n"
            f"Har bir yangi sulolaga uning poytaxti — **faqat 1 ta shaxsiy strategik qal'a** qurish beriladi!\n\n"
            f"*(Uni keyinchalik Tier 1-5 gacha kengaytirish, devorlarini mustahkamlash, yovvoyi olov o'rnatish va daromadlarini oshirish mumkin)*\n\n"
            f"✍️ Qal'angiz nomini chatga yozing *(masalan: `Muz Qasri`, `Oq Qo'rg'on`, `Shadowkeep`)*:"
        )
        await update.effective_message.reply_text(text, parse_mode="Markdown")
        return

    # 4-QADAM: Shaxsiy Qal'a Nomi (Custom Castle Name)
    if context.user_data.get("awaiting_custom_castle_name"):
        if len(raw_name) < 2 or len(raw_name) > 35:
            await update.effective_message.reply_text(
                "❌ Qal'a nomi 2 dan 35 tagacha belgidan iborat bo'lishi kerak. Iltimos, qaytadan yozing:"
            )
            return

        if any(c in raw_name for c in ["\n", "\r", "\t", "`", "/", "\\"]):
            await update.effective_message.reply_text(
                "❌ Nomda nojo'ya belgilar mavjud. Iltimos, oddiy harflardan iborat nom kiriting:"
            )
            return

        context.user_data["new_castle_name"] = raw_name
        context.user_data.pop("awaiting_custom_castle_name", None)
        context.user_data["awaiting_custom_hero_name"] = True

        h_name = context.user_data.get("new_house_name", "Yangi Xonadon")
        h_emoji = context.user_data.get("new_house_emoji", "🏰")
        h_reg = context.user_data.get("new_house_region", "Westeros")

        text = (
            f"🏰 **Xonadon:** {h_emoji} *{escape_md(h_name)}*\n"
            f"📍 **Mintaqa:** *{h_reg}*\n"
            f"🏯 **Qal'a:** *{escape_md(raw_name)}*\n\n"
            f"👤 **5-QADAM: Lord / Qahramoningiz ismini kiriting:**\n"
            f"Siz ushbu yangi sulolaning asoschisi va Oliy Hukmdori (Qiroli) bo'lasiz!\n\n"
            f"✍️ O'zingiz (Qahramoningiz) uchun ism yozing *(masalan: `Aegon`, `Zafarbek`, `Shadowblade`)*:\n\n"
            f"⚠️ _Nom 2-30 belgidan iborat bo'lishi va Westeros bo'yicha yagona bo'lishi shart!_"
        )
        await update.effective_message.reply_text(text, parse_mode="Markdown")
        return

    # 5-QADAM: Yangi Sulola Lordi Ismi & Yakuniy Yaratish
    if context.user_data.get("awaiting_custom_hero_name"):
        if not username:
            await update.effective_message.reply_text(
                "❌ **O'YINDA QATNASHISH UCHUN TELEGRAM USERNAME BO'LISHI SHART!**\n\n"
                "Iltimos, Telegram sozlamalaridan o'zingizga `@username` o'rnating va qaytadan yozing!",
                parse_mode="Markdown"
            )
            return

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

        h_name = context.user_data.get("new_house_name")
        h_reg = context.user_data.get("new_house_region")
        h_emoji = context.user_data.get("new_house_emoji", "🏰")
        c_name = context.user_data.get("new_castle_name")

        if not h_name or not h_reg or not c_name:
            context.user_data.clear()
            await update.effective_message.reply_text(
                "⚠️ Ma'lumotlar to'liq emas. Iltimos, qaytadan /start ni bosing."
            )
            return

        async with AsyncSessionLocal() as session:
            existing = await crud.get_user_by_telegram_id(session, user_id)
            if existing and getattr(existing, "is_banned", False):
                await update.effective_message.reply_text("🚫 **SIZNING HISOBINGIZ BLOKLANGAN!**", parse_mode="Markdown")
                return

            if existing and existing.house_id:
                context.user_data.clear()
                await update.effective_message.reply_text("❌ Siz allaqachon xonadonga egasiz!", reply_markup=main_menu_keyboard(user_id))
                return

            exclude_id = existing.id if existing else None
            if await crud.is_character_name_taken(session, raw_name, exclude_user_id=exclude_id):
                await update.effective_message.reply_text(
                    f"❌ **{escape_md(raw_name)}** nomi allaqachon band qilingan! Iltimos, boshqa nom tanlang:"
                )
                return

            try:
                user, new_house, new_territory = await crud.create_custom_house_user_and_territory(
                    session=session,
                    telegram_id=user_id,
                    username=username,
                    full_name=full_name,
                    house_name=h_name,
                    region=h_reg,
                    emoji=h_emoji,
                    castle_name=c_name,
                    hero_name=raw_name,
                )

                pending_bonus = await crud.get_pending_season_bonus(session, user_id)
                if pending_bonus:
                    await crud.apply_season_top_bonus(session, user, pending_bonus)
            except ValueError as ve:
                await update.effective_message.reply_text(f"❌ {ve}")
                return

        context.user_data.clear()

        # Notifiy owner
        from core.notifier import notify_owner
        await notify_owner(
            context.application,
            f"👑 *YANGI SULOLA VA QAL'A BARPO ETILDI!*\n\n"
            f"👤 Lord: *{escape_md(raw_name)}*\n"
            f"🆔 Telegram: `{user_id}` (@{username or 'yoq'})\n"
            f"🏰 Xonadon: *{h_emoji} {escape_md(h_name)}*\n"
            f"📍 Mintaqa: *{h_reg}*\n"
            f"🏯 Ilk Qal'a: *{escape_md(c_name)}*\n"
            f"👑 Maqom: *Asoschi & Yagona Lord*"
        )

        welcome_text = (
            f"🎉 **TABRIKLAYMIZ! YANGI SULOLA VA QAL'A BARPO ETILDI!**\n\n"
            f"👑 Hukmdor: **{escape_md(raw_name)}**\n"
            f"🏰 Xonadon: **{h_emoji} {escape_md(h_name)}**\n"
            f"📍 Mintaqa: **{h_reg}**\n"
            f"🏯 Poytaxt Qal'a: **{escape_md(c_name)}** (1 ta shaxsiy qal'angiz)\n"
            f"🎖️ Lavozim: **Xonadon Asoschisi va Oliy Qiroli (1/1)**\n\n"
            f"📦 **Boshlang'ich Ta'minot:**\n"
            f"• 🪙 Oltin: **250** | 🌾 Oziq: **500** | ⛓️ Temir: **125**\n"
            f"• 🛡️ Armiya: **100** piyoda, **50** kamonchi, **25** otliq, **25** nayzachi\n"
            f"• 🏰 Qal'a mudofaasi: **500** ball | Soatlik daromad: **+100🪙, +250🌾, +75⛓️**\n\n"
            f"🛡️ Yangi hukmdor sifatida sizga **3 kunlik Tinchlik Qalqoni (Peace Shield)** taqdim etildi!\n\n"
            f"Qal'angizni boshqaring, devorlarini mustahkamlang, askarlar yollang va Temir Taxt uchun jangga otlaning!"
        )

        try:
            await update.effective_message.reply_text(
                "⚔️ *Westeros taxti uchun jangga xush kelibsiz!*",
                parse_mode="Markdown",
                reply_markup=persistent_reply_keyboard()
            )
        except Exception:
            pass

        try:
            await update.effective_message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))
        except Exception:
            await update.effective_message.reply_text(welcome_text, parse_mode=None, reply_markup=main_menu_keyboard(user_id))
        return

    # STANDART QAHRAMON NOMI (50 ta tarixiy xonadon uchun)
    if not context.user_data.get("awaiting_custom_name"):
        return

    if not username:
        await update.effective_message.reply_text(
            "❌ **KECHIRASIZ, O'YINDA QATNASHISH UCHUN TELEGRAM USERNAME BO'LISHI SHART!**\n\n"
            "Iltimos, Telegram sozlamalaridan o'zingizga `@username` o'rnating va qaytadan /start bosing!",
            parse_mode="Markdown"
        )
        return

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
        if existing and getattr(existing, "is_banned", False):
            await update.effective_message.reply_text(
                "🚫 **SIZNING HISOBINGIZ BLOKLANGAN!**",
                parse_mode="Markdown"
            )
            return

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

        # Bo'sh xonadonni aniqlash (har bir xonadonga faqat 1 kishi)
        house_obj = None
        if house_code:
            h_res = await session.execute(
                select(models.House).where(models.House.code == house_code)
            )
            found_h = h_res.scalar_one_or_none()
            if found_h:
                cnt = await crud.get_house_members_count(session, found_h.id)
                if cnt < 1:
                    house_obj = found_h

        reassigned_notice = ""
        if not house_obj:
            house_obj = await crud.get_random_available_house(session)
            if not house_obj:
                context.user_data.pop("awaiting_custom_name", None)
                context.user_data["awaiting_custom_house_name"] = True
                await update.effective_message.reply_text(
                    "⚔️ **WESTEROSDA BARCHA 50 TA ASOSIY XONADONLAR BAND BO'LDI!**\n\n"
                    "Ammo siz o'zingizning yangi xonadoningizga asos solishingiz va yangi Qal'a barpo etishingiz mumkin!\n\n"
                    "✍️ **1-QADAM: Yangi Xonadoningiz nomini yozing:**\n"
                    "Chatga yangi sulolangiz nomini matn sifatida yuboring *(masalan: `Qora Burgutlar`, `House Shadow`, `Muz Qoplonlari`)*:"
                )
                return
            if house_code and house_code != house_obj.code:
                reassigned_notice = f"\n\n*(Eslatma: Avvalgi xonadon band bo'lgani sababli, bot sizni bo'sh **{house_obj.emoji} {house_obj.name}** safiga Yagona Lord qilib tayinladi)*"
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
        f"👥 A'zolar soni: *1/1 (Yagona Lord)*"
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
    """Pastki doimiy menyu tugmalari bosilganda (Faqat shaxsiy chatda!)"""
    if not update.effective_chat or update.effective_chat.type != "private":
        return
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
    elif text == "💎 VIP & Donate":
        from handlers.donate_handler import donate_command
        await donate_command(update, context)
    elif text == "📢 Guruh & Kanal":
        from handlers.community_handler import community_command
        await community_command(update, context)


def register_start_handlers(app):
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.Regex("^(🏠 Bosh Menyu|🏰 Qalalarim|💎 VIP & Donate|📢 Guruh & Kanal)$") & filters.ChatType.PRIVATE, bottom_menu_text_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_custom_name_input), group=2)
    app.add_handler(CallbackQueryHandler(random_house_pick_callback, pattern="^random_house_pick$"))
    app.add_handler(CallbackQueryHandler(region_selected_callback, pattern="^sel_reg:"))
    app.add_handler(CallbackQueryHandler(house_selected_callback, pattern="^sel_house:"))
    app.add_handler(CallbackQueryHandler(hero_selected_callback, pattern="^sel_hero:"))
    app.add_handler(CallbackQueryHandler(hero_taken_callback, pattern="^hero_taken$"))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^menu_main$"))
    app.add_handler(CallbackQueryHandler(random_house_pick_callback, pattern="^back_to_regions$"))
    app.add_handler(CallbackQueryHandler(custom_house_region_callback, pattern="^reg_house_reg:"))
    app.add_handler(CallbackQueryHandler(custom_house_emoji_page_callback, pattern="^reg_emoji_page:"))
    app.add_handler(CallbackQueryHandler(custom_house_emoji_callback, pattern="^reg_house_emoji:"))
    app.add_handler(CallbackQueryHandler(noop_callback, pattern="^noop$"))

