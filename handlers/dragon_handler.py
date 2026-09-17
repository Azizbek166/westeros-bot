import random
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from keyboards.menus import back_to_main_keyboard
from config import escape_md


DRAGON_PRESETS = [
    ("Balerion", "A", "🖤 Qora Qo'rqinch — eng bahaybat va qora olov purkovchi afsona"),
    ("Drogon", "A", "🖤 Qora va qizil qanotli qudratli ajdar"),
    ("Rhaegal", "B", "💚 Zumrad yashil va bronza olovli jangovar ajdar"),
    ("Viserion", "C", "💛 Oltin va oq rangli ulug'vor ajdar"),
    ("Caraxes", "A", "🩸 Qonli Bo'ron — Daemon Targaryenning shafqatsiz ajdari"),
    ("Vhagar", "A", "⚡ Qadimgi Urushlar Afsonasi — eng ulkan qanotlar"),
    ("Syrax", "B", "💛 Oltin rangli chaqqon malika ajdari"),
]


async def dragon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dragons buyrug'i"""
    user_id = update.effective_user.id
    await show_dragon_hub(update, user_id, is_message=True)


async def dragon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_dragons callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_dragon_hub(query, user_id, is_message=False)


async def show_dragon_hub(target, user_id: int, is_message: bool):
    """Ajdarlar markazi (Maksimal 2 ta ajdar, 20-daraja, tuxum qo'yish tizimi)"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            msg = "Iltimos, avval /start ni bosing."
            if is_message:
                await target.message.reply_text(msg)
            else:
                await target.edit_message_text(msg)
            return

        dragons = await crud.get_user_dragons(session, user.id)

        if not dragons:
            # Ajdar tuxumini tanlash (narxlar bilan)
            buttons = []
            prices = {"A": "3,000🪙 1,500⛓️", "B": "2,000🪙 1,000⛓️", "C": "1,200🪙 600⛓️"}
            for name, grade, desc in DRAGON_PRESETS:
                p = prices.get(grade, "2,000🪙 1,000⛓️")
                buttons.append([InlineKeyboardButton(f"🥚 {name} ({grade} Toifa — {p})", callback_data=f"dragon_claim:{name}:{grade}")])
            buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

            text = (
                f"🐉 **VALYRIA MEROSI — AFSONAVIY AJDARLAR**\n\n"
                f"Ajdarlar — Vesterosning eng noyob va qudratli maxluqlaridir! "
                f"Ularni xarid qilish va boqish faqat boy va nufuzli lordlar qo'lidan keladi.\n\n"
                f"🎒 Sizning zaxirangiz: **{user.gold:,}**🪙 oltin, **{user.iron:,}**⛓️ temir\n\n"
                f"Tarbiyalash uchun ajdar tuxumini tanlang:"
            )
            try:
                if is_message:
                    await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
                else:
                    await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                if hasattr(target, "message") and target.message:
                    await target.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            return

        stage_names = {
            "egg": "🥚 Ajdar Tuxumi (Ochirilmagan)",
            "baby": "🐉 Kichik Ajdar (Olov purkay oladi)",
            "adult": "🦅 Bahaybat Jangovar Ajdar (Qal'alarni yondiruvchi)",
        }
        grade_names = {"A": "🔥 A Toifa", "B": "💚 B Toifa", "C": "💛 C Toifa"}

        count_str = f"({len(dragons)}/3)"
        desc_header = ""
        if len(dragons) >= 3:
            desc_header = "👑 **Siz Vesteros osmonida 3 ta qudratli ajdarga ega afsonaviy hukmdorsiz!**\n\n"

        text = (
            f"🐉 **SIZNING AFSONAVIY AJDARLARINGIZ {count_str}**\n\n"
            f"{desc_header}"
        )

        buttons = []
        for idx, dragon in enumerate(dragons, 1):
            hunger_bar = "█" * (dragon.hunger // 10) + "░" * (10 - (dragon.hunger // 10))
            st_name = stage_names.get(dragon.stage, dragon.stage)
            gr_name = grade_names.get(dragon.grade, dragon.grade)

            egg_info = ""
            if dragon.stage == "adult" and dragon.level >= 10:
                if dragon.has_laid_egg:
                    egg_info = "🐣 Nasl: Tuxum qo'ygan\n"
                elif len(dragons) < 3:
                    egg_info = "✨ **Tuxum qo'yishga tayyor!** (Nasl qoldirish mumkin)\n"

            deploy_st = await crud.get_dragon_deployment_status(session, dragon.id)
            if deploy_st["type"] == "stationed":
                loc_str = f"🏰 **{deploy_st.get('territory_name', 'Qal\'a')}** mudofaasida"
            elif deploy_st["type"] == "marching":
                loc_str = f"⚔️ **{deploy_st.get('target_name', 'Qal\'a')}**ga harbiy yurishda"
            else:
                loc_str = "🏠 Uyada (hujum va mudofaaga tayyor)"

            text += (
                f"**{idx}-Ajdar: {dragon.name}**\n"
                f"🏷️ Toifa: **{gr_name}** | Holati: **{st_name}**\n"
                f"📍 Joylashuvi: {loc_str}\n"
                f"⭐ Daraja: **{dragon.level} / 20**\n"
                f"⚔️ Jang Quvvati: **{dragon.power:,}**\n"
                f"🍗 To'qlik: `[{hunger_bar}]` **{dragon.hunger}%**\n"
            )

            if dragon.artifact_code:
                from data.artifacts_data import ARTIFACTS_DATA
                art_item = ARTIFACTS_DATA.get(dragon.artifact_code, {})
                text += f"🏺 Taqilgan Artefakt: **{art_item.get('name', dragon.artifact_code)}** (+{int(art_item.get('dragon_bonus', 0)*100)}% quvvat)\n"

            text += f"{egg_info}"

            if deploy_st["type"] == "stationed":
                buttons.append([InlineKeyboardButton(f"↩️ {dragon.name}ni Qal'adan Uyaga Qaytarish", callback_data=f"dragon_recall_home:{deploy_st['territory_id']}:{dragon.id}")])

            if dragon.stage == "egg":
                buttons.append([InlineKeyboardButton(f"✨ {dragon.name} Tuxumini Ochirish (2,500🌾 1,500⛓️ 1,000🪙)", callback_data=f"dragon_hatch_{dragon.id}")])
            else:
                costs = crud.get_dragon_upgrade_cost(dragon)
                feed_cost = 250 + (dragon.level * 40)
                if dragon.level < 20:
                    text += f"📈 **Keyingi {dragon.level+1}-daraja uchun:** 🌾{costs['food']:,} | ⛓️{costs['iron']:,} | 🪙{costs['gold']:,}\n\n"
                else:
                    text += f"⭐ **Ajdar maksimal cho'qqisiga yetgan!**\n\n"

                row1 = [
                    InlineKeyboardButton(f"🍗 Boqish (-{feed_cost}🌾)", callback_data=f"dragon_feed_{dragon.id}"),
                ]
                if dragon.level < 20:
                    row1.append(InlineKeyboardButton(f"🔥 Kuchaytirish ({dragon.level}->{dragon.level+1})", callback_data=f"dragon_train_{dragon.id}"))
                else:
                    row1.append(InlineKeyboardButton("⭐ MAX", callback_data=f"dragon_max_{dragon.id}"))
                buttons.append(row1)

                buttons.append([InlineKeyboardButton(f"🏺 {dragon.name} Artefaktlari", callback_data=f"dragon_art_shop_{dragon.id}")])

                if dragon.stage == "adult" and dragon.level >= 10 and len(dragons) < 3 and not dragon.has_laid_egg:
                    buttons.append([InlineKeyboardButton(f"🥚 {dragon.name}: Yangi Tuxum Qo'yish (Nasl)", callback_data=f"dragon_lay_egg_{dragon.id}")])

            buttons.append([InlineKeyboardButton(f"🗑️ {dragon.name}ni Tashlash (Ozod Qilish)", callback_data=f"dragon_release_ask_{dragon.id}")])

        if len(dragons) < 3:
            buttons.append([InlineKeyboardButton(f"🥚 Yangi Ajdar Xarid Qilish ({len(dragons)}/3)", callback_data="dragon_buy_more")])

        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        try:
            if is_message:
                await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            if hasattr(target, "message") and target.message:
                await target.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def dragon_claim_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdar tuxumini tanlash va sotib olish"""
    query = update.callback_query

    parts = query.data.split(":")
    name = parts[1]
    grade = parts[2]
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return
        ok, msg, dragon = await crud.claim_dragon_egg(session, user.id, name, grade)

    await query.answer(msg, show_alert=True)
    if ok:
        await show_dragon_hub(query, user_id, is_message=False)


async def dragon_hatch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tuxumni ochirish"""
    query = update.callback_query
    user_id = query.from_user.id
    
    dragon_id = None
    if "_" in query.data and query.data.split("_")[-1].isdigit():
        dragon_id = int(query.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return
        ok, msg = await crud.hatch_dragon(session, user.id, dragon_id)

    await query.answer(msg, show_alert=True)
    await show_dragon_hub(query, user_id, is_message=False)


async def dragon_feed_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarni boqish"""
    query = update.callback_query
    user_id = query.from_user.id

    dragon_id = None
    if "_" in query.data and query.data.split("_")[-1].isdigit():
        dragon_id = int(query.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return
        ok, msg = await crud.feed_dragon(session, user.id, dragon_id)

    await query.answer(msg, show_alert=True)
    await show_dragon_hub(query, user_id, is_message=False)


async def dragon_train_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarni mashq qildirish"""
    query = update.callback_query
    user_id = query.from_user.id

    dragon_id = None
    if "_" in query.data and query.data.split("_")[-1].isdigit():
        dragon_id = int(query.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return
        ok, msg = await crud.train_dragon(session, user.id, dragon_id)

    await query.answer(msg, show_alert=True)
    await show_dragon_hub(query, user_id, is_message=False)


async def dragon_lay_egg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarning yangi tuxum qo'yishi"""
    query = update.callback_query
    user_id = query.from_user.id
    dragon_id = int(query.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return
        ok, msg = await crud.dragon_lay_egg(session, user.id, dragon_id)

    await query.answer(msg, show_alert=True)
    await show_dragon_hub(query, user_id, is_message=False)


async def show_dragon_art_shop(query, user_id: int, dragon_id: int):
    """Ajdar artefaktlari menyusini ko'rsatish"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        dragon = await session.get(models.Dragon, dragon_id)
        if not user or not dragon:
            return

        from data.artifacts_data import ARTIFACTS_DATA, DRAGON_ARTIFACTS

        curr_art_str = "Mavjud emas"
        if dragon.artifact_code:
            curr_art_str = ARTIFACTS_DATA.get(dragon.artifact_code, {}).get("name", dragon.artifact_code)

        text = (
            f"🏺 **{dragon.name.upper()} UCHUN VALYRIA ARTEFAKTLARI**\n\n"
            f"Hozirgi quvvat: **{dragon.power:,}** | Daraja: **{dragon.level}**\n"
            f"Taqilgan artefakt: **{curr_art_str}**\n\n"
            f"🎒 Hamyoningiz: **{user.gold:,}**🪙 oltin, **{user.iron:,}**⛓️ temir\n\n"
            f"Ajdar uchun afsonaviy relikni tanlang va jihozlang:"
        )

        buttons = []
        for code in DRAGON_ARTIFACTS:
            item = ARTIFACTS_DATA.get(code, {})
            is_equipped = (dragon.artifact_code == code)
            btn_txt = f"{'✅ ' if is_equipped else '⚡ '}{item.get('name')} ({item.get('price_gold', 0):,}🪙, {item.get('price_iron', 0):,}⛓️)"
            if is_equipped:
                btn_txt += " [Taqilgan]"
            buttons.append([InlineKeyboardButton(btn_txt, callback_data=f"dragon_buy_art:{dragon.id}:{code}")])

        buttons.append([InlineKeyboardButton("🔙 Ajdarlarga Qaytish", callback_data="menu_dragons")])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def dragon_art_shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdar artefaktlari do'koni va jihozlash menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    dragon_id = int(query.data.split("_")[-1])
    await show_dragon_art_shop(query, user_id, dragon_id)


async def dragon_buy_art_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdar artefaktini sotib olish va taqish"""
    query = update.callback_query
    parts = query.data.split(":")
    dragon_id = int(parts[1])
    art_code = parts[2]
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            await query.answer("Foydalanuvchi topilmadi.", show_alert=True)
            return
        ok, msg = await crud.equip_dragon_artifact(session, user.id, dragon_id, art_code)

    await query.answer(msg, show_alert=True)
    await show_dragon_art_shop(query, user_id, dragon_id)


async def dragon_max_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⭐ Ushbu ajdar maksimal 20-darajaga yetgan! U o'zining eng qudratli cho'qqisida.", show_alert=True)


async def dragon_release_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdardan voz kechish (tashlash) tasdig'ini so'rash"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    user_id = query.from_user.id
    try:
        dragon_id = int(query.data.split("_")[-1])
    except Exception:
        dragon_id = 0

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_any(session, user_id)
        dragon = await session.get(models.Dragon, dragon_id) if (dragon_id and dragon_id <= 2147483647) else None
        if (not dragon or (user and dragon.user_id != user.id)) and user:
            u_dragons = await crud.get_user_dragons(session, user.id)
            if u_dragons:
                dragon = u_dragons[0]

        if not dragon:
            try:
                await query.answer("❌ Ajdar topilmadi yoki u allaqachon tashlangan.", show_alert=True)
            except Exception:
                pass
            await show_dragon_hub(query, user_id, is_message=False)
            return

        buttons = [
            [InlineKeyboardButton("🗑️ Ha, Ajdarni Tashlash", callback_data=f"dragon_release_confirm_{dragon.id}")],
            [InlineKeyboardButton("❌ Bekor Qilish", callback_data="menu_dragons")],
        ]
        dr_name = dragon.name.replace("*", "").replace("_", "")
        text = (
            f"⚠️ **DIQQAT: AJDARNI TASHLASH!**\n\n"
            f"Haqiqatan ham **{dr_name}** ({dragon.grade} Toifa, {dragon.level}-daraja) ajdaringizdan voz kechib, uni tashlamoqchimisiz?\n\n"
            f"❗️ *Ushbu amalni ortga qaytarib bo'lmaydi!* "
            f"Ajdar tashlangach, bo'shagan o'ringa yangi ajdar xarid qilishingiz mumkin bo'ladi."
        )
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                if query.message:
                    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def dragon_release_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarni bazadan o'chirish (tashlash)"""
    query = update.callback_query
    try:
        dragon_id = int(query.data.split("_")[-1])
    except Exception:
        dragon_id = 0
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.release_user_dragon(session, user_id, dragon_id)

    try:
        clean_msg = msg.replace("**", "").replace("*", "").replace("_", "")
        await query.answer(clean_msg, show_alert=True)
    except Exception:
        pass
    await show_dragon_hub(query, user_id, is_message=False)


async def dragon_buy_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'shimcha ajdar tuxumi xarid qilish oynasi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        buttons = []
        prices = {"A": "3,000🪙 1,500⛓️", "B": "2,000🪙 1,000⛓️", "C": "1,200🪙 600⛓️"}
        for name, grade, desc in DRAGON_PRESETS:
            p = prices.get(grade, "2,000🪙 1,000⛓️")
            buttons.append([InlineKeyboardButton(f"🥚 {name} ({grade} Toifa — {p})", callback_data=f"dragon_claim:{name}:{grade}")])
        buttons.append([InlineKeyboardButton("🔙 Ajdarlar Markaziga Qaytish", callback_data="menu_dragons")])

        text = (
            f"🥚 **YANGI AJDAR TUXUMINI TANLASH (3 tagacha)**\n\n"
            f"🎒 Sizning zaxirangiz: **{user.gold:,}**🪙 oltin, **{user.iron:,}**⛓️ temir\n\n"
            f"Quyidagi afsonaviy ajdarlardan birini tanlang:"
        )
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text.replace("*", ""), reply_markup=InlineKeyboardMarkup(buttons))


async def dragon_recall_home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarni qal'adan to'g'ridan-to'g'ri uyaga qaytarish"""
    query = update.callback_query
    parts = query.data.split(":")
    terr_id = int(parts[1])
    dragon_id = int(parts[2])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.recall_dragon_from_castle(session, user_id, terr_id, dragon_id)

    try:
        clean_msg = msg.replace("**", "").replace("*", "").replace("_", "")
        await query.answer(clean_msg, show_alert=True)
    except Exception:
        pass
    await show_dragon_hub(query, user_id, is_message=False)


def register_dragon_handlers(app):
    app.add_handler(CommandHandler("dragons", dragon_command))
    app.add_handler(CommandHandler("dragon", dragon_command))
    app.add_handler(CallbackQueryHandler(dragon_callback, pattern="^menu_dragons$"))
    app.add_handler(CallbackQueryHandler(dragon_buy_more_callback, pattern="^dragon_buy_more$"))
    app.add_handler(CallbackQueryHandler(dragon_recall_home_callback, pattern="^dragon_recall_home:"))
    app.add_handler(CallbackQueryHandler(dragon_claim_callback, pattern="^dragon_claim:"))
    app.add_handler(CallbackQueryHandler(dragon_hatch_callback, pattern="^dragon_hatch"))
    app.add_handler(CallbackQueryHandler(dragon_feed_callback, pattern="^dragon_feed"))
    app.add_handler(CallbackQueryHandler(dragon_train_callback, pattern="^dragon_train"))
    app.add_handler(CallbackQueryHandler(dragon_lay_egg_callback, pattern="^dragon_lay_egg_"))
    app.add_handler(CallbackQueryHandler(dragon_art_shop_callback, pattern="^dragon_art_shop_"))
    app.add_handler(CallbackQueryHandler(dragon_buy_art_callback, pattern="^dragon_buy_art:"))
    app.add_handler(CallbackQueryHandler(dragon_max_callback, pattern="^dragon_max_"))
    app.add_handler(CallbackQueryHandler(dragon_release_ask_callback, pattern="^dragon_release_ask_"))
    app.add_handler(CallbackQueryHandler(dragon_release_confirm_callback, pattern="^dragon_release_confirm_"))

