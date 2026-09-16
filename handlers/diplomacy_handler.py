from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from sqlalchemy import select, func
from config import escape_md

NPC_HOUSE_IDS = {47, 48, 49, 50}


async def diplomacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/alliance va /diplomacy buyrug'i"""
    user_id = update.effective_user.id
    await show_diplomacy_hub(update, user_id, is_message=True)


async def diplomacy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_diplomacy callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_diplomacy_hub(query, user_id, is_message=False)


async def show_diplomacy_hub(target, user_id: int, is_message: bool):
    """Diplomatiya markazi: Ittifoqlar, Takliflar va Harbiy Yordam"""
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

        # Faol ittifoqlar (1 Harbiy va 1 To'y)
        active_alliances = await crud.get_active_alliances_for_house(session, house.id)
        mil_alliance = next((a for a in active_alliances if getattr(a, "type", "military") == "military"), None)
        mar_alliance = next((a for a in active_alliances if getattr(a, "type", "military") == "marriage"), None)

        mil_text = "❌ Mavjud emas *(Bo'sh - 1 ta mumkin)*"
        if mil_alliance:
            other_id = mil_alliance.house_b_id if mil_alliance.house_a_id == house.id else mil_alliance.house_a_id
            other_h = await session.get(models.House, other_id)
            if other_h:
                mil_text = f"✅ **{other_h.emoji} {escape_md(other_h.name)}** ({escape_md(other_h.region)})"

        mar_text = "❌ Mavjud emas *(Bo'sh - 1 ta mumkin)*"
        if mar_alliance:
            other_id = mar_alliance.house_b_id if mar_alliance.house_a_id == house.id else mar_alliance.house_a_id
            other_h = await session.get(models.House, other_id)
            if other_h:
                mar_text = f"✅ **{other_h.emoji} {escape_md(other_h.name)}** ({escape_md(other_h.region)})"

        # Kutilayotgan takliflar (bizga kelgan)
        pending_alliances = await crud.get_pending_alliances_for_house(session, house.id)
        pending_buttons = []
        pending_text = ""
        for p in pending_alliances:
            sender_h = await session.get(models.House, p.house_a_id)
            if sender_h:
                p_type = getattr(p, "type", "military")
                type_name = "⚔️ Harbiy Ittifoq" if p_type == "military" else "💍 To'y Ittifoqi"
                pending_text += f"• 📬 **{sender_h.emoji} {escape_md(sender_h.name)}** sizga **{type_name}** taklif qilmoqda!\n"
                if user.rank in ["king", "commander"]:
                    pending_buttons.append([
                        InlineKeyboardButton(f"✅ Qabul ({type_name[:2]}): {sender_h.name}", callback_data=f"diplo_ans:{p.id}:1"),
                        InlineKeyboardButton(f"❌ Rad: {sender_h.name}", callback_data=f"diplo_ans:{p.id}:0"),
                    ])

        buttons = []
        buttons.extend(pending_buttons)

        buttons.append([InlineKeyboardButton("🤝 Yangi Ittifoq Taklif Qilish", callback_data="diplo_propose_alliance:0")])
        if active_alliances:
            buttons.append([InlineKeyboardButton("🛡️ Ittifoqchiga Qo'shin Yordami Yuborish", callback_data="diplo_reinforce_pick")])
        buttons.append([InlineKeyboardButton("⚔️ Urush E'lon Qilish (Xaritaga o'tish)", callback_data="menu_map")])
        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        text = (
            f"🤝 **DIPLOMATIYA VA ITTIFOQLAR**\n\n"
            f"🏰 Xonadoningiz: **{house.emoji} {escape_md(house.name)}**\n"
            f"🎖️ Lavozimingiz: **{user.rank.title()}**\n\n"
            f"📋 **XONADON ITTIFOQLARI HOLATI:**\n"
            f"• ⚔️ **Harbiy Ittifoq:** {mil_text}\n"
            f"• 💍 **To'y Ittifoqi (Nikoh):** {mar_text}\n\n"
        )
        if pending_text:
            text += f"📬 **KUTILAYOTGAN TAKLIFLAR:**\n{pending_text}\n"

        text += (
            "ℹ️ *Qoida: Har bir xonadon ko'pi bilan 1 ta Harbiy va 1 ta To'y ittifoqi tuza oladi. "
            "Ittifoqchilar o'zaro urush qila olmaydi va qal'alarini birgalikda himoya qilishlari mumkin! "
            "(NPC xonadonlar bilan ittifoq tuzilmaydi)*"
        )

        try:
            if is_message:
                await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            if is_message:
                await target.message.reply_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await target.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


async def propose_alliance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ittifoq taklif qilish uchun xonadonlar ro'yxatini chiqarish (NPC larsiz va sahifalangan)"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    offset = 0
    if ":" in query.data:
        try:
            offset = int(query.data.split(":")[1])
        except Exception:
            offset = 0

    page_size = 8
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        if user.rank not in ["king", "commander"]:
            await query.answer("❌ Faqat Xonadon Lordi yoki Harbiy Qo'mondoni ittifoq taklif qilishi mumkin!", show_alert=True)
            return

        # Tekshirish: agar xonadonda 2 ta ittifoq ham to'la bo'lsa
        active_alliances = await crud.get_active_alliances_for_house(session, user.house.id)
        has_mil = any(getattr(a, "type", "military") == "military" for a in active_alliances)
        has_mar = any(getattr(a, "type", "military") == "marriage" for a in active_alliances)

        if has_mil and has_mar:
            await query.answer("❌ Xonadoningizda allaqachon 1 ta Harbiy va 1 ta To'y ittifoqi mavjud! Boshqa ittifoq tuzib bo'lmaydi.", show_alert=True)
            return

        # Faol o'yinchi xonadonlari ro'yxati (NPC larsiz: 47, 48, 49, 50 va is_npc == False)
        base_query = (
            select(models.House)
            .where(
                models.House.id != user.house.id,
                models.House.id.not_in(NPC_HOUSE_IDS),
                models.House.is_npc.is_(False)
            )
        )

        total_res = await session.execute(select(func.count(models.House.id)).where(
            models.House.id != user.house.id,
            models.House.id.not_in(NPC_HOUSE_IDS),
            models.House.is_npc.is_(False)
        ))
        total_houses = total_res.scalar() or 0

        houses_res = await session.execute(
            base_query.order_by(models.House.region, models.House.name).offset(offset).limit(page_size)
        )
        houses = houses_res.scalars().all()

        buttons = []
        for h in houses:
            buttons.append([InlineKeyboardButton(f"🤝 {h.emoji} {h.name} ({h.region})", callback_data=f"diplo_pick_type:{h.id}")])

        nav_row = []
        if offset >= page_size:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"diplo_propose_alliance:{offset - page_size}"))
        if offset + page_size < total_houses:
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"diplo_propose_alliance:{offset + page_size}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Diplomatiyaga Qaytish", callback_data="menu_diplomacy")])

        text = (
            f"🤝 **YANGI ITTIFOQ TAKLIF QILISH**\n\n"
            f"Ittifoq taklif qilmoqchi bo'lgan xonadoningizni tanlang:\n"
            f"*(Ro'yxatda faqat o'yinchi xonadonlari mavjud, NPC lar chiqarib tashlangan)*"
        )
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


async def pick_alliance_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ittifoq turini tanlash (Harbiy yoki To'y)"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    target_house_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        target_house = await session.get(models.House, target_house_id)
        if not target_house:
            await query.answer("Xonadon topilmadi!", show_alert=True)
            return

        active_alliances = await crud.get_active_alliances_for_house(session, user.house.id)
        has_mil = any(getattr(a, "type", "military") == "military" for a in active_alliances)
        has_mar = any(getattr(a, "type", "military") == "marriage" for a in active_alliances)

        buttons = []
        if not has_mil:
            buttons.append([InlineKeyboardButton("⚔️ Harbiy Ittifoq (Harbiy yordam & Sulh)", callback_data=f"diplo_send_prop:{target_house_id}:military")])
        if not has_mar:
            buttons.append([InlineKeyboardButton("💍 To'y Ittifoqi (Nikoh ittifoqi & Do'stlik)", callback_data=f"diplo_send_prop:{target_house_id}:marriage")])

        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="diplo_propose_alliance:0")])

        text = (
            f"🤝 **ITTIFOQ TURINI TANLANG**\n\n"
            f"🏰 Nishon Xonadon: **{target_house.emoji} {escape_md(target_house.name)}** ({escape_md(target_house.region)})\n\n"
            f"Qaysi turdagi ittifoq shartnomasini taklif qilmoqchisiz?\n\n"
            f"• ⚔️ **Harbiy Ittifoq:** Bir-biringizning qal'alaringizga qo'shin yordami yuborish va o'zaro hujum qilmaslik kafolati.\n"
            f"• 💍 **To'y Ittifoqi:** Xonadonlararo sulolaviy nikoh va mustahkam do'stona aloqalar."
        )

        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


async def send_proposal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Taklifni yuborish"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    target_house_id = int(parts[1])
    alliance_type = parts[2] if len(parts) > 2 else "military"
    user_id = query.from_user.id

    type_name = "⚔️ Harbiy Ittifoq" if alliance_type == "military" else "💍 To'y Ittifoqi"

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        success, msg = await crud.propose_alliance(session, user.house.id, target_house_id, alliance_type=alliance_type)
        target_house = await session.get(models.House, target_house_id)

        # Agar nishon xonadon Lordi bo'lsa, unga bildirishnoma jo'natish
        if success and target_house and target_house.lord_user_id:
            try:
                await context.bot.send_message(
                    chat_id=target_house.lord_user_id,
                    text=(
                        f"📬 **QARG'A XABARI!**\n\n"
                        f"🏰 **{user.house.emoji} {escape_md(user.house.name)}** xonadoni siz bilan "
                        f"**{type_name}** tuzishni taklif qilmoqda!\n\n"
                        f"Taklifni qabul qilish yoki rad etish uchun /alliance menyusiga kiring."
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    try:
        await query.answer(msg, show_alert=True)
    except Exception:
        pass
    await show_diplomacy_hub(query, user_id, is_message=False)


async def answer_proposal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Taklifni qabul qilish yoki rad etish"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    alliance_id = int(parts[1])
    accept = bool(int(parts[2]))
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or user.rank not in ["king", "commander"]:
            await query.answer("❌ Faqat Lord yoki Qo'mondon qaror qabul qilishi mumkin!", show_alert=True)
            return

        ok, msg = await crud.respond_to_alliance(session, alliance_id, accept)

    try:
        await query.answer(msg, show_alert=True)
    except Exception:
        pass
    await show_diplomacy_hub(query, user_id, is_message=False)


async def reinforce_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ittifoqchining qaysi qal'asiga yordam yuborishni tanlash"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        active_alliances = await crud.get_active_alliances_for_house(session, user.house.id)
        allied_house_ids = []
        for a in active_alliances:
            other_id = a.house_b_id if a.house_a_id == user.house.id else a.house_a_id
            allied_house_ids.append(other_id)

        # Ittifoqchilar qal'alari
        allied_castles_res = await session.execute(
            select(models.Territory).where(models.Territory.owner_house_id.in_(allied_house_ids))
        )
        castles = allied_castles_res.scalars().all()

        buttons = []
        for c in castles:
            buttons.append([InlineKeyboardButton(f"🛡️ {c.name} ({c.castle_name})", callback_data=f"diplo_send_rf:{c.id}")])

        buttons.append([InlineKeyboardButton("🔙 Diplomatiyaga Qaytish", callback_data="menu_diplomacy")])

        text = (
            f"🛡️ **QAL'AGA QO'SHIN YORDAMI (REINFORCEMENTS)**\n\n"
            f"Ittifoqchilaringizni dushman qamalidan himoya qilish uchun ularning qal'asiga garnizon qo'shinlarini yuborishingiz mumkin.\n"
            f"Himoyalash uchun qal'ani tanlang:"
        )
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


async def send_rf_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'aga harbiy yordamni tasdiqlash va jo'natish"""
    query = update.callback_query
    await query.answer()

    castle_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    # Yuboriladigan qo'shin miqdori (yengil standart otryad: 20 piyoda, 10 kamonchi, 5 otliq, 5 nayzachi)
    async with AsyncSessionLocal() as session:
        success, msg = await crud.send_castle_reinforcements(
            session=session,
            user_id=user_id,
            target_territory_id=castle_id,
            infantry=20,
            archers=10,
            cavalry=5,
            spearmen=5,
        )

    try:
        await query.answer(msg, show_alert=True)
    except Exception:
        pass
    await show_diplomacy_hub(query, user_id, is_message=False)


def register_diplomacy_handlers(app):
    app.add_handler(CommandHandler("alliance", diplomacy_command))
    app.add_handler(CommandHandler("diplomacy", diplomacy_command))
    app.add_handler(CallbackQueryHandler(diplomacy_callback, pattern="^menu_diplomacy$"))
    app.add_handler(CallbackQueryHandler(propose_alliance_callback, pattern="^diplo_propose_alliance(:[0-9]+)?$"))
    app.add_handler(CallbackQueryHandler(pick_alliance_type_callback, pattern="^diplo_pick_type:"))
    app.add_handler(CallbackQueryHandler(send_proposal_callback, pattern="^diplo_send_prop:"))
    app.add_handler(CallbackQueryHandler(answer_proposal_callback, pattern="^diplo_ans:"))
    app.add_handler(CallbackQueryHandler(reinforce_pick_callback, pattern="^diplo_reinforce_pick$"))
    app.add_handler(CallbackQueryHandler(send_rf_callback, pattern="^diplo_send_rf:"))

