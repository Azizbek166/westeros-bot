"""
Dengiz Janglari va Flot Telegram Handler (prefiks: nav_).
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from config import escape_md
from data.naval_data import (
    SHIP_TYPES,
    SEA_ZONES,
    DAILY_NAVAL_PVE_LIMIT,
    DAILY_NAVAL_PVP_LIMIT,
)
from database import AsyncSessionLocal, crud
from services.naval_service import (
    get_or_create_fleet,
    calc_fleet_stats,
    build_ships,
    raid_sea_zone,
    get_pvp_targets,
    attack_player_fleet,
    get_naval_leaderboard,
    _refresh_daily_naval_counters,
)

logger = logging.getLogger(__name__)


async def _render_naval_hub(tg_id: int):
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_id)
        if not user:
            return "❌ Avval /start buyrug'ini bosing.", InlineKeyboardMarkup([])
        fleet = await get_or_create_fleet(session, user.id)
        _refresh_daily_naval_counters(fleet)
        await session.commit()
        stats = calc_fleet_stats(fleet)

    bonus_tag = " (+15% Flagman ruhi!)" if stats["flagship_bonus"] else ""
    text = (
        "🌊 *DENGIZ JANGLARI VA QIROLLIK FLOTI*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Xazina:* {user.gold or 0:,}🪙 | {user.food or 0:,}🌾 | {user.iron or 0:,}⛓️\n\n"
        f"⚓ *Sizning Flotingiz ({stats['total_ships']} ta kema):*\n"
        f"• ⛵ Yelkanli Qayiq: *{fleet.sloops or 0}*\n"
        f"• 🚣 Jangovar Galera: *{fleet.galleys or 0}*\n"
        f"• ⛴️ Harbiy Kema: *{fleet.warships or 0}*\n"
        f"• 🚢 Qirollik Flagmani: *{fleet.flagships or 0}*\n\n"
        f"⚔️ *Flot Quvvati:* *{stats['power']:,}*{bonus_tag}\n"
        f"🛡️ *Dengiz Mudofaasi:* *{stats['defense']:,}*\n"
        f"🏆 *G'alabalar:* {(fleet.naval_wins or 0) + (fleet.pirate_wins or 0)} | "
        f"🏴‍☠️ Bugungi reydlar: {fleet.daily_pve_count or 0}/{DAILY_NAVAL_PVE_LIMIT} | "
        f"⚔️ PvP: {fleet.daily_pvp_count or 0}/{DAILY_NAVAL_PVP_LIMIT}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚓ Kemasozlik (Kema Qurish)", callback_data="nav_shipyard")],
        [
            InlineKeyboardButton("🏴‍☠️ Qaroqchilarga Reyd", callback_data="nav_pve"),
            InlineKeyboardButton("⚔️ PvP Dengiz Jangi", callback_data="nav_pvp"),
        ],
        [InlineKeyboardButton("🏆 Dengizlar Hukmdori Reytingi", callback_data="nav_top")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ])
    return text, kb


async def naval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    text, kb = await _render_naval_hub(update.effective_user.id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def naval_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text, kb = await _render_naval_hub(query.from_user.id)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=kb)


async def nav_shipyard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lines = ["⚓ *KEMASOZLIK DOCKI — KEMA QURISH*\n"]
    buttons = []
    for key, s in SHIP_TYPES.items():
        lines.append(
            f"{s['icon']} *{s['name']}*\n"
            f"  └ Narx: {s['gold']:,}🪙, {s['iron']:,}⛓️, {s['food']:,}🌾 | "
            f"⚔️ +{s['power']} | 🛡️ +{s['defense']}\n"
            f"  └ _{s['desc']}_"
        )
        buttons.append([
            InlineKeyboardButton(f"{s['icon']} +1 {s['name']}", callback_data=f"nav_build:{key}:1"),
            InlineKeyboardButton("+5 ta", callback_data=f"nav_build:{key}:5"),
        ])
    buttons.append([InlineKeyboardButton("🔙 Flotga Qaytish", callback_data="menu_naval")])
    text = "\n".join(lines)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


async def nav_build_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = (query.data or "").split(":")
    if len(parts) < 3:
        return
    ship_key = parts[1]
    cnt = int(parts[2]) if parts[2].isdigit() else 1
    async with AsyncSessionLocal() as session:
        ok, msg = await build_ships(session, query.from_user.id, ship_key, cnt)
    await query.answer(msg.replace("*", "")[:190], show_alert=True)
    if ok:
        await naval_menu_callback(update, context)


async def nav_pve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lines = ["🏴‍☠️ *DENGIZ QAROQCHILARIGA QARSHI YURISH*\n"]
    buttons = []
    for key, z in SEA_ZONES.items():
        lines.append(
            f"• *{z['name']}*\n"
            f"  └ Raqib: _{z['enemy_name']}_ (Min kuch: {z['min_power']})\n"
            f"  └ O'lja: {z['gold_min']:,}-{z['gold_max']:,}🪙, +{z['xp']} XP"
        )
        buttons.append([InlineKeyboardButton(f"⚔️ {z['name']}", callback_data=f"nav_raid:{key}")])
    buttons.append([InlineKeyboardButton("🔙 Flotga Qaytish", callback_data="menu_naval")])
    text = "\n".join(lines)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


async def nav_raid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    zone_key = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
    async with AsyncSessionLocal() as session:
        ok, msg = await raid_sea_zone(session, query.from_user.id, zone_key)
    await query.answer("⚔️ Dengiz jangi yakunlandi!" if ok else msg[:180], show_alert=not ok)
    if ok:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏴‍☠️ Yana Reyd Qilish", callback_data="nav_pve")],
            [InlineKeyboardButton("🌊 Flotga Qaytish", callback_data="menu_naval")],
        ])
        try:
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await query.edit_message_text(msg.replace("*", ""), parse_mode=None, reply_markup=kb)


async def nav_pvp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, query.from_user.id)
        if not user:
            return
        targets = await get_pvp_targets(session, user, limit=8)

    if not targets:
        text = "⚔️ *PvP DENGIZ JANGI*\n\nHozircha dengizda hujum qilish mumkin bo'lgan raqib flotlari topilmadi."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Flotga Qaytish", callback_data="menu_naval")]])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        return

    lines = ["⚔️ *PvP DENGIZ JANGI — RAQIB FLOTINI TANLANG:*\n"]
    buttons = []
    for t in targets:
        nm = escape_md(t["name"])
        lines.append(f"• *{nm}* — ⚓ {t['ships']} kema | ⚔️ Kuch: {t['power']:,}")
        buttons.append([InlineKeyboardButton(f"⚔️ {t['name']} ({t['power']:,} kuch)", callback_data=f"nav_atk:{t['user_id']}")])
    buttons.append([InlineKeyboardButton("🔙 Flotga Qaytish", callback_data="menu_naval")])
    text = "\n".join(lines)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=InlineKeyboardMarkup(buttons))


async def nav_attack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tid_str = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
    if not tid_str.isdigit():
        return
    async with AsyncSessionLocal() as session:
        ok, msg = await attack_player_fleet(session, query.from_user.id, int(tid_str))
    await query.answer("⚔️ Jang yakunlandi!" if ok else msg[:180], show_alert=not ok)
    if ok:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚔️ Yana Hujum Qilish", callback_data="nav_pvp")],
            [InlineKeyboardButton("🌊 Flotga Qaytish", callback_data="menu_naval")],
        ])
        try:
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await query.edit_message_text(msg.replace("*", ""), parse_mode=None, reply_markup=kb)


async def nav_top_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with AsyncSessionLocal() as session:
        top = await get_naval_leaderboard(session, limit=10)
    lines = ["🏆 *DENGIZLAR HUKMDORI — TOP 10 ADMIRAL*\n"]
    if not top:
        lines.append("Hozircha dengiz janglari o'tkazilmagan.")
    else:
        for i, row in enumerate(top, 1):
            nm = escape_md(row["name"])
            lines.append(
                f"{i}. *{nm}* — 🏆 {row['wins']} g'alaba | ⚓ {row['ships']} kema | ⚔️ {row['power']:,}"
            )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Flotga Qaytish", callback_data="menu_naval")]])
    text = "\n".join(lines)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await query.edit_message_text(text.replace("*", ""), parse_mode=None, reply_markup=kb)


def register_naval_handlers(app: Application):
    app.add_handler(CommandHandler("naval", naval_command))
    app.add_handler(CallbackQueryHandler(naval_menu_callback, pattern="^menu_naval$"))
    app.add_handler(CallbackQueryHandler(nav_shipyard_callback, pattern="^nav_shipyard$"))
    app.add_handler(CallbackQueryHandler(nav_build_callback, pattern="^nav_build:"))
    app.add_handler(CallbackQueryHandler(nav_pve_callback, pattern="^nav_pve$"))
    app.add_handler(CallbackQueryHandler(nav_raid_callback, pattern="^nav_raid:"))
    app.add_handler(CallbackQueryHandler(nav_pvp_callback, pattern="^nav_pvp$"))
    app.add_handler(CallbackQueryHandler(nav_attack_callback, pattern="^nav_atk:"))
    app.add_handler(CallbackQueryHandler(nav_top_callback, pattern="^nav_top$"))
