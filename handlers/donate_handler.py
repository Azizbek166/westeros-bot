from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from database import AsyncSessionLocal, crud, models
from config import (
    DONATE_TIERS,
    OWNER_ID,
    ADMIN_IDS,
    escape_md,
    get_miniapp_url,
)
from services.donate_service import (
    is_authorized_admin,
    resolve_package_info,
    get_payment_requisites_service,
    update_payment_requisites_service,
    submit_donation_request_service,
    approve_donation_request_service,
    reject_donation_request_service,
    get_user_donation_history_service,
    get_admin_donation_stats_service,
)
from core.cosmetics import COSMETICS_CATALOG
from keyboards.menus import back_to_main_keyboard


def is_admin(user_id: int) -> bool:
    return is_authorized_admin(user_id)


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
    """To'liq Donat do'koni klaviaturasi: Premium Pass, Resurs paketlari, Tezlashtirish, Kosmetika va Mening so'rovlarim"""
    buttons = [
        [
            InlineKeyboardButton(
                "👑 Premium Season Pass (30 kun) — 25,000 so'm",
                callback_data="donate_pick:premium_pass",
            )
        ],
        [
            InlineKeyboardButton(
                "💎 Noble VIP (30 kun) — 15,000 so'm",
                callback_data="donate_pick:vip_noble",
            ),
            InlineKeyboardButton(
                "🎁 Starter Pack — 5,000 so'm",
                callback_data="donate_pick:starter_pack",
            ),
        ],
        [
            InlineKeyboardButton(
                "📦 Kichik Resurs — 10,000 so'm",
                callback_data="donate_pick:knight",
            ),
            InlineKeyboardButton(
                "🧰 O'rta Resurs (+10%) — 25,000 so'm",
                callback_data="donate_pick:lord",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏛️ Katta Resurs (+15%) — 50,000 so'm",
                callback_data="donate_pick:dragonlord",
            ),
            InlineKeyboardButton(
                "👑 Maksimal Xazina (+25%) — 99,000 so'm",
                callback_data="donate_pick:sovereign",
            ),
        ],
        [
            InlineKeyboardButton(
                "⚡ Tezlashtirish Paketi (Qurilish/Parvarish) — 15,000 so'm",
                callback_data="donate_pick:speedup_pack",
            )
        ],
        [
            InlineKeyboardButton(
                "🎨 Kosmetika (Ramka, Unvon, Ajdar Terisi)",
                callback_data="donate_cosmetics_menu",
            )
        ],
        [
            InlineKeyboardButton(
                "📋 Mening so'rovlarim (Tarix va Premium muddat)",
                callback_data="donate_my_requests",
            )
        ],
        [
            InlineKeyboardButton(
                "📱 Mini App Donat Do'koni 💎",
                web_app=WebAppInfo(url=get_miniapp_url("donate")),
            )
        ],
        [
            InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def donate_tier_keyboard(tier_id: str) -> InlineKeyboardMarkup:
    """Tanlangan paket uchun 'To'lov qildim' (chek yuborish) klaviaturasi"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ To'lov qildim (Chek skrinshotini yuborish)",
                callback_data=f"donate_submit:{tier_id}",
            )
        ],
        [
            InlineKeyboardButton("🔙 Paketlar ro'yxati", callback_data="menu_donate"),
            InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main"),
        ],
    ])


def donate_troop_amount_keyboard(troop_type: str) -> InlineKeyboardMarkup:
    """Qo'shin xaridi uchun summa tanlash klaviaturasi"""
    amounts = [10000, 25000, 50000, 100000]
    rows = []
    for amt in amounts:
        cnt = calc_troops(troop_type, amt)
        rows.append([
            InlineKeyboardButton(
                f"💰 {amt:,} so'm — {cnt:,} ta",
                callback_data=f"donate_troop_amt:{troop_type}:{amt}",
            )
        ])
    rows.append([InlineKeyboardButton("✍️ Boshqa summa kiritish", callback_data=f"donate_troop_custom:{troop_type}")])
    rows.append([InlineKeyboardButton("🔙 Orqaga", callback_data="menu_donate")])
    return InlineKeyboardMarkup(rows)


async def _build_donate_intro_text() -> str:
    async with AsyncSessionLocal() as session:
        reqs = await crud.get_payment_settings(session)
    card_num = reqs["card_number"]
    card_holder = reqs["card_holder"]
    return (
        "💎 **VESTEROS PREMIUM PASS & VIP DO'KONI**\n\n"
        "Hurmatli Lord! Barcha paketlar **qo'lda tasdiqlash** orqali xavfsiz faollashtiriladi:\n\n"
        "📦 **Mavjud Paketlar:**\n"
        "• 👑 **Premium Season Pass (25,000 so'm / 30 kun):**\n"
        "  — Premium belgi, Valiriya ramkasi va «Mavsum Aslzodasi» unvoni\n"
        "  — Darhol beriladigan yoqimli bonus: **+2,500 Oltin, +5,000 Bug'doy, +1,500 Temir, +50 Nufuz**\n"
        "  — 30 kun davomida har kuni qo'shimcha kunlik bonus (**+300 Oltin, +600 Bug'doy, +200 Temir**)\n"
        "  — Mavsumning barcha 20 ta Premium mukofot yo'laklari\n"
        "• 👑 **Noble VIP (15,000 so'm / 30 kun):**\n"
        "  — 1-bosishda barcha qal'alardan soliq yig'ish, profilga video, VIP nishoni\n"
        "  — Darhol bonus: **+1,000 Oltin, +2,000 Bug'doy, +500 Temir**\n"
        "• 🎁 **Starter Pack (5,000 so'm / 7 kun VIP):**\n"
        "  — «Yetti Qirollik Ritsari» unvoni + Po'lat ramka\n"
        "  — Darhol bonus: **+800 Oltin, +1,500 Bug'doy, +400 Temir**\n\n"
        "💳 **To'lov Karta Rekvizitlari:**\n"
        f"• Karta raqami: `{card_num}`\n"
        f"• Karta egasi: *{escape_md(card_holder)}*\n\n"
        "👇 *Kerakli paketni tanlang, to'lov qiling va chek skrinshotini yuboring:*"
    )


async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/donate, /vip, /shop buyrug'i"""
    text = await _build_donate_intro_text()
    if update.message:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=donate_menu_keyboard(),
        )


async def donate_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_donate callback query"""
    query = update.callback_query
    await query.answer()

    text = await _build_donate_intro_text()
    try:
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=donate_menu_keyboard(),
        )
    except Exception:
        await query.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=donate_menu_keyboard(),
        )


async def donate_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan to'plam tafsilotlarini va admin kiritgan karta raqamini ko'rsatish"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":", 1)
    if len(parts) < 2:
        return

    tier_id = parts[1]
    tier = DONATE_TIERS.get(tier_id)
    if not tier:
        pkg = resolve_package_info(tier_id)
        if not pkg:
            await query.answer("Paket topilmadi!", show_alert=True)
            return
        tier = {
            "name": pkg["name"],
            "subtitle": "Maxsus kosmetik buyum",
            "description": pkg["description"],
            "price_label": pkg["price_label"],
        }

    async with AsyncSessionLocal() as session:
        reqs = await crud.get_payment_settings(session)
        pending = await crud.get_user_pending_donation_request(session, telegram_id=query.from_user.id)

    card_num = reqs["card_number"]
    card_holder = reqs["card_holder"]

    pending_note = ""
    if pending:
        pending_note = (
            f"\n⚠️ *Eslatma: Sizda hozirda ko'rib chiqilayotgan so'rov mavjud "
            f"(#{pending.id} — {escape_md(pending.tier_name)}). "
            f"Yangi so'rov yuborish uchun avval joriy so'rov ko'rib chiqilishini kuting.*\n"
        )

    text = (
        f"💎 **{tier['name'].upper()}**\n"
        f"_{tier.get('subtitle', '')}_\n\n"
        f"📦 **Paket tarkibi va mukofotlar:**\n"
        f"{tier.get('description', '')}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💳 **TO'LOV REKVIZITLARI:**\n"
        f"• Karta raqami: `{card_num}`\n"
        f"• Karta egasi: *{escape_md(card_holder)}*\n"
        f"• To'lov summasi: *{tier['price_label']}*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"{pending_note}\n"
        f"📌 **QANDAY FAOLLASHTIRILADI?**\n"
        f"1. Yuqoridagi karta raqamiga **{tier['price_label']}** o'tkazing.\n"
        f"2. To'lov chekini skrinshot (rasm) qilib oling.\n"
        f"3. Pastdagi **«✅ To'lov qildim»** tugmasini bosing va chek rasmini botga yuboring.\n"
        f"4. Admin tasdiqlashi bilan paket va resurslar hisobingizga avtomatik tushadi!"
    )

    try:
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=donate_tier_keyboard(tier_id),
        )
    except Exception:
        await query.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=donate_tier_keyboard(tier_id),
        )


async def donate_troops_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'shin sotib olish — Pay-to-win to'xtatilgani haqida tushuntirish"""
    query = update.callback_query
    await query.answer()

    text = (
        "⚖️ **HALOL VA ADOLATLI BALANS: PAY-TO-WIN YO'Q!**\n\n"
        "Hurmatli Lord! O'yinda raqobatbardoshlik, sharaf va tenglikni ta'minlash maqsadida "
        "real pul evaziga askarlar yoki jang quvvatini sotib olish bekor qilingan.\n\n"
        "🎁 **Do'konda nima bor?**\n"
        "• 👑 **Premium Season Pass** (30 kunlik premium status, yoqimli resurs bonusi va kunlik bonuslar)\n"
        "• 👑 **Noble VIP** va kosmetik qal'a/ajdar ko'rinishlari!"
    )
    buttons = [
        [InlineKeyboardButton("👑 Paketlarni Ko'rish", callback_data="menu_donate")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ]
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def donate_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'To'lov qildim' bosilganda chek rasmini so'rash (pending tekshiruvi bilan)"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":", 1)
    if len(parts) < 2:
        return

    tier_id = parts[1]
    pkg = resolve_package_info(tier_id)
    if not pkg:
        await query.answer("Paket topilmadi!", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        pending = await crud.get_user_pending_donation_request(session, telegram_id=query.from_user.id)
        reqs = await crud.get_payment_settings(session)

    if pending:
        await query.answer(
            f"⏳ Sizda allaqachon kutilayotgan so'rov bor (#{pending.id}). Admin javobini kuting!",
            show_alert=True,
        )
        return

    context.user_data["awaiting_receipt_tier"] = tier_id
    context.user_data.pop("awaiting_receipt_is_troops", None)

    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="donate_cancel_receipt")]
    ])

    prompt_text = (
        f"📸 **TO'LOV CHEKI SKRINSHOTINI YUBORING (MAJBURIY)**\n\n"
        f"📦 Tanlangan paket: **{pkg['name']}**\n"
        f"💵 To'lov summasi: **{pkg['price_label']}**\n"
        f"💳 Karta: `{reqs['card_number']}` (*{escape_md(reqs['card_holder'])}*)\n\n"
        f"👉 Iltimos, to'lov cheki (skrinshot) **rasmini** shu yerga yuboring:"
    )

    try:
        await query.edit_message_text(
            prompt_text,
            parse_mode="Markdown",
            reply_markup=cancel_kb,
        )
    except Exception:
        await query.message.reply_text(
            prompt_text,
            parse_mode="Markdown",
            reply_markup=cancel_kb,
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
    """Foydalanuvchi yuborgan to'lov cheki skrinshotini qabul qilish va adminga yuborish"""
    is_troops = context.user_data.get("awaiting_receipt_is_troops", False)
    tier_id = context.user_data.get("awaiting_receipt_tier")

    if not is_troops and not tier_id:
        return

    user = update.effective_user
    if not user or not update.message:
        return

    # Rasm (photo) yoki rasm hujjatini tekshirish
    photo_file_id = None
    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id
    elif update.message.document and (update.message.document.mime_type or "").startswith("image/"):
        photo_file_id = update.message.document.file_id

    if not photo_file_id:
        await update.message.reply_text(
            "⚠️ To'lov cheki **rasm (skrinshot)** ko'rinishida yuborilishi majburiy! "
            "Iltimos, skrinshot rasmini yuboring.",
            parse_mode="Markdown",
        )
        return

    context.user_data.pop("awaiting_receipt_tier", None)
    context.user_data.pop("awaiting_receipt_is_troops", None)

    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            await update.message.reply_text("Iltimos, avval /start buyrug'ini bosing.")
            return

        if is_troops:
            troop_type = context.user_data.pop("donate_troop_type", "infantry")
            amount = context.user_data.pop("donate_troop_amount", 0)
            troop_count = context.user_data.pop("donate_troop_count", 0)
            t_info = TROOP_RATES.get(troop_type, {"name": "Oddiy askar", "rate": 1, "icon": "🗡️"})
            ok, msg, req = await submit_donation_request_service(
                session=session,
                user=user_db,
                package_id=f"troops_{troop_type}_{amount}",
                receipt_file_id=photo_file_id,
                bot=context.bot,
                request_type="troops",
                troop_type=troop_type,
                troop_count=troop_count,
                custom_price_uzs=amount,
                custom_tier_name=f"{troop_count:,} ta {t_info['name']}",
            )
        else:
            ok, msg, req = await submit_donation_request_service(
                session=session,
                user=user_db,
                package_id=tier_id,
                receipt_file_id=photo_file_id,
                bot=context.bot,
            )

    await update.message.reply_text(
        msg,
        reply_markup=back_to_main_keyboard(),
    )


async def handle_donate_text_WhenAwaitingReceipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi chek kutilyotgan paytda oddiy matn yozsa, skrinshot majburiyligini eslatish"""
    if context.user_data.get("awaiting_admin_reject_reason"):
        await handle_admin_reject_reason_text(update, context)
        return
    if context.user_data.get("awaiting_admin_card_input"):
        await handle_admin_card_settings_text(update, context)
        return
    if not context.user_data.get("awaiting_receipt_tier") and not context.user_data.get("awaiting_receipt_is_troops"):
        return
    if not update.message or not update.message.text:
        return
    if update.message.text.startswith("/"):
        return

    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="donate_cancel_receipt")]
    ])
    await update.message.reply_text(
        "⚠️ **To'lov cheki skrinshotini (rasm) yuborish majburiy!**\n"
        "Matn emas, to'lov cheki rasmini yuboring yoki bekor qilish tugmasini bosing.",
        parse_mode="Markdown",
        reply_markup=cancel_kb,
    )


async def admin_donate_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin tomonidan to'lovni tasdiqlash va mukofotlarni berish (Yagona servis orqali)"""
    query = update.callback_query
    admin_user = query.from_user

    if not is_admin(admin_user.id):
        await query.answer("❌ Sizda bu amalni bajarish huquqi yo'q!", show_alert=True)
        return

    data = query.data or ""
    req_id = 0
    if ":" in data:
        parts = data.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            req_id = int(parts[1])
    elif data.startswith("adm_don_ok_"):
        tail = data.replace("adm_don_ok_", "")
        if tail.isdigit():
            req_id = int(tail)

    if req_id <= 0:
        await query.answer("⚠️ So'rov ID topilmadi.", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        ok, msg, details = await approve_donation_request_service(
            session=session,
            request_id=req_id,
            admin_telegram_id=admin_user.id,
            bot=context.bot,
        )
        req = await crud.get_donation_request_by_id(session, req_id)

    if not ok:
        await query.answer(f"⚠️ {msg}", show_alert=True)
        return

    await query.answer("✅ To'lov tasdiqlandi va mukofotlar berildi!", show_alert=True)

    admin_name = admin_user.full_name
    target_user_id = req.telegram_id if req else 0
    tier_label = details.get("tier_name") or (req.tier_name if req else "Paket")
    price_label = details.get("price_label") or (req.price_label if req else "")

    new_caption = (
        f"✅ <b>TO'LOV TASDIQLANDI (#{req_id})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Tasdiqlagan admin:</b> {admin_name} (<code>{admin_user.id}</code>)\n"
        f"👤 <b>O'yinchi ID:</b> <code>{target_user_id}</code>\n"
        f"📦 <b>Paket:</b> {tier_label} ({price_label})\n"
        f"🪙 +{details.get('gold', 0):,} Oltin | 🌾 +{details.get('food', 0):,} Bug'doy | ⚒️ +{details.get('iron', 0):,} Temir\n"
        f"📌 <b>Holati:</b> Approved (Mukofotlar berildi)"
    )

    back_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Donatlar Ro'yxati", callback_data="admin_donations_list:0:pending"),
            InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel"),
        ]
    ])

    try:
        if query.message.caption is not None:
            await query.edit_message_caption(caption=new_caption, parse_mode="HTML", reply_markup=back_kb)
        else:
            await query.edit_message_text(text=new_caption, parse_mode="HTML", reply_markup=back_kb)
    except Exception:
        try:
            await query.message.reply_text(text=new_caption, parse_mode="HTML", reply_markup=back_kb)
        except Exception:
            pass


REJECT_REASON_PRESETS = {
    "no_pay": "Hisobga to'lov kelib tushmagan.",
    "bad_img": "Yuborilgan rasm to'lov cheki emas yoki o'qib bo'lmaydi.",
    "wrong_amt": "To'lov summasi paket narxiga mos emas.",
    "dup_img": "Eski yoki avval ishlatilgan to'lov cheki yuborilgan.",
}


async def admin_donate_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin tomonidan to'lovni rad etish (sabab tanlash yoki bevosita rad etish)"""
    query = update.callback_query
    admin_user = query.from_user

    if not is_admin(admin_user.id):
        await query.answer("❌ Sizda bu amalni bajarish huquqi yo'q!", show_alert=True)
        return

    data = query.data or ""
    req_id = 0
    reason_key = None

    if data.startswith("adm_don_no_"):
        tail = data.replace("adm_don_no_", "")
        if tail.isdigit():
            req_id = int(tail)
    elif ":" in data:
        parts = data.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            req_id = int(parts[1])
        if len(parts) >= 3:
            reason_key = parts[2]

    if req_id <= 0:
        await query.answer("⚠️ So'rov ID topilmadi.", show_alert=True)
        return

    # Agar sabab tanlanmagan bo'lsa, sabab tanlash tugmalarini ko'rsatamiz
    if not reason_key:
        await query.answer("Rad etish sababini tanlang")
        reason_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ To'lov tushmagan", callback_data=f"admin_donate_reject:{req_id}:no_pay")],
            [InlineKeyboardButton("🖼️ Chek xato / o'qib bo'lmaydi", callback_data=f"admin_donate_reject:{req_id}:bad_img")],
            [InlineKeyboardButton("💰 Summa noto'g'ri", callback_data=f"admin_donate_reject:{req_id}:wrong_amt")],
            [InlineKeyboardButton("♻️ Eski / dublikat chek", callback_data=f"admin_donate_reject:{req_id}:dup_img")],
            [InlineKeyboardButton("✍️ Boshqa sabab yozish", callback_data=f"admin_donate_reject:{req_id}:custom")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data=f"admin_donate_view:{req_id}")],
        ])
        prompt = f"❓ <b>So'rov #{req_id} ni rad etish sababini tanlang:</b>"
        try:
            if query.message.caption is not None:
                await query.edit_message_caption(caption=prompt, parse_mode="HTML", reply_markup=reason_kb)
            else:
                await query.edit_message_text(text=prompt, parse_mode="HTML", reply_markup=reason_kb)
        except Exception:
            await query.message.reply_text(text=prompt, parse_mode="HTML", reply_markup=reason_kb)
        return

    if reason_key == "custom":
        await query.answer()
        context.user_data["awaiting_admin_reject_reason"] = req_id
        await query.message.reply_text(
            f"✍️ <b>So'rov #{req_id}</b> uchun rad etish sababini yozib yuboring:",
            parse_mode="HTML",
        )
        return

    reason_text = REJECT_REASON_PRESETS.get(reason_key, "To'lov cheki tasdiqlanmadi.")

    async with AsyncSessionLocal() as session:
        ok, msg, req = await reject_donation_request_service(
            session=session,
            request_id=req_id,
            admin_telegram_id=admin_user.id,
            reason=reason_text,
            bot=context.bot,
        )

    if not ok:
        await query.answer(f"⚠️ {msg}", show_alert=True)
        return

    await query.answer("❌ So'rov rad etildi va foydalanuvchiga xabar yuborildi.", show_alert=True)

    new_caption = (
        f"❌ <b>TO'LOV SO'ROVI RAD ETILDI (#{req_id})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Rad etgan admin:</b> {admin_user.full_name} (<code>{admin_user.id}</code>)\n"
        f"👤 <b>Foydalanuvchi:</b> <code>{req.telegram_id if req else 0}</code>\n"
        f"📦 <b>Paket:</b> {req.tier_name if req else '-'}\n"
        f"📝 <b>Sabab:</b> {reason_text}\n"
        f"📌 <b>Holati:</b> Rejected"
    )
    back_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Donatlar Ro'yxati", callback_data="admin_donations_list:0:pending"),
            InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel"),
        ]
    ])
    try:
        if query.message.caption is not None:
            await query.edit_message_caption(caption=new_caption, parse_mode="HTML", reply_markup=back_kb)
        else:
            await query.edit_message_text(text=new_caption, parse_mode="HTML", reply_markup=back_kb)
    except Exception:
        try:
            await query.message.reply_text(text=new_caption, parse_mode="HTML", reply_markup=back_kb)
        except Exception:
            pass


async def handle_admin_reject_reason_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin qo'lda yozgan rad etish sababini qabul qilish"""
    req_id = context.user_data.pop("awaiting_admin_reject_reason", None)
    if not req_id or not update.message or not update.message.text:
        return

    admin_user = update.effective_user
    if not admin_user or not is_admin(admin_user.id):
        return

    reason_text = update.message.text.strip()
    async with AsyncSessionLocal() as session:
        ok, msg, req = await reject_donation_request_service(
            session=session,
            request_id=int(req_id),
            admin_telegram_id=admin_user.id,
            reason=reason_text,
            bot=context.bot,
        )

    back_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Donatlar Ro'yxati", callback_data="admin_donations_list:0:pending"),
            InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel"),
        ]
    ])
    if ok:
        await update.message.reply_text(
            f"❌ <b>So'rov #{req_id} rad etildi!</b>\n📝 Sabab: {reason_text}",
            parse_mode="HTML",
            reply_markup=back_kb,
        )
    else:
        await update.message.reply_text(f"⚠️ {msg}", reply_markup=back_kb)


async def admin_card_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin Panelda karta raqami va karta egasini ko'rish / o'zgartirish menyusi"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    context.user_data.pop("awaiting_admin_card_input", None)
    async with AsyncSessionLocal() as session:
        reqs = await crud.get_payment_settings(session)

    text = (
        f"💳 <b>DONAT KARTA REKVIZITLARI SOZLAMALARI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 <b>Karta raqami:</b> <code>{reqs['card_number']}</code>\n"
        f"👤 <b>Karta egasi:</b> <b>{reqs['card_holder']}</b>\n"
        f"🕒 <b>Yangilangan:</b> {reqs.get('updated_at') or 'Standart'}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Ushbu ma'lumotlar ham Botda, ham Mini Appda barcha o'yinchilarga ko'rinadi."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Karta va Egasini O'zgartirish", callback_data="admin_card_edit_start")],
        [InlineKeyboardButton("🔙 Donat So'rovlariga Qaytish", callback_data="admin_donations_list:0:pending")],
        [InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")],
    ])
    try:
        await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await query.message.reply_text(text=text, parse_mode="HTML", reply_markup=kb)


async def admin_card_edit_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Karta raqami va egasini kiritishni boshlash"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    context.user_data["awaiting_admin_card_input"] = True
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_card_settings")]
    ])
    prompt = (
        "✏️ <b>YANGI KARTA REKVIZITLARINI KIRITING</b>\n\n"
        "Iltimos, yangi karta raqami va karta egasi ismini <code>|</code> belgisi bilan ajratib yuboring.\n\n"
        "📌 <b>Namuna:</b>\n"
        "<code>9860 1201 3456 7890 | ALISHER NAVOIY</code>"
    )
    try:
        await query.edit_message_text(text=prompt, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await query.message.reply_text(text=prompt, parse_mode="HTML", reply_markup=kb)


async def handle_admin_card_settings_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin yuborgan yangi karta raqami va karta egasini saqlash"""
    if not context.user_data.get("awaiting_admin_card_input"):
        return
    if not update.message or not update.message.text:
        return

    admin_user = update.effective_user
    if not admin_user or not is_admin(admin_user.id):
        context.user_data.pop("awaiting_admin_card_input", None)
        return

    raw = update.message.text.strip()
    if "|" in raw:
        parts = raw.split("|", 1)
        card_number = parts[0].strip()
        card_holder = parts[1].strip()
    elif "\n" in raw:
        parts = [p.strip() for p in raw.splitlines() if p.strip()]
        if len(parts) < 2:
            await update.message.reply_text("⚠️ Karta raqami va egasini `KARTA_RAQAMI | ISM FAMILIYA` formatida yuboring.")
            return
        card_number, card_holder = parts[0], parts[1]
    else:
        await update.message.reply_text(
            "⚠️ Format noto'g'ri! Karta raqami va karta egasini `|` belgisi bilan ajratib yozing.\n"
            "Masalan: `9860 1201 3456 7890 | SARDOR KARIMOV`",
            parse_mode="Markdown",
        )
        return

    context.user_data.pop("awaiting_admin_card_input", None)
    async with AsyncSessionLocal() as session:
        ok, msg, data = await update_payment_requisites_service(
            session=session,
            admin_telegram_id=admin_user.id,
            card_number=card_number,
            card_holder=card_holder,
        )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Karta Sozlamalari", callback_data="admin_card_settings")],
        [InlineKeyboardButton("🔙 Donat So'rovlari", callback_data="admin_donations_list:0:pending")],
    ])
    if ok:
        await update.message.reply_text(
            f"{msg}\n\n"
            f"🔢 Karta: <code>{data['card_number']}</code>\n"
            f"👤 Karta egasi: <b>{data['card_holder']}</b>",
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        await update.message.reply_text(f"❌ {msg}", reply_markup=kb)


async def donate_cosmetics_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot ichida Kosmetika (Ramkalar, Unvonlar, Ajdar Terilari, Qal'alar) tanlash menyusi"""
    query = update.callback_query
    await query.answer()

    buttons = []
    for item_id, item in COSMETICS_CATALOG.items():
        if item_id in ("vip_noble", "starter_pack"):
            continue
        p_uzs = item.get("price_uzs", 15000)
        icon = item.get("icon", "✨")
        name = item.get("name", item_id)
        buttons.append([
            InlineKeyboardButton(
                f"{icon} {name} — {p_uzs:,} so'm",
                callback_data=f"donate_pick:{item_id}",
            )
        ])
    buttons.append([InlineKeyboardButton("🔙 Donat Do'koniga Qaytish", callback_data="menu_donate")])

    text = (
        "🎨 **VALYRIYA KOSMETIKA DO'KONI**\n\n"
        "Profil ramkalari, faxriy unvonlar, ajdar terilari va qal'a ko'rinishlarini tanlang.\n"
        "Barcha kosmetik buyumlar to'lov cheki (skrinshot) tasdiqlangach taqdim etiladi:"
    )
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.message.reply_text(text.replace("*", ""), reply_markup=InlineKeyboardMarkup(buttons))


async def donate_my_requests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchining donat so'rovlari tarixi va faol Premium qolgan kunlari ('Mening so'rovlarim')"""
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_any(session, tg_id)
        history = await get_user_donation_history_service(session, user, limit=10) if user else []

    now = datetime.utcnow()
    vip_status_str = "❌ Faol emas"
    if user and user.vip_until and user.vip_until > now:
        days_left = max(1, int((user.vip_until - now).total_seconds() // 86400) + 1)
        vip_status_str = f"✅ **Faol ({days_left} kun qoldi — {user.vip_until.strftime('%Y-%m-%d')} gacha)**"

    status_map = {
        "pending": "⏳ Ko'rib chiqilmoqda",
        "approved": "✅ Tasdiqlangan",
        "rejected": "❌ Rad etilgan",
    }

    lines = [
        "📋 **MENING DONAT SO'ROVLARIM VA PREMIUM HOLATIM**\n",
        f"👑 **Premium / VIP Holati:** {vip_status_str}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if not history:
        lines.append("Sizda hali yuborilgan donat so'rovlari yo'q.")
    else:
        for r in history:
            st_lbl = status_map.get(r["status"], r["status"])
            note_str = f"\n   📝 _Sabab: {escape_md(r['admin_notes'])}_" if r.get("admin_notes") and r["status"] == "rejected" else ""
            lines.append(
                f"• **#{r['id']}** — {escape_md(r['tier_name'])} ({r['price_label']})\n"
                f"   Holati: {st_lbl} | 📅 {r['created_at']}{note_str}"
            )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="donate_my_requests")],
        [InlineKeyboardButton("🔙 Donat Do'koni", callback_data="menu_donate")],
    ])
    text = "\n".join(lines)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await query.message.reply_text(text.replace("*", "").replace("_", ""), reply_markup=kb)


async def admin_donate_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adminga kunlik, haftalik va umumiy donat statistikasini ko'rsatish"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        stats = await get_admin_donation_stats_service(session)

    text = (
        f"📊 <b>DONAT STATISTIKASI (KUNLIK / HAFTALIK)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>Bugun (oxirgi 24 soat):</b>\n"
        f"• Tasdiqlangan: <b>{stats['daily_approved_count']} ta</b>\n"
        f"• Tushum: <b>{stats['daily_approved_uzs']:,} so'm</b>\n\n"
        f"🗓️ <b>Oxirgi 7 kun (Haftalik):</b>\n"
        f"• Tasdiqlangan: <b>{stats['weekly_approved_count']} ta</b>\n"
        f"• Tushum: <b>{stats['weekly_approved_uzs']:,} so'm</b>\n\n"
        f"🏛️ <b>Jami tasdiqlangan:</b>\n"
        f"• Soni: <b>{stats['total_approved_count']} ta</b>\n"
        f"• Jami summa: <b>{stats['total_approved_uzs']:,} so'm</b>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Donat So'rovlariga Qaytish", callback_data="admin_donations_list:0:pending")],
        [InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")],
    ])
    try:
        await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await query.message.reply_text(text=text, parse_mode="HTML", reply_markup=kb)


def register_donate_handlers(app):
    """Donate handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["donate", "vip", "donat", "homiylik", "stars", "shop"], donate_command))
    app.add_handler(CallbackQueryHandler(donate_menu_callback, pattern="^menu_donate$"))
    app.add_handler(CallbackQueryHandler(donate_cosmetics_menu_callback, pattern="^donate_cosmetics_menu$"))
    app.add_handler(CallbackQueryHandler(donate_my_requests_callback, pattern="^donate_my_requests$"))
    app.add_handler(CallbackQueryHandler(donate_troops_menu_callback, pattern="^donate_troops_menu$"))
    app.add_handler(CallbackQueryHandler(donate_pick_callback, pattern="^donate_pick:"))
    app.add_handler(CallbackQueryHandler(donate_submit_callback, pattern="^donate_submit:"))
    app.add_handler(CallbackQueryHandler(donate_cancel_callback, pattern="^donate_cancel_receipt$"))
    app.add_handler(CallbackQueryHandler(admin_donate_approve_callback, pattern="^(admin_donate_approve:|adm_don_ok_)"))
    app.add_handler(CallbackQueryHandler(admin_donate_reject_callback, pattern="^(admin_donate_reject:|adm_don_no_)"))
    app.add_handler(CallbackQueryHandler(admin_card_settings_callback, pattern="^admin_card_settings$"))
    app.add_handler(CallbackQueryHandler(admin_card_edit_start_callback, pattern="^admin_card_edit_start$"))
    app.add_handler(CallbackQueryHandler(admin_donate_stats_callback, pattern="^admin_donate_stats$"))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, donate_receipt_receiver), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_donate_text_WhenAwaitingReceipt), group=2)
