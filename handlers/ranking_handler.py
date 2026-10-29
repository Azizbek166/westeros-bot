import logging
from typing import Dict, Any, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from keyboards.menus import back_to_main_keyboard
from config import escape_md

logger = logging.getLogger(__name__)

MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def get_user_display_name(u: models.User) -> str:
    """O'yinchining ifodali nomi: Qahramon nomi yoki Telegram ismi, username bilan (lazy-load xatolaridan to'liq himoyalangan)"""
    hero_name = getattr(u, "full_name", None) or "Lord"
    try:
        from sqlalchemy.orm import inspect
        insp = inspect(u)
        if "characters" in insp.dict:
            chars = insp.dict["characters"]
            if chars and len(chars) > 0 and getattr(chars[0], "name", None):
                hero_name = chars[0].name
    except Exception:
        pass
    uname = f" (@{u.username})" if getattr(u, "username", None) else ""
    return f"{hero_name}{uname}"


async def format_prestige_text(session, period: str = "all") -> str:
    top_users = await crud.get_top10_prestige(session, period=period)
    if period == "daily":
        header = "👑 **BUGUNGI KUNNING ENG FAOL VA NUFUZLI 10 LORDI (KUNLIK REYTING)**"
        footer = "\n_Kunlik nufuz har kuni 00:00 UTC da yangilanadi._"
    elif period == "weekly":
        header = "👑 **USHBU HAFTANING ENG NUFUZLI 10 LORDI (HAFTALIK REYTING)**"
        footer = "\n_Haftalik reyting yakshanba kuni soat 20:00 da sarhisob qilinadi._"
    else:
        header = "👑 **VESTEROSNING ENG MASHHUR VA NUFUZLI 10 LORDI (UMUMIY REYTING)**"
        footer = "\n_Mavsum yakunida umumiy reyting g'olibi Shon-sharaf Zalidan joy oladi._"

    lines = [header, ""]
    if not top_users:
        lines.append("_Hozircha reytingda o'yinchilar yo'q._")
    else:
        for idx, u in enumerate(top_users):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            name = get_user_display_name(u)
            h_name = u.house.name if u.house else "Mustaqil"
            h_emoji = u.house.emoji if u.house else "🏰"
            t_badge = f" [🎖️ {escape_md(u.title)}]" if getattr(u, "title", None) else ""

            if period == "daily":
                pts = getattr(u, "daily_prestige_earned", 0) or 0
                lines.append(f"{med} **{escape_md(name)}**{t_badge}\n     {h_emoji} {escape_md(h_name)} — **+{pts:,} 🏆** bugun (Jami: {u.prestige:,} 🏆)")
            elif period == "weekly":
                pts = getattr(u, "weekly_prestige_earned", 0) or 0
                lines.append(f"{med} **{escape_md(name)}**{t_badge}\n     {h_emoji} {escape_md(h_name)} — **+{pts:,} 🏆** bu hafta (Jami: {u.prestige:,} 🏆)")
            else:
                lines.append(f"{med} **{escape_md(name)}**{t_badge}\n     {h_emoji} {escape_md(h_name)} — **{u.prestige:,} 🏆** nufuz")

    lines.append(footer)
    return "\n".join(lines)


async def format_xp_text(session) -> str:
    """Foydalanuvchilarning tajriba va daraja (XP & Level) bo'yicha alohida TOP 10 reytingi"""
    top_users = await crud.get_top10_xp(session)
    header = "🌟 **VESTEROSNING ENG TAJRIBALI TOP 10 LORDLARI (DARAJA VA XP REYTINGI)**"
    footer = "\n_Tajriba (XP) qal'alarni kengaytirish, janglar, topshiriqlar va turnirlar orqali qo'lga kiritiladi._"

    lines = [header, ""]
    if not top_users:
        lines.append("_Hozircha tajribali lordlar mavjud emas._")
    else:
        from core.leveling import LEVEL_TITLES, MAX_LEVEL
        for idx, u in enumerate(top_users):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            name = get_user_display_name(u)
            h_name = u.house.name if u.house else "Mustaqil"
            h_emoji = u.house.emoji if u.house else "🏰"
            t_badge = f" [🎖️ {escape_md(u.title)}]" if getattr(u, "title", None) else ""
            lvl = u.level or 1
            xp = u.xp or 0
            lvl_info = LEVEL_TITLES.get(lvl, {})
            title_name = lvl_info.get("title", f"Lord Lv.{lvl}")
            next_xp = LEVEL_TITLES.get(lvl + 1, {}).get("xp_req", 0) if lvl < MAX_LEVEL else None
            xp_desc = f"{xp:,} / {next_xp:,} XP" if next_xp else f"{xp:,} XP (Maksimal)"

            lines.append(
                f"{med} **{escape_md(name)}**{t_badge}\n"
                f"     {h_emoji} {escape_md(h_name)} — **{lvl}-daraja** ({xp_desc})\n"
                f"     └ 👑 Unvon: *{title_name}*"
            )

    lines.append(footer)
    return "\n".join(lines)


async def format_last_week_text(session) -> str:
    """O'tgan haftadagi umumiy TOP 10 sarhisob jadvali (rasmiy hisobot)"""
    from sqlalchemy import select
    evt_res = await session.execute(
        select(models.EventState).where(models.EventState.event_name == "last_weekly_leaderboard")
    )
    last_ev = evt_res.scalar_one_or_none()
    if last_ev and last_ev.data_json:
        return last_ev.data_json

    from core.leaderboard_engine import generate_weekly_rankings, format_weekly_leaderboard_post
    data = await generate_weekly_rankings(session)
    post_text = format_weekly_leaderboard_post(data)
    return post_text


async def format_wealth_text(session, period: str = "all") -> str:
    top_users = await crud.get_top10_wealth(session, period=period)
    if period == "daily":
        header = "💰 **BUGUN ENG KO'P OLTIN TOPGAN TOP 10 LORDLAR (KUNLIK REYTING)**"
        footer = "\n_Kunlik ishlab topilgan boyliklar har kuni 00:00 da hisoblanadi._"
    elif period == "weekly":
        header = "💰 **HAFTA DAVOMIDA ENG KO'P OLTIN TOPGAN TOP 10 LORDLAR (HAFTALIK REYTING)**"
        footer = "\n_Hafta yakunida eng boy savdogar va lordlarga maxsus unvonlar beriladi._"
    else:
        header = "💰 **VESTEROSNING ENG BOY TOP 10 LORDLARI (UMUMIY XAZINA)**"
        footer = "\n_Temir Bank omonatlari va shaxsiy xazinalar bo'yicha eng boy hukmdorlar._"

    lines = [header, ""]
    if not top_users:
        lines.append("_Hozircha xazinador lordlar mavjud emas._")
    else:
        for idx, u in enumerate(top_users):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            name = get_user_display_name(u)
            h_name = u.house.name if u.house else "Mustaqil"
            h_emoji = u.house.emoji if u.house else "🏰"

            if period == "daily":
                pts = getattr(u, "daily_gold_earned", 0) or 0
                lines.append(f"{med} **{escape_md(name)}**\n     {h_emoji} {escape_md(h_name)} — **+{pts:,} 🪙** bugun (Xazina: {u.gold:,} 🪙)")
            elif period == "weekly":
                pts = getattr(u, "weekly_gold_earned", 0) or 0
                lines.append(f"{med} **{escape_md(name)}**\n     {h_emoji} {escape_md(h_name)} — **+{pts:,} 🪙** bu hafta (Xazina: {u.gold:,} 🪙)")
            else:
                lines.append(f"{med} **{escape_md(name)}**\n     {h_emoji} {escape_md(h_name)} — **{u.gold:,} 🪙** oltin")

    lines.append(footer)
    return "\n".join(lines)


async def format_armies_text(session) -> str:
    top_armies = await crud.get_top10_armies_detailed(session)
    lines = [
        "🛡️ **VESTEROSNING ENG QUDRATLI TOP 10 SARKARDALARI VA ARMIYALARI**",
        ""
    ]
    if not top_armies:
        lines.append("_Hozircha faol armiyalar mavjud emas._")
    else:
        for idx, entry in enumerate(top_armies):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            u = entry["user"]
            name = get_user_display_name(u)
            h_name = u.house.name if u.house else "Mustaqil"
            h_emoji = u.house.emoji if u.house else "🏰"
            lines.append(
                f"{med} **{escape_md(name)}** ({h_emoji} {escape_md(h_name)})\n"
                f"     🛡️ **{entry['total_troops']:,}** askar | Jang quvvati: **{entry['power']:,} ⚡**"
            )
    lines.append("\n_Harbiy quvvat barcha qismlar, otliqlar, maxsus gvardiya va qamal qurollari bo'yicha hisoblanadi._")
    return "\n".join(lines)


async def format_castles_text(session) -> str:
    top_castles = await crud.get_top10_castles(session)
    lines = [
        "🏰 **ENG KO'P QAL'A VA HUDUDLARNI ZABT ETGAN TOP 10 LORDLAR**",
        ""
    ]
    if not top_castles:
        lines.append("_Hozircha zabt etilgan qal'alar yo'q._")
    else:
        for idx, entry in enumerate(top_castles):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            u = entry["user"]
            name = get_user_display_name(u)
            h_name = u.house.name if u.house else "Mustaqil"
            h_emoji = u.house.emoji if u.house else "🏰"
            cnt = entry["castles_count"]
            lines.append(
                f"{med} **{escape_md(name)}** ({h_emoji} {escape_md(h_name)})\n"
                f"     🏰 **{cnt} ta** qal'a va viloyat sohibi"
            )
    lines.append("\n_Har bir qo'lga kiritilgan qal'a xonadon va hukmdorga muntazam o'lpon keltiradi._")
    return "\n".join(lines)


async def format_dragons_text(session) -> str:
    top_dragons = await crud.get_top10_dragons(session)
    lines = [
        "🐉 **VESTEROSNING ENG AFSONAVIY VA QUDRATLI TOP 10 AJDARLARI**",
        ""
    ]
    if not top_dragons:
        lines.append("_Hozircha tirik ajdarlar uchratilmadi._")
    else:
        stage_map = {"egg": "Tuxum 🥚", "baby": "Kichik ajdar 🐣", "adult": "Uchuvchi Bahaybat Ajdar 🐉"}
        for idx, entry in enumerate(top_dragons):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            d = entry["dragon"]
            u = entry["user"]
            name = get_user_display_name(u)
            st_str = stage_map.get(d.stage, d.stage)
            lines.append(
                f"{med} 🐲 **{escape_md(d.name)}** ({st_str}, {d.level}-daraja)\n"
                f"     Egasi: **{escape_md(name)}** | Jang quvvati: **{d.power:,} ⚡**"
            )
    lines.append("\n_Ajdar qanchalik yaxshi boqilsa va jangda chiniqsa, uning qudrati shunchalik yuksaladi._")
    return "\n".join(lines)


async def format_houses_text(session) -> str:
    top_houses = await crud.get_top_houses(session, limit=10)
    lines = [
        "🏛️ **VESTEROSNING ENG QUDRATLI VA NAFIS TOP 10 BUYUK XONADONLARI**",
        ""
    ]
    if not top_houses:
        lines.append("_Hozircha xonadonlar ro'yxati mavjud emas._")
    else:
        for idx, h in enumerate(top_houses):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            lines.append(
                f"{med} {h.emoji} **{escape_md(h.name)}** ({h.region})\n"
                f"     🏆 Nufuz: **{h.prestige:,}** | 🪙 G'azna: **{h.gold:,}**"
            )
    lines.append("\n_Xonadon nufuzi barcha a'zolarning urushdagi zafarlari va qal'alar soniga bog'liq._")
    return "\n".join(lines)


async def format_champion_text(session) -> str:
    champ = await crud.get_season_champion_candidate(session)
    u = champ.get("user")
    h = champ.get("house")
    reason = champ.get("reason")
    held_kl = champ.get("kings_landing_held")
    score = champ.get("score", 0)

    lines = [
        "╔══════════════════════════════╗",
        "  👑 **TEMIR TAXT QIROLI VA MAVSUM G'OLIBI** 🏆",
        "╚══════════════════════════════╝\n"
    ]

    if not u:
        lines.append(
            "⚔️ Hozirda Temir Taxt uchun ayovsiz kurash davom etmoqda!\n"
            "King's Landing qal'asini zabt etgan yoki mavsumda eng yuqori natija ko'rsatgan hukmdor Vesteros Qiroli deb e'lon qilinadi."
        )
    else:
        u_name = get_user_display_name(u)
        h_name = h.name if h else "Mustaqil"
        h_emoji = h.emoji if h else "🏰"
        t_title = f" «{u.title}»" if getattr(u, "title", None) else ""

        if held_kl:
            title_text = "👑 **TEMIR TAXT VA KING'S LANDING AMALDAGI SOHIBI:**"
            how = "🏰 **King's Landing (Qirol Qarorgohi)** qal'asini qo'lda ushlab turibdi!"
        else:
            title_text = "🌟 **JORIY MAVSUM YETAKCHISI (G'OLIB NOMZOD):**"
            how = f"📊 Umumiy Mavsum Ballari bo'yicha mutlaq peshqadam! (Jami ball: **{score:,}**)"

        lines.extend([
            title_text,
            f"👑 **{escape_md(u_name)}**{t_title}",
            f"🏰 Xonadon: **{h_emoji} {escape_md(h_name)}**",
            f"🎖️ Daraja: **{u.level}** | Nufuz: **{u.prestige:,} 🏆**",
            f"🪙 Xazina: **{u.gold:,}** | 🛡️ Armiya: **{champ.get('total_army', 0):,}** askar",
            f"🏰 Qal'alar soni: **{champ.get('castles_count', 0)}** ta",
            f"\n📌 **G'alaba sababi:** {how}\n",
            "📜 **Mavsum G'olibi Qoidasi:**",
            "1. King's Landing qal'asini zabt etgan Lord mavsum yakunida birinchi darajali **Temir Taxt Qiroli** deb e'lon qilinadi.",
            "2. Agar King's Landing neytral/NPC bo'lsa, quyidagi ball tizimi bo'yicha 1-o'rindagi o'yinchi yutadi:",
            "   `Ball = (Nufuz * 2) + (Oltin // 50) + (Armiya // 5) + (Qal'alar * 500)`",
            "\n🏆 G'olib Shon-sharaf Zalida abadiy muhrlanadi va maxsus sovrinlar bilan taqdirlanadi!"
        ])

    return "\n".join(lines)


def get_ranking_keyboard(category: str = "prestige", period: str = "all") -> InlineKeyboardMarkup:
    """Interaktiv reyting menyusi tugmalari"""
    buttons = [
        [
            InlineKeyboardButton(f"{'✅ ' if category == 'prestige' else ''}👑 Nufuz (Top 10)", callback_data="rank_cat:prestige:all"),
            InlineKeyboardButton(f"{'✅ ' if category == 'xp' else ''}🌟 Tajriba/XP (Top 10)", callback_data="rank_cat:xp:all"),
        ],
        [
            InlineKeyboardButton(f"{'✅ ' if category == 'wealth' else ''}💰 Boylik (Top 10)", callback_data="rank_cat:wealth:all"),
            InlineKeyboardButton(f"{'✅ ' if category == 'armies' else ''}🛡️ Armiya (Top 10)", callback_data="rank_cat:armies:all"),
        ],
        [
            InlineKeyboardButton(f"{'✅ ' if category == 'castles' else ''}🏰 Qal'alar (Top 10)", callback_data="rank_cat:castles:all"),
            InlineKeyboardButton(f"{'✅ ' if category == 'dragons' else ''}🐉 Ajdarlar (Top 10)", callback_data="rank_cat:dragons:all"),
        ],
        [
            InlineKeyboardButton(f"{'✅ ' if category == 'houses' else ''}🏛️ Xonadonlar (Top 10)", callback_data="rank_cat:houses:all"),
            InlineKeyboardButton(f"{'✅ ' if category == 'champion' else ''}👑 Mavsum G'olibi (Taxt)", callback_data="rank_cat:champion:all"),
        ],
        [
            InlineKeyboardButton(f"{'✅ ' if category == 'last_week' else ''}🗓️ O'tgan Hafta Sarhisobi (Top 10)", callback_data="rank_cat:last_week:all"),
        ],
    ]

    # Nufuz yoki boylik tanlangan bo'lsa, davrlar (kunlik, haftalik, umumiy) filtri chiqadi
    if category in ["prestige", "wealth"]:
        buttons.append([
            InlineKeyboardButton(f"{'🔹 ' if period == 'daily' else ''}📅 Kunlik", callback_data=f"rank_cat:{category}:daily"),
            InlineKeyboardButton(f"{'🔹 ' if period == 'weekly' else ''}🗓️ Haftalik", callback_data=f"rank_cat:{category}:weekly"),
            InlineKeyboardButton(f"{'🔹 ' if period == 'all' else ''}🌟 Umumiy", callback_data=f"rank_cat:{category}:all"),
        ])

    buttons.append([
        InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main"),
    ])
    return InlineKeyboardMarkup(buttons)


async def show_ranking_hub(target, user_id: int, category: str = "prestige", period: str = "all", is_message: bool = True, is_group: bool = False):
    """Reyting jadvalini shakllantirish va yuborish"""
    async with AsyncSessionLocal() as session:
        if category == "prestige":
            text = await format_prestige_text(session, period=period)
        elif category == "xp":
            text = await format_xp_text(session)
        elif category == "last_week":
            text = await format_last_week_text(session)
        elif category == "wealth":
            text = await format_wealth_text(session, period=period)
        elif category == "armies":
            text = await format_armies_text(session)
        elif category == "castles":
            text = await format_castles_text(session)
        elif category == "dragons":
            text = await format_dragons_text(session)
        elif category == "houses":
            text = await format_houses_text(session)
        elif category == "champion":
            text = await format_champion_text(session)
        else:
            text = await format_prestige_text(session, period="all")

    if is_group:
        # Guruhda pastki qotib qolgan klaviaturalarni yo'qotish uchun ReplyKeyboardRemove yuboriladi
        group_footer = (
            "\n💡 _Boshqa reytinglar: /top xp, /top hafta, /top oltin, /top otgan_hafta, /top armiya, /top qalalar, /top ajdar, /top taxt_"
        )
        full_text = text + group_footer
        clean_kb = ReplyKeyboardRemove()
        try:
            await target.reply_text(full_text, parse_mode="Markdown", reply_markup=clean_kb)
        except Exception:
            await target.reply_text(full_text, parse_mode=None, reply_markup=clean_kb)
        return

    # Shaxsiy chatda interaktiv klaviatura bilan ko'rsatiladi
    kb = get_ranking_keyboard(category=category, period=period)
    if is_message:
        try:
            await target.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await target.reply_text(text, parse_mode=None, reply_markup=kb)
    else:
        try:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await target.edit_message_text(text, parse_mode=None, reply_markup=kb)


async def ranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/rank, /top, /reyting buyruqlari (Guruh va shaxsiy chatda ishlaydi)"""
    msg = update.effective_message
    if not msg:
        return

    chat = update.effective_chat
    is_group = bool(chat and chat.type in ["group", "supergroup"])
    user_id = update.effective_user.id

    # Parametrlar (masalan: /top kun, /top hafta, /top armiya, /top ajdar, /top oltin, /top taxt)
    args = context.args or []
    arg_str = " ".join(args).lower().strip()

    category = "prestige"
    period = "all"

    if arg_str:
        if any(w in arg_str for w in ["otgan", "o'tgan", "last_week", "lastweek", "sarhisob"]):
            category = "last_week"
            period = "all"
        elif any(w in arg_str for w in ["xp", "tajriba", "daraja", "level", "lvl"]):
            category = "xp"
            period = "all"
        elif any(w in arg_str for w in ["kun", "bugun", "daily", "day"]):
            category = "prestige"
            period = "daily"
        elif any(w in arg_str for w in ["hafta", "weekly", "week"]):
            category = "prestige"
            period = "weekly"
        elif any(w in arg_str for w in ["oltin", "boylik", "gold", "wealth", "pul"]):
            category = "wealth"
            if "kun" in arg_str: period = "daily"
            elif "hafta" in arg_str: period = "weekly"
            else: period = "all"
        elif any(w in arg_str for w in ["armiya", "army", "askarlar", "harbiy"]):
            category = "armies"
        elif any(w in arg_str for w in ["qala", "qalalar", "castle", "castles", "hudud"]):
            category = "castles"
        elif any(w in arg_str for w in ["ajdar", "dragon", "dragons", "ajdarlar"]):
            category = "dragons"
        elif any(w in arg_str for w in ["xonadon", "house", "houses", "oilalar"]):
            category = "houses"
        elif any(w in arg_str for w in ["taxt", "chempion", "champion", "winner", "qirol", "g'olib"]):
            category = "champion"

    await show_ranking_hub(msg, user_id, category=category, period=period, is_message=True, is_group=is_group)


async def ranking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_rank callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_ranking_hub(query, user_id, category="prestige", period="all", is_message=False, is_group=False)


async def ranking_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """rank_cat:<category>:<period> callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    data = query.data or ""
    parts = data.split(":")
    category = parts[1] if len(parts) > 1 else "prestige"
    period = parts[2] if len(parts) > 2 else "all"

    await show_ranking_hub(query, user_id, category=category, period=period, is_message=False, is_group=False)


def register_ranking_handlers(app):
    app.add_handler(CommandHandler(["rank", "ranking", "top", "reyting", "leaderboard", "reytinglar"], ranking_command))
    app.add_handler(CallbackQueryHandler(ranking_callback, pattern="^menu_rank$"))
    app.add_handler(CallbackQueryHandler(ranking_category_callback, pattern="^rank_cat:"))
