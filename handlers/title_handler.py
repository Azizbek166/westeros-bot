"""
Player Titles (Unvonlarim) Panel & Admin Title Management Handlers.
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

from config import escape_md, is_admin
from database import crud
from database.db import AsyncSessionLocal
from services.campaign_service import format_tashkent_dt
from services.title_service import (
    equip_user_title,
    find_user_by_identifier,
    format_rarity_badge,
    format_stat_bonus,
    get_or_create_title,
    get_user_titles_overview,
    grant_title_to_user,
    list_all_titles,
)

logger = logging.getLogger(__name__)

TITLES_PER_PAGE = 6


async def _safe_send_or_edit(target, text: str, reply_markup=None, parse_mode="Markdown"):
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
# O'YINCHI "🏅 UNVONLARIM" PANELI
# ============================================================

async def _render_titles_panel(target, telegram_id: int, mode: str = "unlocked", page: int = 0):
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, telegram_id)
        if not user:
            await _safe_send_or_edit(target, "❌ Avval /start bosib ro'yxatdan o'ting.")
            return
        ov = await get_user_titles_overview(session, user)

    active_t = ov["active_title"]
    active_str = f"{active_t.icon} **{escape_md(active_t.name)}**" if active_t else "_Tanlanmagan_"

    items = ov["unlocked"] if mode == "unlocked" else ov["locked"]
    total_pages = max(1, (len(items) + TITLES_PER_PAGE - 1) // TITLES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    page_items = items[page * TITLES_PER_PAGE : (page + 1) * TITLES_PER_PAGE]

    header = "🏅 **UNVONLARIM PANELI**" if mode == "unlocked" else "🔒 **QULFLANGAN UNVONLAR (MAQSADLAR)**"
    lines = [
        header,
        f"• **Joriy faol unvon:** {active_str}",
        f"• **Ochilgan unvonlar:** `{ov['unlocked_count']} / {ov['total_count']}`\n",
    ]

    buttons = []
    if not page_items:
        if mode == "unlocked":
            lines.append("_Sizda hali ochilgan unvonlar yo'q. Kampaniyalarni yakunlab eksklyuziv unvonlarga ega bo'ling!_")
        else:
            lines.append("🎉 _Barcha mavjud unvonlar allaqachon ochilgan!_")
    else:
        for entry in page_items:
            t = entry["title"]
            if mode == "unlocked":
                is_eq = entry.get("is_active", False)
                prefix = "✅" if is_eq else "🏅"
                suffix = " (Taqilgan)" if is_eq else ""
                lines.append(f"{prefix} {t.icon} **{escape_md(t.name)}**{suffix} — _{format_rarity_badge(t.rarity)}_")
                buttons.append([
                    InlineKeyboardButton(
                        f"{prefix} {t.icon} {t.name}{suffix}",
                        callback_data=f"title_view:{t.id}:unlocked:{page}",
                    )
                ])
            else:
                hint = escape_md(t.description or "Maxsus yutuq yoki kampaniya orqali ochiladi")
                lines.append(f"🔒 {t.icon} **{escape_md(t.name)}** ({format_rarity_badge(t.rarity)})\n   _{hint}_")
                buttons.append([
                    InlineKeyboardButton(
                        f"🔒 {t.icon} {t.name}",
                        callback_data=f"title_view:{t.id}:locked:{page}",
                    )
                ])

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"titles_list:{mode}:{page - 1}"))
        nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"titles_list:{mode}:{page + 1}"))
        buttons.append(nav)

    if mode == "unlocked":
        buttons.append([InlineKeyboardButton("🔒 Qulflangan unvonlarni ko‘rish", callback_data="titles_list:locked:0")])
    else:
        buttons.append([InlineKeyboardButton("🏅 Ochilgan unvonlarim", callback_data="titles_list:unlocked:0")])

    if active_t:
        buttons.append([InlineKeyboardButton("❌ Faol unvonni yechish", callback_data=f"title_unequip:{page}")])

    buttons.append([InlineKeyboardButton("🔙 Profilga qaytish", callback_data="menu_profile")])
    await _safe_send_or_edit(target, "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


async def titles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await _render_titles_panel(update.message, update.effective_user.id, mode="unlocked", page=0)


async def menu_titles_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _render_titles_panel(query, query.from_user.id, mode="unlocked", page=0)


async def titles_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = (query.data or "").split(":")
    mode = parts[1] if len(parts) > 1 else "unlocked"
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    await _render_titles_panel(query, query.from_user.id, mode=mode, page=page)


async def title_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = (query.data or "").split(":")
    try:
        title_id = int(parts[1])
    except Exception:
        return
    mode = parts[2] if len(parts) > 2 else "unlocked"
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, query.from_user.id)
        if not user:
            return
        ov = await get_user_titles_overview(session, user)

    unlocked_entry = next((x for x in ov["unlocked"] if x["title"].id == title_id), None)
    locked_entry = next((x for x in ov["locked"] if x["title"].id == title_id), None)
    entry = unlocked_entry or locked_entry
    if not entry:
        await query.answer("❌ Unvon topilmadi.", show_alert=True)
        return

    t = entry["title"]
    is_unlocked = unlocked_entry is not None
    is_equipped = bool(unlocked_entry and unlocked_entry.get("is_active"))

    status_line = (
        "✅ **Holat:** Profilga taqilgan"
        if is_equipped
        else ("🏅 **Holat:** Ochilgan" if is_unlocked else "🔒 **Holat:** Qulflangan")
    )
    date_line = (
        f"📅 **Ochilgan sana:** `{format_tashkent_dt(unlocked_entry['unlocked_at'])}`\n"
        if is_unlocked and unlocked_entry.get("unlocked_at")
        else ""
    )

    text = (
        f"{t.icon} **{escape_md(t.name)}**\n"
        f"━━━━━━━━━━━━━━\n"
        f"{status_line}\n"
        f"💎 **Kamyoplik:** {format_rarity_badge(t.rarity)}\n"
        f"⚡ **Bonus:** {format_stat_bonus(t.stat_bonus_json)}\n"
        f"{date_line}"
        f"📜 **Tavsif:** _{escape_md(t.description or 'Maxsus faxriy unvon.')}_"
    )

    buttons = []
    if is_unlocked:
        if is_equipped:
            buttons.append([InlineKeyboardButton("❌ Unvonni yechish", callback_data=f"title_unequip:{page}")])
        else:
            buttons.append([InlineKeyboardButton("✨ Profilga taqish", callback_data=f"title_equip:{t.id}:{page}")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"titles_list:{mode}:{page}")])
    await _safe_send_or_edit(query, text, reply_markup=InlineKeyboardMarkup(buttons))


async def title_equip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = (query.data or "").split(":")
    title_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, query.from_user.id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await equip_user_title(session, user.id, title_id)
    await query.answer(msg.replace("*", ""), show_alert=True)
    await _render_titles_panel(query, query.from_user.id, mode="unlocked", page=page)


async def title_unequip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = (query.data or "").split(":")
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, query.from_user.id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        _, msg = await equip_user_title(session, user.id, None)
    await query.answer(msg.replace("*", ""), show_alert=True)
    await _render_titles_panel(query, query.from_user.id, mode="unlocked", page=page)


# ============================================================
# ADMIN UNVONLAR BOSHQARUVI (YARATISH & O'YINCHIGA BERISH)
# ============================================================

async def _render_admin_titles(target):
    async with AsyncSessionLocal() as session:
        titles = await list_all_titles(session)
    lines = ["🏅 **ADMIN: UNVONLAR KATALOGI**\n"]
    buttons = []
    for t in titles:
        lines.append(f"• `#{t.id}` {t.icon} **{escape_md(t.name)}** ({format_rarity_badge(t.rarity)})")
        buttons.append([
            InlineKeyboardButton(f"🎁 Berish: {t.icon} {t.name}", callback_data=f"admin_title_grant:{t.id}")
        ])
    buttons.append([InlineKeyboardButton("➕ Yangi unvon yaratish", callback_data="admin_title_new")])
    buttons.append([InlineKeyboardButton("🔙 Kampaniyalar boshqaruvi", callback_data="admin_campaigns")])
    await _safe_send_or_edit(target, "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


async def admin_titles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not is_admin(update.effective_user.id):
        return
    context.user_data.pop("admin_title_fsm", None)
    await _render_admin_titles(update.message)


async def admin_titles_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    context.user_data.pop("admin_title_fsm", None)
    await _render_admin_titles(query)


async def admin_title_new_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    context.user_data["admin_title_fsm"] = {"action": "create"}
    await _safe_send_or_edit(
        query,
        "➕ **YANGI UNVON YARATISH**\n\n"
        "Quyidagi formatda bitta xabar yuboring:\n"
        "`Nomi | Emoji | Kamyoplik (ODDIY/NOYOB/AFSONAVIY) | Tavsif`\n\n"
        "Masalan: `Qonli Qilich | ⚔️ | AFSONAVIY | Turnir g'olibiga maxsus unvon`\n"
        "Bekor qilish: `/cancel`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_titles")]]),
    )


async def admin_title_grant_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    title_id = int((query.data or "").split(":")[1])
    context.user_data["admin_title_fsm"] = {"action": "grant", "title_id": title_id}
    await _safe_send_or_edit(
        query,
        "🎁 **O'YINCHIGA UNVON BERISH**\n\n"
        "O'yinchining `telegram_id` raqamini yoki `@username` ini yuboring (bekor qilish: `/cancel`):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_titles")]]),
    )


async def admin_title_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    fsm = context.user_data.get("admin_title_fsm")
    if not fsm or not is_admin(update.effective_user.id):
        return
    text = update.message.text.strip()
    if text.lower() in ("/cancel", "bekor"):
        context.user_data.pop("admin_title_fsm", None)
        await update.message.reply_text("❌ Bekor qilindi.")
        return

    if fsm.get("action") == "create":
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 2:
            await update.message.reply_text("❌ Format xato! Kamida `Nomi | Emoji` ko'rinishida yuboring.", parse_mode="Markdown")
            return
        name = parts[0]
        icon = parts[1] if len(parts) >= 2 else "🏅"
        rarity = parts[2].upper() if len(parts) >= 3 else "NOYOB"
        desc = parts[3] if len(parts) >= 4 else "Maxsus tadbir mukofoti"
        async with AsyncSessionLocal() as session:
            t = await get_or_create_title(session, name, icon=icon, rarity=rarity, description=desc)
        context.user_data.pop("admin_title_fsm", None)
        await update.message.reply_text(
            f"✅ Yangi unvon yaratildi: {t.icon} **{escape_md(t.name)}** ({format_rarity_badge(t.rarity)})",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏅 Unvonlar katalogi", callback_data="admin_titles")]]),
        )
        return

    if fsm.get("action") == "grant":
        title_id = fsm["title_id"]
        async with AsyncSessionLocal() as session:
            target_u = await find_user_by_identifier(session, text)
            if not target_u:
                await update.message.reply_text("❌ Bunday foydalanuvchi topilmadi. Qayta urining yoki `/cancel` yozing.", parse_mode="Markdown")
                return
            ok, newly, t_obj = await grant_title_to_user(session, target_u.id, title_id=title_id)
        context.user_data.pop("admin_title_fsm", None)
        if ok and t_obj:
            try:
                await context.bot.send_message(
                    chat_id=target_u.telegram_id,
                    text=(
                        f"🏅 Yangi unvon ochildi: {t_obj.icon} **«{escape_md(t_obj.name)}»**!\n"
                        f"Uni «Unvonlarim» panelidan (/titles) profilga taqishingiz mumkin."
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            note = "yangi ochildi" if newly else "allaqachon mavjud edi"
            await update.message.reply_text(
                f"✅ **{escape_md(target_u.full_name)}** ga {t_obj.icon} **«{escape_md(t_obj.name)}»** unvoni berildi ({note}).",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏅 Unvonlar katalogi", callback_data="admin_titles")]]),
            )
        else:
            await update.message.reply_text("❌ Unvon berishda xatolik yuz berdi.")


def register_title_handlers(app: Application):
    app.add_handler(CommandHandler(["titles", "unvonlar"], titles_command))
    app.add_handler(CommandHandler(["admin_titles"], admin_titles_command))
    app.add_handler(CallbackQueryHandler(menu_titles_callback, pattern="^menu_titles$"))
    app.add_handler(CallbackQueryHandler(titles_list_callback, pattern="^titles_list:(unlocked|locked):[0-9]+$"))
    app.add_handler(CallbackQueryHandler(title_view_callback, pattern="^title_view:[0-9]+:(unlocked|locked):[0-9]+$"))
    app.add_handler(CallbackQueryHandler(title_equip_callback, pattern="^title_equip:[0-9]+:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(title_unequip_callback, pattern="^title_unequip:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(admin_titles_callback, pattern="^admin_titles$"))
    app.add_handler(CallbackQueryHandler(admin_title_new_callback, pattern="^admin_title_new$"))
    app.add_handler(CallbackQueryHandler(admin_title_grant_callback, pattern="^admin_title_grant:[0-9]+$"))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, admin_title_text_handler),
        group=5,
    )
