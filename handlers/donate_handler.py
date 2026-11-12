from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, LabeledPrice, PreCheckoutQuery
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
    ContextTypes,
)
from database import AsyncSessionLocal, crud, models
from config import (
    DONATE_CARD_NUMBER,
    DONATE_CARD_HOLDER,
    DONATE_TIERS,
    OWNER_ID,
    ADMIN_IDS,
    escape_md,
    get_miniapp_url,
)
from core.cosmetics import COSMETICS_CATALOG, get_cosmetic_item, record_payment_transaction, grant_cosmetic_item
from keyboards.menus import back_to_main_keyboard


def is_admin(user_id: int) -> bool:
    try:
        uid = int(user_id)
        return uid in [int(x) for x in ADMIN_IDS] or uid == int(OWNER_ID)
    except Exception:
        return False


TROOP_RATES = {
    "infantry": {"name": "Oddiy askar", "rate": 1, "icon": "🗡️"},
    "archers": {"name": "Kamonchi", "rate": 2, "icon": "🏹"},
    "cavalry": {"name": "Otliq", "rate": 2, "icon": "🐎"},
    "spearmen": {"name": "Nayzachi", "rate": 2, "icon": "🛡️"},
}


def calc_troops(troop_type: str, amount_uzs: int) -> int:
    rate = TROOP_RATES.get(troop_type, {}).get("rate", 1)
    if rate <= 0:
        return 0
    return amount_uzs // rate


def donate_menu_keyboard() -> InlineKeyboardMarkup:
    """VIP to'plamlar va Kosmetika do'koni klaviaturasi"""
    buttons = [
        [
            InlineKeyboardButton(
                "📱 Telegram Mini App Kosmetika Do'koni 💎",
                web_app=WebAppInfo(url=get_miniapp_url("donate"))
            )
        ],
        [
            InlineKeyboardButton("👑 Noble VIP (30 kun) — 15,000 so'm / 75 ⭐", callback_data="donate_pick:vip_noble"),
        ],
        [
            InlineKeyboardButton("🎁 Starter Pack (Boshlang'ich) — 5,000 so'm / 25 ⭐", callback_data="donate_pick:starter_pack"),
        ],
        [
            InlineKeyboardButton("⚖️ Halol O'yin: Qo'shin Sotib Olish Haqida", callback_data="donate_troops_menu"),
        ],
        [
            InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")
        ]
    ]
    return InlineKeyboardMarkup(buttons)


async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/donate, /vip, /shop buyrug'i"""
    text = (
        "💎 **VESTEROS KOSMETIKA & QULAYLIKLAR DO'KONI**\n\n"
        "Hurmatli Lord! O'yinimizda **100% Halol Balans** amal qiladi: pullik buyumlar jangda hech qanday kuch, armiya yoki resurs ustunligi bermaydi!\n\n"
        "🛍️ **Do'konda mavjud:**\n"
        "• 👑 **Noble VIP:** 1-bosishda soliq yig'ish, profilga jonli video qo'yish, zarhal nishon.\n"
        "• 🎁 **Starter Pack:** Eksklyuziv po'lat ramka + unvon + 7 kunlik VIP.\n"
        "• 🏰 **Qal'a Skinlari:** Muz Qasri, Valiriya Qora Bazalti, Oltin Saroy.\n"
        "• 🐉 **Ajdarlar:** Qora Soyalar, Qonli Qizil, Zumrad va Oltin ajdar.\n"
        "• ⛓️ **Profil Ramkalari & Unvonlar:** Yetti Qirollikda ajralib turing!\n\n"
        "⭐️ **To'lov usullari:** Telegram Stars (rasmiy) yoki O'zbekiston bank kartalari.\n\n"
        "👇 *Quyidagi tugmalar orqali tanlang yoki Mini Appni oching:*"
    )
    if update.message:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=donate_menu_keyboard()
        )


async def donate_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_donate callback query"""
    query = update.callback_query
    await query.answer()

    text = (
        "💎 **VESTEROS KOSMETIKA & QULAYLIKLAR DO'KONI**\n\n"
        "Hurmatli Lord! O'yinimizda **100% Halol Balans** amal qiladi: pullik buyumlar jangda hech qanday kuch, armiya yoki resurs ustunligi bermaydi!\n\n"
        "🛍️ **Do'konda mavjud:**\n"
        "• 👑 **Noble VIP:** 1-bosishda soliq yig'ish, profilga jonli video qo'yish, zarhal nishon.\n"
        "• 🎁 **Starter Pack:** Eksklyuziv po'lat ramka + unvon + 7 kunlik VIP.\n"
        "• 🏰 **Qal'a Skinlari:** Muz Qasri, Valiriya Qora Bazalti, Oltin Saroy.\n"
        "• 🐉 **Ajdarlar:** Qora Soyalar, Qonli Qizil, Zumrad va Oltin ajdar.\n"
        "• ⛓️ **Profil Ramkalari & Unvonlar:** Yetti Qirollikda ajralib turing!\n\n"
        "⭐️ **To'lov usullari:** Telegram Stars (rasmiy) yoki O'zbekiston bank kartalari.\n\n"
        "👇 *Quyidagi tugmalar orqali tanlang yoki Mini Appni oching:*"
    )
    try:
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=donate_menu_keyboard()
        )
    except Exception:
        await query.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=donate_menu_keyboard()
        )


async def donate_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan to'plam tafsilotlarini va karta raqamini ko'rsatish"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":", 1)
    if len(parts) < 2:
        return

    tier_id = parts[1]
    tier = DONATE_TIERS.get(tier_id)
    if not tier:
        await query.answer("To'plam topilmadi!", show_alert=True)
        return

    text = (
        f"💎 **{tier['name'].upper()}**\n"
        f"_{tier['subtitle']}_\n\n"
        f"📦 **To'plam tarkibi va bonuslar:**\n"
        f"{tier['description']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💳 **TO'LOV REKVIZITLARI:**\n"
        f"• Karta raqami: `{DONATE_CARD_NUMBER}`\n"
        f"• Karta egasi: *{escape_md(DONATE_CARD_HOLDER)}*\n"
        f"• To'lov summasi: *{tier['price_label']}*\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 **QANDAY TO'LANADI?**\n"
        f"1. Bank ilovangizda (Click, Payme, Uzum va h.k.) yuqoridagi kartaga **{tier['price_label']}** o'tkazing.\n"
        f"2. To'lov chekini rasm (screenshot) qilib saqlang.\n"
        f"3. Pastdagi **«📸 To'lov chekini yuborish»** tugmasini bosing va chekni botga jo'nating!\n"
    )

    try:
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=donate_tier_keyboard(tier_id)
        )
    except Exception:
        await query.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=donate_tier_keyboard(tier_id)
        )


async def donate_troops_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'shin sotib olish — Pay-to-win to'xtatilgani haqida tushuntirish"""
    query = update.callback_query
    await query.answer()

    text = (
        "⚖️ **HALOL VA ADOLATLI BALANS: PAY-TO-WIN YO'Q!**\n\n"
        "Hurmatli Lord! O'yinda raqobatbardoshlik, sharaf va tenglikni ta'minlash maqsadida "
        "real pul evaziga askarlar, jang quvvati yoki resurslarni to'g'ridan-to'g'ri sotib olish "
        "butunlay bekor qilindi.\n\n"
        "🛡️ **Nima uchun?**\n"
        "• Har bir g'alaba o'yinchining shaxsiy aql-zakovati va taktikasiga bog'liq bo'lishi kerak.\n"
        "• Yangi va eski o'yinchilar o'rtasida sun'iy moddiy tafovut bo'lmasligi kafolatlanadi.\n\n"
        "🎁 **Do'konda nima bor?**\n"
        "Faqat go'zal qal'a va ajdar ko'rinishlari, faxriy unvonlar, ramkalar va "
        "o'yin qulayliklari (Noble VIP) mavjud!\n\n"
        "Barcha askarlarni Qal'angizdagi mashg'ulot maydonida sharaf bilan tayyorlang!"
    )
    buttons = [
        [
            InlineKeyboardButton(
                "📱 Mini App Do'konini Ochish 💎",
                web_app=WebAppInfo(url=get_miniapp_url("donate"))
            )
        ],
        [InlineKeyboardButton("👑 Noble VIP & To'plamlar", callback_data="menu_donate")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ]
    try:
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception:
        await query.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )


async def donate_troop_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan qo'shin turi uchun summa tanlash paneli"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":", 1)
    if len(parts) < 2:
        return

    troop_type = parts[1]
    t_info = TROOP_RATES.get(troop_type)
    if not t_info:
        await query.answer("Qo'shin turi topilmadi!", show_alert=True)
        return

    text = (
        f"⚔️ **{t_info['icon']} {t_info['name'].upper()} SOTIB OLISH**\n\n"
        f"💵 Narx: **{t_info['rate']} so'm = 1 ta {t_info['name']}**\n\n"
        f"Kerakli to'lov summasini tanlang yoki o'zingiz kiriting:"
    )
    try:
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=donate_troop_amount_keyboard(troop_type)
        )
    except Exception:
        await query.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=donate_troop_amount_keyboard(troop_type)
        )


async def donate_troop_amt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan summa bo'yicha to'lov tafsilotlari va karta rekvizitlari"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    troop_type = parts[1]
    try:
        amount = int(parts[2])
    except ValueError:
        return

    t_info = TROOP_RATES.get(troop_type)
    if not t_info:
        return

    count = calc_troops(troop_type, amount)

    text = (
        f"⚔️ **QO'SHIN SOTIB OLISH — TO'LOV**\n\n"
        f"👤 Tanlangan qo'shin: {t_info['icon']} **{t_info['name']}**\n"
        f"💰 To'lov summasi: **{amount:,} so'm**\n"
        f"🛡️ Beriladigan qo'shin soni: **{count:,} ta {t_info['name']}**\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💳 **TO'LOV REKVIZITLARI:**\n"
        f"• Karta raqami: `{DONATE_CARD_NUMBER}`\n"
        f"• Karta egasi: *{escape_md(DONATE_CARD_HOLDER)}*\n"
        f"• To'lov summasi: *{amount:,} so'm*\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 **QANDAY TO'LANADI?**\n"
        f"1. Bank ilovangizda (Click, Payme, Uzum va h.k.) yuqoridagi kartaga **{amount:,} so'm** o'tkazing.\n"
        f"2. To'lov chekini rasm (screenshot) qilib saqlang.\n"
        f"3. Pastdagi **«📸 To'lov chekini yuborish»** tugmasini bosing va chekni botga jo'nating!\n"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 To'lov chekini yuborish", callback_data=f"donate_troop_submit:{troop_type}:{amount}")],
        [InlineKeyboardButton("🔙 Boshqa summa tanlash", callback_data=f"donate_troop_type:{troop_type}")],
        [InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main")]
    ])

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def donate_troop_custom_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'shin uchun erkin summa kiritish so'rovi"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":", 1)
    if len(parts) < 2:
        return

    troop_type = parts[1]
    t_info = TROOP_RATES.get(troop_type)
    if not t_info:
        return

    context.user_data["awaiting_donate_troop_custom"] = troop_type

    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"donate_troop_type:{troop_type}")]
    ])

    text = (
        f"✍️ **SUMMANI KIRITING**\n\n"
        f"Qancha so'mga {t_info['icon']} **{t_info['name']}** sotib olmoqchisiz?\n"
        f"*(Kurs: {t_info['rate']} so'm = 1 ta)*\n\n"
        f"Iltimos, to'lov qilmoqchi bo'lgan summani faqat raqamlar bilan yozing (Masalan: `50000` yoki `120000`)."
    )

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=cancel_kb)
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=cancel_kb)


async def handle_donate_troop_amount_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi qo'lda kiritgan to'lov summasini qabul qilish"""
    troop_type = context.user_data.pop("awaiting_donate_troop_custom", None)
    if not troop_type or not update.message or not update.message.text:
        return

    text = update.message.text.strip().replace(" ", "").replace(",", "").replace(".", "")
    if not text.isdigit():
        await update.message.reply_text(
            "⚠️ Iltimos, faqat raqam kiriting (masalan: `50000` yoki `100000`).",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_donate_troop_custom"] = troop_type
        return

    amount = int(text)
    if amount < 1000:
        await update.message.reply_text(
            "⚠️ Minimal to'lov summasi — 1,000 so'm. Iltimos, kattaroq summa kiriting.",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_donate_troop_custom"] = troop_type
        return

    t_info = TROOP_RATES.get(troop_type, {"name": "Askar", "rate": 1, "icon": "🗡️"})
    count = calc_troops(troop_type, amount)

    msg_text = (
        f"⚔️ **QO'SHIN SOTIB OLISH — TO'LOV**\n\n"
        f"👤 Tanlangan qo'shin: {t_info['icon']} **{t_info['name']}**\n"
        f"💰 To'lov summasi: **{amount:,} so'm**\n"
        f"🛡️ Beriladigan qo'shin soni: **{count:,} ta {t_info['name']}**\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💳 **TO'LOV REKVIZITLARI:**\n"
        f"• Karta raqami: `{DONATE_CARD_NUMBER}`\n"
        f"• Karta egasi: *{escape_md(DONATE_CARD_HOLDER)}*\n"
        f"• To'lov summasi: *{amount:,} so'm*\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 **QANDAY TO'LANADI?**\n"
        f"1. Bank ilovangizda (Click, Payme, Uzum va h.k.) yuqoridagi kartaga **{amount:,} so'm** o'tkazing.\n"
        f"2. To'lov chekini rasm (screenshot) qilib saqlang.\n"
        f"3. Pastdagi **«📸 To'lov chekini yuborish»** tugmasini bosing va chekni botga jo'nating!\n"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 To'lov chekini yuborish", callback_data=f"donate_troop_submit:{troop_type}:{amount}")],
        [InlineKeyboardButton("🔙 Boshqa summa tanlash", callback_data=f"donate_troop_type:{troop_type}")],
        [InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main")]
    ])

    await update.message.reply_text(msg_text, parse_mode="Markdown", reply_markup=kb)


async def donate_troop_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'shin uchun chek yuborish bosqichini boshlash"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    troop_type = parts[1]
    try:
        amount = int(parts[2])
    except ValueError:
        return

    t_info = TROOP_RATES.get(troop_type)
    if not t_info:
        return

    count = calc_troops(troop_type, amount)

    context.user_data["awaiting_receipt_is_troops"] = True
    context.user_data["donate_troop_type"] = troop_type
    context.user_data["donate_troop_amount"] = amount
    context.user_data["donate_troop_count"] = count

    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="donate_cancel_receipt")]
    ])

    prompt_text = (
        f"📸 **TO'LOV CHEKINI YUBORING**\n\n"
        f"Tanlangan qo'shin: {t_info['icon']} **{count:,} ta {t_info['name']}**\n"
        f"To'lov summasi: **{amount:,} so'm**\n"
        f"Karta: `{DONATE_CARD_NUMBER}` ({escape_md(DONATE_CARD_HOLDER)})\n\n"
        f"👉 Bank ilovangizdagi muvaffaqiyatli to'lov cheki (screenshot yoki kvitansiya) rasmini shu yerga yuboring."
    )

    try:
        await query.edit_message_text(prompt_text, parse_mode="Markdown", reply_markup=cancel_kb)
    except Exception:
        await query.message.reply_text(prompt_text, parse_mode="Markdown", reply_markup=cancel_kb)


async def donate_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chek yuborish bosqichini boshlash"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":", 1)
    if len(parts) < 2:
        return

    tier_id = parts[1]
    tier = DONATE_TIERS.get(tier_id)
    if not tier:
        await query.answer("To'plam topilmadi!", show_alert=True)
        return

    context.user_data["awaiting_receipt_tier"] = tier_id

    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="donate_cancel_receipt")]
    ])

    prompt_text = (
        f"📸 **TO'LOV CHEKINI YUBORING**\n\n"
        f"Siz tanladingiz: **{tier['name']}** ({tier['price_label']})\n"
        f"Karta: `{DONATE_CARD_NUMBER}` ({escape_md(DONATE_CARD_HOLDER)})\n\n"
        f"👉 Bank ilovangizdagi muvaffaqiyatli to'lov cheki (screenshot yoki kvitansiya) rasmini shu yerga yuboring."
    )

    try:
        await query.edit_message_text(
            prompt_text,
            parse_mode="Markdown",
            reply_markup=cancel_kb
        )
    except Exception:
        await query.message.reply_text(
            prompt_text,
            parse_mode="Markdown",
            reply_markup=cancel_kb
        )


async def donate_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chek yuborishni bekor qilish"""
    query = update.callback_query
    await query.answer("Chek yuborish bekor qilindi.")
    context.user_data.pop("awaiting_receipt_tier", None)
    context.user_data.pop("awaiting_receipt_is_troops", None)
    context.user_data.pop("donate_troop_type", None)
    context.user_data.pop("donate_troop_amount", None)
    context.user_data.pop("donate_troop_count", None)
    context.user_data.pop("awaiting_donate_troop_custom", None)
    await donate_menu_callback(update, context)


async def donate_receipt_receiver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi yuborgan to'lov chekini qabul qilish va adminga uzatish"""
    is_troops = context.user_data.get("awaiting_receipt_is_troops", False)
    tier_id = context.user_data.get("awaiting_receipt_tier")

    if not is_troops and not tier_id:
        return

    user = update.effective_user
    if not user:
        return

    # Foto yoki hujjat tekshirish
    photo_file_id = None
    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id
    elif update.message.document:
        photo_file_id = update.message.document.file_id

    if not photo_file_id:
        await update.message.reply_text(
            "⚠️ Iltimos, to'lov chekini rasm (foto yoki screenshot) ko'rinishida yuboring!"
        )
        return

    # 1. Qo'shin sotib olish cheki bo'lsa
    if is_troops:
        troop_type = context.user_data.pop("donate_troop_type", "infantry")
        amount = context.user_data.pop("donate_troop_amount", 0)
        troop_count = context.user_data.pop("donate_troop_count", 0)
        context.user_data.pop("awaiting_receipt_is_troops", None)
        context.user_data.pop("awaiting_donate_troop_custom", None)

        t_info = TROOP_RATES.get(troop_type, {"name": "Oddiy askar", "rate": 1, "icon": "🗡️"})
        t_name = t_info["name"]

        async with AsyncSessionLocal() as session:
            user_db = await crud.get_user_with_relations(session, user.id)
            if not user_db:
                await update.message.reply_text("Iltimos, avval /start ni bosing.")
                return

            req = await crud.create_donation_request(
                session=session,
                user_id=user_db.id,
                telegram_id=user.id,
                user_full_name=user.full_name or "Lord",
                user_username=user.username or "",
                tier_id=f"troops_{troop_type}_{amount}",
                receipt_file_id=photo_file_id,
                request_type="troops",
                amount=amount,
                tier_name=f"{troop_count:,} ta {t_name}",
                troop_type=troop_type,
                troop_count=troop_count
            )

        req_id = req.id if req else 0

        # Foydalanuvchiga tasdiq xabari
        await update.message.reply_text(
            f"✅ **To'lov chekingiz muvaffaqiyatli qabul qilindi (So'rov #{req_id})!**\n\n"
            f"🛡️ Tanlangan qo'shin: **{troop_count:,} ta {t_name}**\n"
            f"💰 To'lov summasi: **{amount:,} so'm**\n\n"
            "Administrator tekshirishi uchun jo'natildi. To'lov tasdiqlanishi bilan armiyangizga barcha askarlar to'liq qo'shiladi va bu yerda bildirishnoma olasiz! ⚔️\n\n"
            "Sabringiz uchun tashakkur!",
            parse_mode="Markdown",
            reply_markup=back_to_main_keyboard()
        )

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        username_str = f"@{user.username}" if user.username else "yo'q"
        admin_caption = (
            f"⚔️ **QO'SHIN SOTIB OLISH SO'ROVI (DONATE #{req_id})**\n\n"
            f"👤 O‘yinchi: *{escape_md(user.full_name)}* ({username_str})\n"
            f"🆔 ID raqami: `{user.id}`\n"
            f"💰 To‘lov summasi: *{amount:,} so‘m*\n"
            f"🛡️ Tanlangan qo‘shin turi: *{t_name}*\n"
            f"🔢 Berilishi kerak bo‘lgan qo‘shin soni: *{troop_count:,} ta*\n"
            f"💳 Karta: `{DONATE_CARD_NUMBER}` ({escape_md(DONATE_CARD_HOLDER)})\n"
            f"⏱️ Vaqt: `{now_str}`\n\n"
            f"❓ **Ushbu o‘yinchiga {troop_count:,} ta {t_name} berilsinmi?**"
        )

        admin_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"admin_donate_approve:{req_id}"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data=f"admin_donate_reject:{req_id}"),
            ]
        ])

        admin_targets = set([OWNER_ID] + ADMIN_IDS)
        for adm_id in admin_targets:
            try:
                if update.message.photo:
                    await context.bot.send_photo(
                        chat_id=adm_id,
                        photo=photo_file_id,
                        caption=admin_caption,
                        parse_mode="Markdown",
                        reply_markup=admin_kb
                    )
                else:
                    await context.bot.send_document(
                        chat_id=adm_id,
                        document=photo_file_id,
                        caption=admin_caption,
                        parse_mode="Markdown",
                        reply_markup=admin_kb
                    )
            except Exception as e:
                print(f"Admin {adm_id} ga qo'shin cheki yuborishda xatolik: {e}")
        return

    # 2. VIP To'plam cheki bo'lsa
    tier = DONATE_TIERS.get(tier_id)
    if not tier:
        context.user_data.pop("awaiting_receipt_tier", None)
        return

    context.user_data.pop("awaiting_receipt_tier", None)

    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            await update.message.reply_text("Iltimos, avval /start ni bosing.")
            return

        req = await crud.create_donation_request(
            session=session,
            user_id=user_db.id,
            telegram_id=user.id,
            user_full_name=user.full_name or "Lord",
            user_username=user.username or "",
            tier_id=tier_id,
            receipt_file_id=photo_file_id
        )

    req_id = req.id if req else 0

    # 1. Foydalanuvchiga tasdiq xabari
    await update.message.reply_text(
        f"✅ **To'lov chekingiz muvaffaqiyatli qabul qilindi (So'rov #{req_id})!**\n\n"
        "Administrator tekshirishi uchun jo'natildi. To'lov tasdiqlanishi bilan hisobingizga barcha mukofotlar to'liq avtomatik yuklanadi va bu yerda bildirishnoma olasiz! ⚔️\n\n"
        "Sabringiz uchun tashakkur!",
        parse_mode="Markdown",
        reply_markup=back_to_main_keyboard()
    )

    # 2. Adminga xabar va rasm yuborish
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    username_str = f"@{user.username}" if user.username else "yo'q"
    caption = (
        f"💎 **YANGI TO'LOV CHEKI (DONATE #{req_id})!**\n\n"
        f"👤 Hukmdor: *{escape_md(user.full_name)}* ({username_str})\n"
        f"🆔 Telegram ID: `{user.id}`\n"
        f"📦 To'plam: *{tier['name']}*\n"
        f"💰 Narxi: *{tier['price_label']}*\n"
        f"💳 Karta: `{DONATE_CARD_NUMBER}` ({escape_md(DONATE_CARD_HOLDER)})\n"
        f"⏱️ Vaqt: `{now_str}`\n\n"
        f"To'lovni tasdiqlaysizmi?"
    )

    admin_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Tasdiqlash va Berish", callback_data=f"admin_donate_approve:{req_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"admin_donate_reject:{req_id}"),
        ],
        [
            InlineKeyboardButton("📋 Admin Panelda Ko'rish", callback_data=f"admin_donate_view:{req_id}"),
        ]
    ])

    admin_targets = set([OWNER_ID] + ADMIN_IDS)
    for adm_id in admin_targets:
        try:
            if update.message.photo:
                await context.bot.send_photo(
                    chat_id=adm_id,
                    photo=photo_file_id,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=admin_kb
                )
            else:
                await context.bot.send_document(
                    chat_id=adm_id,
                    document=photo_file_id,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=admin_kb
                )
        except Exception as e:
            print(f"Admin {adm_id} ga chek yuborishda xatolik: {e}")


async def admin_donate_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin tomonidan to'lovni tasdiqlash va mukofotlarni berish"""
    query = update.callback_query
    admin_user = query.from_user

    if not is_admin(admin_user.id):
        await query.answer("❌ Sizda bu amalni bajarish huquqi yo'q!", show_alert=True)
        return

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 2:
        return

    target_user_id = 0
    if len(parts) == 2 and parts[1].isdigit():
        req_id = int(parts[1])
        async with AsyncSessionLocal() as session:
            ok, msg, details = await crud.approve_donation_request(session, req_id, admin_user.id)
            req = await crud.get_donation_request_by_id(session, req_id)
            if req:
                target_user_id = req.telegram_id
    else:
        tier_id = parts[1]
        try:
            target_user_id = int(parts[2])
        except ValueError:
            return
        async with AsyncSessionLocal() as session:
            ok, msg, details = await crud.apply_donate_rewards(session, target_user_id, tier_id)

    if not ok:
        await query.answer(f"⚠️ {msg}", show_alert=True)
        return

    await query.answer("✅ To'lov tasdiqlandi va mukofotlar to'liq berildi!", show_alert=True)

    admin_name = admin_user.full_name

    # Agar qo'shin xaridi bo'lsa
    if details.get("is_troops"):
        troop_name = details.get("troop_name", "askarlar")
        troop_count = details.get("troop_count", 0)
        amount_paid = details.get("amount", 0)

        new_caption = (
            f"✅ **QO'SHIN TO'LOVI TASDIQLANDI!**\n\n"
            f"👑 Tasdiqlagan admin: *{escape_md(admin_name)}*\n"
            f"👤 Qabul qiluvchi: `{target_user_id}`\n"
            f"🛡️ Berilgan qo'shin: *+{troop_count:,} ta {troop_name}*\n"
            f"💰 To'lov: *{amount_paid:,} so'm*\n"
            f"📌 Holati: Muvaffaqiyatli topshirildi"
        )

        back_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔙 Donatlar Ro'yxatiga Qaytish", callback_data="admin_donations_list:0:pending"),
                InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel"),
            ]
        ])

        try:
            if query.message.caption is not None:
                await query.edit_message_caption(caption=new_caption, parse_mode="Markdown", reply_markup=back_kb)
            else:
                await query.edit_message_text(text=new_caption, parse_mode="Markdown", reply_markup=back_kb)
        except Exception:
            try:
                await query.message.reply_text(text=new_caption, parse_mode="Markdown", reply_markup=back_kb)
            except Exception:
                pass

        user_congrats = (
            f"🎉 **TABRIKLAYMIZ! TO'LOVINGIZ TASDIQLANDI!**\n\n"
            f"Hurmatli Lord! Siz xarid qilgan qo'shinlar ma'muriyat tomonidan tasdiqlandi va armiyangiz safiga qo'shildi!\n\n"
            f"🛡️ Berilgan qo'shin: **+{troop_count:,} ta {troop_name}**\n"
            f"💰 To'lov: **{amount_paid:,} so'm**\n\n"
            f"⚔️ Vesteros janglarida g'alaba siz tomonda bo'lsin!"
        )

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=user_congrats,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Foydalanuvchi {target_user_id} ga bildirishnoma yuborishda xatolik: {e}")
        return

    # VIP to'plam bo'lsa
    troops_summary = ", ".join([f"{k}: +{v}" for k, v in details.get("troops", {}).items()]) if details.get("troops") else "yo'q"
    dragon_summary = details.get("dragon") or details.get("dragon_boost") or "yo'q"
    title_summary = details.get("title") or "o'zgarishsiz"

    new_caption = (
        f"✅ **TO'LOV TASDIQLANDI VA MUKOFOTLAR BERILDI!**\n\n"
        f"👑 Tasdiqlagan admin: *{escape_md(admin_name)}*\n"
        f"👤 Qabul qiluvchi: `{target_user_id}`\n"
        f"📦 To'plam: *{details.get('tier_name', 'VIP To\'plam')}* ({details.get('price_label', '')})\n\n"
        f"🪙 Oltin: +{details.get('gold', 0):,} | 🌾 Oziq: +{details.get('food', 0):,} | ⛓️ Temir: +{details.get('iron', 0):,}\n"
        f"🛡️ Armiya: {troops_summary}\n"
        f"🐉 Ajdaho: {dragon_summary}\n"
        f"🕊️ Qalqon: +{details.get('shield_hours', 0)} soat | ⭐ Prestige: +{details.get('prestige', 0)}\n"
        f"👑 Unvon: {title_summary}"
    )

    back_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Donatlar Ro'yxatiga Qaytish", callback_data="admin_donations_list:0:pending"),
            InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel"),
        ]
    ])

    try:
        if query.message.caption is not None:
            await query.edit_message_caption(caption=new_caption, parse_mode="Markdown", reply_markup=back_kb)
        else:
            await query.edit_message_text(text=new_caption, parse_mode="Markdown", reply_markup=back_kb)
    except Exception:
        try:
            await query.message.reply_text(text=new_caption, parse_mode="Markdown", reply_markup=back_kb)
        except Exception:
            pass

    # Foydalanuvchiga bayramona xabar yuborish
    congrats_text = (
        f"🎉 **TABRIKLAYMIZ! TO'LOVINGIZ TASDIQLANDI!**\n\n"
        f"Hurmatli Lord! Siz xarid qilgan «**{details.get('tier_name', 'VIP To\'plam')}**» to'plami muvaffaqiyatli tasdiqlandi va hisobingizga yuklandi!\n\n"
        f"🎁 **Taqdim etilgan boyliklar:**\n"
        f"• 🪙 Oltin: **+{details.get('gold', 0):,}**\n"
        f"• 🌾 Oziq-ovqat: **+{details.get('food', 0):,}**\n"
        f"• ⛓️ Temir: **+{details.get('iron', 0):,}**\n"
        f"• 🕊️ Tinchlik Qalqoni: **+{details.get('shield_hours', 0)} soat**\n"
        f"• ⭐ Nufuz (Prestige): **+{details.get('prestige', 0)}**\n"
    )
    if details.get("troops"):
        congrats_text += f"• 🛡️ Armiya: **{troops_summary}**\n"
    if details.get("dragon"):
        congrats_text += f"• 🐉 Ajdaho: **{details['dragon']}**\n"
    if details.get("dragon_boost"):
        congrats_text += f"• 🐉 Ajdaho Kuchayishi: **{details['dragon_boost']}**\n"
    if details.get("wildfire_castle"):
        congrats_text += f"• 💚 Yovvoyi Olov: **{details['wildfire_castle']}** qal'asiga o'rnatildi!\n"
    if details.get("title"):
        congrats_text += f"• 👑 Faxriy Unvon: «**{details['title']}**»\n"

    v_tier = details.get("vip_tier")
    if v_tier == "lord":
        congrats_text += "\n✨ **VIP IMTIYOZ:** Sizga «🏰 Lordlar Xazinasi» yaltiroq profili, fotosurat va 🎥 shaxsiy video qo'yish huquqi berildi! /profile menyusida sozlang.\n"
    elif v_tier == "dragonlord":
        congrats_text += "\n⚜️ **VIP IMTIYOZ:** Sizga «🐉 Valyriya Merosi» olovli yaltiroq profili, fotosurat, 🎥 shaxsiy video, shior va fon musiqasi sozlash huquqi berildi! /profile menyusida sozlang.\n"
    elif v_tier == "sovereign":
        congrats_text += "\n👑 **VIP IMTIYOZ:** Sizga «👑 Temir Taxt Sohibi» imperatorlik yaltiroq profili, fotosurat, 🎥 shaxsiy video, shior, musiqa, +25% doimiy daromad va Butun Vesterosga Qirollik Farmoni chiqarish huquqi berildi! /profile menyusida sozlang.\n"

    congrats_text += "\n⚔️ Vesteros taxti sari kurashda sizga zafarlar tilaymiz!"

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=congrats_text,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Foydalanuvchi {target_user_id} ga bildirishnoma yuborishda xatolik: {e}")


async def admin_donate_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin tomonidan to'lovni rad etish"""
    query = update.callback_query
    admin_user = query.from_user

    if not is_admin(admin_user.id):
        await query.answer("❌ Sizda bu amalni bajarish huquqi yo'q!", show_alert=True)
        return

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 2:
        return

    target_user_id = 0
    tier_name = "To'lov so'rovi"
    if len(parts) == 2 and parts[1].isdigit():
        req_id = int(parts[1])
        async with AsyncSessionLocal() as session:
            ok, msg, req = await crud.reject_donation_request(session, req_id, admin_user.id)
            if not ok:
                await query.answer(f"⚠️ {msg}", show_alert=True)
                return
            if req:
                target_user_id = req.telegram_id
                tier_name = req.tier_name
    else:
        tier_id = parts[1]
        try:
            target_user_id = int(parts[2])
        except ValueError:
            return
        tier = DONATE_TIERS.get(tier_id, {"name": "VIP To'plam"})
        tier_name = tier["name"]

    await query.answer("❌ To'lov rad etildi.", show_alert=True)

    admin_name = admin_user.full_name
    new_caption = (
        f"❌ **TO'LOV SO'ROVI RAD ETILDI**\n\n"
        f"👑 Rad etgan admin: *{escape_md(admin_name)}*\n"
        f"👤 Foydalanuvchi: `{target_user_id}`\n"
        f"📦 So'rov: *{tier_name}*\n"
        f"📌 Holati: Rad etilgan"
    )

    back_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Donatlar Ro'yxatiga Qaytish", callback_data="admin_donations_list:0:pending"),
            InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel"),
        ]
    ])

    try:
        if query.message.caption is not None:
            await query.edit_message_caption(caption=new_caption, parse_mode="Markdown", reply_markup=back_kb)
        else:
            await query.edit_message_text(text=new_caption, parse_mode="Markdown", reply_markup=back_kb)
    except Exception:
        try:
            await query.message.reply_text(text=new_caption, parse_mode="Markdown", reply_markup=back_kb)
        except Exception:
            pass

    # Foydalanuvchiga xabar berish
    reject_text = (
        f"❌ **TO'LOV TASDIQLANMADI**\n\n"
        f"Hurmatli Lord, siz yuborgan «**{tier_name}**» bo'yicha to'lov cheki ma'muriyat tomonidan tasdiqlanmadi.\n\n"
        f"Sababi: Hisobga to'lov kelib tushmagan yoki chek noto'g'ri bo'lishi mumkin.\n"
        f"Agar buni xatolik deb hisoblasangiz, iltimos ma'muriyat bilan bog'laning."
    )
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=reject_text,
            parse_mode="Markdown"
        )
    except Exception:
        pass



async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram Stars precheckout tekshiruvi"""
    query = update.pre_checkout_query
    if not query:
        return
    await query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram Stars to'lovi muvaffaqiyatli qabul qilinganda"""
    msg = update.effective_message
    if not msg or not msg.successful_payment:
        return

    payment = msg.successful_payment
    tg_user = update.effective_user
    payload = payment.invoice_payload or ""  # e.g. "cosmetic:castle_valyrian" or "vip_noble"

    item_id = payload.split(":")[-1] if ":" in payload else payload
    amount_stars = payment.total_amount

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if user:
            idempotency_key = f"stars_{payment.telegram_payment_charge_id}"
            await record_payment_transaction(
                session=session,
                telegram_id=tg_user.id,
                item_id=item_id,
                provider="telegram_stars",
                idempotency_key=idempotency_key,
                amount_stars=amount_stars,
                user_id=user.id,
            )
            await grant_cosmetic_item(session, user, item_id)

    item = get_cosmetic_item(item_id)
    item_name = item["name"] if item else item_id
    congrats = (
        f"🎉 **TO'LOV MUVAFFAQIYATLI AMALGA OSHIRILDI!**\n\n"
        f"⭐ **{amount_stars} Stars** qabul qilindi.\n"
        f"🎁 Sizga **«{item_name}»** muvaffaqiyatli taqdim etildi!\n\n"
        f"Uni Telegram Mini Appda yoki /profile menyusida faollashtirishingiz mumkin."
    )
    await msg.reply_text(congrats, parse_mode="Markdown")


def register_donate_handlers(app):
    """Donate handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["donate", "vip", "donat", "homiylik", "stars", "shop"], donate_command))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(CallbackQueryHandler(donate_menu_callback, pattern="^menu_donate$"))
    app.add_handler(CallbackQueryHandler(donate_troops_menu_callback, pattern="^donate_troops_menu$"))
    app.add_handler(CallbackQueryHandler(donate_troop_type_callback, pattern="^donate_troop_type:"))
    app.add_handler(CallbackQueryHandler(donate_troop_amt_callback, pattern="^donate_troop_amt:"))
    app.add_handler(CallbackQueryHandler(donate_troop_custom_callback, pattern="^donate_troop_custom:"))
    app.add_handler(CallbackQueryHandler(donate_troop_submit_callback, pattern="^donate_troop_submit:"))
    app.add_handler(CallbackQueryHandler(donate_pick_callback, pattern="^donate_pick:"))
    app.add_handler(CallbackQueryHandler(donate_submit_callback, pattern="^donate_submit:"))
    app.add_handler(CallbackQueryHandler(donate_cancel_callback, pattern="^donate_cancel_receipt$"))
    app.add_handler(CallbackQueryHandler(admin_donate_approve_callback, pattern="^admin_donate_approve:"))
    app.add_handler(CallbackQueryHandler(admin_donate_reject_callback, pattern="^admin_donate_reject:"))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, donate_receipt_receiver), group=1)
