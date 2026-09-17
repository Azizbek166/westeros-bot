import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
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
        "Westerosdagi barcha strategik qal'alar va shahar-portlar joylashuvi.\n"
        "Qal'a haqida batafsil ma'lumot olish, garnizon joylashtirish yoki unga yurish qilish uchun quyidan tanlang:"
    )
    map_img_path = os.path.join("assets", "westeros_map.jpg")
    has_photo = os.path.exists(map_img_path)

    if is_message:
        if has_photo:
            with open(map_img_path, "rb") as f:
                await target.message.reply_photo(photo=f, caption=text, parse_mode="Markdown", reply_markup=territories_keyboard())
        else:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=territories_keyboard())
    else:
        chat_id = target.message.chat_id
        bot = target.get_bot() if hasattr(target, "get_bot") else target.message.get_bot()
        if has_photo:
            if getattr(target.message, "photo", None):
                try:
                    await target.edit_message_caption(caption=text, parse_mode="Markdown", reply_markup=territories_keyboard())
                    return
                except Exception:
                    pass
            try:
                await target.message.delete()
            except Exception:
                pass
            try:
                with open(map_img_path, "rb") as f:
                    await bot.send_photo(chat_id=chat_id, photo=f, caption=text, parse_mode="Markdown", reply_markup=territories_keyboard())
                return
            except Exception:
                pass

        try:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=territories_keyboard())
        except Exception:
            try:
                await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=territories_keyboard())
            except Exception:
                clean_text = text.replace("*", "").replace("_", "")
                await bot.send_message(chat_id=chat_id, text=clean_text, reply_markup=territories_keyboard())


async def view_territory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bitta hudud tafsilotlarini ko'rsatish"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    user_id = query.from_user.id
    terr_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        terr = await crud.get_territory_by_id(session, terr_id)
        if not terr:
            await query.answer("Hudud topilmadi.", show_alert=True)
            return

        user = await crud.get_user_any(session, user_id)
        is_own = user and user.house_id and user.house_id == terr.owner_house_id

        # Ittifoqchi qal'asi ekanligini tekshirish
        is_ally = False
        alliance_type_str = ""
        if user and user.house_id and terr.owner_house_id and not is_own:
            al_res = await session.execute(
                select(models.Alliance).where(
                    models.Alliance.status == "active",
                    ((models.Alliance.house_a_id == user.house_id) & (models.Alliance.house_b_id == terr.owner_house_id)) |
                    ((models.Alliance.house_a_id == terr.owner_house_id) & (models.Alliance.house_b_id == user.house_id))
                )
            )
            al = al_res.scalar_one_or_none()
            if al:
                is_ally = True
                alliance_type_str = " (💍 To'y Ittifoqchimiz)" if al.type == "marriage" else " (⚔️ Harbiy Ittifoqchimiz)"

        owner_name = f"{terr.owner_house.emoji} {terr.owner_house.name}" if terr.owner_house else "Egaliksiz (Qaroqchilar)"
        clean_owner = owner_name.replace("*", "").replace("_", "").replace("`", "")

        dragon_info_str = "Mavjud emas"
        st_dragon = crud.get_stationed_dragon_info(terr)
        if st_dragon:
            dragon_info_str = f"🔥 **{st_dragon.get('dragon_name')}** (Kuch: {st_dragon.get('power')}, Egasi: {st_dragon.get('user_name')})"

        buttons = []
        c_lvl = getattr(terr, "castle_level", 1) or 1
        if is_own:
            buttons.append([InlineKeyboardButton("🛡️ Qal'ani Himoya Qilish (Askar Joylash)", callback_data=f"def_rf_menu:{terr.id}")])
            buttons.append([InlineKeyboardButton("↩️ Garnizondan Askarlarni Qaytarish", callback_data=f"def_withdraw_rf:{terr.id}")])
            if st_dragon:
                if (user and st_dragon.get("user_id") == user.id) or (user and user.house and user.house.lord_user_id == user.telegram_id):
                    buttons.append([InlineKeyboardButton("🚫 Ajdarni Qal'adan Qaytarish", callback_data=f"def_recall_dragon:{terr.id}")])
                else:
                    buttons.append([InlineKeyboardButton("🐉 Ajdar Qo'riqlamoqda", callback_data="terr_dragon_info")])
            else:
                buttons.append([InlineKeyboardButton("🐉 Ajdarni Mudofaaga Joylashtirish", callback_data=f"def_station_dragon:{terr.id}")])
            if c_lvl < 5:
                c_cost_g = c_lvl * 3000
                c_cost_i = c_lvl * 2500
                buttons.append([InlineKeyboardButton(f"🏰 Qal'ani Kengaytirish (Tier {c_lvl+1}: {c_cost_g:,}🪙/{c_cost_i:,}⛓️)", callback_data=f"upgrade_castle:{terr.id}")])
            buttons.append([InlineKeyboardButton("🛡️ Devorni Kuchaytirish (+150 Mudofaa)", callback_data=f"upgrade_walls:{terr.id}")])
            buttons.append([InlineKeyboardButton("💰 Qal'a Boshqaruvi & O'lpon", callback_data=f"my_c_detail:{terr.id}")])
        elif is_ally:
            buttons.append([InlineKeyboardButton(f"🤝 Qal'a Mudofaasiga Yordam Yuborish{alliance_type_str}", callback_data=f"def_rf_menu:{terr.id}")])
            if not st_dragon:
                buttons.append([InlineKeyboardButton("🐉 Ittifoqchi Qal'aga Ajdar Yuborish", callback_data=f"def_station_dragon:{terr.id}")])
        else:
            buttons.append([InlineKeyboardButton("⚔️ Ushbu Qal'aga Yurish Qilish", callback_data=f"march_prep:{terr.id}")])

        buttons.append([InlineKeyboardButton("🔙 Xaritaga Qaytish", callback_data="menu_map")])

        ally_tag = f"\n🤝 **Ittifoqchilik:** Bu sizning rasmiy ittifoqchingiz qal'asi! Mudofaa uchun askar va ajdar yuborishingiz mumkin.\n" if is_ally else ""

        if is_own:
            footer_text = "Qal'ani dushmandan himoya qilish uchun garnizonni to'ldiring va devorlarni mustahkamlang!"
        elif is_ally:
            footer_text = "Ittifoqchining qal'asi mudofaasiga ko'maklashing!"
        else:
            footer_text = "Ushbu hududni egallash xonadoningizga doimiy daromad va shon-sharaf keltiradi!"

        g_inf = terr.garrison_infantry or 0
        g_arc = terr.garrison_archers or 0
        g_cav = terr.garrison_cavalry or 0
        g_sp = terr.garrison_spearmen or 0
        pop = terr.population or 0
        g_inc = terr.gold_income or 0
        f_inc = terr.food_income or 0
        i_inc = terr.iron_income or 0
        def_val = terr.defense or 0
        c_name = terr.castle_name or terr.name or "Qal'a"
        t_name = terr.name or "Hudud"
        reg = terr.region or "Vesteros"

        text = (
            f"🏰 **{t_name.upper()} — {c_name}**\n\n"
            f"📍 Mintaqa: **{reg}**\n"
            f"👑 Hukmron Xonadon: **{clean_owner}**{ally_tag}\n"
            f"👥 Aholi: **{pop:,}**\n\n"
            f"💰 **SOATLIK DAROMAD:**\n"
            f"🪙 +{g_inc} oltin | 🌾 +{f_inc} oziq-ovqat | ⛓️ +{i_inc} temir\n\n"
            f"🛡️ **QAL'A MUDOFAASI:** {def_val} ball\n"
            f"🐉 **MUDOFAADAGI AJDAR:** {dragon_info_str}\n\n"
            f"⚔️ **GARNIZON KUCHLARI:**\n"
            f"• 🛡️ Piyoda: {g_inf:,}\n"
            f"• 🏹 Kamonchi: {g_arc:,}\n"
            f"• 🐎 Otliq: {g_cav:,}\n"
            f"• 🗡️ Nayzachi: {g_sp:,}\n\n"
            f"{footer_text}"
        )

        chat_id = query.message.chat_id
        if getattr(query.message, "photo", None):
            try:
                await query.message.delete()
            except Exception:
                pass
            try:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                clean_text = text.replace("*", "").replace("_", "").replace("`", "")
                await context.bot.send_message(chat_id=chat_id, text=clean_text, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            try:
                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                clean_text = text.replace("*", "").replace("_", "").replace("`", "")
                try:
                    await query.edit_message_text(clean_text, reply_markup=InlineKeyboardMarkup(buttons))
                except Exception:
                    await context.bot.send_message(chat_id=chat_id, text=clean_text, reply_markup=InlineKeyboardMarkup(buttons))


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
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            await query.answer("Foydalanuvchi topilmadi.", show_alert=True)
            return
        ok, msg = await crud.station_dragon_in_castle(session, user.id, terr_id)

    await query.answer(msg, show_alert=True)
    try:
        await view_territory_callback(update, context)
    except Exception:
        pass


async def def_recall_dragon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarni qal'a mudofaasidan qaytarib olish"""
    query = update.callback_query
    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            await query.answer("Foydalanuvchi topilmadi.", show_alert=True)
            return
        ok, msg = await crud.recall_dragon_from_castle(session, user.id, terr_id)

    await query.answer(msg, show_alert=True)
    try:
        await view_territory_callback(update, context)
    except Exception:
        pass


async def terr_dragon_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🐉 Qal'a osmonida ittifoqchi ajdar parvoz qilib, qal'ani dushman zarbalaridan himoya qilmoqda.", show_alert=True)


async def my_castles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/castles buyrug'i"""
    user_id = update.effective_user.id
    await show_my_castles(update, user_id, is_message=True)


async def my_castles_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_castles callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_my_castles(query, user_id, is_message=False)


async def show_my_castles(target, user_id: int, is_message: bool):
    """Xonadonga qarashli barcha qal'alar va daromadlar boshqaruvi"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house_id:
            msg = "Siz hali birorta ham xonadonga a'zo emassiz!"
            if is_message:
                await target.message.reply_text(msg)
            else:
                await target.edit_message_text(msg)
            return

        castles = await crud.get_house_territories(session, user.house_id)

        if not castles:
            text = (
                f"🏰 **QAL'ALARIM — {user.house.emoji} {user.house.name.upper()}**\n\n"
                f"Hozirda xonadoningiz birorta ham strategik qal'aga egalik qilmaydi.\n"
                f"🗺️ **Xarita** bo'limiga o'ting va dushman qal'alariga yurish qilib, ularni zabt eting!\n"
                f"Qal'alarni bosib olgach, ulardan soatlik o'lpon yig'ishingiz mumkin."
            )
            buttons = [
                [InlineKeyboardButton("🗺️ Westeros Xaritasi", callback_data="menu_map")],
                [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
            ]
            if is_message:
                await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            return

        from datetime import datetime, timedelta
        now = datetime.utcnow()

        text = (
            f"🏰 **QAL'ALARIM VA G'AZNALAR — {user.house.emoji} {user.house.name.upper()}**\n\n"
            f"Xonadoningiz tasarrufidagi barcha qal'alar va ularning g'aznalari:\n\n"
        )

        buttons = []
        for c in castles:
            tot_gar = c.garrison_infantry + c.garrison_archers + c.garrison_cavalry + c.garrison_spearmen
            last_tax = c.last_tax_collected_at or (now - timedelta(hours=4))
            hours = min(4, int(max(0, (now - last_tax).total_seconds()) // 3600))
            tax_tag = f"💰 {hours}/4 soat o'lpon tayyor" if hours >= 1 else "⏳ O'lpon yig'ilmoqda"

            text += (
                f"• 🏰 **{c.castle_name}** ({c.name})\n"
                f"  └ 🛡️ Garnizon: **{tot_gar:,}** askar | Mudofaa: **{c.defense}**\n"
                f"  └ 💰 Daromad: +{c.gold_income}🪙, +{c.food_income}🌾, +{c.iron_income}⛓️/soat\n"
                f"  └ ✨ Holat: _{tax_tag}_\n\n"
            )
            buttons.append([InlineKeyboardButton(f"🏰 {c.castle_name} ({hours}s o'lpon)", callback_data=f"my_c_detail:{c.id}")])

        buttons.append([InlineKeyboardButton("🗺️ Butun Xarita", callback_data="menu_map")])
        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def show_my_castle_detail(query, user_id: int, terr_id: int):
    """Qal'a boshqaruvi va o'lpon yig'ish sahifasini ko'rsatish"""
    from datetime import datetime, timedelta
    now = datetime.utcnow()

    async with AsyncSessionLocal() as session:
        terr = await crud.get_territory_by_id(session, terr_id)
        user = await crud.get_user_with_relations(session, user_id)
        if not terr or not user:
            return

        last_tax = terr.last_tax_collected_at or (now - timedelta(hours=4))
        elapsed_sec = max(0, (now - last_tax).total_seconds())
        hours = min(4, int(elapsed_sec // 3600))
        rem_min = max(1, int((3600 - elapsed_sec) // 60)) if hours < 1 else 0

        gold_inc = terr.gold_income or 0
        food_inc = terr.food_income or 0
        iron_inc = terr.iron_income or 0
        acc_gold = gold_inc * hours
        acc_food = food_inc * hours
        acc_iron = iron_inc * hours

        st_dragon = crud.get_stationed_dragon_info(terr)
        drg_str = f"🔥 {st_dragon.get('dragon_name')} ({st_dragon.get('user_name')})" if st_dragon else "Mavjud emas"

        c_name = (terr.castle_name or terr.name or "Qal'a").upper()
        g_inf = terr.garrison_infantry or 0
        g_arc = terr.garrison_archers or 0
        g_cav = terr.garrison_cavalry or 0
        g_sp = terr.garrison_spearmen or 0

        c_lvl = getattr(terr, "castle_level", 1) or 1
        tier_names = {
            1: "Istehkom Qal'acha (Tier 1)",
            2: "Mustahkam Tosh Qal'a (Tier 2)",
            3: "Ulug'vor Feodal Qasr (Tier 3)",
            4: "Momaqaldiroq Qal'asi (Tier 4)",
            5: "O'tib Bo'lmas Afsonaviy Qasr (Tier 5)",
        }
        tier_str = tier_names.get(c_lvl, f"Tier {c_lvl}")

        text = (
            f"🏰 **QAL'A BOSHQARUVI: {c_name}**\n\n"
            f"📍 Hudud: **{terr.name}** ({terr.region})\n"
            f"🏛️ Qal'a Bosqichi: **{tier_str}**\n"
            f"🛡️ Mudofaa Devori: **{terr.defense or 0}** ball\n"
            f"🐉 Mudofaadagi Ajdar: **{drg_str}**\n\n"
            f"⚔️ **GARNIZON KUCHLARI:**\n"
            f"• 🛡️ Piyoda: **{g_inf:,}**\n"
            f"• 🏹 Kamonchi: **{g_arc:,}**\n"
            f"• 🐎 Otliq: **{g_cav:,}**\n"
            f"• 🗡️ Nayzachi: **{g_sp:,}**\n\n"
            f"💰 **TO'PLANGAN O'LPON ({hours}/4 soat):**\n"
            f"• 🪙 Oltin: **+{acc_gold:,}**\n"
            f"• 🌾 Oziq: **+{acc_food:,}**\n"
            f"• ⛓️ Temir: **+{acc_iron:,}**\n"
            f"{f'⏳ Keyingi o\'lpon tayyor bo\'lishiga: {rem_min} daqiqa' if hours < 1 else '✅ O\'lponni yig\'ib olishga tayyor!'}\n"
        )

        buttons = []
        if hours >= 1:
            buttons.append([InlineKeyboardButton(f"💰 O'lpon Olish ({hours} soatlik: +{acc_gold:,}🪙)", callback_data=f"collect_tax:{terr.id}")])

        buttons.append([InlineKeyboardButton("🛡️ Garnizonga Askar Joylashtirish", callback_data=f"def_rf_menu:{terr.id}")])
        buttons.append([InlineKeyboardButton("↩️ Garnizondan Askarlarni Qaytarish", callback_data=f"def_withdraw_rf:{terr.id}")])

        if st_dragon:
            buttons.append([InlineKeyboardButton("🚫 Ajdarni Qaytarib Olish", callback_data=f"def_recall_dragon:{terr.id}")])
        else:
            buttons.append([InlineKeyboardButton("🐉 Ajdarni Qal'aga Joylashtirish", callback_data=f"def_station_dragon:{terr.id}")])

        if c_lvl < 5:
            c_cost_g = c_lvl * 3000
            c_cost_i = c_lvl * 2500
            buttons.append([InlineKeyboardButton(f"🏰 Qal'ani Kengaytirish (Tier {c_lvl+1}: {c_cost_g:,}🪙/{c_cost_i:,}⛓️)", callback_data=f"upgrade_castle:{terr.id}")])

        buttons.append([InlineKeyboardButton("🛡️ Devorni Kuchaytirish (-1,500🪙, -2,000⛓️)", callback_data=f"upgrade_walls:{terr.id}")])
        buttons.append([InlineKeyboardButton("🔙 Qalalarim Ro'yxati", callback_data="menu_castles")])
        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def my_castle_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'a boshqaruvi va o'lpon yig'ish sahifasi"""
    query = update.callback_query
    await query.answer()
    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id
    await show_my_castle_detail(query, user_id, terr_id)


async def collect_tax_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'lpon yig'ib olish"""
    query = update.callback_query
    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            await query.answer("Foydalanuvchi topilmadi.", show_alert=True)
            return
        ok, msg, res = await crud.collect_castle_tax(session, user.id, terr_id)

    await query.answer(msg if not ok else "✅ O'lpon muvaffaqiyatli qabul qilindi!", show_alert=True)
    await show_my_castle_detail(query, user_id, terr_id)


async def upgrade_walls_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'a devorlarini kuchaytirish"""
    query = update.callback_query
    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await session.get(models.Territory, terr_id)
        if not user or not terr:
            await query.answer("Ma'lumot topilmadi.", show_alert=True)
            return

        if user.gold < 1500 or user.iron < 2000:
            await query.answer("❌ Devorni kuchaytirish uchun 1,500 oltin va 2,000 temir kerak!", show_alert=True)
            return

        user.gold -= 1500
        user.iron -= 2000
        terr.defense = (terr.defense or 0) + 150
        user.prestige = (user.prestige or 0) + 50
        await session.commit()

    await query.answer("🏰 Qal'a devorlari mustahkamlandi! (+150 Mudofaa, +50 Prestige)", show_alert=True)
    await show_my_castle_detail(query, user_id, terr_id)


async def upgrade_castle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'a qasrini (Tier) keyingi bosqichga ko'tarish"""
    query = update.callback_query
    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.upgrade_castle_keep(session, user_id, terr_id)

    await query.answer(msg, show_alert=True)
    await show_my_castle_detail(query, user_id, terr_id)


async def show_garrison_withdraw_menu(target, user_id: int, terr_id: int):
    """Qal'a garnizonidan askarlarni qaytarib olish menyusi"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await session.get(models.Territory, terr_id)
        if not user or not terr:
            return

        g_inf = terr.garrison_infantry or 0
        g_arc = terr.garrison_archers or 0
        g_cav = terr.garrison_cavalry or 0
        g_sp = terr.garrison_spearmen or 0
        tot_g = g_inf + g_arc + g_cav + g_sp

        u_army = (
            (user.army.infantry or 0)
            + (user.army.archers or 0)
            + (user.army.cavalry or 0)
            + (user.army.spearmen or 0)
        ) if (user and user.army) else 0

        buttons = [
            [
                InlineKeyboardButton("↩️ 50 ta Askar", callback_data=f"def_with_act:{terr.id}:50"),
                InlineKeyboardButton("↩️ 100 ta Askar", callback_data=f"def_with_act:{terr.id}:100"),
            ],
            [
                InlineKeyboardButton("↩️ 250 ta Askar", callback_data=f"def_with_act:{terr.id}:250"),
                InlineKeyboardButton("↩️ 500 ta Askar", callback_data=f"def_with_act:{terr.id}:500"),
            ],
            [
                InlineKeyboardButton("↩️ Barcha Garnizonni Qaytarish", callback_data=f"def_with_act:{terr.id}:all"),
            ],
            [
                InlineKeyboardButton("✍️ Sonini Qo'lda Kiritish", callback_data=f"def_custom_with:{terr.id}"),
            ],
            [
                InlineKeyboardButton("🔙 Qal'aga Qaytish", callback_data=f"my_c_detail:{terr.id}"),
            ]
        ]

        c_name = (terr.castle_name or terr.name or "Qal'a").upper()
        text = (
            f"↩️ **GARNIZONDAN ASKARLARNI QAYTARISH: {c_name}**\n\n"
            f"🏰 **Qal'adagi hozirgi garnizon:**\n"
            f"• 🛡️ Piyoda: **{g_inf:,}**\n"
            f"• 🏹 Kamonchi: **{g_arc:,}**\n"
            f"• 🐎 Otliq: **{g_cav:,}**\n"
            f"• 🗡️ Nayzachi: **{g_sp:,}**\n"
            f"🎯 Jami garnizon: **{tot_g:,}** askar\n\n"
            f"👥 **Sizning shaxsiy armiyangiz:** {u_army:,} askar\n\n"
            f"Qal'a garnizonidan shaxsiy armiyangizga qancha askarni qaytarib olmoqchisiz?"
        )
        try:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            clean_text = text.replace("*", "").replace("_", "")
            try:
                await target.edit_message_text(clean_text, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                if hasattr(target, "message") and target.message:
                    await target.message.reply_text(clean_text, reply_markup=InlineKeyboardMarkup(buttons))


async def def_withdraw_rf_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'a garnizonidan askarlarni qaytarib olish sahifasini ochish"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id
    await show_garrison_withdraw_menu(query, user_id, terr_id)


async def def_with_act_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Garnizondan tugma orqali askarlarni qaytarib olish amali"""
    query = update.callback_query
    parts = query.data.split(":")
    terr_id = int(parts[1])
    count_val = parts[2]
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        if count_val == "all":
            ok, msg, _ = await crud.withdraw_castle_reinforcements(
                session=session,
                user_id=user_id,
                territory_id=terr_id,
                withdraw_all=True
            )
        else:
            ok, msg, _ = await crud.withdraw_castle_reinforcements(
                session=session,
                user_id=user_id,
                territory_id=terr_id,
                count=int(count_val)
            )

    try:
        await query.answer(msg.replace("*", ""), show_alert=True)
    except Exception:
        pass
    await show_garrison_withdraw_menu(query, user_id, terr_id)


async def def_custom_with_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Garnizondan qo'lda son yozib qaytarib olish so'rovi"""
    query = update.callback_query
    await query.answer()
    terr_id = int(query.data.split(":")[1])
    context.user_data["awaiting_with_input"] = {"terr_id": terr_id}

    buttons = [
        [InlineKeyboardButton("🔙 Bekor Qilish", callback_data=f"def_withdraw_rf:{terr_id}")],
    ]
    text = (
        "✍️ **GARNIZONDAN QAYTARILADIGAN ASKARLAR SONI**\n\n"
        "Qal'adan qancha askarni shaxsiy armiyangizga qaytarib olmoqchisiz?\n"
        "Iltimos, sonni chatga xabar sifatida yozib yuboring:\n\n"
        "*(Masalan: `150` yoki `1000`)*"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


def register_map_handlers(app):
    app.add_handler(CommandHandler("map", map_command))
    app.add_handler(CommandHandler("territory", map_command))
    app.add_handler(CommandHandler(["castles", "mycastles"], my_castles_command))
    app.add_handler(CallbackQueryHandler(map_callback, pattern="^menu_map$"))
    app.add_handler(CallbackQueryHandler(my_castles_callback, pattern="^menu_castles$"))
    app.add_handler(CallbackQueryHandler(my_castle_detail_callback, pattern="^my_c_detail:"))
    app.add_handler(CallbackQueryHandler(collect_tax_callback, pattern="^collect_tax:"))
    app.add_handler(CallbackQueryHandler(upgrade_walls_callback, pattern="^upgrade_walls:"))
    app.add_handler(CallbackQueryHandler(upgrade_castle_callback, pattern="^upgrade_castle:"))
    app.add_handler(CallbackQueryHandler(def_withdraw_rf_callback, pattern="^def_withdraw_rf:"))
    app.add_handler(CallbackQueryHandler(def_with_act_callback, pattern="^def_with_act:"))
    app.add_handler(CallbackQueryHandler(def_custom_with_callback, pattern="^def_custom_with:"))
    app.add_handler(CallbackQueryHandler(view_territory_callback, pattern="^view_terr:"))
    app.add_handler(CallbackQueryHandler(terr_own_info_callback, pattern="^terr_own_info$"))
    app.add_handler(CallbackQueryHandler(def_station_dragon_callback, pattern="^def_station_dragon:"))
    app.add_handler(CallbackQueryHandler(def_recall_dragon_callback, pattern="^def_recall_dragon:"))
    app.add_handler(CallbackQueryHandler(terr_dragon_info_callback, pattern="^terr_dragon_info$"))
