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
        daily_yield = int(dep_gold * 0.015)

        # Foiz olish vaqti
        now = datetime.utcnow()
        last_claim = bank.last_interest_claimed_at or bank.deposit_updated_at or now
        elapsed_sec = (now - last_claim).total_seconds()
        days_ready = int(elapsed_sec // 86400)
        accumulated_interest = int(dep_gold * 0.015 * days_ready) if days_ready >= 1 else 0

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
            f"• Kunlik daromad: <b>+{daily_yield:,}🪙/kun</b> (+1.5%)\n"
            f"• Yig'ilgan tayyor foiz: <b>{accumulated_interest:,}🪙</b> ({days_ready} kunlik)\n\n"
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
        bank = await crud.get_or_create_iron_bank(session, user_id)

    curr_dep = bank.deposit_gold or 0
    max_add = max(0, 50000 - curr_dep)

    text = (
        f"📥 <b>BRAAVOS TEMIR BANKIGA OMONAT QO'YISH</b>\n\n"
        f"Omonatga qo'yilgan har bir oltin sizga kuniga <b>+1.5%</b> sof foyda keltiradi!\n"
        f"Maksimal depozit: <b>50,000🪙</b> (siz yana ko'pi bilan <b>{max_add:,}🪙</b> qo'ya olasiz).\n\n"
        f"Hamyoningizda mavjud: <b>{user.gold:,}🪙 Oltin</b>\n\n"
        f"Qancha oltin omonatga qo'ymoqchisiz?"
    )

    buttons = [
        [
            InlineKeyboardButton("🪙 1,000", callback_data="bank_dep_do:1000"),
            InlineKeyboardButton("🪙 5,000", callback_data="bank_dep_do:5000"),
            InlineKeyboardButton("🪙 10,000", callback_data="bank_dep_do:10000"),
        ],
        [
            InlineKeyboardButton("🪙 25,000", callback_data="bank_dep_do:25000"),
            InlineKeyboardButton("🪙 Hammasi (MAX)", callback_data=f"bank_dep_do:{min(user.gold, max_add)}"),
        ],
        [InlineKeyboardButton("🔙 Bank Zaliga Qaytish", callback_data="menu_bank")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def bank_dep_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Omonat qo'yish ijrosi"""
    query = update.callback_query
    amount = int(query.data.split(":")[1])
    user_id = query.from_user.id

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
        bank = await crud.get_or_create_iron_bank(session, user_id)

    curr_dep = bank.deposit_gold or 0
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
            InlineKeyboardButton("🪙 Barchasini Yechish", callback_data=f"bank_with_do:{curr_dep}"),
        ],
        [InlineKeyboardButton("🔙 Bank Zaliga Qaytish", callback_data="menu_bank")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def bank_with_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Omonatni yechish ijrosi"""
    query = update.callback_query
    amount = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.withdraw_from_iron_bank(session, user_id, amount)

    await query.answer(msg[:150], show_alert=True)
    await show_bank_hub(query, user_id, is_message=False)


async def bank_claim_int_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kunlik to'plangan foizni olish"""
    query = update.callback_query
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.claim_iron_bank_interest(session, user_id)

    await query.answer(msg[:150], show_alert=True)
    await show_bank_hub(query, user_id, is_message=False)


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
    app.add_handler(CallbackQueryHandler(bank_dep_do_callback, pattern="^bank_dep_do:"))
    app.add_handler(CallbackQueryHandler(bank_with_menu_callback, pattern="^bank_with_menu$"))
    app.add_handler(CallbackQueryHandler(bank_with_do_callback, pattern="^bank_with_do:"))
    app.add_handler(CallbackQueryHandler(bank_claim_int_callback, pattern="^bank_claim_int$"))
    app.add_handler(CallbackQueryHandler(bank_loan_menu_callback, pattern="^bank_loan_menu$"))
    app.add_handler(CallbackQueryHandler(bank_loan_do_callback, pattern="^bank_loan_do:"))
    app.add_handler(CallbackQueryHandler(bank_repay_loan_callback, pattern="^bank_repay_loan$"))
