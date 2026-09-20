import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def caravan_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Savdo karvonlari asosiy menyusi"""
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

        my_caravans = await crud.get_active_trade_caravans(session, user_id=user.id)
        my_status = ""
        if my_caravans:
            my_status = "\n🐪 **Sizning yo'ldagi karvonlaringiz:**\n"
            now = datetime.utcnow()
            for c in my_caravans:
                rem_sec = max(0, int((c.arrival_time - now).total_seconds()))
                rem_min = rem_sec // 60
                rem_s = rem_sec % 60
                d_name = c.destination_territory.name if c.destination_territory else "Savdo shahri"
                my_status += f"• #{c.id} 📦 {c.resource_amount:,} {c.resource_type.capitalize()} ➔ {d_name} (⏳ {rem_min}d {rem_s}s qoldi)\n"

        text = (
            "🐪💰 **WESTEROS SAVDO KARVONLARI VA PISTIRMALAR**\n\n"
            "Savdogarlar boylik orttirish uchun shahar va qal'alararo ulkan karvonlar yuboradilar. Ammo yo'llar xavfli — qaroqchilar va dushman xonadonlar har qadamda pistirmada kutib turadi!\n\n"
            f"🌾 Oziq-ovqat: **{user.food:,}** | ⛏️ Temir: **{user.iron:,}** | 💰 Oltin: **{user.gold:,}**\n\n"
            "📜 **Karvon tizimi imkoniyatlari:**\n"
            "• 5,000 resurs ➔ **+2,500** Oltin (3 daqiqa)\n"
            "• 10,000 resurs ➔ **+5,500** Oltin (3 daqiqa)\n"
            "• 20,000 resurs ➔ **+12,000** Oltin (3 daqiqa)\n\n"
            "⚔️ **Qaroqchilik (Raid):** Yo'ldagi dushman karvonlariga hujum qilib, ularning 70% yukini va 1,000 Oltin o'ljani tortib olishingiz mumkin!"
            f"{my_status}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🐪 Yangi Karvon Jo'natish", callback_data="caravan_wizard_res")],
            [InlineKeyboardButton("⚔️ Westeros Yo'llari (Pistirma / Raid)", callback_data="caravan_routes")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ])

        if query:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.effective_message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def caravan_wizard_res_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """1-bosqich: Resurs turini tanlash"""
    query = update.callback_query
    await query.answer()

    text = (
        "🐪📦 **1-BOSQICH: QANDAY YUK YUBORASIZ?**\n\n"
        "Eksport qilish uchun resurs turini tanlang:"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌾 Oziq-ovqat karvoni", callback_data="caravan_step_amt:food")],
        [InlineKeyboardButton("⛏️ Temir karvoni", callback_data="caravan_step_amt:iron")],
        [InlineKeyboardButton("🔙 Karvon menyusi", callback_data="menu_caravan")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def caravan_wizard_amt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """2-bosqich: Yuk hajmini tanlash"""
    query = update.callback_query
    await query.answer()

    res_type = query.data.split(":")[1]
    text = (
        f"🐪📦 **2-BOSQICH: {res_type.upper()} YUK MIQDORI:**\n\n"
        "Qancha miqdorda yuk eksport qilmoqchisiz?"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 5,000 yuk (Kutilayotgan foyda: +2,500💰)", callback_data=f"caravan_step_dest:{res_type}:5000")],
        [InlineKeyboardButton("📦 10,000 yuk (Kutilayotgan foyda: +5,500💰)", callback_data=f"caravan_step_dest:{res_type}:10000")],
        [InlineKeyboardButton("📦 20,000 yuk (Kutilayotgan foyda: +12,000💰)", callback_data=f"caravan_step_dest:{res_type}:20000")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="caravan_wizard_res")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def caravan_wizard_dest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """3-bosqich: Manzil savdo portini tanlash"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    res_type = parts[1]
    amount = parts[2]

    trade_hubs = [
        {"id": 1, "name": "King's Landing (Poytaxt Porti)"},
        {"id": 7, "name": "Oldtown (Yulduzli Savdo Maydoni)"},
        {"id": 13, "name": "Lannisport (Oltin Bozor)"},
        {"id": 19, "name": "Gulltown (Vodiy Bandargohi)"},
        {"id": 4, "name": "White Harbor (Shimol Savdo Qal'asi)"},
    ]

    buttons = []
    for hub in trade_hubs:
        buttons.append([InlineKeyboardButton(f"⚓ {hub['name']}", callback_data=f"caravan_step_sec:{res_type}:{amount}:{hub['id']}")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"caravan_step_amt:{res_type}")])

    text = (
        "🐪⚓ **3-BOSQICH: MANZIL SAVDO PORTINI TANLANG:**\n\n"
        "Karvoningiz qaysi yirik savdo markaziga qatnaydi?"
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def caravan_wizard_security_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """4-bosqich: Soqchilar himoyasini belgilash"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    res_type = parts[1]
    amount = parts[2]
    dest_id = parts[3]

    text = (
        "🛡️🐎 **4-BOSQICH: SOQCHILAR TARKIBINI TANLANG:**\n\n"
        "Soqchilar karvonni dushman qaroqchilaridan himoya qiladi. Agar soqchilar kam bo'lsa, dushmanlar karvonni talab ketishi osonlashadi!\n\n"
        "Askarlar karvon manzilga xavfsiz yetgach armiyangiz safiga qaytadi."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ Yengil soqchi (20 Otliq, 30 Piyoda)", callback_data=f"caravan_launch:{res_type}:{amount}:{dest_id}:20:30")],
        [InlineKeyboardButton("🛡️🛡️ Ishonchli gvardiya (50 Otliq, 80 Piyoda)", callback_data=f"caravan_launch:{res_type}:{amount}:{dest_id}:50:80")],
        [InlineKeyboardButton("🛡️🛡️🛡️ Zirhli eskort (100 Otliq, 150 Piyoda)", callback_data=f"caravan_launch:{res_type}:{amount}:{dest_id}:100:150")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data=f"caravan_step_dest:{res_type}:{amount}")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def caravan_launch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Karvonni yo'lga chiqarish"""
    query = update.callback_query
    await query.answer("Karvon shakllantirilmoqda...")

    parts = query.data.split(":")
    res_type = parts[1]
    amount = int(parts[2])
    dest_id = int(parts[3])
    esc_cav = int(parts[4])
    esc_inf = int(parts[5])

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        origin_terr_id = 1
        if user.house_id:
            h_terr = await session.execute(
                select(models.Territory).where(models.Territory.owner_house_id == user.house_id).limit(1)
            )
            found_t = h_terr.scalar_one_or_none()
            if found_t:
                origin_terr_id = found_t.id

        ok, msg = await crud.dispatch_trade_caravan(
            session=session,
            user_id=user.id,
            origin_territory_id=origin_terr_id,
            destination_territory_id=dest_id,
            resource_type=res_type,
            amount=amount,
            escort_cav=esc_cav,
            escort_inf=esc_inf,
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🐪 Karvonlar menyusi", callback_data="menu_caravan")]
        ])
        await query.edit_message_text(msg, reply_markup=keyboard, parse_mode="Markdown")


async def caravan_routes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yo'ldagi raqib karvonlarini ko'rish va pistirma uyushtirish"""
    query = update.callback_query
    await query.answer()

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        caravans = await crud.get_active_trade_caravans(session)
        rival_caravans = [c for c in caravans if c.owner_user_id != user.id and c.owner_house_id != user.house_id]

        if not rival_caravans:
            text = (
                "🛣️ **WESTEROS SAVDO YO'LLARI:**\n\n"
                "Ayni paytda yo'llarda dushman savdo karvonlari ko'rinmayapti.\n"
                "Savdogarlar qal'alarida yangi yuk ortmoqda. Birozdan so'ng yana tekshiring!"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Yangilash", callback_data="caravan_routes")],
                [InlineKeyboardButton("🔙 Karvon menyusi", callback_data="menu_caravan")],
            ])
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            return

        now = datetime.utcnow()
        text = "🛣️⚔️ **YO'LDAGI RAQIB SAVDO KARVONLARI:**\n\n"
        buttons = []
        for c in rival_caravans:
            rem_sec = max(0, int((c.arrival_time - now).total_seconds()))
            h_name = c.owner_house.name if c.owner_house else "Noma'lum xonadon"
            dest_name = c.destination_territory.name if c.destination_territory else "Port"
            text += (
                f"🐪 **Karvon #{c.id}** ({h_name})\n"
                f"📦 Yuk: **{c.resource_amount:,}** {c.resource_type.capitalize()} ➔ {dest_name}\n"
                f"🛡️ Soqchilar: {c.escort_cavalry} Otliq, {c.escort_infantry} Piyoda\n"
                f"⏳ Qolgan vaqt: {rem_sec // 60}m {rem_sec % 60}s\n\n"
            )
            buttons.append([InlineKeyboardButton(f"⚔️ Karvon #{c.id} ga Pistirma", callback_data=f"caravan_raid_pick:{c.id}")])

        buttons.append([InlineKeyboardButton("🔄 Yangilash", callback_data="caravan_routes")])
        buttons.append([InlineKeyboardButton("🔙 Karvon menyusi", callback_data="menu_caravan")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def caravan_raid_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pistirma uchun hujumchi kuchlarni tanlash"""
    query = update.callback_query
    await query.answer()

    caravan_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        caravan = await session.get(models.TradeCaravan, caravan_id)
        if not caravan or caravan.status != "moving":
            await query.edit_message_text("❌ Ushbu karvon allaqachon manzilga yetgan yoki talangan.")
            return

        text = (
            f"⚔️💥 **PISTIRMA QUROLI VA ASKARLARINI TANLANG:**\n\n"
            f"Maqsad: Karvon #{caravan.id} ({caravan.resource_amount:,} {caravan.resource_type.capitalize()})\n"
            f"Himoyachilar: {caravan.escort_cavalry} Otliq, {caravan.escort_infantry} Piyoda\n\n"
            f"Qaysi otryad bilan pistirmadan tashlanasiz?"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🐎 Tezkor chopqun (30 Otliq, 30 Piyoda)", callback_data=f"caravan_raid_do:{caravan_id}:30:30")],
            [InlineKeyboardButton("⚔️ Katta qaroqchilar to'dasi (80 Otliq, 80 Piyoda)", callback_data=f"caravan_raid_do:{caravan_id}:80:80")],
            [InlineKeyboardButton("🔙 Qaytish", callback_data="caravan_routes")],
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def caravan_raid_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pistirma jangini amalga oshirish"""
    query = update.callback_query
    await query.answer("Pistirma boshlandi...")

    parts = query.data.split(":")
    caravan_id = int(parts[1])
    inf = int(parts[2])
    cav = int(parts[3])

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        ok, msg, _ = await crud.raid_trade_caravan(
            session=session,
            user_id=user.id,
            caravan_id=caravan_id,
            raid_inf=inf,
            raid_cav=cav,
            bot_app=context.application,
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛣️ Westeros Yo'llari", callback_data="caravan_routes")],
            [InlineKeyboardButton("🔙 Karvon menyusi", callback_data="menu_caravan")],
        ])
        await query.edit_message_text(msg, reply_markup=keyboard, parse_mode="Markdown")


def register_caravan_handlers(app: Application):
    """Savdo karvonlari handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["caravan", "caravans"], caravan_menu_callback))
    app.add_handler(CallbackQueryHandler(caravan_menu_callback, pattern="^menu_caravan$"))
    app.add_handler(CallbackQueryHandler(caravan_wizard_res_callback, pattern="^caravan_wizard_res$"))
    app.add_handler(CallbackQueryHandler(caravan_wizard_amt_callback, pattern="^caravan_step_amt:(food|iron)$"))
    app.add_handler(CallbackQueryHandler(caravan_wizard_dest_callback, pattern="^caravan_step_dest:(food|iron):\\d+$"))
    app.add_handler(CallbackQueryHandler(caravan_wizard_security_callback, pattern="^caravan_step_sec:(food|iron):\\d+:\\d+$"))
    app.add_handler(CallbackQueryHandler(caravan_launch_callback, pattern="^caravan_launch:(food|iron):\\d+:\\d+:\\d+:\\d+$"))
    app.add_handler(CallbackQueryHandler(caravan_routes_callback, pattern="^caravan_routes$"))
    app.add_handler(CallbackQueryHandler(caravan_raid_pick_callback, pattern="^caravan_raid_pick:\\d+$"))
    app.add_handler(CallbackQueryHandler(caravan_raid_do_callback, pattern="^caravan_raid_do:\\d+:\\d+:\\d+$"))
