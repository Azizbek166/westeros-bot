from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from sqlalchemy import select
from keyboards.menus import back_to_main_keyboard
from config import escape_md


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

        # Faol ittifoqlar
        active_alliances = await crud.get_active_alliances_for_house(session, house.id)
        allied_houses_text = ""
        for a in active_alliances:
            other_id = a.house_b_id if a.house_a_id == house.id else a.house_a_id
            other_h = await session.get(models.House, other_id)
            if other_h:
                allied_houses_text += f"• 🛡️ **{other_h.emoji} {other_h.name}**\n"

        if not allied_houses_text:
            allied_houses_text = "Hozircha faol ittifoqlar yo'q.\n"

        # Kutilayotgan takliflar (bizga kelgan)
        pending_alliances = await crud.get_pending_alliances_for_house(session, house.id)
        pending_buttons = []
        pending_text = ""
        for p in pending_alliances:
            sender_h = await session.get(models.House, p.house_a_id)
            if sender_h:
                pending_text += f"• 📬 **{sender_h.emoji} {sender_h.name}** sizga ittifoq taklif qilmoqda!\n"
                if user.rank in ["king", "commander"]:
                    pending_buttons.append([
                        InlineKeyboardButton(f"✅ Qabul: {sender_h.name}", callback_data=f"diplo_ans:{p.id}:1"),
                        InlineKeyboardButton(f"❌ Rad: {sender_h.name}", callback_data=f"diplo_ans:{p.id}:0"),
                    ])

        buttons = []
        # Takliflarni tasdiqlash tugmalari
        buttons.extend(pending_buttons)

        buttons.append([InlineKeyboardButton("🤝 Yangi Ittifoq Taklif Qilish", callback_data="diplo_propose_alliance")])
        if active_alliances:
            buttons.append([InlineKeyboardButton("🛡️ Ittifoqchiga Qo'shin Yordami Yuborish", callback_data="diplo_reinforce_pick")])
        buttons.append([InlineKeyboardButton("⚔️ Urush E'lon Qilish (Xaritaga o'tish)", callback_data="menu_map")])
        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        text = (
            f"🤝 **DIPLOMATIYA VA HARBIY ITTIFOQLAR**\n\n"
            f"🏰 Xonadoningiz: **{house.emoji} {house.name}**\n"
            f"🎖️ Lavozimingiz: **{user.rank.title()}**\n\n"
            f"🛡️ **FAOL HARBIY ITTIFOQCHILAR:**\n{allied_houses_text}\n"
        )
        if pending_text:
            text += f"📬 **KUTILAYOTGAN TAKLIFLAR:**\n{pending_text}\n"

        text += (
            "Ittifoqchilar bir-biriga hujum qila olmaydi va qiyin damda o'z qal'alariga "
            "qo'shimcha mudofaa askarlarini (garnizon yordami) yuborishi mumkin!"
        )

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def propose_alliance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ittifoq taklif qilish uchun xonadonlar ro'yxatini chiqarish"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        if user.rank not in ["king", "commander"]:
            await query.answer("❌ Faqat Xonadon Lordi yoki Harbiy Qo'mondoni ittifoq taklif qilishi mumkin!", show_alert=True)
            return

        # Faol xonadonlar ro'yxati (o'yinchisi bor yoki taniqli xonadonlar)
        houses_res = await session.execute(
            select(models.House).where(models.House.id != user.house.id).order_by(models.House.region, models.House.name).limit(20)
        )
        houses = houses_res.scalars().all()

        buttons = []
        for h in houses:
            buttons.append([InlineKeyboardButton(f"🤝 {h.emoji} {h.name} ({h.region})", callback_data=f"diplo_send_prop:{h.id}")])

        buttons.append([InlineKeyboardButton("🔙 Diplomatiyaga Qaytish", callback_data="menu_diplomacy")])

        text = (
            f"🤝 **YANGI ITTIFOQ TAKLIF QILISH**\n\n"
            f"Qaysi xonadonga elchi va qarg'a orqali ittifoq taklifi yubormoqchisiz?\n"
            f"Xonadon tanlang:"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def send_proposal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Taklifni yuborish"""
    query = update.callback_query
    await query.answer()

    target_house_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            return

        success, msg = await crud.propose_alliance(session, user.house.id, target_house_id)
        target_house = await session.get(models.House, target_house_id)

        # Agar nishon xonadon Lordi bo'lsa, unga bildirishnoma jo'natish
        if success and target_house and target_house.lord_user_id:
            try:
                await context.bot.send_message(
                    chat_id=target_house.lord_user_id,
                    text=(
                        f"📬 **QARG'A XABARI!**\n\n"
                        f"🏰 **{user.house.emoji} {user.house.name}** xonadoni siz bilan Harbiy Ittifoq tuzishni taklif qilmoqda!\n\n"
                        f"Taklifni qabul qilish yoki rad etish uchun /alliance menyusiga kiring."
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    await query.answer(msg, show_alert=True)
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

        ok = await crud.respond_to_alliance(session, alliance_id, accept)

    res_msg = "✅ Harbiy Ittifoq muvaffaqiyatli tuzildi!" if accept else "❌ Ittifoq taklifi rad etildi."
    await query.answer(res_msg, show_alert=True)
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
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


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

    await query.answer(msg, show_alert=True)
    await show_diplomacy_hub(query, user_id, is_message=False)


def register_diplomacy_handlers(app):
    app.add_handler(CommandHandler("alliance", diplomacy_command))
    app.add_handler(CommandHandler("diplomacy", diplomacy_command))
    app.add_handler(CallbackQueryHandler(diplomacy_callback, pattern="^menu_diplomacy$"))
    app.add_handler(CallbackQueryHandler(propose_alliance_callback, pattern="^diplo_propose_alliance$"))
    app.add_handler(CallbackQueryHandler(send_proposal_callback, pattern="^diplo_send_prop:"))
    app.add_handler(CallbackQueryHandler(answer_proposal_callback, pattern="^diplo_ans:"))
    app.add_handler(CallbackQueryHandler(reinforce_pick_callback, pattern="^diplo_reinforce_pick$"))
    app.add_handler(CallbackQueryHandler(send_rf_callback, pattern="^diplo_send_rf:"))

