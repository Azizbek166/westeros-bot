import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def _safe_edit_or_reply(query, update, text: str, reply_markup: InlineKeyboardMarkup = None, parse_mode: str = "Markdown"):
    """Xabarni xavfsiz tahrirlash yoki yuborish (photo xabarlar va parse xatolariga chidamli)"""
    if query:
        msg = query.message
        if getattr(msg, "photo", None):
            try:
                await msg.delete()
            except Exception:
                pass
            return await msg.chat.send_message(text, reply_markup=reply_markup, parse_mode=parse_mode)
        try:
            return await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            try:
                return await query.edit_message_text(text, reply_markup=reply_markup)
            except Exception:
                return await msg.reply_text(text, reply_markup=reply_markup)
    elif update and update.effective_message:
        try:
            return await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            return await update.effective_message.reply_text(text, reply_markup=reply_markup)


async def spy_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Josuslik asosiy menyusi"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            msg = "❌ Siz hali ro'yxatdan o'tmagansiz. /start bosing."
            await _safe_edit_or_reply(query, update, msg)
            return

        await crud.check_and_reset_daily_limits(session, user)
        scout_cnt = getattr(user, "daily_spy_scout_count", 0) or 0
        sabotage_cnt = getattr(user, "daily_spy_sabotage_count", 0) or 0
        gates_cnt = getattr(user, "daily_spy_gates_count", 0) or 0

        rep_text = ""
        try:
            reports = await crud.get_user_spy_reports(session, user.id, limit=3)
            if reports:
                rep_text = "\n📜 **Oxirgi hisobotlar:**\n"
                for r in reports:
                    status_emoji = "✅" if r.status == "success" else "❌"
                    t_name = r.target_territory.name if (r.target_territory and getattr(r.target_territory, "name", None)) else f"Qal'a #{r.target_territory_id}"
                    t_time = (r.created_at or datetime.utcnow()).strftime('%H:%M')
                    m_type = (r.mission_type or "scout").upper()
                    rep_text += f"• {status_emoji} *{m_type}* ({t_name}) — {t_time}\n"
        except Exception as e:
            logger.warning(f"Oxirgi josuslik hisobotlarini olishda xatolik: {e}")

        text = (
            "🕵️🗡️ **JOSUSLIK VA QIZIL TO'Y NIFOG'I (ESPIONAGE)**\n\n"
            "Vesterosda janglar faqat ochiq maydonda yutilmaydi. Yashirin xanjar, zaharlangan sharob va sotib olingan qo'riqchilar butun saltanat taqdirini hal qiladi!\n\n"
            f"💰 Hamyoningiz: **{user.gold:,}** Oltin\n"
            f"🎖️ Nufuzingiz: **{user.prestige:,}** ball\n\n"
            "🎯 **Mavjud Operatsiyalar va Kunlik Limitlar:**\n"
            f"1. 🕵️ **Razvedka (1,000💰):** Qal'a garnizoni, devor balandligi, wildfire va ajdarlarni aniqlash. (85% omad) | Limit: **{scout_cnt}/2**\n"
            f"2. 🔥 **Sabotaj (3,000💰):** Yashil olov bochkalarini yoqish yoki devorlarni yemirib ketish. (65% omad) | Limit: **{sabotage_cnt}/2**\n"
            f"3. 🚪 **Darvozalarni ochish (5,000💰):** Qal'a temir darvozalarini ichkaridan ochib qo'yish (-30% devor mudofaasi, 2 soat). (55% omad) | Limit: **{gates_cnt}/2**\n\n"
            "⚠️ *Eslatma: Har bir operatsiya uchun kuniga ko'pi bilan 2 martadan limit berilgan. Josus qo'lga olinsa, qatl etiladi, oltin va nufuz boy beriladi!*"
            f"{rep_text}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Qal'aga josus yuborish", callback_data="spy_pick_page:0")],
            [InlineKeyboardButton("📜 Barcha hisobotlarim", callback_data="spy_history")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ])

        await _safe_edit_or_reply(query, update, text, reply_markup=keyboard)


async def spy_pick_terr_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Josuslik uchun nishon hududni tanlash (sahifalangan)"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    offset = 0
    if query and query.data and query.data.startswith("spy_pick_page:"):
        try:
            offset = int(query.data.split(":")[1])
        except Exception:
            offset = 0

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        res = await session.execute(select(models.Territory).order_by(models.Territory.id))
        all_terrs = res.scalars().all()

        eligible_terrs = []
        for t in all_terrs:
            if user.house_id and t.owner_house_id == user.house_id:
                continue
            if getattr(t, "conquered_by_user_id", None) == user.id:
                continue
            eligible_terrs.append(t)

        if not eligible_terrs:
            text = (
                "🎯 **JOSUSLIK UCHUN QAL'ALAR:**\n\n"
                "Hozirda josus yuborish uchun dushman qal'alari mavjud emas. Barcha qal'alar sizga yoki xonadoningizga tegishli!"
            )
            buttons = [[InlineKeyboardButton("🔙 Josuslik menyusi", callback_data="menu_espionage")]]
            await _safe_edit_or_reply(query, update, text, reply_markup=InlineKeyboardMarkup(buttons))
            return

        page_size = 8
        page_terrs = eligible_terrs[offset : offset + page_size]

        buttons = []
        row = []
        for t in page_terrs:
            row.append(InlineKeyboardButton(f"🏰 {t.name}", callback_data=f"spy_terr:{t.id}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        nav_row = []
        if offset > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"spy_pick_page:{max(0, offset - page_size)}"))
        if offset + page_size < len(eligible_terrs):
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"spy_pick_page:{offset + page_size}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Josuslik menyusi", callback_data="menu_espionage")])

        total_pages = max(1, (len(eligible_terrs) + page_size - 1) // page_size)
        current_page = (offset // page_size) + 1

        text = (
            "🎯 **JOSUSLIK UCHUN QAL'ANI TANLANG:**\n\n"
            f"Qaysi dushman qal'asiga ayg'oqchi yubormoqchisiz?\n"
            f"📄 Sahifa: **{current_page}/{total_pages}** | 💰 Hamyoningiz: **{user.gold:,}** Oltin"
        )
        await _safe_edit_or_reply(query, update, text, reply_markup=InlineKeyboardMarkup(buttons))


async def spy_terr_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan qal'a bo'yicha operatsiyani tanlash"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    terr_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        terr = await session.get(models.Territory, terr_id)
        if not terr:
            await _safe_edit_or_reply(query, update, "❌ Qal'a topilmadi.")
            return

        tg_user = update.effective_user
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        u_gold = user.gold if user else 0
        if user:
            await crud.check_and_reset_daily_limits(session, user)

        scout_cnt = getattr(user, "daily_spy_scout_count", 0) if user else 0
        sabotage_cnt = getattr(user, "daily_spy_sabotage_count", 0) if user else 0
        gates_cnt = getattr(user, "daily_spy_gates_count", 0) if user else 0

        scout_tag = f"({scout_cnt}/2)" if scout_cnt < 2 else "(2/2 [TO'LIQ])"
        sabotage_tag = f"({sabotage_cnt}/2)" if sabotage_cnt < 2 else "(2/2 [TO'LIQ])"
        gates_tag = f"({gates_cnt}/2)" if gates_cnt < 2 else "(2/2 [TO'LIQ])"

        h_name = "Mustaqil"
        if terr.owner_house_id:
            h = await session.get(models.House, terr.owner_house_id)
            if h:
                h_name = f"{getattr(h, 'emoji', '🛡️')} {h.name}"

        text = (
            f"🏰 **QAL'A: {terr.name}** ({terr.castle_name})\n"
            f"👑 Xonadon: **{h_name}**\n"
            f"🗺️ Mintaqa: **{terr.region}**\n"
            f"💰 Sizdagi oltin: **{u_gold:,}** Oltin\n\n"
            f"Ushbu qal'aga qanday operatsiya uyushtirilsin?"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🕵️ Razvedka {scout_tag} — 1,000💰", callback_data=f"spy_do:scout:{terr.id}")],
            [InlineKeyboardButton(f"🔥 Sabotaj {sabotage_tag} — 3,000💰", callback_data=f"spy_do:sabotage:{terr.id}")],
            [InlineKeyboardButton(f"🚪 Darvozalarni ochish {gates_tag} — 5,000💰", callback_data=f"spy_do:open_gates:{terr.id}")],
            [InlineKeyboardButton("🔙 Qal'alar ro'yxati", callback_data="spy_pick_page:0")],
        ])
        await _safe_edit_or_reply(query, update, text, reply_markup=keyboard)


async def spy_execute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Josuslik operatsiyasini ijro etish"""
    query = update.callback_query
    if query:
        try:
            await query.answer("Operatsiya bajarilmoqda...")
        except Exception:
            pass

    parts = query.data.split(":")
    mission_type = parts[1]
    terr_id = int(parts[2])

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        success, report_text, rep_data = await crud.send_spy_mission(
            session=session,
            user_id=user.id,
            target_territory_id=terr_id,
            mission_type=mission_type,
            bot_app=context.application,
        )

        if not success and not rep_data:
            if query:
                clean_alert = report_text.replace("❌", "").replace("*", "").strip()
                await query.answer(f"❌ {clean_alert[:140]}", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Boshqa Qal'a", callback_data="spy_pick_page:0")],
            [InlineKeyboardButton("📜 Barcha hisobotlar", callback_data="spy_history")],
            [InlineKeyboardButton("🔙 Josuslik menyusi", callback_data="menu_espionage")],
        ])
        await _safe_edit_or_reply(query, update, report_text, reply_markup=keyboard)


async def spy_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha josuslik hisobotlarini ko'rish"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        reports = await crud.get_user_spy_reports(session, user.id, limit=5)
        if not reports:
            text = "📜 **JOSUSLIK HISOBOTLARI:**\n\nSizda hali hech qanday josuslik hisobotlari yo'q."
        else:
            text = "📜 **SIZNING OXIRGI 5 TA JOSUSLIK HISOBOTINGIZ:**\n\n"
            for r in reports:
                status_icon = "🟢 Muvaffaqiyatli" if r.status == "success" else "🔴 Fosh bo'ldi"
                t_name = r.target_territory.name if (r.target_territory and getattr(r.target_territory, "name", None)) else f"Qal'a #{r.target_territory_id}"
                clean_snippet = (r.report_text or "").replace("*", "").replace("_", "").replace("`", "")[:120].strip()
                t_time = (r.created_at or datetime.utcnow()).strftime("%d.%m %H:%M")
                m_type = (r.mission_type or "scout").upper()
                text += (
                    f"• **{m_type}** ({t_name}) — {status_icon} ({t_time})\n"
                    f"{clean_snippet}...\n\n"
                )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Qal'aga josus yuborish", callback_data="spy_pick_page:0")],
            [InlineKeyboardButton("🔙 Josuslik menyusi", callback_data="menu_espionage")]
        ])
        await _safe_edit_or_reply(query, update, text, reply_markup=keyboard)


def register_espionage_handlers(app: Application):
    """Josuslik handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["spy", "espionage", "josuslik", "josus"], spy_menu_callback))
    app.add_handler(CallbackQueryHandler(spy_menu_callback, pattern="^menu_espionage$"))
    app.add_handler(CallbackQueryHandler(spy_pick_terr_callback, pattern="^spy_pick_"))
    app.add_handler(CallbackQueryHandler(spy_terr_detail_callback, pattern="^spy_terr:\\d+$"))
    app.add_handler(CallbackQueryHandler(spy_execute_callback, pattern="^spy_do:(scout|sabotage|open_gates):\\d+$"))
    app.add_handler(CallbackQueryHandler(spy_history_callback, pattern="^spy_history$"))
