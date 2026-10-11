import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from sqlalchemy import select, func
from config import ADMIN_IDS, OWNER_ID

logger = logging.getLogger(__name__)

NPC_HOUSE_IDS = {47, 48, 49, 50}


def sanitize_md(text: str) -> str:
    """Markdown formatida entity parsing xatosi bermasligi uchun maxsus belgilarni tozalash"""
    if not text:
        return ""
    return str(text).replace("*", "").replace("_", " ").replace("`", "").replace("[", "(").replace("]", ")").strip()


async def is_diplomacy_leader(session, user: models.User, house: models.House) -> bool:
    """Xonadonda diplomatiya va ittifoq qarorlarini qabul qilish vakolati borligini tekshirish"""
    if not user or not house:
        return False
    try:
        uid = int(user.telegram_id)
        if uid in [int(x) for x in ADMIN_IDS] or uid == int(OWNER_ID):
            return True
    except Exception:
        pass

    if house.lord_user_id == user.telegram_id:
        return True
    if user.rank in ["king", "commander"]:
        return True

    # Agar xonadonda atigi 1 ta o'yinchi bo'lsa, u amalda xonadon yetakchisidir
    res = await session.execute(
        select(func.count(models.User.id)).where(models.User.house_id == house.id)
    )
    cnt = res.scalar() or 0
    if cnt <= 1:
        return True
    return False


async def safe_send_or_edit(target, text: str, reply_markup=None, is_message: bool = False):
    """
    Xabarni tahrirlash yoki yuborishning xavfsiz mexanizmi:
    1. Markdown parse rejimi bilan urinadi.
    2. Agar Telegram Markdown entity parsing xatoligi (BadRequest) bersa, plain-text da xabar chiqaradi.
    3. Agar tahrirlash imkoni bo'lmasa, reply orqali javob qaytaradi.
    """
    try:
        if is_message:
            msg_obj = getattr(target, "message", target)
            return await msg_obj.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            return await target.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        err_msg = str(e).lower()
        if "message is not modified" in err_msg:
            return None
        logger.warning(f"Markdown send/edit failed ({type(e).__name__}: {e}), attempting fallback...")

        plain_text = text.replace("**", "").replace("*", "").replace("_", "").replace("`", "")

        # 1-urinish: edit plain text
        if not is_message and hasattr(target, "edit_message_text"):
            try:
                return await target.edit_message_text(plain_text, parse_mode=None, reply_markup=reply_markup)
            except Exception:
                pass

        # 2-urinish: reply plain text
        msg_obj = target if is_message else getattr(target, "message", None)
        if msg_obj and hasattr(msg_obj, "reply_text"):
            try:
                return await msg_obj.reply_text(plain_text, parse_mode=None, reply_markup=reply_markup)
            except Exception as e2:
                logger.error(f"Plain text reply fallback failed: {e2}")


async def diplomacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/alliance, /diplomacy va /ittifoq buyruqlari"""
    user_id = update.effective_user.id
    await show_diplomacy_hub(update, user_id, is_message=True)


async def diplomacy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_diplomacy callback"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    user_id = query.from_user.id
    await show_diplomacy_hub(query, user_id, is_message=False)


async def show_diplomacy_hub(target, user_id: int, is_message: bool):
    """Diplomatiya markazi: Ittifoqlar, Takliflar va Harbiy Yordam"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            msg = "❌ Siz hali xonadon tanlamagansiz. Avval /start ni bosing."
            await safe_send_or_edit(target, msg, is_message=is_message)
            return

        house = user.house
        is_leader = await is_diplomacy_leader(session, user, house)

        # 1. Faol ittifoqlar (1 Harbiy va 1 To'y)
        active_alliances = await crud.get_active_alliances_for_house(session, house.id)
        mil_alliance = next((a for a in active_alliances if getattr(a, "type", "military") == "military"), None)
        mar_alliance = next((a for a in active_alliances if getattr(a, "type", "military") == "marriage"), None)

        mil_text = "❌ Mavjud emas *(Bo'sh - 1 ta mumkin)*"
        if mil_alliance:
            other_id = mil_alliance.house_b_id if mil_alliance.house_a_id == house.id else mil_alliance.house_a_id
            other_h = await session.get(models.House, other_id)
            if other_h:
                mil_text = f"✅ **{other_h.emoji} {sanitize_md(other_h.name)}** ({sanitize_md(other_h.region)})"

        mar_text = "❌ Mavjud emas *(Bo'sh - 1 ta mumkin)*"
        if mar_alliance:
            other_id = mar_alliance.house_b_id if mar_alliance.house_a_id == house.id else mar_alliance.house_a_id
            other_h = await session.get(models.House, other_id)
            if other_h:
                mar_text = f"✅ **{other_h.emoji} {sanitize_md(other_h.name)}** ({sanitize_md(other_h.region)})"

        # 2. Kiruvchi takliflar (Bizga kelgan)
        pending_incoming = await crud.get_pending_alliances_for_house(session, house.id)
        pending_buttons = []
        pending_text = ""
        for p in pending_incoming:
            sender_h = await session.get(models.House, p.house_a_id)
            if sender_h:
                p_type = getattr(p, "type", "military")
                type_name = "⚔️ Harbiy Ittifoq" if p_type == "military" else "💍 To'y Ittifoqi"
                pending_text += f"• 📬 **{sender_h.emoji} {sanitize_md(sender_h.name)}** sizga **{type_name}** taklif qilmoqda!\n"
                if is_leader:
                    pending_buttons.append([
                        InlineKeyboardButton(f"✅ Qabul ({type_name[:2]}): {sender_h.name}", callback_data=f"diplo_ans:{p.id}:1"),
                        InlineKeyboardButton(f"❌ Rad: {sender_h.name}", callback_data=f"diplo_ans:{p.id}:0"),
                    ])

        # 3. Chiquvchi takliflar (Biz yuborgan, javob kutilmoqda)
        pending_sent = await crud.get_sent_pending_alliances_for_house(session, house.id)
        sent_buttons = []
        sent_text = ""
        for s in pending_sent:
            target_h = await session.get(models.House, s.house_b_id)
            if target_h:
                s_type = getattr(s, "type", "military")
                type_name = "⚔️ Harbiy Ittifoq" if s_type == "military" else "💍 To'y Ittifoqi"
                sent_text += f"• ⏳ **{target_h.emoji} {sanitize_md(target_h.name)}** ga **{type_name}** yuborilgan (Javob kutilmoqda)\n"
                if is_leader:
                    sent_buttons.append([
                        InlineKeyboardButton(f"❌ Taklifni Bekor Qilish: {target_h.name}", callback_data=f"diplo_cancel_prop:{s.id}"),
                    ])

        buttons = []
        buttons.extend(pending_buttons)
        buttons.extend(sent_buttons)

        buttons.append([InlineKeyboardButton("🤝 Yangi Ittifoq Taklif Qilish", callback_data="diplo_propose_alliance:0")])
        if active_alliances:
            buttons.append([InlineKeyboardButton("🛡️ Ittifoqchiga Qo'shin Yordami Yuborish", callback_data="diplo_reinforce_pick")])

        # Ittifoqni uzish imkoniyati (Faqat yetakchilar uchun)
        if is_leader:
            break_row = []
            if mil_alliance:
                break_row.append(InlineKeyboardButton("💔 Harbiy Ittifoqni Uzish", callback_data=f"diplo_break_prompt:{mil_alliance.id}"))
            if mar_alliance:
                break_row.append(InlineKeyboardButton("💔 To'y Ittifoqini Uzish", callback_data=f"diplo_break_prompt:{mar_alliance.id}"))
            if break_row:
                buttons.append(break_row)

        buttons.append([InlineKeyboardButton("⚖️ Savdo Bozori (Xonadonlararo Birja)", callback_data="menu_trade")])
        buttons.append([InlineKeyboardButton("⚔️ Urush E'lon Qilish (Xaritaga o'tish)", callback_data="menu_map")])
        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        text = (
            f"🤝 **DIPLOMATIYA VA ITTIFOQLAR**\n\n"
            f"🏰 Xonadoningiz: **{house.emoji} {sanitize_md(house.name)}**\n"
            f"🎖️ Lavozimingiz: **{sanitize_md(user.rank.title())}**\n\n"
            f"📋 **XONADON ITTIFOQLARI HOLATI:**\n"
            f"• ⚔️ **Harbiy Ittifoq:** {mil_text}\n"
            f"• 💍 **To'y Ittifoqi (Nikoh):** {mar_text}\n\n"
        )

        if pending_text:
            text += f"📬 **KIRUVCHI TAKLIFLAR:**\n{pending_text}\n"

        if sent_text:
            text += f"📤 **YUBORILGAN TAKLIFLAR (KUTILMOQDA):**\n{sent_text}\n"

        text += (
            "ℹ️ _Qoida: Har bir xonadon ko'pi bilan 1 ta Harbiy va 1 ta To'y ittifoqi tuza oladi. "
            "Ittifoqchilar o'zaro urush qila olmaydi va qal'alarini birgalikda himoya qilishlari mumkin! "
            "(NPC xonadonlar bilan ittifoq tuzilmaydi)_"
        )

        await safe_send_or_edit(target, text, reply_markup=InlineKeyboardMarkup(buttons), is_message=is_message)


async def propose_alliance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ittifoq taklif qilish uchun xonadonlar ro'yxatini chiqarish (Faol o'yinchilari bor xonadonlar yuqorida)"""
    query = update.callback_query
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
            await query.answer("❌ Xonadon ma'lumotlari topilmadi.", show_alert=True)
            return

        is_leader = await is_diplomacy_leader(session, user, user.house)
        if not is_leader:
            await query.answer("❌ Faqat Xonadon Lordi yoki Harbiy Qo'mondoni ittifoq taklif qilishi mumkin!", show_alert=True)
            return

        # Tekshirish: agar xonadonda 2 ta ittifoq ham to'la bo'lsa
        active_alliances = await crud.get_active_alliances_for_house(session, user.house.id)
        has_mil = any(getattr(a, "type", "military") == "military" for a in active_alliances)
        has_mar = any(getattr(a, "type", "military") == "marriage" for a in active_alliances)

        if has_mil and has_mar:
            await query.answer("❌ Xonadoningizda allaqachon 1 ta Harbiy va 1 ta To'y ittifoqi mavjud! Boshqa ittifoq tuzib bo'lmaydi.", show_alert=True)
            return

        houses_data, total_houses = await crud.get_houses_for_alliance_picker(
            session, user.house.id, offset=offset, limit=page_size
        )

        buttons = []
        for h in houses_data:
            badge = ""
            if h["player_count"] > 0:
                badge = f" ({h['player_count']} lord)"
            if h.get("pending_sent_type"):
                badge += " ⏳"
            buttons.append([
                InlineKeyboardButton(f"🤝 {h['emoji']} {h['name']}{badge}", callback_data=f"diplo_pick_type:{h['id']}")
            ])

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
            f"*(Haqiqiy o'yinchilari bor faol xonadonlar ro'yxat boshida ko'rsatilgan)*\n\n"
            f"💡 _Qoida: Har bir xonadon ko'pi bilan 1 ta Harbiy va 1 ta To'y ittifoqi tuza oladi._"
        )
        try:
            await query.answer()
        except Exception:
            pass
        await safe_send_or_edit(query, text, reply_markup=InlineKeyboardMarkup(buttons), is_message=False)


async def pick_alliance_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ittifoq turini tanlash (Harbiy yoki To'y)"""
    query = update.callback_query
    user_id = query.from_user.id
    target_house_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            await query.answer("Xonadon topilmadi!", show_alert=True)
            return

        target_house = await session.get(models.House, target_house_id)
        if not target_house:
            await query.answer("Xonadon topilmadi!", show_alert=True)
            return

        active_alliances = await crud.get_active_alliances_for_house(session, user.house.id)
        has_mil = any(getattr(a, "type", "military") == "military" for a in active_alliances)
        has_mar = any(getattr(a, "type", "military") == "marriage" for a in active_alliances)

        # Shu xonadonga allaqachon yuborilgan kutilayotgan takliflar
        pending_sent = await crud.get_sent_pending_alliances_for_house(session, user.house.id)
        sent_types = {p.type for p in pending_sent if p.house_b_id == target_house_id}

        buttons = []
        if not has_mil and "military" not in sent_types:
            buttons.append([InlineKeyboardButton("⚔️ Harbiy Ittifoq (Harbiy yordam & Sulh)", callback_data=f"diplo_send_prop:{target_house_id}:military")])
        if not has_mar and "marriage" not in sent_types:
            buttons.append([InlineKeyboardButton("💍 To'y Ittifoqi (Nikoh ittifoqi & Do'stlik)", callback_data=f"diplo_send_prop:{target_house_id}:marriage")])

        if not buttons:
            await query.answer(f"⚠️ {target_house.name} bilan barcha mumkin bo'lgan ittifoqlar tuzilgan yoki taklif yuborilgan!", show_alert=True)
            return

        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="diplo_propose_alliance:0")])

        # O'yinchilar soni haqida ma'lumot
        p_res = await session.execute(
            select(func.count(models.User.id)).where(models.User.house_id == target_house.id)
        )
        p_count = p_res.scalar() or 0
        p_status = f"👤 Faol a'zolar: {p_count} ta lord" if p_count > 0 else "⚠️ Bu xonadonda hali o'yinchilar yo'q (bo'sh xonadon)"

        text = (
            f"🤝 **ITTIFOQ TURINI TANLANG**\n\n"
            f"🏰 Nishon Xonadon: **{target_house.emoji} {sanitize_md(target_house.name)}** ({sanitize_md(target_house.region)})\n"
            f"{p_status}\n\n"
            f"Qaysi turdagi ittifoq shartnomasini taklif qilmoqchisiz?\n\n"
            f"• ⚔️ **Harbiy Ittifoq:** Bir-biringizning qal'alaringizga qo'shin yordami yuborish va o'zaro hujum qilmaslik kafolati.\n"
            f"• 💍 **To'y Ittifoqi:** Xonadonlararo sulolaviy nikoh va do'stona aloqalar."
        )

        try:
            await query.answer()
        except Exception:
            pass
        await safe_send_or_edit(query, text, reply_markup=InlineKeyboardMarkup(buttons), is_message=False)


async def send_proposal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Taklifni yuborish"""
    query = update.callback_query
    parts = query.data.split(":")
    target_house_id = int(parts[1])
    alliance_type = parts[2] if len(parts) > 2 else "military"
    user_id = query.from_user.id

    type_name = "⚔️ Harbiy Ittifoq" if alliance_type == "military" else "💍 To'y Ittifoqi"

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            await query.answer("❌ Xatolik yuz berdi.", show_alert=True)
            return

        success, msg = await crud.propose_alliance(session, user.house.id, target_house_id, alliance_type=alliance_type)
        target_house = await session.get(models.House, target_house_id)

        # Nishon xonadon Lordi yoki birinchi a'zosiga qarg'a xabari jo'natish
        if success and target_house:
            target_lord_tg_id = target_house.lord_user_id
            if not target_lord_tg_id:
                first_player_res = await session.execute(
                    select(models.User.telegram_id).where(models.User.house_id == target_house.id).limit(1)
                )
                target_lord_tg_id = first_player_res.scalar_one_or_none()

            if target_lord_tg_id:
                try:
                    await context.bot.send_message(
                        chat_id=target_lord_tg_id,
                        text=(
                            f"📬 **QARG'A XABARI: YANGI ITTIFOQ TAKLIFI!**\n\n"
                            f"🏰 **{user.house.emoji} {sanitize_md(user.house.name)}** xonadoni sizga "
                            f"**{type_name}** tuzishni taklif qilmoqda!\n\n"
                            f"Taklifni qabul qilish yoki rad etish uchun /alliance yoki 🤝 Diplomatiya menyusiga kiring."
                        ),
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

    try:
        await query.answer(msg[:190], show_alert=True)
    except Exception:
        pass
    await show_diplomacy_hub(query, user_id, is_message=False)


async def answer_proposal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Taklifni qabul qilish yoki rad etish"""
    query = update.callback_query
    parts = query.data.split(":")
    alliance_id = int(parts[1])
    accept = bool(int(parts[2]))
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            await query.answer("❌ Xonadon ma'lumotlari topilmadi.", show_alert=True)
            return

        is_leader = await is_diplomacy_leader(session, user, user.house)
        if not is_leader:
            await query.answer("❌ Faqat Lord yoki Qo'mondon qaror qabul qilishi mumkin!", show_alert=True)
            return

        ok, msg, info = await crud.respond_to_alliance(session, alliance_id, accept)

    # Taklif qilgan xonadon Lordiga qarg'a xabari
    if ok and info and info.get("sender_lord_id"):
        try:
            if info["accepted"]:
                notif_text = (
                    f"🎉 **QARG'A XABARI: ITTIFOQ KUCHGA KIRDI!**\n\n"
                    f"🏰 **{info['receiver_house_emoji']} {sanitize_md(info['receiver_house_name'])}** sizning "
                    f"**{info['type_name']}** taklifingizni qabul qildi!\n\n"
                    f"Endi siz rasmiy ittifoqdoshsiz: bir-biringizga hujum qila olmaysiz va qal'alaringizni birgalikda himoya qilasiz!"
                )
            else:
                notif_text = (
                    f"❌ **QARG'A XABARI: ITTIFOQ RAD ETILDI**\n\n"
                    f"🏰 **{info['receiver_house_emoji']} {sanitize_md(info['receiver_house_name'])}** sizning "
                    f"**{info['type_name']}** taklifingizni rad etdi."
                )

            await context.bot.send_message(
                chat_id=info["sender_lord_id"],
                text=notif_text,
                parse_mode="Markdown",
            )
        except Exception:
            pass

    try:
        await query.answer(msg[:190], show_alert=True)
    except Exception:
        pass
    await show_diplomacy_hub(query, user_id, is_message=False)


async def cancel_proposal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yuborilgan taklifni bekor qilish"""
    query = update.callback_query
    parts = query.data.split(":")
    alliance_id = int(parts[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            await query.answer("❌ Xatolik yuz berdi.", show_alert=True)
            return

        is_leader = await is_diplomacy_leader(session, user, user.house)
        if not is_leader:
            await query.answer("❌ Faqat Lord yoki Qo'mondon taklifni bekor qila oladi!", show_alert=True)
            return

        ok, msg = await crud.cancel_pending_alliance(session, alliance_id, user.house.id)

    try:
        await query.answer(msg[:190], show_alert=True)
    except Exception:
        pass
    await show_diplomacy_hub(query, user_id, is_message=False)


async def reinforce_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ittifoqchining qaysi qal'asiga yordam yuborishni tanlash"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
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

        allied_castles_res = await session.execute(
            select(models.Territory).where(models.Territory.owner_house_id.in_(allied_house_ids))
        )
        castles = allied_castles_res.scalars().all()

        if not allied_house_ids:
            text = (
                "🛡️ **QAL'AGA QO'SHIN YORDAMI (REINFORCEMENTS)**\n\n"
                "❌ Sizning xonadoningiz hozirda hech qaysi xonadon bilan faol ittifoqqa ega emas.\n"
                "Ittifoqchilar qal'asini himoya qilish uchun avval boshqa xonadon bilan ittifoq shartnomasini imzolang!"
            )
            buttons = [[InlineKeyboardButton("🔙 Diplomatiyaga Qaytish", callback_data="menu_diplomacy")]]
        elif not castles:
            text = (
                "🛡️ **QAL'AGA QO'SHIN YORDAMI (REINFORCEMENTS)**\n\n"
                "❌ Hozirda rasmiy ittifoqchilaringizga qarashli qal'alar mavjud emas.\n"
                "Ittifoqchilaringiz xaritadagi qal'alarni egallaganlarida, ularga ushbu bo'lim orqali harbiy yordam yubora olasiz."
            )
            buttons = [[InlineKeyboardButton("🔙 Diplomatiyaga Qaytish", callback_data="menu_diplomacy")]]
        else:
            buttons = []
            for c in castles:
                buttons.append([InlineKeyboardButton(f"🛡️ {c.name} ({c.castle_name})", callback_data=f"def_rf_menu:{c.id}")])
            buttons.append([InlineKeyboardButton("🔙 Diplomatiyaga Qaytish", callback_data="menu_diplomacy")])

            text = (
                f"🛡️ **QAL'AGA QO'SHIN YORDAMI (REINFORCEMENTS)**\n\n"
                f"Ittifoqchilaringizni dushman qamalidan himoya qilish uchun ularning qal'asiga garnizon qo'shinlarini yuborishingiz mumkin.\n"
                f"Himoyalash uchun qal'ani tanlang:"
            )

        await safe_send_or_edit(query, text, reply_markup=InlineKeyboardMarkup(buttons), is_message=False)


async def send_rf_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'aga harbiy yordam menyusiga yo'naltirish"""
    query = update.callback_query
    castle_id = int(query.data.split(":")[1])
    query.data = f"def_rf_menu:{castle_id}"
    from handlers.battle_handler import def_rf_menu_callback
    await def_rf_menu_callback(update, context)


async def diplo_break_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ittifoqni uzish tasdiqlash ekrani"""
    query = update.callback_query
    parts = query.data.split(":")
    alliance_id = int(parts[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            await query.answer("❌ Xatolik yuz berdi.", show_alert=True)
            return

        is_leader = await is_diplomacy_leader(session, user, user.house)
        if not is_leader:
            await query.answer("❌ Faqat Xonadon Lordi yoki Qo'mondoni ittifoqni uza oladi!", show_alert=True)
            return

        alliance = await session.get(models.Alliance, alliance_id)
        if not alliance or alliance.status != "active":
            await query.answer("❌ Ushbu ittifoq faol emas!", show_alert=True)
            await show_diplomacy_hub(query, user_id, is_message=False)
            return

        other_id = alliance.house_b_id if alliance.house_a_id == user.house.id else alliance.house_a_id
        other_h = await session.get(models.House, other_id)
        if not other_h:
            await query.answer("❌ Xonadon topilmadi!", show_alert=True)
            return

        type_name = "⚔️ Harbiy Ittifoq" if alliance.type == "military" else "💍 To'y Ittifoqi"

        buttons = [
            [InlineKeyboardButton("✅ Ha, Ittifoqni Uzaman (-10% Jarima)", callback_data=f"diplo_break_do:{alliance.id}")],
            [InlineKeyboardButton("🔙 Bekor Qilish", callback_data="menu_diplomacy")],
        ]

        text = (
            f"⚠️ **HAQIQATAN HAM ITTIFOQNI UZMOQCHIMISIZ?**\n\n"
            f"🏰 Nishon: **{other_h.emoji} {sanitize_md(other_h.name)}** ({sanitize_md(other_h.region)})\n"
            f"📜 Ittifoq turi: **{type_name}**\n\n"
            f"🛑 **QASAMYOD BUZILISHI JAZOSI:**\n"
            f"Westerosda ittifoq shartnomasini buzish katta isnod va xiyonat sanaladi!\n"
            f"• Xonadon nufuzi (Prestige) **-10%** ga kamayadi;\n"
            f"• Xonadoningizdagi barcha lordlarning (a'zolarining) **XP va Prestige ballari -10%** ga kamayadi!\n\n"
            f"Ushbu qat'iy qarorni tasdiqlaysizmi?"
        )
        try:
            await query.answer()
        except Exception:
            pass
        await safe_send_or_edit(query, text, reply_markup=InlineKeyboardMarkup(buttons), is_message=False)


async def diplo_break_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ittifoqni uzishni bajarish"""
    query = update.callback_query
    parts = query.data.split(":")
    alliance_id = int(parts[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            await query.answer("❌ Xatolik yuz berdi.", show_alert=True)
            return

        is_leader = await is_diplomacy_leader(session, user, user.house)
        if not is_leader:
            await query.answer("❌ Faqat Xonadon Lordi yoki Qo'mondoni ittifoqni uza oladi!", show_alert=True)
            return

        ok, msg, info = await crud.break_alliance(session, alliance_id, user.house.id)

    # Ikkinchi xonadon Lordiga qarg'a orqali xabar jo'natish
    if ok and info and info.get("other_lord_id"):
        try:
            await context.bot.send_message(
                chat_id=info["other_lord_id"],
                text=(
                    f"💔 **QARG'A XABARI: ITTIFOQ BUZILDI!**\n\n"
                    f"🏰 **{user.house.emoji} {sanitize_md(user.house.name)}** xonadoni siz bilan tuzilgan "
                    f"**{info['type_name']}**ni bir tomonlama bekor qildi!\n\n"
                    f"Qasamyodni buzgani sababli ularning xonadoni va lordlarining nufuzi (Prestige) hamda tajribasi (XP) -10% ga kamaytirildi."
                ),
                parse_mode="Markdown",
            )
        except Exception:
            pass

    try:
        await query.answer(msg[:190], show_alert=True)
    except Exception:
        pass
    await show_diplomacy_hub(query, user_id, is_message=False)


def register_diplomacy_handlers(app):
    """Diplomatiya bo'limi handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["alliance", "diplomacy", "ittifoq"], diplomacy_command))
    app.add_handler(CallbackQueryHandler(diplomacy_callback, pattern="^menu_diplomacy$"))
    app.add_handler(CallbackQueryHandler(propose_alliance_callback, pattern="^diplo_propose_alliance(:[0-9]+)?$"))
    app.add_handler(CallbackQueryHandler(pick_alliance_type_callback, pattern="^diplo_pick_type:"))
    app.add_handler(CallbackQueryHandler(send_proposal_callback, pattern="^diplo_send_prop:"))
    app.add_handler(CallbackQueryHandler(answer_proposal_callback, pattern="^diplo_ans:"))
    app.add_handler(CallbackQueryHandler(cancel_proposal_callback, pattern="^diplo_cancel_prop:"))
    app.add_handler(CallbackQueryHandler(diplo_break_prompt_callback, pattern="^diplo_break_prompt:"))
    app.add_handler(CallbackQueryHandler(diplo_break_do_callback, pattern="^diplo_break_do:"))
    app.add_handler(CallbackQueryHandler(reinforce_pick_callback, pattern="^diplo_reinforce_pick$"))
    app.add_handler(CallbackQueryHandler(send_rf_callback, pattern="^diplo_send_rf:"))
