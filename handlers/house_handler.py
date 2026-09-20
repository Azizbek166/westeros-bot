import html
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from keyboards.menus import back_to_main_keyboard
from config import escape_md, RANKS
from sqlalchemy import select, func


async def house_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/house buyrug'i"""
    user_id = update.effective_user.id
    await show_house(update, user_id, is_message=True)


async def house_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_house callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_house(query, user_id, is_message=False)


async def show_house(target, user_id: int, is_message: bool):
    """Xonadon ma'lumotlarini chiqarish"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            msg = "❌ Siz hali xonadon tanlamagansiz. /start ni bosing."
            if is_message:
                await target.message.reply_text(msg)
            else:
                await target.edit_message_text(msg)
            return

        house = user.house
        members_count = await crud.get_house_members_count(session, house.id)
        territories = await crud.get_house_territories(session, house.id)

        # Xonadon Lordini aniqlash
        lord_user = None
        if house.lord_user_id:
            lord_user = await crud.get_user_by_telegram_id(session, house.lord_user_id)
        lord_name = lord_user.full_name if lord_user else "Tayinlanmagan"

        terr_names = ", ".join([t.name for t in territories]) if territories else "Hozircha yo'q"

        buttons = [
            [InlineKeyboardButton("👥 Xonadon A'zolari va Lavozimlar", callback_data="house_members")],
            [InlineKeyboardButton("💰 G'aznaga Ehson Qilish", callback_data="house_donate_menu"),
             InlineKeyboardButton("🏆 Eng Saxiylar", callback_data="house_top_donors")],
            [InlineKeyboardButton("🗳️ Lord Saylovi (Ovoz berish)", callback_data="house_election")],
            [InlineKeyboardButton("🏰 Egallangan Qal'alarimiz", callback_data="menu_castles")],
        ]
        is_lord = (house.lord_user_id == user.telegram_id) or user.rank == "king"
        if is_lord:
            buttons.append([InlineKeyboardButton("🏛️ Xonadon G'aznasini Boshqarish (Lord)", callback_data="house_treasury_manage")])
            buttons.append([InlineKeyboardButton("📢 Harbiy Safarbarlik (Askar So'rash)", callback_data="call_to_arms_broadcast")])
            buttons.append([InlineKeyboardButton("🎖️ Lavozim Tayinlash (Lord)", callback_data="house_rank_assign_menu")])
            buttons.append([InlineKeyboardButton("🚫 Lordlikdan Voz Kechish (Iste'fo)", callback_data="house_abdicate_prompt")])
        elif house.lord_user_id:
            buttons.append([InlineKeyboardButton("🛡️ Lordga Askar Berish (Safarbarlik)", callback_data="troop_donation_menu")])

        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        text = (
            f"🏰 **XONADON MA'LUMOTLARI**\n\n"
            f"{house.emoji} **{house.name}**\n"
            f"📍 Mintaqa: **{house.region}**\n"
            f"👑 Xonadon Lordi: **{escape_md(lord_name)}**\n"
            f"🎖️ Sizning Lavozimingiz: **{RANKS.get(user.rank, {}).get('name', user.rank.title())}**\n\n"
            f"📜 Shior: _{escape_md(house.description)}_\n\n"
            f"🏛️ **Xonadon Umumiy G'aznasi:**\n"
            f"• 🪙 Oltin: **{house.gold:,}** | 🌾 Oziq: **{house.food:,}** | ⛓️ Temir: **{house.iron:,}**\n\n"
            f"🔥 Maxsus Qo'shin: **{house.special_troop_name}**\n"
            f"🛡️ Mudofaa Bonusi: **+{int((house.defense_bonus - 1.0) * 100)}%**\n"
            f"🏆 Xonadon Prestige: **{house.prestige:,}**\n"
            f"👥 Jami A'zolar: **{members_count}** ta\n\n"
            f"🗺️ Nazoratdagi Hududlar ({len(territories)} ta):\n"
            f"_{escape_md(terr_names)}_"
        )

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def house_members_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadon a'zolari va ularning lavozimlarini ko'rsatish"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        members = await crud.get_house_members_with_characters(session, user.house.id)

        text = f"👥 **{user.house.emoji} {user.house.name} — A'ZOLAR VA LAVOZIMLAR:**\n\n"
        for m in members:
            rank_info = RANKS.get(m.rank, {}).get("name", m.rank.title())
            char_name = m.characters[0].name if m.characters else "Ritsar"
            text += f"• **{escape_md(char_name)}** ({escape_md(m.full_name)})\n  └ Lavozim: {rank_info} | {m.level}-daraja\n"

        buttons = [
            [InlineKeyboardButton("🗳️ Lord Saylovi", callback_data="house_election")],
            [InlineKeyboardButton("🔙 Xonadonga Qaytish", callback_data="menu_house")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def house_rank_assign_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lord a'zolarga lavozim tayinlashi uchun a'zolar ro'yxati"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or user.rank != "king":
            await query.answer("❌ Faqat Xonadon Lordi lavozim tayinlashi mumkin!", show_alert=True)
            return

        members = await crud.get_house_members_with_characters(session, user.house.id)
        buttons = []
        for m in members:
            if m.id != user.id:
                char_name = m.characters[0].name if m.characters else m.full_name
                buttons.append([InlineKeyboardButton(f"🎖️ {char_name} ({m.rank})", callback_data=f"hrank_pick:{m.id}")])

        buttons.append([InlineKeyboardButton("🔙 Xonadonga Qaytish", callback_data="menu_house")])

        text = (
            f"👑 **LAVOZIM TAYINLASH (Lord Huquqi)**\n\n"
            f"Lavozimini o'zgartirmoqchi bo'lgan xonadon a'zosini tanlang:"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def house_pick_target_rank_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan a'zoga yangi lavozim tanlash"""
    query = update.callback_query
    await query.answer()

    target_user_id = int(query.data.split(":")[1])
    context.user_data["rank_target_user_id"] = target_user_id

    buttons = [
        [InlineKeyboardButton("⚔️ Harbiy Qo'mondon (Commander)", callback_data="hset_rank:commander")],
        [InlineKeyboardButton("🛡️ Ritsar (Knight)", callback_data="hset_rank:knight")],
        [InlineKeyboardButton("🏹 Kapitan (Captain)", callback_data="hset_rank:captain")],
        [InlineKeyboardButton("👤 Oddiy A'zo (Member)", callback_data="hset_rank:member")],
        [InlineKeyboardButton("🔙 Bekor Qilish", callback_data="menu_house")],
    ]

    text = "Qaysi lavozimni berishni xohlaysiz?"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def house_set_rank_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lavozimni tasdiqlash va saqlash"""
    query = update.callback_query
    await query.answer()

    new_rank = query.data.split(":")[1]
    target_user_id = context.user_data.get("rank_target_user_id")

    if not target_user_id:
        await query.answer("Xatolik: a'zo topilmadi.", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        await crud.set_user_rank(session, target_user_id, new_rank)
        target_user = await crud.get_user_any(session, target_user_id)
        name = target_user.full_name if target_user else "A'zo"

    rank_name = RANKS.get(new_rank, {}).get("name", new_rank)
    await query.answer(f"✅ {name} muvaffaqiyatli {rank_name} lavozimiga tayinlandi!", show_alert=True)
    await show_house(query, query.from_user.id, is_message=False)


async def house_election_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lord Saylovi: nomzodlar ro'yxati, ovozlar statistikasi va ovoz berish"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        stats = await crud.get_house_election_stats(session, user.house.id, user.id)
        house = stats["house"]
        total_m = stats["total_members"]
        needed = stats["needed_votes"]
        candidates = stats["candidates"]
        my_vote_id = stats["my_vote_cand_id"]
        current_lord = stats["current_lord"]
        remaining_days = stats.get("remaining_days", 10)
        term_expired = stats.get("term_expired", False)

    if current_lord:
        term_status = "⌛ *10 kunlik vakolat tugagan! Yangi Lord saylanishi kerak.*" if term_expired else f"⏳ Vakolat muddati: **{remaining_days} kun** qoldi (har 10 kunda yangi saylov)"
        lord_name = f"👑 **{escape_md(current_lord.full_name)}**\n   └ {term_status}"
    else:
        lord_name = "❌ *Xonadonda hozircha Lord yo'q (Vakant)*"

    cand_lines = []
    for c in candidates:
        star = "👑 " if c["is_lord"] else "👤 "
        voted_tag = " 👈 [Sizning ovozingiz]" if c["id"] == my_vote_id else ""
        prog_bar = "█" * c["votes"] + "░" * max(0, needed - c["votes"])
        cand_lines.append(
            f"{star}**{escape_md(c['name'])}** ({escape_md(c['full_name'])})\n"
            f"   └ Ovozlar: `[{prog_bar}]` **{c['votes']}** ta ({c['pct']}%) {voted_tag}"
        )
    cand_text = "\n\n".join(cand_lines) if cand_lines else "Nomzodlar ro'yxati bo'sh."

    buttons = []
    if not current_lord:
        buttons.append([InlineKeyboardButton("👑 Xonadon Lordligini Da'vo Qilish", callback_data="claim_house_lord")])

    for c in candidates:
        btn_label = f"🗳️ {c['name'][:18]} ga ovoz" if c["id"] != my_vote_id else f"✅ {c['name'][:18]} (Ovozingiz)"
        buttons.append([InlineKeyboardButton(btn_label, callback_data=f"hvote:{c['id']}")])

    buttons.append([InlineKeyboardButton("🔄 Yangilash", callback_data="house_election")])
    buttons.append([InlineKeyboardButton("🔙 Xonadonga Qaytish", callback_data="menu_house")])

    text = (
        f"🗳️ **{house.emoji} {house.name.upper()} — XONADON LORDI SAYLOVI**\n\n"
        f"Hozirgi Lord:\n{lord_name}\n\n"
        f"Xonadon A'zolari: **{total_m}** ta\n"
        f"G'alaba uchun zarur: **{needed}** ta ovoz (50%+)\n\n"
        f"📊 **NOMZODLAR VA OVOZLAR NATIJASI:**\n\n"
        f"{cand_text}\n\n"
        f"ℹ️ *Eslatma: Har bir Lordning vakolati 10 kun. 10 kundan so'ng yangi saylov avtomatik boshlanadi. "
        f"50% dan ortiq ovoz to'plagan nomzod darhol xonadon Lordi etib tayinlanadi!*"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def claim_house_lord_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bo'sh xonadon Lordligini qabul qilish"""
    query = update.callback_query
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user or not user.house_id:
            await query.answer("❌ Xonadon topilmadi.", show_alert=True)
            return
        ok, msg = await crud.claim_vacant_house_lord(session, user.id)

    await query.answer(msg, show_alert=True)
    await house_election_callback(update, context)


async def house_abdicate_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lordlikdan voz kechish tasdig'ini so'rash"""
    query = update.callback_query
    await query.answer()

    buttons = [
        [InlineKeyboardButton("✅ Ha, Lordlikdan Voz Kechaman", callback_data="house_abdicate_confirm")],
        [InlineKeyboardButton("❌ Bekor Qilish", callback_data="menu_house")],
    ]
    text = (
        "⚠️ **OGOHLANTIRISH!**\n\n"
        "Rostdan ham xonadon Lordligidan voz kechmoqchimisiz?\n\n"
        "• Lordlik lavozimingiz bekor qilinadi va oddiy a'zo (Member) maqomiga o'tasiz.\n"
        "• Xonadonda yangi Lord saylovi boshlanadi.\n"
        "• Ushbu amalni ortga qaytarib bo'lmaydi!"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def house_abdicate_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lordlikdan voz kechishni amalga oshirish"""
    query = update.callback_query
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Foydalanuvchi topilmadi.", show_alert=True)
            return
        ok, msg = await crud.abdicate_house_lord(session, user.id)

    await query.answer(msg, show_alert=True)
    await show_house(query, user_id, is_message=False)


async def house_leave_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadondan chiqishni taqiqlash"""
    query = update.callback_query
    await query.answer("❌ Westeros qonunlariga ko'ra, xonadonga berilgan qasamyod umrboddir! Xonadondan chiqish yoki uni almashtirish taqiqlanadi.", show_alert=True)
    await show_house(query, query.from_user.id, is_message=False)


async def house_leave_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadondan chiqishni taqiqlash"""
    query = update.callback_query
    await query.answer("❌ Westeros qonunlariga ko'ra, xonadonga berilgan qasamyod umrboddir! Xonadondan chiqish yoki uni almashtirish taqiqlanadi.", show_alert=True)
    await show_house(query, query.from_user.id, is_message=False)


async def house_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ovoz berish amali"""
    query = update.callback_query
    candidate_user_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            await query.answer("❌ Xonadon a'zosi emassiz.", show_alert=True)
            return

        outcome = await crud.cast_house_vote(session, user.house.id, user.id, candidate_user_id)

    await query.answer(outcome, show_alert=True)
    await house_election_callback(update, context)


async def call_to_arms_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lord tomonidan barcha xonadon a'zolariga harbiy safarbarlik qarg'asi uchirish"""
    query = update.callback_query
    await query.answer("📢 Barcha xonadon a'zolariga safarbarlik qarg'alari uchirildi!", show_alert=True)
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        is_lord = (user.house.lord_user_id == user.telegram_id) or user.rank == "king"
        if not is_lord:
            await query.answer("❌ Faqat Xonadon Lordi umumiy harbiy safarbarlik e'lon qila oladi!", show_alert=True)
            return

        members_res = await session.execute(
            select(models.User).where(
                models.User.house_id == user.house.id,
                models.User.telegram_id != user.telegram_id,
            ).limit(20)
        )
        members = members_res.scalars().all()

        lord_title = user.characters[0].name if user.characters else user.full_name
        broadcast_text = (
            f"📢⚔️ **LORD CHAQRUVI! UMUMIY HARBIY SAFARBARLIK!**\n\n"
            f"🏰 **{user.house.emoji} {user.house.name}** Lordi **{escape_md(lord_title)}** barcha xonadon ritsarlari va a'zolarini qurol ko'tarishga chaqirmoqda!\n\n"
            f"Buyuk jang va zafarlar uchun Lord armiyasiga askarlar safarbar qiling! "
            f"Har bir askar yordami sizga **Prestige (Nufuz)** va xonadon ichida yuksak mavqe olib keladi!"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛡️ Lordga Askar Safarbar Qilish", callback_data="troop_donation_menu")],
            [InlineKeyboardButton("🏰 Xonadonga O'tish", callback_data="menu_house")],
        ])

        for m in members:
            try:
                await context.bot.send_message(
                    chat_id=m.telegram_id,
                    text=broadcast_text,
                    parse_mode="Markdown",
                    reply_markup=markup,
                )
            except Exception:
                pass

        # Xonadon guruhiga ham harbiy safarbarlik signali
        from core.notifier import notify_house_group
        grp_bcast_text = (
            f"📢⚔️ <b>LORDNING HARBIY SAFARBARLIK CHAQIRIG'I!</b>\n\n"
            f"🏰 <b>{html.escape(user.house.emoji)} {html.escape(user.house.name)}</b> Lordi <b>{html.escape(lord_title)}</b> barcha a'zolarni qurol ko'tarishga chaqirmoqda!\n\n"
            f"Buyuk g'alabalar va qal'alarni zabt etish uchun Lord armiyasiga askar safarbar qiling!"
        )
        asyncio.create_task(notify_house_group(context.application, user.house.id, grp_bcast_text, parse_mode="HTML"))


async def troop_donation_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lord armiyasiga askar yuborish menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house or not user.house.lord_user_id:
            await query.answer("❌ Xonadonda saylangan Lord yo'q.", show_alert=True)
            return

        lord = await crud.get_user_by_telegram_id(session, user.house.lord_user_id)
        if not lord:
            await query.answer("❌ Lord topilmadi.", show_alert=True)
            return

        if user.id == lord.id:
            await query.answer("⚠️ Siz o'zingiz xonadon Lordisiz! A'zolardan askar so'rash uchun Safarbarlik tugmasini bosing.", show_alert=True)
            return

        total_army = (user.army.infantry + user.army.archers + user.army.cavalry + user.army.spearmen) if user.army else 0

        lord_name = lord.characters[0].name if lord.characters else lord.full_name
        buttons = [
            [InlineKeyboardButton("🛡️ 20 ta Piyoda", callback_data="donate_troop:infantry:20"),
             InlineKeyboardButton("🏹 20 ta Kamonchi", callback_data="donate_troop:archers:20")],
            [InlineKeyboardButton("🐎 10 ta Otliq", callback_data="donate_troop:cavalry:10"),
             InlineKeyboardButton("🗡️ 10 ta Nayzachi", callback_data="donate_troop:spearmen:10")],
            [InlineKeyboardButton("⚔️ Aralash Qo'shin (50 ta askar)", callback_data="donate_troop:mixed:50")],
            [InlineKeyboardButton("🔙 Xonadonga Qaytish", callback_data="menu_house")],
        ]

        text = (
            f"🛡️ **LORD ARMISIGA ASKAR SAFARBAR QILISH**\n\n"
            f"👑 Xonadon Lordi: **{escape_md(lord_name)}**\n"
            f"👥 Sizning shaxsiy armiyangiz: **{total_army:,}** askar\n"
            f"• 🛡️ Piyoda: {user.army.infantry} | 🏹 Kamonchi: {user.army.archers}\n"
            f"• 🐎 Otliq: {user.army.cavalry} | 🗡️ Nayzachi: {user.army.spearmen}\n\n"
            f"Lordning harbiy yurishlarida ishtirok etish uchun uning qo'shiniga askarlaringizni yuboring. "
            f"Har bir yordam uchun sizga **Prestige** beriladi!"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def troop_donation_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lordga askar o'tkazish amali"""
    query = update.callback_query
    parts = query.data.split(":")
    ttype = parts[1]
    count = int(parts[2])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house or not user.house.lord_user_id:
            await query.answer("❌ Xonadonda Lord yo'q.", show_alert=True)
            return

        lord = await crud.get_user_by_telegram_id(session, user.house.lord_user_id)
        if not lord:
            await query.answer("❌ Lord topilmadi.", show_alert=True)
            return

        inf = count if ttype == "infantry" else (15 if ttype == "mixed" else 0)
        arc = count if ttype == "archers" else (15 if ttype == "mixed" else 0)
        cav = count if ttype == "cavalry" else (10 if ttype == "mixed" else 0)
        spm = count if ttype == "spearmen" else (10 if ttype == "mixed" else 0)

        ok, msg = await crud.transfer_troops_to_lord(
            session=session,
            sender_user_id=user.id,
            lord_user_id=lord.id,
            infantry=inf,
            archers=arc,
            cavalry=cav,
            spearmen=spm,
        )

    await query.answer(msg, show_alert=True)
    if ok:
        await troop_donation_menu_callback(update, context)


async def house_donate_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadon g'aznasiga ehson menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        house = user.house
        text = (
            f"💰 **{house.emoji} {house.name} G'AZNASIGA EHSON**\n\n"
            f"Shaxsiy boyliklaringizni umumiy xazinaga topshirib, xonadoningiz qudratini oshiring!\n"
            f"*(Ehson qilishda kunlik cheklov yo'q)*\n\n"
            f"🏛️ **Hozirgi xonadon g'aznasi:**\n"
            f"• 🪙 Oltin: {house.gold:,}\n"
            f"• 🌾 Oziq-ovqat: {house.food:,}\n"
            f"• ⛓️ Temir: {house.iron:,}\n\n"
            f"🎒 **Sizning zaxirangiz:**\n"
            f"🪙 {user.gold:,} | 🌾 {user.food:,} | ⛓️ {user.iron:,}\n\n"
            f"Ehson miqdorini tanlang:"
        )

        buttons = [
            [
                InlineKeyboardButton("🪙 500", callback_data="hdonate:gold:500"),
                InlineKeyboardButton("🪙 2,500", callback_data="hdonate:gold:2500"),
                InlineKeyboardButton("🪙 10k", callback_data="hdonate:gold:10000"),
            ],
            [
                InlineKeyboardButton("🌾 1,000", callback_data="hdonate:food:1000"),
                InlineKeyboardButton("🌾 5,000", callback_data="hdonate:food:5000"),
                InlineKeyboardButton("🌾 20k", callback_data="hdonate:food:20000"),
            ],
            [
                InlineKeyboardButton("⛓️ 500", callback_data="hdonate:iron:500"),
                InlineKeyboardButton("⛓️ 2,500", callback_data="hdonate:iron:2500"),
                InlineKeyboardButton("⛓️ 10k", callback_data="hdonate:iron:10000"),
            ],
            [InlineKeyboardButton("✨ Katta Karvon (1k🪙 + 2k🌾 + 1k⛓️)", callback_data="hdonate:combo:1")],
            [
                InlineKeyboardButton("✍️ 🪙 Oltin (Qo'lda)", callback_data="h_custom_donate:gold"),
                InlineKeyboardButton("✍️ 🌾 Oziq (Qo'lda)", callback_data="h_custom_donate:food"),
                InlineKeyboardButton("✍️ ⛓️ Temir (Qo'lda)", callback_data="h_custom_donate:iron"),
            ],
            [InlineKeyboardButton("🔙 Xonadonga Qaytish", callback_data="menu_house")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def house_custom_donate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadon g'aznasiga qo'lda kiritilgan miqdorda ehson qilish so'rovi"""
    query = update.callback_query
    await query.answer()
    res_type = query.data.split(":")[1]
    context.user_data["awaiting_house_donate_input"] = {"res_type": res_type}

    res_names = {
        "gold": "🪙 Oltin",
        "food": "🌾 Oziq-ovqat",
        "iron": "⛓️ Temir",
    }
    r_name = res_names.get(res_type, res_type)

    buttons = [
        [InlineKeyboardButton("🔙 Bekor Qilish", callback_data="house_donate_menu")],
    ]
    text = (
        f"✍️ **XONADON G'AZNASIGA EHSON: {r_name.upper()}**\n\n"
        f"G'aznaga qancha **{r_name}** ehson qilmoqchisiz?\n"
        f"Iltimos, miqdorni xabar sifatida yozib yuboring:\n\n"
        f"*(Masalan: `5000`, `25000` yoki borini ehson qilish uchun `all` deb yozing)*"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def house_donate_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ehsonni amalga oshirish"""
    query = update.callback_query
    user_id = query.from_user.id
    parts = query.data.split(":")
    dtype = parts[1]

    gold = 0
    food = 0
    iron = 0
    if dtype == "gold":
        gold = int(parts[2])
    elif dtype == "food":
        food = int(parts[2])
    elif dtype == "iron":
        iron = int(parts[2])
    elif dtype == "combo":
        gold = 1000
        food = 2000
        iron = 1000

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house_id:
            await query.answer("❌ Siz hali xonadonga a'zo emassiz.", show_alert=True)
            return

        ok, msg = await crud.donate_to_house_treasury(
            session=session,
            user_id=user.id,
            gold=gold,
            food=food,
            iron=iron
        )

    await query.answer(msg, show_alert=True)
    if ok:
        await house_donate_menu_callback(update, context)


async def house_top_donors_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadonning eng saxiy lordlari ro'yxati"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        top_donors = await crud.get_top_house_contributors(session, user.house.id, limit=5)
        text = f"🏆 **{user.house.emoji} {user.house.name} — ENG SAXIY LORDLAR:**\n\n"

        if not top_donors:
            text += "Hozircha hech kim g'aznaga ehson qilmagan.\nBirinchi bo'lib hissa qo'shing!"
        else:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, (name, rank, total) in enumerate(top_donors):
                m = medals[i] if i < len(medals) else "•"
                rank_title = RANKS.get(rank, {}).get("name", rank)
                text += f"{m} **{escape_md(name)}** ({rank_title})\n  └ Jami hissa: **{total:,}** resurs\n"

        buttons = [
            [InlineKeyboardButton("💰 Ehson Qilish", callback_data="house_donate_menu")],
            [InlineKeyboardButton("🔙 Xonadonga Qaytish", callback_data="menu_house")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def house_treasury_manage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lord uchun xonadon g'aznasini tasarruf etish boshqaruvi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        house = user.house
        is_lord = (house.lord_user_id == user.telegram_id) or user.rank == "king"
        if not is_lord:
            await query.answer("❌ Faqat Xonadon Lordi g'aznadan foydalanishi mumkin!", show_alert=True)
            return

        members_count = await crud.get_house_members_count(session, house.id)

        text = (
            f"🏛️ **XONADON G'AZNASI BOSHQARUVI — {house.emoji} {house.name}**\n\n"
            f"👑 Xonadon Lordi sifatida siz umumiy g'aznani xonadon manfaati uchun tasarruf etishingiz mumkin.\n\n"
            f"💰 **G'AZNA ZAXIRASI:**\n"
            f"• 🪙 Oltin: **{house.gold:,}**\n"
            f"• 🌾 Oziq-ovqat: **{house.food:,}**\n"
            f"• ⛓️ Temir: **{house.iron:,}**\n\n"
            f"👥 **Xonadon a'zolari:** {members_count} nafar\n\n"
            f"Kerakli amaliyotni tanlang:"
        )

        context.user_data.pop("awaiting_house_with_input", None)
        buttons = [
            [
                InlineKeyboardButton("✍️ 🪙 Oltin Yechish (Qo'lda)", callback_data="h_custom_with:gold"),
            ],
            [
                InlineKeyboardButton("✍️ 🌾 Oziq Yechish (Qo'lda)", callback_data="h_custom_with:food"),
                InlineKeyboardButton("✍️ ⛓️ Temir Yechish (Qo'lda)", callback_data="h_custom_with:iron"),
            ],
            [
                InlineKeyboardButton("🪙 -1,000 Oltin", callback_data="h_with:gold:1000"),
                InlineKeyboardButton("🪙 -2,500 Oltin", callback_data="h_with:gold:2500"),
            ],
            [
                InlineKeyboardButton("🌾 -2,000 Oziq", callback_data="h_with:food:2000"),
                InlineKeyboardButton("⛓️ -1,000 Temir", callback_data="h_with:iron:1000"),
            ],
            [
                InlineKeyboardButton("🎁 Har Bir A'zoga +500🪙 Ulashish", callback_data="h_dist:gold:500"),
            ],
            [
                InlineKeyboardButton("🎁 Har Bir A'zoga +1,000🌾 Ulashish", callback_data="h_dist:food:1000"),
            ],
            [
                InlineKeyboardButton("🔙 Xonadonga Qaytish", callback_data="menu_house"),
            ]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def house_treasury_custom_with_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lord uchun xonadon g'aznasidan qo'lda yozib resurs yechib olish so'rovi"""
    query = update.callback_query
    await query.answer()
    res_type = query.data.split(":")[1]
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            await query.answer("Xonadon topilmadi.", show_alert=True)
            return

        house = user.house
        is_lord = (house.lord_user_id == user.telegram_id) or user.rank == "king"
        if not is_lord:
            await query.answer("❌ Faqat Xonadon Lordi g'aznadan foydalanishi mumkin!", show_alert=True)
            return

        avail = getattr(house, res_type, 0) or 0

    res_names = {"gold": "🪙 Oltin", "food": "🌾 Oziq-ovqat", "iron": "⛓️ Temir"}
    r_name = res_names.get(res_type, res_type.capitalize())

    context.user_data["awaiting_house_with_input"] = {"res_type": res_type}

    text = (
        f"✍️ **XONADON G'AZNASIDAN {r_name.upper()} YECHISH**\n\n"
        f"G'aznada mavjud zaxira: **{avail:,}** {r_name}\n\n"
        f"Shaxsiy hisobingizga qancha {r_name} yechib olmoqchisiz?\n"
        f"Iltimos, miqdorni chatga xabar qilib yozing:\n\n"
        f"*(Masalan: `5000` yoki butun zaxirani yechish uchun `all`)*"
    )
    buttons = [
        [InlineKeyboardButton("🔙 Bekor Qilish", callback_data="house_treasury_manage")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def house_treasury_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """G'aznadan Lord shaxsiy hisobiga mablag' yechish"""
    query = update.callback_query
    parts = query.data.split(":")
    res_type = parts[1]
    amount = int(parts[2])
    user_id = query.from_user.id

    gold = amount if res_type == "gold" else 0
    food = amount if res_type == "food" else 0
    iron = amount if res_type == "iron" else 0

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house_id:
            await query.answer("Xonadon topilmadi.", show_alert=True)
            return

        ok, msg = await crud.withdraw_house_treasury(
            session=session,
            house_id=user.house_id,
            user_id=user.id,
            gold=gold,
            food=food,
            iron=iron,
        )

    await query.answer(msg, show_alert=True)
    await house_treasury_manage_callback(update, context)


async def house_treasury_distribute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """G'aznadan barcha a'zolarga ulashish"""
    query = update.callback_query
    parts = query.data.split(":")
    res_type = parts[1]
    amount = int(parts[2])
    user_id = query.from_user.id

    gold = amount if res_type == "gold" else 0
    food = amount if res_type == "food" else 0
    iron = amount if res_type == "iron" else 0

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house_id:
            await query.answer("Xonadon topilmadi.", show_alert=True)
            return

        ok, msg, count = await crud.distribute_house_treasury(
            session=session,
            house_id=user.house_id,
            user_id=user.id,
            gold=gold,
            food=food,
            iron=iron,
        )

    await query.answer(msg, show_alert=True)
    await house_treasury_manage_callback(update, context)


async def set_house_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruhni xonadonga bog'lash: faqat guruhda xonadon Lordi yoki Admin bera oladi"""
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ Ushbu buyruq faqat xonadoningizning Telegram guruhida ishlatiladi!")
        return

    from config import ADMIN_IDS, OWNER_ID
    is_admin = (user.id in ADMIN_IDS) or (user.id == OWNER_ID)

    async with AsyncSessionLocal() as session:
        db_user = await crud.get_user_with_relations(session, user.id)
        if not db_user or not db_user.house:
            await update.message.reply_text("❌ Siz hali biron-bir xonadonga a'zo emassiz!")
            return

        house = db_user.house
        is_lord = (house.lord_user_id == user.id) or (db_user.rank == "king") or is_admin

        if not is_lord:
            await update.message.reply_text("❌ Guruhni bog'lash huquqi faqat Xonadon Lordi yoki Bot Administratoriga berilgan!")
            return

        # Bog'lash
        await crud.set_house_group_chat(session, house.id, chat.id, chat.title or "Xonadon Shtabi")

    bot_user = await context.bot.get_me()
    bot_link = f"https://t.me/{bot_user.username}"

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏰 Botga Kirish / Safarbarlik", url=bot_link)],
    ])

    text = (
        f"🏰 <b>{html.escape(house.emoji)} {html.escape(house.name)} RASMIY QARORGOHI TAYINLANDI!</b>\n\n"
        f"Ushbu Telegram guruhi (<b>{html.escape(chat.title or 'Guruh')}</b>) endi {html.escape(house.name)} xonadonining rasmiy harbiy shtabi hisoblanadi.\n\n"
        f"🔔 <b>GURUHGA BORUVCHI AVTOMATIK OGOHLANTIRISHLAR:</b>\n"
        f"• 🚨 Dushman qal'alarimizga harbiy yurish boshlaganda;\n"
        f"• ⚔️ Qal'alar jangi yakunlari va yo'qotishlar hisoboti;\n"
        f"• 📢 Lordning umumiy safarbarlik chaqiruvlari.\n\n"
        f"💬 <b>Guruhdagi buyruqlar:</b>\n"
        f"• <code>/houseinfo</code> — Xonadon g'aznasi, qal'alari va qudrati\n"
        f"• <code>/calltoarms</code> — Lordning safarbarlik signali\n"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def house_group_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruhda yoki shaxsiy chatda xonadon ma'lumotlarini ko'rish"""
    chat = update.effective_chat
    user = update.effective_user

    async with AsyncSessionLocal() as session:
        house = None
        if chat.type in ("group", "supergroup"):
            house = await crud.get_house_by_group_chat_id(session, chat.id)

        if not house:
            db_user = await crud.get_user_with_relations(session, user.id)
            if db_user and db_user.house:
                house = db_user.house

        if not house:
            await update.message.reply_text(
                "❌ Ushbu guruh biron-bir xonadonga bog'lanmagan.\n"
                "Bog'lash uchun xonadon Lordi guruhda /sethousechat buyrug'ini yozishi kerak."
            )
            return

        lord_user = await crud.get_user_by_telegram_id(session, house.lord_user_id) if house.lord_user_id else None
        lord_name = lord_user.full_name if lord_user else "Saylanmagan"

        members_count_res = await session.execute(
            select(func.count(models.User.id)).where(models.User.house_id == house.id)
        )
        members_count = members_count_res.scalar() or 0

        terrs_res = await session.execute(
            select(models.Territory).where(models.Territory.owner_house_id == house.id)
        )
        terrs = terrs_res.scalars().all()
        terr_names = ", ".join([t.name for t in terrs[:5]]) if terrs else "Hozircha yo'q"
        if len(terrs) > 5:
            terr_names += f" va yana {len(terrs)-5} ta"

    bot_user = await context.bot.get_me()
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏰 Botda Boshqarish", url=f"https://t.me/{bot_user.username}?start=house")]
    ])

    text = (
        f"🏰 <b>{html.escape(house.emoji)} {html.escape(house.name)} — MA'LUMOTLAR</b>\n\n"
        f"📍 Mintaqa: <b>{html.escape(house.region)}</b>\n"
        f"👑 Xonadon Lordi: <b>{html.escape(lord_name)}</b>\n"
        f"👥 A'zolar soni: <b>{members_count} nafar</b>\n"
        f"🏆 Nufuz (Prestige): <b>{house.prestige:,}</b>\n\n"
        f"🏛️ <b>Umumiy Xonadon G'aznasi:</b>\n"
        f"• 🪙 Oltin: <b>{house.gold:,}</b>\n"
        f"• 🌾 Oziq-ovqat: <b>{house.food:,}</b>\n"
        f"• ⛓️ Temir: <b>{house.iron:,}</b>\n\n"
        f"🏯 <b>Egallangan Qal'alar ({len(terrs)} ta):</b>\n"
        f"<i>{html.escape(terr_names)}</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def house_group_call_to_arms_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruhda Lord tomonidan harbiy safarbarlik chaqirig'i"""
    chat = update.effective_chat
    user = update.effective_user

    async with AsyncSessionLocal() as session:
        house = None
        if chat.type in ("group", "supergroup"):
            house = await crud.get_house_by_group_chat_id(session, chat.id)

        db_user = await crud.get_user_with_relations(session, user.id)
        if not db_user:
            await update.message.reply_text("❌ Avval botga /start bosing.")
            return

        if not house:
            house = db_user.house

        if not house:
            await update.message.reply_text("❌ Xonadon aniqlanmadi.")
            return

        from config import ADMIN_IDS, OWNER_ID
        is_lord = (house.lord_user_id == user.id) or (db_user.rank in ("king", "commander")) or (user.id in ADMIN_IDS) or (user.id == OWNER_ID)
        if not is_lord:
            await update.message.reply_text("❌ Faqat xonadon Lordi yoki Bosh Sarkardasi umumiy safarbarlik chaqirig'ini bera oladi!")
            return

        lord_name = db_user.characters[0].name if db_user.characters else db_user.full_name

    bot_user = await context.bot.get_me()
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Askar Berish / Safarbarlik", url=f"https://t.me/{bot_user.username}?start=house")],
        [InlineKeyboardButton("🛡️ Qal'alar Mudofaasi", url=f"https://t.me/{bot_user.username}?start=castles")]
    ])

    text = (
        f"🚨⚔️ <b>HARBIY SAFARBARLIK CHAQIRIG'I!</b>\n\n"
        f"🏰 <b>{html.escape(house.emoji)} {html.escape(house.name)}</b> Lordi <b>{html.escape(lord_name)}</b> barcha ritsarlar va a'zolarni zudlik bilan harbiy safarbarlikka chaqirmoqda!\n\n"
        f"Dushmanlar poytaxtimiz va qal'alarimizga xavf solmoqda. "
        f"Barcha jangchilar botga kirib, Lord armiyasiga askar taqdim etsin yoki qal'a mudofaasini kuchaytirsin!"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)


def register_house_handlers(app):
    app.add_handler(CommandHandler("house", house_command))
    app.add_handler(CommandHandler(["sethousechat", "setgrouphouse"], set_house_chat_command))
    app.add_handler(CommandHandler(["houseinfo", "groupinfo"], house_group_info_command))
    app.add_handler(CommandHandler(["calltoarms", "safarbarlik"], house_group_call_to_arms_command))
    app.add_handler(CallbackQueryHandler(house_callback, pattern="^menu_house$"))
    app.add_handler(CallbackQueryHandler(house_members_callback, pattern="^house_members$"))
    app.add_handler(CallbackQueryHandler(house_rank_assign_menu_callback, pattern="^house_rank_assign_menu$"))
    app.add_handler(CallbackQueryHandler(house_pick_target_rank_callback, pattern="^hrank_pick:"))
    app.add_handler(CallbackQueryHandler(house_set_rank_callback, pattern="^hset_rank:"))
    app.add_handler(CallbackQueryHandler(house_election_callback, pattern="^house_election$"))
    app.add_handler(CallbackQueryHandler(claim_house_lord_callback, pattern="^claim_house_lord$"))
    app.add_handler(CallbackQueryHandler(house_abdicate_prompt_callback, pattern="^house_abdicate_prompt$"))
    app.add_handler(CallbackQueryHandler(house_abdicate_confirm_callback, pattern="^house_abdicate_confirm$"))
    app.add_handler(CallbackQueryHandler(house_leave_prompt_callback, pattern="^house_leave_prompt$"))
    app.add_handler(CallbackQueryHandler(house_leave_confirm_callback, pattern="^house_leave_confirm$"))
    app.add_handler(CallbackQueryHandler(house_vote_callback, pattern="^hvote:"))
    app.add_handler(CallbackQueryHandler(call_to_arms_broadcast_callback, pattern="^call_to_arms_broadcast$"))
    app.add_handler(CallbackQueryHandler(troop_donation_menu_callback, pattern="^troop_donation_menu$"))
    app.add_handler(CallbackQueryHandler(troop_donation_action_callback, pattern="^donate_troop:"))
    app.add_handler(CallbackQueryHandler(house_donate_menu_callback, pattern="^house_donate_menu$"))
    app.add_handler(CallbackQueryHandler(house_custom_donate_callback, pattern="^h_custom_donate:"))
    app.add_handler(CallbackQueryHandler(house_donate_action_callback, pattern="^hdonate:"))
    app.add_handler(CallbackQueryHandler(house_top_donors_callback, pattern="^house_top_donors$"))
    app.add_handler(CallbackQueryHandler(house_treasury_manage_callback, pattern="^house_treasury_manage$"))
    app.add_handler(CallbackQueryHandler(house_treasury_custom_with_callback, pattern="^h_custom_with:"))
    app.add_handler(CallbackQueryHandler(house_treasury_withdraw_callback, pattern="^h_with:"))
    app.add_handler(CallbackQueryHandler(house_treasury_distribute_callback, pattern="^h_dist:"))

