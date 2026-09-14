from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from keyboards.menus import back_to_main_keyboard
from config import escape_md, RANKS
from sqlalchemy import select


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
        ]
        if user.rank == "king":
            buttons.append([InlineKeyboardButton("🎖️ Lavozim Tayinlash (Lord)", callback_data="house_rank_assign_menu")])

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
        target_user = await session.get(models.User, target_user_id)
        name = target_user.full_name if target_user else "A'zo"

    rank_name = RANKS.get(new_rank, {}).get("name", new_rank)
    await query.answer(f"✅ {name} muvaffaqiyatli {rank_name} lavozimiga tayinlandi!", show_alert=True)
    await show_house(query, query.from_user.id, is_message=False)


async def house_election_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lord Saylovi: nomzodlar ro'yxati va ovoz berish"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        members = await crud.get_house_members_with_characters(session, user.house.id)
        buttons = []
        for m in members:
            char_name = m.characters[0].name if m.characters else m.full_name
            buttons.append([InlineKeyboardButton(f"🗳️ {char_name} ({m.rank})", callback_data=f"hvote:{m.id}")])

        buttons.append([InlineKeyboardButton("🔙 Xonadonga Qaytish", callback_data="menu_house")])

        text = (
            f"🗳️ **XONADON LORDI SAYLOVI**\n\n"
            f"Xonadonning barcha a'zolari o'z ovozlarini Lordlikka munosib nomzodga berishi mumkin.\n"
            f"Agar nomzod xonadon a'zolarining **50% dan ko'p** ovozini to'plasa, u darhol yangi Lord (King) deb e'lon qilinadi!\n\n"
            f"O'z ovozingizni bering:"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def house_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ovoz berish amali"""
    query = update.callback_query
    await query.answer()

    candidate_user_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        outcome = await crud.cast_house_vote(session, user.house.id, user.id, candidate_user_id)

    await query.answer(outcome, show_alert=True)
    await show_house(query, user_id, is_message=False)


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
            f"Shaxsiy boyliklaringizni umumiy xazinaga topshirib, xonadon qudratini oshiring!\n"
            f"Har bir ehson uchun sizga shaxsiy **Prestige (Nufuz)** beriladi.\n\n"
            f"🏛️ **Hozirgi xonadon g'aznasi:**\n"
            f"• 🪙 Oltin: {house.gold:,}\n"
            f"• 🌾 Oziq-ovqat: {house.food:,}\n"
            f"• ⛓️ Temir: {house.iron:,}\n\n"
            f"🎒 **Sizning zaxirangiz:**\n"
            f"🪙 {user.gold:,} | 🌾 {user.food:,} | ⛓️ {user.iron:,}\n\n"
            f"Ehson miqdorini tanlang:"
        )

        buttons = [
            [InlineKeyboardButton("🪙 100 Oltin", callback_data="hdonate:gold:100"),
             InlineKeyboardButton("🪙 500 Oltin", callback_data="hdonate:gold:500")],
            [InlineKeyboardButton("🌾 500 Oziq-ovqat", callback_data="hdonate:food:500"),
             InlineKeyboardButton("⛓️ 200 Temir", callback_data="hdonate:iron:200")],
            [InlineKeyboardButton("✨ Katta Karvon (500🪙 + 500🌾 + 200⛓️)", callback_data="hdonate:combo:1")],
            [InlineKeyboardButton("🔙 Xonadonga Qaytish", callback_data="menu_house")],
        ]
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
        gold = 500
        food = 500
        iron = 200

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.donate_to_house_treasury(
            session=session,
            user_id=user_id,
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


def register_house_handlers(app):
    app.add_handler(CommandHandler("house", house_command))
    app.add_handler(CallbackQueryHandler(house_callback, pattern="^menu_house$"))
    app.add_handler(CallbackQueryHandler(house_members_callback, pattern="^house_members$"))
    app.add_handler(CallbackQueryHandler(house_rank_assign_menu_callback, pattern="^house_rank_assign_menu$"))
    app.add_handler(CallbackQueryHandler(house_pick_target_rank_callback, pattern="^hrank_pick:"))
    app.add_handler(CallbackQueryHandler(house_set_rank_callback, pattern="^hset_rank:"))
    app.add_handler(CallbackQueryHandler(house_election_callback, pattern="^house_election$"))
    app.add_handler(CallbackQueryHandler(house_vote_callback, pattern="^hvote:"))
    app.add_handler(CallbackQueryHandler(house_donate_menu_callback, pattern="^house_donate_menu$"))
    app.add_handler(CallbackQueryHandler(house_donate_action_callback, pattern="^hdonate:"))
    app.add_handler(CallbackQueryHandler(house_top_donors_callback, pattern="^house_top_donors$"))
