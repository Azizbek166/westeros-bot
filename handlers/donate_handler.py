from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from database import AsyncSessionLocal, crud
from config import (
    DONATE_CARD_NUMBER,
    DONATE_CARD_HOLDER,
    DONATE_TIERS,
    OWNER_ID,
    ADMIN_IDS,
    escape_md,
)
from keyboards.menus import back_to_main_keyboard


def is_admin(user_id: int) -> bool:
    try:
        uid = int(user_id)
        return uid in [int(x) for x in ADMIN_IDS] or uid == int(OWNER_ID)
    except Exception:
        return False


def donate_menu_keyboard() -> InlineKeyboardMarkup:
    """VIP to'plamlar ro'yxati klaviaturasi"""
    buttons = []
    for tier_id, tier in DONATE_TIERS.items():
        buttons.append([
            InlineKeyboardButton(
                f"{tier['name']} — {tier['price_label']}",
                callback_data=f"donate_pick:{tier_id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")
    ])
    return InlineKeyboardMarkup(buttons)


def donate_tier_keyboard(tier_id: str) -> InlineKeyboardMarkup:
    """Tanlangan to'plam tafsilotlari klaviaturasi"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📸 To'lov chekini yuborish", callback_data=f"donate_submit:{tier_id}")
        ],
        [
            InlineKeyboardButton("🔙 Barcha To'plamlar", callback_data="menu_donate"),
            InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main"),
        ]
    ])


async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/donate, /vip buyrug'i"""
    text = (
        "💎 **WESTEROS AFSONAVIY VIP & DONATE TIZIMI**\n\n"
        "Vesteros olamining eng qudratli lordlari va hukmdorlari uchun maxsus to'plamlar!\n"
        "Har bir to'plam sizga daxlsizlik qalqoni, ulkan xazina, yangi askarlar va hatto jangovar ajdaho taqdim etadi.\n\n"
        f"💳 **To'lov usuli:** O'zbekiston bank kartalari (Humo / Uzcard)\n"
        f"🛡️ **Xavfsizlik:** To'lov cheki yuborilgach, mukofotlar to'g'ridan-to'g'ri profilingizga biriktiriladi.\n\n"
        "👇 *Kerakli to'plamni tanlang:*"
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
        "💎 **WESTEROS AFSONAVIY VIP & DONATE TIZIMI**\n\n"
        "Vesteros olamining eng qudratli lordlari va hukmdorlari uchun maxsus to'plamlar!\n"
        "Har bir to'plam sizga daxlsizlik qalqoni, ulkan xazina, yangi askarlar va hatto jangovar ajdaho taqdim etadi.\n\n"
        f"💳 **To'lov usuli:** O'zbekiston bank kartalari (Humo / Uzcard)\n"
        f"🛡️ **Xavfsizlik:** To'lov cheki yuborilgach, mukofotlar to'g'ridan-to'g'ri profilingizga biriktiriladi.\n\n"
        "👇 *Kerakli to'plamni tanlang:*"
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
    await donate_menu_callback(update, context)


async def donate_receipt_receiver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi yuborgan to'lov chekini qabul qilish va adminga uzatish"""
    tier_id = context.user_data.get("awaiting_receipt_tier")
    if not tier_id:
        return

    tier = DONATE_TIERS.get(tier_id)
    if not tier:
        context.user_data.pop("awaiting_receipt_tier", None)
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

    # Holatni tozalaymiz
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

    # Admin xabarini yangilash
    admin_name = admin_user.full_name
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
    tier_name = "VIP To'plam"
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
        f"📦 To'plam: *{tier_name}*\n"
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
        f"Hurmatli Lord, siz yuborgan «**{tier_name}**» to'plami bo'yicha to'lov cheki ma'muriyat tomonidan tasdiqlanmadi.\n\n"
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



def register_donate_handlers(app):
    """Donate handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["donate", "vip", "donat", "homiylik"], donate_command))
    app.add_handler(CallbackQueryHandler(donate_menu_callback, pattern="^menu_donate$"))
    app.add_handler(CallbackQueryHandler(donate_pick_callback, pattern="^donate_pick:"))
    app.add_handler(CallbackQueryHandler(donate_submit_callback, pattern="^donate_submit:"))
    app.add_handler(CallbackQueryHandler(donate_cancel_callback, pattern="^donate_cancel_receipt$"))
    app.add_handler(CallbackQueryHandler(admin_donate_approve_callback, pattern="^admin_donate_approve:"))
    app.add_handler(CallbackQueryHandler(admin_donate_reject_callback, pattern="^admin_donate_reject:"))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, donate_receipt_receiver), group=1)
