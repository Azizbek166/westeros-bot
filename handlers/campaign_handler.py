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
    compute_player_campaign_power,
    create_campaign,
    delete_campaign,
    delete_campaign_mission,
    format_campaign_min_duration,
    format_completion_rewards_preview,
    format_duration_uz,
    format_tashkent_dt,
    get_campaign_player_counts,
    get_campaign_player_state,
    get_campaign_stats,
    get_campaign_with_missions,
    get_mission_choice_cooldown_minutes,
    get_mission_cooldown_hours,
    get_mission_daily_attempts,
    list_campaigns,
    parse_completion_rewards,
    parse_mission_options,
    parse_task_data,
    parse_tashkent_dt,
    simulate_admin_test_step,
    submit_campaign_mission_action,
    toggle_campaign_notifications,
    update_campaign_info,
    update_campaign_settings,
    update_mission_details,
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
                min_lvl = max(1, int(getattr(c, "min_level", 1) or 1))
                lvl_tag = f" [Lvl {min_lvl}+]" if min_lvl > 1 else ""
                if st and st["progress"].is_completed:
                    badge = "✅ Yakunlangan"
                    btn_icon = "✅"
                elif done == 0 and st and st["unlocked"]:
                    badge = "🆕 Yangi"
                    btn_icon = "🆕"
                elif st and not st["unlocked"]:
                    rem = format_duration_uz(st["remaining_unlock_seconds"])
                    badge = f"⏳ Jarayonda ({done}/{total} • {rem})"
                    btn_icon = "⏳"
                else:
                    badge = f"⏳ Jarayonda ({done}/{total} • 🔓 Ochiq)"
                    btn_icon = "▶️"
                lines.append(f"• **{escape_md(c.title)}**{lvl_tag} — {badge}")
                buttons.append([
                    InlineKeyboardButton(
                        f"{btn_icon} {c.title} ({done}/{total})",
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

        min_lvl = max(1, int(getattr(camp, "min_level", 1) or 1))
        user_lvl = max(1, int(getattr(user, "level", 1) or 1))
        grand_preview = format_completion_rewards_preview(camp)

        lines = [
            f"🗺️ **{escape_md(camp.title)}**",
            f"_{escape_md(camp.description or '')}_\n",
            progress_line,
            f"🎖️ **Daraja talabi:** `{min_lvl}+` (sizda: `{user_lvl}`)",
            f"🏆 **Final mukofoti:** {grand_preview}",
        ]

        buttons = []
        if user_lvl < min_lvl and not prog.is_completed:
            lines.append(f"\n🔒 Ushbu kampaniyani o'ynash uchun kamida **{min_lvl}-daraja**ga yeting.")
        elif prog.is_completed:
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
            tdata = parse_task_data(cur_m)
            if mtype in ("quiz", "narrative_choice", "riddle", "riddle_investigation", "combat", "combat_encounter"):
                lines.append(f"🎯 Bugungi urinishlar: **{st['attempts_left']}/{st['max_daily_attempts']}**")
                if st["attempts_left"] <= 0:
                    mid_str = format_duration_uz(st["midnight_reset_seconds"])
                    lines.append(f"🚫 Urinishlar tugadi, ertaga qayta urinib ko'ring ({mid_str} qoldi).")
            if mtype in ("quiz", "narrative_choice") and st["choice_cooldown_seconds"] > 0:
                lines.append(f"⏳ Qayta tanlash kutishi: **{format_duration_uz(st['choice_cooldown_seconds'])}**")

            if mtype == "story":
                start_lbl = "⚔️ Kampaniyani Boshlash" if done == 0 else "▶️ Davom etish"
                buttons.append([
                    InlineKeyboardButton(
                        start_lbl,
                        callback_data=f"camp_act:{camp.id}:{cur_m.order_index}:continue",
                    )
                ])
            elif mtype in ("quiz", "narrative_choice", "branch"):
                for opt in parse_mission_options(cur_m):
                    buttons.append([
                        InlineKeyboardButton(
                            str(opt.get("text", opt.get("key"))),
                            callback_data=f"camp_act:{camp.id}:{cur_m.order_index}:{opt.get('key')}",
                        )
                    ])
            elif mtype in ("combat", "combat_encounter"):
                enemy_name = tdata.get("enemy_name") or "Qaroqchilar Boshlig'i"
                enemy_hp = int(tdata.get("enemy_hp", 200) or 200)
                enemy_atk = int(tdata.get("enemy_attack", 40) or 40)
                enemy_pwr = int(tdata.get("enemy_power", enemy_hp + enemy_atk * 5) or (enemy_hp + enemy_atk * 5))
                p_pwr = await compute_player_campaign_power(session, user)
                lines.append(f"👹 **Raqib:** {escape_md(enemy_name)} (Quvvat: `{enemy_pwr:,}`)")
                lines.append(f"⚔️ **Sizning quvvatingiz:** `{p_pwr:,}`")
                buttons.append([
                    InlineKeyboardButton(
                        f"🗡️ Jang Qilish ({enemy_name})",
                        callback_data=f"camp_act:{camp.id}:{cur_m.order_index}:fight",
                    )
                ])
            elif mtype in ("tribute", "resource_tribute"):
                cost_parts = []
                if tdata.get("cost_gold"):
                    cost_parts.append(f"{int(tdata['cost_gold']):,}🪙")
                if tdata.get("cost_food"):
                    cost_parts.append(f"{int(tdata['cost_food']):,}🌾")
                if tdata.get("cost_iron"):
                    cost_parts.append(f"{int(tdata['cost_iron']):,}⛓️")
                cost_label = ", ".join(cost_parts) or "Resurs"
                btn_txt = tdata.get("button_text") or f"💰 To'lash / Pora Berish ({cost_label})"
                buttons.append([
                    InlineKeyboardButton(
                        btn_txt,
                        callback_data=f"camp_act:{camp.id}:{cur_m.order_index}:pay",
                    )
                ])
            elif mtype in ("riddle", "riddle_investigation"):
                if tdata.get("clue_text"):
                    buttons.append([
                        InlineKeyboardButton(
                            "🔍 Dalilni Tekshirish",
                            callback_data=f"camp_clue:{camp.id}:{cur_m.order_index}",
                        )
                    ])
                r_opts = parse_mission_options(cur_m)
                if r_opts:
                    for opt in r_opts:
                        buttons.append([
                            InlineKeyboardButton(
                                str(opt.get("text", opt.get("key"))),
                                callback_data=f"camp_act:{camp.id}:{cur_m.order_index}:{opt.get('key')}",
                            )
                        ])
                else:
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
# ADMIN QISMI (LIST, WIZARD, EDIT, STAGE BUILDER, STATS, TEST)
# ============================================================

ADMIN_FSM_KEYS = (
    "admin_camp_wizard",
    "admin_camp_edit",
    "admin_camp_add_mission",
    "admin_m_edit",
    "admin_camp_cal_input",
)


def _clear_admin_campaign_fsm(user_data: dict):
    for k in ADMIN_FSM_KEYS:
        user_data.pop(k, None)


def _cancel_kb(back_cb: str = "admin_campaigns") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"admin_camp_cancel:{back_cb}")]
    ])


def _is_skip_val(text: str) -> bool:
    return (text or "").strip().lower() in ("0", "yo'q", "yoq", "no", "-", "none")


async def _render_admin_campaigns_list(target):
    async with AsyncSessionLocal() as session:
        camps = await list_campaigns(session, include_drafts=True)
        counts = await get_campaign_player_counts(session)

    lines = ["📜 **KAMPANIYALAR BOSHQARUVI (ADMIN)**\n"]
    buttons = []
    if not camps:
        lines.append("Hozircha kampaniyalar yaratilmagan.")
    for c in camps:
        is_pub = c.status == "published"
        st_icon = "🟢" if is_pub else "🔴"
        st_lbl = "Faol" if is_pub else "Qoralama"
        m_cnt = len(c.missions or [])
        p_cnt = counts.get(c.id, 0)
        lines.append(f"{st_icon} **{escape_md(c.title)}** ({m_cnt} bosqich | {p_cnt} o'yinchi) — _{st_lbl}_")
        buttons.append([
            InlineKeyboardButton(
                f"{st_icon} {c.title} ({m_cnt} bosqich | {p_cnt} o'yinchi)",
                callback_data=f"admin_camp_view:{c.id}",
            )
        ])

    buttons.append([InlineKeyboardButton("➕ Yangi kampaniya yaratish", callback_data="admin_camp_new")])
    buttons.append([InlineKeyboardButton("🔙 Admin menyuga qaytish", callback_data="admin_panel")])
    await _safe_edit_or_reply(target, "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


async def admin_campaigns_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    _clear_admin_campaign_fsm(context.user_data)
    try:
        await _render_admin_campaigns_list(query)
    except Exception as e:
        logger.exception(f"admin_campaigns_callback error: {e}")
        await _safe_edit_or_reply(
            query,
            f"❌ Admin kampaniyalar panelini ochishda xatolik:\n{e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin menyuga qaytish", callback_data="admin_panel")]]),
            parse_mode=None,
        )


async def admin_camp_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    _clear_admin_campaign_fsm(context.user_data)
    await query.answer("❌ Jarayon bekor qilindi.")
    back_cb = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else "admin_campaigns"
    if back_cb.startswith("admin_camp_view:"):
        await _render_admin_campaign_view(query, int(back_cb.split(":")[1]))
    elif back_cb.startswith("admin_camp_missions:"):
        await _render_admin_camp_missions(query, int(back_cb.split(":")[1]))
    else:
        await _render_admin_campaigns_list(query)


async def _render_admin_campaign_view(target, campaign_id: int):
    async with AsyncSessionLocal() as session:
        camp = await get_campaign_with_missions(session, campaign_id)
        if not camp:
            await _safe_edit_or_reply(target, "❌ Kampaniya topilmadi.")
            return
        missions = sorted(camp.missions or [], key=lambda m: m.order_index)
        dur = format_campaign_min_duration(camp, missions)
        rewards_preview = format_completion_rewards_preview(camp)

    st_str = "🟢 Faol (Published)" if camp.status == "published" else "🔴 Qoralama (Draft)"
    text = (
        f"📜 **KAMPANIYA #{camp.id}: {escape_md(camp.title)}**\n"
        f"_{escape_md(camp.description or '')}_\n\n"
        f"• Holat: **{st_str}**\n"
        f"• Bosqichlar soni: `{len(missions)} ta`\n"
        f"• Minimal daraja: `{camp.min_level or 1}-daraja`\n"
        f"• Yakuniy mukofotlar: {rewards_preview}\n"
        f"• Ochilish rejimi: `{camp.unlock_mode}` | Kutish: `{camp.default_cooldown_hours} soat`\n"
        f"• Kunlik urinish: `{camp.default_daily_attempts}` | Tanlov kutishi: `{camp.default_choice_cooldown_minutes} daq`\n"
        f"• ⏱️ **Minimal davomiylik:** {dur}\n"
    )
    pub_btn = (
        InlineKeyboardButton("🔴 To'xtatish (Draft)", callback_data=f"admin_camp_set:{camp.id}:status:draft")
        if camp.status == "published"
        else InlineKeyboardButton("🟢 Faollashtirish (Publish)", callback_data=f"admin_camp_set:{camp.id}:status:published")
    )
    buttons = [
        [pub_btn],
        [
            InlineKeyboardButton("📋 Bosqichlar ro'yxati", callback_data=f"admin_camp_missions:{camp.id}"),
            InlineKeyboardButton("➕ Bosqich qo'shish", callback_data=f"admin_m_add:{camp.id}"),
        ],
        [
            InlineKeyboardButton("✏️ Ma'lumotlarni tahrirlash", callback_data=f"admin_camp_edit:{camp.id}"),
            InlineKeyboardButton("📊 Statistika", callback_data=f"admin_camp_stats:{camp.id}"),
        ],
        [
            InlineKeyboardButton("⚙️ Vaqt va limitlar", callback_data=f"admin_camp_settings:{camp.id}"),
            InlineKeyboardButton("🧪 Sinov rejimi", callback_data=f"admin_camp_test:{camp.id}:1"),
        ],
        [InlineKeyboardButton("🗑 Kampaniyani o'chirish", callback_data=f"admin_camp_del_ask:{camp.id}")],
        [InlineKeyboardButton("🔙 Kampaniyalar ro'yxati", callback_data="admin_campaigns")],
    ]
    await _safe_edit_or_reply(target, text, reply_markup=InlineKeyboardMarkup(buttons))


async def admin_camp_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    _clear_admin_campaign_fsm(context.user_data)
    camp_id = int((query.data or "").split(":")[1])
    await _render_admin_campaign_view(query, camp_id)


async def admin_camp_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    parts = (query.data or "").split(":")
    camp_id = int(parts[1])
    if len(parts) == 2:
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📝 Sarlavhani o'zgartirish", callback_data=f"admin_camp_edit:{camp_id}:title"),
                InlineKeyboardButton("📖 Tavsifni o'zgartirish", callback_data=f"admin_camp_edit:{camp_id}:description"),
            ],
            [
                InlineKeyboardButton("🎖️ Minimal daraja", callback_data=f"admin_camp_edit:{camp_id}:min_level"),
                InlineKeyboardButton("🏆 Yakuniy mukofot (Oltin)", callback_data=f"admin_camp_edit:{camp_id}:reward_gold"),
            ],
            [
                InlineKeyboardButton("👑 Yakuniy Unvon", callback_data=f"admin_camp_edit:{camp_id}:reward_title"),
                InlineKeyboardButton("🗡️ Yakuniy Buyum", callback_data=f"admin_camp_edit:{camp_id}:reward_item"),
            ],
            [InlineKeyboardButton("🔙 Orqaga", callback_data=f"admin_camp_view:{camp_id}")],
        ])
        await _safe_edit_or_reply(query, "✏️ **KAMPANIYA MA'LUMOTLARINI TAHRIRLASH**\n\nNimani o'zgartirmoqchisiz?", reply_markup=kb)
        return

    field = parts[2]
    _clear_admin_campaign_fsm(context.user_data)
    context.user_data["admin_camp_edit"] = {"campaign_id": camp_id, "field": field}
    prompts = {
        "title": "📝 Yangi kampaniya sarlavhasini yuboring:",
        "description": "📖 Yangi kampaniya tavsifini yuboring:",
        "min_level": "🎖️ Minimal darajani butun son ko'rinishida yuboring (masalan: `5`):",
        "reward_gold": "🪙 Yakuniy oltin mukofotini kiriting (masalan: `1500`):",
        "reward_title": "👑 Eksklyuziv unvon nomini kiriting (olib tashlash uchun `0` yozing):",
        "reward_item": "🗡️ Yakuniy buyum nomini kiriting (olib tashlash uchun `0` yozing):",
    }
    await _safe_edit_or_reply(query, prompts.get(field, "Yangi qiymatni yuboring:"), reply_markup=_cancel_kb(f"admin_camp_view:{camp_id}"))


async def admin_camp_del_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    camp_id = int((query.data or "").split(":")[1])
    async with AsyncSessionLocal() as session:
        camp = await get_campaign_with_missions(session, camp_id)
    if not camp:
        await _safe_edit_or_reply(query, "❌ Kampaniya topilmadi.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ Ha, o'chirilsin", callback_data=f"admin_camp_del_do:{camp_id}")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"admin_camp_view:{camp_id}")],
    ])
    await _safe_edit_or_reply(
        query,
        f"⚠️ **DIQQAT! KAMPANIYANI O'CHIRISH**\n\n«**{escape_md(camp.title)}**» kampaniyasi, uning barcha bosqichlari va o'yinchi progressi butunlay o'chiriladi. Tasdiqlaysizmi?",
        reply_markup=kb,
    )


async def admin_camp_del_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    camp_id = int((query.data or "").split(":")[1])
    async with AsyncSessionLocal() as session:
        _, msg = await delete_campaign(session, camp_id)
    await query.answer(msg, show_alert=True)
    await _render_admin_campaigns_list(query)


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
        f"• 👥 **Jami boshlaganlar:** `{st['total_players']} kishi`",
        f"• ⏳ **Jarayonda:** `{st['in_progress_players']} kishi`",
        f"• 🏆 **Yakunlaganlar:** `{st['completed_players']} kishi` (`{st['completion_rate_pct']}%`)",
        f"• ⏱️ **Minimal davomiylik:** {st['min_duration_label']}\n",
        "📌 **Bosqichlar bo'yicha taqsimot:**",
    ]
    for m in st["missions"]:
        in_p = st["in_progress_by_mission"].get(m.order_index, 0)
        w = st["waiting_by_mission"].get(m.order_index, 0)
        lines.append(f"• {m.order_index}-bosqichda ({escape_md(m.title)}): **{in_p} kishi** (⏳ kutmoqda: {w})")

    lines.append("\n🏅 **Oxirgi 5 ta yakunlagan o'yinchi:**")
    recent = st.get("recent_completers") or []
    if not recent:
        lines.append("_Hozircha yakunlagan o'yinchilar yo'q._")
    else:
        for idx, r in enumerate(recent, 1):
            uname = f" (@{escape_md(r['username'])})" if r.get("username") else ""
            ts = format_tashkent_dt(r.get("completed_at"))
            lines.append(f"{idx}. **{escape_md(r['full_name'])}**{uname} — `{ts}`")

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
    await query.answer(msg, show_alert=not ok)
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
    lines = [f"📋 **BOSQICHLAR RO'YXATI: {escape_md(camp.title)}**\n"]
    buttons = []
    if not missions:
        lines.append("_Hozircha bosqichlar yo'q. Faollashtirish uchun kamida 1 ta bosqich qo'shing._")
    for m in missions:
        cd = get_mission_cooldown_hours(camp, m)
        cal = format_tashkent_dt(m.calendar_unlock_at) if m.calendar_unlock_at else "—"
        lines.append(
            f"• **{m.order_index}-bosqich:** {escape_md(m.title)} (`{m.mission_type}`) | ⏳ {cd}h | 📅 {cal}"
        )
        buttons.append([
            InlineKeyboardButton(
                f"✏️ {m.order_index}-bosqich: {m.title} ({m.mission_type})",
                callback_data=f"admin_m_view:{camp_id}:{m.id}",
            ),
            InlineKeyboardButton("🗑️", callback_data=f"admin_m_del:{camp_id}:{m.id}"),
        ])
    buttons.append([InlineKeyboardButton("➕ Bosqich qo'shish", callback_data=f"admin_m_add:{camp_id}")])
    buttons.append([InlineKeyboardButton("🔙 Kampaniyaga qaytish", callback_data=f"admin_camp_view:{camp_id}")])
    await _safe_edit_or_reply(target, "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


async def _render_admin_mission_detail(target, camp_id: int, mission_id: int):
    async with AsyncSessionLocal() as session:
        camp = await get_campaign_with_missions(session, camp_id)
        m = next((x for x in (camp.missions or []) if x.id == mission_id), None) if camp else None
    if not camp or not m:
        await _safe_edit_or_reply(target, "❌ Bosqich topilmadi.")
        return
    cd = get_mission_cooldown_hours(camp, m)
    cal = format_tashkent_dt(m.calendar_unlock_at) if m.calendar_unlock_at else "Belgilanmagan"
    text = (
        f"📜 **{m.order_index}-BOSQICH: {escape_md(m.title)}**\n"
        f"• Turi (`task_type`): `{m.mission_type}`\n"
        f"• Mukofot: `+{m.reward_gold}🪙`, `+{m.reward_xp} XP`\n"
        f"• Kutish vaqti: `{cd} soat` | Kalendar: `{cal}`\n\n"
        f"📖 **Hikoya:**\n{escape_md(m.story_text[:400])}\n\n"
        f"✅ **Yakuniy matn:**\n{escape_md((m.success_text or '—')[:250])}"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Hikoyani tahrirlash", callback_data=f"admin_m_edit:{camp_id}:{m.id}:story_text"),
            InlineKeyboardButton("✅ Yakuniy matn", callback_data=f"admin_m_edit:{camp_id}:{m.id}:success_text"),
        ],
        [
            InlineKeyboardButton("🎁 Mukofot (Oltin/XP)", callback_data=f"admin_m_edit:{camp_id}:{m.id}:step_rewards"),
            InlineKeyboardButton("⚙️ Task data", callback_data=f"admin_m_edit:{camp_id}:{m.id}:task_data"),
        ],
        [
            InlineKeyboardButton("⏳ Kutish: 72h", callback_data=f"admin_m_set:{camp_id}:{m.id}:cd:72"),
            InlineKeyboardButton("♻️ Standart", callback_data=f"admin_m_set:{camp_id}:{m.id}:cd:default"),
            InlineKeyboardButton("📅 Kalendar sana", callback_data=f"admin_m_cal_ask:{camp_id}:{m.id}"),
        ],
        [InlineKeyboardButton("🗑️ Bosqichni o'chirish", callback_data=f"admin_m_del:{camp_id}:{m.id}")],
        [InlineKeyboardButton("🔙 Bosqichlar ro'yxati", callback_data=f"admin_camp_missions:{camp_id}")],
    ])
    await _safe_edit_or_reply(target, text, reply_markup=kb)


async def admin_m_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    parts = (query.data or "").split(":")
    await _render_admin_mission_detail(query, int(parts[1]), int(parts[2]))


async def admin_m_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    parts = (query.data or "").split(":")
    camp_id, mission_id, field = int(parts[1]), int(parts[2]), parts[3]
    _clear_admin_campaign_fsm(context.user_data)
    context.user_data["admin_m_edit"] = {"campaign_id": camp_id, "mission_id": mission_id, "field": field}
    prompts = {
        "story_text": "📖 Bosqich uchun yangi hikoya matnini (`story_text`) yuboring:",
        "success_text": "✅ Bosqich yakunlanganda chiqadigan matnni (`success_text`) yuboring:",
        "step_rewards": "🎁 Bosqich mukofotini `Oltin XP` ko'rinishida yuboring (masalan: `200 120`):",
        "task_data": "⚙️ Yangi `task_data` ni JSON yoki oddiy qiymat ko'rinishida yuboring (masalan: `{\"cost_gold\": 150}` yoki `{\"enemy_name\": \"Qotil\", \"enemy_hp\": 200, \"enemy_attack\": 30, \"enemy_defense\": 10}`):",
    }
    await _safe_edit_or_reply(query, prompts.get(field, "Yangi qiymatni yuboring:"), reply_markup=_cancel_kb(f"admin_camp_missions:{camp_id}"))


async def admin_m_del_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    parts = (query.data or "").split(":")
    camp_id, mission_id = int(parts[1]), int(parts[2])
    async with AsyncSessionLocal() as session:
        _, msg = await delete_campaign_mission(session, mission_id)
    await query.answer(msg, show_alert=True)
    await _render_admin_camp_missions(query, camp_id)


async def admin_m_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    parts = (query.data or "").split(":")
    camp_id = int(parts[1])
    if len(parts) == 2:
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎭 Tanlov (Narrative Choice)", callback_data=f"admin_m_add:{camp_id}:narrative_choice"),
                InlineKeyboardButton("⚔️ Jang (Combat Encounter)", callback_data=f"admin_m_add:{camp_id}:combat_encounter"),
            ],
            [
                InlineKeyboardButton("🧩 Jumboq (Riddle)", callback_data=f"admin_m_add:{camp_id}:riddle_investigation"),
                InlineKeyboardButton("💰 Resurs / Pora (Tribute)", callback_data=f"admin_m_add:{camp_id}:resource_tribute"),
            ],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"admin_camp_cancel:admin_camp_missions:{camp_id}")],
        ])
        await _safe_edit_or_reply(
            query,
            "➕ **YANGI BOSQICH QO'SHISH (1/5)**\n\nBosqich turini (`task_type`) tanlang:",
            reply_markup=kb,
        )
        return

    mtype = parts[2]
    _clear_admin_campaign_fsm(context.user_data)
    context.user_data["admin_camp_add_mission"] = {
        "campaign_id": camp_id,
        "mission_type": mtype,
        "step": "title",
    }
    await _safe_edit_or_reply(
        query,
        f"➕ **YANGI BOSQICH (`{mtype}`) — 2/5**\n\nBosqich sarlavhasini yuboring:",
        reply_markup=_cancel_kb(f"admin_camp_missions:{camp_id}"),
    )


async def camp_clue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = (query.data or "").split(":")
    try:
        camp_id, order = int(parts[1]), int(parts[2])
    except Exception:
        await query.answer("🔍 Dalil topilmadi.", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        camp = await get_campaign_with_missions(session, camp_id)
        m = next((x for x in (camp.missions or []) if x.order_index == order), None) if camp else None
    clue = parse_task_data(m).get("clue_text") if m else None
    await query.answer(str(clue or "Qo'shimcha dalil yo'q.")[:195], show_alert=True)


async def admin_campaigns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not is_admin(update.effective_user.id):
        return
    _clear_admin_campaign_fsm(context.user_data)
    await _render_admin_campaigns_list(update.message)


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
# ADMIN KAMPANIYA YARATISH WIZARDI (FSM)
# ============================================================

async def admin_camp_new_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    _clear_admin_campaign_fsm(context.user_data)
    context.user_data["admin_camp_wizard"] = {"step": "title", "rewards": {}}
    await _safe_edit_or_reply(
        query,
        "🧙‍♂️ **YANGI KAMPANIYA YARATISH (1/7: Sarlavha)**\n\nKampaniya sarlavhasini yozib yuboring:",
        reply_markup=_cancel_kb("admin_campaigns"),
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
            "🧙‍♂️ **YANGI KAMPANIYA (7/7: Kutish vaqti)**\n\nMissiyalar orasidagi standart kutish vaqtini tanlang:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⏳ 12 soat", callback_data="admin_cwiz:cd:12"),
                    InlineKeyboardButton("⏳ 24 soat (Standart)", callback_data="admin_cwiz:cd:24"),
                    InlineKeyboardButton("⏳ 48 soat", callback_data="admin_cwiz:cd:48"),
                ],
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_camp_cancel:admin_campaigns")],
            ]),
        )
    elif key == "cd":
        wiz["default_cooldown_hours"] = int(val)
        wiz["step"] = "confirm"
        cd_h = wiz["default_cooldown_hours"]
        sample_10_days = (10 * cd_h) // 24
        rew = wiz.get("rewards") or {}
        await _safe_edit_or_reply(
            query,
            f"🧙‍♂️ **YANGI KAMPANIYA: TASDIQLASH**\n\n"
            f"• Sarlavha: **{escape_md(wiz['title'])}**\n"
            f"• Tavsif: _{escape_md(wiz.get('description', ''))}_\n"
            f"• Minimal daraja: `{wiz.get('min_level', 1)}-daraja`\n"
            f"• Yakuniy mukofot: `{rew.get('gold', 0):,}🪙` | Buyum: `{rew.get('item') or '—'}` | Unvon: `{rew.get('title') or '—'}` | Yutuq: `{rew.get('achievement_name') or '—'}`\n"
            f"• Rejim: `{wiz.get('unlock_mode', 'cooldown')}` | Kutish: `{cd_h} soat`\n"
            f"• ⏱️ **Minimal davomiylik namunasi:** 10 bosqich × {cd_h} soat = **kamida {sample_10_days} kun**\n\n"
            f"Kampaniya **🔴 Qoralama (Draft)** holatida yaratiladi. Tasdiqlaysizmi?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yaratish (Qoralama)", callback_data="admin_cwiz:save:1")],
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_camp_cancel:admin_campaigns")],
            ]),
        )
    elif key == "save":
        async with AsyncSessionLocal() as session:
            camp = await create_campaign(
                session=session,
                title=wiz["title"],
                description=wiz.get("description", ""),
                min_level=wiz.get("min_level", 1),
                completion_rewards=wiz.get("rewards") or {},
                unlock_mode=wiz.get("unlock_mode", "cooldown"),
                default_cooldown_hours=wiz.get("default_cooldown_hours", 24),
                default_daily_attempts=3,
                default_choice_cooldown_minutes=30,
                status="draft",
                created_by=query.from_user.id,
            )
        _clear_admin_campaign_fsm(context.user_data)
        await _render_admin_campaign_view(query, camp.id)


# ============================================================
# MATNLI KIRISHLAR (RIDDLE, ADMIN WIZARD, EDIT, STAGE BUILDER)
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

    if not is_admin(user_id):
        return

    # Universal /cancel for admin FSMs
    if text.lower() in ("/cancel", "bekor") and any(u_data.get(k) for k in ADMIN_FSM_KEYS):
        _clear_admin_campaign_fsm(u_data)
        await update.message.reply_text(
            "❌ Jarayon bekor qilindi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📜 Kampaniyalar boshqaruvi", callback_data="admin_campaigns")]]),
        )
        return

    # 2. Admin kalendar sanasi kiritish
    cal_ctx = u_data.get("admin_camp_cal_input")
    if cal_ctx:
        if text.lower() == "none":
            dt_utc = None
        else:
            dt_utc = parse_tashkent_dt(text)
            if dt_utc is None:
                await update.message.reply_text("❌ Sana formati noto'g'ri! Masalan: `2026-12-01 10:00`", parse_mode="Markdown")
                return
        async with AsyncSessionLocal() as session:
            _, msg, _ = await update_mission_settings(session, cal_ctx["mission_id"], calendar_unlock_at=dt_utc)
        _clear_admin_campaign_fsm(u_data)
        await update.message.reply_text(
            f"{msg}\n📅 Yangi sana: {format_tashkent_dt(dt_utc)}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Bosqichlar ro'yxati", callback_data=f"admin_camp_missions:{cal_ctx['campaign_id']}")]]),
        )
        return

    # 2a. Admin kampaniya ma'lumotlarini tahrirlash
    edit_c = u_data.get("admin_camp_edit")
    if edit_c:
        camp_id, field = edit_c["campaign_id"], edit_c["field"]
        async with AsyncSessionLocal() as session:
            camp = await get_campaign_with_missions(session, camp_id)
            if not camp:
                _clear_admin_campaign_fsm(u_data)
                await update.message.reply_text("❌ Kampaniya topilmadi.")
                return
            if field == "title":
                await update_campaign_info(session, camp_id, title=text)
            elif field == "description":
                await update_campaign_info(session, camp_id, description=text)
            elif field == "min_level":
                try:
                    lvl = int(text)
                    if lvl < 1:
                        raise ValueError
                except ValueError:
                    await update.message.reply_text("❌ Noto'g'ri son! Minimal daraja 1 dan katta butun son bo'lishi kerak (masalan: `5`).", parse_mode="Markdown")
                    return
                await update_campaign_info(session, camp_id, min_level=lvl)
            elif field in ("reward_gold", "reward_title", "reward_item"):
                rew = parse_completion_rewards(camp)
                if field == "reward_gold":
                    try:
                        g = int(text)
                        if g < 0:
                            raise ValueError
                    except ValueError:
                        await update.message.reply_text("❌ Noto'g'ri son! Oltin miqdorini butun son ko'rinishida kiriting (masalan: `1500`).", parse_mode="Markdown")
                        return
                    rew["gold"] = g
                elif field == "reward_title":
                    if _is_skip_val(text):
                        rew.pop("title", None)
                    else:
                        rew["title"] = text[:100]
                elif field == "reward_item":
                    if _is_skip_val(text):
                        rew.pop("item", None)
                    else:
                        rew["item"] = text[:120]
                await update_campaign_info(session, camp_id, completion_rewards=rew)
        _clear_admin_campaign_fsm(u_data)
        await _render_admin_campaign_view(update.message, camp_id)
        return

    # 2b. Admin bosqichni tahrirlash
    edit_m = u_data.get("admin_m_edit")
    if edit_m:
        camp_id, mission_id, field = edit_m["campaign_id"], edit_m["mission_id"], edit_m["field"]
        async with AsyncSessionLocal() as session:
            if field == "story_text":
                await update_mission_details(session, mission_id, story_text=text)
            elif field == "success_text":
                await update_mission_details(session, mission_id, success_text=text)
            elif field == "step_rewards":
                parts = text.split()
                try:
                    g = int(parts[0])
                    xp = int(parts[1]) if len(parts) > 1 else 0
                    if g < 0 or xp < 0:
                        raise ValueError
                except (ValueError, IndexError):
                    await update.message.reply_text("❌ Noto'g'ri format! Masalan: `200 120` (Oltin XP).", parse_mode="Markdown")
                    return
                await update_mission_details(session, mission_id, reward_gold=g, reward_xp=xp)
            elif field == "task_data":
                import json as _json
                try:
                    parsed = _json.loads(text)
                    if not isinstance(parsed, dict):
                        raise ValueError
                except Exception:
                    await update.message.reply_text("❌ Noto'g'ri JSON! Masalan: `{\"cost_gold\": 150}`", parse_mode="Markdown")
                    return
                await update_mission_details(session, mission_id, task_data=parsed)
        _clear_admin_campaign_fsm(u_data)
        await _render_admin_mission_detail(update.message, camp_id, mission_id)
        return

    # 2c. Admin ko'p bosqichli Stage Builder (➕ Bosqich qo'shish)
    add_m = u_data.get("admin_camp_add_mission")
    if add_m:
        camp_id = add_m["campaign_id"]
        mtype = add_m["mission_type"]
        step = add_m.get("step", "title")
        cancel_kb = _cancel_kb(f"admin_camp_missions:{camp_id}")

        if step == "title":
            add_m["title"] = text[:180]
            add_m["step"] = "story_text"
            await update.message.reply_text(
                "➕ **YANGI BOSQICH (3/5: Hikoya matni)**\n\nO'yinchiga ko'rinadigan hikoya (`story_text`) matnini yuboring:",
                parse_mode="Markdown",
                reply_markup=cancel_kb,
            )
            return
        if step == "story_text":
            add_m["story_text"] = text
            add_m["step"] = "task_data"
            prompts = {
                "narrative_choice": "🎭 **Tanlov variantlarini kiriting:**\n`To'g'ri variant | Noto'g'ri variant 1 | Noto'g'ri variant 2`",
                "combat_encounter": "⚔️ **Raqib ma'lumotlarini kiriting:**\n`Raqib nomi | HP | Hujum | Himoya` (masalan: `Yollanma Qotil | 180 | 28 | 10`)",
                "riddle_investigation": "🧩 **Jumboq javob va variantlarini kiriting:**\n`To'g'ri javob | Noto'g'ri 1 | Noto'g'ri 2`",
                "resource_tribute": "💰 **Kerakli oltin miqdorini kiriting** (butun son, masalan: `150`):",
            }
            await update.message.reply_text(
                f"➕ **YANGI BOSQICH (4/5: Vazifa sozlamasi)**\n\n{prompts.get(mtype, 'Vazifa qiymatini yuboring:')}",
                parse_mode="Markdown",
                reply_markup=cancel_kb,
            )
            return
        if step == "task_data":
            if mtype == "combat_encounter":
                parts = [p.strip() for p in text.split("|")]
                if len(parts) < 3:
                    await update.message.reply_text("❌ Format xato! Masalan: `Yollanma Qotil | 180 | 28 | 10`", parse_mode="Markdown")
                    return
                try:
                    hp = int(parts[1])
                    atk = int(parts[2])
                    dfn = int(parts[3]) if len(parts) >= 4 else 10
                    if hp <= 0 or atk <= 0 or dfn < 0:
                        raise ValueError
                except ValueError:
                    await update.message.reply_text("❌ HP, Hujum va Himoya musbat butun son bo'lishi kerak!", parse_mode="Markdown")
                    return
                add_m["task_data"] = {
                    "enemy_name": parts[0],
                    "enemy_hp": hp,
                    "enemy_attack": atk,
                    "enemy_defense": dfn,
                    "enemy_power": hp + atk * 5,
                }
            elif mtype == "resource_tribute":
                try:
                    cost_g = int(text)
                    if cost_g <= 0:
                        raise ValueError
                except ValueError:
                    await update.message.reply_text("❌ Oltin miqdori musbat butun son bo'lishi kerak (masalan: `150`).", parse_mode="Markdown")
                    return
                add_m["task_data"] = {"cost_gold": cost_g}
            elif mtype in ("narrative_choice", "riddle_investigation"):
                parts = [p.strip() for p in text.split("|") if p.strip()]
                if len(parts) < 2:
                    await update.message.reply_text("❌ Kamida 2 ta variantni `|` bilan ajratib yozing: `To'g'ri | Noto'g'ri 1 | Noto'g'ri 2`", parse_mode="Markdown")
                    return
                opts = [{"key": "opt_0", "text": parts[0], "is_correct": True}]
                for idx, wrong in enumerate(parts[1:], 1):
                    opts.append({"key": f"opt_{idx}", "text": wrong, "is_correct": False})
                add_m["options"] = opts
                add_m["correct_answer"] = "opt_0"
            add_m["step"] = "success_text"
            await update.message.reply_text(
                "➕ **YANGI BOSQICH (4.5/5: Yakuniy matn)**\n\nBosqich muvaffaqiyatli o'tilganda chiqadigan matnni (`success_text`) yuboring:",
                parse_mode="Markdown",
                reply_markup=cancel_kb,
            )
            return
        if step == "success_text":
            add_m["success_text"] = text
            add_m["step"] = "step_rewards"
            await update.message.reply_text(
                "➕ **YANGI BOSQICH (5/5: Bosqich mukofoti)**\n\nOltin va XP miqdorini bo'shliq bilan kiriting (masalan: `150 100` yoki `0 50`):",
                parse_mode="Markdown",
                reply_markup=cancel_kb,
            )
            return
        if step == "step_rewards":
            parts = text.split()
            try:
                r_gold = int(parts[0])
                r_xp = int(parts[1]) if len(parts) > 1 else 0
                if r_gold < 0 or r_xp < 0:
                    raise ValueError
            except (ValueError, IndexError):
                await update.message.reply_text("❌ Noto'g'ri son! Oltin va XP ni butun son ko'rinishida yuboring (masalan: `150 100`).", parse_mode="Markdown")
                return
            async with AsyncSessionLocal() as session:
                camp = await get_campaign_with_missions(session, camp_id)
                next_idx = max((m.order_index for m in (camp.missions or [])), default=0) + 1 if camp else 1
                await add_campaign_mission(
                    session=session,
                    campaign_id=camp_id,
                    order_index=next_idx,
                    title=add_m["title"],
                    story_text=add_m["story_text"],
                    mission_type=mtype,
                    options=add_m.get("options"),
                    correct_answer=add_m.get("correct_answer"),
                    task_data=add_m.get("task_data"),
                    success_text=add_m.get("success_text", ""),
                    reward_gold=r_gold,
                    reward_xp=r_xp,
                )
            _clear_admin_campaign_fsm(u_data)
            await update.message.reply_text(
                f"✅ **{next_idx}-bosqich qo'shildi:** {escape_md(add_m['title'])} (`{mtype}` | +{r_gold}🪙, +{r_xp} XP)",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Bosqichlar ro'yxati", callback_data=f"admin_camp_missions:{camp_id}")]]),
            )
            return

    # 3. Admin kampaniya yaratish wizardi (FSM)
    wiz = u_data.get("admin_camp_wizard")
    if wiz:
        step = wiz.get("step")
        cancel_kb = _cancel_kb("admin_campaigns")
        if step == "title":
            wiz["title"] = text[:180]
            wiz["step"] = "description"
            await update.message.reply_text(
                "🧙‍♂️ **YANGI KAMPANIYA (2/7: Tavsif)**\n\nO'yinchilarga ko'rinadigan kampaniya tavsifini yuboring:",
                parse_mode="Markdown",
                reply_markup=cancel_kb,
            )
            return
        if step == "description":
            wiz["description"] = text[:700]
            wiz["step"] = "min_level"
            await update.message.reply_text(
                "🧙‍♂️ **YANGI KAMPANIYA (3/7: Minimal daraja)**\n\nMinimal o'yinchi darajasini kiriting (masalan: `1`, `5`, `10`):",
                parse_mode="Markdown",
                reply_markup=cancel_kb,
            )
            return
        if step == "min_level":
            try:
                lvl = int(text)
                if lvl < 1:
                    raise ValueError
            except ValueError:
                await update.message.reply_text("❌ Noto'g'ri son! Minimal daraja 1 yoki undan katta butun son bo'lishi kerak.", parse_mode="Markdown", reply_markup=cancel_kb)
                return
            wiz["min_level"] = lvl
            wiz["step"] = "reward_gold"
            await update.message.reply_text(
                "🧙‍♂️ **YANGI KAMPANIYA (4/7: Yakuniy oltin mukofoti)**\n\nKampaniya yakunida beriladigan oltin miqdorini kiriting (masalan: `1500`):",
                parse_mode="Markdown",
                reply_markup=cancel_kb,
            )
            return
        if step == "reward_gold":
            try:
                g = int(text)
                if g < 0:
                    raise ValueError
            except ValueError:
                await update.message.reply_text("❌ Noto'g'ri son! Oltin miqdorini butun son ko'rinishida kiriting (masalan: `1500`).", parse_mode="Markdown", reply_markup=cancel_kb)
                return
            wiz.setdefault("rewards", {})["gold"] = g
            wiz["step"] = "reward_item"
            await update.message.reply_text(
                "🧙‍♂️ **YANGI KAMPANIYA (5/7: Yakuniy buyum)**\n\nMukofot buyumi nomini kiriting (o'tkazib yuborish uchun `0` yoki `Yo'q` yozing):",
                parse_mode="Markdown",
                reply_markup=cancel_kb,
            )
            return
        if step == "reward_item":
            if not _is_skip_val(text):
                wiz.setdefault("rewards", {})["item"] = text[:120]
            wiz["step"] = "reward_title"
            await update.message.reply_text(
                "🧙‍♂️ **YANGI KAMPANIYA (6/7: Eksklyuziv Unvon)**\n\nUnvon (Title) nomini kiriting (o'tkazib yuborish uchun `0` yoki `Yo'q` yozing):",
                parse_mode="Markdown",
                reply_markup=cancel_kb,
            )
            return
        if step == "reward_title":
            if not _is_skip_val(text):
                wiz.setdefault("rewards", {})["title"] = text[:100]
            wiz["step"] = "reward_ach"
            await update.message.reply_text(
                "🧙‍♂️ **YANGI KAMPANIYA (6.5/7: Yutuq / Achievement)**\n\nYutuq nomini kiriting (o'tkazib yuborish uchun `0` yoki `Yo'q` yozing):",
                parse_mode="Markdown",
                reply_markup=cancel_kb,
            )
            return
        if step == "reward_ach":
            if not _is_skip_val(text):
                import re as _re
                slug_code = "camp_" + _re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:36]
                wiz.setdefault("rewards", {})["achievement_name"] = text[:100]
                wiz.setdefault("rewards", {})["achievement_code"] = slug_code
            wiz["step"] = "mode"
            await update.message.reply_text(
                "🧙‍♂️ **YANGI KAMPANIYA: OCHILISH REJIMI**\n\n"
                "• **Kutish rejimi (Cooldown):** har bosqichdan keyin belgilangan soat kutish\n"
                "• **Kalendar rejimi (Calendar):** har bosqich aniq sana va vaqtda ochiladi",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏳ Kutish rejimi (Cooldown)", callback_data="admin_cwiz:mode:cooldown")],
                    [InlineKeyboardButton("📅 Kalendar rejimi (Calendar)", callback_data="admin_cwiz:mode:calendar")],
                    [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_camp_cancel:admin_campaigns")],
                ]),
            )
            return


def register_campaign_handlers(app: Application):
    app.add_handler(CommandHandler(["campaign", "campaigns"], campaigns_command))
    app.add_handler(CommandHandler(["admin_campaigns"], admin_campaigns_command))
    app.add_handler(CallbackQueryHandler(menu_campaigns_callback, pattern="^menu_campaigns$"))
    app.add_handler(CallbackQueryHandler(camp_view_callback, pattern="^camp_view:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(camp_locked_info_callback, pattern="^camp_locked_info:[0-9]+:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(camp_notify_toggle_callback, pattern="^camp_notify_toggle:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(camp_act_callback, pattern="^camp_act:[0-9]+:[0-9]+:.+$"))
    app.add_handler(CallbackQueryHandler(camp_riddle_ask_callback, pattern="^camp_riddle_ask:[0-9]+:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(camp_clue_callback, pattern="^camp_clue:[0-9]+:[0-9]+$"))

    # Admin handlers
    app.add_handler(CallbackQueryHandler(admin_campaigns_callback, pattern="^admin_campaigns$"))
    app.add_handler(CallbackQueryHandler(admin_camp_cancel_callback, pattern="^admin_camp_cancel(:.*)?$"))
    app.add_handler(CallbackQueryHandler(admin_camp_view_callback, pattern="^admin_camp_view:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_camp_edit_callback, pattern="^admin_camp_edit:[0-9]+(:[a-z_]+)?$"))
    app.add_handler(CallbackQueryHandler(admin_camp_del_ask_callback, pattern="^admin_camp_del_ask:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_camp_del_do_callback, pattern="^admin_camp_del_do:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_camp_stats_callback, pattern="^admin_camp_stats:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_camp_settings_callback, pattern="^admin_camp_settings:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_camp_set_callback, pattern="^admin_camp_set:[0-9]+:[a-z]+:.+$"))
    app.add_handler(CallbackQueryHandler(admin_camp_missions_callback, pattern="^admin_camp_missions:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_m_view_callback, pattern="^admin_m_view:[0-9]+:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_m_edit_callback, pattern="^admin_m_edit:[0-9]+:[0-9]+:[a-z_]+$"))
    app.add_handler(CallbackQueryHandler(admin_m_set_callback, pattern="^admin_m_set:[0-9]+:[0-9]+:[a-z]+:.+$"))
    app.add_handler(CallbackQueryHandler(admin_m_del_callback, pattern="^admin_m_del:[0-9]+:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_m_add_callback, pattern="^admin_m_add:[0-9]+(:[a-z_]+)?$"))
    app.add_handler(CallbackQueryHandler(admin_m_cal_ask_callback, pattern="^admin_m_cal_ask:[0-9]+:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_camp_test_callback, pattern="^admin_camp_test:[0-9]+:[0-9]+(:.*)?$"))
    app.add_handler(CallbackQueryHandler(admin_camp_new_callback, pattern="^admin_camp_new$"))
    app.add_handler(CallbackQueryHandler(admin_camp_wiz_choice_callback, pattern="^admin_cwiz:[a-z]+:.+$"))

    # Matnli kirishlar (group=4 — boshqa handlerlarga xalaqit bermaydi)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, campaign_text_input_handler),
        group=4,
    )
