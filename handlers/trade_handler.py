import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from database import AsyncSessionLocal, crud, models
from config import escape_md

logger = logging.getLogger(__name__)

RESOURCE_LABELS = {
    "food": "🌾 Don (Oziq-ovqat)",
    "iron": "⛓️ Temir",
    "gold": "🪙 Oltin",
}

RESOURCE_SHORT = {
    "food": "🌾 Don",
    "iron": "⛓️ Temir",
    "gold": "🪙 Oltin",
}


async def show_trade_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadonlararo savdo bozori (Trade Hub)"""
    user_id = update.effective_user.id
    query = update.callback_query

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            msg = "❌ Avval /start bosing."
            if query:
                await query.answer()
                await query.edit_message_text(msg)
            else:
                await update.message.reply_text(msg)
            return

        house = user.house
        house_name = f"{house.emoji} {escape_md(house.name)}" if house else "Yo'q"

        active_trades = await crud.get_active_house_trades(session)
        my_trades = await crud.get_user_active_trades(session, user.id)

        text = (
            "⚖️ **XONADONLARARO SAVDO BIRJASI (BOZOR)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏰 Sizning Xonadoningiz: **{house_name}**\n"
            f"💰 Hamyoningiz: **{(user.gold or 0):,}**🪙 | **{(user.food or 0):,}**🌾 | **{(user.iron or 0):,}**⛓️\n\n"
            "Bu yerda buyuk xonadonlar o'zaro resurs ayirboshlaydilar.\n"
            "Savdo muvaffaqiyatli yakunlanganda har ikkala xonadonga **+10 Prestige** beriladi! 👑\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        if not house:
            text += "⚠️ _Savdoda ishtirok etish uchun biror xonadonga a'zo bo'lishingiz kerak._\n\n"

        keyboard = []

        # Boshqa xonadonlarning ochiq takliflari
        other_trades = [t for t in active_trades if not house or t.seller_house_id != house.id]
        if other_trades:
            text += "📜 **BOZORDAGI FAOL TAKLIFLAR:**\n"
            for t in other_trades[:10]:
                off_name = RESOURCE_SHORT.get(t.offer_resource, t.offer_resource)
                req_name = RESOURCE_SHORT.get(t.request_resource, t.request_resource)
                s_house = t.seller_house.name if t.seller_house else "Xonadon"
                s_emoji = t.seller_house.emoji if t.seller_house else "🏰"
                text += (
                    f"• **Lot #{t.id}** ({s_emoji} {escape_md(s_house)}):\n"
                    f"  🎁 Beradi: **{t.offer_amount:,}** {off_name} ➡️ So'raydi: **{t.request_amount:,}** {req_name}\n"
                )
                if house:
                    keyboard.append([
                        InlineKeyboardButton(
                            f"🤝 #{t.id} Xarid: {t.request_amount:,} {req_name} to'lab, {t.offer_amount:,} {off_name} olish",
                            callback_data=f"trade_buy:{t.id}"
                        )
                    ])
            text += "\n"
        else:
            text += "📭 _Hozircha boshqa xonadonlardan faol savdo takliflari yo'q._\n\n"

        # Foydalanuvchining o'z takliflari
        if my_trades:
            text += "📋 **SIZNING SAVDOGA QO'YGAN LOTLARINGIZ:**\n"
            for mt in my_trades:
                m_off = RESOURCE_SHORT.get(mt.offer_resource, mt.offer_resource)
                m_req = RESOURCE_SHORT.get(mt.request_resource, mt.request_resource)
                text += f"• **Lot #{mt.id}**: {mt.offer_amount:,} {m_off} ➡️ {mt.request_amount:,} {m_req}\n"
                keyboard.append([
                    InlineKeyboardButton(f"❌ Bekor qilish #{mt.id} (Resursni qaytarish)", callback_data=f"trade_cancel:{mt.id}")
                ])
            text += "\n"

        action_row = []
        if house:
            action_row.append(InlineKeyboardButton("➕ E'lon Joylashtirish", callback_data="trade_create_menu"))
        action_row.append(InlineKeyboardButton("🔄 Yangilash", callback_data="menu_trade"))
        keyboard.append(action_row)

        keyboard.append([InlineKeyboardButton("🔙 Bosh Menyu", callback_data="menu_main")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        if query:
            await query.answer()
            try:
                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
            except Exception:
                await query.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def trade_create_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tezkor e'lon joylashtirish menyusi"""
    query = update.callback_query
    await query.answer()

    text = (
        "➕ **YANGI SAVDO LOTI JOYLASHTIRISH**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Taklif etgan resursingiz xavfsiz depozitga (escrow) olinadi va boshqa xonadon a'zosi xarid qilganda darhol hisoblarga o'tkaziladi.\n\n"
        "⚡ **Tezkor shablonlardan birini tanlang yoki buyruq yozing:**\n\n"
        "Qo'lda kiritish formati:\n"
        "`/createtrade <beriladigan> <miqdor> <so'raladigan> <miqdor>`\n"
        "Masalan:\n"
        "• `/createtrade food 500 gold 200`\n"
        "• `/createtrade iron 200 gold 200`\n"
        "• `/createtrade gold 300 food 1000`\n"
    )

    keyboard = [
        [
            InlineKeyboardButton("🌾 500 Don ➡️ 🪙 250 Oltin", callback_data="trade_add:food:500:gold:250"),
            InlineKeyboardButton("🌾 1000 Don ➡️ 🪙 500 Oltin", callback_data="trade_add:food:1000:gold:500")
        ],
        [
            InlineKeyboardButton("⛓️ 100 Temir ➡️ 🪙 100 Oltin", callback_data="trade_add:iron:100:gold:100"),
            InlineKeyboardButton("⛓️ 300 Temir ➡️ 🪙 300 Oltin", callback_data="trade_add:iron:300:gold:300")
        ],
        [
            InlineKeyboardButton("🪙 200 Oltin ➡️ 🌾 500 Don", callback_data="trade_add:gold:200:food:500"),
            InlineKeyboardButton("🪙 100 Oltin ➡️ ⛓️ 120 Temir", callback_data="trade_add:gold:100:iron:120")
        ],
        [
            InlineKeyboardButton("🔙 Bozorga Qaytish", callback_data="menu_trade")
        ]
    ]

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def trade_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tezkor shablon orqali savdo yaratish"""
    query = update.callback_query
    user_id = query.from_user.id

    parts = query.data.split(":")
    if len(parts) != 5:
        await query.answer("Noto'g'ri buyruq!", show_alert=True)
        return

    _, offer_res, offer_amt_s, req_res, req_amt_s = parts
    try:
        offer_amt = int(offer_amt_s)
        req_amt = int(req_amt_s)
    except ValueError:
        await query.answer("Noto'g'ri miqdor!", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        ok, msg, trade = await crud.create_house_trade(session, user_id, offer_res, offer_amt, req_res, req_amt)
        await query.answer(msg[:100], show_alert=True)

    await show_trade_hub(update, context)


async def trade_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Taklifni sotib olish"""
    query = update.callback_query
    user_id = query.from_user.id

    parts = query.data.split(":")
    if len(parts) != 2:
        await query.answer("Xatolik!", show_alert=True)
        return

    try:
        trade_id = int(parts[1])
    except ValueError:
        await query.answer("Noto'g'ri ID!", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.fulfill_house_trade(session, user_id, trade_id)
        await query.answer(msg[:150], show_alert=True)

    await show_trade_hub(update, context)


async def trade_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'z taklifini bekor qilish"""
    query = update.callback_query
    user_id = query.from_user.id

    parts = query.data.split(":")
    if len(parts) != 2:
        await query.answer("Xatolik!", show_alert=True)
        return

    try:
        trade_id = int(parts[1])
    except ValueError:
        await query.answer("Noto'g'ri ID!", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.cancel_house_trade(session, user_id, trade_id)
        await query.answer(msg[:100], show_alert=True)

    await show_trade_hub(update, context)


async def create_trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/createtrade <beriladigan> <miqdor> <so'raladigan> <miqdor>"""
    user_id = update.effective_user.id
    args = context.args

    if not args or len(args) < 4:
        await update.message.reply_text(
            "ℹ️ **Bozorda e'lon joylashtirish tartibi:**\n"
            "`/createtrade <beriladigan> <miqdor> <so'raladigan> <miqdor>`\n\n"
            "Resurslar: `food` (don), `iron` (temir), `gold` (oltin)\n"
            "Masalan:\n"
            "`/createtrade food 500 gold 200`\n"
            "`/createtrade iron 150 gold 150`",
            parse_mode="Markdown"
        )
        return

    offer_res = args[0].lower()
    try:
        offer_amt = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Taklif miqdori son bo'lishi kerak!")
        return

    req_res = args[2].lower()
    try:
        req_amt = int(args[3])
    except ValueError:
        await update.message.reply_text("❌ So'ralayotgan miqdor son bo'lishi kerak!")
        return

    async with AsyncSessionLocal() as session:
        ok, msg, trade = await crud.create_house_trade(session, user_id, offer_res, offer_amt, req_res, req_amt)
        await update.message.reply_text(msg, parse_mode="Markdown")
        if ok:
            await show_trade_hub(update, context)


def register_trade_handlers(app):
    app.add_handler(CommandHandler("trade", show_trade_hub))
    app.add_handler(CommandHandler("bozor", show_trade_hub))
    app.add_handler(CommandHandler("createtrade", create_trade_command))
    app.add_handler(CallbackQueryHandler(show_trade_hub, pattern="^menu_trade$"))
    app.add_handler(CallbackQueryHandler(trade_create_menu_callback, pattern="^trade_create_menu$"))
    app.add_handler(CallbackQueryHandler(trade_add_callback, pattern="^trade_add:"))
    app.add_handler(CallbackQueryHandler(trade_buy_callback, pattern="^trade_buy:"))
    app.add_handler(CallbackQueryHandler(trade_cancel_callback, pattern="^trade_cancel:"))
