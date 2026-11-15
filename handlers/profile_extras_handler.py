"""
Profil Studiyasi Bezaklari Telegram Handler (prefiks: pfx_).
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, ContextTypes, filters

from config import DONATE_TIERS, OWNER_ID, is_admin, escape_md
from database import AsyncSessionLocal, crud
from services.profile_extras_service import (
    PROFILE_THEMES,
    CREST_EMOJIS,
    get_active_vip_tier,
    get_profile_extras_view,
    has_min_vip_tier,
    set_profile_theme,
    set_profile_crest,
    set_castle_name,
    set_victory_message,
    admin_get_user_profile_extras,
    admin_clear_user_profile_text,
)
from services.section_media_service import (
    SECTION_MEDIA_CONFIG,
    get_all_user_section_media,
    set_user_section_media,
    clear_user_section_media,
)

logger = logging.getLogger(__name__)


async def _render_extras_studio(tg_id: int):
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_id)
        if not user or get_active_vip_tier(user) == "free":
            return (
                "❌ Ushbu bo'lim faqat faol VIP Homiy egalari uchundir!",
                InlineKeyboardMarkup([[InlineKeyboardButton("💎 VIP Paketlar", callback_data="menu_donate")]]),
            )
        view = await get_profile_extras_view(session, user)

    theme_name = view["theme"]["name"] if view.get("theme") else "Oddiy"
    crest_str = view.get("crest") or "O'rnatilmagan"
    castle_str = escape_md(view["castle_name"]) if view.get("castle_name") else "O'rnatilmagan"
    vic_str = escape_md(view["victory_message"]) if view.get("victory_message") else "O'rnatilmagan"
    badges_str = ", ".join(view.get("badges", [])) or "Yo'q"

    text = (
        "🎨 *PROFIL STUDIYASI — BEZAKLAR*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• 🎨 Profil temasi: *{theme_name}*\n"
        f"• 🛡️ Gerb emoji: *{crest_str}*\n"
        f"• 🏰 Qal'a nomi: *{castle_str}*\n"
        f"• ⚔️ G'alaba xabari: *{vic_str}*\n"
        f"• 🏅 Doimiy nishonlar: *{badges_str}*\n\n"
        "Quyidan kerakli bezakni tanlang:"
    )

    buttons = [
        [InlineKeyboardButton("🎨 Profil Temasini Tanlash", callback_data="pfx_themes")],
        [InlineKeyboardButton("🖼️ Bo'limlar Mediasi (Ajdar, Qal'a...)", callback_data="pfx_sec_menu")],
    ]
    if has_min_vip_tier(user, "lord"):
        buttons.append([InlineKeyboardButton("🛡️ Gerb Emoji Tanlash", callback_data="pfx_crests")])
    if has_min_vip_tier(user, "dragonlord"):
        buttons.append([InlineKeyboardButton("⚔️ G'alaba Xabarini Yozish", callback_data="pfx_victory_ask")])
    if has_min_vip_tier(user, "sovereign"):
        buttons.append([InlineKeyboardButton("🏰 Qal'a Nomini Yozish", callback_data="pfx_castle_ask")])
    buttons.append([InlineKeyboardButton("🔙 VIP Studiyaga Qaytish", callback_data="vip_studio")])
    return text, InlineKeyboardMarkup(buttons)


async def pfx_studio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text, kb = await _render_extras_studio(query.from_user.id)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=kb)


async def pfx_themes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buttons = []
    for key, t in PROFILE_THEMES.items():
        req = DONATE_TIERS.get(t["min_tier"], {}).get("name", t["min_tier"])
        buttons.append([InlineKeyboardButton(f"{t['name']} ({req})", callback_data=f"pfx_theme:{key}")])
    buttons.append([InlineKeyboardButton("🗑️ Temani Olib Tashlash", callback_data="pfx_theme:none")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="pfx_studio")])
    await query.edit_message_text(
        "🎨 *PROFIL TEMASINI TANLANG:*\nTema profil kartangizning bezak chiziqlarini o'zgartiradi.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def pfx_theme_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    key = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
    async with AsyncSessionLocal() as session:
        ok, msg = await set_profile_theme(session, query.from_user.id, key)
    await query.answer(msg, show_alert=not ok)
    if ok:
        text, kb = await _render_extras_studio(query.from_user.id)
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=kb)


async def pfx_crests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = []
    row = []
    for idx, em in enumerate(CREST_EMOJIS):
        row.append(InlineKeyboardButton(em, callback_data=f"pfx_crest:{idx}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🗑️ Gerbni Olib Tashlash", callback_data="pfx_crest:none")])
    rows.append([InlineKeyboardButton("🔙 Orqaga", callback_data="pfx_studio")])
    await query.edit_message_text(
        "🛡️ *GERB EMOJI TANLANG:*\nIsmingiz yonida va reytinglarda ko'rinadi.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def pfx_crest_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    val = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
    crest = None
    if val != "none":
        try:
            crest = CREST_EMOJIS[int(val)]
        except (ValueError, IndexError):
            await query.answer("❌ Noto'g'ri tanlov.", show_alert=True)
            return
    async with AsyncSessionLocal() as session:
        ok, msg = await set_profile_crest(session, query.from_user.id, crest)
    await query.answer(msg, show_alert=not ok)
    if ok:
        text, kb = await _render_extras_studio(query.from_user.id)
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=kb)


async def pfx_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if data == "pfx_castle_ask":
        context.user_data["pfx_awaiting"] = "castle_name"
        prompt = "🏰 Qal'angizning shaxsiy nomini yuboring (maksimal 24 ta belgi, havola va @siz):"
        clr_cb = "pfx_clear:castle_name"
    else:
        context.user_data["pfx_awaiting"] = "victory_message"
        prompt = "⚔️ Duel yoki jang g'alabasida ko'rinadigan shaxsiy g'alaba xabaringizni yuboring (maksimal 80 ta belgi, havola va @siz):"
        clr_cb = "pfx_clear:victory_message"
    await query.edit_message_text(
        prompt,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Olib Tashlash", callback_data=clr_cb)],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="pfx_studio")],
        ]),
    )


async def pfx_clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    field = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
    context.user_data.pop("pfx_awaiting", None)
    async with AsyncSessionLocal() as session:
        if field == "castle_name":
            ok, msg = await set_castle_name(session, query.from_user.id, None)
        else:
            ok, msg = await set_victory_message(session, query.from_user.id, None)
    await query.answer(msg, show_alert=not ok)
    text, kb = await _render_extras_studio(query.from_user.id)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=kb)


async def pfx_text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    awaiting = context.user_data.get("pfx_awaiting")
    if not awaiting or not update.message or not update.message.text:
        return
    raw_text = update.message.text
    async with AsyncSessionLocal() as session:
        if awaiting == "castle_name":
            ok, msg = await set_castle_name(session, update.effective_user.id, raw_text)
        else:
            ok, msg = await set_victory_message(session, update.effective_user.id, raw_text)
    if ok:
        context.user_data.pop("pfx_awaiting", None)
    await update.message.reply_text(msg)


async def pfx_admin_mod_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if not is_admin(uid) and uid != OWNER_ID:
        await query.answer("❌ Faqat admin!", show_alert=True)
        return
    await query.answer()
    parts = (query.data or "").split(":")
    if len(parts) < 2 or not parts[1].isdigit():
        return
    target_id = int(parts[1])
    async with AsyncSessionLocal() as session:
        info = await admin_get_user_profile_extras(session, target_id)
    if not info.get("found"):
        await query.edit_message_text("❌ Foydalanuvchi topilmadi.")
        return
    u = info["user"]
    text = (
        f"🛡️ *PROFIL MATNLARI MODERATSIYASI*\n"
        f"Lord: {escape_md(u.full_name or str(u.id))}\n\n"
        f"• Shior: {escape_md(info['custom_status'] or 'Yoq')}\n"
        f"• Qal'a nomi: {escape_md(info['castle_name'] or 'Yoq')}\n"
        f"• G'alaba xabari: {escape_md(info['victory_message'] or 'Yoq')}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Shiorni Tozalash", callback_data=f"pfx_adm_clr:{u.id}:status")],
        [InlineKeyboardButton("🗑️ Qal'a Nomini Tozalash", callback_data=f"pfx_adm_clr:{u.id}:castle_name")],
        [InlineKeyboardButton("🗑️ G'alaba Xabarini Tozalash", callback_data=f"pfx_adm_clr:{u.id}:victory_message")],
        [InlineKeyboardButton("🧹 Barchasini Tozalash", callback_data=f"pfx_adm_clr:{u.id}:all")],
        [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def pfx_admin_clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if not is_admin(uid) and uid != OWNER_ID:
        await query.answer("❌ Faqat admin!", show_alert=True)
        return
    parts = (query.data or "").split(":")
    if len(parts) < 3 or not parts[1].isdigit():
        return
    target_id = int(parts[1])
    field = parts[2]
    async with AsyncSessionLocal() as session:
        ok, msg = await admin_clear_user_profile_text(session, target_id, field)
    await query.answer(msg, show_alert=True)
    query.data = f"pfx_adm_mod:{target_id}"
    await pfx_admin_mod_callback(update, context)


async def pfx_sec_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, query.from_user.id)
        if not user or get_active_vip_tier(user) == "free":
            await query.edit_message_text(
                "❌ Bo'limlarga rasm/video qo'yish faqat faol VIP Homiy egalari uchundir!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 VIP Paketlar", callback_data="menu_donate")]]),
            )
            return
        media_map = await get_all_user_section_media(session, user)

    lines = [
        "🖼️ *BO'LIMLAR MEDIASI (VIP)*",
        "Har bir bo'limni ochganingizda ko'rinadigan shaxsiy rasm (Noble+) yoki video/GIF (Lord+) o'rnating:\n",
    ]
    buttons = []
    for key, cfg in SECTION_MEDIA_CONFIG.items():
        cur = media_map.get(key)
        status = f"✅ ({cur['media_type']})" if cur else "⚪ O'rnatilmagan"
        lines.append(f"• *{cfg['name']}:* {status}")
        buttons.append([InlineKeyboardButton(f"{cfg['name']} — {status}", callback_data=f"pfx_sec_pick:{key}")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="pfx_studio")])
    text = "\n".join(lines)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


async def pfx_sec_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
    cfg = SECTION_MEDIA_CONFIG.get(key)
    if not cfg:
        return
    context.user_data["pfx_awaiting_sec_media"] = key
    text = (
        f"🖼️ *{cfg['name'].upper()}*\n\n"
        f"{cfg['desc']}\n\n"
        "📤 Endi menga **Rasm** (Noble+) yoki **Video / GIF** (Lord+) yuboring.\n"
        "_(Yoki pastdagi tugma orqali o'chirib tashlashingiz mumkin)_"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Mediani O'chirish", callback_data=f"pfx_sec_clear:{key}")],
        [InlineKeyboardButton("🔙 Bo'limlar Ro'yxati", callback_data="pfx_sec_menu")],
    ])
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=kb)


async def pfx_sec_clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    key = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
    context.user_data.pop("pfx_awaiting_sec_media", None)
    async with AsyncSessionLocal() as session:
        ok, msg = await clear_user_section_media(session, query.from_user.id, key)
    await query.answer(msg, show_alert=True)
    await pfx_sec_menu_callback(update, context)


async def pfx_sec_media_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sec_key = context.user_data.get("pfx_awaiting_sec_media")
    if not sec_key or not update.message:
        return
    media_type = None
    file_id = None
    if update.message.photo:
        media_type = "photo"
        file_id = update.message.photo[-1].file_id
    elif update.message.video:
        media_type = "video"
        file_id = update.message.video.file_id
    elif update.message.animation:
        media_type = "animation"
        file_id = update.message.animation.file_id
    if not media_type or not file_id:
        return

    async with AsyncSessionLocal() as session:
        ok, msg = await set_user_section_media(
            session, update.effective_user.id, sec_key, media_type, file_id
        )
    if ok:
        context.user_data.pop("pfx_awaiting_sec_media", None)
    await update.message.reply_text(
        msg,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🖼️ Bo'limlar Mediasi", callback_data="pfx_sec_menu")]]),
    )


def register_profile_extras_handlers(app: Application):
    app.add_handler(CallbackQueryHandler(pfx_studio_callback, pattern="^pfx_studio$"))
    app.add_handler(CallbackQueryHandler(pfx_themes_callback, pattern="^pfx_themes$"))
    app.add_handler(CallbackQueryHandler(pfx_theme_set_callback, pattern="^pfx_theme:"))
    app.add_handler(CallbackQueryHandler(pfx_crests_callback, pattern="^pfx_crests$"))
    app.add_handler(CallbackQueryHandler(pfx_crest_set_callback, pattern="^pfx_crest:"))
    app.add_handler(CallbackQueryHandler(pfx_prompt_callback, pattern="^pfx_(castle|victory)_ask$"))
    app.add_handler(CallbackQueryHandler(pfx_clear_callback, pattern="^pfx_clear:"))
    app.add_handler(CallbackQueryHandler(pfx_sec_menu_callback, pattern="^pfx_sec_menu$"))
    app.add_handler(CallbackQueryHandler(pfx_sec_pick_callback, pattern="^pfx_sec_pick:"))
    app.add_handler(CallbackQueryHandler(pfx_sec_clear_callback, pattern="^pfx_sec_clear:"))
    app.add_handler(CallbackQueryHandler(pfx_admin_mod_callback, pattern="^pfx_adm_mod:"))
    app.add_handler(CallbackQueryHandler(pfx_admin_clear_callback, pattern="^pfx_adm_clr:"))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, pfx_text_input_handler),
        group=4,
    )
    app.add_handler(
        MessageHandler(
            (filters.PHOTO | filters.VIDEO | filters.ANIMATION) & filters.ChatType.PRIVATE,
            pfx_sec_media_input_handler,
        ),
        group=4,
    )
