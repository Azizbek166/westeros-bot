import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from database.db import AsyncSessionLocal
from database import crud, models


async def show_daily_menu(target, user_id: int, is_message: bool = False):
    """Kunlik Tuhfalar va Mukofotlar Markazi (Daily Rewards Hub)"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            msg = "❌ Avval botdan ro'yxatdan o'tish uchun /start bosing."
            if is_message:
                await target.reply_text(msg)
            else:
                await target.message.reply_text(msg)
            return

        await crud.check_and_reset_daily_limits(session, user)

        now = datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")

        # 1. Streak holati
        streak_count = user.streak_count or 1
        is_streak_claimed = (user.last_streak_date == today_str)
        if is_streak_claimed:
            remaining_hours = 23 - now.hour
            remaining_mins = 59 - now.minute
            next_day = (streak_count % 7) + 1
            streak_status_line = f"✅ Bugungi tuhfa qabul qilingan!\n⏳ {next_day}-kun sovg'asi: `{remaining_hours}s {remaining_mins}d` dan so'ng ochiladi."
        else:
            cur_reward = crud.STREAK_REWARDS.get(streak_count, crud.STREAK_REWARDS[1])
            streak_status_line = f"🎁 **Bugungi {streak_count}-kun tuhfasi tayyor!**\n└ _Sovrin: {cur_reward['gold']:,}🪙 {cur_reward['food']:,}🌾 {cur_reward['iron']:,}⛓️_"

        # 2. Omad Sandig'i holati
        chest_date = getattr(user, "daily_chest_date", "") or ""
        is_chest_claimed = (chest_date == today_str)
        if is_chest_claimed:
            remaining_hours = 23 - now.hour
            remaining_mins = 59 - now.minute
            chest_status_line = f"⏳ Bugun ochilgan (Yangi sandiq `{remaining_hours}s {remaining_mins}d` dan so'ng)"
        else:
            chest_status_line = "🔓 **1 marta bepul ochishga tayyor!** (Valiriya xazinasi, oltinlar, qo'shinlar)"

        # 3. Kunlik Vazifalar holati
        q_data = await crud.get_daily_quests_data(session, user)
        done_count = q_data["done_count"]
        unclaimed_count = sum(1 for q in q_data["quests"].values() if q["is_done"] and not q["is_claimed"])

        if unclaimed_count > 0:
            quest_alert = f"🔔 **{unclaimed_count} ta mukofot olishga tayyor!**"
        elif done_count == 4:
            quest_alert = "🌟 Barcha vazifalar to'liq bajarildi!"
        else:
            quest_alert = f"⚔️ {4 - done_count} ta vazifa qoldi"

        # Taqvimi
        calendar_text = crud.format_streak_calendar(streak_count, claimed_today=is_streak_claimed)
        house = user.house

        text = (
            f"╔══════════════════════════════╗\n"
            f"   👑 **QIROLLIK TUHFALARI VA MUKOFOTLARI** 🎁\n"
            f"╚══════════════════════════════╝\n\n"
            f"Hurmatli Lord **{user.username}**{f' ({house.name})' if house else ''}!\n"
            f"Vesteros qirollik saroyi va xazinaboni siz uchun har kungi in'omlarni taqdim etadi:\n\n"
            f"🔥 **Uzluksiz Kirish (Streak):** `{streak_count}/7-kun`\n"
            f"{streak_status_line}\n\n"
            f"🎰 **Qirollik Omad Sandig'i:**\n"
            f"{chest_status_line}\n\n"
            f"🎯 **Kunlik Faollik Vazifalari:** `{done_count}/4 ta bajarildi`\n"
            f"{quest_alert}\n\n"
            f"📅 **7 Kunlik Tuhfalar Taqvimi:**\n"
            f"{calendar_text}\n\n"
            f"💡 _Har kuni kiring: 7-kunda Katta Valiriya Xazinasi va doimiy Omad Sandig'ini qo'lga kiriting!_"
        )

        buttons = []

        # Row 1: Streak claim / status
        if not is_streak_claimed:
            buttons.append([
                InlineKeyboardButton(f"🎁 {streak_count}-Kun Tuhfasini Olish", callback_data="daily_claim_streak")
            ])
        else:
            buttons.append([
                InlineKeyboardButton(f"✅ Bugungi Tuhfa Olingan ({streak_count}/7)", callback_data="daily_streak_already")
            ])

        # Row 2: Lucky Chest
        if not is_chest_claimed:
            buttons.append([
                InlineKeyboardButton("🎰 Qirollik Omad Sandig'i (Bepul Ochish)", callback_data="daily_open_chest")
            ])
        else:
            buttons.append([
                InlineKeyboardButton("⏳ Omad Sandig'i Ochilgan", callback_data="daily_chest_already")
            ])

        # Row 3: Daily Quests
        quest_btn_text = f"🎯 Kunlik Vazifalar ({done_count}/4)"
        if unclaimed_count > 0:
            quest_btn_text += f" 🎁+{unclaimed_count}"
        buttons.append([
            InlineKeyboardButton(quest_btn_text, callback_data="daily_quests_menu")
        ])

        # Row 4: Detailed Calendar & Main Menu
        buttons.append([
            InlineKeyboardButton("📅 7 Kunlik Sovg'alar Ro'yxati", callback_data="daily_calendar")
        ])
        buttons.append([
            InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")
        ])

        markup = InlineKeyboardMarkup(buttons)

        if is_message:
            await target.reply_text(text, parse_mode="Markdown", reply_markup=markup)
        else:
            try:
                await target.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
            except Exception:
                await target.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def daily_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kunlik tuhfalar bo'limi ochilishi"""
    query = update.callback_query
    if query:
        await query.answer()
        await show_daily_menu(query, update.effective_user.id, is_message=False)
    else:
        await show_daily_menu(update.effective_message, update.effective_user.id, is_message=True)


async def daily_claim_streak_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """7 kunlik kirish (streak) mukofotini qabul qilish"""
    query = update.callback_query
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.claim_daily_bonus(session, user.id)

    if ok:
        await query.answer("🎉 Tabriklaymiz! Kunlik tuhfa xazinangizga qo'shildi!", show_alert=False)
    else:
        await query.answer("⏳ Bugungi tuhfa allaqachon olingan!", show_alert=True)

    buttons = [
        [InlineKeyboardButton("🎰 Omad Sandig'ini Ochish", callback_data="daily_open_chest")],
        [InlineKeyboardButton("🎯 Kunlik Faollik Vazifalari", callback_data="daily_quests_menu")],
        [InlineKeyboardButton("🎁 Kunlik Tuhfalar Markazi", callback_data="menu_daily")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ]
    markup = InlineKeyboardMarkup(buttons)

    try:
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=markup)


async def daily_open_chest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qirollik Omad Sandig'ini ochish"""
    query = update.callback_query
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg, reward = await crud.open_daily_lucky_chest(session, user.id)

    if ok:
        await query.answer("🎰 Omad Sandig'i ochildi!", show_alert=False)
    else:
        await query.answer("⏳ Bugun omad sandig'ini ochib bo'lgansiz!", show_alert=True)

    buttons = [
        [InlineKeyboardButton("🎁 7 Kunlik Tuhfani Olish", callback_data="daily_claim_streak")],
        [InlineKeyboardButton("🎯 Kunlik Vazifalar", callback_data="daily_quests_menu")],
        [InlineKeyboardButton("🎁 Kunlik Tuhfalar Markazi", callback_data="menu_daily")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ]
    markup = InlineKeyboardMarkup(buttons)

    try:
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=markup)


async def show_daily_quests_menu(target, user_id: int, is_message: bool = False):
    """Kunlik Faollik Vazifalari menyusi"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return

        q_data = await crud.get_daily_quests_data(session, user)
        quests = q_data["quests"]
        done_count = q_data["done_count"]
        grand_done = q_data["grand_done"]
        grand_claimed = q_data["grand_claimed"]

        # Matn shakllantirish
        lines = [
            "╔══════════════════════════════╗",
            "   🎯 **KUNLIK FAOLLIK VAZIFALARI** 🏆",
            "╚══════════════════════════════╝\n",
            f"Har kuni Vesteros bo'ylab faollik ko'rsating va qo'shimcha boyliklarni qo'lga kiriting!\n",
            f"📊 **Bugungi umumiy natija:** `{done_count}/4 ta vazifa bajarildi`\n",
        ]

        # 4 ta vazifa holati
        quest_keys = [("duel", "1"), ("citadel", "2"), ("recruit", "3"), ("caravan", "4")]
        buttons = []

        for q_key, num in quest_keys:
            q = quests[q_key]
            status_icon = "✅" if q["is_claimed"] else ("🎁" if q["is_done"] else "⏳")
            status_text = "Olingan" if q["is_claimed"] else ("Mukofot tayyor!" if q["is_done"] else f"Bajarilmagan ({q['current']}/{q['target']})")

            lines.append(f"**{num}. {q['title']}** [{status_icon} {status_text}]")
            lines.append(f"   _{q['desc']}_")
            lines.append(f"   💰 Mukofot: {q['reward_desc']}\n")

            # Agar bajarilgan va olinmagan bo'lsa tugma chiqaramiz
            if q["is_done"] and not q["is_claimed"]:
                buttons.append([
                    InlineKeyboardButton(f"🎁 {num}-Vazifa Mukofotini Olish", callback_data=f"daily_claim_quest:{q_key}")
                ])

        # Grand Bonus holati
        grand_q = quests["grand"]
        g_icon = "✅" if grand_claimed else ("👑" if grand_done else "🔒")
        g_status = "Olingan" if grand_claimed else ("TAYYOR! OLISHINGIZ MUMKIN!" if grand_done else f"{done_count}/4 ta bajarildi")

        lines.append("───────────────────────────────")
        lines.append(f"👑 **BARCHA VAZIFALAR GRAND-BONUSI** [{g_icon} {g_status}]")
        lines.append(f"   _{grand_q['desc']}_")
        lines.append(f"   🌟 Mukofot: {grand_q['reward_desc']}")

        if grand_done and not grand_claimed:
            buttons.insert(0, [
                InlineKeyboardButton("👑 GRAND-BONUSNI OLISH (+12,000🪙, +25 Gvardiya...) 👑", callback_data="daily_claim_quest:grand")
            ])

        # Pastki navigatsiya
        nav_row = [
            InlineKeyboardButton("🎁 Kunlik Markaz", callback_data="menu_daily"),
            InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main"),
        ]
        buttons.append(nav_row)

        markup = InlineKeyboardMarkup(buttons)
        text = "\n".join(lines)

        if is_message:
            await target.reply_text(text, parse_mode="Markdown", reply_markup=markup)
        else:
            try:
                await target.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
            except Exception:
                await target.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def daily_quests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vazifalar menyusi callback"""
    query = update.callback_query
    await query.answer()
    await show_daily_quests_menu(query, update.effective_user.id, is_message=False)


async def daily_claim_quest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aynan bitta vazifa mukofotini qabul qilish"""
    query = update.callback_query
    user_id = update.effective_user.id
    quest_key = query.data.split(":")[1]

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return

        ok, msg = await crud.claim_daily_quest_reward(session, user.id, quest_key)

    if ok:
        await query.answer("🎁 Mukofot qabul qilindi!", show_alert=False)
    else:
        await query.answer(f"⚠️ {msg}", show_alert=True)
        return

    # Menyuni yangilash
    await show_daily_quests_menu(query, user_id, is_message=False)


async def show_daily_calendar_menu(target, user_id: int):
    """7 kunlik barcha sovg'alar tafsilotlari"""
    lines = [
        "╔══════════════════════════════╗",
        "   📅 **7 KUNLIK SOVG'ALAR TAFSILOTI** 🎁",
        "╚══════════════════════════════╝\n",
        "Har kuni uzluksiz botga kirgan lordlar quyidagi shohona in'omlarga ega bo'ladilar:\n",
    ]

    for day in range(1, 8):
        info = crud.STREAK_REWARDS[day]
        lines.append(f"👑 **{info['title']}**")
        lines.append(f"   • 🪙 Oltin: **+{info['gold']:,}** | 🌾 Oziq: **+{info['food']:,}** | ⛓️ Temir: **+{info['iron']:,}**")
        lines.append(f"   • 🏆 Nufuz: **+{info['prestige']:,}** | ⭐ Tajriba: **+{info['xp']:,} XP**")
        if info.get("extra_desc"):
            lines.append(f"   • {info['extra_desc']}")
        lines.append("")

    lines.append("───────────────────────────────")
    lines.append("📌 **Muhim qoidalar:**")
    lines.append("1. Agar biror kun botga kirmasangiz, streak 1-kunga qaytib ketadi!")
    lines.append("2. 7-kunning Super Valiriya Tuhfasini olganingizdan so'ng, yangi 7 kunlik tsikl boshlanadi.")
    lines.append("3. Har kuni bundan tashqari **Qirollik Omad Sandig'i**ni 1 marta bepul ochishingiz mumkin!")

    buttons = [
        [InlineKeyboardButton("🎁 Kunlik Tuhfalar Saroyiga Qaytish", callback_data="menu_daily")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ]
    markup = InlineKeyboardMarkup(buttons)
    text = "\n".join(lines)

    try:
        await target.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        await target.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def daily_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kalendar ko'rish callback"""
    query = update.callback_query
    await query.answer()
    await show_daily_calendar_menu(query, update.effective_user.id)


async def daily_streak_already_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Streak allaqachon olingan bo'lsa xabar berish"""
    query = update.callback_query
    now = datetime.utcnow()
    remaining_hours = 23 - now.hour
    remaining_mins = 59 - now.minute
    await query.answer(
        f"✅ Bugungi kunlik tuhfani allaqachon olgansiz!\nNavbatdagi tuhfa {remaining_hours} soat {remaining_mins} daqiqadan so'ng (ertaga) ochiladi.",
        show_alert=True
    )


async def daily_chest_already_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Omad sandig'i allaqachon ochilgan bo'lsa xabar berish"""
    query = update.callback_query
    now = datetime.utcnow()
    remaining_hours = 23 - now.hour
    remaining_mins = 59 - now.minute
    await query.answer(
        f"⏳ Qirollik omad sandig'ini bugun ochib bo'lgansiz!\nYangi bepul sandiq {remaining_hours} soat {remaining_mins} daqiqadan so'ng ochiladi.",
        show_alert=True
    )


def register_daily_handlers(app):
    """Kunlik tuhfalar bo'yicha barcha handlerlarni ro'yxatdan o'tkazish"""
    # Buyruqlar
    app.add_handler(CommandHandler(["daily", "bonus", "tuhfa", "sovga", "sovg'a", "sandiq", "omad"], daily_menu_callback))

    # Callbacklar
    app.add_handler(CallbackQueryHandler(daily_menu_callback, pattern="^menu_daily$"))
    app.add_handler(CallbackQueryHandler(daily_menu_callback, pattern="^claim_daily_bonus$")) # eski tugmalar uchun moslik
    app.add_handler(CallbackQueryHandler(daily_claim_streak_callback, pattern="^daily_claim_streak$"))
    app.add_handler(CallbackQueryHandler(daily_open_chest_callback, pattern="^daily_open_chest$"))
    app.add_handler(CallbackQueryHandler(daily_quests_callback, pattern="^daily_quests_menu$"))
    app.add_handler(CallbackQueryHandler(daily_claim_quest_callback, pattern="^daily_claim_quest:"))
    app.add_handler(CallbackQueryHandler(daily_calendar_callback, pattern="^daily_calendar$"))
    app.add_handler(CallbackQueryHandler(daily_streak_already_callback, pattern="^daily_streak_already$"))
    app.add_handler(CallbackQueryHandler(daily_chest_already_callback, pattern="^daily_chest_already$"))
