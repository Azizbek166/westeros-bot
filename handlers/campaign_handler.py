"""
Campaign Mission & Pacing Handlers (O'yinchi + Admin UI, Wizard, Statistika, Sinov rejimi).
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import is_admin, escape_md
from database import crud
from database.db import AsyncSessionLocal
from services.campaign_service import (
    add_campaign_mission,
    create_campaign,
    format_campaign_min_duration,
    format_duration_uz,
    format_tashkent_dt,
    get_campaign_player_state,
    get_campaign_stats,
    get_campaign_with_missions,
    get_mission_choice_cooldown_minutes,
    get_mission_cooldown_hours,
    get_mission_daily_attempts,
    list_campaigns,
    parse_mission_options,
    parse_tashkent_dt,
    simulate_admin_test_step,
    submit_campaign_mission_action,
    toggle_campaign_notifications,
    update_campaign_settings,
    update_mission_settings,
)

logger = logging.getLogger(__name__)


async def _safe_edit_or_reply(target, text: str, reply_markup=None, parse_mode="Markdown"):
    if hasattr(target, "edit_message_text"):
        try:
            await target.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
            return
        except Exception:
            try:
                await target.edit_message_text(
                    text.replace("*", "").replace("_", "").replace("`", ""),
                    reply_markup=reply_markup,
                )
                return
            except Exception:
                await target.message.reply_text(
                    text.replace("*", "").replace("_", "").replace("`", ""),
                    reply_markup=reply_markup,
                )
                return
    try:
        await target.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        await target.reply_text(
            text.replace("*", "").replace("_", "").replace("`", ""),
            reply_markup=reply_markup,
        )


# ============================================================
# O'YINCHI QISMI (CAMPAIGN LIST, VIEW, PLAY, NOTIFY TOGGLE)
# ============================================================

async def _render_campaigns_list(target, telegram_id: int):
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, telegram_id)
        if not user:
            await _safe_edit_or_reply(target, "❌ Avval /start bosib ro'yxatdan o'ting.")
            return
        camps = await list_campaigns(session, include_drafts=False)

        lines = [
            "🗺️ **KAMPANIYA MISSIYALARI**",
            "_Uzoq muddatli hikoyaviy sarguzashtlar. Barcha o'yinchilar uchun teng vaqt qoidasi (0 Pay-To-Win)._\n",
        ]
        buttons = []
        if not camps:
            lines.append("Hozircha faol kampaniyalar yo'q. Tez orada yangi kampaniyalar ochiladi!")
        else:
            for c in camps:
                st = await get_campaign_player_state(session, user, c.id)
                total = st["total_missions"] if st else len(c.missions or [])
                done = st["progress"].completed_missions_count if st else 0
                if st and st["progress"].is_completed:
                    badge = "🏆 Yakunlangan"
                elif st and not st["unlocked"]:
                    rem = format_duration_uz(st["remaining_unlock_seconds"])
                    badge = f"⏳ {rem}"
                else:
                    badge = "🔓 Ochiq"
                lines.append(f"• **{escape_md(c.title)}** — `{done}/{total}` ({badge})")
                buttons.append([
                    InlineKeyboardButton(
                        f"🗺️ {c.title} ({done}/{total})",
                        callback_data=f"camp_view:{c.id}",
                    )
                ])

        if is_admin(telegram_id):
            buttons.append([InlineKeyboardButton("⚙️ Admin: Kampaniyalarni Boshqarish", callback_data="admin_campaigns")])
        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])
        await _safe_edit_or_reply(target, "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


async def campaigns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        try:
            await _render_campaigns_list(update.message, update.effective_user.id)
        except Exception as e:
            logger.exception(f"campaigns_command error: {e}")
            await update.message.reply_text(f"❌ Kampaniya panelini ochishda xatolik:\n{e}")


async def menu_campaigns_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await _render_campaigns_list(query, query.from_user.id)
    except Exception as e:
        logger.exception(f"menu_campaigns_callback error: {e}")
        await _safe_edit_or_reply(
            query,
            f"❌ Kampaniya panelini ochishda xatolik:\n{e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")]]),
            parse_mode=None,
        )


async def _render_campaign_view(target, telegram_id: int, campaign_id: int):
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, telegram_id)
        if not user:
            await _safe_edit_or_reply(target, "❌ Avval /start bosib ro'yxatdan o'ting.")
            return
        st = await get_campaign_player_state(session, user, campaign_id)
        if not st or st["campaign"].status != "published":
            await _safe_edit_or_reply(
                target,
                "❌ Kampaniya topilmadi yoki hali nashr qilinmagan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kampaniyalar", callback_data="menu_campaigns")]]),
            )
            return

        camp = st["campaign"]
        prog = st["progress"]
        total = st["total_missions"]
        done = prog.completed_missions_count
        rem_days = st["remaining_days_estimate"]
        cur_m = st["current_mission"]

        if prog.is_completed:
            progress_line = f"📊 **Progress:** `{done}/{total}` missiya — 🏆 **Yakunlangan!**"
        elif rem_days > 0:
            progress_line = f"📊 **Progress:** `{done}/{total}` missiya, taxminan **{rem_days} kun** qoldi"
        else:
            progress_line = f"📊 **Progress:** `{done}/{total}` missiya (bugun davom ettirish mumkin)"

        lines = [
            f"🗺️ **{escape_md(camp.title)}**",
            f"_{escape_md(camp.description or '')}_\n",
            progress_line,
        ]

        buttons = []
        if prog.is_completed:
            lines.append("\n🎉 Siz ushbu kampaniyaning barcha missiyalarini yakunladingiz!")
        elif not cur_m:
            lines.append("\n⚠️ Keyingi missiya topilmadi.")
        elif not st["unlocked"]:
            rem_str = format_duration_uz(st["remaining_unlock_seconds"])
            lines.append(f"\n⏳ **Keyingi missiya:** {rem_str}dan keyin ochiladi")
            if st["effective_unlock_at"]:
                lines.append(f"📅 Ochilish vaqti: `{format_tashkent_dt(st['effective_unlock_at'])}`")
            lines.append(f"🔒 *{cur_m.order_index}-missiya: {escape_md(cur_m.title)}*")
            buttons.append([
                InlineKeyboardButton(
                    f"🔒 {cur_m.order_index}-missiya ({rem_str})",
                    callback_data=f"camp_locked_info:{camp.id}:{cur_m.order_index}",
                )
            ])
        else:
            lines.append(f"\n📜 **{cur_m.order_index}-missiya: {escape_md(cur_m.title)}**")
            lines.append(f"{cur_m.story_text}\n")

            mtype = (cur_m.mission_type or "story").lower()
            if mtype in ("quiz", "riddle"):
                lines.append(f"🎯 Bugungi urinishlar: **{st['attempts_left']}/{st['max_daily_attempts']}**")
                if st["attempts_left"] <= 0:
                    mid_str = format_duration_uz(st["midnight_reset_seconds"])
                    lines.append(f"🚫 Urinishlar tugadi, ertaga qayta urinib ko'ring ({mid_str} qoldi).")
            if mtype == "quiz" and st["choice_cooldown_seconds"] > 0:
                lines.append(f"⏳ Qayta tanlash kutishi: **{format_duration_uz(st['choice_cooldown_seconds'])}**")

            if mtype == "story":
                buttons.append([
                    InlineKeyboardButton(
                        "▶️ Davom etish",
                        callback_data=f"camp_act:{camp.id}:{cur_m.order_index}:continue",
                    )
                ])
            elif mtype in ("quiz", "branch"):
                for opt in parse_mission_options(cur_m):
                    buttons.append([
                        InlineKeyboardButton(
                            str(opt.get("text", opt.get("key"))),
                            callback_data=f"camp_act:{camp.id}:{cur_m.order_index}:{opt.get('key')}",
                        )
                    ])
            elif mtype == "riddle":
                buttons.append([
                    InlineKeyboardButton(
                        "✍️ Javob Yozish",
                        callback_data=f"camp_riddle_ask:{camp.id}:{cur_m.order_index}",
                    )
                ])

        notify_label = "🔔 Bildirishnoma: YOQIQ" if prog.notify_enabled else "🔕 Bildirishnoma: O'CHIQ"
        buttons.append([InlineKeyboardButton(notify_label, callback_data=f"camp_notify_toggle:{camp.id}")])
        buttons.append([InlineKeyboardButton("🔄 Yangilash", callback_data=f"camp_view:{camp.id}")])
        buttons.append([InlineKeyboardButton("🔙 Kampaniyalar Ro'yxati", callback_data="menu_campaigns")])

        await _safe_edit_or_reply(target, "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


async def camp_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        camp_id = int((query.data or "").split(":")[1])
    except Exception:
        return
    await _render_campaign_view(query, query.from_user.id, camp_id)


async def camp_locked_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = (query.data or "").split(":")
    try:
        camp_id = int(parts[1])
    except Exception:
        await query.answer("⏳ Missiya hali ochilmagan.", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, query.from_user.id)
        st = await get_campaign_player_state(session, user, camp_id) if user else None
    if st and not st["unlocked"]:
        rem = format_duration_uz(st["remaining_unlock_seconds"])
        await query.answer(f"⏳ Hali ochilmagan! Keyingi missiya {rem}dan keyin ochiladi.", show_alert=True)
    else:
        await query.answer("🔓 Missiya ochildi! Sahifa yangilanmoqda...", show_alert=False)
        await _render_campaign_view(query, query.from_user.id, camp_id)


async def camp_notify_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        camp_id = int((query.data or "").split(":")[1])
    except Exception:
        await query.answer()
        return
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, query.from_user.id)
        if not user:
            await query.answer("❌ Foydalanuvchi topilmadi.", show_alert=True)
            return
        ok, enabled = await toggle_campaign_notifications(session, user, camp_id)
    if ok:
        msg = "🔔 Yangi missiya ochilganda xabar yuboriladi." if enabled else "🔕 Ushbu kampaniya bildirishnomalari o'chirildi."
        await query.answer(msg, show_alert=True)
    else:
        await query.answer("❌ Xatolik.", show_alert=True)
    await _render_campaign_view(query, query.from_user.id, camp_id)


async def camp_act_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = (query.data or "").split(":", 3)
    if len(parts) < 4:
        await query.answer()
        return
    try:
        camp_id = int(parts[1])
        mission_order = int(parts[2])
        action_val = parts[3]
    except Exception:
        await query.answer("❌ Noto'g'ri so'rov.", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, query.from_user.id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        res = await submit_campaign_mission_action(
            session=session,
            user_id=user.id,
            campaign_id=camp_id,
            mission_order=mission_order,
            action_value=action_val,
        )

    await query.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗺️ Kampaniya Sahifasi", callback_data=f"camp_view:{camp_id}")],
        [InlineKeyboardButton("🔙 Kampaniyalar", callback_data="menu_campaigns")],
    ])
    await _safe_edit_or_reply(query, res["message"], reply_markup=kb)


async def camp_riddle_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = (query.data or "").split(":")
    try:
        camp_id = int(parts[1])
        mission_order = int(parts[2])
    except Exception:
        await query.answer()
        return
    await query.answer()
    context.user_data["camp_awaiting_riddle"] = {"campaign_id": camp_id, "mission_order": mission_order}
    await _safe_edit_or_reply(
        query,
        "✍️ **JUMBOQ JAVOBINI YUBORING**\n\nJavobingizni bitta xabar ko'rinishida yozing (bekor qilish: `/cancel`).",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data=f"camp_view:{camp_id}")]]),
    )


# ============================================================
# ADMIN QISMI (LIST, WIZARD, SETTINGS, STATS, TEST MODE)
# ============================================================

async def admin_campaigns_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    try:
        async with AsyncSessionLocal() as session:
            camps = await list_campaigns(session, include_drafts=True)

        lines = ["⚙️ **ADMIN: KAMPANIYALAR BOSHQARUVI**\n"]
        buttons = []
        for c in camps:
            st_icon = "🟢" if c.status == "published" else ("📝" if c.status == "draft" else "📦")
            mode_icon = "📅" if c.unlock_mode == "calendar" else f"⏳{c.default_cooldown_hours}h"
            dur = format_campaign_min_duration(c, c.missions or [])
            lines.append(f"{st_icon} **#{c.id} {escape_md(c.title)}** | {mode_icon} | {dur}")
            buttons.append([InlineKeyboardButton(f"{st_icon} #{c.id} {c.title}", callback_data=f"admin_camp_view:{c.id}")])

        buttons.append([InlineKeyboardButton("➕ Yangi Kampaniya Yaratish (Wizard)", callback_data="admin_camp_new")])
        buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
        await _safe_edit_or_reply(query, "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.exception(f"admin_campaigns_callback error: {e}")
        await _safe_edit_or_reply(
            query,
            f"❌ Admin kampaniyalar panelini ochishda xatolik:\n{e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]),
            parse_mode=None,
        )


async def _render_admin_campaign_view(target, campaign_id: int):
    async with AsyncSessionLocal() as session:
        camp = await get_campaign_with_missions(session, campaign_id)
        if not camp:
            await _safe_edit_or_reply(target, "❌ Kampaniya topilmadi.")
            return
        missions = sorted(camp.missions or [], key=lambda m: m.order_index)
        dur = format_campaign_min_duration(camp, missions)

    text = (
        f"⚙️ **KAMPANIYA #{camp.id}: {escape_md(camp.title)}**\n\n"
        f"• Holat: `{camp.status}`\n"
        f"• Ochilish rejimi: `{camp.unlock_mode}`\n"
        f"• Standart kutish: `{camp.default_cooldown_hours} soat`\n"
        f"• Kunlik urinishlar limiti: `{camp.default_daily_attempts} ta/kun` (Toshkent 00:00 reset)\n"
        f"• Noto'g'ri tanlov kutishi: `{camp.default_choice_cooldown_minutes} daqiqa`\n"
        f"• ⏱️ **Minimal davomiylik:** {dur}\n"
    )
    pub_btn = (
        InlineKeyboardButton("📝 Draftga o'tkazish", callback_data=f"admin_camp_set:{camp.id}:status:draft")
        if camp.status == "published"
        else InlineKeyboardButton("🟢 Nashr qilish (Publish)", callback_data=f"admin_camp_set:{camp.id}:status:published")
    )
    buttons = [
        [InlineKeyboardButton("📊 Statistika (Kutayotganlar)", callback_data=f"admin_camp_stats:{camp.id}")],
        [InlineKeyboardButton("🧪 Admin Sinov Rejimi (Tez sinash)", callback_data=f"admin_camp_test:{camp.id}:1")],
        [InlineKeyboardButton("⚙️ Vaqt va Limit Sozlamalari", callback_data=f"admin_camp_settings:{camp.id}")],
        [InlineKeyboardButton("📜 Missiyalar & Alohida Vaqtlar", callback_data=f"admin_camp_missions:{camp.id}")],
        [pub_btn],
        [InlineKeyboardButton("🔙 Kampaniyalar", callback_data="admin_campaigns")],
    ]
    await _safe_edit_or_reply(target, text, reply_markup=InlineKeyboardMarkup(buttons))


async def admin_camp_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    camp_id = int((query.data or "").split(":")[1])
    await _render_admin_campaign_view(query, camp_id)


async def admin_camp_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    camp_id = int((query.data or "").split(":")[1])
    async with AsyncSessionLocal() as session:
        st = await get_campaign_stats(session, camp_id)
    if not st:
        await query.answer("❌ Topilmadi.", show_alert=True)
        return

    camp = st["campaign"]
    lines = [
        f"📊 **KAMPANIYA STATISTIKASI: {escape_md(camp.title)}**\n",
        f"• ⏱️ Minimal davomiylik: **{st['min_duration_label']}**",
        f"• 👥 Jami boshlagan o'yinchilar: **{st['total_players']} ta**",
        f"• 🏆 To'liq yakunlaganlar: **{st['completed_players']} ta**\n",
        "⏳ **Har missiyada kutish holatida turganlar:**",
    ]
    for m in st["missions"]:
        w = st["waiting_by_mission"].get(m.order_index, 0)
        a = st["active_by_mission"].get(m.order_index, 0)
        lines.append(f"• {m.order_index}-missiya ({escape_md(m.title)}): ⏳ Kutmoqda: **{w}** | 🔓 Ochiq: **{a}**")

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data=f"admin_camp_view:{camp_id}")]])
    await _safe_edit_or_reply(query, "\n".join(lines), reply_markup=kb)


async def admin_camp_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    camp_id = int((query.data or "").split(":")[1])
    async with AsyncSessionLocal() as session:
        camp = await get_campaign_with_missions(session, camp_id)
    if not camp:
        return

    text = (
        f"⚙️ **SOZLAMALAR: {escape_md(camp.title)}**\n"
        f"_Nashr qilingan kampaniyada o'zgartirish yangi o'yinchilar va hali ochilmagan missiyalarga qo'llanadi, eski progress saqlanadi._\n\n"
        f"• Rejim: `{camp.unlock_mode}`\n"
        f"• Standart kutish: `{camp.default_cooldown_hours} soat`\n"
        f"• Kunlik urinish: `{camp.default_daily_attempts}`\n"
        f"• Noto'g'ri tanlov kutishi: `{camp.default_choice_cooldown_minutes} daqiqa`"
    )
    next_mode = "calendar" if camp.unlock_mode == "cooldown" else "cooldown"
    buttons = [
        [InlineKeyboardButton(f"🔀 Rejimni almashtirish -> {next_mode}", callback_data=f"admin_camp_set:{camp_id}:mode:{next_mode}")],
        [
            InlineKeyboardButton("⏳ 12 soat", callback_data=f"admin_camp_set:{camp_id}:cd:12"),
            InlineKeyboardButton("⏳ 24 soat", callback_data=f"admin_camp_set:{camp_id}:cd:24"),
            InlineKeyboardButton("⏳ 48 soat", callback_data=f"admin_camp_set:{camp_id}:cd:48"),
            InlineKeyboardButton("⏳ 72 soat", callback_data=f"admin_camp_set:{camp_id}:cd:72"),
        ],
        [
            InlineKeyboardButton("🎯 2 urinish", callback_data=f"admin_camp_set:{camp_id}:att:2"),
            InlineKeyboardButton("🎯 3 urinish", callback_data=f"admin_camp_set:{camp_id}:att:3"),
            InlineKeyboardButton("🎯 5 urinish", callback_data=f"admin_camp_set:{camp_id}:att:5"),
        ],
        [
            InlineKeyboardButton("⏱️ Tanlov kutish: 15m", callback_data=f"admin_camp_set:{camp_id}:ccd:15"),
            InlineKeyboardButton("⏱️ 30m", callback_data=f"admin_camp_set:{camp_id}:ccd:30"),
            InlineKeyboardButton("⏱️ 60m", callback_data=f"admin_camp_set:{camp_id}:ccd:60"),
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data=f"admin_camp_view:{camp_id}")],
    ]
    await _safe_edit_or_reply(query, text, reply_markup=InlineKeyboardMarkup(buttons))


async def admin_camp_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    parts = (query.data or "").split(":")
    camp_id = int(parts[1])
    field = parts[2]
    val = parts[3]

    kwargs = {}
    if field == "status":
        kwargs["status"] = val
    elif field == "mode":
        kwargs["unlock_mode"] = val
    elif field == "cd":
        kwargs["default_cooldown_hours"] = int(val)
    elif field == "att":
        kwargs["default_daily_attempts"] = int(val)
    elif field == "ccd":
        kwargs["default_choice_cooldown_minutes"] = int(val)

    async with AsyncSessionLocal() as session:
        ok, msg, _ = await update_campaign_settings(session, camp_id, **kwargs)
    await query.answer(msg, show_alert=False)
    if field == "status":
        await _render_admin_campaign_view(query, camp_id)
    else:
        await admin_camp_settings_callback(update, context)


async def _render_admin_camp_missions(target, camp_id: int):
    async with AsyncSessionLocal() as session:
        camp = await get_campaign_with_missions(session, camp_id)
    if not camp:
        return
    missions = sorted(camp.missions or [], key=lambda m: m.order_index)
    lines = [f"📜 **MISSIYALAR: {escape_md(camp.title)}**\n"]
    buttons = []
    for m in missions:
        cd = get_mission_cooldown_hours(camp, m)
        att = get_mission_daily_attempts(camp, m)
        ccd = get_mission_choice_cooldown_minutes(camp, m)
        cal = format_tashkent_dt(m.calendar_unlock_at) if m.calendar_unlock_at else "—"
        lines.append(
            f"• **{m.order_index}. {escape_md(m.title)}** (`{m.mission_type}`) | "
            f"⏳ {cd}h | 🎯 {att}/kun | ⏱️ {ccd}m | 📅 {cal}"
        )
        buttons.append([
            InlineKeyboardButton(f"⏳ {m.order_index}-m: 72h", callback_data=f"admin_m_set:{camp_id}:{m.id}:cd:72"),
            InlineKeyboardButton(f"♻️ Standart", callback_data=f"admin_m_set:{camp_id}:{m.id}:cd:default"),
            InlineKeyboardButton(f"📅 Sana", callback_data=f"admin_m_cal_ask:{camp_id}:{m.id}"),
        ])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"admin_camp_view:{camp_id}")])
    await _safe_edit_or_reply(target, "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


async def admin_camp_missions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    camp_id = int((query.data or "").split(":")[1])
    await _render_admin_camp_missions(query, camp_id)


async def admin_m_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    parts = (query.data or "").split(":")
    camp_id = int(parts[1])
    mission_id = int(parts[2])
    field = parts[3]
    val = parts[4]
    async with AsyncSessionLocal() as session:
        if field == "cd":
            override = None if val == "default" else int(val)
            _, msg, _ = await update_mission_settings(session, mission_id, cooldown_hours_override=override)
        else:
            msg = "✅ Saqlandi."
    await query.answer(msg)
    await _render_admin_camp_missions(query, camp_id)


async def admin_m_cal_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    parts = (query.data or "").split(":")
    camp_id, mission_id = int(parts[1]), int(parts[2])
    context.user_data["admin_camp_cal_input"] = {"campaign_id": camp_id, "mission_id": mission_id}
    await _safe_edit_or_reply(
        query,
        "📅 **KALENDAR OCHILISH SANASINI KIRITING (Toshkent vaqti)**\n\n"
        "Format: `YYYY-MM-DD HH:MM` (masalan: `2026-12-01 10:00`) yoki o'chirish uchun `none` yozing.\n"
        "Bekor qilish: `/cancel`.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data=f"admin_camp_missions:{camp_id}")]]),
    )


# ============================================================
# ADMIN SINOV REJIMI (READ-ONLY, KUTISHLARSIZ)
# ============================================================

async def admin_camp_test_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    parts = (query.data or "").split(":")
    camp_id = int(parts[1])
    order = int(parts[2])
    action_val = parts[3] if len(parts) > 3 else None

    async with AsyncSessionLocal() as session:
        camp = await get_campaign_with_missions(session, camp_id)
        if not camp:
            await _safe_edit_or_reply(query, "❌ Kampaniya topilmadi.")
            return
        missions = sorted(camp.missions or [], key=lambda m: m.order_index)

        header_note = ""
        if action_val is not None:
            sim = await simulate_admin_test_step(session, camp_id, order, action_val)
            header_note = sim["message"] + "\n\n"
            if sim["ok"]:
                if sim.get("completed_campaign"):
                    await _safe_edit_or_reply(
                        query,
                        f"{header_note}🏆 **[SINOV YAKUNLANDI]** Barcha {len(missions)} ta missiya muvaffaqiyatli tekshirildi (haqiqiy progressga yozilmadi).",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kampaniya", callback_data=f"admin_camp_view:{camp_id}")]]),
                    )
                    return
                order = sim["next_mission_order"]

        m = next((x for x in missions if x.order_index == order), None)
        if not m:
            await _safe_edit_or_reply(
                query,
                "❌ Missiya topilmadi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kampaniya", callback_data=f"admin_camp_view:{camp_id}")]]),
            )
            return

    text = (
        f"{header_note}🧪 **ADMIN SINOV REJIMI** *(kutishlar o'tkazib yuboriladi, bazaga yozilmaydi)*\n"
        f"🗺️ {escape_md(camp.title)} — **{m.order_index}/{len(missions)}: {escape_md(m.title)}** (`{m.mission_type}`)\n\n"
        f"{m.story_text}"
    )
    buttons = []
    if m.mission_type in ("quiz", "branch"):
        for opt in parse_mission_options(m):
            buttons.append([
                InlineKeyboardButton(
                    str(opt.get("text", opt.get("key"))),
                    callback_data=f"admin_camp_test:{camp_id}:{m.order_index}:{opt.get('key')}",
                )
            ])
    else:
        buttons.append([
            InlineKeyboardButton(
                "⏩ Keyingi Missiyaga O'tish (Sinov)",
                callback_data=f"admin_camp_test:{camp_id}:{m.order_index}:ok",
            )
        ])
    buttons.append([InlineKeyboardButton("🔙 Sinovni Tugatish", callback_data=f"admin_camp_view:{camp_id}")])
    await _safe_edit_or_reply(query, text, reply_markup=InlineKeyboardMarkup(buttons))


# ============================================================
# ADMIN KAMPANIYA YARATISH WIZARDI
# ============================================================

async def admin_camp_new_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    context.user_data["admin_camp_wizard"] = {"step": "title"}
    await _safe_edit_or_reply(
        query,
        "🧙‍♂️ **YANGI KAMPANIYA WIZARDI (1/4)**\n\nKampaniya nomini yozib yuboring (bekor qilish: `/cancel`):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bekor qilish", callback_data="admin_campaigns")]]),
    )


async def admin_camp_wiz_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    wiz = context.user_data.get("admin_camp_wizard")
    if not wiz:
        return
    parts = (query.data or "").split(":")
    key, val = parts[1], parts[2]

    if key == "mode":
        wiz["unlock_mode"] = val
        wiz["step"] = "cooldown"
        await _safe_edit_or_reply(
            query,
            "🧙‍♂️ **WIZARD (3/4): MISSIYALAR ORASIDAGI KUTISH VAQTI**\n\nStandart kutish vaqtini tanlang:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⏳ 12 soat", callback_data="admin_cwiz:cd:12"),
                    InlineKeyboardButton("⏳ 24 soat (Standart)", callback_data="admin_cwiz:cd:24"),
                    InlineKeyboardButton("⏳ 48 soat", callback_data="admin_cwiz:cd:48"),
                ],
                [InlineKeyboardButton("🔙 Bekor qilish", callback_data="admin_campaigns")],
            ]),
        )
    elif key == "cd":
        wiz["default_cooldown_hours"] = int(val)
        wiz["step"] = "confirm"
        cd_h = wiz["default_cooldown_hours"]
        sample_10_days = (10 * cd_h) // 24
        await _safe_edit_or_reply(
            query,
            f"🧙‍♂️ **WIZARD (4/4): TASDIQLASH**\n\n"
            f"• Nomi: **{escape_md(wiz['title'])}**\n"
            f"• Tavsif: _{escape_md(wiz.get('description', ''))}_\n"
            f"• Rejim: `{wiz.get('unlock_mode', 'cooldown')}`\n"
            f"• Standart kutish: `{cd_h} soat`\n"
            f"• Kunlik urinishlar: `3 ta/kun`\n"
            f"• ⏱️ **Minimal davomiylik namunasi:** 10 missiya × {cd_h} soat = **kamida {sample_10_days} kun**\n\n"
            f"Kampaniyani yaratishni tasdiqlaysizmi?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yaratish (Draft)", callback_data="admin_cwiz:save:1")],
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_campaigns")],
            ]),
        )
    elif key == "save":
        async with AsyncSessionLocal() as session:
            camp = await create_campaign(
                session=session,
                title=wiz["title"],
                description=wiz.get("description", ""),
                unlock_mode=wiz.get("unlock_mode", "cooldown"),
                default_cooldown_hours=wiz.get("default_cooldown_hours", 24),
                default_daily_attempts=3,
                default_choice_cooldown_minutes=30,
                status="draft",
                created_by=query.from_user.id,
            )
        context.user_data.pop("admin_camp_wizard", None)
        await _render_admin_campaign_view(query, camp.id)


# ============================================================
# MATNLI KIRISHLAR (RIDDLE JAVOBI, WIZARD, KALENDAR SANASI)
# ============================================================

async def campaign_text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    u_data = context.user_data
    user_id = update.effective_user.id

    # 1. O'yinchi jumboq javobi
    riddle_ctx = u_data.get("camp_awaiting_riddle")
    if riddle_ctx:
        if text.lower() in ("/cancel", "bekor"):
            u_data.pop("camp_awaiting_riddle", None)
            await update.message.reply_text("❌ Javob yuborish bekor qilindi.")
            return
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, user_id)
            if not user:
                u_data.pop("camp_awaiting_riddle", None)
                return
            res = await submit_campaign_mission_action(
                session=session,
                user_id=user.id,
                campaign_id=riddle_ctx["campaign_id"],
                mission_order=riddle_ctx["mission_order"],
                action_value=text,
            )
        if res["ok"] or res.get("code") in ("wrong_and_limit_reached", "daily_limit_reached", "locked", "stale_mission"):
            u_data.pop("camp_awaiting_riddle", None)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗺️ Kampaniya Sahifasi", callback_data=f"camp_view:{riddle_ctx['campaign_id']}")],
        ])
        await _safe_edit_or_reply(update.message, res["message"], reply_markup=kb)
        return

    # 2. Admin kalendar sanasi kiritish
    cal_ctx = u_data.get("admin_camp_cal_input")
    if cal_ctx and is_admin(user_id):
        if text.lower() in ("/cancel", "bekor"):
            u_data.pop("admin_camp_cal_input", None)
            await update.message.reply_text("❌ Bekor qilindi.")
            return
        if text.lower() == "none":
            dt_utc = None
        else:
            dt_utc = parse_tashkent_dt(text)
            if dt_utc is None:
                await update.message.reply_text("❌ Format xato! Masalan: `2026-12-01 10:00`", parse_mode="Markdown")
                return
        async with AsyncSessionLocal() as session:
            _, msg, _ = await update_mission_settings(session, cal_ctx["mission_id"], calendar_unlock_at=dt_utc)
        u_data.pop("admin_camp_cal_input", None)
        await update.message.reply_text(
            f"{msg}\n📅 Yangi sana: {format_tashkent_dt(dt_utc)}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📜 Missiyalar", callback_data=f"admin_camp_missions:{cal_ctx['campaign_id']}")]]),
        )
        return

    # 3. Admin kampaniya wizardi (title -> description)
    wiz = u_data.get("admin_camp_wizard")
    if wiz and is_admin(user_id):
        if text.lower() in ("/cancel", "bekor"):
            u_data.pop("admin_camp_wizard", None)
            await update.message.reply_text("❌ Wizard bekor qilindi.")
            return
        if wiz.get("step") == "title":
            wiz["title"] = text[:180]
            wiz["step"] = "description"
            await update.message.reply_text("🧙‍♂️ **WIZARD (2/4)**\n\nKampaniya tavsifini yozib yuboring:", parse_mode="Markdown")
            return
        if wiz.get("step") == "description":
            wiz["description"] = text[:600]
            wiz["step"] = "mode"
            await update.message.reply_text(
                "🧙‍♂️ **WIZARD (2.5/4): OCHILISH REJIMINI TANLANG**\n\n"
                "• **Kutish rejimi (Cooldown):** har missiyadan keyin belgilangan soat kutish\n"
                "• **Kalendar rejimi (Calendar):** har missiya aniq sana va vaqtda ochiladi",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏳ Kutish rejimi (Cooldown)", callback_data="admin_cwiz:mode:cooldown")],
                    [InlineKeyboardButton("📅 Kalendar rejimi (Calendar)", callback_data="admin_cwiz:mode:calendar")],
                ]),
            )
            return


def register_campaign_handlers(app: Application):
    app.add_handler(CommandHandler(["campaign", "campaigns"], campaigns_command))
    app.add_handler(CallbackQueryHandler(menu_campaigns_callback, pattern="^menu_campaigns$"))
    app.add_handler(CallbackQueryHandler(camp_view_callback, pattern="^camp_view:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(camp_locked_info_callback, pattern="^camp_locked_info:[0-9]+:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(camp_notify_toggle_callback, pattern="^camp_notify_toggle:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(camp_act_callback, pattern="^camp_act:[0-9]+:[0-9]+:.+$"))
    app.add_handler(CallbackQueryHandler(camp_riddle_ask_callback, pattern="^camp_riddle_ask:[0-9]+:[0-9]+$"))

    # Admin handlers
    app.add_handler(CallbackQueryHandler(admin_campaigns_callback, pattern="^admin_campaigns$"))
    app.add_handler(CallbackQueryHandler(admin_camp_view_callback, pattern="^admin_camp_view:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_camp_stats_callback, pattern="^admin_camp_stats:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_camp_settings_callback, pattern="^admin_camp_settings:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_camp_set_callback, pattern="^admin_camp_set:[0-9]+:[a-z]+:.+$"))
    app.add_handler(CallbackQueryHandler(admin_camp_missions_callback, pattern="^admin_camp_missions:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_m_set_callback, pattern="^admin_m_set:[0-9]+:[0-9]+:[a-z]+:.+$"))
    app.add_handler(CallbackQueryHandler(admin_m_cal_ask_callback, pattern="^admin_m_cal_ask:[0-9]+:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_camp_test_callback, pattern="^admin_camp_test:[0-9]+:[0-9]+(:.*)?$"))
    app.add_handler(CallbackQueryHandler(admin_camp_new_callback, pattern="^admin_camp_new$"))
    app.add_handler(CallbackQueryHandler(admin_camp_wiz_choice_callback, pattern="^admin_cwiz:[a-z]+:.+$"))

    # Matnli kirishlar (group=4 — boshqa handlerlarga xalaqit bermaydi)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, campaign_text_input_handler),
        group=4,
    )
