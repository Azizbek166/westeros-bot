import html
import asyncio
from datetime import datetime
from typing import Optional, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from database import AsyncSessionLocal, crud, models
from keyboards.menus import back_to_main_keyboard

BANNER_PRESETS = ["🛡️", "⚔️", "🦅", "🐺", "🦁", "🐉", "👑", "⚡", "🌊", "🏰", "🏹", "🩸"]


# ============================================================
# 1. ASOSIY ENTRY POINT (/guild & menu_guild)
# ============================================================

async def guild_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/guild yoki /gildiya buyrug'i"""
    user_id = update.effective_user.id
    await show_guild_hub(update, context, user_id, is_message=True)


async def guild_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_guild callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_guild_hub(query, context, user_id, is_message=False)


async def show_guild_hub(target, context: ContextTypes.DEFAULT_TYPE, user_id: int, is_message: bool):
    """Gildiya markazi: Foydalanuvchi a'zo bo'lsa Mening Gildiyam, bo'lmasa Gildiyalar Portali chiqadi"""
    # Wizard holatlarini tozalash
    context.user_data.pop("guild_wizard", None)
    context.user_data.pop("awaiting_guild_desc", None)
    context.user_data.pop("awaiting_guild_search", None)

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            msg = "❌ Iltimos, avval /start ni bosing."
            if is_message:
                await target.message.reply_text(msg)
            else:
                await target.edit_message_text(msg)
            return

        guild, member = await crud.get_user_guild_membership(session, user.id)

        if guild and member:
            # Foydalanuvchi gildiyada -> Mening Gildiyam
            await show_my_guild(target, session, user, guild, member, is_message=is_message)
        else:
            # Foydalanuvchi gildiyada emas -> Gildiyalar Portali
            await show_guild_portal(target, session, user, is_message=is_message)


# ============================================================
# 2. GILDIYALAR PORTALI (Gildiyada bo'lmaganlar uchun)
# ============================================================

async def show_guild_portal(target, session, user: models.User, is_message: bool):
    """Gildiyasi yo'q foydalanuvchilar uchun boshlang'ich portal"""
    has_cd, exp_at, rem_sec = await crud.check_guild_cooldown(session, user.id)

    cd_text = ""
    if has_cd:
        hrs = rem_sec // 3600
        mins = (rem_sec % 3600) // 60
        cd_text = (
            f"⏳ <b>Anti-Hopping Cooldown:</b> Faol\n"
            f"<i>Yangi gildiyaga kirish uchun: {hrs} soat {mins} daqiqa kuting.</i>\n\n"
        )

    text = (
        f"🛡️ <b>VESTEROS GILDIYALARI VA BIRODARLIKLARI</b>\n\n"
        f"Gildiya — bu turli xonadon lordlari bir bayroq ostida birlashadigan "
        f"shon-sharafli harbiy va savdo birodarligidir!\n\n"
        f"⚔️ <b>Gildiya imtiyozlari:</b>\n"
        f"• Birgalikdagi vazifalar va maxsus faollik kvestlari\n"
        f"• Vesteros bo'yicha mustaqil Gildiyalar Reytingi\n"
        f"• Birodarlik darajalari va noyob unvonlar\n"
        f"• Qardosh lordlar bilan o'zaro hamjihatlik\n\n"
        f"👤 Sizning holatingiz: <b>Hech qaysi gildiyada emassiz</b>\n"
        f"💰 Hamyoningizda: <b>{user.gold:,}🪙 Oltin</b> | Darajangiz: <b>{user.level or 1}</b>\n\n"
        f"{cd_text}"
        f"Quyidagi amallardan birini tanlang:"
    )

    buttons = [
        [InlineKeyboardButton("🔍 Gildiyalarni Ko'rish & Qidirish", callback_data="guild_list:0")],
        [InlineKeyboardButton("🏆 Gildiyalar Reytingi", callback_data="guild_rankings:0")],
        [InlineKeyboardButton("➕ Yangi Gildiya Yaratish (25,000🪙)", callback_data="guild_create_start")],
        [InlineKeyboardButton("📨 Yuborilgan Arizalarim", callback_data="guild_my_apps")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ]
    markup = InlineKeyboardMarkup(buttons)

    if is_message:
        await target.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        if hasattr(target, "message") and target.message and target.message.photo:
            await target.message.delete()
            await target.message.chat.send_message(text, parse_mode="HTML", reply_markup=markup)
        else:
            await target.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


# ============================================================
# 3. MENING GILDIYAM (Gildiya a'zosi bo'lganlar uchun)
# ============================================================

async def show_my_guild(target, session, user: models.User, guild: models.Guild, member: models.GuildMember, is_message: bool):
    """Mening Gildiyam Boshqaruv Paneli"""
    leader_name = guild.leader.full_name if guild.leader else "Noma'lum"
    role_title = crud.ROLE_LABELS.get(member.role, member.role)
    members_cnt = len(guild.members or [])

    rec_status_map = {
        "open": "🟢 Ochiq (Darhol qo'shilish)",
        "apply": "🟡 Ariza orqali",
        "closed": "🔴 Yopiq",
    }
    rec_text = rec_status_map.get(guild.recruiting_type, "Ochiq")

    # Kutilayotgan arizalar soni (Officer+ uchun)
    pending_apps_count = 0
    if member.role in ["master", "deputy", "officer"]:
        from sqlalchemy import select, func
        p_stmt = select(func.count(models.GuildApplication.id)).where(
            models.GuildApplication.guild_id == guild.id,
            models.GuildApplication.status == "pending"
        )
        pending_apps_count = (await session.execute(p_stmt)).scalar() or 0

    buff_status_str = ""
    now = datetime.utcnow()
    if guild.active_buff_type and guild.active_buff_expires_at and guild.active_buff_expires_at > now:
        b_name = crud.GUILD_BUFFS_CONFIG.get(guild.active_buff_type, {}).get("name", guild.active_buff_type)
        time_left = guild.active_buff_expires_at - now
        hours = int(time_left.total_seconds() // 3600)
        minutes = int((time_left.total_seconds() % 3600) // 60)
        buff_status_str = f"⚡ <b>Faol Buff:</b> {b_name} <i>({hours}s {minutes}daq)</i>\n"

    text = (
        f"{guild.banner} <b>{html.escape(guild.name)} {html.escape(guild.tag)}</b>\n"
        f"<i>\"{html.escape(guild.description or 'Vesteros birodarligi')}\"</i>\n\n"
        f"👑 <b>Yetakchi:</b> {html.escape(leader_name)}\n"
        f"🎖️ <b>Sizning lavozimingiz:</b> {role_title}\n"
        f"⭐ <b>Gildiya Darajasi:</b> Level {guild.level} ({guild.xp:,} XP)\n"
        f"🏆 <b>Nufuzi (Prestige):</b> {guild.prestige:,} ball\n"
        f"💰 <b>Xazina:</b> {guild.treasury_gold or 0:,}🪙 | {guild.treasury_iron or 0:,}⛓️\n"
        f"{buff_status_str}"
        f"👥 <b>A'zolar:</b> {members_cnt} / {guild.max_members} nafar\n"
        f"🚪 <b>Qabul holati:</b> {rec_text}\n"
    )

    buttons = [
        [
            InlineKeyboardButton("💰 Gildiya Xazinasi", callback_data="guild_treasury_menu"),
            InlineKeyboardButton("📜 Kunlik Vazifalar", callback_data="guild_quests_menu"),
        ],
        [
            InlineKeyboardButton("👥 A'zolar Ro'yxati", callback_data="guild_members:0"),
            InlineKeyboardButton("🏆 Reyting", callback_data="guild_rankings:0"),
        ],
        [
            InlineKeyboardButton("🏇 Ritsarlar Turniri", callback_data="menu_tourney"),
        ],
    ]

    # Ofitser, O'rinbosar va Yetakchi uchun arizalar
    if member.role in ["master", "deputy", "officer"]:
        app_label = f"📥 Arizalar ({pending_apps_count})" if pending_apps_count > 0 else "📥 Arizalar (0)"
        buttons.append([InlineKeyboardButton(app_label, callback_data="guild_apps:0")])

    # O'rinbosar va Yetakchi uchun sozlamalar
    if member.role in ["master", "deputy"]:
        buttons.append([InlineKeyboardButton("⚙️ Gildiya Sozlamalari", callback_data="guild_settings")])

    # Faqat Yetakchi uchun boshqaruv (Yetakchilikni topshirish, tarqatish)
    if member.role == "master":
        buttons.append([InlineKeyboardButton("👑 Yetakchilikni Topshirish", callback_data="guild_transfer_pick")])
        buttons.append([InlineKeyboardButton("💥 Gildiyani Tarqatish", callback_data="guild_disband_ask")])
    else:
        # Oddiy a'zo, ofitser yoki o'rinbosar uchun chiqish tugmasi
        buttons.append([InlineKeyboardButton("🚪 Gildiyani Tark Etish", callback_data="guild_leave_ask")])

    buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])
    markup = InlineKeyboardMarkup(buttons)

    if is_message:
        await target.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        if hasattr(target, "message") and target.message and target.message.photo:
            await target.message.delete()
            await target.message.chat.send_message(text, parse_mode="HTML", reply_markup=markup)
        else:
            await target.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


# ============================================================
# 4. GILDIYA YARATISH WIZARDI
# ============================================================

async def guild_create_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiya yaratishni boshlash (talablar tekshiruvi)"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return

        if (user.level or 1) < crud.GUILD_CREATION_MIN_LEVEL:
            await query.answer(
                f"❌ Gildiya yaratish uchun kamida {crud.GUILD_CREATION_MIN_LEVEL}-daraja (Oliy Qo'mondon) bo'lishingiz kerak! Sizda: {user.level or 1}-daraja.",
                show_alert=True
            )
            return

        if (user.gold or 0) < crud.GUILD_CREATION_GOLD_COST:
            await query.answer(
                f"❌ Gildiya yaratish uchun {crud.GUILD_CREATION_GOLD_COST:,}🪙 oltin talab etiladi! Sizda: {user.gold:,}🪙.",
                show_alert=True
            )
            return

        has_cd, exp_at, rem_sec = await crud.check_guild_cooldown(session, user.id)
        if has_cd:
            hrs = rem_sec // 3600
            mins = (rem_sec % 3600) // 60
            await query.answer(
                f"⏳ Siz yaqinda gildiyani tark etgansiz! Cooldown: {hrs} soat {mins} daqiqa qoldi.",
                show_alert=True
            )
            return

        curr_guild, _ = await crud.get_user_guild_membership(session, user.id)
        if curr_guild:
            await query.answer(f"❌ Siz allaqachon '{curr_guild.name}' gildiyasi a'zosisiz!", show_alert=True)
            return

    # Wizardni boshlash
    context.user_data["guild_wizard"] = {"step": "name"}

    text = (
        f"➕ <b>YANGI GILDIYA YARATISH (1-BOSQICH / NOMI)</b>\n\n"
        f"Gildiya ochish orqali siz Vesterosda o'z harbiy birodarligingizni tuzasiz!\n\n"
        f"💰 <b>Narxi:</b> 25,000🪙 Oltin\n"
        f"👑 <b>Dastlabki sig'im:</b> 15 nafar a'zo\n\n"
        f"✍️ <b>1-Qadam:</b> Gildiyangiz nomini chatga yozib yuboring:\n"
        f"<i>(3 tadan 32 tagacha belgi, masalan: Qora Qarg'alar, Oltin Ritsarlar, Ajdar Qalbi)</i>"
    )
    buttons = [[InlineKeyboardButton("🔙 Bekor Qilish", callback_data="menu_guild")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_wizard_banner_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """3-bosqich: Gerb (ramz) tanlash klaviaturasi"""
    query = update.callback_query
    await query.answer()

    wiz = context.user_data.get("guild_wizard", {})
    name = wiz.get("name", "Gildiya")
    tag = wiz.get("tag", "[GD]")

    text = (
        f"➕ <b>YANGI GILDIYA YARATISH (3-BOSQICH / GERB)</b>\n\n"
        f"🏰 Nomi: <b>{html.escape(name)}</b>\n"
        f"🏷️ Tegi: <b>{html.escape(tag)}</b>\n\n"
        f"🛡️ <b>Birodarlik bayrog'i uchun ramzni tanlang:</b>"
    )

    row1 = [InlineKeyboardButton(b, callback_data=f"guild_wiz_b:{b}") for b in BANNER_PRESETS[:6]]
    row2 = [InlineKeyboardButton(b, callback_data=f"guild_wiz_b:{b}") for b in BANNER_PRESETS[6:]]
    buttons = [row1, row2, [InlineKeyboardButton("🔙 Bekor Qilish", callback_data="menu_guild")]]

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_wizard_banner_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerb tanlangach, 4-bosqich: Qabul rejimini tanlash"""
    query = update.callback_query
    await query.answer()
    banner = query.data.split(":")[1]

    wiz = context.user_data.get("guild_wizard", {})
    wiz["banner"] = banner
    wiz["step"] = "recruitment"
    context.user_data["guild_wizard"] = wiz

    name = wiz.get("name", "Gildiya")
    tag = wiz.get("tag", "[GD]")

    text = (
        f"➕ <b>YANGI GILDIYA YARATISH (4-BOSQICH / QABUL REJIMI)</b>\n\n"
        f"{banner} <b>{html.escape(name)} {html.escape(tag)}</b>\n\n"
        f"A'zolarni qabul qilish qoidasini tanlang:\n\n"
        f"• <b>🟢 Ochiq:</b> 5-darajadan yuqori har qanday lord darhol a'zo bo'la oladi.\n"
        f"• <b>🟡 Ariza orqali:</b> Lordlar ariza yuboradi, siz yoki ofitserlaringiz tasdiqlagach qabul qilinadi.\n"
    )
    buttons = [
        [
            InlineKeyboardButton("🟢 Ochiq Qabul", callback_data="guild_wiz_rec:open"),
            InlineKeyboardButton("🟡 Ariza Orqali", callback_data="guild_wiz_rec:apply"),
        ],
        [InlineKeyboardButton("🔙 Bekor Qilish", callback_data="menu_guild")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_wizard_rec_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qabul rejimi tanlangach, Yakuniy Tasdiqlash oynasi"""
    query = update.callback_query
    await query.answer()
    rec_type = query.data.split(":")[1]

    wiz = context.user_data.get("guild_wizard", {})
    wiz["recruiting_type"] = rec_type
    wiz["step"] = "confirm"
    context.user_data["guild_wizard"] = wiz

    name = wiz.get("name", "Gildiya")
    tag = wiz.get("tag", "[GD]")
    banner = wiz.get("banner", "🛡️")
    rec_str = "🟢 Ochiq (Darhol)" if rec_type == "open" else "🟡 Ariza orqali"

    text = (
        f"🏁 <b>GILDIYA YARATISHNI TASDIQLASH</b>\n\n"
        f"Barcha ma'lumotlarni tekshiring:\n"
        f"• Ramz: <b>{banner}</b>\n"
        f"• Nomi: <b>{html.escape(name)}</b>\n"
        f"• Tegi: <b>{html.escape(tag)}</b>\n"
        f"• Qabul rejimi: <b>{rec_str}</b>\n"
        f"• Dastlabki a'zolar sig'imi: <b>15 nafar</b>\n\n"
        f"💰 <b>Hisobingizdan 25,000🪙 Oltin yechib olinadi.</b>\n"
        f"Yangi birodarlikni rasman tashkil etishni tasdiqlaysizmi?"
    )
    buttons = [
        [InlineKeyboardButton("✅ 25,000🪙 To'lash & Yaratish", callback_data="guild_wiz_create_do")],
        [InlineKeyboardButton("❌ Bekor Qilish", callback_data="menu_guild")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_wizard_create_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiya yaratish ijrosi"""
    query = update.callback_query
    user_id = query.from_user.id
    wiz = context.user_data.pop("guild_wizard", None)

    if not wiz:
        await query.answer("❌ Jarayon eskirgan. Qaytadan boshlang.", show_alert=True)
        await show_guild_hub(query, context, user_id, is_message=False)
        return

    name = wiz.get("name", "")
    tag = wiz.get("tag", "")
    banner = wiz.get("banner", "🛡️")
    rec_type = wiz.get("recruiting_type", "open")

    async with AsyncSessionLocal() as session:
        ok, msg, guild = await crud.create_guild(
            session=session,
            telegram_id=user_id,
            name=name,
            tag=tag,
            description="Vesterosning shonli birodarligi.",
            banner=banner,
            recruiting_type=rec_type
        )

    await query.answer(msg[:150], show_alert=True)
    await show_guild_hub(query, context, user_id, is_message=False)


# ============================================================
# 5. GILDIYALAR RO'YXATI VA QIDIRISH
# ============================================================

async def guild_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Faol gildiyalar ro'yxati (har sahifada 5 ta)"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    try:
        page = int(query.data.split(":")[1])
    except Exception:
        page = 0

    limit = 5
    offset = page * limit

    async with AsyncSessionLocal() as session:
        guilds, total_cnt = await crud.get_active_guilds(session, limit=limit, offset=offset)

    if not guilds and page == 0:
        text = (
            f"🔍 <b>VESTEROS GILDIYALARI RO'YXATI</b>\n\n"
            f"Hozircha Vesterosda birorta ham gildiya tuzilmagan!\n"
            f"Siz birinchi bo'lib o'z birodarligingizni ochishingiz mumkin."
        )
        buttons = [
            [InlineKeyboardButton("➕ Birinchi Bo'lib Yaratish", callback_data="guild_create_start")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="menu_guild")],
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    text = (
        f"🔍 <b>VESTEROS GILDIYALARI (Jami: {total_cnt} ta)</b>\n"
        f"<i>Sahifa: {page + 1} / {max(1, (total_cnt + limit - 1) // limit)}</i>\n\n"
        f"Birodarlik haqida batafsil ko'rish uchun uning tugmasini bosing:\n\n"
    )

    buttons = []
    for g in guilds:
        m_cnt = len(g.members or [])
        rec_dot = "🟢" if g.recruiting_type == "open" else ("🟡" if g.recruiting_type == "apply" else "🔴")
        btn_label = f"{g.banner} {g.name} {g.tag} | Lvl {g.level} ({m_cnt}/{g.max_members}) {rec_dot}"
        buttons.append([InlineKeyboardButton(btn_label, callback_data=f"guild_view:{g.id}:{page}")])

    # Sahifalash
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"guild_list:{page - 1}"))
    if (page + 1) * limit < total_cnt:
        nav_row.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"guild_list:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("🔎 Qidirish", callback_data="guild_search_ask"),
        InlineKeyboardButton("🔙 Orqaga", callback_data="menu_guild")
    ])

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiya tafsilotlarini ko'rish va a'zo bo'lish/ariza yuborish"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    parts = query.data.split(":")
    guild_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        guild = await crud.get_guild_by_id(session, guild_id)
        if not guild:
            await query.answer("❌ Ushbu gildiya topilmadi.", show_alert=True)
            return

        user_guild, user_mem = await crud.get_user_guild_membership(session, user.id)
        leader_name = guild.leader.full_name if guild.leader else "Noma'lum"
        m_cnt = len(guild.members or [])

        rec_status_map = {
            "open": "🟢 Ochiq (Darhol qo'shilish)",
            "apply": "🟡 Ariza orqali (Yetakchi tasdig'i)",
            "closed": "🔴 Yopiq",
        }
        rec_text = rec_status_map.get(guild.recruiting_type, "Ochiq")

        text = (
            f"{guild.banner} <b>{html.escape(guild.name)} {html.escape(guild.tag)}</b>\n"
            f"<i>\"{html.escape(guild.description or 'Vesteros birodarligi')}\"</i>\n\n"
            f"👑 <b>Yetakchi:</b> {html.escape(leader_name)}\n"
            f"⭐ <b>Darajasi:</b> Level {guild.level} ({guild.xp:,} XP)\n"
            f"🏆 <b>Nufuzi:</b> {guild.prestige:,} ball\n"
            f"👥 <b>A'zolar:</b> {m_cnt} / {guild.max_members} nafar\n"
            f"🚪 <b>Qabul:</b> {rec_text}\n"
        )

        buttons = []

        if not user_guild:
            # Foydalanuvchi gildiyada emas -> Qo'shilish yoki ariza
            if guild.recruiting_type == "open":
                buttons.append([InlineKeyboardButton("⚔️ Gildiyaga Qo'shilish", callback_data=f"guild_join_do:{guild.id}:{page}")])
            elif guild.recruiting_type == "apply":
                buttons.append([InlineKeyboardButton("📨 Ariza Yuborish", callback_data=f"guild_join_do:{guild.id}:{page}")])
            else:
                buttons.append([InlineKeyboardButton("🔴 Qabul Yopiq", callback_data="noop")])
        elif user_guild.id == guild.id:
            buttons.append([InlineKeyboardButton("🏰 Mening Gildiyam", callback_data="menu_guild")])

        buttons.append([InlineKeyboardButton("🔙 Ro'yxatga Qaytish", callback_data=f"guild_list:{page}")])

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_join_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiyaga qo'shilish yoki ariza yuborish ijrosi"""
    query = update.callback_query
    user_id = query.from_user.id
    parts = query.data.split(":")
    guild_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.join_or_apply_guild(session, user_id, guild_id)

    await query.answer(msg[:150], show_alert=True)
    if ok:
        await show_guild_hub(query, context, user_id, is_message=False)
    else:
        # Qaytadan view ga o'tish
        query.data = f"guild_view:{guild_id}:{page}"
        await guild_view_callback(update, context)


# ============================================================
# 6. A'ZOLAR RO'YXATI VA BOSHQARUVI
# ============================================================

async def guild_members_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiya a'zolari ro'yxati"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    try:
        page = int(query.data.split(":")[1])
    except Exception:
        page = 0

    limit = 8
    offset = page * limit

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        guild, viewer_mem = await crud.get_user_guild_membership(session, user.id)
        if not guild or not viewer_mem:
            await query.answer("❌ Siz gildiya a'zosi emassiz.", show_alert=True)
            await show_guild_hub(query, context, user_id, is_message=False)
            return

        all_members = list(guild.members or [])
        # Tartib: master, deputy, officer, member, joined_at
        all_members.sort(key=lambda m: crud.ROLE_HIERARCHY.get(m.role, 0), reverse=True)
        total_cnt = len(all_members)
        page_members = all_members[offset:offset + limit]

        text = (
            f"👥 <b>{html.escape(guild.name)} — A'ZOLAR RO'YXATI</b>\n"
            f"<i>Jami a'zolar: {total_cnt} / {guild.max_members} nafar | Sahifa: {page + 1}</i>\n\n"
        )

        buttons = []
        for m in page_members:
            u = m.user
            u_name = u.full_name if u else "Lord"
            role_icon = "👑" if m.role == "master" else ("⚔️" if m.role == "deputy" else ("🎖️" if m.role == "officer" else "🛡️"))
            lvl = u.level or 1 if u else 1
            btn_text = f"{role_icon} {u_name} (Lvl {lvl})"

            # Agar ko'rayotgan shaxs Master, Deputy yoki Officer bo'lsa va o'zidan kichikroq bo'lsa, boshqarish tugmasi chiqadi
            if viewer_mem.role in ["master", "deputy", "officer"] and m.user_id != user.id:
                buttons.append([InlineKeyboardButton(btn_text, callback_data=f"guild_mem_manage:{m.id}:{page}")])
            else:
                buttons.append([InlineKeyboardButton(btn_text, callback_data="noop")])

        # Sahifalash
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"guild_members:{page - 1}"))
        if (page + 1) * limit < total_cnt:
            nav_row.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"guild_members:{page + 1}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Mening Gildiyam", callback_data="menu_guild")])

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_member_manage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A'zo ustidan boshqaruv (Lavozim berish, Haydash)"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    parts = query.data.split(":")
    target_mem_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0

    async with AsyncSessionLocal() as session:
        actor = await crud.get_user_by_telegram_id(session, user_id)
        guild, actor_mem = await crud.get_user_guild_membership(session, actor.id)
        if not guild or not actor_mem or actor_mem.role not in ["master", "deputy", "officer"]:
            await query.answer("❌ Sizda bu a'zoni boshqarish huquqi yo'q.", show_alert=True)
            return

        target_mem = await session.get(models.GuildMember, target_mem_id)
        if not target_mem or target_mem.guild_id != guild.id:
            await query.answer("❌ Ushbu a'zo topilmadi.", show_alert=True)
            return

        target_user = await session.get(models.User, target_mem.user_id)
        t_name = target_user.full_name if target_user else "A'zo"
        role_label = crud.ROLE_LABELS.get(target_mem.role, target_mem.role)

        actor_level = crud.ROLE_HIERARCHY.get(actor_mem.role, 0)
        target_level = crud.ROLE_HIERARCHY.get(target_mem.role, 0)

        text = (
            f"👤 <b>A'ZONI BOSHQARISH</b>\n\n"
            f"• Ismi: <b>{html.escape(t_name)}</b>\n"
            f"• Darajasi: <b>Level {target_user.level or 1}</b>\n"
            f"• Hozirgi lavozimi: <b>{role_label}</b>\n"
            f"• Qo'shilgan vaqti: <code>{target_mem.joined_at.strftime('%Y-%m-%d')}</code>\n\n"
            f"Quyidagi amallardan birini tanlang:"
        )

        buttons = []

        # Lavozim o'zgartirish (Master barchasini, Deputy faqat oddiy a'zoni Ofitser qila oladi)
        if actor_mem.role == "master":
            role_buttons = []
            if target_mem.role != "deputy":
                role_buttons.append(InlineKeyboardButton("⚔️ O'rinbosar qilish", callback_data=f"guild_role_set:{target_mem.id}:deputy:{page}"))
            if target_mem.role != "officer":
                role_buttons.append(InlineKeyboardButton("🎖️ Ofitser qilish", callback_data=f"guild_role_set:{target_mem.id}:officer:{page}"))
            if target_mem.role != "member":
                role_buttons.append(InlineKeyboardButton("🛡️ Oddiy a'zo qilish", callback_data=f"guild_role_set:{target_mem.id}:member:{page}"))
            if role_buttons:
                buttons.append(role_buttons)
        elif actor_mem.role == "deputy" and target_mem.role == "member":
            buttons.append([InlineKeyboardButton("🎖️ Ofitser qilish", callback_data=f"guild_role_set:{target_mem.id}:officer:{page}")])

        # Haydash (faqat o'zidan kichik lavozimdagi a'zoni)
        if actor_level > target_level and target_mem.role != "master":
            buttons.append([InlineKeyboardButton("👢 Gildiyadan Haydash", callback_data=f"guild_kick_ask:{target_mem.id}:{page}")])

        buttons.append([InlineKeyboardButton("🔙 A'zolar Ro'yxatiga Qaytish", callback_data=f"guild_members:{page}")])

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_role_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A'zo lavozimini o'zgartirish ijrosi"""
    query = update.callback_query
    user_id = query.from_user.id
    parts = query.data.split(":")
    target_mem_id = int(parts[1])
    new_role = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.set_guild_member_role(session, user_id, target_mem_id, new_role)

    await query.answer(msg[:150], show_alert=True)
    # Qaytadan a'zo panelini ko'rsatish
    query.data = f"guild_mem_manage:{target_mem_id}:{page}"
    await guild_member_manage_callback(update, context)


async def guild_kick_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Haydashdan oldin tasdiqlash so'rovi"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    target_mem_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0

    async with AsyncSessionLocal() as session:
        target_mem = await session.get(models.GuildMember, target_mem_id)
        if not target_mem:
            return
        target_user = await session.get(models.User, target_mem.user_id)
        t_name = target_user.full_name if target_user else "A'zo"

    text = (
        f"⚠️ <b>HAYDASHNI TASDIQLASH</b>\n\n"
        f"Haqiqatan ham <b>{html.escape(t_name)}</b>ni gildiyadan chetlashtirmoqchimisiz?\n\n"
        f"<i>Eslatma: Haydalgan o'yinchiga 24 soatlik Rejoin Cooldown beriladi.</i>"
    )
    buttons = [
        [InlineKeyboardButton("👢 Ha, Haydalsin", callback_data=f"guild_kick_do:{target_mem_id}:{page}")],
        [InlineKeyboardButton("🔙 Bekor Qilish", callback_data=f"guild_mem_manage:{target_mem_id}:{page}")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_kick_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Haydash ijrosi"""
    query = update.callback_query
    user_id = query.from_user.id
    parts = query.data.split(":")
    target_mem_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.kick_guild_member(session, user_id, target_mem_id)

    await query.answer(msg[:150], show_alert=True)
    query.data = f"guild_members:{page}"
    await guild_members_callback(update, context)


# ============================================================
# 7. ARIZALARNI KO'RIB CHIQISH (Officer+)
# ============================================================

async def guild_apps_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiyaga tushgan arizalar ro'yxati"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    try:
        page = int(query.data.split(":")[1])
    except Exception:
        page = 0

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        guild, mem = await crud.get_user_guild_membership(session, user.id)
        if not guild or not mem or mem.role not in ["master", "deputy", "officer"]:
            await query.answer("❌ Arizalarni ko'rish huquqi yo'q.", show_alert=True)
            return

        from sqlalchemy import select
        stmt = (
            select(models.GuildApplication)
            .options(selectinload(models.GuildApplication.user))
            .where(
                models.GuildApplication.guild_id == guild.id,
                models.GuildApplication.status == "pending"
            )
            .order_by(models.GuildApplication.created_at.asc())
        )
        apps = list((await session.execute(stmt)).scalars().all())

    if not apps:
        text = (
            f"📥 <b>GILDIYAGA TUSHGAN ARIZALAR</b>\n\n"
            f"Hozirda yangi kutilayotgan arizalar mavjud emas."
        )
        buttons = [[InlineKeyboardButton("🔙 Mening Gildiyam", callback_data="menu_guild")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    text = f"📥 <b>KUTILAYOTGAN ARIZALAR (Jami: {len(apps)} ta)</b>\n\n"
    buttons = []
    for a in apps[:8]:
        applicant = a.user
        a_name = applicant.full_name if applicant else "Nomzod"
        lvl = applicant.level or 1 if applicant else 1
        btn_accept = InlineKeyboardButton("✅", callback_data=f"guild_app_do:{a.id}:accept:{page}")
        btn_reject = InlineKeyboardButton("❌", callback_data=f"guild_app_do:{a.id}:reject:{page}")
        btn_info = InlineKeyboardButton(f"{a_name} (Lvl {lvl})", callback_data="noop")
        buttons.append([btn_info, btn_accept, btn_reject])

    buttons.append([InlineKeyboardButton("🔙 Mening Gildiyam", callback_data="menu_guild")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_app_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Arizani qabul qilish yoki rad etish ijrosi"""
    query = update.callback_query
    user_id = query.from_user.id
    parts = query.data.split(":")
    app_id = int(parts[1])
    action = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.handle_guild_application(session, user_id, app_id, action)

    await query.answer(msg[:150], show_alert=True)
    query.data = f"guild_apps:{page}"
    await guild_apps_callback(update, context)


# ============================================================
# 8. MENING ARIZALARIM (Gildiyaga kirmagan foydalanuvchi arizalari)
# ============================================================

async def guild_my_apps_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchining yuborilgan arizalari"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        apps = await crud.get_user_pending_applications(session, user_id)

    if not apps:
        text = (
            f"📨 <b>YUBORILGAN ARIZALARIM</b>\n\n"
            f"Sizda hozirda ko'rib chiqilayotgan faol arizalar mavjud emas."
        )
        buttons = [[InlineKeyboardButton("🔙 Orqaga", callback_data="menu_guild")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    text = f"📨 <b>YUBORILGAN ARIZALAR (Jami: {len(apps)} ta)</b>\n\n"
    buttons = []
    for a in apps:
        g = a.guild
        g_name = f"{g.banner} {g.name} {g.tag}" if g else "Gildiya"
        buttons.append([
            InlineKeyboardButton(f"{g_name} — Kutilmoqda", callback_data="noop"),
            InlineKeyboardButton("🗑️ Bekor Qilish", callback_data=f"guild_my_app_del:{a.id}")
        ])

    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="menu_guild")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_my_app_del_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Arizani bekor qilish ijrosi"""
    query = update.callback_query
    user_id = query.from_user.id
    app_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.cancel_guild_application(session, user_id, app_id)

    await query.answer(msg[:150], show_alert=True)
    await guild_my_apps_callback(update, context)


# ============================================================
# 9. YETAKCHILIKNI TOPSHIRISH (Faqat Master)
# ============================================================

async def guild_transfer_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yetakchilikni topshirish uchun nomzod tanlash"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        guild, mem = await crud.get_user_guild_membership(session, user.id)
        if not guild or not mem or mem.role != "master":
            await query.answer("❌ Faqat Yetakchi topshira oladi.", show_alert=True)
            return

        candidates = [m for m in guild.members if m.user_id != user.id]

    if not candidates:
        await query.answer("❌ Gildiyada boshqa a'zo yo'q. Topshirish uchun avval a'zo qabul qiling.", show_alert=True)
        return

    text = (
        f"👑 <b>YETAKCHILIKNI TOPSHIRISH</b>\n\n"
        f"Boshqaruv jilovini qaysi a'zoga topshirmoqchisiz?\n"
        f"<i>(Eslatma: Topshirganingizdan so'ng siz O'rinbosar lavozimiga o'tasiz)</i>"
    )
    buttons = []
    for c in candidates:
        u = c.user
        name = u.full_name if u else "A'zo"
        role_label = crud.ROLE_LABELS.get(c.role, c.role)
        buttons.append([InlineKeyboardButton(f"{name} ({role_label})", callback_data=f"guild_transfer_ask:{c.id}")])

    buttons.append([InlineKeyboardButton("🔙 Bekor Qilish", callback_data="menu_guild")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_transfer_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yetakchilikni topshirish tasdiq so'rovi"""
    query = update.callback_query
    await query.answer()
    target_mem_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        target_mem = await session.get(models.GuildMember, target_mem_id)
        if not target_mem:
            return
        target_user = await session.get(models.User, target_mem.user_id)
        t_name = target_user.full_name if target_user else "Yangi Yetakchi"

    text = (
        f"⚠️ <b>DIQQAT! YETAKCHILIKNI TOPSHIRISH</b>\n\n"
        f"Haqiqatan ham Gildiyaning barcha vakolatlarini <b>{html.escape(t_name)}</b>ga topshirishni tasdiqlaysizmi?\n\n"
        f"<i>Ushbu amalni ortga qaytarib bo'lmaydi!</i>"
    )
    buttons = [
        [InlineKeyboardButton("👑 Ha, Yetakchilikni Topshirish", callback_data=f"guild_transfer_do:{target_mem_id}")],
        [InlineKeyboardButton("🔙 Bekor Qilish", callback_data="menu_guild")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_transfer_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yetakchilikni topshirish ijrosi"""
    query = update.callback_query
    user_id = query.from_user.id
    target_mem_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.transfer_guild_leadership(session, user_id, target_mem_id)

    await query.answer(msg[:150], show_alert=True)
    await show_guild_hub(query, context, user_id, is_message=False)


# ============================================================
# 10. GILDIYANI TARQATISH (Faqat Master)
# ============================================================

async def guild_disband_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiyani tarqatish tasdiq so'rovi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        guild, mem = await crud.get_user_guild_membership(session, user.id)
        if not guild or not mem or mem.role != "master":
            await query.answer("❌ Faqat Yetakchi tarqata oladi.", show_alert=True)
            return

    text = (
        f"💥 <b>DIQQAT! GILDIYANI TARQATISH</b>\n\n"
        f"Siz rostdan ham <b>{html.escape(guild.name)}</b> birodarligini butunlay tarqatib yubormoqchimisiz?\n\n"
        f"⚠️ <b>Oqibatlari:</b>\n"
        f"• Barcha a'zolar gildiyadan chiqariladi\n"
        f"• Barcha arizalar bekor qilinadi\n"
        f"• Gildiya yutuqlari va nufuzi o'chiriladi\n"
        f"• Ushbu amalni <b>ortga qaytarib bo'lmaydi!</b>"
    )
    buttons = [
        [InlineKeyboardButton("💥 Ha, Butunlay Tarqatilsin", callback_data=f"guild_disband_do:{guild.id}")],
        [InlineKeyboardButton("🔙 Bekor Qilish", callback_data="menu_guild")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_disband_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiyani tarqatish ijrosi"""
    query = update.callback_query
    user_id = query.from_user.id
    guild_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.disband_guild(session, user_id, guild_id)

    await query.answer(msg[:150], show_alert=True)
    await show_guild_hub(query, context, user_id, is_message=False)


# ============================================================
# 11. GILDIYANI TARK ETISH (Leave Guild)
# ============================================================

async def guild_leave_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiyadan chiqish tasdiq so'rovi"""
    query = update.callback_query
    await query.answer()

    text = (
        f"🚪 <b>GILDIYANI TARK ETISH</b>\n\n"
        f"Haqiqatan ham o'z birodarligingizni tark etmoqchimisiz?\n\n"
        f"⚠️ <b>Anti-Hopping Qoidasi:</b>\n"
        f"Gildiyani tark etganingizdan so'ng <b>24 soat davomida</b> boshqa hech qaysi gildiyaga kira olmaysiz yoki yangi gildiya ocha olmaysiz!"
    )
    buttons = [
        [InlineKeyboardButton("🚪 Ha, Tark Etaman", callback_data="guild_leave_do")],
        [InlineKeyboardButton("🔙 Qolish", callback_data="menu_guild")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_leave_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiyadan chiqish ijrosi"""
    query = update.callback_query
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.leave_guild(session, user_id)

    await query.answer(msg[:150], show_alert=True)
    await show_guild_hub(query, context, user_id, is_message=False)


# ============================================================
# 12. GILDIYA SOZLAMALARI (Deputy va Master)
# ============================================================

async def guild_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiya sozlamalari paneli"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        guild, mem = await crud.get_user_guild_membership(session, user.id)
        if not guild or not mem or mem.role not in ["master", "deputy"]:
            await query.answer("❌ Faqat Yetakchi va O'rinbosar sozlamalarni o'zgartira oladi.", show_alert=True)
            return

        rec_status_map = {
            "open": "🟢 Ochiq (Darhol qo'shilish)",
            "apply": "🟡 Ariza orqali",
            "closed": "🔴 Yopiq",
        }
        rec_text = rec_status_map.get(guild.recruiting_type, "Ochiq")

        text = (
            f"⚙️ <b>GILDIYA SOZLAMALARI</b>\n\n"
            f"• Ramz: <b>{guild.banner}</b>\n"
            f"• Tavsif: <i>\"{html.escape(guild.description or 'Yo\'q')}\"</i>\n"
            f"• Qabul holati: <b>{rec_text}</b>\n\n"
            f"O'zgartirmoqchi bo'lgan parametrni tanlang:"
        )

        buttons = [
            [
                InlineKeyboardButton("🔄 Qabulni O'zgartirish", callback_data="guild_set_rec_ask"),
                InlineKeyboardButton("🛡️ Gerbni Almashtirish", callback_data="guild_set_banner_pick"),
            ],
            [InlineKeyboardButton("✍️ Tavsifni Yangilash", callback_data="guild_set_desc_ask")],
            [InlineKeyboardButton("🔙 Mening Gildiyam", callback_data="menu_guild")],
        ]

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_set_rec_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qabul rejimini tanlash"""
    query = update.callback_query
    await query.answer()

    text = "🚪 <b>QABUL REJIMINI TANLANG:</b>"
    buttons = [
        [
            InlineKeyboardButton("🟢 Ochiq", callback_data="guild_set_rec_do:open"),
            InlineKeyboardButton("🟡 Ariza orqali", callback_data="guild_set_rec_do:apply"),
            InlineKeyboardButton("🔴 Yopiq", callback_data="guild_set_rec_do:closed"),
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="guild_settings")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_set_rec_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qabul rejimini saqlash"""
    query = update.callback_query
    user_id = query.from_user.id
    mode = query.data.split(":")[1]

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        guild, mem = await crud.get_user_guild_membership(session, user.id)
        if guild:
            ok, msg = await crud.update_guild_settings(session, user_id, guild.id, recruiting_type=mode)
            await query.answer(msg, show_alert=True)

    await guild_settings_callback(update, context)


async def guild_set_banner_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerbni almashtirish"""
    query = update.callback_query
    await query.answer()

    text = "🛡️ <b>YANGI BAYROQ RAMZINI TANLANG:</b>"
    row1 = [InlineKeyboardButton(b, callback_data=f"guild_set_banner_do:{b}") for b in BANNER_PRESETS[:6]]
    row2 = [InlineKeyboardButton(b, callback_data=f"guild_set_banner_do:{b}") for b in BANNER_PRESETS[6:]]
    buttons = [row1, row2, [InlineKeyboardButton("🔙 Orqaga", callback_data="guild_settings")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_set_banner_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerbni saqlash"""
    query = update.callback_query
    user_id = query.from_user.id
    banner = query.data.split(":")[1]

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        guild, mem = await crud.get_user_guild_membership(session, user.id)
        if guild:
            ok, msg = await crud.update_guild_settings(session, user_id, guild.id, banner=banner)
            await query.answer(msg, show_alert=True)

    await guild_settings_callback(update, context)


async def guild_set_desc_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tavsif kiritish so'rovi"""
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_guild_desc"] = True

    text = (
        f"✍️ <b>GILDIYA TAVSIFINI KIRITING:</b>\n\n"
        f"Gildiyangiz shiori yoki qisqacha tavsifini chatga yozib yuboring (maksimal 200 ta belgi):"
    )
    buttons = [[InlineKeyboardButton("🔙 Bekor Qilish", callback_data="guild_settings")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_quests_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiya kunlik vazifalari (Quests) interfeysi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return

        guild, mem = await crud.get_user_guild_membership(session, user.id)
        if not guild or not mem:
            await query.answer("❌ Siz gildiya a'zosi emassiz.", show_alert=True)
            await show_guild_hub(query, context, user_id, is_message=False)
            return

        data = await crud.get_guild_quests_data(session, guild.id, user.id)

    cur_lvl = data["level"]
    cur_xp = data["xp"]
    nxt_xp = data["next_level_xp"]
    lvl_title = data["title"]
    quests = data["quests"]

    # Progress bar
    if cur_lvl >= 5:
        prog_bar = "██████████ (MAX)"
    else:
        prev_lvl_xp = crud.GUILD_LEVEL_THRESHOLDS.get(cur_lvl, {}).get("xp", 0)
        span = max(1, nxt_xp - prev_lvl_xp)
        cur_span = max(0, cur_xp - prev_lvl_xp)
        filled = min(10, int((cur_span / span) * 10))
        prog_bar = f"{'█' * filled}{'░' * (10 - filled)} ({cur_xp:,}/{nxt_xp:,} XP)"

    text_lines = [
        f"{guild.banner} <b>{html.escape(guild.name)} — KUNLIK VAZIFALAR</b>",
        f"📅 Sana: <code>{data['today_str']}</code>",
        f"⭐ Daraja: <b>Level {cur_lvl} ({lvl_title})</b>",
        f"📈 Taraqqiyot: <code>{prog_bar}</code>",
        f"🏆 Gildiya Nufuzi: <b>{guild.prestige:,} Prestige</b>",
        f"👥 A'zolar: <b>{len(guild.members or [])}/{guild.max_members}</b>\n",
        "<i>Har bir topshiriq jamoaviy bajariladi. Shaxsiy hissa qo'shgan a'zolar alohida rag'batlantiriladi!</i>\n",
        "───────────────────────────────"
    ]

    buttons = []
    for q in quests:
        status_icon = "✅" if q["is_completed"] else "⏳"
        status_label = "Bajarildi!" if q["is_completed"] else f"{q['current']}/{q['target']}"

        text_lines.append(
            f"{status_icon} <b>{q['title']}</b> ({status_label})\n"
            f"   <i>{q['desc']}</i>\n"
            f"   👤 Sizning hissangiz: <b>{q['user_progress']}/{q['individual_cap']}</b>\n"
            f"   🎁 Sovrin: <code>+{q['rewards']['gold']}🪙, +{q['rewards']['iron']}⛓️, +{q['rewards']['xp']} XP</code>"
        )
        if q["is_completed"] and q["reward_claimed"]:
            text_lines.append("   ✨ <i>Siz ushbu vazifa mukofotini olgansiz.</i>\n")
        elif q["can_claim"]:
            text_lines.append("   🎉 <b>Mukofot tayyor! Olishingiz mumkin:</b>\n")
            buttons.append([
                InlineKeyboardButton(f"🎁 Mukofotni Olish ({q['title'][:18]}...)", callback_data=f"guild_quest_claim:{q['id']}")
            ])
        else:
            text_lines.append("")

    buttons.append([
        InlineKeyboardButton("🔄 Yangilash", callback_data="guild_quests_menu"),
        InlineKeyboardButton("🔙 Mening Gildiyam", callback_data="menu_guild")
    ])

    await query.edit_message_text("\n".join(text_lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_quest_claim_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiya vazifasi mukofotini olish ijrosi"""
    query = update.callback_query
    user_id = query.from_user.id
    quest_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.claim_guild_quest_reward(session, user_id, quest_id)

    await query.answer(msg[:150], show_alert=True)
    await guild_quests_menu_callback(update, context)


async def guild_rankings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mustaqil Gildiyalar Reytingi (Sahifalanuvchi)"""
    query = update.callback_query
    await query.answer()

    try:
        page = int(query.data.split(":")[1])
    except Exception:
        page = 0

    limit = 8
    offset = page * limit

    async with AsyncSessionLocal() as session:
        guilds, total_cnt = await crud.get_guild_rankings(session, limit=limit, offset=offset)

    if not guilds and page == 0:
        text = (
            f"🏆 <b>VESTEROS GILDIYALARI REYTINGI</b>\n\n"
            f"Hozircha Vesterosda birorta ham faol gildiya mavjud emas."
        )
        buttons = [[InlineKeyboardButton("🔙 Orqaga", callback_data="menu_guild")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    text_lines = [
        "🏆 <b>VESTEROS GILDIYALARI REYTINGI (TOP BIRODARLIKLAR)</b>",
        f"<i>Sahifa: {page + 1} / {max(1, (total_cnt + limit - 1) // limit)} | Jami: {total_cnt} ta gildiya</i>\n",
        "<i>Reyting faqat jamoaviy faollik, bajarilgan vazifalar va daraja asosida hisoblanadi.</i>\n",
    ]

    for g in guilds:
        r_num = g["rank"]
        med = medals[r_num - 1] if r_num <= len(medals) else f"{r_num}."
        text_lines.append(
            f"{med} <b>{g['banner']} {html.escape(g['name'])} {html.escape(g['tag'])}</b>\n"
            f"     ⭐ Level {g['level']} ({g['xp']:,} XP) | 🏆 <b>{g['prestige']:,} Prestige</b>\n"
            f"     👑 Yetakchi: <b>{html.escape(g['leader_name'])}</b> | 👥 A'zolar: <b>{g['members_count']}/{g['max_members']}</b>\n"
        )

    buttons = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"guild_rankings:{page - 1}"))
    if (page + 1) * limit < total_cnt:
        nav_row.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"guild_rankings:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="menu_guild")])

    await query.edit_message_text("\n".join(text_lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_search_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qidirish so'rovi"""
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_guild_search"] = True

    text = (
        f"🔍 <b>GILDIYA QIDIRISH</b>\n\n"
        f"Qidirayotgan gildiyangiz nomini yoki tegini chatga yozib yuboring (masalan: <i>TITAN</i> yoki <i>Qora</i>):"
    )
    buttons = [[InlineKeyboardButton("🔙 Ro'yxatga Qaytish", callback_data="guild_list:0")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


# ============================================================
# 13. CHAT MATNLI XABARLARINI USHLASH (Text Input Handler)
# ============================================================

async def handle_guild_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiya nomlari, teglari, qidiruv va tavsiflarini chatdan qabul qilish"""
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id

    # 1. Wizard: Yangi gildiya nomi kiritilayotganda
    wiz = context.user_data.get("guild_wizard")
    if wiz and wiz.get("step") == "name":
        if len(text) < 3 or len(text) > 32:
            await update.message.reply_text("❌ Gildiya nomi 3 tadan 32 tagacha belgidan iborat bo'lishi kerak! Qaytadan yozing:")
            return

        async with AsyncSessionLocal() as session:
            existing, _ = await crud.get_active_guilds(session, search=text)
            exact = [g for g in existing if g.name.lower() == text.lower()]
            if exact:
                await update.message.reply_text(f"❌ '{text}' nomli gildiya allaqachon mavjud! Boshqa nom tanlang:")
                return

        wiz["name"] = text
        wiz["step"] = "tag"
        context.user_data["guild_wizard"] = wiz

        prompt = (
            f"🏰 Nomi: <b>{html.escape(text)}</b>\n\n"
            f"🏷️ <b>2-QADAM: Gildiya qisqartmasi (tegi)ni kiriting:</b>\n"
            f"Bu sizning o'yinchilaringiz ismida va reytingda ko'rinadigan qisqa belgi bo'ladi (2 tadan 6 tagacha harf yoki son):\n"
            f"<i>Masalan: TITAN, WOLF, CROW, VALOR</i>"
        )
        buttons = [[InlineKeyboardButton("🔙 Bekor Qilish", callback_data="menu_guild")]]
        await update.message.reply_text(prompt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # 2. Wizard: Teg kiritilayotganda
    if wiz and wiz.get("step") == "tag":
        clean_tag = text.replace("[", "").replace("]", "").upper().strip()
        if len(clean_tag) < 2 or len(clean_tag) > 6 or not clean_tag.isalnum():
            await update.message.reply_text("❌ Teg 2 tadan 6 tagacha faqat harf va sonlardan iborat bo'lishi kerak! Masalan: <code>TITAN</code>:")
            return

        formatted_tag = f"[{clean_tag}]"
        async with AsyncSessionLocal() as session:
            existing, _ = await crud.get_active_guilds(session, search=clean_tag)
            exact = [g for g in existing if g.tag.upper() == formatted_tag]
            if exact:
                await update.message.reply_text(f"❌ '{formatted_tag}' tegi band! Boshqa teg tanlang:")
                return

        wiz["tag"] = formatted_tag
        wiz["step"] = "banner"
        context.user_data["guild_wizard"] = wiz

        # Banner tanlashga yo'naltirish
        h_name = wiz.get("name", "Gildiya")
        prompt = (
            f"➕ <b>YANGI GILDIYA YARATISH (3-BOSQICH / GERB)</b>\n\n"
            f"🏰 Nomi: <b>{html.escape(h_name)}</b>\n"
            f"🏷️ Tegi: <b>{html.escape(formatted_tag)}</b>\n\n"
            f"🛡️ <b>Birodarlik bayrog'i uchun ramzni tanlang:</b>"
        )
        row1 = [InlineKeyboardButton(b, callback_data=f"guild_wiz_b:{b}") for b in BANNER_PRESETS[:6]]
        row2 = [InlineKeyboardButton(b, callback_data=f"guild_wiz_b:{b}") for b in BANNER_PRESETS[6:]]
        buttons = [row1, row2, [InlineKeyboardButton("🔙 Bekor Qilish", callback_data="menu_guild")]]
        await update.message.reply_text(prompt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # 3. Sozlamalar: Tavsif kiritilayotganda
    if context.user_data.get("awaiting_guild_desc"):
        context.user_data.pop("awaiting_guild_desc", None)
        desc = text[:200]
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, user_id)
            guild, mem = await crud.get_user_guild_membership(session, user.id)
            if guild:
                ok, msg = await crud.update_guild_settings(session, user_id, guild.id, description=desc)
                await update.message.reply_text(msg)
                await show_guild_hub(update, context, user_id, is_message=True)
        return

    # 5. Xazina: Maxsus miqdordagi oltin yoki temir kiritilganda
    dep_res = context.user_data.get("awaiting_guild_dep_res")
    if dep_res:
        context.user_data.pop("awaiting_guild_dep_res", None)
        try:
            amt = int(text.replace(" ", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text("❌ Noto'g'ri son kiritildi! Iltimos, faqat butun musbat son yozing.")
            return

        if amt <= 0:
            await update.message.reply_text("❌ Miqdor musbat bo'lishi kerak!")
            return

        async with AsyncSessionLocal() as session:
            g_amt = amt if dep_res == "gold" else 0
            i_amt = amt if dep_res == "iron" else 0
            ok, msg = await crud.deposit_to_guild_treasury(session, user_id, gold_amount=g_amt, iron_amount=i_amt)
            await update.message.reply_text(msg)
            await show_guild_hub(update, context, user_id, is_message=True)
        return

    # 4. Qidiruv: Qidiruv so'zi kiritilganda
    if context.user_data.get("awaiting_guild_search"):
        context.user_data.pop("awaiting_guild_search", None)
        async with AsyncSessionLocal() as session:
            guilds, total_cnt = await crud.get_active_guilds(session, limit=10, search=text)

        if not guilds:
            msg = f"❌ '{html.escape(text)}' so'rovi bo'yicha hech qanday gildiya topilmadi."
            buttons = [[InlineKeyboardButton("🔙 Ro'yxatga Qaytish", callback_data="guild_list:0")]]
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
            return

        msg = f"🔍 <b>QIDIRUV NATIJALARI ('{html.escape(text)}') — {len(guilds)} ta topildi:</b>\n\n"
        buttons = []
        for g in guilds:
            m_cnt = len(g.members or [])
            rec_dot = "🟢" if g.recruiting_type == "open" else ("🟡" if g.recruiting_type == "apply" else "🔴")
            btn_label = f"{g.banner} {g.name} {g.tag} | Lvl {g.level} ({m_cnt}/{g.max_members}) {rec_dot}"
            buttons.append([InlineKeyboardButton(btn_label, callback_data=f"guild_view:{g.id}:0")])
        buttons.append([InlineKeyboardButton("🔙 Ro'yxatga Qaytish", callback_data="guild_list:0")])
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return


# ============================================================


# ============================================================
# STAGE 4 — GILDIYA XAZINASI HANDLERLARI
# ============================================================

async def guild_treasury_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiya xazinasi bosh menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        tdata = await crud.get_guild_treasury_data(session, user_id)

    if not tdata:
        await query.answer("❌ Siz biron bir gildiyaga a'zo emassiz!", show_alert=True)
        return

    buff_str = "<i>Hozirda faol buff mavjud emas</i>"
    if tdata["active_buff"]:
        b = tdata["active_buff"]
        buff_str = f"🟢 <b>{html.escape(b['name'])}</b>\n⏳ Qolgan vaqt: <b>{b['remaining_str']}</b>"

    text = (
        f"🏛️ <b>GILDIYA XAZINASI — {tdata['banner']} {html.escape(tdata['guild_name'])} {html.escape(tdata['guild_tag'])}</b>\n\n"
        f"💰 <b>Xazinadagi Oltin:</b> <code>{tdata['treasury_gold']:,}</code>🪙\n"
        f"⛓️ <b>Xazinadagi Temir:</b> <code>{tdata['treasury_iron']:,}</code>⛓️\n\n"
        f"⚡ <b>Birodarlik Buffi Holati:</b>\n{buff_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Sizning balansingiz:</b> {tdata['user_gold']:,}🪙 | {tdata['user_iron']:,}⛓️\n"
        f"📊 <b>Bugungi hissangiz:</b> {tdata['daily_deposited_gold']:,} / 5,000🪙 | {tdata['daily_deposited_iron']:,} / 1,000⛓️\n"
        f"⏳ <b>Bugun topshira olasiz:</b> {tdata['remaining_daily_gold']:,}🪙 | {tdata['remaining_daily_iron']:,}⛓️\n"
        f"🌟 <b>Jami topshirganingiz:</b> {tdata['total_deposited_gold']:,}🪙 | {tdata['total_deposited_iron']:,}⛓️\n\n"
        f"💡 <i>Eslatma: Xazina mablag'lari faqat butun gildiya uchun kuchli bufflar va yangilanishlarni xarid qilishga sarflanadi. Shaxsiy hisobga qaytarib olib bo'lmaydi!</i>"
    )

    buttons = [
        [
            InlineKeyboardButton("📥 Oltin Topshirish", callback_data="guild_treasury_dep_gold_menu"),
            InlineKeyboardButton("📥 Temir Topshirish", callback_data="guild_treasury_dep_iron_menu"),
        ],
        [
            InlineKeyboardButton("⚡ Birodarlik Bufflari", callback_data="guild_treasury_buffs_menu"),
            InlineKeyboardButton("📜 Xazina Tarixi", callback_data="guild_treasury_history:0"),
        ],
        [
            InlineKeyboardButton("🔙 Mening Gildiyam", callback_data="menu_guild"),
        ]
    ]

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_treasury_dep_gold_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xazinaga oltin topshirish menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        tdata = await crud.get_guild_treasury_data(session, user_id)

    if not tdata:
        await query.answer("❌ Gildiya topilmadi!", show_alert=True)
        return

    rem = tdata["remaining_daily_gold"]
    bal = tdata["user_gold"]

    text = (
        f"🪙 <b>XAZINAGA OLTIN TOPSHIRISH</b>\n\n"
        f"💰 Shaxsiy balansingiz: <b>{bal:,}🪙</b>\n"
        f"⏳ Bugungi qolgan limit: <b>{rem:,} / 5,000🪙</b>\n\n"
        f"Qancha oltin topshirmoqchisiz?"
    )

    buttons = [
        [
            InlineKeyboardButton("+500🪙", callback_data="guild_dep_quick:gold:500"),
            InlineKeyboardButton("+1,000🪙", callback_data="guild_dep_quick:gold:1000"),
        ],
        [
            InlineKeyboardButton("+2,500🪙", callback_data="guild_dep_quick:gold:2500"),
            InlineKeyboardButton("+5,000🪙", callback_data="guild_dep_quick:gold:5000"),
        ],
        [
            InlineKeyboardButton("⚡ Maksimal", callback_data="guild_dep_quick:gold:max"),
            InlineKeyboardButton("✍️ Boshqa miqdor", callback_data="guild_dep_ask:gold"),
        ],
        [
            InlineKeyboardButton("🔙 Xazinaga Qaytish", callback_data="guild_treasury_menu"),
        ]
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_treasury_dep_iron_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xazinaga temir topshirish menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        tdata = await crud.get_guild_treasury_data(session, user_id)

    if not tdata:
        await query.answer("❌ Gildiya topilmadi!", show_alert=True)
        return

    rem = tdata["remaining_daily_iron"]
    bal = tdata["user_iron"]

    text = (
        f"⛓️ <b>XAZINAGA TEMIR TOPSHIRISH</b>\n\n"
        f"⛓️ Shaxsiy balansingiz: <b>{bal:,}⛓️</b>\n"
        f"⏳ Bugungi qolgan limit: <b>{rem:,} / 1,000⛓️</b>\n\n"
        f"Qancha temir topshirmoqchisiz?"
    )

    buttons = [
        [
            InlineKeyboardButton("+100⛓️", callback_data="guild_dep_quick:iron:100"),
            InlineKeyboardButton("+250⛓️", callback_data="guild_dep_quick:iron:250"),
        ],
        [
            InlineKeyboardButton("+500⛓️", callback_data="guild_dep_quick:iron:500"),
            InlineKeyboardButton("+1,000⛓️", callback_data="guild_dep_quick:iron:1000"),
        ],
        [
            InlineKeyboardButton("⚡ Maksimal", callback_data="guild_dep_quick:iron:max"),
            InlineKeyboardButton("✍️ Boshqa miqdor", callback_data="guild_dep_ask:iron"),
        ],
        [
            InlineKeyboardButton("🔙 Xazinaga Qaytish", callback_data="guild_treasury_menu"),
        ]
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_dep_quick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tezkor depozit tugmalari orqali xazinaga mablag' o'tkazish"""
    query = update.callback_query
    parts = query.data.split(":")
    res_type = parts[1]
    amt_arg = parts[2]
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        tdata = await crud.get_guild_treasury_data(session, user_id)
        if not tdata:
            await query.answer("❌ Gildiya topilmadi!", show_alert=True)
            return

        if res_type == "gold":
            if amt_arg == "max":
                amount = min(tdata["user_gold"], tdata["remaining_daily_gold"])
            else:
                amount = int(amt_arg)
            ok, msg = await crud.deposit_to_guild_treasury(session, user_id, gold_amount=amount, iron_amount=0)
        else:
            if amt_arg == "max":
                amount = min(tdata["user_iron"], tdata["remaining_daily_iron"])
            else:
                amount = int(amt_arg)
            ok, msg = await crud.deposit_to_guild_treasury(session, user_id, gold_amount=0, iron_amount=amount)

    await query.answer(msg, show_alert=True)
    await guild_treasury_menu_callback(update, context)


async def guild_dep_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'lda miqdor kiritish so'rovi"""
    query = update.callback_query
    await query.answer()
    res_type = query.data.split(":")[1]
    context.user_data["awaiting_guild_dep_res"] = res_type

    res_name = "oltin" if res_type == "gold" else "temir"
    icon = "🪙" if res_type == "gold" else "⛓️"
    prompt = (
        f"✍️ <b>Xazinaga topshirmoqchi bo'lgan {res_name} miqdorini yozing ({icon}):</b>\n\n"
        f"<i>Masalan: 750</i>"
    )
    buttons = [[InlineKeyboardButton("🔙 Bekor Qilish", callback_data="guild_treasury_menu")]]
    await query.edit_message_text(prompt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_treasury_buffs_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Birodarlik bufflari ro'yxati va faollashtirish menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        tdata = await crud.get_guild_treasury_data(session, user_id)

    if not tdata:
        await query.answer("❌ Gildiya topilmadi!", show_alert=True)
        return

    is_leader_or_deputy = tdata["user_role"] in ("master", "deputy")
    active_buff = tdata["active_buff"]

    text = (
        f"⚡ <b>BIRODARLIK BUFFLARI VA YANGILANISHLAR</b>\n\n"
        f"🏛️ Xazina balansi: <b>{tdata['treasury_gold']:,}🪙</b> | <b>{tdata['treasury_iron']:,}⛓️</b>\n\n"
        f"<i>Xazina mablag'larini butun jamoaga ta'sir qiluvchi kuchli bonuslarga sarflash mumkin:</i>\n\n"
    )

    buttons = []
    for code, b in crud.GUILD_BUFFS_CONFIG.items():
        cost_parts = []
        if b["gold_cost"] > 0:
            cost_parts.append(f"{b['gold_cost']:,}🪙")
        if b["iron_cost"] > 0:
            cost_parts.append(f"{b['iron_cost']:,}⛓️")
        cost_str = " + ".join(cost_parts)

        text += (
            f"<b>{b['name']}</b>\n"
            f"📖 {b['desc']}\n"
            f"💰 Narxi: <code>{cost_str}</code>\n"
        )

        if active_buff and active_buff["type"] == code:
            text += f"🟢 <b>Faol:</b> {active_buff['remaining_str']} qoldi\n\n"
            btn_text = f"🟢 {b['name']} (Faol)"
            btn_data = "guild_treasury_buffs_menu"
        else:
            can_afford = (tdata["treasury_gold"] >= b["gold_cost"]) and (tdata["treasury_iron"] >= b["iron_cost"])
            if not is_leader_or_deputy:
                text += "🔒 <i>Faqat Master / Deputy yoqa oladi</i>\n\n"
                btn_text = f"🔒 {b['name']}"
                btn_data = "guild_treasury_buffs_menu"
            elif not can_afford:
                text += "❌ <i>Xazinada mablag' yetarli emas</i>\n\n"
                btn_text = f"🔒 {b['name']} (Mablag' kam)"
                btn_data = "guild_treasury_buffs_menu"
            else:
                text += "✅ <i>Faollashtirish mumkin</i>\n\n"
                btn_text = f"⚡ Faollashtirish: {b['name']}"
                btn_data = f"guild_buff_ask:{code}"

        buttons.append([InlineKeyboardButton(btn_text, callback_data=btn_data)])

    buttons.append([InlineKeyboardButton("🔙 Xazinaga Qaytish", callback_data="guild_treasury_menu")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_buff_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buffni faollashtirishdan oldin tasdiqlash so'rovi"""
    query = update.callback_query
    await query.answer()
    buff_code = query.data.split(":")[1]

    b = crud.GUILD_BUFFS_CONFIG.get(buff_code)
    if not b:
        await query.answer("❌ Noto'g'ri buff!", show_alert=True)
        return

    cost_parts = []
    if b["gold_cost"] > 0:
        cost_parts.append(f"{b['gold_cost']:,}🪙 oltin")
    if b["iron_cost"] > 0:
        cost_parts.append(f"{b['iron_cost']:,}⛓️ temir")
    cost_str = " va ".join(cost_parts)

    prompt = (
        f"❓ <b>BIRODARLIK BUFFINI FAOLLASHTIRISH</b>\n\n"
        f"Siz rostdan ham gildiya xazinasidan <b>{cost_str}</b> sarflab, "
        f"<b>{b['name']}</b> buffini faollashtirmoqchimisiz?\n\n"
        f"<i>Ta'siri: {b['desc']}</i>"
    )
    buttons = [
        [InlineKeyboardButton("✅ Ha, Faollashtir!", callback_data=f"guild_buff_do:{buff_code}")],
        [InlineKeyboardButton("❌ Bekor Qilish", callback_data="guild_treasury_buffs_menu")],
    ]
    await query.edit_message_text(prompt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def guild_buff_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buffni xarid qilish va darhol faollashtirish"""
    query = update.callback_query
    buff_code = query.data.split(":")[1]
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.spend_guild_treasury_buff(session, user_id, buff_code)

    await query.answer(msg, show_alert=True)
    await guild_treasury_buffs_menu_callback(update, context)


async def guild_treasury_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gildiya xazinasi operatsiyalari tarixi"""
    query = update.callback_query
    await query.answer()
    page = int(query.data.split(":")[1])
    user_id = update.effective_user.id

    limit = 8
    offset = page * limit

    async with AsyncSessionLocal() as session:
        tdata = await crud.get_guild_treasury_data(session, user_id)
        if not tdata:
            await query.answer("❌ Gildiya topilmadi!", show_alert=True)
            return

        history, total_cnt = await crud.get_guild_treasury_history(session, tdata["guild_id"], limit=limit, offset=offset)

    if not history:
        text = (
            f"📜 <b>XAZINA TARIXI — {tdata['banner']} {html.escape(tdata['guild_name'])}</b>\n\n"
            f"<i>Hozircha xazina bo'yicha hech qanday amallar bajarilmagan.</i>"
        )
        buttons = [[InlineKeyboardButton("🔙 Xazinaga Qaytish", callback_data="guild_treasury_menu")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    text = (
        f"📜 <b>XAZINA TARIXI — {tdata['banner']} {html.escape(tdata['guild_name'])}</b>\n"
        f"Jami yozuvlar: {total_cnt} ta | Sahifa: {page + 1}/{(total_cnt - 1)//limit + 1}\n\n"
    )

    for tx in history:
        date_str = tx["created_at"].strftime("%d.%m %H:%M") if tx["created_at"] else ""
        icon = "📥" if tx["tx_type"] == "deposit" else "⚡"
        amounts = []
        if tx["amount_gold"] != 0:
            sign = "+" if tx["amount_gold"] > 0 else ""
            amounts.append(f"{sign}{tx['amount_gold']:,}🪙")
        if tx["amount_iron"] != 0:
            sign = "+" if tx["amount_iron"] > 0 else ""
            amounts.append(f"{sign}{tx['amount_iron']:,}⛓️")
        amt_str = " ".join(amounts)

        text += (
            f"{icon} <code>{date_str}</code> • <b>{html.escape(tx['user_name'])}</b>\n"
            f"    └ <b>{amt_str}</b>: <i>{html.escape(tx['details'] or '')}</i>\n"
        )

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"guild_treasury_history:{page - 1}"))
    if offset + limit < total_cnt:
        nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"guild_treasury_history:{page + 1}"))

    buttons = []
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("🔙 Xazinaga Qaytish", callback_data="guild_treasury_menu")])

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


# ============================================================
# 14. BARCHA HANDLERLARNI RO'YXATDAN O'TKAZISH
# ============================================================

def register_guild_handlers(app):
    """Barcha gildiya handlerlarini Telegram Application ga ulash"""
    app.add_handler(CommandHandler(["guild", "gildiya"], guild_command))
    app.add_handler(CallbackQueryHandler(guild_menu_callback, pattern="^menu_guild$"))

    # Yaratish wizardi
    app.add_handler(CallbackQueryHandler(guild_create_start_callback, pattern="^guild_create_start$"))
    app.add_handler(CallbackQueryHandler(guild_wizard_banner_pick_callback, pattern="^guild_wiz_banner_pick$"))
    app.add_handler(CallbackQueryHandler(guild_wizard_banner_selected, pattern="^guild_wiz_b:"))
    app.add_handler(CallbackQueryHandler(guild_wizard_rec_selected, pattern="^guild_wiz_rec:"))
    app.add_handler(CallbackQueryHandler(guild_wizard_create_do, pattern="^guild_wiz_create_do$"))

    # Ro'yxat va qidiruv
    app.add_handler(CallbackQueryHandler(guild_list_callback, pattern="^guild_list:"))
    app.add_handler(CallbackQueryHandler(guild_view_callback, pattern="^guild_view:"))
    app.add_handler(CallbackQueryHandler(guild_join_do_callback, pattern="^guild_join_do:"))
    app.add_handler(CallbackQueryHandler(guild_search_ask_callback, pattern="^guild_search_ask$"))

    # A'zolar ro'yxati va boshqaruvi
    app.add_handler(CallbackQueryHandler(guild_members_callback, pattern="^guild_members:"))
    app.add_handler(CallbackQueryHandler(guild_member_manage_callback, pattern="^guild_mem_manage:"))
    app.add_handler(CallbackQueryHandler(guild_role_set_callback, pattern="^guild_role_set:"))
    app.add_handler(CallbackQueryHandler(guild_kick_ask_callback, pattern="^guild_kick_ask:"))
    app.add_handler(CallbackQueryHandler(guild_kick_do_callback, pattern="^guild_kick_do:"))

    # Arizalar (Officer+)
    app.add_handler(CallbackQueryHandler(guild_apps_callback, pattern="^guild_apps:"))
    app.add_handler(CallbackQueryHandler(guild_app_do_callback, pattern="^guild_app_do:"))

    # Mening arizalarim
    app.add_handler(CallbackQueryHandler(guild_my_apps_callback, pattern="^guild_my_apps$"))
    app.add_handler(CallbackQueryHandler(guild_my_app_del_callback, pattern="^guild_my_app_del:"))

    # Yetakchilikni topshirish
    app.add_handler(CallbackQueryHandler(guild_transfer_pick_callback, pattern="^guild_transfer_pick$"))
    app.add_handler(CallbackQueryHandler(guild_transfer_ask_callback, pattern="^guild_transfer_ask:"))
    app.add_handler(CallbackQueryHandler(guild_transfer_do_callback, pattern="^guild_transfer_do:"))

    # Tarqatish
    app.add_handler(CallbackQueryHandler(guild_disband_ask_callback, pattern="^guild_disband_ask$"))
    app.add_handler(CallbackQueryHandler(guild_disband_do_callback, pattern="^guild_disband_do:"))

    # Chiqish
    app.add_handler(CallbackQueryHandler(guild_leave_ask_callback, pattern="^guild_leave_ask$"))
    app.add_handler(CallbackQueryHandler(guild_leave_do_callback, pattern="^guild_leave_do$"))

    # Sozlamalar
    app.add_handler(CallbackQueryHandler(guild_settings_callback, pattern="^guild_settings$"))
    app.add_handler(CallbackQueryHandler(guild_set_rec_ask_callback, pattern="^guild_set_rec_ask$"))
    app.add_handler(CallbackQueryHandler(guild_set_rec_do_callback, pattern="^guild_set_rec_do:"))
    app.add_handler(CallbackQueryHandler(guild_set_banner_pick_callback, pattern="^guild_set_banner_pick$"))
    app.add_handler(CallbackQueryHandler(guild_set_banner_do_callback, pattern="^guild_set_banner_do:"))
    app.add_handler(CallbackQueryHandler(guild_set_desc_ask_callback, pattern="^guild_set_desc_ask$"))

    # Vazifalar va Reyting (Stage 3)
    app.add_handler(CallbackQueryHandler(guild_quests_menu_callback, pattern="^guild_quests_menu$"))
    app.add_handler(CallbackQueryHandler(guild_quest_claim_callback, pattern="^guild_quest_claim:"))
    app.add_handler(CallbackQueryHandler(guild_rankings_callback, pattern="^guild_rankings:"))

    # Xazina va Bufflar (Stage 4)
    app.add_handler(CallbackQueryHandler(guild_treasury_menu_callback, pattern="^guild_treasury_menu$"))
    app.add_handler(CallbackQueryHandler(guild_treasury_dep_gold_menu_callback, pattern="^guild_treasury_dep_gold_menu$"))
    app.add_handler(CallbackQueryHandler(guild_treasury_dep_iron_menu_callback, pattern="^guild_treasury_dep_iron_menu$"))
    app.add_handler(CallbackQueryHandler(guild_dep_quick_callback, pattern="^guild_dep_quick:"))
    app.add_handler(CallbackQueryHandler(guild_dep_ask_callback, pattern="^guild_dep_ask:"))
    app.add_handler(CallbackQueryHandler(guild_treasury_buffs_menu_callback, pattern="^guild_treasury_buffs_menu$"))
    app.add_handler(CallbackQueryHandler(guild_buff_ask_callback, pattern="^guild_buff_ask:"))
    app.add_handler(CallbackQueryHandler(guild_buff_do_callback, pattern="^guild_buff_do:"))
    app.add_handler(CallbackQueryHandler(guild_treasury_history_callback, pattern="^guild_treasury_history:"))

    # Chat matnli xabarlarini qabul qilish (group=3)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_guild_text_input),
        group=3
    )
