import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def spy_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Josuslik asosiy menyusi"""
    query = update.callback_query
    if query:
        await query.answer()

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            msg = "❌ Siz hali ro'yxatdan o'tmagansiz. /start bosing."
            if query:
                await query.edit_message_text(msg)
            else:
                await update.effective_message.reply_text(msg)
            return

        reports = await crud.get_user_spy_reports(session, user.id, limit=3)
        rep_text = ""
        if reports:
            rep_text = "\n📜 **Oxirgi hisobotlar:**\n"
            for r in reports:
                status_emoji = "✅" if r.status == "success" else "❌"
                t_name = r.target_territory.name if r.target_territory else f"Qal'a #{r.target_territory_id}"
                t_time = (r.created_at or datetime.utcnow()).strftime('%H:%M')
                rep_text += f"• {status_emoji} *{r.mission_type.upper()}* ({t_name}) — {t_time}\n"

        text = (
            "🕵️🗡️ **JOSUSLIK VA QIZIL TO'Y NIFOG'I (ESPIONAGE)**\n\n"
            "Vesterosda janglar faqat ochiq maydonda yutilmaydi. Yashirin xanjar, zaharlangan sharob va sotib olingan qo'riqchilar butun saltanat taqdirini hal qiladi!\n\n"
            f"💰 Hamyoningiz: **{user.gold:,}** Oltin\n"
            f"🎖️ Nufuzingiz: **{user.prestige:,}** ball\n\n"
            "🎯 **Mavjud Operatsiyalar:**\n"
            "1. 🕵️ **Razvedka (1,000💰):** Qal'a garnizoni, devor balandligi, wildfire va ajdarlarni aniqlash. (85% omad)\n"
            "2. 🔥 **Sabotaj (3,000💰):** Yashil olov bochkalarini yoqish yoki devorlarni yemirib ketish. (65% omad)\n"
            "3. 🚪 **Darvozalarni ochish (5,000💰):** Qal'a temir darvozalarini ichkaridan ochib qo'yish (-30% devor mudofaasi, 2 soat). (55% omad)\n\n"
            "⚠️ *Eslatma: Josus qo'lga olinsa, u qatl etiladi, oltin va nufuz boy beriladi!*"
            f"{rep_text}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Qal'aga josus yuborish", callback_data="spy_pick_page:0")],
            [InlineKeyboardButton("📜 Barcha hisobotlarim", callback_data="spy_history")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ])

        if query:
            try:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            except Exception:
                await query.edit_message_text(text, reply_markup=keyboard)
        else:
            await update.effective_message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def spy_pick_terr_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Josuslik uchun nishon hududni tanlash (sahifalangan)"""
    query = update.callback_query
    await query.answer()

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
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        except Exception:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def spy_terr_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan qal'a bo'yicha operatsiyani tanlash"""
    query = update.callback_query
    await query.answer()

    terr_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        terr = await session.get(models.Territory, terr_id)
        if not terr:
            await query.edit_message_text("❌ Qal'a topilmadi.")
            return

        tg_user = update.effective_user
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        u_gold = user.gold if user else 0

        h_name = "Mustaqil"
        if terr.owner_house_id:
            h = await session.get(models.House, terr.owner_house_id)
            if h:
                h_name = f"{h.sigil or '🛡️'} {h.name}"

        text = (
            f"🏰 **QAL'A: {terr.name}** ({terr.castle_name})\n"
            f"👑 Xonadon: **{h_name}**\n"
            f"🗺️ Mintaqa: **{terr.region}**\n"
            f"💰 Sizdagi oltin: **{u_gold:,}** Oltin\n\n"
            f"Ushbu qal'aga qanday operatsiya uyushtirilsin?"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🕵️ Razvedka qilish (1,000💰)", callback_data=f"spy_do:scout:{terr.id}")],
            [InlineKeyboardButton("🔥 Sabotaj uyushtirish (3,000💰)", callback_data=f"spy_do:sabotage:{terr.id}")],
            [InlineKeyboardButton("🚪 Darvozalarni ochish (5,000💰)", callback_data=f"spy_do:open_gates:{terr.id}")],
            [InlineKeyboardButton("🔙 Qal'alar ro'yxati", callback_data="spy_pick_page:0")],
        ])
        try:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await query.edit_message_text(text, reply_markup=keyboard)


async def spy_execute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Josuslik operatsiyasini ijro etish"""
    query = update.callback_query
    await query.answer("Operatsiya bajarilmoqda...")

    parts = query.data.split(":")
    mission_type = parts[1]
    terr_id = int(parts[2])

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        success, report_text, _ = await crud.send_spy_mission(
            session=session,
            user_id=user.id,
            target_territory_id=terr_id,
            mission_type=mission_type,
            bot_app=context.application,
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Boshqa Qal'a", callback_data="spy_pick_page:0")],
            [InlineKeyboardButton("📜 Barcha hisobotlar", callback_data="spy_history")],
            [InlineKeyboardButton("🔙 Josuslik menyusi", callback_data="menu_espionage")],
        ])
        try:
            await query.edit_message_text(report_text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await query.edit_message_text(report_text, reply_markup=keyboard)


async def spy_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha josuslik hisobotlarini ko'rish"""
    query = update.callback_query
    await query.answer()

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
                t_name = r.target_territory.name if r.target_territory else f"Qal'a #{r.target_territory_id}"
                clean_snippet = (r.report_text or "").replace("*", "").replace("_", "").replace("`", "")[:120].strip()
                t_time = (r.created_at or datetime.utcnow()).strftime("%d.%m %H:%M")
                text += (
                    f"• **{r.mission_type.upper()}** ({t_name}) — {status_icon} ({t_time})\n"
                    f"{clean_snippet}...\n\n"
                )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Qal'aga josus yuborish", callback_data="spy_pick_page:0")],
            [InlineKeyboardButton("🔙 Josuslik menyusi", callback_data="menu_espionage")]
        ])
        try:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await query.edit_message_text(text, reply_markup=keyboard)


def register_espionage_handlers(app: Application):
    """Josuslik handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["spy", "espionage"], spy_menu_callback))
    app.add_handler(CallbackQueryHandler(spy_menu_callback, pattern="^menu_espionage$"))
    app.add_handler(CallbackQueryHandler(spy_pick_terr_callback, pattern="^spy_pick_(terr|page:\\d+)$"))
    app.add_handler(CallbackQueryHandler(spy_terr_detail_callback, pattern="^spy_terr:\\d+$"))
    app.add_handler(CallbackQueryHandler(spy_execute_callback, pattern="^spy_do:(scout|sabotage|open_gates):\\d+$"))
    app.add_handler(CallbackQueryHandler(spy_history_callback, pattern="^spy_history$"))
