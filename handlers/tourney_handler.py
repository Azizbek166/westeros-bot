import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from config import ADMIN_IDS, OWNER_ID
from sqlalchemy import select, desc

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    try:
        uid = int(user_id)
        return uid in [int(x) for x in ADMIN_IDS] or uid == int(OWNER_ID)
    except Exception:
        return False


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


async def tourney_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ritsarlar turniri va stavkalar asosiy menyusi"""
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

        tourney = await crud.get_active_tournament(session)
        if not tourney:
            # So'nggi yakunlangan turnir ma'lumotlarini olish
            last_res = await session.execute(
                select(models.Tournament)
                .where(models.Tournament.status == "completed")
                .order_by(desc(models.Tournament.id))
                .limit(1)
            )
            last_t = last_res.scalar_one_or_none()
            last_info = ""
            if last_t and last_t.winner_name:
                last_info = f"\n\n🎖️ **So'nggi Turnir Chempioni:** {last_t.winner_name}\n🏆 **Turnir:** {last_t.name} (Jamg'arma: {last_t.prize_pool:,}💰)"

            text = (
                "🏇🏆 **WESTEROS RITSARLAR ARENASI**\n\n"
                "Ayni paytda arena tinch. Navbatdagi ritsarlar turniri Qirol / Admin tomonidan tez orada e'lon qilinadi!"
                f"{last_info}"
            )
            buttons = []
            if is_admin(tg_user.id):
                buttons.append([InlineKeyboardButton("👑 Yangi Turnirni Boshlash (Admin)", callback_data="admin_tourney_start")])
            buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])
            kb = InlineKeyboardMarkup(buttons)
            if query:
                await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
            else:
                await update.effective_message.reply_text(text, reply_markup=kb, parse_mode="Markdown")
            return

        parts = tourney.participants or []
        parts_list = ""
        if parts:
            parts_list = "\n🤺 **Ishtirokchi Ritsarlar:**\n"
            for idx, p in enumerate(parts, 1):
                parts_list += f"{idx}. **{p.fighter_name}** — ⚡ {p.fighter_power} jang quvvati\n"
        else:
            parts_list = "\n_Hozircha jang maydoniga ritsarlar tushmagan._\n"

        user_is_entered = any(p.user_id == user.id for p in parts)
        status_label = "✅ Siz qatnashyapsiz" if user_is_entered else "❌ Qatnashmadingiz"

        text = (
            f"🏇🏆 **{tourney.name}**\n\n"
            f"Qirollikning eng dovyurak ritsarlari nayza va qilich jangi uchun arena maydoniga yig'ilmoqda!\n\n"
            f"💰 **Umumiy Jamg'arma:** **{tourney.prize_pool:,}** Oltin\n"
            f"🥇 1-O'rin g'olibi: **70%** jamg'arma + **100** Nufuz + **'Qirollik Chempioni'** unvoni\n"
            f"🥈 2-O'rin sohibi: **30%** jamg'arma + **50** Nufuz\n"
            f"🎰 Stavka yutug'i: **1.8x** koeffitsiyent\n"
            f"👤 Sizning holatingiz: **{status_label}**\n"
            f"💰 Oltiningiz: **{user.gold:,}** Oltin\n"
            f"{parts_list}"
        )

        buttons = []
        if not user_is_entered:
            buttons.append([InlineKeyboardButton("🤺 Turnirga kirish (2,000💰)", callback_data="tourney_enter_pick")])
        buttons.append([InlineKeyboardButton("🎰 Stavka tikish (1.8x)", callback_data="tourney_bet_pick")])
        buttons.append([InlineKeyboardButton("📜 Qoidalar va Shartlar", callback_data="tourney_rules")])

        if is_admin(tg_user.id):
            buttons.append([InlineKeyboardButton("🏁 Turnirni Yakunlash (Admin)", callback_data="admin_tourney_resolve")])

        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        keyboard = InlineKeyboardMarkup(buttons)
        await _safe_edit_or_reply(query, update, text, reply_markup=keyboard)


async def tourney_enter_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jangchi tanlash (O'zi yoki Bosh Sarkardasi)"""
    query = update.callback_query
    await query.answer()

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
        army = army_res.scalar_one_or_none()
        has_champ = bool(army and army.champion)

        buttons = [
            [InlineKeyboardButton("👤 O'zim (Ritsar unvoni bilan)", callback_data="tourney_do_enter:self")]
        ]
        if has_champ:
            buttons.append([InlineKeyboardButton("🌟 Bosh Sarkardamni tushirish (Yuqori quvvat)", callback_data="tourney_do_enter:champ")])

        buttons.append([InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")])

        text = (
            "🤺 **TURNIR MAYDONIGA KIM CHIQADI?**\n\n"
            "Kirish to'lovi: **2,000** Oltin (turnir jamg'armasiga qo'shiladi).\n\n"
            "• *O'zingiz:* Nufuzingiz va duellaringiz asosida quvvat beriladi (120-200).\n"
            "• *Bosh Sarkarda:* Jon Snow, Jaime Lannister kabi afsonaviy chempionlar eng yuqori quvvat (210-240) bilan jang qiladi!"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def tourney_do_enter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Turnirga ro'yxatdan o'tishni amalga oshirish"""
    query = update.callback_query
    await query.answer()

    use_champ = (query.data.split(":")[1] == "champ")
    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        ok, msg = await crud.enter_tournament(session, user.id, use_champion=use_champ)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]
        ])
        await query.edit_message_text(msg, reply_markup=keyboard, parse_mode="Markdown")


async def tourney_bet_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stavka uchun jangchini tanlash"""
    query = update.callback_query
    await query.answer()

    async with AsyncSessionLocal() as session:
        tourney = await crud.get_active_tournament(session)
        if not tourney or not tourney.participants:
            await query.edit_message_text(
                "❌ Hozircha turnirda ishtirokchi jangchilar yo'q. Avval jangchilar qo'shilishi kerak.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]])
            )
            return

        buttons = []
        for p in tourney.participants:
            buttons.append([InlineKeyboardButton(f"🤺 {p.fighter_name} ({p.fighter_power}⚡)", callback_data=f"tourney_bet_fighter:{p.id}")])

        buttons.append([InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")])
        text = (
            "🎰 **QAYSI RITSAR G'ALABASIGA STAVKA TIKASIZ?**\n\n"
            "Turnir g'olibini to'g'ri topsangiz, tikkan miqdoringiz **1.8 baravar** (1.8x) ko'paytirib qaytariladi!"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def tourney_bet_amount_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stavka miqdorini tanlash"""
    query = update.callback_query
    await query.answer()

    part_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        part = await session.get(models.TournamentParticipant, part_id)
        if not part:
            await query.edit_message_text("❌ Jangchi topilmadi.")
            return

        text = (
            f"💰 **STAVKA MIQDORINI TANLANG:**\n\n"
            f"Tanlangan ritsar: **{part.fighter_name}** (⚡ {part.fighter_power})\n"
            f"Agar ushbu jangchi turnir chempioni bo'lsa, yutug'ingiz 1.8x bo'ladi."
        )
        amounts = [500, 1000, 2500, 5000]
        buttons = []
        for amt in amounts:
            buttons.append([InlineKeyboardButton(f"💰 {amt:,} Oltin (Yutuq: {int(amt*1.8):,}💰)", callback_data=f"tourney_bet_do:{part_id}:{amt}")])

        buttons.append([InlineKeyboardButton("🔙 Jangchilar ro'yxati", callback_data="tourney_bet_pick")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def tourney_bet_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stavka tikishni tasdiqlash"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    part_id = int(parts[1])
    amt = int(parts[2])

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        ok, msg = await crud.place_tournament_bet(session, user.id, part_id, amt)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]
        ])
        await query.edit_message_text(msg, reply_markup=keyboard, parse_mode="Markdown")


async def tourney_rules_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Turnir qoidalari"""
    query = update.callback_query
    await query.answer()

    text = (
        "📜 **QIROL QO'LI TURNIRI QOIDALARI:**\n\n"
        "1. **Ishtirok:** Har bir o'yinchi 2,000 Oltin evaziga o'z ritsari yoki tayinlangan afsonaviy sarkardasi bilan ishtirok etishi mumkin.\n"
        "2. **Jang Format:** Nayza jangi (Jousting) va Qilich jangi (Sword Melee) bo'yicha ketma-ket saralash duellari o'tkaziladi.\n"
        "3. **G'oliblik:**\n"
        "• 🥇 1-O'rin: Jamg'armaning 70% ulushi + 100 Nufuz + 'Qirollik Chempioni' unvoni!\n"
        "• 🥈 2-O'rin: Jamg'armaning 30% ulushi + 50 Nufuz!\n"
        "4. **Stavkalar:** Har bir o'yinchi o'zi ishongan ritsarga 500 dan 5,000 Oltin stavka tikishi mumkin. Agar u g'olib chiqsa — 1.8x to'lanadi!"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def admin_tourney_resolve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin tomonidan turnirni hozir yakunlash"""
    query = update.callback_query
    await query.answer("Turnir hisoblanmoqda...")

    tg_user = update.effective_user
    if not is_admin(tg_user.id):
        await query.answer("❌ Faqat Administrator turnirni yakunlay oladi!", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        ok, report = await crud.resolve_tournament(session, bot_app=context.application)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 Yangi Turnir Boshlash", callback_data="admin_tourney_start")],
            [InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]
        ])
        await query.edit_message_text(report, reply_markup=keyboard, parse_mode="Markdown")


async def admin_tourney_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin tomonidan yangi turnirni boshlash"""
    query = update.callback_query
    await query.answer("Turnir e'lon qilinmoqda...")

    tg_user = update.effective_user
    if not is_admin(tg_user.id):
        await query.answer("❌ Faqat Administrator turnir boshlay oladi!", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        ok, res_msg = await crud.admin_start_tournament(session, bot_app=context.application)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏇 Turnir maydoniga o'tish", callback_data="menu_tourney")]
        ])
        await query.edit_message_text(res_msg, reply_markup=keyboard, parse_mode="Markdown")


def register_tourney_handlers(app: Application):
    """Turnir handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["tourney", "tournament"], tourney_menu_callback))
    app.add_handler(CallbackQueryHandler(tourney_menu_callback, pattern="^menu_tourney$"))
    app.add_handler(CallbackQueryHandler(tourney_enter_pick_callback, pattern="^tourney_enter_pick$"))
    app.add_handler(CallbackQueryHandler(tourney_do_enter_callback, pattern="^tourney_do_enter:(self|champ)$"))
    app.add_handler(CallbackQueryHandler(tourney_bet_pick_callback, pattern="^tourney_bet_pick$"))
    app.add_handler(CallbackQueryHandler(tourney_bet_amount_callback, pattern="^tourney_bet_fighter:\\d+$"))
    app.add_handler(CallbackQueryHandler(tourney_bet_do_callback, pattern="^tourney_bet_do:\\d+:\\d+$"))
    app.add_handler(CallbackQueryHandler(tourney_rules_callback, pattern="^tourney_rules$"))
    app.add_handler(CallbackQueryHandler(admin_tourney_resolve_callback, pattern="^admin_tourney_resolve$"))
    app.add_handler(CallbackQueryHandler(admin_tourney_start_callback, pattern="^admin_tourney_start$"))
