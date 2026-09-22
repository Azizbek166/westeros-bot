import html
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from keyboards.menus import back_to_main_keyboard


async def bank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/bank buyrug'i"""
    user_id = update.effective_user.id
    await show_bank_hub(update, user_id, is_message=True)


async def bank_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_bank callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_bank_hub(query, user_id, is_message=False)


async def show_bank_hub(target, user_id: int, is_message: bool = False):
    """Braavos Temir Banki asosiy zali"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        bank = await crud.get_or_create_iron_bank(session, user.id)

        # Omonat hisobi
        dep_gold = bank.deposit_gold or 0
        daily_yield = int(dep_gold * crud.DAILY_INTEREST_RATE)

        # Foiz olish vaqti (soatbay hisoblanadi, kuniga 0.375%)
        now = datetime.utcnow()
        last_claim = bank.last_interest_claimed_at or bank.deposit_updated_at or now
        elapsed_sec = max(0, (now - last_claim).total_seconds())
        hours_ready = int(elapsed_sec // 3600)
        accumulated_interest = int(dep_gold * (crud.DAILY_INTEREST_RATE / 24.0) * hours_ready) if hours_ready >= 1 else 0
        mins_left = max(1, int((3600 - (elapsed_sec % 3600)) // 60))

        if dep_gold > 0:
            if hours_ready >= 1:
                hours_str = f"{hours_ready // 24} kun {hours_ready % 24} soatlik" if hours_ready >= 24 else f"{hours_ready} soatlik"
                interest_status_str = f"<b>+{accumulated_interest:,}🪙</b> ({hours_str})"
            else:
                interest_status_str = f"<b>0🪙</b> <i>(keyingi foiz: ~{mins_left} daq)</i>"
        else:
            interest_status_str = "<b>0🪙</b>"

        # Qarz hisobi
        loan_gold = bank.loan_gold or 0
        total_loan_due = int(loan_gold * 1.10) if loan_gold > 0 else 0

        loan_status_str = "Hozirda qarzingiz yo'q ✅"
        if loan_gold > 0:
            if bank.loan_due_at:
                diff_sec = (bank.loan_due_at - now).total_seconds()
                if diff_sec > 0:
                    d_left = int(diff_sec // 86400)
                    h_left = int((diff_sec % 86400) // 3600)
                    loan_status_str = f"Muddati: <b>{d_left} kun {h_left} soat qoldi</b>"
                else:
                    loan_status_str = "🚨 <b>MUDDATI O'TIB KETGAN (MUBORAK 'OLTIN GALA' KELMOQDA)!</b>"
            else:
                loan_status_str = "Muddati: 5 kun"

        text = (
            f"🏛️ <b>BRAAVOS TEMIR BANKI (THE IRON BANK)</b>\n\n"
            f"<i>'Temir Bank o'z haqini har doim oladi!'</i>\n\n"
            f"💰 Hamyoningiz: <b>{user.gold:,}🪙 Oltin</b>\n\n"
            f"──────── <b>OMONAT BO'LIMI</b> ────────\n"
            f"• Saqlanayotgan oltin: <b>{dep_gold:,} / 50,000🪙</b>\n"
            f"• Kunlik daromad: <b>+{daily_yield:,}🪙/kun</b> (+0.375%)\n"
            f"• Yig'ilgan tayyor foiz: {interest_status_str}\n\n"
            f"──────── <b>KREDIT (QARZ) BO'LIMI</b> ────────\n"
            f"• Asosiy qarz: <b>{loan_gold:,}🪙</b>\n"
            f"• Qaytarilishi kerak: <b>{total_loan_due:,}🪙</b> (+10% foiz)\n"
            f"• Holati: {loan_status_str}\n\n"
            f"Quyidagi amallardan birini tanlang:"
        )

        buttons = []

        # Omonat tugmalari
        dep_row = []
        if dep_gold < 50000:
            dep_row.append(InlineKeyboardButton("📥 Omonat Qo'yish", callback_data="bank_dep_menu"))
        if dep_gold > 0:
            dep_row.append(InlineKeyboardButton("📤 Omonatni Yechish", callback_data="bank_with_menu"))
        if dep_row:
            buttons.append(dep_row)

        if accumulated_interest > 0:
            buttons.append([InlineKeyboardButton(f"🪙 Foizni Yechib Olish (+{accumulated_interest:,}🪙)", callback_data="bank_claim_int")])
        elif dep_gold > 0:
            buttons.append([InlineKeyboardButton(f"⏳ Foiz to'planmoqda (~{mins_left} daqiqa)", callback_data="bank_int_wait_info")])

        # Qarz tugmalari
        if loan_gold <= 0:
            buttons.append([InlineKeyboardButton("📜 Qarz Olish (Kredit)", callback_data="bank_loan_menu")])
        else:
            buttons.append([InlineKeyboardButton(f"💰 Qarzni Qaytarish ({total_loan_due:,}🪙)", callback_data="bank_repay_loan")])

        buttons.append([InlineKeyboardButton("⚖️ Savdo Bozoriga O'tish", callback_data="menu_trade")])
        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        markup = InlineKeyboardMarkup(buttons)
        if is_message:
            await target.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        else:
            await target.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def bank_dep_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Omonat qo'yish miqdorini tanlash menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_any(session, user_id)
        if not user:
            return
        bank = await crud.get_or_create_iron_bank(session, user.id)

    curr_dep = bank.deposit_gold or 0
    max_add = max(0, 50000 - curr_dep)
    if max_add <= 0:
        await query.answer("❌ Omonat limiti to'lgan (Maksimal: 50,000🪙)!", show_alert=True)
        return

    text = (
        f"📥 <b>BRAAVOS TEMIR BANKIGA OMONAT QO'YISH</b>\n\n"
        f"Omonatga qo'yilgan har bir oltin sizga kuniga <b>+1.5%</b> sof foyda keltiradi!\n"
        f"Maksimal depozit: <b>50,000🪙</b> (siz yana ko'pi bilan <b>{max_add:,}🪙</b> qo'ya olasiz).\n\n"
        f"Hamyoningizda mavjud: <b>{user.gold:,}🪙 Oltin</b>\n\n"
        f"Qancha oltin omonatga qo'ymoqchisiz?"
    )

    max_can_dep = min(user.gold or 0, max_add)

    buttons = [
        [
            InlineKeyboardButton("🪙 1,000", callback_data="bank_dep_do:1000"),
            InlineKeyboardButton("🪙 5,000", callback_data="bank_dep_do:5000"),
            InlineKeyboardButton("🪙 10,000", callback_data="bank_dep_do:10000"),
        ],
        [
            InlineKeyboardButton("🪙 25,000", callback_data="bank_dep_do:25000"),
            InlineKeyboardButton(
                "🪙 Hammasi (MAX)", 
                callback_data=f"bank_dep_do:{max_can_dep}" if max_can_dep > 0 else "bank_dep_empty_alert"
            ),
        ],
        [
            InlineKeyboardButton("✍️ Qo'lda Yozib Qo'yish", callback_data="bank_custom_dep"),
        ],
        [InlineKeyboardButton("🔙 Bank Zaliga Qaytish", callback_data="menu_bank")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def bank_dep_empty_alert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Omonat qo'yish uchun oltin yetarli emasligi haqida ogohlantirish"""
    query = update.callback_query
    await query.answer("❌ Hamyoningizda omonatga qo'yish uchun yetarli oltin yo'q!", show_alert=True)


async def bank_custom_dep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'lda kiritish orqali omonat qo'yish so'rovi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_any(session, user_id)
        if not user:
            return
        bank = await crud.get_or_create_iron_bank(session, user.id)

    curr_dep = bank.deposit_gold or 0
    max_add = max(0, 50000 - curr_dep)
    if max_add <= 0:
        await query.answer("❌ Maksimal depozit limitiga yetgansiz (50,000🪙)!", show_alert=True)
        return

    context.user_data["awaiting_bank_dep_input"] = True

    text = (
        f"✍️ <b>OMONATGA QO'YISH (QO'LDA KIRITISH)</b>\n\n"
        f"💰 Hamyoningizda: <b>{user.gold:,}🪙 Oltin</b>\n"
        f"🏛️ Hozirgi depozitingiz: <b>{curr_dep:,} / 50,000🪙</b>\n"
        f"📥 Qo'yishingiz mumkin bo'lgan maksimal miqdor: <b>{min(user.gold, max_add):,}🪙</b>\n\n"
        f"Qancha oltin omonatga qo'ymoqchisiz? Quyida sonni yozing (masalan: <code>3500</code>) yoki barchasini qo'yish uchun <code>all</code> deb yuboring:"
    )
    buttons = [
        [InlineKeyboardButton("🔙 Bekor Qilish", callback_data="bank_dep_menu")]
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def bank_dep_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Omonat qo'yish ijrosi"""
    query = update.callback_query
    raw_val = query.data.split(":")[1]
    try:
        amount = int(raw_val)
    except ValueError:
        amount = 0

    user_id = query.from_user.id

    if amount <= 0:
        await query.answer("❌ Noto'g'ri summa yoki hamyoningizda yetarli oltin yo'q!", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.deposit_to_iron_bank(session, user_id, amount)

    await query.answer(msg[:150], show_alert=True)
    await show_bank_hub(query, user_id, is_message=False)


async def bank_with_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Omonatni qaytarib olish menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_any(session, user_id)
        if not user:
            return
        bank = await crud.get_or_create_iron_bank(session, user.id)

    curr_dep = bank.deposit_gold or 0
    if curr_dep <= 0:
        await query.answer("❌ Bankda faol omonatingiz mavjud emas!", show_alert=True)
        return

    text = (
        f"📤 <b>OMONATNI YECHIB OLISH</b>\n\n"
        f"Temir Bankdagi depozitingiz: <b>{curr_dep:,}🪙 Oltin</b>\n\n"
        f"Qancha mablag'ni hamyoningizga qaytarib olmoqchisiz?"
    )

    buttons = [
        [
            InlineKeyboardButton("🪙 1,000", callback_data="bank_with_do:1000"),
            InlineKeyboardButton("🪙 5,000", callback_data="bank_with_do:5000"),
            InlineKeyboardButton("🪙 10,000", callback_data="bank_with_do:10000"),
        ],
        [
            InlineKeyboardButton("🪙 Barchasini Yechish", callback_data="bank_with_do:all"),
        ],
        [
            InlineKeyboardButton("✍️ Qo'lda Yozib Yechish", callback_data="bank_custom_with"),
        ],
        [InlineKeyboardButton("🔙 Bank Zaliga Qaytish", callback_data="menu_bank")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def bank_custom_with_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'lda kiritish orqali omonatni yechish so'rovi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_any(session, user_id)
        if not user:
            return
        bank = await crud.get_or_create_iron_bank(session, user.id)

    curr_dep = bank.deposit_gold or 0
    if curr_dep <= 0:
        await query.answer("❌ Bankda faol omonatingiz mavjud emas!", show_alert=True)
        return

    context.user_data["awaiting_bank_with_input"] = True

    text = (
        f"✍️ <b>OMONATNI YECHISH (QO'LDA KIRITISH)</b>\n\n"
        f"🏛️ Bankdagi depozitingiz: <b>{curr_dep:,}🪙 Oltin</b>\n\n"
        f"Qancha oltin yechib olmoqchisiz? Quyida sonni yozing (masalan: <code>2500</code>) yoki barchasini yechish uchun <code>all</code> deb yuboring:"
    )
    buttons = [
        [InlineKeyboardButton("🔙 Bekor Qilish", callback_data="bank_with_menu")]
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def bank_with_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Omonatni yechish ijrosi"""
    query = update.callback_query
    raw_val = query.data.split(":")[1]
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        if raw_val == "all":
            user = await crud.get_user_any(session, user_id)
            if not user:
                return
            bank = await crud.get_or_create_iron_bank(session, user.id)
            amount = bank.deposit_gold or 0
        else:
            try:
                amount = int(raw_val)
            except ValueError:
                amount = 0

        if amount <= 0:
            await query.answer("❌ Omonatda yechish uchun mablag' yo'q!", show_alert=True)
            return

        ok, msg = await crud.withdraw_from_iron_bank(session, user_id, amount)

    await query.answer(msg[:150], show_alert=True)
    await show_bank_hub(query, user_id, is_message=False)


async def bank_claim_int_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kunlik / soatlik to'plangan foizni olish"""
    query = update.callback_query
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.claim_iron_bank_interest(session, user_id)

    await query.answer(msg[:150], show_alert=True)
    await show_bank_hub(query, user_id, is_message=False)


async def bank_int_wait_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foiz to'planishi haqida ma'lumot beruvchi bildirishnoma"""
    query = update.callback_query
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_any(session, user_id)
        if not user:
            await query.answer()
            return
        bank = await crud.get_or_create_iron_bank(session, user.id)

    now = datetime.utcnow()
    last_claim = bank.last_interest_claimed_at or bank.deposit_updated_at or now
    elapsed_sec = max(0, (now - last_claim).total_seconds())
    rem_mins = max(1, int((3600 - (elapsed_sec % 3600)) // 60))
    await query.answer(
        f"⏳ Omonat foizlari har 1 soatda to'planadi (kuniga +0.375%).\nKeyingi foiz tushishiga taxminan {rem_mins} daqiqa qoldi!",
        show_alert=True
    )


async def bank_loan_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qarz olish menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        is_lord = (user.house and user.house.lord_user_id == user.telegram_id) or (user.rank == "king")
        max_loan = 30000 if is_lord else 10000

    text = (
        f"📜 <b>BRAAVOS TEMIR BANKIDAN QARZ (KREDIT) OLISH</b>\n\n"
        f"Zudlik bilan armiya to'plash yoki qal'alarni mustahkamlash uchun oltin kerakmi? "
        f"Temir Bank sizga kerakli mablag'ni taqdim etadi!\n\n"
        f"⚖️ <b>SHARTLAR:</b>\n"
        f"• Kredit muddati: <b>5 kun (120 soat)</b>\n"
        f"• Foiz stavkasi: <b>+10%</b>\n"
        f"• Siz uchun maksimal qarz: <b>{max_loan:,}🪙 Oltin</b> {'(Lord imtiyozi)' if is_lord else ''}\n\n"
        f"☠️ <i>Eslatma: Agar qarz 5 kun ichida qaytarilmasa, Temir Bank sizga qarshi 'Oltin Gala' yollanma armiyasini jo'natadi!</i>"
    )

    buttons = [
        [
            InlineKeyboardButton("🪙 5,000 Olish", callback_data="bank_loan_do:5000"),
            InlineKeyboardButton("🪙 10,000 Olish", callback_data="bank_loan_do:10000"),
        ],
    ]
    if max_loan >= 30000:
        buttons.append([
            InlineKeyboardButton("👑 20,000 Olish (Lord)", callback_data="bank_loan_do:20000"),
            InlineKeyboardButton("👑 30,000 Olish (MAX)", callback_data="bank_loan_do:30000"),
        ])
    buttons.append([InlineKeyboardButton("🔙 Bank Zaliga Qaytish", callback_data="menu_bank")])

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def bank_loan_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qarz olish ijrosi"""
    query = update.callback_query
    amount = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.take_iron_bank_loan(session, user_id, amount)

    await query.answer(msg[:150], show_alert=True)
    await show_bank_hub(query, user_id, is_message=False)


async def bank_repay_loan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qarzni to'lash ijrosi"""
    query = update.callback_query
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.repay_iron_bank_loan(session, user_id)

    await query.answer(msg[:150], show_alert=True)
    await show_bank_hub(query, user_id, is_message=False)


def register_bank_handlers(app):
    app.add_handler(CommandHandler(["bank", "ironbank"], bank_command))
    app.add_handler(CallbackQueryHandler(bank_callback, pattern="^menu_bank$"))
    app.add_handler(CallbackQueryHandler(bank_dep_menu_callback, pattern="^bank_dep_menu$"))
    app.add_handler(CallbackQueryHandler(bank_dep_empty_alert_callback, pattern="^bank_dep_empty_alert$"))
    app.add_handler(CallbackQueryHandler(bank_custom_dep_callback, pattern="^bank_custom_dep$"))
    app.add_handler(CallbackQueryHandler(bank_dep_do_callback, pattern="^bank_dep_do:"))
    app.add_handler(CallbackQueryHandler(bank_with_menu_callback, pattern="^bank_with_menu$"))
    app.add_handler(CallbackQueryHandler(bank_custom_with_callback, pattern="^bank_custom_with$"))
    app.add_handler(CallbackQueryHandler(bank_with_do_callback, pattern="^bank_with_do:"))
    app.add_handler(CallbackQueryHandler(bank_claim_int_callback, pattern="^bank_claim_int$"))
    app.add_handler(CallbackQueryHandler(bank_int_wait_info_callback, pattern="^bank_int_wait_info$"))
    app.add_handler(CallbackQueryHandler(bank_loan_menu_callback, pattern="^bank_loan_menu$"))
    app.add_handler(CallbackQueryHandler(bank_loan_do_callback, pattern="^bank_loan_do:"))
    app.add_handler(CallbackQueryHandler(bank_repay_loan_callback, pattern="^bank_repay_loan$"))
