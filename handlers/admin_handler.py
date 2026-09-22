import asyncio
import json
import html
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from config import ADMIN_IDS, OWNER_ID, escape_md
from sqlalchemy import select, func, desc

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    try:
        uid = int(user_id)
        return uid in [int(x) for x in ADMIN_IDS] or uid == int(OWNER_ID)
    except Exception:
        return False


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
    try:
        from core.notifier import notify_owner
        await notify_owner(
            context.application,
            f"⚙️ *ADMIN HARAKATI:*\n👤 Admin: *{escape_md(query.from_user.full_name)}* (`{user_id}`)\n📌 Panel ochildi: `⚙️ Admin Paneli`"
        )
    except Exception:
        pass
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
        ww_hp = "500,000"
        if ww_event:
            ww_data = json.loads(ww_event.data_json)
            ww_hp = f"{ww_data.get('hp', 500000):,}"

        # Urush holati
        war_st = await crud.get_war_status(session)
        if war_st["is_active"]:
            rem_str = ""
            if war_st.get("remaining_seconds") is not None and war_st["remaining_seconds"] > 0:
                rem_h = war_st["remaining_seconds"] // 3600
                rem_m = (war_st["remaining_seconds"] % 3600) // 60
                rem_str = f" ({rem_h}s {rem_m}d qoldi)" if rem_h > 0 else f" ({rem_m} daq qoldi)"
            war_status_str = f"🟢 Ochiq (Urush ketmoqda){rem_str}"
        else:
            war_status_str = "🔴 Yopiq (Sulh davri)"

        text = (
            f"👑 **WESTEROS OLIY ADMINISTRATOR PANELI**\n\n"
            f"📊 **SERVER STATISTIKASI:**\n"
            f"• 👥 Jami Lordlar: **{total_users}** ta\n"
            f"• 🪙 Umumiy Xazina: **{total_gold:,}** oltin\n"
            f"• ⚔️ Faol Yurishlar: **{active_marches}** ta\n"
            f"• ⚔️ Harbiy Holat: **{war_status_str}**\n"
            f"• 🐉 Tirik Ajdarlar: **{total_dragons}** ta\n"
            f"• ❄️ Tun Qiroli HP: **{ww_hp}** / 500,000\n\n"
            f"Boshqaruv bo'limini tanlang:"
        )

        target_user_id = target.effective_user.id if is_message else target.from_user.id
        buttons = [
            [InlineKeyboardButton("👥 O'yinchilarni Boshqarish (User Manager)", callback_data="admin_users_list:0")],
            [InlineKeyboardButton("👑 Xonadon Lordlarini Tayinlash", callback_data="admin_lords_menu")],
            [InlineKeyboardButton("🏰 Xonadonlar va G'aznalar", callback_data="admin_houses_list")],
            [InlineKeyboardButton("🏯 Qalalar va Mintaqalar (Castles)", callback_data="admin_castles_list:0")],
            [InlineKeyboardButton("🏆 Egallangan Qal'alar (O'yinchilar bo'yicha)", callback_data="admin_player_castles:0")],
            [InlineKeyboardButton("⚔️ Harbiy Holat & Urush Boshqaruvi", callback_data="admin_war_control")],
            [InlineKeyboardButton("🏇 Ritsarlar Turniri Boshqaruvi", callback_data="admin_tourney_menu")],
            [InlineKeyboardButton("🐉 Barcha Ajdarlar (Dragon Manager)", callback_data="admin_dragons_list:0")],
            [InlineKeyboardButton("❄️ Global Hodisalar & Tun Qiroli", callback_data="admin_events_menu")],
            [InlineKeyboardButton("🎁 Barchaga Ommaviy Sovg'a (+2000🪙)", callback_data="admin_mass_gift")],
            [InlineKeyboardButton("🔄 Barcha Kunlik Limitlarni Yangilash", callback_data="admin_reset_all_limits")],
            [InlineKeyboardButton("📢 Global E'lon (Broadcast)", callback_data="admin_broadcast_info")],
            [InlineKeyboardButton("🛡️ Adminlar Ro'yxati & Huquqlar", callback_data="admin_admins_list")],
        ]

        if is_admin(target_user_id) or str(target_user_id) == str(OWNER_ID):
            buttons.append([InlineKeyboardButton("👑 MAVSUMNI TUGATISH & YANGI MAVSUM (RESET)", callback_data="admin_season_menu")])
            buttons.append([InlineKeyboardButton("⚠️ O'YINNI 0 QILISH (MAVSUM RESET)", callback_data="admin_wipe_ask")])

        buttons.append([InlineKeyboardButton("🔙 Bosh Menyu", callback_data="menu_main")])

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
        user = await crud.get_user_any(session, user_id)
        if not user:
            await query.edit_message_text("❌ O'yinchi topilmadi.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_users_list:0")]]))
            return

        house = await session.get(models.House, user.house_id) if user.house_id else None
        h_name = house.name if house else "Xonadonsiz"
        army = await crud.get_user_army(session, user.id)
        dragon = await crud.get_user_dragon(session, user.id)
        drg_str = f"{dragon.name} ({dragon.stage})" if dragon else "Mavjud emas"
        char_name = user.characters[0].name if user.characters else user.full_name
        title_line = f"• 🎖️ Sharafli Unvon: **{escape_md(user.title)}**\n" if user.title else "• 🎖️ Sharafli Unvon: _Biriktirilmagan_\n"

        text = (
            f"👤 **LORD MA'LUMOTLARI: {escape_md(char_name)}**\n\n"
            f"• Telegram ID: `{user.telegram_id}`\n"
            f"• Username: @{escape_md(user.username or 'yoq')}\n"
            f"• 🏰 Xonadon: **{escape_md(h_name)}**\n"
            f"• 👑 Lavozim: **{user.rank}** | Daraja: **{user.level}**\n"
            f"{title_line}"
            f"• 🏆 Prestige: **{user.prestige:,}** | XP: **{user.xp:,}**\n\n"
            f"💰 **RESURSLAR:**\n"
            f"• 🪙 Oltin: **{user.gold:,}**\n"
            f"• 🌾 Oziq-ovqat: **{user.food:,}**\n"
            f"• ⛓️ Temir: **{user.iron:,}**\n\n"
            f"⚔️ **ARMIYA:**\n"
            f"• 🗡️ Piyoda: {army.infantry:,} | 🏹 Kamonchi: {army.archers:,}\n"
            f"• 🏇 Otliq: {army.cavalry:,} | 🔱 Nayzachi: {army.spearmen:,} | 🛡️ Maxsus: {army.special_troops:,}\n\n"
            f"🐉 **AJDAR:** {drg_str}\n\n"
            f"Boshqaruv amalini tanlang:"
        )

        buttons = [
            [
                InlineKeyboardButton("💰 +5k", callback_data=f"adm_act:{user.id}:gold:5000"),
                InlineKeyboardButton("💰 -2k", callback_data=f"adm_act:{user.id}:gold:-2000"),
                InlineKeyboardButton("💰 -5k", callback_data=f"adm_act:{user.id}:gold:-5000"),
            ],
            [
                InlineKeyboardButton("🌾 +10k", callback_data=f"adm_act:{user.id}:food:10000"),
                InlineKeyboardButton("🌾 -5k", callback_data=f"adm_act:{user.id}:food:-5000"),
                InlineKeyboardButton("🌾 -10k", callback_data=f"adm_act:{user.id}:food:-10000"),
            ],
            [
                InlineKeyboardButton("⛓️ +5k", callback_data=f"adm_act:{user.id}:iron:5000"),
                InlineKeyboardButton("⛓️ -2k", callback_data=f"adm_act:{user.id}:iron:-2000"),
                InlineKeyboardButton("⛓️ -5k", callback_data=f"adm_act:{user.id}:iron:-5000"),
            ],
            [
                InlineKeyboardButton("🆙 +1 Daraja", callback_data=f"adm_act:{user.id}:level:1"),
                InlineKeyboardButton("⬆️ +1,000 XP", callback_data=f"adm_act:{user.id}:xp:1000"),
            ],
            [
                InlineKeyboardButton("👑 Lord (King)", callback_data=f"adm_act:{user.id}:rank:king"),
                InlineKeyboardButton("⚔️ Qo'mondon", callback_data=f"adm_act:{user.id}:rank:commander"),
                InlineKeyboardButton("🛡️ Ritsar", callback_data=f"adm_act:{user.id}:rank:knight"),
            ],
            [
                InlineKeyboardButton("🎖️ Sharafli Unvon Berish (Title)", callback_data=f"adm_u_titles:{user.id}"),
            ],
            [
                InlineKeyboardButton("🏰 Xonadonni O'zgartirish", callback_data=f"adm_u_house_pick:{user.id}:0"),
                InlineKeyboardButton("🚪 Xonadondan Chiqarish", callback_data=f"adm_u_remhouse:{user.id}"),
            ],
            [
                InlineKeyboardButton("⚔️ Armiyasini Boshqarish (Qo'shin berish)", callback_data=f"adm_u_army_menu:{user.id}"),
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
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


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
        user = await crud.get_user_any(session, user_id)
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
        elif action == "xp":
            user.xp = max(0, user.xp + int(val))
            msg = f"XP o'zgartirildi: {user.xp:,}"
        elif action == "level":
            user.level = max(1, user.level + int(val))
            msg = f"Daraja o'zgartirildi: {user.level}"
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


async def admin_user_house_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'yinchini boshqa xonadonga o'tkazish uchun xonadon tanlash"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    user_id = int(parts[1])
    offset = int(parts[2]) if len(parts) > 2 else 0

    page_size = 8
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_any(session, user_id)
        if not user:
            await query.answer("O'yinchi topilmadi!", show_alert=True)
            return

        total_houses_res = await session.execute(select(func.count(models.House.id)))
        total_houses = total_houses_res.scalar() or 0

        res = await session.execute(
            select(models.House).order_by(models.House.name).offset(offset).limit(page_size)
        )
        houses = res.scalars().all()

        text = (
            f"🏰 **O'YINCHINI BOSHQA XONADONGA O'TKAZISH**\n\n"
            f"👤 O'yinchi: **{escape_md(user.full_name)}**\n"
            f"Yangi xonadonni tanlang:\n"
        )

        buttons = []
        for h in houses:
            is_curr = " (Hozirgi)" if user.house_id == h.id else ""
            buttons.append([InlineKeyboardButton(f"{h.emoji} {h.name}{is_curr}", callback_data=f"adm_u_house_do:{user.id}:{h.id}")])

        nav_row = []
        if offset >= page_size:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"adm_u_house_pick:{user.id}:{offset - page_size}"))
        if offset + page_size < total_houses:
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"adm_u_house_pick:{user.id}:{offset + page_size}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 O'yinchiga Qaytish", callback_data=f"admin_u_detail:{user.id}")])

        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


async def admin_user_house_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'yinchini tanlangan xonadonga ko'chirish ijrosi"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    user_id = int(parts[1])
    new_house_id = int(parts[2])

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.admin_transfer_user_house(session, user_id, new_house_id)
        if ok:
            user = await crud.get_user_any(session, user_id)
            house = await session.get(models.House, new_house_id)
            if user and house:
                try:
                    await context.bot.send_message(
                        chat_id=user.telegram_id,
                        text=(
                            f"🏰 **XONADON O'ZGARDI!**\n\n"
                            f"Oliy Administrator sizni **{house.emoji} {house.name}** xonadoniga o'tkazdi!"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

    try:
        await query.answer(msg, show_alert=True)
    except Exception:
        pass

    query.data = f"admin_u_detail:{user_id}"
    await admin_user_detail_callback(update, context)


async def admin_user_remhouse_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'yinchini xonadondan chiqarib yuborish (Xonadonsiz qilish)"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    user_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        ok, msg = await crud.admin_remove_user_from_house(session, user_id)

    try:
        await query.answer(msg, show_alert=True)
    except Exception:
        pass

    query.data = f"admin_u_detail:{user_id}"
    await admin_user_detail_callback(update, context)


async def admin_user_army_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'yinchi armiyasini tahrirlash menyusi"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    user_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_any(session, user_id)
        if not user:
            await query.answer("O'yinchi topilmadi!", show_alert=True)
            return

        army = await crud.get_user_army(session, user.id)
        text = (
            f"⚔️ **O'YINCHI ARMIYASINI BOSHQARISH**\n\n"
            f"👤 O'yinchi: **{escape_md(user.full_name)}**\n\n"
            f"• 🗡️ Piyoda (Infantry): **{army.infantry:,}** ta\n"
            f"• 🏹 Kamonchi (Archers): **{army.archers:,}** ta\n"
            f"• 🏇 Otliq (Cavalry): **{army.cavalry:,}** ta\n"
            f"• 🔱 Nayzachi (Spearmen): **{army.spearmen:,}** ta\n"
            f"• 🛡️ Maxsus Qo'shin (Special): **{army.special_troops:,}** ta\n\n"
            f"Qo'shin turini tanlab miqdorini oshiring yoki kamaytiring:"
        )

        buttons = [
            [
                InlineKeyboardButton("🗡️ +100 Piyoda", callback_data=f"adm_u_army_act:{user.id}:infantry:100"),
                InlineKeyboardButton("🗡️ -100 Piyoda", callback_data=f"adm_u_army_act:{user.id}:infantry:-100"),
            ],
            [
                InlineKeyboardButton("🏹 +100 Kamonchi", callback_data=f"adm_u_army_act:{user.id}:archers:100"),
                InlineKeyboardButton("🏹 -100 Kamonchi", callback_data=f"adm_u_army_act:{user.id}:archers:-100"),
            ],
            [
                InlineKeyboardButton("🏇 +50 Otliq", callback_data=f"adm_u_army_act:{user.id}:cavalry:50"),
                InlineKeyboardButton("🏇 -50 Otliq", callback_data=f"adm_u_army_act:{user.id}:cavalry:-50"),
            ],
            [
                InlineKeyboardButton("🔱 +50 Nayzachi", callback_data=f"adm_u_army_act:{user.id}:spearmen:50"),
                InlineKeyboardButton("🔱 -50 Nayzachi", callback_data=f"adm_u_army_act:{user.id}:spearmen:-50"),
            ],
            [
                InlineKeyboardButton("🛡️ +20 Maxsus", callback_data=f"adm_u_army_act:{user.id}:special_troops:20"),
                InlineKeyboardButton("🛡️ -20 Maxsus", callback_data=f"adm_u_army_act:{user.id}:special_troops:-20"),
            ],
            [
                InlineKeyboardButton("⚡ Hammasiga +500 tadan qo'shish", callback_data=f"adm_u_army_act:{user.id}:all:500"),
            ],
            [InlineKeyboardButton("🔙 Lord Kartasiga Qaytish", callback_data=f"admin_u_detail:{user.id}")],
        ]

        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


async def admin_user_army_act_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Armiya miqdorini o'zgartirish ijrosi"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    user_id = int(parts[1])
    unit_type = parts[2]
    val = int(parts[3])

    async with AsyncSessionLocal() as session:
        kwargs = {}
        if unit_type == "all":
            kwargs = {
                "infantry": val,
                "archers": val,
                "cavalry": val,
                "spearmen": val,
                "special_troops": val,
            }
        else:
            kwargs[unit_type] = val

        ok, msg = await crud.admin_set_user_army(session, user_id, add_mode=True, **kwargs)

    try:
        await query.answer(msg, show_alert=True)
    except Exception:
        pass

    query.data = f"adm_u_army_menu:{user_id}"
    await admin_user_army_menu_callback(update, context)


# ============================================================
# HOUSE MANAGEMENT
# ============================================================

async def admin_houses_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadonlar ro'yxati va xazinasi (sahifalangan)"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    offset = 0
    if ":" in query.data:
        try:
            offset = int(query.data.split(":")[1])
        except Exception:
            offset = 0

    page_size = 8
    async with AsyncSessionLocal() as session:
        total_res = await session.execute(select(func.count(models.House.id)))
        total_houses = total_res.scalar() or 0

        res = await session.execute(
            select(models.House).order_by(desc(models.House.prestige)).offset(offset).limit(page_size)
        )
        houses = res.scalars().all()

        buttons = []
        for h in houses:
            buttons.append([InlineKeyboardButton(f"{h.emoji} {h.name} (💰{h.gold:,} 🏆{h.prestige})", callback_data=f"adm_h_detail:{h.id}")])

        nav_row = []
        if offset >= page_size:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_houses_list:{offset - page_size}"))
        if offset + page_size < total_houses:
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"admin_houses_list:{offset + page_size}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])

        text = (
            f"🏰 **XONADONLAR VA G'AZNALAR BOSHQARUVI ({offset + 1}-{min(offset + page_size, total_houses)} / {total_houses}):**\n\n"
            f"Xonadonni tanlang:"
        )
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


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
            [InlineKeyboardButton("🔙 Xonadonlar", callback_data="admin_houses_list:0")],
        ]
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


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
    """Barcha xonadonlar va ularning Lordlari ro'yxati (sahifalangan)"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    offset = 0
    if ":" in query.data:
        try:
            offset = int(query.data.split(":")[1])
        except Exception:
            offset = 0

    page_size = 8
    async with AsyncSessionLocal() as session:
        total_houses_res = await session.execute(select(func.count(models.House.id)))
        total_houses = total_houses_res.scalar() or 0

        res = await session.execute(
            select(models.House).order_by(models.House.id).offset(offset).limit(page_size)
        )
        houses = res.scalars().all()

        text = (
            f"👑 **WESTEROS XONADON LORDLARI BOSHQARUVI ({offset + 1}-{min(offset + page_size, total_houses)} / {total_houses})**\n\n"
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

            text += f"• {h.emoji} **{escape_md(h.name)}**: {escape_md(lord_label)}\n"
            buttons.append([InlineKeyboardButton(f"{h.emoji} {h.name} — {lord_label}", callback_data=f"adm_lord_h:{h.id}")])

        nav_row = []
        if offset >= page_size:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"adm_lords_page:{offset - page_size}"))
        if offset + page_size < total_houses:
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"adm_lords_page:{offset + page_size}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


async def show_admin_lord_house_detail(query, house_id: int):
    """Tanlangan xonadon Lordi boshqaruv kartasini ko'rsatish"""
    async with AsyncSessionLocal() as session:
        house = await session.get(models.House, house_id)
        if not house:
            try:
                await query.answer("Xonadon topilmadi!", show_alert=True)
            except Exception:
                pass
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
                f"• Username: @{escape_md(lord_user.username or 'yoq')}\n"
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
            [InlineKeyboardButton("👑 Xonadon A'zolaridan Tayinlash", callback_data=f"adm_pick_lord:{house.id}:0")],
            [InlineKeyboardButton("🌐 Barcha O'yinchilardan Tanlash", callback_data=f"adm_pick_all_lord:{house.id}:0")],
        ]
        if house.lord_user_id:
            buttons.append([InlineKeyboardButton("🚫 Lordni Bo'shatish (Vakant Qilish)", callback_data=f"adm_dismiss_lord:{house.id}")])

        if total_votes > 0:
            buttons.append([InlineKeyboardButton("🗳️ Saylov Ovozlarini Tozalash (0)", callback_data=f"adm_reset_votes:{house.id}")])

        buttons.append([InlineKeyboardButton("🏰 Xonadon G'aznasi & Resurslar", callback_data=f"adm_h_detail:{house.id}")])
        buttons.append([InlineKeyboardButton("🔙 Xonadonlar Ro'yxati", callback_data="admin_lords_menu")])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_lord_house_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan xonadon Lordi boshqaruv menyusi"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    if not is_admin(query.from_user.id):
        return

    house_id = int(query.data.split(":")[1])
    await show_admin_lord_house_detail(query, house_id)


async def admin_pick_lord_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadon a'zolaridan Lord tanlash (sahifalangan)"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
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
            f"👑 **{house.emoji} {house.name} XONADONIGA LORD TAYINLASH**\n"
            f"*(Ushbu xonadon a'zolari ro'yxati)*\n\n"
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

        buttons.append([InlineKeyboardButton("🌐 Barcha O'yinchilardan Tanlash", callback_data=f"adm_pick_all_lord:{house.id}:0")])
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"adm_lord_h:{house.id}")])

        if not page_members:
            text += "❌ Bu xonadonda hozircha birorta ham a'zo mavjud emas!\n*(Quyidagi 'Barcha O'yinchilardan Tanlash' tugmasi orqali xohlagan o'yinchini tayinlashingiz mumkin)*\n"

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_pick_all_lord_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha o'yinchilardan Lord tanlash (sahifalangan)"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    house_id = int(parts[1])
    offset = int(parts[2]) if len(parts) > 2 else 0

    async with AsyncSessionLocal() as session:
        house = await session.get(models.House, house_id)
        if not house:
            return

        res = await session.execute(
            select(models.User).order_by(models.User.id).offset(offset).limit(6)
        )
        users = res.scalars().all()

        count_res = await session.execute(select(func.count(models.User.id)))
        total_users = count_res.scalar() or 0

        text = (
            f"👑 **{house.emoji} {house.name} XONADONIGA LORD TAYINLASH**\n"
            f"*(Barcha o'yinchilar ro'yxati)*\n\n"
            f"O'yinchini tanlang. U avtomatik ushbu xonadonga o'tkazilib, **Lord (King)** etib tayinlanadi:\n\n"
        )

        buttons = []
        for u in users:
            char_name = u.characters[0].name if u.characters else (u.full_name or f"User {u.id}")
            is_current = (house.lord_user_id == u.telegram_id) or (u.house_id == house.id and u.rank == "king")
            badge = "👑 (Lord)" if is_current else "👉"
            buttons.append([InlineKeyboardButton(
                f"{badge} {char_name} ({escape_md(u.full_name)[:12]}, Lvl {u.level})",
                callback_data=f"adm_conf_lord:{house.id}:{u.id}"
            )])

        nav_row = []
        if offset >= 6:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"adm_pick_all_lord:{house.id}:{offset - 6}"))
        if offset + 6 < total_users:
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"adm_pick_all_lord:{house.id}:{offset + 6}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"adm_lord_h:{house.id}")])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))



async def admin_conf_lord_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lord etib tayinlashni tasdiqlash sahifasi"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    house_id = int(parts[1])
    target_user_id = int(parts[2])

    async with AsyncSessionLocal() as session:
        house = await session.get(models.House, house_id)
        user = await crud.get_user_any(session, target_user_id)
        if not house or not user:
            try:
                await query.answer("Ma'lumot topilmadi!", show_alert=True)
            except Exception:
                pass
            return

        char_name = user.characters[0].name if user.characters else user.full_name

        text = (
            f"👑 **LORD TAYINLASHNI TASDIQLASH**\n\n"
            f"🏰 Xonadon: **{house.emoji} {house.name}**\n"
            f"👤 Nomzod: **{char_name}** ({escape_md(user.full_name)})\n"
            f"🆔 Telegram ID: `{user.telegram_id}`\n"
            f"⚔️ Daraja: **{user.level}** | Hozirgi unvon: **{user.rank}**\n\n"
            f"⚠️ Haqiqatan ham ushbu o'yinchini {house.name} xonadoni Lordi (King) etib tayinlaysizmi?\n"
            f"(Oldingi Lord mavjud bo'lsa, u avtomatik ravishda oddiy a'zolikka o'tkaziladi)"
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
            user = await crud.get_user_any(session, target_user_id)
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

    try:
        await query.answer(msg, show_alert=True)
    except Exception:
        pass
    await show_admin_lord_house_detail(query, house_id)


async def admin_dismiss_lord_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lordni lavozimidan ozod etish (bo'shatish)"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    house_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        ok, msg = await crud.admin_dismiss_house_lord(session, house_id)

    try:
        await query.answer(msg, show_alert=True)
    except Exception:
        pass
    await show_admin_lord_house_detail(query, house_id)


async def admin_reset_votes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saylov ovozlarini tozalash"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    house_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        ok, msg = await crud.admin_reset_house_election_votes(session, house_id)

    try:
        await query.answer(msg, show_alert=True)
    except Exception:
        pass
    await show_admin_lord_house_detail(query, house_id)


# ============================================================
# GLOBAL EVENTS & BOSS MANAGEMENT
# ============================================================

async def admin_events_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global hodisalar boshqaruvi"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(models.EventState).where(models.EventState.event_name == "plague")
        )
        plague_ev = res.scalar_one_or_none()
        plague_active = plague_ev.is_active if plague_ev else True

    plague_status_text = "🟢 Faol (Westeros bo'ylab tarqalmoqda)" if plague_active else "🔴 To'xtatilgan (Nofaol)"

    text = (
        "❄️ **GLOBAL HODISALAR VA BOSSLAR BOSHQARUVI**\n\n"
        f"☣️ **Vabo Epidemiyasi:** {plague_status_text}\n\n"
        "Kerakli amalni tanlang:"
    )
    buttons = [
        [InlineKeyboardButton("❄️ Tun Qiroli HP: 500,000 ga tiklash", callback_data="adm_ev_act:nk_reset")],
        [InlineKeyboardButton("❄️ Tun Qiroli HP: 5,000 ga tushirish (Sinov)", callback_data="adm_ev_act:nk_low")],
    ]

    if plague_active:
        buttons.append([InlineKeyboardButton("🛑 Vabo Epidemiyasini To'xtatish", callback_data="adm_ev_act:plague_stop")])
        buttons.append([InlineKeyboardButton("📢 Vabo haqida e'lon yuborish", callback_data="adm_ev_act:plague_bcast")])
    else:
        buttons.append([InlineKeyboardButton("☣️ Vabo Epidemiyasini Boshlash", callback_data="adm_ev_act:plague_start")])

    buttons.append([InlineKeyboardButton("🥷 Qaroqchilar Hujumini e'lon qilish", callback_data="adm_ev_act:bandits")])
    buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])

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

        plague_res = await session.execute(
            select(models.EventState).where(models.EventState.event_name == "plague")
        )
        plague_ev = plague_res.scalar_one_or_none()

        if act == "nk_reset":
            if ww_event:
                ww_event.data_json = json.dumps({"hp": 500000, "max_hp": 500000, "status": "active"})
                await session.commit()
            msg = "❄️ Tun Qiroli armiyasi to'liq 500,000 ga tiklandi!"
        elif act == "nk_low":
            if ww_event:
                ww_event.data_json = json.dumps({"hp": 5000, "status": "active"})
                await session.commit()
            msg = "❄️ Tun Qiroli armiyasi 5,000 HP ga tushirildi!"
        elif act in ["plague", "plague_start"]:
            if not plague_ev:
                plague_ev = models.EventState(event_name="plague", data_json=json.dumps({"status": "active", "severity": "heavy"}), is_active=True)
                session.add(plague_ev)
            else:
                plague_ev.is_active = True
                plague_ev.started_at = datetime.utcnow()
            await session.commit()
            msg = "☣️ Mintaqaviy vabo epidemiyasi boshlandi va barcha lordlarga xabar yuborildi!"
            users_res = await session.execute(select(models.User.telegram_id))
            all_ids = users_res.scalars().all()
            bcast_text = (
                "☣️ **OGOHLANTIRISH: WESTEROS BO'YLAB VABO EPIDEMIYASI BOSHLANDI!**\n\n"
                "Qal'alar, qishloqlar va bozorlarda qora o'lat tarqaldi!\n"
                "Barcha Lordlar va jangchilar ehtiyot choralarini ko'rsin. Har bir o'yinchi kuniga 2 martagacha tabiblar yordamida o'z xalqini davolashi mumkin!"
            )
            async def _bg_plague_bcast(bot, ids, txt):
                for tg_id in ids:
                    try:
                        await bot.send_message(chat_id=tg_id, text=txt, parse_mode="Markdown")
                        await asyncio.sleep(0.04)
                    except Exception:
                        pass
            asyncio.create_task(_bg_plague_bcast(context.bot, all_ids, bcast_text))
        elif act == "plague_stop":
            if not plague_ev:
                plague_ev = models.EventState(event_name="plague", data_json=json.dumps({"status": "stopped"}), is_active=False)
                session.add(plague_ev)
            else:
                plague_ev.is_active = False
            await session.commit()
            msg = "🛑 Vabo epidemiyasi to'xtatildi!"
        elif act == "plague_bcast":
            msg = "📢 Vabo haqidagi ogohlantirish barcha o'yinchilarga jo'natilmoqda!"
            users_res = await session.execute(select(models.User.telegram_id))
            all_ids = users_res.scalars().all()
            bcast_text = (
                "☣️ **OGOHLANTIRISH: WESTEROS BO'YLAB VABO EPIDEMIYASI DAVOM ETMOQDA!**\n\n"
                "Mintaqangizni qora o'latdan asrang. Maesterlar yordamida dorilar tayyorlang yoki karantin joriy qiling!"
            )
            async def _bg_plague_reminder(bot, ids, txt):
                for tg_id in ids:
                    try:
                        await bot.send_message(chat_id=tg_id, text=txt, parse_mode="Markdown")
                        await asyncio.sleep(0.04)
                    except Exception:
                        pass
            asyncio.create_task(_bg_plague_reminder(context.bot, all_ids, bcast_text))
        elif act == "bandits":
            msg = "🥷 Qaroqchilar hujumi boshlandi va barcha lordlarga xabar yuborildi!"
            users_res = await session.execute(select(models.User.telegram_id))
            all_ids = users_res.scalars().all()
            bcast_text = (
                "🥷 **OGOHLANTIRISH: QAROQCHILAR VA ISYONCHILAR BOSQINI!**\n\n"
                "Westerosning barcha savdo karvonlari va qal'alari xavf ostida!\n"
                "Qal'angiz garnizonini mustahkamlang va qaroqchilarga qarshi pistirma uyushtiring!"
            )
            async def _bg_bandits_bcast(bot, ids, txt):
                for tg_id in ids:
                    try:
                        await bot.send_message(chat_id=tg_id, text=txt, parse_mode="Markdown")
                        await asyncio.sleep(0.04)
                    except Exception:
                        pass
            asyncio.create_task(_bg_bandits_bcast(context.bot, all_ids, bcast_text))
        else:
            msg = "Amal bajarildi."

    try:
        await query.answer(f"✅ {msg}", show_alert=True)
    except Exception:
        pass
    await admin_events_menu_callback(update, context)


# ============================================================
# WAR MODE / HARBIY HOLAT BOSHQARUVI
# ============================================================

async def admin_war_control_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin paneli: Urush rejimini boshqarish menyusi"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    async with AsyncSessionLocal() as session:
        war_st = await crud.get_war_status(session)

    is_active = war_st["is_active"]
    rem_seconds = war_st.get("remaining_seconds")

    if is_active:
        status_line = "🟢 **URUSH REJIMI: FAOLLASHTIRILGAN (OCHIQ)**"
        attack_line = "⚔️ Qal'alarga hujumlar: **OCHIQ (Ruxsat berilgan)**"
        if rem_seconds is not None and rem_seconds > 0:
            rem_h = rem_seconds // 3600
            rem_m = (rem_seconds % 3600) // 60
            rem_s = rem_seconds % 60
            t_str = f"{rem_h} soat {rem_m} daqiqa" if rem_h > 0 else f"{rem_m} daqiqa {rem_s} soniya"
            timer_line = f"⏱️ Qolgan vaqt: **{t_str}**"
        else:
            timer_line = "⏱️ Muddat: **Cheksiz (Admin tomonidan qo'lda yopiladi)**"
    else:
        status_line = "🔴 **URUSH REJIMI: TO'XTATILGAN (SULH / TINCHLIK)**"
        attack_line = "🕊️ Qal'alarga hujumlar: **BLOKLANGAN (Taqiqlangan)**"
        timer_line = "⏱️ Holat: **Tinchlik davri amal qilmoqda**"

    opened_at_str = war_st.get("opened_at") or "Noma'lum"
    if "T" in opened_at_str:
        opened_at_str = opened_at_str.replace("T", " ")[:16] + " UTC"

    text = (
        f"⚔️ **WESTEROS HARBIY HOLAT & URUSH BOSHQARUVI**\n\n"
        f"📊 **JORIY HOLAT:**\n"
        f"• {status_line}\n"
        f"• {attack_line}\n"
        f"• {timer_line}\n"
        f"• 🕒 So'nggi o'zgarish: `{opened_at_str}`\n\n"
        f"📜 **QOIDALAR VA QO'LLANMA:**\n"
        f"• **Urush Ochiq:** Barcha o'yinchilar dushman qal'alariga harbiy yurish qila oladi.\n"
        f"• **Urush Yopiq:** O'yinchilar qal'alarga hujum qila olmaydi. Faqat askar yollash, o'z qal'asini mustahkamlash va tayyorgarlik ko'rish mumkin.\n"
        f"• **Taymer bilan ochish:** Belgilangan vaqt (masalan: 2 soat) tugashi bilan bot avtomatik urushni yopadi va sulh e'lonini barcha o'yinchilarga jo'natadi!\n\n"
        f"Kerakli amalni tanlang:"
    )

    buttons = []
    if not is_active:
        # Urush yopiq - ochish tugmalari
        buttons.append([
            InlineKeyboardButton("⏱️ 2 Soatga Ochish (Tavsiya)", callback_data="adm_war_set:2.0:bcast"),
        ])
        buttons.append([
            InlineKeyboardButton("⏱️ 1 Soatga", callback_data="adm_war_set:1.0:bcast"),
            InlineKeyboardButton("⏱️ 3 Soatga", callback_data="adm_war_set:3.0:bcast"),
            InlineKeyboardButton("⏱️ 4 Soatga", callback_data="adm_war_set:4.0:bcast"),
        ])
        buttons.append([
            InlineKeyboardButton("🟢 Doimiy Ochish (Qo'lda yopiladi)", callback_data="adm_war_set:0:bcast"),
        ])
        buttons.append([
            InlineKeyboardButton("🔕 E'lonsiz (Jimjit) 2 Soatga Ochish", callback_data="adm_war_set:2.0:silent"),
        ])
    else:
        # Urush ochiq - yopish va uzaytirish tugmalari
        buttons.append([
            InlineKeyboardButton("🔴 Urushni Yopish (Sulh e'lon qilish)", callback_data="adm_war_set:off:bcast"),
        ])
        buttons.append([
            InlineKeyboardButton("🔕 Jimjit Yopish (E'lonsiz)", callback_data="adm_war_set:off:silent"),
        ])
        buttons.append([
            InlineKeyboardButton("➕ 1 Soat Uzaytirish", callback_data="adm_war_add:1.0"),
            InlineKeyboardButton("➕ 2 Soat Uzaytirish", callback_data="adm_war_add:2.0"),
        ])
        buttons.append([
            InlineKeyboardButton("📢 Urush E'lonini Hamma O'yinchilarga Yuborish", callback_data="adm_war_bcast_now"),
        ])

    buttons.append([
        InlineKeyboardButton("🔄 Yangilash", callback_data="admin_war_control"),
        InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel"),
    ])

    markup = InlineKeyboardMarkup(buttons)
    if query and query.message:
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            clean = text.replace("*", "").replace("_", "").replace("`", "")
            await query.edit_message_text(clean, parse_mode=None, reply_markup=markup)
    elif update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def admin_war_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Urush rejimini o'zgartirish callback handler"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    alert_msg = ""
    async with AsyncSessionLocal() as session:
        if data.startswith("adm_war_set:"):
            parts = data.split(":")
            mode = parts[1]
            bcast = parts[2] if len(parts) > 2 else "bcast"

            if mode == "off":
                await crud.set_war_status(session, is_active=False, opened_by=user_id)
                alert_msg = "✅ Urush to'xtatildi! Vesterosda sulh davri boshlandi."
                if bcast == "bcast":
                    bcast_text = (
                        "🕊️ **QIROL FARMONI: UMUMIY SULH (TINCHLIK) E'LON QILINDI!**\n\n"
                        "Qirolning oliy farmoniga ko'ra Vesterosda harbiy harakatlar to'xtatildi.\n"
                        "Barcha dushman qal'alariga hujumlar va qamallar yopildi.\n\n"
                        "🛡️ Endi armiyangizni tiklang, don va temir to'plang, o'z qal'angiz devorlarini mustahkamlang!\n"
                        "Keyingi harbiy yurishlar ochilishi haqida botda xabar beriladi."
                    )
                    users_res = await session.execute(select(models.User.telegram_id))
                    all_ids = users_res.scalars().all()
                    for tg_id in all_ids:
                        try:
                            await context.bot.send_message(chat_id=tg_id, text=bcast_text, parse_mode="Markdown")
                        except Exception:
                            pass
            else:
                hours = float(mode)
                await crud.set_war_status(session, is_active=True, duration_hours=hours if hours > 0 else None, opened_by=user_id)
                dur_text = f"{int(hours)} soatga" if hours > 0 else "doimiy"
                alert_msg = f"✅ Urush rejimi {dur_text} muvaffaqiyatli ochildi!"
                if bcast == "bcast":
                    dur_banner = f" (⏱️ Davomiyligi: **{int(hours)} soat**)" if hours > 0 else ""
                    bcast_text = (
                        f"⚔️ **QIROL FARMONI: HARBIY HOLAT E'LON QILINDI!**{dur_banner}\n\n"
                        f"Vesteros uzra urush darvozalari ochildi!\n"
                        f"Barcha Lordlar va jangchilar o'z qo'shinlarini dushman qal'alariga yurishga jo'natishi mumkin. Qon va shon-sharaf sizniki bo'lsin! 🚩\n\n"
                        f"*(Xaritadan dushman qal'asini tanlang va yurish boshlang!)*"
                    )
                    users_res = await session.execute(select(models.User.telegram_id))
                    all_ids = users_res.scalars().all()
                    for tg_id in all_ids:
                        try:
                            await context.bot.send_message(chat_id=tg_id, text=bcast_text, parse_mode="Markdown")
                        except Exception:
                            pass

        elif data.startswith("adm_war_add:"):
            hours = float(data.split(":")[1])
            await crud.extend_war_duration(session, additional_hours=hours)
            alert_msg = f"✅ Urush vaqti +{int(hours)} soatga uzaytirildi!"

        elif data == "adm_war_bcast_now":
            war_st = await crud.get_war_status(session)
            if war_st["is_active"]:
                rem_sec = war_st.get("remaining_seconds")
                dur_str = ""
                if rem_sec and rem_sec > 0:
                    dur_str = f" (Qolgan vaqt: {rem_sec // 3600} soat {(rem_sec % 3600) // 60} daqiqa)"
                bcast_text = (
                    f"⚔️ **QIROL FARMONI: HARBIY HOLAT DAVOM ETMOQDA!**{dur_str}\n\n"
                    f"Qal'alarga yurishlar davom etmoqda. O'z xonadoningiz bayrog'ini baland ko'taring!"
                )
                users_res = await session.execute(select(models.User.telegram_id))
                all_ids = users_res.scalars().all()
                for tg_id in all_ids:
                    try:
                        await context.bot.send_message(chat_id=tg_id, text=bcast_text, parse_mode="Markdown")
                    except Exception:
                        pass
                alert_msg = "📢 Barcha o'yinchilarga urush eslatmasi yuborildi!"
            else:
                alert_msg = "Urush hozir yopiq."

    try:
        await query.answer(alert_msg, show_alert=True)
    except Exception:
        pass

    await admin_war_control_callback(update, context)


async def set_war_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/setwar on [hours] yoki /setwar off buyrug'i"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    args = context.args
    if not args:
        await admin_war_control_callback(update, context)
        return

    action = args[0].lower()
    async with AsyncSessionLocal() as session:
        if action in ["on", "open", "start", "ochish"]:
            hours = 2.0
            if len(args) > 1 and args[1].replace(".", "", 1).isdigit():
                hours = float(args[1])
            await crud.set_war_status(session, is_active=True, duration_hours=hours if hours > 0 else None, opened_by=user_id)
            await update.message.reply_text(
                f"✅ **Urush rejimi {int(hours) if hours > 0 else 'cheksiz'} soatga ochildi!**\nBoshqaruv uchun `/setwar` yozing.",
                parse_mode="Markdown"
            )
        elif action in ["off", "close", "stop", "yopish"]:
            await crud.set_war_status(session, is_active=False, opened_by=user_id)
            await update.message.reply_text(
                "✅ **Urush to'xtatildi! Sulh rejimi faollashtirildi.**",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "Foydalanish: `/setwar on 2` (2 soatga ochish) yoki `/setwar off` (yopish)",
                parse_mode="Markdown"
            )


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
            u.daily_caravan_send_count = 0
            u.daily_caravan_raid_count = 0
            u.daily_spy_scout_count = 0
            u.daily_spy_sabotage_count = 0
            u.daily_spy_gates_count = 0
            u.daily_bandit_count = 0
            u.daily_duel_count = 0
            u.daily_recruit_count = 0
        await session.commit()
        cnt = len(all_users)

    await query.answer(f"✅ Barcha {cnt} nafar o'yinchining kunlik limitlari yangilandi!", show_alert=True)
    await show_admin_dashboard(query, is_message=False)


async def admin_tourney_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin paneldan Ritsarlar Turniri boshqaruvi"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        tourney = await crud.get_active_tournament(session)
        if tourney:
            p_count = len(tourney.participants or [])
            b_count = len(tourney.bets or [])
            text = (
                f"🏇🏆 **RITSARLAR TURNIRI BOSHQARUVI**\n\n"
                f"📌 Holati: 🟢 **Faol (Janglar kutilmoqda)**\n"
                f"🏷️ Nomi: **{tourney.name}**\n"
                f"💰 Jamg'arma: **{tourney.prize_pool:,}** Oltin\n"
                f"🤺 Ishtirokchilar: **{p_count}** ta ritsar\n"
                f"🎰 Tikilgan stavkalar: **{b_count}** ta\n\n"
                f"Siz turnirni istalgan payt yakunlashingiz, duellarni o'tkazib g'olib chempionni aniqlashingiz va stavka yutuqlarini tarqatishingiz mumkin."
            )
            buttons = [
                [InlineKeyboardButton("🏁 Turnirni Yakunlash (Duellarni o'tkazish)", callback_data="admin_tourney_resolve")],
                [InlineKeyboardButton("🏇 Turnir Maydoniga O'tish", callback_data="menu_tourney")],
                [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
            ]
        else:
            last_res = await session.execute(
                select(models.Tournament)
                .where(models.Tournament.status == "completed")
                .order_by(desc(models.Tournament.id))
                .limit(1)
            )
            last_t = last_res.scalar_one_or_none()
            last_info = "Hali birorta turnir o'tkazilmagan."
            if last_t:
                last_info = f"'{last_t.name}' (G'olib: {last_t.winner_name or 'Noma\'lum'}, Jamg'arma: {last_t.prize_pool:,}💰)"

            text = (
                f"🏇🏆 **RITSARLAR TURNIRI BOSHQARUVI**\n\n"
                f"📌 Holati: 🔴 **Hozirda faol turnir mavjud emas**\n"
                f"📜 So'nggi turnir: {last_info}\n\n"
                f"Yangi turnirni boshlash tugmasini bossangiz, turnir ochiladi va butun saltanat bo'ylab o'yinchilarga e'lon qilinadi!"
            )
            buttons = [
                [InlineKeyboardButton("👑 Yangi Turnirni Boshlash (25,000💰 Jamg'arma)", callback_data="admin_tourney_start")],
                [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
            ]

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


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
    """/givegold, /givefood, /giveiron, /deductgold, /deductfood, /deductiron @user miqdor"""
    if not is_admin(update.effective_user.id):
        return

    cmd = update.message.text.split()[0].lstrip("/").lower()
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(f"Foydalanish: `/{cmd} @username [miqdor]`", parse_mode="Markdown")
        return

    target = args[0]
    amount = int(args[1]) if args[1].lstrip("-").isdigit() else 0

    is_deduct = cmd.startswith("deduct") or cmd.startswith("take") or cmd.startswith("sub")
    if is_deduct:
        amount = -abs(amount)

    async with AsyncSessionLocal() as session:
        # User topish
        u = None
        if target.isdigit():
            u = await crud.get_user_any(session, int(target))
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
            u.gold = max(0, (u.gold or 0) + amount)
            res_str = f"🪙 Oltin: {u.gold:,}"
        elif "food" in cmd:
            u.food = max(0, (u.food or 0) + amount)
            res_str = f"🌾 Oziq-ovqat: {u.food:,}"
        elif "iron" in cmd:
            u.iron = max(0, (u.iron or 0) + amount)
            res_str = f"⛓️ Temir: {u.iron:,}"

        await session.commit()

    if amount < 0:
        action_str = f"-{abs(amount):,} ayirildi"
    else:
        action_str = f"+{amount:,} berildi"
    await update.message.reply_text(f"✅ {escape_md(u.full_name)} hisobidan {action_str}!\nYangi hisob: {res_str}")


async def deduct_resource_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/deduct <gold|food|iron> @username <miqdor>"""
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args or len(args) < 3:
        await update.message.reply_text("Foydalanish: `/deduct <gold|food|iron> @username <miqdor>`", parse_mode="Markdown")
        return
    res_type = args[0].lower()
    target = args[1]
    amt = int(args[2]) if args[2].lstrip("-").isdigit() else 0
    amt = -abs(amt)
    context.args = [target, str(amt)]
    update.message.text = f"/deduct{res_type} {target} {amt}"
    await handle_give_resource_command(update, context)


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
                target_user = await crud.get_user_any(session, int(user_arg))
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


# ============================================================
# CASTLES & TERRITORIES MANAGEMENT
# ============================================================

async def admin_castles_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qalalar va mintaqalar ro'yxati (sahifalangan)"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    if not is_admin(query.from_user.id):
        return

    offset = int(query.data.split(":")[1]) if ":" in query.data else 0

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(models.Territory).order_by(models.Territory.id).offset(offset).limit(6)
        )
        territories = res.scalars().all()

        count_res = await session.execute(select(func.count(models.Territory.id)))
        total_terrs = count_res.scalar() or 0

        buttons = []
        for t in territories:
            h = await session.get(models.House, t.owner_house_id) if t.owner_house_id else None
            h_str = f"{h.emoji} {h.name[:10]}" if h else "Xo'jasiz"
            tot_garr = (t.garrison_infantry or 0) + (t.garrison_archers or 0) + (t.garrison_cavalry or 0) + (t.garrison_spearmen or 0)
            buttons.append([InlineKeyboardButton(
                f"🏯 {t.name} ({t.castle_name or 'Qal\'a'}) — {h_str} ({tot_garr:,})",
                callback_data=f"adm_c_detail:{t.id}"
            )])

        nav_row = []
        if offset >= 6:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_castles_list:{offset - 6}"))
        if offset + 6 < total_terrs:
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"admin_castles_list:{offset + 6}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🏆 O'yinchilar Egallagan Qal'alar", callback_data="admin_player_castles:0")])
        buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])

        text = (
            f"🏯 **WESTEROS QALALARI VA MINTAQALARI BOSHQARUVI**\n\n"
            f"Jami qalalar: **{total_terrs}** ta\n"
            f"Qal'ani tanlab, uning garnizoni, egasi, devorlari va holatini to'liq boshqarishingiz mumkin:"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def render_player_castles_html(session, offset: int = 0, PAGE_SIZE: int = 2):
    """Admin paneli: o'yinchilar va qal'alar ro'yxatini HTML formatda tayyorlash"""
    summary = await crud.get_player_conquered_castles_summary(session)
    players = summary.get("players", [])
    conquerors = summary.get("conquerors", [])
    direct_conquests_total = summary.get("direct_conquests_total", 0)
    total_terrs = summary.get("total_territories", 43)
    player_terrs = summary.get("player_controlled", 0)
    npc_terrs = summary.get("npc_controlled", 0)

    active_players = [p for p in players if p.get("total_castles", 0) > 0]
    if not active_players:
        active_players = players

    total_players = len(active_players)
    current_page_players = active_players[offset : offset + PAGE_SIZE]

    text = (
        f"🏆 <b>VESTEROS QAL'ALARI — EGALLANGAN VA XONADON QAL'ALARI</b>\n\n"
        f"📊 <b>UMUMIY STATISTIKA:</b>\n"
        f"• 🏯 Jami Qal'alar: <b>{total_terrs}</b> ta\n"
        f"• ⚔️ Fath Etilgan Qal'alar: <b>{direct_conquests_total}</b> ta\n"
        f"• 👑 Lordlar Nazoratida: <b>{player_terrs}</b> ta qal'a\n"
        f"• 🤖 NPC Xonadonlar Nazoratida: <b>{npc_terrs}</b> ta qal'a\n"
        f"• 👥 Qal'aga ega Lordlar: <b>{total_players}</b> nafar\n\n"
    )

    if conquerors:
        text += "⚔️ <b>JANGDA BOSIB OLINGAN QAL'ALAR:</b>\n"
        for cp in conquerors[:5]:
            cp_name = html.escape(cp['name'])
            cp_house = html.escape(cp['house_name'])
            c_names = ", ".join(html.escape(c['name']) for c in cp.get('conquered_castles', []))
            text += f"• <b>{cp_name}</b> ({cp['house_emoji']} {cp_house}): <b>{cp['direct_conquests']} ta</b> ({c_names})\n"
        text += "\n"
    else:
        text += "⚔️ <b>JANGDA BOSIB OLINGAN QAL'ALAR:</b>\n<i>Hozircha hech kim dushman qal'asini bosib olmagan.</i>\n\n"

    if not active_players:
        text += "ℹ️ <i>Hozircha o'yinchilar qal'aga egalik qilmaydi.</i>"
    else:
        text += "🏰 <b>LORDLAR VA ULARNING QAL'ALARI:</b>\n"
        text += "────────────────────────────\n"

        for idx, p in enumerate(current_page_players, start=offset + 1):
            p_name = html.escape(p['name'])
            p_uname = f"@{html.escape(p['username'])}" if p.get("username") else f"ID: <code>{p['telegram_id']}</code>"
            lord_badge = "👑 Lord" if p.get("is_lord") else f"🎖️ {str(p.get('rank', 'member')).title()}"
            direct_str = f" (⚔️ {p['direct_conquests']} tasi fath etilgan)" if p.get("direct_conquests", 0) > 0 else ""

            text += (
                f"<b>{idx}. {p_name}</b> ({p_uname})\n"
                f"• {p['house_emoji']} Xonadon: <b>{html.escape(p['house_name'])}</b> ({lord_badge})\n"
                f"• 🏯 Jami Qal'alari: <b>{p['total_castles']} ta</b>{direct_str}\n"
            )

            if p.get("castles"):
                text += "• Qal'alar:\n"
                for c in p.get("castles", [])[:6]:
                    c_name = html.escape(c['name'])
                    c_castle = html.escape(c['castle_name'] or "Qal'a")
                    c_region = html.escape(c.get('region', ''))
                    tag = "⚔️ Fath etilgan" if c.get("is_direct_conquest") else ("👑 Poytaxt" if c.get("is_capital") else "🛡️ Xonadon")
                    text += (
                        f"   ▫️ 🏯 <b>{c_name}</b> ({c_castle}) — <i>{c_region}</i>\n"
                        f"      ┗ [{tag}] Devor: {c['defense']} | Garnizon: {c['garrison_total']:,}\n"
                    )
                if len(p.get("castles", [])) > 6:
                    text += f"   ▫️ <i>... va yana {len(p.get('castles', [])) - 6} ta qal'a</i>\n"
            else:
                text += "• <i>Qal'alari yo'q</i>\n"
            text += "\n"

        text += "────────────────────────────\n"
        total_pages = max(1, (total_players + PAGE_SIZE - 1) // PAGE_SIZE)
        curr_page = offset // PAGE_SIZE + 1
        text += f"Sahifa: {curr_page} / {total_pages}"

    buttons = []
    for p in current_page_players:
        buttons.append([
            InlineKeyboardButton(
                f"👤 {p['name'][:15]} ({p['total_castles']} qal'a)",
                callback_data=f"admin_u_detail:{p['user_id']}"
            )
        ])

    nav_row = []
    if offset >= PAGE_SIZE:
        nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_player_castles:{offset - PAGE_SIZE}"))
    if offset + PAGE_SIZE < total_players:
        nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"admin_player_castles:{offset + PAGE_SIZE}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("🗺️ Barcha Qal'alar Ro'yxati (40 ta)", callback_data="admin_all_castles_ov:0")
    ])
    buttons.append([
        InlineKeyboardButton("🏯 Qalalar Garnizoni Boshqaruvi", callback_data="admin_castles_list:0"),
        InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel"),
    ])

    if len(text) > 3900:
        text = text[:3850] + "\n\n<i>... (Ko'proq ma'lumot keyingi sahifada)</i>"

    return text, buttons


async def admin_player_castles_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin paneli: qaysi o'yinchi nechta va qaysi qalalarni egallaganligi ro'yxati"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    user_id = query.from_user.id
    if not is_admin(user_id):
        try:
            await query.answer("❌ Administrator huquqi yo'q!", show_alert=True)
        except Exception:
            pass
        return

    offset = 0
    if query.data and ":" in query.data:
        try:
            offset = int(query.data.split(":")[1])
        except Exception:
            offset = 0

    try:
        async with AsyncSessionLocal() as session:
            text, buttons = await render_player_castles_html(session, offset=offset)

        markup = InlineKeyboardMarkup(buttons)
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception as e_edit:
            if "Message is not modified" in str(e_edit):
                return
            # Agar edit ishlamasa (masalan rasmli xabar bo'lsa), yangi xabar qilib yuborish
            clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
            try:
                await query.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
            except Exception:
                await query.message.reply_text(clean_text[:3900], parse_mode=None, reply_markup=markup)
    except Exception as err:
        logger.error(f"admin_player_castles_callback xatosi: {err}", exc_info=True)
        try:
            await query.answer(f"⚠️ Xatolik: {str(err)[:100]}", show_alert=True)
        except Exception:
            pass
        try:
            await query.message.reply_text(f"⚠️ Egallangan qal'alar bo'limida xatolik yuz berdi: {err}")
        except Exception:
            pass


async def admin_player_castles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/conqueredcastles yoki /admincastles buyrug'i"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Faqat Administrator ushbu buyruqni bera oladi!")
        return

    try:
        async with AsyncSessionLocal() as session:
            text, buttons = await render_player_castles_html(session, offset=0)
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as err:
        logger.error(f"admin_player_castles_command xatosi: {err}", exc_info=True)
        await update.message.reply_text(f"⚠️ Qal'alar ro'yxatini olishda xatolik: {err}")


async def admin_all_castles_overview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin paneli: barcha 40 ta qal'alar va ularning egalari to'liq ro'yxati"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    user_id = query.from_user.id
    if not is_admin(user_id):
        try:
            await query.answer("❌ Administrator huquqi yo'q!", show_alert=True)
        except Exception:
            pass
        return

    offset = 0
    if query.data and ":" in query.data:
        try:
            offset = int(query.data.split(":")[1])
        except Exception:
            offset = 0

    PAGE_SIZE = 6

    try:
        async with AsyncSessionLocal() as session:
            summary = await crud.get_player_conquered_castles_summary(session)

        all_castles = summary.get("castles_overview", [])
        total_castles = len(all_castles)
        page_castles = all_castles[offset : offset + PAGE_SIZE]

        text = (
            f"🏯 <b>VESTEROS BARCHA QAL'ALARI VA ULARNING EGALARI</b>\n\n"
            f"Jami qal'alar: <b>{total_castles}</b> ta | Sahifa: <b>{offset // PAGE_SIZE + 1} / {max(1, (total_castles + PAGE_SIZE - 1) // PAGE_SIZE)}</b>\n\n"
        )

        buttons = []
        for c in page_castles:
            status_emoji = "⚔️" if c.get("is_direct_conquest") else "🏰"
            c_name = html.escape(c['name'])
            c_castle = html.escape(c['castle_name'] or "Qal'a")
            c_region = html.escape(c.get('region', ''))
            c_holder = html.escape(c['holder_name'])
            text += (
                f"{status_emoji} <b>{c_name}</b> ({c_castle}) — <i>{c_region}</i>\n"
                f"   • Egasi: <b>{c_holder}</b>\n"
                f"   • Mudofaa: <b>{c['defense']}</b> | Garnizon: <b>{c['garrison_total']:,}</b> askar\n\n"
            )
            buttons.append([
                InlineKeyboardButton(
                    f"🏯 {c['name']} ({c['holder_name'][:18]})",
                    callback_data=f"adm_c_detail:{c['id']}"
                )
            ])

        nav_row = []
        if offset >= PAGE_SIZE:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_all_castles_ov:{offset - PAGE_SIZE}"))
        if offset + PAGE_SIZE < total_castles:
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"admin_all_castles_ov:{offset + PAGE_SIZE}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([
            InlineKeyboardButton("🏆 O'yinchilar Bo'yicha Ro'yxat", callback_data="admin_player_castles:0"),
            InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel"),
        ])

        if len(text) > 3900:
            text = text[:3850] + "\n\n<i>... (Ko'proq ma'lumot keyingi sahifada)</i>"

        markup = InlineKeyboardMarkup(buttons)
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception as e_edit:
            if "Message is not modified" in str(e_edit):
                return
            clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
            try:
                await query.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
            except Exception:
                await query.message.reply_text(clean_text[:3900], parse_mode=None, reply_markup=markup)
    except Exception as err:
        logger.error(f"admin_all_castles_overview_callback xatosi: {err}", exc_info=True)
        try:
            await query.answer(f"⚠️ Xatolik: {str(err)[:100]}", show_alert=True)
        except Exception:
            pass


async def admin_user_titles_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin paneli: O'yinchiga sharafli unvon berish menyusi"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    user_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_any(session, user_id)
        if not user:
            await query.answer("O'yinchi topilmadi.", show_alert=True)
            return

        char_name = user.characters[0].name if user.characters else user.full_name
        current_title = user.title or "Mavjud emas"

        text = (
            f"🎖️ <b>SHARAFLI UNVONLAR BOSHQARUVI</b>\n\n"
            f"👤 O'yinchi: <b>{html.escape(char_name)}</b> (ID: <code>{user.telegram_id}</code>)\n"
            f"🏷️ Hozirgi unvoni: <b>{html.escape(current_title)}</b>\n\n"
            f"Quyidagi mashhur unvonlardan birini tanlang yoki o'zingiz istalgan unvonni yozish uchun buyruqdan foydalaning:\n"
            f"<code>/settitle {user.telegram_id} [unvon_nomi]</code>\n\n"
            f"Tayyor unvonlar:"
        )

        preset_titles = [
            ("❄️ Shimol Najotkori", "Shimol Najotkori"),
            ("🖐️ Qirol Qo'li", "Qirol Qo'li"),
            ("🛡️ Vesteros Qalqoni", "Vesteros Qalqoni"),
            ("🐉 Ajdarlar Otasi", "Ajdarlar Otasi"),
            ("🐉 Ajdarlar Onasi", "Ajdarlar Onasi"),
            ("👑 Oliy Lord", "Oliy Lord"),
            ("⚔️ Bosh Qo'mondon", "Bosh Qo'mondon"),
            ("🗡️ Qonxo'r Qilich", "Qonxo'r Qilich"),
            ("🏹 Kamonchilar Chempioni", "Kamonchilar Chempioni"),
            ("🌊 Dengizlar Hukmdori", "Dengizlar Hukmdori"),
        ]

        buttons = []
        for label, title_val in preset_titles:
            buttons.append([
                InlineKeyboardButton(label, callback_data=f"adm_set_title:{user.id}:{title_val}")
            ])

        buttons.append([
            InlineKeyboardButton("❌ Unvonni Olib Tashlash", callback_data=f"adm_set_title:{user.id}:__clear__")
        ])
        buttons.append([
            InlineKeyboardButton("🔙 O'yinchi Sahifasiga Qaytish", callback_data=f"admin_u_detail:{user.id}")
        ])

        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
            await query.edit_message_text(clean_text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


async def admin_set_title_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin tanlagan unvonni o'yinchiga biriktirish"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":", 2)
    user_id = int(parts[1])
    title_val = parts[2]
    new_title = None if title_val == "__clear__" else title_val

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_any(session, user_id)
        if not user:
            await query.answer("O'yinchi topilmadi.", show_alert=True)
            return

        user.title = new_title
        await session.commit()

        # O'yinchiga bildirishnoma yuborish
        if user.telegram_id:
            try:
                if new_title:
                    notice = (
                        f"🎖️ <b>SHARAFLI UNVON TOPSHIRILDI!</b>\n\n"
                        f"Oliy Administrator tomonidan sizga <b>'{html.escape(new_title)}'</b> faxriy unvoni berildi!\n"
                        f"Ushbu unvon endi profilingiz va reytinglarda namoyon bo'ladi."
                    )
                else:
                    notice = "ℹ️ Sizdagi faxriy unvon administrator tomonidan olib tashlandi."
                await context.bot.send_message(chat_id=user.telegram_id, text=notice, parse_mode="HTML")
            except Exception:
                pass

    status_msg = "Unvon olib tashlandi!" if not new_title else f"Yangi unvon berildi: {new_title}"
    try:
        await query.answer(f"✅ {status_msg}", show_alert=True)
    except Exception:
        pass

    await show_admin_user_detail(query, user_id)


async def set_title_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/settitle <@username | tg_id> <unvon> buyrug'i"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Faqat Administrator ushbu buyruqni bera oladi!")
        return

    args = context.args
    if not args or len(args) < 2:
        text = (
            "🎖️ <b>O'YINCHIGA UNVON BERISH BUYRUG'I</b>\n\n"
            "Foydalanish:\n"
            "<code>/settitle &lt;@username yoki telegram_id&gt; &lt;unvon_nomi&gt;</code>\n\n"
            "Misollar:\n"
            "• <code>/settitle @azizbek Shimol Najotkori</code>\n"
            "• <code>/settitle 7689627859 Qirol Qo'li</code>\n"
            "• <code>/settitle @shokh Vesteros Qalqoni</code>\n\n"
            "Unvonni olib tashlash uchun: <code>/deltitle &lt;@username yoki telegram_id&gt;</code>"
        )
        await update.message.reply_text(text, parse_mode="HTML")
        return

    target_ident = args[0].strip()
    title_text = " ".join(args[1:]).strip()

    async with AsyncSessionLocal() as session:
        target_user = None
        if target_ident.startswith("@"):
            uname = target_ident.lstrip("@").lower()
            res = await session.execute(select(models.User).where(func.lower(models.User.username) == uname))
            target_user = res.scalar_one_or_none()
        elif target_ident.isdigit():
            tg_id = int(target_ident)
            target_user = await crud.get_user_by_telegram_id(session, tg_id)
            if not target_user:
                target_user = await crud.get_user_any(session, int(target_ident))

        if not target_user:
            await update.message.reply_text(f"❌ '{target_ident}' bo'yicha o'yinchi topilmadi.")
            return

        target_user.title = title_text
        await session.commit()

        # O'yinchiga bildirishnoma
        if target_user.telegram_id:
            try:
                await context.bot.send_message(
                    chat_id=target_user.telegram_id,
                    text=f"🎖️ <b>SHARAFLI UNVON!</b>\n\nSizga Oliy Administrator tomonidan <b>'{html.escape(title_text)}'</b> faxriy unvoni berildi!",
                    parse_mode="HTML",
                )
            except Exception:
                pass

        await update.message.reply_text(
            f"✅ <b>{html.escape(target_user.full_name)}</b> (<code>{target_user.telegram_id}</code>) ga yangi unvon berildi:\n"
            f"🎖️ <b>{html.escape(title_text)}</b>",
            parse_mode="HTML",
        )


async def del_title_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/deltitle <@username | tg_id> buyrug'i"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Faqat Administrator ushbu buyruqni bera oladi!")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Foydalanish: <code>/deltitle &lt;@username yoki telegram_id&gt;</code>", parse_mode="HTML")
        return

    target_ident = args[0].strip()
    async with AsyncSessionLocal() as session:
        target_user = None
        if target_ident.startswith("@"):
            uname = target_ident.lstrip("@").lower()
            res = await session.execute(select(models.User).where(func.lower(models.User.username) == uname))
            target_user = res.scalar_one_or_none()
        elif target_ident.isdigit():
            tg_id = int(target_ident)
            target_user = await crud.get_user_by_telegram_id(session, tg_id)
            if not target_user:
                target_user = await crud.get_user_any(session, int(target_ident))

        if not target_user:
            await update.message.reply_text(f"❌ '{target_ident}' bo'yicha o'yinchi topilmadi.")
            return

        target_user.title = None
        await session.commit()
        await update.message.reply_text(f"✅ <b>{html.escape(target_user.full_name)}</b> ning unvoni olib tashlandi.", parse_mode="HTML")


async def show_admin_castle_detail(query, terr_id: int):
    """Qal'a to'liq ma'lumotlari va boshqaruv menyusini ko'rsatish"""
    async with AsyncSessionLocal() as session:
        terr = await session.get(models.Territory, terr_id)
        if not terr:
            try:
                await query.answer("Qal'a topilmadi!", show_alert=True)
            except Exception:
                pass
            return

        house = await session.get(models.House, terr.owner_house_id) if terr.owner_house_id else None
        h_str = f"{house.emoji} **{house.name}**" if house else "❌ **Egasi yo'q**"

        st_dr = crud.get_stationed_dragon_info(terr)
        if st_dr:
            drg_name = st_dr.get("dragon_name", st_dr.get("name", "Ajdar"))
            drg_power = st_dr.get("power", 0)
            drg_str = f"🐉 {drg_name} (Kuch: {drg_power:,})"
        else:
            drg_str = "Yo'q"

        g_inf = terr.garrison_infantry or 0
        g_arc = terr.garrison_archers or 0
        g_cav = terr.garrison_cavalry or 0
        g_sp = terr.garrison_spearmen or 0
        tot_garrison = g_inf + g_arc + g_cav + g_sp

        castle_type = "👑 Poytaxt Qal'a" if terr.is_capital else "🏯 Strategik Qal'a"
        defense = terr.defense or 0
        wall_status = "🛡️ Mustahkam (100%)" if defense >= 800 else f"🛡️ {defense} ball"

        text = (
            f"🏯 **QAL'A: {terr.name.upper()} ({terr.castle_name or 'Qal\'a'})**\n\n"
            f"📍 Mintaqa: **{terr.region}** | Turi: **{castle_type}**\n"
            f"🏰 Hukmron Xonadon: {h_str}\n"
            f"🛡️ Qal'a Mudofaasi: **{defense}** / 1,000\n"
            f"🧱 Devor Holati: **{wall_status}**\n"
            f"💰 Soatlik Daromad: +{terr.gold_income or 0}🪙, +{terr.food_income or 0}🌾, +{terr.iron_income or 0}⛓️\n\n"
            f"👥 **GARNIZON (Jami: {tot_garrison:,} askar):**\n"
            f"• 🛡️ Piyoda: **{g_inf:,}**\n"
            f"• 🏹 Kamonchi: **{g_arc:,}**\n"
            f"• 🐎 Otliq: **{g_cav:,}**\n"
            f"• 🗡️ Nayzachi: **{g_sp:,}**\n\n"
            f"🐉 **Qo'riqchi Ajdar:** {drg_str}\n\n"
            f"Boshqaruv amalini tanlang:"
        )

        buttons = [
            [
                InlineKeyboardButton("🛡️ Garnizonga +500 Har Biridan", callback_data=f"adm_c_act:{terr.id}:add_garrison:500"),
                InlineKeyboardButton("🧱 Devorni 1,000 ga Tiklash", callback_data=f"adm_c_act:{terr.id}:repair_walls:1000"),
            ],
            [
                InlineKeyboardButton("🏰 Hukmron Xonadonni O'zgartirish", callback_data=f"adm_c_pick_h:{terr.id}:0"),
                InlineKeyboardButton("🗑️ Garnizonni Tozalash (0)", callback_data=f"adm_c_act:{terr.id}:clear_garrison:0"),
            ],
            [InlineKeyboardButton("🔙 Qalalar Ro'yxati", callback_data="admin_castles_list:0")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_castle_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'a to'liq boshqaruvi"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    if not is_admin(query.from_user.id):
        return

    terr_id = int(query.data.split(":")[1])
    await show_admin_castle_detail(query, terr_id)


async def admin_castle_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'a ustida amallar bajarish"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    terr_id = int(parts[1])
    action = parts[2]
    val = int(parts[3])

    async with AsyncSessionLocal() as session:
        terr = await session.get(models.Territory, terr_id)
        if not terr:
            return

        if action == "add_garrison":
            terr.garrison_infantry = (terr.garrison_infantry or 0) + val
            terr.garrison_archers = (terr.garrison_archers or 0) + val
            terr.garrison_cavalry = (terr.garrison_cavalry or 0) + val
            terr.garrison_spearmen = (terr.garrison_spearmen or 0) + val
            msg = f"Garnizonga har turdan +{val} askar qo'shildi!"
        elif action == "repair_walls":
            terr.defense = val
            msg = f"Qal'a devorlari va mudofaasi {val} ballga tiklandi!"
        elif action == "clear_garrison":
            terr.garrison_infantry = 0
            terr.garrison_archers = 0
            terr.garrison_cavalry = 0
            terr.garrison_spearmen = 0
            msg = "Garnizon to'liq tozalandi (0)!"

        await session.commit()

    try:
        await query.answer(f"✅ {msg}", show_alert=True)
    except Exception:
        pass
    await show_admin_castle_detail(query, terr_id)


async def admin_castle_pick_house_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'aga yangi hukmron xonadon tanlash"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    terr_id = int(parts[1])
    offset = int(parts[2]) if len(parts) > 2 else 0

    async with AsyncSessionLocal() as session:
        terr = await session.get(models.Territory, terr_id)
        if not terr:
            return

        res = await session.execute(
            select(models.House).order_by(models.House.id).offset(offset).limit(6)
        )
        houses = res.scalars().all()

        count_res = await session.execute(select(func.count(models.House.id)))
        total_houses = count_res.scalar() or 0

        text = (
            f"🏰 **{terr.name.upper()} QAL'ASINI BIRIKTIRISH**\n\n"
            f"Ushbu qal'aga qaysi xonadon hukmron bo'lishini tanlang:\n"
        )

        buttons = []
        for h in houses:
            is_curr = (terr.owner_house_id == h.id)
            badge = "👑 " if is_curr else ""
            buttons.append([InlineKeyboardButton(
                f"{badge}{h.emoji} {h.name}",
                callback_data=f"adm_c_set_h:{terr.id}:{h.id}"
            )])

        nav_row = []
        if offset >= 6:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"adm_c_pick_h:{terr.id}:{offset - 6}"))
        if offset + 6 < total_houses:
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"adm_c_pick_h:{terr.id}:{offset + 6}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"adm_c_detail:{terr.id}")])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_castle_set_house_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'a egasini belgilash ijrosi"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    terr_id = int(parts[1])
    house_id = int(parts[2])

    async with AsyncSessionLocal() as session:
        terr = await session.get(models.Territory, terr_id)
        house = await session.get(models.House, house_id)
        if terr and house:
            terr.owner_house_id = house.id
            await session.commit()
            msg = f"{terr.name} qal'asi {house.name} xonadoniga topshirildi!"

    try:
        await query.answer(f"✅ {msg}", show_alert=True)
    except Exception:
        pass
    await show_admin_castle_detail(query, terr_id)


# ============================================================
# DRAGON MANAGEMENT
# ============================================================

async def admin_dragons_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha ajdarlar ro'yxati (sahifalangan)"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    if not is_admin(query.from_user.id):
        return

    offset = int(query.data.split(":")[1]) if ":" in query.data else 0

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(models.Dragon).order_by(desc(models.Dragon.power)).offset(offset).limit(6)
        )
        dragons = res.scalars().all()

        count_res = await session.execute(select(func.count(models.Dragon.id)))
        total_dragons = count_res.scalar() or 0

        buttons = []
        for d in dragons:
            u = await crud.get_user_any(session, d.user_id) if d.user_id else None
            u_name = u.full_name[:12] if u else "Egasi yo'q"
            stage_icon = "🥚" if d.stage == "egg" else "🐉"
            buttons.append([InlineKeyboardButton(
                f"{stage_icon} {d.name} (Lvl {d.level}, {d.stage.title()}) — {u_name}",
                callback_data=f"adm_d_detail:{d.id}"
            )])

        nav_row = []
        if offset >= 6:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_dragons_list:{offset - 6}"))
        if offset + 6 < total_dragons:
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"admin_dragons_list:{offset + 6}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])

        text = (
            f"🐉 **WESTEROS AJDARLARI BOSHQARUVI**\n\n"
            f"Jami ajdarlar: **{total_dragons}** ta\n"
            f"Ajdar ustiga bosib uning darajasi, bosqichi, kuchi, ochligi va artefaktini boshqarishingiz mumkin:"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def show_admin_dragon_detail(query, drg_id: int):
    """Ajdar to'liq ma'lumotlari va boshqaruv kartasini ko'rsatish"""
    async with AsyncSessionLocal() as session:
        dragon = await session.get(models.Dragon, drg_id)
        if not dragon:
            try:
                await query.answer("Ajdar topilmadi!", show_alert=True)
            except Exception:
                pass
            return

        user = await crud.get_user_any(session, dragon.user_id) if dragon.user_id else None
        u_name = f"{user.full_name} (ID: `{user.telegram_id}`)" if user else "❌ Mavjud emas"

        from data.artifacts_data import ARTIFACTS_DATA
        art_info = ARTIFACTS_DATA.get(dragon.artifact_code, {}) if dragon.artifact_code else {}
        art_str = f"{art_info.get('emoji', '💎')} {art_info.get('name', dragon.artifact_code)}" if art_info else "Yo'q"

        stage_uz = {
            "egg": "🥚 Tuxum",
            "baby": "🐣 Ajdar Bolasi",
            "young": "🦎 Yosh Ajdar",
            "adult": "🐉 Katta Ajdar (Drakarys)",
            "ancient": "👑 Qadimiy Ajdar (Balerion)"
        }.get(dragon.stage, dragon.stage)

        text = (
            f"🐉 **AJDAR: {dragon.name.upper()}**\n\n"
            f"👤 Egasi: **{u_name}**\n"
            f"🧬 Holati / Bosqichi: **{stage_uz}**\n"
            f"⭐ Darajasi: **{dragon.level}** / 20\n"
            f"⚡ Jangovar Kuch: **{dragon.power:,}**\n"
            f"🍖 Qorin To'qligi: **{dragon.hunger}%**\n"
            f"💎 Maxsus Ajdar Artefakti: **{art_str}**\n\n"
            f"Boshqaruv amalini tanlang:"
        )

        buttons = [
            [
                InlineKeyboardButton("⭐ +1 Daraja", callback_data=f"adm_d_act:{dragon.id}:lvl:1"),
                InlineKeyboardButton("⚡ +5 Daraja", callback_data=f"adm_d_act:{dragon.id}:lvl:5"),
                InlineKeyboardButton("🍖 Qorin 100%", callback_data=f"adm_d_act:{dragon.id}:feed:100"),
            ],
            [
                InlineKeyboardButton("🧬 Bosqichni O'zgartirish", callback_data=f"adm_d_stages:{dragon.id}"),
                InlineKeyboardButton("💎 Artefakt Berish", callback_data=f"adm_d_arts:{dragon.id}"),
            ],
            [
                InlineKeyboardButton("💥 Kuchga +100 Qo'shish", callback_data=f"adm_d_act:{dragon.id}:power:100"),
            ],
            [InlineKeyboardButton("🔙 Ajdarlar Ro'yxati", callback_data="admin_dragons_list:0")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_dragon_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdar to'liq boshqaruvi"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    if not is_admin(query.from_user.id):
        return

    drg_id = int(query.data.split(":")[1])
    await show_admin_dragon_detail(query, drg_id)


async def admin_dragon_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdar xususiyatlarini o'zgartirish"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    drg_id = int(parts[1])
    action = parts[2]
    val = int(parts[3])

    async with AsyncSessionLocal() as session:
        dragon = await session.get(models.Dragon, drg_id)
        if not dragon:
            return

        if action == "lvl":
            dragon.level = min(20, dragon.level + val)
            dragon.power += val * 35
            if dragon.level >= 10 and dragon.stage in ["egg", "baby", "young"]:
                dragon.stage = "adult"
            msg = f"Daraja {dragon.level} ga ko'tarildi! Kuch: {dragon.power:,}"
        elif action == "feed":
            dragon.hunger = 100
            msg = "Ajdarning qorni to'liq to'ydirildi (100%)!"
        elif action == "power":
            dragon.power += val
            msg = f"Ajdar kuchiga +{val} qo'shildi (Jami: {dragon.power:,})!"

        await session.commit()

    try:
        await query.answer(f"✅ {msg}", show_alert=True)
    except Exception:
        pass
    await show_admin_dragon_detail(query, drg_id)


async def admin_dragon_stages_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarga bosqich tanlash menyusi"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    if not is_admin(query.from_user.id):
        return

    drg_id = int(query.data.split(":")[1])

    text = "🧬 **AJDARNING YOSHI VA BOSQICHINI TANLANG:**"
    buttons = [
        [InlineKeyboardButton("🥚 Tuxum (Egg)", callback_data=f"adm_d_set_stg:{drg_id}:egg")],
        [InlineKeyboardButton("🐣 Bola (Baby)", callback_data=f"adm_d_set_stg:{drg_id}:baby")],
        [InlineKeyboardButton("🦎 Yosh (Young)", callback_data=f"adm_d_set_stg:{drg_id}:young")],
        [InlineKeyboardButton("🐉 Katta (Adult)", callback_data=f"adm_d_set_stg:{drg_id}:adult")],
        [InlineKeyboardButton("👑 Qadimiy (Ancient)", callback_data=f"adm_d_set_stg:{drg_id}:ancient")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data=f"adm_d_detail:{drg_id}")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_dragon_set_stage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdar bosqichini o'rnatish"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    drg_id = int(parts[1])
    stage = parts[2]

    async with AsyncSessionLocal() as session:
        dragon = await session.get(models.Dragon, drg_id)
        if dragon:
            dragon.stage = stage
            await session.commit()
            msg = f"Ajdar bosqichi {stage.upper()} ga o'zgartirildi!"

    try:
        await query.answer(f"✅ {msg}", show_alert=True)
    except Exception:
        pass
    await show_admin_dragon_detail(query, drg_id)


async def admin_dragon_arts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarga artefakt berish menyusi"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    if not is_admin(query.from_user.id):
        return

    drg_id = int(query.data.split(":")[1])

    text = "💎 **AJDARGA MAXSUS ARTEFAKT TANLANG:**"
    buttons = [
        [InlineKeyboardButton("🛡️ Dragon Armor (+40% Kuch/Himoya)", callback_data=f"adm_d_set_art:{drg_id}:dragon_armor")],
        [InlineKeyboardButton("🔥 Fire Ruby (+50% Olov/Drakarys)", callback_data=f"adm_d_set_art:{drg_id}:fire_ruby")],
        [InlineKeyboardButton("🏇 Ancient Saddle (+30% Tezlik/Taktika)", callback_data=f"adm_d_set_art:{drg_id}:ancient_saddle")],
        [InlineKeyboardButton("📯 Dragonbinder (+100% Jangovar Kuch)", callback_data=f"adm_d_set_art:{drg_id}:dragonbinder")],
        [InlineKeyboardButton("❌ Artefaktni Olib Tashlash", callback_data=f"adm_d_set_art:{drg_id}:none")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data=f"adm_d_detail:{drg_id}")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_dragon_set_art_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarga artefakt o'rnatish"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    drg_id = int(parts[1])
    code = parts[2]

    async with AsyncSessionLocal() as session:
        dragon = await session.get(models.Dragon, drg_id)
        if dragon:
            dragon.artifact_code = None if code == "none" else code
            await session.commit()
            msg = "Artefakt olib tashlandi!" if code == "none" else f"Artefakt {code} o'rnatildi!"

    try:
        await query.answer(f"✅ {msg}", show_alert=True)
    except Exception:
        pass
    await show_admin_dragon_detail(query, drg_id)


# ============================================================
# SEARCH & RAPID ADMIN COMMANDS
# ============================================================

async def admin_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/adminsearch <query> - foydalanuvchini id, username yoki ism bo'yicha qidirish"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    if not context.args:
        await update.message.reply_text("ℹ️ Foydalanish: `/adminsearch <id | @username | ism>`", parse_mode="Markdown")
        return

    search_query = " ".join(context.args).strip()
    clean_query = search_query.lstrip("@")

    async with AsyncSessionLocal() as session:
        matched_users = []
        if clean_query.isdigit():
            u = await crud.get_user_by_telegram_id(session, int(clean_query))
            if not u:
                u = await crud.get_user_any(session, int(clean_query))
            if u:
                matched_users.append(u)

        stmt = select(models.User).where(
            (models.User.username.ilike(f"%{clean_query}%")) |
            (models.User.full_name.ilike(f"%{clean_query}%"))
        ).limit(10)
        res = await session.execute(stmt)
        for u in res.scalars().all():
            if not any(m.id == u.id for m in matched_users):
                matched_users.append(u)

        if not matched_users:
            await update.message.reply_text(f"❌ '{search_query}' bo'yicha hech qanday o'yinchi topilmadi.")
            return

        buttons = []
        for u in matched_users:
            h = await session.get(models.House, u.house_id) if u.house_id else None
            h_str = f"({h.name})" if h else "(Xonadonsiz)"
            buttons.append([InlineKeyboardButton(f"👤 {u.full_name[:16]} {h_str}", callback_data=f"admin_u_detail:{u.id}")])

        buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
        await update.message.reply_text(
            f"🔍 **QIDIRUV NATIJALARI:** `{search_query}` ({len(matched_users)} ta topildi):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )


async def set_house_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sethouse <user_id|@username> <house_id>"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    if len(context.args) < 2:
        await update.message.reply_text("ℹ️ Foydalanish: `/sethouse <telegram_id yoki @username> <house_id>`", parse_mode="Markdown")
        return

    target_str = context.args[0].strip().lstrip("@")
    try:
        house_id = int(context.args[1].strip())
    except ValueError:
        await update.message.reply_text("❌ House ID butun son bo'lishi kerak!")
        return

    async with AsyncSessionLocal() as session:
        target_user = None
        if target_str.isdigit():
            target_user = await crud.get_user_by_telegram_id(session, int(target_str))
            if not target_user:
                target_user = await crud.get_user_any(session, int(target_str))
        else:
            target_user = await crud.get_user_by_username(session, target_str)

        if not target_user:
            await update.message.reply_text(f"❌ O'yinchi topilmadi: {target_str}")
            return

        ok, msg = await crud.admin_transfer_user_house(session, target_user.id, house_id)
        await update.message.reply_text(f"{'✅' if ok else '❌'} {msg}")


async def give_army_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/givearmy <user_id|@username> <infantry|archers|cavalry|spearmen|special> <count>"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "ℹ️ Foydalanish: `/givearmy <telegram_id yoki @username> <infantry|archers|cavalry|spearmen|special> <miqdor>`",
            parse_mode="Markdown"
        )
        return

    target_str = context.args[0].strip().lstrip("@")
    unit_type = context.args[1].strip().lower()
    try:
        count = int(context.args[2].strip())
    except ValueError:
        await update.message.reply_text("❌ Miqdor butun son bo'lishi kerak!")
        return

    valid_types = {
        "infantry": "infantry", "piyoda": "infantry",
        "archers": "archers", "kamonchi": "archers",
        "cavalry": "cavalry", "otliq": "cavalry",
        "spearmen": "spearmen", "nayzachi": "spearmen",
        "special": "special_troops", "special_troops": "special_troops", "maxsus": "special_troops"
    }

    if unit_type not in valid_types:
        await update.message.reply_text(f"❌ Noto'g'ri qo'shin turi: {unit_type}. Turlar: infantry, archers, cavalry, spearmen, special")
        return

    col_name = valid_types[unit_type]
    async with AsyncSessionLocal() as session:
        target_user = None
        if target_str.isdigit():
            target_user = await crud.get_user_by_telegram_id(session, int(target_str))
            if not target_user:
                target_user = await crud.get_user_any(session, int(target_str))
        else:
            target_user = await crud.get_user_by_username(session, target_str)

        if not target_user:
            await update.message.reply_text(f"❌ O'yinchi topilmadi: {target_str}")
            return

        ok, msg = await crud.admin_set_user_army(session, target_user.id, add_mode=True, **{col_name: count})
        await update.message.reply_text(f"{'✅' if ok else '❌'} {msg}")


async def admin_season_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Mavsumni boshqarish va yakunlash menyusi"""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if not is_admin(uid) and uid != OWNER_ID:
        await query.answer("❌ Faqat Administrator kirishi mumkin!", show_alert=True)
        return

    try:
        async with AsyncSessionLocal() as session:
            summary = await crud.get_season_status_summary(session)

        s_num = summary["season_number"]
        next_s_num = s_num + 1
        rem_str = f"{summary['rem_days']} kun {summary['rem_hours']} soat {summary['rem_mins']} daqiqa"
        winner_h = escape_md(str(summary["winner_house_name"]))
        winner_emoji = summary["winner_house_emoji"]
        king_name = escape_md(str(summary["king_name"]))

        top3_text = ""
        for p in summary["top3_players"]:
            badge = "🥇" if p["rank"] == 1 else ("🥈" if p["rank"] == 2 else "🥉")
            p_name = escape_md(str(p['name']))
            p_h = escape_md(str(p['house']))
            top3_text += f"• {badge} *{p['rank']}-o'rin:* {p_name} ({p_h}) — *{p['prestige']:,}🎖️* Nufuz (Daraja: {p['level']})\n"

        if not top3_text:
            top3_text = "• _Hozircha faol o'yinchilar yo'q_\n"

        text = (
            f"👑 *{s_num}-MAVSUM BOSHQARUVI & YAKUNLASH*\n\n"
            f"⏱️ *Qolgan muddat:* {rem_str}\n"
            f"🏰 *Amaldagi Temir Taxt Egalari:* {winner_emoji} *{winner_h}*\n"
            f"👑 *Vesteros Qiroli:* *{king_name}*\n\n"
            f"🏆 *JORIY MAVSUM YETAKCHILARI (TOP 3):*\n"
            f"{top3_text}\n"
            f"📜 *Mavsumni yakunlash oqibatlari:*\n"
            f"1. O'yin g'olibi ({king_name}) abadiy *Shon-sharaf Zali (Hall of Fame)*ga muhrlanadi.\n"
            f"2. Yuqoridagi TOP 3 lordlarga yangi {next_s_num}-Mavsum uchun *maxsus boshlang'ich bonuslar* (unvon, xazina, saralangan qo'shinlar) biriktiriladi.\n"
            f"3. Barcha o'yinchilar, armiyalar va qal'alar 0 ga tushirilib, *{next_s_num}-Mavsum* rasman boshlanadi!\n\n"
            f"Mavsumni yakunlab, yangi mavsumni boshlashni istaysizmi?"
        )

        buttons = [
            [InlineKeyboardButton("🏆 Mavsumni Yakunlash & Yangi Mavsum Boshlash", callback_data="admin_season_conclude_ask")],
            [InlineKeyboardButton("🔙 Admin Panelga Qaytish", callback_data="admin_panel")],
        ]
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"admin_season_menu_callback xatosi: {e}", exc_info=True)
        await query.answer(f"Xatolik: {e}", show_alert=True)


async def admin_season_conclude_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mavsumni yakunlashdan oldin tasdiqlash so'rovi"""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if not is_admin(uid) and uid != OWNER_ID:
        await query.answer("❌ Faqat Administrator ushbu amalni bajara oladi!", show_alert=True)
        return

    try:
        async with AsyncSessionLocal() as session:
            summary = await crud.get_season_status_summary(session)

        s_num = summary["season_number"]
        next_s_num = s_num + 1
        king_name = escape_md(str(summary['king_name']))

        text = (
            f"⚠️ *DIQQAT: {s_num}-MAVSUMNI TO'LIQ YAKUNLASH VA 0 DAN BOSHLASH!*\n\n"
            f"Haqiqatan ham {s_num}-mavsumni yakunlab, yangi *{next_s_num}-Mavsum*ni boshlamoqchimisiz?\n\n"
            f"*Nimalar sodir bo'ladi:*\n"
            f"• G'olib *{king_name}* Shon-sharaf zaliga yoziladi.\n"
            f"• TOP 3 o'yinchilariga yangi mavsumda ro'yxatdan o'tishda maxsus bonuslar saqlanadi.\n"
            f"• Barcha o'yinchilar profillari, armiyalari va resurslari 0 ga tushiriladi.\n"
            f"• Barcha 60 ta qal'a boshlang'ich holatiga qaytariladi.\n"
            f"• Hamma /start orqali yangi mavsumda qaytadan boshlaydi!\n\n"
            f"❗️ _Ushbu amalni ortga qaytarib bo'lmaydi!_"
        )
        buttons = [
            [InlineKeyboardButton("👑 HA, MAVSUMNI YAKUNLASH VA 0 QILISH", callback_data="admin_season_conclude_do")],
            [InlineKeyboardButton("❌ Bekor Qilish", callback_data="admin_season_menu")],
        ]
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"admin_season_conclude_ask_callback xatosi: {e}", exc_info=True)
        await query.answer(f"Xatolik: {e}", show_alert=True)


async def admin_season_conclude_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mavsumni yakunlash va yangi mavsum boshlash ijrosi"""
    query = update.callback_query
    uid = query.from_user.id
    if not is_admin(uid) and uid != OWNER_ID:
        await query.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    try:
        await query.answer("⏳ Mavsum yakunlanmoqda va baza yangilanmoqda...", show_alert=False)
    except Exception:
        pass

    try:
        # Jarayon boshlanganini darhol ko'rsatish
        try:
            await query.edit_message_text(
                "⏳ *MAVSUM YAKUNLANMOQDA...*\n\n"
                "• G'olib Shon-sharaf zaliga muhrlanmoqda...\n"
                "• TOP 3 o'yinchilarga bonuslar biriktirilmoqda...\n"
                "• Barcha o'yinchilar va armiyalar 0 ga tushirilmoqda...\n"
                "• Qal'alar boshlang'ich holatiga qaytarilmoqda...\n\n"
                "_Iltimos, kuting..._",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        async with AsyncSessionLocal() as session:
            ok, ann, res_info = await crud.admin_conclude_and_restart_season(session, context.application)

        if not ok:
            text_err = f"❌ *Xatolik yuz berdi:*\n{ann}"
            buttons_err = [[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]
            try:
                await query.edit_message_text(text_err, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons_err))
            except Exception:
                await query.edit_message_text(text_err, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons_err))
            return

        top3_lines = ""
        for p in res_info.get("top3_players", []):
            badge = "🥇" if p["rank"] == 1 else ("🥈" if p["rank"] == 2 else "🥉")
            p_name = escape_md(str(p['name']))
            top3_lines += f"{badge} *{p['rank']}-o'rin:* {p_name} ({p['prestige']:,}🎖️)\n"

        winner_name = escape_md(str(res_info.get('winner_name', 'Qirol')))
        winner_house = escape_md(str(res_info.get('winner_house', 'Vesteros')))
        s_num = res_info.get('season_number', 1)
        next_s_num = res_info.get('next_season_number', 2)

        text = (
            f"👑🏆 *{s_num}-MAVSUM MUVAFFAQIYATLI YAKUNLANDI!* 🏆👑\n\n"
            f"🏛️ *Mavsum Chempioni:* *{winner_name}* ({winner_house})\n"
            f"📜 O'yin g'olibi nomi abadiy *Shon-sharaf Zali (Hall of Fame)*ga oltin harflar bilan muhrlandi!\n\n"
            f"🎖️ *Yangi mavsumda bonus oluvchi TOP 3 lordlar:*\n"
            f"{top3_lines or 'Mavjud emas'}\n"
            f"🌟 *{next_s_num}-MAVSUM BOSHLANDI!*\n"
            f"• Barcha o'yinchilar ma'lumotlari to'liq 0 ga tushirildi.\n"
            f"• Qal'alar va garnizonlar boshlang'ich holatiga qaytdi.\n"
            f"• Endi barcha o'yinchilar /start buyrug'i orqali yangi taqdirini tanlashi mumkin!"
        )
        buttons = [
            [InlineKeyboardButton("👑 /start orqali Yangidan Boshlash", callback_data="menu_main")],
            [InlineKeyboardButton("⚙️ Admin Paneli", callback_data="admin_panel")],
        ]
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))

    except Exception as e:
        logger.error(f"admin_season_conclude_do_callback xatosi: {e}", exc_info=True)
        err_msg = f"❌ *Kutilmagan xatolik yuz berdi:*\n`{escape_md(str(e))}`"
        err_btns = [
            [InlineKeyboardButton("🔄 Qayta Urinish", callback_data="admin_season_conclude_ask")],
            [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
        ]
        try:
            await query.edit_message_text(err_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(err_btns))
        except Exception:
            await query.edit_message_text(f"❌ Xatolik yuz berdi: {str(e)}", parse_mode=None, reply_markup=InlineKeyboardMarkup(err_btns))


async def end_season_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/endseason yoki /concludeseason buyrug'i"""
    uid = update.effective_user.id
    if not is_admin(uid) and uid != OWNER_ID:
        await update.message.reply_text("❌ Faqat Administrator ushbu buyruqni bera oladi!")
        return

    try:
        async with AsyncSessionLocal() as session:
            summary = await crud.get_season_status_summary(session)

        s_num = summary["season_number"]
        next_s_num = s_num + 1
        king_name = escape_md(str(summary['king_name']))

        text = (
            f"⚠️ *DIQQAT: {s_num}-MAVSUMNI TO'LIQ YAKUNLASH VA 0 DAN BOSHLASH!*\n\n"
            f"Haqiqatan ham {s_num}-mavsumni yakunlab, yangi *{next_s_num}-Mavsum*ni boshlamoqchimisiz?\n\n"
            f"• G'olib *{king_name}* Shon-sharaf zaliga yoziladi.\n"
            f"• TOP 3 o'yinchilariga yangi mavsumda ro'yxatdan o'tishda maxsus bonuslar saqlanadi.\n"
            f"• Barcha o'yinchilar profillari, armiyalari va resurslari 0 ga tushiriladi.\n"
            f"• Hamma /start orqali yangi mavsumda qaytadan boshlaydi!"
        )
        buttons = [
            [InlineKeyboardButton("👑 HA, MAVSUMNI YAKUNLASH VA 0 QILISH", callback_data="admin_season_conclude_do")],
            [InlineKeyboardButton("❌ Bekor Qilish", callback_data="menu_main")],
        ]
        try:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await update.message.reply_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"end_season_command xatosi: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Xatolik yuz berdi: {str(e)}")



async def admin_wipe_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'yinni tozalashdan oldin ogohlantirish ekrani"""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if not is_admin(uid) and uid != OWNER_ID:
        await query.answer("❌ Faqat Administrator o'yinni tozalashi mumkin!", show_alert=True)
        return

    text = (
        "⚠️ **DIQQAT: BUTUN O'YIN MA'LUMOTLARINI 0 GA TUSHIRISH!**\n\n"
        "Haqiqatan ham barcha ma'lumotlarni o'chirib, o'yinni yangi mavsumdek 0 dan boshlamoqchimisiz?\n\n"
        "**Nimalar sodir bo'ladi:**\n"
        "• Barcha o'yinchilar profillari, resurslari va darajalari o'chiriladi.\n"
        "• Barcha armiyalar, ajdarlar va qahramonlar o'chiriladi.\n"
        "• Xonadonlar va qal'alar boshlang'ich holatiga qaytariladi.\n"
        "• Hamma (shu jumladan siz ham) /start bosib yangidan ro'yxatdan o'tadi!\n\n"
        "❗️ *Ushbu amalni ortga qaytarib bo'lmaydi!*"
    )
    buttons = [
        [InlineKeyboardButton("⚠️ HA, BARCHASINI O'CHIRIB 0 QILISH", callback_data="admin_wipe_confirm")],
        [InlineKeyboardButton("❌ Bekor Qilish", callback_data="admin_panel")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_wipe_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Butun o'yinni tozalashni amalga oshirish"""
    query = update.callback_query
    uid = query.from_user.id
    if not is_admin(uid) and uid != OWNER_ID:
        await query.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    await query.answer("⏳ Baza tozalanmoqda...", show_alert=False)
    async with AsyncSessionLocal() as session:
        await crud.reset_entire_game(session)

    text = (
        "✅ **BUTUN O'YIN MUVAFFAQIYATLI TOZALANDI!**\n\n"
        "• Barcha o'yinchilar va ularning ma'lumotlari bazadan to'liq o'chirildi.\n"
        "• Barcha xonadonlar va 40 ta qal'a boshlang'ich holatiga qaytarildi.\n"
        "• O'yin to'liq 0 dan boshlandi!\n\n"
        "Endi /start buyrug'ini bosing va yangi saltanatingizni quring!"
    )
    buttons = [
        [InlineKeyboardButton("👑 /start orqali Yangidan Boshlash", callback_data="menu_main")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def wipe_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/wipe_game yoki /reset_game buyrug'i"""
    uid = update.effective_user.id
    if not is_admin(uid) and uid != OWNER_ID:
        await update.message.reply_text("❌ Faqat Administrator ushbu buyruqni bera oladi!")
        return

    text = (
        "⚠️ **DIQQAT: BUTUN O'YIN MA'LUMOTLARINI 0 GA TUSHIRISH!**\n\n"
        "Barcha o'yinchilar, armiyalar, ajdarlar va yutuqlar o'chirilib, qal'alar boshlang'ich holatiga qaytariladi.\n\n"
        "Hamma /start bosib 0 dan boshlaydi.\n\n"
        "Tasdiqlaysizmi?"
    )
    buttons = [
        [InlineKeyboardButton("⚠️ HA, BARCHASINI O'CHIRIB 0 QILISH", callback_data="admin_wipe_confirm")],
        [InlineKeyboardButton("❌ Bekor Qilish", callback_data="menu_main")],
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


def register_admin_handlers(app):
    app.add_handler(CommandHandler(["wipe_game", "reset_game", "restart_game"], wipe_game_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("adminsearch", admin_search_command))
    app.add_handler(CommandHandler("sethouse", set_house_command))
    app.add_handler(CommandHandler("givearmy", give_army_command))
    app.add_handler(CommandHandler("addadmin", add_admin_command))
    app.add_handler(CommandHandler("deladmin", del_admin_command))
    app.add_handler(CommandHandler([
        "givegold", "givefood", "giveiron",
        "deductgold", "deductfood", "deductiron",
        "takegold", "takefood", "takeiron",
        "subgold", "subfood", "subiron",
    ], handle_give_resource_command))
    app.add_handler(CommandHandler("deduct", deduct_resource_command))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_admins_list_callback, pattern="^admin_admins_list$"))
    app.add_handler(CallbackQueryHandler(admin_lords_menu_callback, pattern="^(admin_lords_menu|adm_lords_page:)"))
    app.add_handler(CallbackQueryHandler(admin_lord_house_detail_callback, pattern="^adm_lord_h:"))
    app.add_handler(CallbackQueryHandler(admin_pick_lord_callback, pattern="^adm_pick_lord:"))
    app.add_handler(CallbackQueryHandler(admin_pick_all_lord_callback, pattern="^adm_pick_all_lord:"))
    app.add_handler(CallbackQueryHandler(admin_conf_lord_callback, pattern="^adm_conf_lord:"))
    app.add_handler(CallbackQueryHandler(admin_do_lord_callback, pattern="^adm_do_lord:"))
    app.add_handler(CallbackQueryHandler(admin_dismiss_lord_callback, pattern="^adm_dismiss_lord:"))
    app.add_handler(CallbackQueryHandler(admin_reset_votes_callback, pattern="^adm_reset_votes:"))
    app.add_handler(CallbackQueryHandler(admin_users_list_callback, pattern="^admin_users_list:"))
    app.add_handler(CallbackQueryHandler(admin_user_detail_callback, pattern="^admin_u_detail:"))
    app.add_handler(CallbackQueryHandler(admin_user_action_callback, pattern="^adm_act:"))
    app.add_handler(CallbackQueryHandler(admin_user_house_pick_callback, pattern="^adm_u_house_pick:"))
    app.add_handler(CallbackQueryHandler(admin_user_house_do_callback, pattern="^adm_u_house_do:"))
    app.add_handler(CallbackQueryHandler(admin_user_remhouse_callback, pattern="^adm_u_remhouse:"))
    app.add_handler(CallbackQueryHandler(admin_user_army_menu_callback, pattern="^adm_u_army_menu:"))
    app.add_handler(CallbackQueryHandler(admin_user_army_act_callback, pattern="^adm_u_army_act:"))
    app.add_handler(CallbackQueryHandler(admin_houses_list_callback, pattern="^admin_houses_list(:[0-9]+)?$"))
    app.add_handler(CallbackQueryHandler(admin_house_detail_callback, pattern="^adm_h_detail:"))
    app.add_handler(CallbackQueryHandler(admin_house_action_callback, pattern="^adm_h_act:"))
    app.add_handler(CallbackQueryHandler(admin_castles_list_callback, pattern="^admin_castles_list:"))
    app.add_handler(CommandHandler(["conqueredcastles", "admincastles", "playercastles"], admin_player_castles_command))
    app.add_handler(CallbackQueryHandler(admin_player_castles_callback, pattern="^admin_player_castles(:[0-9]+)?$"))
    app.add_handler(CallbackQueryHandler(admin_all_castles_overview_callback, pattern="^admin_all_castles_ov(:[0-9]+)?$"))
    app.add_handler(CallbackQueryHandler(admin_user_titles_menu_callback, pattern="^adm_u_titles:"))
    app.add_handler(CallbackQueryHandler(admin_set_title_do_callback, pattern="^adm_set_title:"))
    app.add_handler(CommandHandler(["settitle", "unvon"], set_title_command))
    app.add_handler(CommandHandler(["deltitle", "remtitle"], del_title_command))
    app.add_handler(CallbackQueryHandler(admin_castle_detail_callback, pattern="^adm_c_detail:"))
    app.add_handler(CallbackQueryHandler(admin_castle_action_callback, pattern="^adm_c_act:"))
    app.add_handler(CallbackQueryHandler(admin_castle_pick_house_callback, pattern="^adm_c_pick_h:"))
    app.add_handler(CallbackQueryHandler(admin_castle_set_house_callback, pattern="^adm_c_set_h:"))
    app.add_handler(CallbackQueryHandler(admin_dragons_list_callback, pattern="^admin_dragons_list:"))
    app.add_handler(CallbackQueryHandler(admin_dragon_detail_callback, pattern="^adm_d_detail:"))
    app.add_handler(CallbackQueryHandler(admin_dragon_action_callback, pattern="^adm_d_act:"))
    app.add_handler(CallbackQueryHandler(admin_dragon_stages_callback, pattern="^adm_d_stages:"))
    app.add_handler(CallbackQueryHandler(admin_dragon_set_stage_callback, pattern="^adm_d_set_stg:"))
    app.add_handler(CallbackQueryHandler(admin_dragon_arts_callback, pattern="^adm_d_arts:"))
    app.add_handler(CallbackQueryHandler(admin_dragon_set_art_callback, pattern="^adm_d_set_art:"))
    app.add_handler(CallbackQueryHandler(admin_events_menu_callback, pattern="^admin_events_menu$"))
    app.add_handler(CallbackQueryHandler(admin_event_action_callback, pattern="^adm_ev_act:"))
    app.add_handler(CallbackQueryHandler(admin_mass_gift_callback, pattern="^admin_mass_gift$"))
    app.add_handler(CallbackQueryHandler(admin_reset_all_limits_callback, pattern="^admin_reset_all_limits$"))
    app.add_handler(CallbackQueryHandler(admin_tourney_menu_callback, pattern="^admin_tourney_menu$"))
    app.add_handler(CallbackQueryHandler(admin_broadcast_info_callback, pattern="^admin_broadcast_info$"))
    app.add_handler(CommandHandler(["endseason", "concludeseason", "nextseason"], end_season_command))
    app.add_handler(CallbackQueryHandler(admin_season_menu_callback, pattern="^admin_season_menu$"))
    app.add_handler(CallbackQueryHandler(admin_season_conclude_ask_callback, pattern="^admin_season_conclude_ask$"))
    app.add_handler(CallbackQueryHandler(admin_season_conclude_do_callback, pattern="^admin_season_conclude_do$"))
    app.add_handler(CallbackQueryHandler(admin_wipe_ask_callback, pattern="^admin_wipe_ask$"))
    app.add_handler(CallbackQueryHandler(admin_wipe_confirm_callback, pattern="^admin_wipe_confirm$"))
    app.add_handler(CommandHandler(["setwar", "warcontrol"], set_war_command))
    app.add_handler(CallbackQueryHandler(admin_war_control_callback, pattern="^admin_war_control$"))
    app.add_handler(CallbackQueryHandler(admin_war_action_callback, pattern="^(adm_war_set:|adm_war_add:|adm_war_bcast_now)"))


