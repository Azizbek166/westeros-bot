import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from sqlalchemy import select, desc
from core.anti_cheat import can_attack_target
from keyboards.menus import back_to_main_keyboard
from config import BASE_MARCH_MINUTES, escape_md


async def battle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/battle yoki /war buyrug'i"""
    user_id = update.effective_user.id
    await show_battle_hub(update, user_id, is_message=True)


async def battle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_battle callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_battle_hub(query, user_id, is_message=False)


async def show_battle_hub(target, user_id: int, is_message: bool):
    """Harbiy amaliyotlar markazi: joriy yurishlar va hisobotlar"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            msg = "❌ Iltimos, avval /start ni bosing."
            if is_message:
                await target.message.reply_text(msg)
            else:
                await target.edit_message_text(msg)
            return

        # Faol yurishlar
        marches_res = await session.execute(
            select(models.BattleMarch).where(
                models.BattleMarch.attacker_user_id == user.id,
                models.BattleMarch.status == "marching",
            )
        )
        active_marches = marches_res.scalars().all()

        march_text = ""
        if active_marches:
            for m in active_marches:
                terr = await session.get(models.Territory, m.target_territory_id)
                rem_sec = max(0, int((m.arrival_time - datetime.utcnow()).total_seconds()))
                t_name = terr.name if terr else "Qal'a"
                march_text += f"• 🎯 **{t_name}** sari yurish: {rem_sec // 60} daq {rem_sec % 60} soniya qoldi\n"
        else:
            march_text = "Hozirda faol harbiy yurishlar yo'q.\n"

        # Qal'amizga bo'layotgan dushman yurishlari (incoming attacks)
        incoming_text = ""
        if user.house_id:
            terr_ids_res = await session.execute(
                select(models.Territory.id).where(models.Territory.owner_house_id == user.house_id)
            )
            house_terr_ids = terr_ids_res.scalars().all()
            if house_terr_ids:
                inc_res = await session.execute(
                    select(models.BattleMarch).where(
                        models.BattleMarch.target_territory_id.in_(house_terr_ids),
                        models.BattleMarch.status == "marching",
                    )
                )
                inc_marches = inc_res.scalars().all()
                if inc_marches:
                    for im in inc_marches:
                        terr = await session.get(models.Territory, im.target_territory_id)
                        rem_sec = max(0, int((im.arrival_time - datetime.utcnow()).total_seconds()))
                        t_name = terr.name if terr else "Qal'a"
                        dr_icon = "🔥🐉 " if getattr(im, "has_dragon", False) else ""
                        incoming_text += f"• 🚨 {dr_icon}**{t_name}** ga hujum kelmoqda: {rem_sec // 60} daq {rem_sec % 60} soniya qoldi!\n"

        # So'nggi jang hisobotlari
        reports_res = await session.execute(
            select(models.BattleReport)
            .where(
                (models.BattleReport.attacker_user_id == user.id) | 
                (models.BattleReport.defender_user_id == user.house_id)
            )
            .order_by(desc(models.BattleReport.timestamp))
            .limit(3)
        )
        recent_reports = reports_res.scalars().all()

        reports_text = ""
        if recent_reports:
            for r in recent_reports:
                res_icon = "🏆 G'alaba" if (r.result == "attacker_won" and r.attacker_user_id == user.id) or (r.result == "defender_won" and r.defender_user_id == user.house_id) else "🛡️ Talofat"
                reports_text += f"• {res_icon}: {r.details[:70]}...\n"
        else:
            reports_text = "Janglar tarixi bo'sh.\n"

        defense_buttons = []
        if inc_marches:
            for im in inc_marches:
                terr = await session.get(models.Territory, im.target_territory_id)
                rem_sec = max(0, int((im.arrival_time - datetime.utcnow()).total_seconds()))
                t_name = terr.name if terr else "Qal'a"
                defense_buttons.append([
                    InlineKeyboardButton(f"🚨 {t_name} Himoyasiga O'tish! ({rem_sec // 60}d {rem_sec % 60}s)", callback_data=f"defend_siege:{im.id}")
                ])

        buttons = []
        if defense_buttons:
            buttons.extend(defense_buttons)

        is_lord = user.house and ((user.house.lord_user_id == user.telegram_id) or user.rank == "king")
        if is_lord:
            buttons.append([InlineKeyboardButton("📢 Xonadonga Safarbarlik Chaqiruvi (SOS)", callback_data="call_to_arms_broadcast")])

        buttons.append([InlineKeyboardButton("🗺️ Qal'a Tanlash (Xaritaga o'tish)", callback_data="menu_map")])
        buttons.append([InlineKeyboardButton("🔄 Vaqtni Yangilash", callback_data="menu_battle")])
        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        text = (
            f"🛡️ **HARBIY AMALIYOTLAR MARKAZI**\n\n"
            f"🚩 **BIZNING YURISHLAR:**\n{march_text}\n"
        )
        if incoming_text:
            text += f"🚨 **QAL'AMIZGA XAVF (HIMOYA TALAB):**\n{incoming_text}\n"

        text += (
            f"📜 **SO'NGGI JANG HISOBOTLARI:**\n{reports_text}\n"
            f"Yangi qal'ani zabt etish uchun xaritadan nishonni tanlang:"
        )

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def march_prep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hujumga tayyorgarlik, Drakarys taktikasi va armiya ulushini tanlash"""
    query = update.callback_query

    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            await query.answer("Hudud topilmadi.", show_alert=True)
            return

        is_allowed, err_msg = can_attack_target(user, terr)
        if not is_allowed:
            await query.answer(err_msg, show_alert=True)
            await query.edit_message_text(
                f"{err_msg}\n\nO'z xonadoningiz qal'asiga hujum qilib bo'lmaydi. Xaritadan dushman xonadon qal'asini tanlang:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗺️ Xaritaga Qaytish", callback_data="menu_map")]])
            )
            return

        total_army = (
            user.army.infantry
            + user.army.archers
            + user.army.cavalry
            + user.army.spearmen
            + user.army.special_troops
        )

        if total_army < 50:
            await query.answer("❌ Yurish uchun kamida 50 ta askar kerak!", show_alert=True)
            await query.edit_message_text(
                f"❌ **Yurish uchun kamida 50 ta askar kerak!**\n\nSizning armiyangiz: **{total_army}** ta askar.\nArmiya bo'limidan askar yollang:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚔️ Armiya (Askar Yollash)", callback_data="menu_army")],
                    [InlineKeyboardButton("🔙 Xaritaga Qaytish", callback_data="menu_map")]
                ])
            )
            return

        await query.answer()

        # Ajdar holatini tekshirish
        dragon = await crud.get_user_dragon(session, user.id)
        can_use_dragon = dragon and dragon.stage in ["baby", "adult"] and dragon.hunger >= 20

        buttons = []
        dragon_info = ""
        if can_use_dragon:
            dragon_info = (
                f"🐉 **AJDARINGIZ JANGGA TAYYOR!**\n"
                f"• Ismi: **{dragon.name}** ({dragon.stage.title()})\n"
                f"• Jangovar Kuch: **{dragon.power}**⚡ | Qorin: **{dragon.hunger}%**🍗\n\n"
                f"🔥 **DRAKARYS BUYRUG'INI TANLANG:**\n"
            )
            buttons.append([InlineKeyboardButton(f"🔥🏰 Drakarys: Devorlarni Eritish (-50% mudofaa)", callback_data=f"send_march:{terr.id}:100:walls")])
            buttons.append([InlineKeyboardButton(f"🔥🏹 Drakarys: Merganlarni Yoqish (Kamonchilarga)", callback_data=f"send_march:{terr.id}:100:ranged")])
            buttons.append([InlineKeyboardButton(f"🔥🐎 Drakarys: Old Qatorlarni Yoqish (Piyoda/Otliq)", callback_data=f"send_march:{terr.id}:100:frontline")])
            buttons.append([InlineKeyboardButton(f"🔥⚡ Drakarys: Yalpi Olovli Bo'ron (Umumiy)", callback_data=f"send_march:{terr.id}:100:balanced")])
            buttons.append([InlineKeyboardButton("⚔️ Ajdarsiz To'liq Armiya (100%)", callback_data=f"send_march:{terr.id}:100:none")])
            buttons.append([InlineKeyboardButton("🛡️ Ajdarsiz Yarim Armiya (50%)", callback_data=f"send_march:{terr.id}:50:none")])
        else:
            if dragon:
                dragon_info = f"⚠️ *Eslatma:* Ajdaringiz ({dragon.name}) och yoki hali tuxumda bo'lgani uchun jangga qo'shila olmaydi. Uni /dragons da ovqatlantiring.\n\n"
            buttons.append([InlineKeyboardButton("⚔️ To'liq Armiya Bilan Yurish (100%)", callback_data=f"send_march:{terr.id}:100:none")])
            buttons.append([InlineKeyboardButton("🛡️ Armiyaning Yarmi Bilan (50%)", callback_data=f"send_march:{terr.id}:50:none")])

        buttons.append([InlineKeyboardButton("🔙 Bekor Qilish", callback_data=f"view_terr:{terr.id}")])

        text = (
            f"⚔️ **YURISH TAYYORGARLIGI: {terr.name.upper()}**\n\n"
            f"🏰 Nishon: **{terr.castle_name}** ({terr.region})\n"
            f"⏱️ Yurish vaqti: **{BASE_MARCH_MINUTES} daqiqa** (Raqibga himoyalanish va yordam chaqirish uchun vaqt beriladi)\n"
            f"👥 Sizning armiyangiz: **{total_army:,}** askar\n\n"
            f"{dragon_info}"
            f"⚠️ Hujum boshlangach, 3 kunlik Tinchlik Qalqoningiz bekor qilinadi!\n\n"
            f"Hujum taktikasini tanlang:"
        )

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def send_march_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Armiyani manzil sari jo'natish"""
    query = update.callback_query

    parts = query.data.split(":")
    terr_id = int(parts[1])
    percent = int(parts[2])
    dragon_tactic = parts[3] if len(parts) > 3 else "none"
    has_dragon = (dragon_tactic != "none")
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            await query.answer("Ma'lumot topilmadi.", show_alert=True)
            return

        ratio = percent / 100.0
        infantry = int(user.army.infantry * ratio)
        archers = int(user.army.archers * ratio)
        cavalry = int(user.army.cavalry * ratio)
        spearmen = int(user.army.spearmen * ratio)
        special = int(user.army.special_troops * ratio)

        total_sent = infantry + archers + cavalry + spearmen + special
        if total_sent <= 0:
            await query.answer("❌ Askarlar soni yetarli emas.", show_alert=True)
            return

        await query.answer("🚩 Qo'shin yo'lga chiqdi!")

        # Qalqonni bekor qilish
        user.peace_shield_until = None

        march = await crud.create_battle_march(
            session=session,
            attacker_user_id=user.id,
            source_territory_id=terr.id,
            target_territory_id=terr.id,
            infantry=infantry,
            archers=archers,
            cavalry=cavalry,
            spearmen=spearmen,
            special_troops=special,
            character_id=user.characters[0].id if user.characters else None,
            duration_minutes=BASE_MARCH_MINUTES,
            has_dragon=has_dragon,
            dragon_tactic=dragon_tactic,
        )

        # Himoyachi xonadon Lordiga real-time ogohlantirish qarg'asi
        if terr.owner_house_id and terr.owner_house_id != user.house_id:
            target_house = await session.get(models.House, terr.owner_house_id)
            if target_house and target_house.lord_user_id and target_house.lord_user_id != user.telegram_id:
                dragon_text = " 🔥 va BAHAYBAT AJDAR 🐉" if has_dragon else ""
                def_buttons = [
                    [InlineKeyboardButton("⚔️ Harbiy Markaz (Himoyalanish)", callback_data="menu_battle")],
                    [InlineKeyboardButton("🛡️ Qal'aga Shoshilinch Askar Qo'shish", callback_data=f"def_rf_menu:{terr.id}")],
                    [InlineKeyboardButton("🐉 Ajdarni Mudofaaga Joylashtirish", callback_data=f"def_station_dragon:{terr.id}")],
                    [InlineKeyboardButton("🤝 Ittifoqchilarni Chaqirish (SOS)", callback_data=f"def_sos:{terr.id}")],
                ]
                try:
                    await context.bot.send_message(
                        chat_id=target_house.lord_user_id,
                        text=(
                            f"🚨 **QARG'A OGOHLANTIRISHI! QAL'AGA HUJUM BOSHLANDI!**\n\n"
                            f"🏰 **{user.house.emoji} {user.house.name}** armiyasi sizning **{terr.name} ({terr.castle_name})** qal'angiz sari shiddat bilan yurish boshladi!\n"
                            f"⚔️ Hujumchilar: taxminan **{total_sent:,}** askar{dragon_text}\n"
                            f"⏱️ Qamal boshlanishiga: **{BASE_MARCH_MINUTES} daqiqa** qoldi!\n\n"
                            f"🛡️ **MUDOFAA CHORALARI:**\n"
                            f"Zudlik bilan garnizonga o'z armiyangizdan askar safarbar qiling yoki ittifoqchi va vassallardan yordam so'rang!"
                        ),
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(def_buttons),
                    )
                except Exception:
                    pass

    dr_msg = "\n🐉 Ajdarga Drakarys buyrug'i berildi!" if has_dragon else ""
    text = (
        f"🚩 **QO'SHIN YURISHGA CHIQDI!**\n\n"
        f"🎯 Nishon: **{terr.name}** ({terr.castle_name})\n"
        f"⚔️ Safarbar etilgan askarlar: **{total_sent:,}** ta{dr_msg}\n"
        f"⏱️ Yetib borish vaqti: **{BASE_MARCH_MINUTES} daqiqa**\n\n"
        f"Qamal boshlangach, bot sizga avtomatik jang hisobotini yuboradi!\n"
        f"Harbiy holatni /battle orqali kuzatib boring."
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_main_keyboard())


async def def_rf_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Himoyachi uchun tezkor garnizon kuchaytirish menyusi"""
    query = update.callback_query
    await query.answer()

    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            await query.answer("Ma'lumot topilmadi.", show_alert=True)
            return

        total_army = (
            user.army.infantry + user.army.archers + user.army.cavalry + user.army.spearmen
        )

        buttons = [
            [InlineKeyboardButton("🛡️ 50 ta Askar Yuborish", callback_data=f"def_send_rf:{terr.id}:50")],
            [InlineKeyboardButton("🛡️ 100 ta Askar Yuborish", callback_data=f"def_send_rf:{terr.id}:100")],
            [InlineKeyboardButton("🛡️ 250 ta Askar Yuborish", callback_data=f"def_send_rf:{terr.id}:250")],
            [InlineKeyboardButton("🛡️ Barcha Askarlarni Safarbar Qilish", callback_data=f"def_send_rf:{terr.id}:all")],
            [InlineKeyboardButton("🔙 Qal'aga Qaytish", callback_data=f"view_terr:{terr.id}")],
        ]

        text = (
            f"🛡️ **QAL'ANI HIMOYA QILISH: {terr.name.upper()}**\n\n"
            f"🏰 Qal'a garnizoni hozir: {terr.garrison_infantry + terr.garrison_archers + terr.garrison_cavalry + terr.garrison_spearmen:,} askar\n"
            f"👥 Sizning shaxsiy armiyangiz: **{total_army:,}** askar\n\n"
            f"Dushman yetib kelguncha qal'a garnizoniga qo'shiladigan askar sonini tanlang:"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def def_send_rf_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'a garnizoniga shoshilinch yordam askarlarini kiritish"""
    query = update.callback_query

    parts = query.data.split(":")
    terr_id = int(parts[1])
    count_type = parts[2]
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            await query.answer("Ma'lumot topilmadi.", show_alert=True)
            return

        total_army = (
            user.army.infantry + user.army.archers + user.army.cavalry + user.army.spearmen
        )

        if total_army <= 0:
            await query.answer("❌ Sizda yuborish uchun bo'sh askar yo'q!", show_alert=True)
            return

        if count_type == "all":
            send_count = total_army
        else:
            send_count = min(int(count_type), total_army)

        ratio = send_count / float(total_army) if total_army > 0 else 0
        infantry = int(user.army.infantry * ratio)
        archers = int(user.army.archers * ratio)
        cavalry = int(user.army.cavalry * ratio)
        spearmen = int(user.army.spearmen * ratio)

        ok, msg = await crud.send_castle_reinforcements(
            session=session,
            user_id=user.id,
            target_territory_id=terr.id,
            infantry=infantry,
            archers=archers,
            cavalry=cavalry,
            spearmen=spearmen,
        )

    await query.answer(msg, show_alert=True)
    if ok:
        await show_battle_hub(query, user_id, is_message=False)


async def def_sos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadon va ittifoqchilarga shoshilinch SOS qarg'asi uchirish"""
    query = update.callback_query
    await query.answer("📡 Ittifoqchilar va xonadon a'zolariga SOS qarg'alari uchirildi!", show_alert=True)

    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            return

        # Xonadon a'zolariga yuborish
        members_res = await session.execute(
            select(models.User).where(
                models.User.house_id == user.house_id,
                models.User.telegram_id != user.telegram_id,
            ).limit(10)
        )
        members = members_res.scalars().all()

        sos_text = (
            f"🚨 **SHOSHILINCH SOS CHAQIRUV!**\n\n"
            f"🏰 Xonadonimizning **{terr.name} ({terr.castle_name})** qal'asiga dushman yurishi boshlandi!\n"
            f"⏱️ Qamal boshlanishiga sanoqli daqiqalar qoldi!\n\n"
            f"Lord {user.character_name} barcha ittifoqchi va vassallardan zudlik bilan yordam so'ramoqda!"
        )
        sos_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛡️ Qal'aga Yordam Yuborish", callback_data=f"def_rf_menu:{terr.id}")]
        ])

        for m in members:
            try:
                await context.bot.send_message(
                    chat_id=m.telegram_id,
                    text=sos_text,
                    parse_mode="Markdown",
                    reply_markup=sos_markup,
                )
            except Exception:
                pass


async def defend_siege_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'aga bo'layotgan faol qamalni ko'rish va himoyalanish choralarini ko'rish"""
    query = update.callback_query
    await query.answer()
    march_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        march = await session.get(models.BattleMarch, march_id)
        if not march or march.status != "marching":
            await query.answer("Qamal yakunlangan yoki bekor qilingan.", show_alert=True)
            await show_battle_hub(query, user_id, is_message=False)
            return

        terr = await session.get(models.Territory, march.target_territory_id)
        attacker = await session.get(models.User, march.attacker_user_id)
        att_house = await session.get(models.House, attacker.house_id) if (attacker and attacker.house_id) else None

        rem_sec = max(0, int((march.arrival_time - datetime.utcnow()).total_seconds()))
        att_name = attacker.characters[0].name if (attacker and attacker.characters) else (attacker.full_name if attacker else "Dushman")
        att_house_name = f"{att_house.emoji} {att_house.name}" if att_house else "Noma'lum"

        tot_enemy = march.infantry + march.archers + march.cavalry + march.spearmen + march.special_troops
        enemy_dragon_str = "🔥 Bor (Drakarys xavfi!)" if march.has_dragon else "Yo'q"

        # Qal'amiz garnizoni va mudofaasi
        garr_total = terr.garrison_infantry + terr.garrison_archers + terr.garrison_cavalry + terr.garrison_spearmen
        st_dragon = crud.get_stationed_dragon_info(terr)
        def_dragon_str = f"🔥 {st_dragon['dragon_name']} (Kuch: {st_dragon['power']})" if st_dragon else "Yo'q"

        buttons = [
            [InlineKeyboardButton("🛡️ Shoshilinch Askar Joylashtirish", callback_data=f"def_rf_menu:{terr.id}")],
            [InlineKeyboardButton("🐉 Ajdarni Mudofaaga Joylashtirish", callback_data=f"def_station_dragon:{terr.id}")],
            [InlineKeyboardButton("🤝 Xonadonga SOS Chaqiruvi", callback_data=f"def_sos:{terr.id}")],
            [InlineKeyboardButton("🔄 Qamal Holatini Yangilash", callback_data=f"defend_siege:{march.id}")],
            [InlineKeyboardButton("🔙 Harbiy Markazga Qaytish", callback_data="menu_battle")],
        ]

        text = (
            f"🚨 **FAOL QAMAL VA QAL'A HIMOYASI!**\n\n"
            f"🏰 Qal'a: **{terr.name} ({terr.castle_name})**\n"
            f"⏱️ Dushman yetib kelishiga: **{rem_sec // 60} daqiqa {rem_sec % 60} soniya** qoldi!\n\n"
            f"⚔️ **DUSHMAN QO'SHINI:**\n"
            f"• Qo'mondon: **{escape_md(att_name)}** ({escape_md(att_house_name)})\n"
            f"• Hujumchilar: taxminan **{tot_enemy:,}** askar\n"
            f"• Ajdar Hujumi: **{enemy_dragon_str}**\n\n"
            f"🛡️ **QAL'AMIZ MUDOFAASI:**\n"
            f"• Qal'a Devori: **{terr.defense}** ball\n"
            f"• Garnizon: **{garr_total:,}** askar (🛡️{terr.garrison_infantry} | 🏹{terr.garrison_archers} | 🐎{terr.garrison_cavalry} | 🗡️{terr.garrison_spearmen})\n"
            f"• Mudofaadagi Ajdar: **{def_dragon_str}**\n\n"
            f"Qal'a dushmanga boy berilmasligi uchun zudlik bilan himoyani kuchaytiring!"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


def register_battle_handlers(app):
    app.add_handler(CommandHandler("battle", battle_command))
    app.add_handler(CommandHandler("war", battle_command))
    app.add_handler(CallbackQueryHandler(battle_callback, pattern="^menu_battle$"))
    app.add_handler(CallbackQueryHandler(march_prep_callback, pattern="^march_prep:"))
    app.add_handler(CallbackQueryHandler(send_march_callback, pattern="^send_march:"))
    app.add_handler(CallbackQueryHandler(def_rf_menu_callback, pattern="^def_rf_menu:"))
    app.add_handler(CallbackQueryHandler(def_send_rf_callback, pattern="^def_send_rf:"))
    app.add_handler(CallbackQueryHandler(def_sos_callback, pattern="^def_sos:"))
    app.add_handler(CallbackQueryHandler(defend_siege_callback, pattern="^defend_siege:"))
