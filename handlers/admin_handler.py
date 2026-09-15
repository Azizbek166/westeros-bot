import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from config import ADMIN_IDS, OWNER_ID, escape_md
from sqlalchemy import select, func, desc


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/admin buyrug'i"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Kechirasiz, sizda administrator huquqi yo'q!")
        return
    await show_admin_dashboard(update, is_message=True)


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """admin_panel callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("❌ Administrator huquqi talab etiladi!", show_alert=True)
        return
    await show_admin_dashboard(query, is_message=False)


async def show_admin_dashboard(target, is_message: bool):
    """Admin boshqaruv paneli bosh menyusi"""
    async with AsyncSessionLocal() as session:
        # Server statistikasi
        total_users_res = await session.execute(select(func.count(models.User.id)))
        total_users = total_users_res.scalar() or 0

        total_gold_res = await session.execute(select(func.sum(models.User.gold)))
        total_gold = total_gold_res.scalar() or 0

        total_marches_res = await session.execute(
            select(func.count(models.BattleMarch.id)).where(models.BattleMarch.status == "marching")
        )
        active_marches = total_marches_res.scalar() or 0

        total_dragons_res = await session.execute(select(func.count(models.Dragon.id)))
        total_dragons = total_dragons_res.scalar() or 0

        # Tun Qiroli holati
        ww_res = await session.execute(
            select(models.EventState).where(models.EventState.event_name == "white_walkers")
        )
        ww_event = ww_res.scalar_one_or_none()
        ww_hp = "250,000"
        if ww_event:
            ww_data = json.loads(ww_event.data_json)
            ww_hp = f"{ww_data.get('hp', 250000):,}"

        text = (
            f"👑 **WESTEROS OLIY ADMINISTRATOR PANELI**\n\n"
            f"📊 **SERVER STATISTIKASI:**\n"
            f"• 👥 Jami Lordlar: **{total_users}** ta\n"
            f"• 🪙 Umumiy Xazina: **{total_gold:,}** oltin\n"
            f"• ⚔️ Faol Yurishlar: **{active_marches}** ta\n"
            f"• 🐉 Tirik Ajdarlar: **{total_dragons}** ta\n"
            f"• ❄️ Tun Qiroli HP: **{ww_hp}** / 250,000\n\n"
            f"Boshqaruv bo'limini tanlang:"
        )

        buttons = [
            [InlineKeyboardButton("👥 O'yinchilarni Boshqarish (User Manager)", callback_data="admin_users_list:0")],
            [InlineKeyboardButton("👑 Xonadon Lordlarini Tayinlash", callback_data="admin_lords_menu")],
            [InlineKeyboardButton("🏰 Xonadonlar va G'aznalar", callback_data="admin_houses_list")],
            [InlineKeyboardButton("❄️ Global Hodisalar & Tun Qiroli", callback_data="admin_events_menu")],
            [InlineKeyboardButton("🎁 Barchaga Ommaviy Sovg'a (+2000🪙)", callback_data="admin_mass_gift")],
            [InlineKeyboardButton("🔄 Barcha Kunlik Limitlarni Yangilash", callback_data="admin_reset_all_limits")],
            [InlineKeyboardButton("📢 Global E'lon (Broadcast)", callback_data="admin_broadcast_info")],
            [InlineKeyboardButton("🛡️ Adminlar Ro'yxati & Huquqlar", callback_data="admin_admins_list")],
            [InlineKeyboardButton("🔙 Bosh Menyu", callback_data="menu_main")],
        ]

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ============================================================
# USER MANAGEMENT
# ============================================================

async def admin_users_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'yinchilar ro'yxati"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    offset = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(models.User).order_by(desc(models.User.id)).offset(offset).limit(6)
        )
        users = res.scalars().all()

        buttons = []
        for u in users:
            name = u.full_name or u.username or f"User {u.id}"
            buttons.append([InlineKeyboardButton(f"👤 {name} ({u.gold:,}🪙, {u.rank})", callback_data=f"admin_u_detail:{u.id}")])

        nav_row = []
        if offset >= 6:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_users_list:{offset - 6}"))
        if len(users) == 6:
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"admin_users_list:{offset + 6}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])

        text = (
            f"👥 **O'YINCHILARNI BOSHQARISH (Ro'yxat)**\n\n"
            f"Kerakli o'yinchini tanlang yoki buyruqdan foydalaning:\n"
            f"`/givegold @username 1000`\n"
            f"`/givefood @username 2000`\n"
            f"`/giveiron @username 1000`"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_user_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'yinchining to'liq ma'lumotlari va boshqaruv amallari"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    user_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        user = await session.get(models.User, user_id)
        if not user:
            await query.edit_message_text("❌ O'yinchi topilmadi.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_users_list:0")]]))
            return

        house = await session.get(models.House, user.house_id) if user.house_id else None
        h_name = house.name if house else "Xonadonsiz"
        army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
        army = army_res.scalar_one_or_none()
        dragon = await crud.get_user_dragon(session, user.id)
        drg_str = f"{dragon.name} ({dragon.stage})" if dragon else "Mavjud emas"

        text = (
            f"👤 **LORD MA'LUMOTLARI: {escape_md(user.full_name)}**\n\n"
            f"• Telegram ID: `{user.telegram_id}`\n"
            f"• Username: @{user.username or 'yoq'}\n"
            f"• 🏰 Xonadon: **{h_name}**\n"
            f"• 🎖️ Lavozim: **{user.rank}** | Daraja: **{user.level}**\n"
            f"• 🏆 Prestige: **{user.prestige:,}** | XP: **{user.xp:,}**\n\n"
            f"💰 **RESURSLAR:**\n"
            f"• 🪙 Oltin: **{user.gold:,}**\n"
            f"• 🌾 Oziq-ovqat: **{user.food:,}**\n"
            f"• ⛓️ Temir: **{user.iron:,}**\n\n"
            f"⚔️ **ARMIYA:** Piyoda: {army.infantry if army else 0}, Otliq: {army.cavalry if army else 0}\n"
            f"🐉 **AJDAR:** {drg_str}\n\n"
            f"Boshqaruv amalini tanlang:"
        )

        buttons = [
            [
                InlineKeyboardButton("💰 +5,000 Oltin", callback_data=f"adm_act:{user.id}:gold:5000"),
                InlineKeyboardButton("💰 -2,000 Oltin", callback_data=f"adm_act:{user.id}:gold:-2000"),
            ],
            [
                InlineKeyboardButton("🌾 +10,000 Oziq", callback_data=f"adm_act:{user.id}:food:10000"),
                InlineKeyboardButton("⛓️ +5,000 Temir", callback_data=f"adm_act:{user.id}:iron:5000"),
            ],
            [
                InlineKeyboardButton("👑 Lord (King)", callback_data=f"adm_act:{user.id}:rank:king"),
                InlineKeyboardButton("⚔️ Qo'mondon", callback_data=f"adm_act:{user.id}:rank:commander"),
                InlineKeyboardButton("🛡️ Ritsar", callback_data=f"adm_act:{user.id}:rank:knight"),
            ],
            [
                InlineKeyboardButton("🔄 Kunlik Limitlarni 0 qilish", callback_data=f"adm_act:{user.id}:reset:0"),
                InlineKeyboardButton("🛡️ +72 soat Qalqon", callback_data=f"adm_act:{user.id}:shield:72"),
            ],
            [
                InlineKeyboardButton("❌ Adminlikdan Olish" if user.telegram_id in ADMIN_IDS else "⭐️ Admin Qilish", callback_data=f"adm_act:{user.id}:toggle_admin:0"),
            ],
            [InlineKeyboardButton("🔙 O'yinchilar Ro'yxati", callback_data="admin_users_list:0")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_user_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'yinchiga resurs yoki unvon berish"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    user_id = int(parts[1])
    action = parts[2]
    val = parts[3]

    async with AsyncSessionLocal() as session:
        user = await session.get(models.User, user_id)
        if not user:
            await query.answer("O'yinchi topilmadi.", show_alert=True)
            return

        if action == "gold":
            user.gold = max(0, user.gold + int(val))
            msg = f"Oltin o'zgartirildi: {user.gold:,}🪙"
        elif action == "food":
            user.food = max(0, user.food + int(val))
            msg = f"Oziq-ovqat o'zgartirildi: {user.food:,}🌾"
        elif action == "iron":
            user.iron = max(0, user.iron + int(val))
            msg = f"Temir o'zgartirildi: {user.iron:,}⛓️"
        elif action == "rank":
            user.rank = val
            if val == "king" and user.house_id:
                h = await session.get(models.House, user.house_id)
                if h:
                    if h.lord_user_id and h.lord_user_id != user.telegram_id:
                        old_l = await crud.get_user_by_telegram_id(session, h.lord_user_id)
                        if old_l and old_l.rank == "king":
                            old_l.rank = "knight"
                    h.lord_user_id = user.telegram_id
            elif val != "king" and user.house_id:
                h = await session.get(models.House, user.house_id)
                if h and h.lord_user_id == user.telegram_id:
                    h.lord_user_id = None
            msg = f"Lavozim {val.upper()} ga o'zgartirildi!"
        elif action == "reset":
            user.daily_quiz_count = 0
            user.daily_council_count = 0
            user.daily_secret_quest_count = 0
            msg = "Barcha kunlik limitlar 0 ga tushirildi!"
        elif action == "shield":
            user.peace_shield_until = datetime.utcnow() + timedelta(hours=int(val))
            msg = f"{val} soatlik Tinchlik Qalqoni berildi!"
        elif action == "toggle_admin":
            from config import save_admin_id, remove_admin_id
            if user.telegram_id in ADMIN_IDS:
                if user.telegram_id == OWNER_ID:
                    await query.answer("❌ Asosiy bot egasini adminlikdan olib bo'lmaydi!", show_alert=True)
                    return
                remove_admin_id(user.telegram_id)
                msg = f"{user.full_name} adminlikdan olindi!"
            else:
                save_admin_id(user.telegram_id)
                msg = f"{user.full_name} muvaffaqiyatli admin etib tayinlandi!"

        await session.commit()

    await query.answer(f"✅ {msg}", show_alert=True)
    await admin_user_detail_callback(update, context)


# ============================================================
# HOUSE MANAGEMENT
# ============================================================

async def admin_houses_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadonlar ro'yxati va xazinasi"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(models.House).order_by(desc(models.House.prestige)).limit(8))
        houses = res.scalars().all()

        buttons = []
        for h in houses:
            buttons.append([InlineKeyboardButton(f"{h.emoji} {h.name} (💰{h.gold:,} 🏆{h.prestige})", callback_data=f"adm_h_detail:{h.id}")])

        buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])

        text = "🏰 **XONADONLAR VA G'AZNALAR BOSHQARUVI:**\n\nXonadonni tanlang:"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_house_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadon boshqaruvi"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    house_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        house = await session.get(models.House, house_id)
        if not house:
            return

        lord_text = "❌ Vakant (Lord yo'q)"
        if house.lord_user_id:
            lord_user = await crud.get_user_by_telegram_id(session, house.lord_user_id)
            if lord_user:
                lord_text = f"👑 {escape_md(lord_user.full_name)} (ID: `{lord_user.telegram_id}`)"

        text = (
            f"🏰 **XONADON: {house.emoji} {house.name}**\n\n"
            f"👑 Xonadon Lordi: **{lord_text}**\n"
            f"📍 Mintaqa: {house.region}\n"
            f"🏆 Prestige: **{house.prestige:,}**\n"
            f"🏛️ G'azna: **{house.gold:,}**🪙 oltin, **{house.food:,}**🌾 oziq, **{house.iron:,}**⛓️ temir\n"
        )

        buttons = [
            [InlineKeyboardButton("👑 Lordni Boshqarish / Yangi Lord Tayinlash", callback_data=f"adm_lord_h:{house.id}")],
            [InlineKeyboardButton("💰 G'aznaga +10,000 Oltin", callback_data=f"adm_h_act:{house.id}:gold:10000")],
            [InlineKeyboardButton("🌾 G'aznaga +20,000 Oziq", callback_data=f"adm_h_act:{house.id}:food:20000")],
            [InlineKeyboardButton("🏆 +500 Xonadon Prestige", callback_data=f"adm_h_act:{house.id}:prestige:500")],
            [InlineKeyboardButton("🔙 Xonadonlar", callback_data="admin_houses_list")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_house_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadon g'aznasini to'ldirish"""
    query = update.callback_query
    parts = query.data.split(":")
    house_id = int(parts[1])
    action = parts[2]
    val = int(parts[3])

    async with AsyncSessionLocal() as session:
        house = await session.get(models.House, house_id)
        if house:
            if action == "gold":
                house.gold += val
            elif action == "food":
                house.food += val
            elif action == "prestige":
                house.prestige += val
            await session.commit()

    await query.answer(f"✅ Xonadon yangilandi!", show_alert=True)
    await admin_house_detail_callback(update, context)


# ============================================================
# LORD MANAGEMENT (XONADON LORDLARINI TAYINLASH VA BOSHQARISH)
# ============================================================

async def admin_lords_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha xonadonlar va ularning Lordlari ro'yxati"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(models.House).order_by(models.House.id))
        houses = res.scalars().all()

        text = (
            "👑 **WESTEROS XONADON LORDLARI BOSHQARUVI**\n\n"
            "Bu yerda har bir xonadonning amaldagi Lordini ko'rishingiz, yangi Lord tayinlashingiz "
            "yoki saylov ovozlarini boshqarishingiz mumkin.\n\n"
            "Xonadonni tanlang:\n\n"
        )

        buttons = []
        for h in houses:
            lord_label = "❌ Vakant"
            if h.lord_user_id:
                lord_u = await crud.get_user_by_telegram_id(session, h.lord_user_id)
                if lord_u:
                    lord_label = f"👑 {lord_u.full_name[:14]}"

            text += f"• {h.emoji} **{h.name}**: {lord_label}\n"
            buttons.append([InlineKeyboardButton(f"{h.emoji} {h.name} — {lord_label}", callback_data=f"adm_lord_h:{h.id}")])

        buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_lord_house_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan xonadon Lordi boshqaruv menyusi"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    house_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        house = await session.get(models.House, house_id)
        if not house:
            await query.answer("Xonadon topilmadi!", show_alert=True)
            return

        members = await crud.get_house_members_with_characters(session, house.id)
        lord_user = None
        if house.lord_user_id:
            lord_user = await crud.get_user_by_telegram_id(session, house.lord_user_id)

        # Saylov ovozlari
        votes_res = await session.execute(
            select(func.count(models.HouseVote.id)).where(models.HouseVote.house_id == house.id)
        )
        total_votes = votes_res.scalar() or 0

        if lord_user:
            lord_info = (
                f"👑 **{escape_md(lord_user.full_name)}**\n"
                f"• Username: @{lord_user.username or 'yoq'}\n"
                f"• Telegram ID: `{lord_user.telegram_id}`\n"
                f"• Daraja: **{lord_user.level}** | Lavozim: **{lord_user.rank}**\n"
                f"• Prestige: **{lord_user.prestige:,}**"
            )
        else:
            lord_info = "❌ **Vakant (Lord belgilanmagan - xonadon boshqaruvsiz!)**"

        text = (
            f"🏰 **XONADON: {house.emoji} {house.name}**\n"
            f"📍 Mintaqa: **{house.region}** | 🏆 Prestige: **{house.prestige:,}**\n"
            f"👥 Jami A'zolar: **{len(members)}** nafar\n"
            f"🗳️ Faol Ovozlar: **{total_votes}** ta\n\n"
            f"👑 **AMALDAGI LORD:**\n"
            f"{lord_info}\n\n"
            f"Boshqaruv amalini tanlang:"
        )

        buttons = [
            [InlineKeyboardButton("👑 A'zolardan Yangi Lord Tayinlash", callback_data=f"adm_pick_lord:{house.id}:0")],
        ]
        if house.lord_user_id:
            buttons.append([InlineKeyboardButton("🚫 Lordni Bo'shatish (Vakant Qilish)", callback_data=f"adm_dismiss_lord:{house.id}")])

        if total_votes > 0:
            buttons.append([InlineKeyboardButton("🗳️ Saylov Ovozlarini Tozalash (0)", callback_data=f"adm_reset_votes:{house.id}")])

        buttons.append([InlineKeyboardButton("🏰 Xonadon G'aznasi & Resurslar", callback_data=f"adm_h_detail:{house.id}")])
        buttons.append([InlineKeyboardButton("🔙 Xonadonlar Ro'yxati", callback_data="admin_lords_menu")])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_pick_lord_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadon a'zolaridan Lord tanlash (sahifalangan)"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    house_id = int(parts[1])
    offset = int(parts[2]) if len(parts) > 2 else 0

    async with AsyncSessionLocal() as session:
        house = await session.get(models.House, house_id)
        if not house:
            return

        members = await crud.get_house_members_with_characters(session, house.id)
        page_size = 6
        page_members = members[offset:offset + page_size]

        text = (
            f"👑 **{house.emoji} {house.name} XONADONIGA LORD TAYINLASH**\n\n"
            f"Quyidagi xonadon a'zolaridan birini tanlang. U darhol **Lord (King)** etib tayinlanadi:\n\n"
        )

        buttons = []
        for m in page_members:
            char_name = m.characters[0].name if m.characters else (m.full_name or f"User {m.id}")
            is_current = (house.lord_user_id == m.telegram_id) or (m.rank == "king")
            badge = "👑 (Lord)" if is_current else "👉"
            buttons.append([InlineKeyboardButton(
                f"{badge} {char_name} (Lvl {m.level}, {m.rank})",
                callback_data=f"adm_conf_lord:{house.id}:{m.id}"
            )])

        nav_row = []
        if offset >= page_size:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"adm_pick_lord:{house.id}:{offset - page_size}"))
        if offset + page_size < len(members):
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"adm_pick_lord:{house.id}:{offset + page_size}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"adm_lord_h:{house.id}")])

        if not page_members:
            text += "❌ Bu xonadonda hozircha birorta ham a'zo mavjud emas!\n"

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_conf_lord_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lord etib tayinlashni tasdiqlash sahifasi"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    house_id = int(parts[1])
    target_user_id = int(parts[2])

    async with AsyncSessionLocal() as session:
        house = await session.get(models.House, house_id)
        user = await session.get(models.User, target_user_id)
        if not house or not user:
            await query.answer("Ma'lumot topilmadi!", show_alert=True)
            return

        char_name = user.characters[0].name if user.characters else user.full_name

        text = (
            f"👑 **LORD TAYINLASHNI TASDIQLASH**\n\n"
            f"🏰 Xonadon: **{house.emoji} {house.name}**\n"
            f"👤 Nomzod: **{char_name}** ({escape_md(user.full_name)})\n"
            f"🆔 Telegram ID: `{user.telegram_id}`\n"
            f"⚔️ Daraja: **{user.level}** | Hozirgi unvon: **{user.rank}**\n\n"
            f"⚠️ Haqiqatan ham ushbu o'yinchini {house.name} xonadoni Lordi (King) etib tayinlaysizmi?\n"
            f"(Oldingi Lord mavjud bo'lsa, u avtomatik ravishda oddiy ritsarga tushiriladi)"
        )

        buttons = [
            [InlineKeyboardButton("✅ HA, LORD ETIB TAYINLASH", callback_data=f"adm_do_lord:{house.id}:{user.id}")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"adm_pick_lord:{house.id}:0")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_do_lord_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lord tayinlash ijrosi"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    house_id = int(parts[1])
    target_user_id = int(parts[2])

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.admin_appoint_house_lord(session, house_id, target_user_id)
        if ok:
            user = await session.get(models.User, target_user_id)
            house = await session.get(models.House, house_id)
            if user and house:
                try:
                    await context.bot.send_message(
                        chat_id=user.telegram_id,
                        text=(
                            f"👑 **BUYUK XABAR!**\n\n"
                            f"Oliy Administrator tomonidan siz **{house.emoji} {house.name}** xonadonining rasmiy "
                            f"**Lordi (King)** etib tayinlandingiz!\n\n"
                            f"Endi xonadon harbiy yurishlari, urushlari va barcha boshqaruv vakolatlari sizning qo'lingizda!"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

    await query.answer(msg, show_alert=True)
    query.data = f"adm_lord_h:{house_id}"
    await admin_lord_house_detail_callback(update, context)


async def admin_dismiss_lord_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lordni lavozimidan ozod etish (bo'shatish)"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    house_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        ok, msg = await crud.admin_dismiss_house_lord(session, house_id)

    await query.answer(msg, show_alert=True)
    query.data = f"adm_lord_h:{house_id}"
    await admin_lord_house_detail_callback(update, context)


async def admin_reset_votes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saylov ovozlarini tozalash"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    house_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        ok, msg = await crud.admin_reset_house_election_votes(session, house_id)

    await query.answer(msg, show_alert=True)
    query.data = f"adm_lord_h:{house_id}"
    await admin_lord_house_detail_callback(update, context)


# ============================================================
# GLOBAL EVENTS & BOSS MANAGEMENT
# ============================================================

async def admin_events_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global hodisalar boshqaruvi"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    text = (
        "❄️ **GLOBAL HODISALAR VA BOSSLAR BOSHQARUVI**\n\n"
        "Kerakli amalni tanlang:"
    )
    buttons = [
        [InlineKeyboardButton("❄️ Tun Qiroli HP: 250,000 ga tiklash", callback_data="adm_ev_act:nk_reset")],
        [InlineKeyboardButton("❄️ Tun Qiroli HP: 5,000 ga tushirish (Sinov)", callback_data="adm_ev_act:nk_low")],
        [InlineKeyboardButton("☣️ Vabo Epidemiyasini e'lon qilish", callback_data="adm_ev_act:plague")],
        [InlineKeyboardButton("🥷 Qaroqchilar Hujumini e'lon qilish", callback_data="adm_ev_act:bandits")],
        [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_event_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hodisani o'zgartirish"""
    query = update.callback_query
    act = query.data.split(":")[1]

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(models.EventState).where(models.EventState.event_name == "white_walkers")
        )
        ww_event = res.scalar_one_or_none()

        if act == "nk_reset":
            if ww_event:
                ww_event.data_json = json.dumps({"hp": 250000, "status": "active"})
                await session.commit()
            msg = "❄️ Tun Qiroli armiyasi to'liq 250,000 ga tiklandi!"
        elif act == "nk_low":
            if ww_event:
                ww_event.data_json = json.dumps({"hp": 5000, "status": "active"})
                await session.commit()
            msg = "❄️ Tun Qiroli armiyasi 5,000 HP ga tushirildi!"
        elif act == "plague":
            msg = "☣️ Vabo epidemiyasi boshlandi!"
        elif act == "bandits":
            msg = "🥷 Qaroqchilar hujumi boshlandi!"

    await query.answer(f"✅ {msg}", show_alert=True)
    await show_admin_dashboard(query, is_message=False)


# ============================================================
# MASS ACTIONS & COMMANDS
# ============================================================

async def admin_mass_gift_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha lordlarga tuhfa ulashish"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        users_res = await session.execute(select(models.User))
        all_users = users_res.scalars().all()
        for u in all_users:
            u.gold += 2000
            u.food += 1000
            u.iron += 500
        await session.commit()
        cnt = len(all_users)

    await query.answer(f"✅ Barcha {cnt} nafar lordga +2,000🪙, +1,000🌾, +500⛓️ tarqatildi!", show_alert=True)
    await show_admin_dashboard(query, is_message=False)


async def admin_reset_all_limits_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha o'yinchilarning kunlik limitlarini 0 qilish"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        users_res = await session.execute(select(models.User))
        all_users = users_res.scalars().all()
        for u in all_users:
            u.daily_quiz_count = 0
            u.daily_council_count = 0
            u.daily_secret_quest_count = 0
        await session.commit()
        cnt = len(all_users)

    await query.answer(f"✅ Barcha {cnt} nafar o'yinchining kunlik limitlari yangilandi!", show_alert=True)
    await show_admin_dashboard(query, is_message=False)


async def admin_broadcast_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast bo'yicha yo'riqnoma"""
    query = update.callback_query
    await query.answer()

    text = (
        "📢 **GLOBAL XABARNOMA YUBORISH**\n\n"
        "Barcha ro'yxatdan o'tgan o'yinchilarga e'lon yuborish uchun chatga quyidagi buyruqni yozing:\n\n"
        "`/broadcast Hurmatli lordlar! Yangi turnir boshlanmoqda!`"
    )
    buttons = [[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def handle_give_resource_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/givegold, /givefood, /giveiron @user miqdor"""
    if not is_admin(update.effective_user.id):
        return

    cmd = update.message.text.split()[0].lstrip("/").lower()
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(f"Foydalanish: `/{cmd} @username [miqdor]`", parse_mode="Markdown")
        return

    target = args[0]
    amount = int(args[1]) if args[1].lstrip("-").isdigit() else 0

    async with AsyncSessionLocal() as session:
        # User topish
        u = None
        if target.isdigit():
            u = await session.get(models.User, int(target))
            if not u:
                u = await crud.get_user_by_telegram_id(session, int(target))
        else:
            clean_u = target.lstrip("@").lower()
            res = await session.execute(select(models.User).where(func.lower(models.User.username) == clean_u))
            u = res.scalar_one_or_none()

        if not u:
            await update.message.reply_text("❌ Foydalanuvchi topilmadi!")
            return

        if "gold" in cmd:
            u.gold = max(0, u.gold + amount)
            res_str = f"🪙 Oltin: {u.gold:,}"
        elif "food" in cmd:
            u.food = max(0, u.food + amount)
            res_str = f"🌾 Oziq-ovqat: {u.food:,}"
        elif "iron" in cmd:
            u.iron = max(0, u.iron + amount)
            res_str = f"⛓️ Temir: {u.iron:,}"

        await session.commit()

    await update.message.reply_text(f"✅ {u.full_name} ga {amount:+,} berildi! Yangi hisob: {res_str}")


async def admin_admins_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adminlar ro'yxati va boshqarish"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    admin_lines = []
    for idx, adm_id in enumerate(ADMIN_IDS, start=1):
        tag = "👑 (Bosh Egasi - Siz)" if adm_id == OWNER_ID else "🛡️ (Admin)"
        admin_lines.append(f"{idx}. `{adm_id}` {tag}")

    admins_text = "\n".join(admin_lines)

    text = (
        f"🛡️ **ADMINLAR RO'YXATI VA HUQUQLARI**\n\n"
        f"Faqat ushbu ro'yxatdagi shaxslar botning administrator paneliga kira oladi:\n\n"
        f"{admins_text}\n\n"
        f"ℹ️ **Qanday qilib yangi admin tayinlanadi?**\n"
        f"1. **User Manager orqali:** *👥 O'yinchilarni Boshqarish* bo'limiga kiring, o'yinchini tanlang va **⭐️ Admin Qilish** tugmasini bosing.\n"
        f"2. **Buyruq orqali:**\n"
        f"• `/addadmin <telegram_id>` — yangi admin qo'shish\n"
        f"• `/deladmin <telegram_id>` — adminni ro'yxatdan o'chirish"
    )

    buttons = [
        [InlineKeyboardButton("👥 O'yinchilardan Tanlash", callback_data="admin_users_list:0")],
        [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/addadmin <telegram_id> buyrug'i"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("❌ Foydalanish: `/addadmin <telegram_id>`\nMasalan: `/addadmin 123456789`", parse_mode="Markdown")
        return

    target_id = int(args[0])
    from config import save_admin_id
    save_admin_id(target_id)
    await update.message.reply_text(f"✅ Telegram ID `{target_id}` muvaffaqiyatli ADMIN etib tayinlandi!", parse_mode="Markdown")


async def del_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/deladmin <telegram_id> buyrug'i"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("❌ Foydalanish: `/deladmin <telegram_id>`\nMasalan: `/deladmin 123456789`", parse_mode="Markdown")
        return

    target_id = int(args[0])
    if target_id == OWNER_ID:
        await update.message.reply_text("❌ Asosiy bot egasini adminlikdan olib bo'lmaydi!")
        return

    from config import remove_admin_id
    if target_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Bu foydalanuvchi adminlar ro'yxatida yo'q!")
        return

    remove_admin_id(target_id)
    await update.message.reply_text(f"✅ Telegram ID `{target_id}` adminlikdan olindi!", parse_mode="Markdown")


async def set_lord_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/setlord <xonadon_id/nomi> <telegram_id/username> buyrug'i"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    args = context.args
    if not args or len(args) < 2:
        text = (
            "👑 **XONADONGA LORD TAYINLASH BUYRUG'I**\n\n"
            "Foydalanish:\n"
            "`/setlord <xonadon_id_yoki_nomi> <telegram_id_yoki_username>`\n\n"
            "Misollar:\n"
            "• `/setlord 1 123456789` (1-xonadonga tayinlash)\n"
            "• `/setlord stark 123456789` (Stark xonadoniga tayinlash)\n"
            "• `/setlord lannister @john_snow` (Username orqali)\n\n"
            "Yoki `/admin` panelidagi **👑 Xonadon Lordlarini Tayinlash** menyusidan 1 bosishda tayinlashingiz mumkin!"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
        return

    house_arg = args[0].strip().lower()
    user_arg = args[1].strip()

    async with AsyncSessionLocal() as session:
        house = None
        if house_arg.isdigit():
            house = await session.get(models.House, int(house_arg))
        if not house:
            res = await session.execute(select(models.House).where(models.House.name.ilike(f"%{house_arg}%")))
            house = res.scalars().first()

        if not house:
            await update.message.reply_text(f"❌ '{house_arg}' nomli xonadon topilmadi!")
            return

        target_user = None
        if user_arg.isdigit():
            target_user = await crud.get_user_by_telegram_id(session, int(user_arg))
            if not target_user:
                target_user = await session.get(models.User, int(user_arg))
        if not target_user:
            clean_username = user_arg.lstrip("@")
            res = await session.execute(select(models.User).where(models.User.username.ilike(clean_username)))
            target_user = res.scalars().first()

        if not target_user:
            await update.message.reply_text(f"❌ Foydalanuvchi topilmadi (`{user_arg}`)!")
            return

        ok, msg = await crud.admin_appoint_house_lord(session, house.id, target_user.id)
        if ok:
            try:
                await context.bot.send_message(
                    chat_id=target_user.telegram_id,
                    text=(
                        f"👑 **BUYUK XABAR!**\n\n"
                        f"Oliy Administrator tomonidan siz **{house.emoji} {house.name}** xonadonining rasmiy "
                        f"**Lordi (King)** etib tayinlandingiz!\n\n"
                        f"Endi xonadon harbiy yurishlari, urushlari va barcha boshqaruv vakolatlari sizning qo'lingizda!"
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        await update.message.reply_text(msg, parse_mode="Markdown")


def register_admin_handlers(app):
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("addadmin", add_admin_command))
    app.add_handler(CommandHandler("deladmin", del_admin_command))
    app.add_handler(CommandHandler("setlord", set_lord_command))
    app.add_handler(CommandHandler(["givegold", "givefood", "giveiron"], handle_give_resource_command))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_admins_list_callback, pattern="^admin_admins_list$"))
    app.add_handler(CallbackQueryHandler(admin_lords_menu_callback, pattern="^admin_lords_menu$"))
    app.add_handler(CallbackQueryHandler(admin_lord_house_detail_callback, pattern="^adm_lord_h:"))
    app.add_handler(CallbackQueryHandler(admin_pick_lord_callback, pattern="^adm_pick_lord:"))
    app.add_handler(CallbackQueryHandler(admin_conf_lord_callback, pattern="^adm_conf_lord:"))
    app.add_handler(CallbackQueryHandler(admin_do_lord_callback, pattern="^adm_do_lord:"))
    app.add_handler(CallbackQueryHandler(admin_dismiss_lord_callback, pattern="^adm_dismiss_lord:"))
    app.add_handler(CallbackQueryHandler(admin_reset_votes_callback, pattern="^adm_reset_votes:"))
    app.add_handler(CallbackQueryHandler(admin_users_list_callback, pattern="^admin_users_list:"))
    app.add_handler(CallbackQueryHandler(admin_user_detail_callback, pattern="^admin_u_detail:"))
    app.add_handler(CallbackQueryHandler(admin_user_action_callback, pattern="^adm_act:"))
    app.add_handler(CallbackQueryHandler(admin_houses_list_callback, pattern="^admin_houses_list$"))
    app.add_handler(CallbackQueryHandler(admin_house_detail_callback, pattern="^adm_h_detail:"))
    app.add_handler(CallbackQueryHandler(admin_house_action_callback, pattern="^adm_h_act:"))
    app.add_handler(CallbackQueryHandler(admin_events_menu_callback, pattern="^admin_events_menu$"))
    app.add_handler(CallbackQueryHandler(admin_event_action_callback, pattern="^adm_ev_act:"))
    app.add_handler(CallbackQueryHandler(admin_mass_gift_callback, pattern="^admin_mass_gift$"))
    app.add_handler(CallbackQueryHandler(admin_reset_all_limits_callback, pattern="^admin_reset_all_limits$"))
    app.add_handler(CallbackQueryHandler(admin_broadcast_info_callback, pattern="^admin_broadcast_info$"))
