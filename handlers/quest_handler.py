import random
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud
from data.quests_data import MAIN_QUESTS, DAILY_QUESTS, SECRET_QUESTS
from data.quiz_data import CITADEL_QUIZ_QUESTIONS
from data.council_data import COUNCIL_DILEMMAS
from keyboards.menus import quests_menu_keyboard, back_to_main_keyboard
from config import escape_md, DAILY_QUIZ_LIMIT, DAILY_COUNCIL_LIMIT, DAILY_SECRET_QUEST_LIMIT, RANKS


async def quest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/quests buyrug'i"""
    text = (
        "📜 **WESTEROS VAZIFALARI VA QUESTLAR**\n\n"
        "Shon-sharaf, oltin va yangi askarlar yutib olish uchun vazifalar turini tanlang:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=quests_menu_keyboard())


async def quest_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_quests callback"""
    query = update.callback_query
    await query.answer()
    text = (
        "📜 **WESTEROS VAZIFALARI VA QUESTLAR**\n\n"
        "Shon-sharaf, oltin va yangi askarlar yutib olish uchun vazifalar turini tanlang:"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=quests_menu_keyboard())


async def quest_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asosiy hikoyaviy va qahramon questlari ro'yxati (Kunlik max 3 ta)"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if user:
            await crud.check_and_reset_daily_limits(session, user)
        cnt = user.daily_story_quest_count if user else 0

    text = (
        f"📜 **ASOSIY HIKOYA VA QAHRAMON TOPSHIRIQLARI**\n\n"
        f"📊 Bugungi imkoniyat: **{max(0, 3 - cnt)}/3** ta vazifa\n\n"
        f"Vesteros taqdirini hal qiluvchi buyuk ssenariy topshiriqlarini bajaring:\n\n"
    )

    buttons = []
    for q in MAIN_QUESTS:
        text += (
            f"**{q['title']}**\n"
            f"_{q['description']}_\n"
            f"🎁 Mukofot: +{q['reward_gold']:,}🪙, +{q['reward_food']:,}🌾, +{q['reward_iron']:,}⛓️, +{q['reward_xp']} XP\n\n"
        )
        buttons.append([InlineKeyboardButton(f"⚡ {q['title'][:25]} (Bajarish)", callback_data=f"qmain_do:{q['code']}")])

    buttons.append([InlineKeyboardButton("🔙 Questlarga Qaytish", callback_data="menu_quests")])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def quest_main_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asosiy/qahramon hikoyaviy questni bajarish (Kunlik max 3 ta)"""
    query = update.callback_query
    code = query.data.split(":")[1]
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        await crud.check_and_reset_daily_limits(session, user)
        if user.daily_story_quest_count >= 3:
            await query.answer("❌ Bugungi 3 ta ssenariy/qahramon topshirig'i limitingiz tugagan! Ertaga yangi vazifalar ochiladi.", show_alert=True)
            return

        target_quest = next((q for q in MAIN_QUESTS if q["code"] == code), None)
        if not target_quest:
            await query.answer("❌ Topshiriq topilmadi!", show_alert=True)
            return

        user.daily_story_quest_count += 1
        user.gold += target_quest["reward_gold"]
        user.food += target_quest["reward_food"]
        user.iron += target_quest["reward_iron"]
        user.xp += target_quest["reward_xp"]
        user.prestige += 30

        from core.leveling import check_user_level_up
        lvl_up, new_lvl, lvl_msg = check_user_level_up(user)

        await session.commit()

        extra = f"\n{lvl_msg}" if lvl_up else ""
        await query.answer(
            f"✅ {target_quest['title']} muvaffaqiyatli yakunlandi!\n+{target_quest['reward_gold']}🪙, +{target_quest['reward_xp']} XP ({user.daily_story_quest_count}/3){extra}",
            show_alert=True
        )

    await quest_main_callback(update, context)


async def quest_daily_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kunlik vazifalar ro'yxati va holati"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        await crud.check_and_reset_daily_limits(session, user)

        rec_cnt = getattr(user, "daily_recruit_count", 0) or 0
        quiz_cnt = getattr(user, "daily_quiz_count", 0) or 0
        council_cnt = getattr(user, "daily_council_count", 0) or 0
        duel_cnt = getattr(user, "daily_duel_count", 0) or 0

        rec_status = "✅ Bajarildi (+125🪙, +250🌾, +80 XP)" if rec_cnt >= 100 else f"⏳ Progress: **{rec_cnt}/100** ta askar"
        quiz_status = "✅ Bajarildi (+150🪙, +75⛓️, +100 XP)" if quiz_cnt >= 5 else f"⏳ Progress: **{quiz_cnt}/5** ta savol"
        council_status = "✅ Bajarildi (+100🪙, +200🌾, +70 XP)" if council_cnt >= 2 else f"⏳ Progress: **{council_cnt}/2** ta masala"
        duel_status = "✅ Bajarildi (+125🪙, +15 XP)" if duel_cnt >= 3 else f"⏳ Progress: **{duel_cnt}/3** ta jang"

        text = (
            "⭐ **BUGUNGI KUNLIK VAZIFALAR VA PROGRESS:**\n\n"
            f"1. 🛡️ **Yangi Qon (100 ta askar yollash)**\n"
            f"   {rec_status}\n\n"
            f"2. 📚 **Maester Saboqlari (5 ta savolga javob)**\n"
            f"   {quiz_status}\n\n"
            f"3. 👑 **Kengash Maslahati (2 ta masala)**\n"
            f"   {council_status}\n\n"
            f"4. ⚔️ **Duel Jasorati (3 ta jangda ishtirok)**\n"
            f"   {duel_status}\n\n"
            "Topshiriqlarni bajarish uchun quyidagi bo'limlarga o'ting:"
        )

        buttons = [
            [
                InlineKeyboardButton("🛡️ Askar Yollash", callback_data="menu_army"),
                InlineKeyboardButton("📚 Maester Saboqlari", callback_data="menu_citadel"),
            ],
            [
                InlineKeyboardButton("👑 Kengash Masalasi", callback_data="menu_council"),
                InlineKeyboardButton("⚔️ Duellar Arenasi", callback_data="menu_duel"),
            ],
            [InlineKeyboardButton("🔙 Questlarga Qaytish", callback_data="menu_quests")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def quest_secret_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yashirin tarmoqli vazifalar"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        await crud.check_and_reset_daily_limits(session, user)
        if user.daily_secret_quest_count >= DAILY_SECRET_QUEST_LIMIT:
            await query.answer(f"⛔ Bugungi yashirin vazifalar limitingiz ({DAILY_SECRET_QUEST_LIMIT}/{DAILY_SECRET_QUEST_LIMIT}) tugadi!\nErtaga yangi mish-mishlar ochiladi.", show_alert=True)
            return
        rem = DAILY_SECRET_QUEST_LIMIT - user.daily_secret_quest_count

    sq = random.choice(SECRET_QUESTS)
    context.user_data["current_secret_quest"] = sq

    buttons = []
    for i, ch in enumerate(sq["choices"]):
        buttons.append([InlineKeyboardButton(ch["text"], callback_data=f"secret_choice:{i}")])
    buttons.append([InlineKeyboardButton("🔙 Questlarga Qaytish", callback_data="menu_quests")])

    text = (
        f"🕵️ **{sq['title']}**\n\n"
        f"📊 Bugungi imkoniyat: **{rem}/{DAILY_SECRET_QUEST_LIMIT}**\n\n"
        f"{sq['situation']}\n\n"
        f"Qanday yo'l tutasiz?"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def secret_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yashirin quest tanlovi natijasi"""
    query = update.callback_query
    await query.answer()

    choice_idx = int(query.data.split(":")[1])
    sq = context.user_data.get("current_secret_quest", SECRET_QUESTS[0])
    chosen = sq["choices"][choice_idx]

    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if user:
            user.daily_secret_quest_count += 1
            user.gold = max(0, user.gold + chosen["gold_reward"])
            user.prestige = max(0, user.prestige + chosen["prestige_reward"])
            user.xp += 100
            await session.commit()

    gold_str = f"+{chosen['gold_reward']}" if chosen['gold_reward'] >= 0 else f"{chosen['gold_reward']}"
    prest_str = f"+{chosen['prestige_reward']}" if chosen['prestige_reward'] >= 0 else f"{chosen['prestige_reward']}"

    text = (
        f"🕵️ **QUEST NATIJASI**\n\n"
        f"{chosen['outcome']}\n\n"
        f"📊 **OQIBATLAR:**\n"
        f"🪙 Oltin: {gold_str}\n"
        f"🏆 Prestige: {prest_str}\n"
        f"⭐ XP: +100"
    )
    buttons = [[InlineKeyboardButton("🔙 Bosh Menyu", callback_data="menu_main")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ============================================================
# CITADEL QUIZ (VIKTORINA)
# ============================================================

async def citadel_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Citadel Maester viktorinasi savoli"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        await crud.check_and_reset_daily_limits(session, user)
        if user.daily_quiz_count >= DAILY_QUIZ_LIMIT:
            await query.answer(f"⛔ Bugungi viktorina limitingiz ({DAILY_QUIZ_LIMIT}/{DAILY_QUIZ_LIMIT}) tugadi!\nErtaga yangi saboqlar ochiladi.", show_alert=True)
            return
        rem = DAILY_QUIZ_LIMIT - user.daily_quiz_count

    q_idx = random.randrange(len(CITADEL_QUIZ_QUESTIONS))
    context.user_data["citadel_quiz_idx"] = q_idx

    question, options, correct_idx = CITADEL_QUIZ_QUESTIONS[q_idx]

    buttons = []
    for i, opt in enumerate(options):
        buttons.append([InlineKeyboardButton(opt, callback_data=f"cit_ans:{i}")])
    buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

    text = (
        f"📚 **CITADEL — MAESTER SABOQLARI**\n\n"
        f"📊 Bugungi imkoniyat: **{rem}/{DAILY_QUIZ_LIMIT}**\n\n"
        f"📜 Savol:\n**{question}**\n\n"
        f"To'g'ri javob uchun: **+75🪙 oltin, +25⛓️ temir va +50 XP**\n\n"
        f"Javobni tanlang:"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def citadel_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Citadel viktorinasi javobini tekshirish"""
    query = update.callback_query
    await query.answer()

    user_ans = int(query.data.split(":")[1])
    q_idx = context.user_data.get("citadel_quiz_idx", 0)
    question, options, correct_idx = CITADEL_QUIZ_QUESTIONS[q_idx]

    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return

        user.daily_quiz_count += 1
        if user_ans == correct_idx:
            user.gold += 75
            user.iron += 25
            user.xp += 50
            await session.commit()
            text = (
                "✅ **TO'G'RI JAVOB!**\n\n"
                "Maesterlar bilimingizni yuqori baholashdi.\n"
                f"💰 Mukofot: **+75🪙 oltin, +25⛓️ temir, +50 XP**\n"
                f"📊 Qolgan viktorinalar: **{max(0, DAILY_QUIZ_LIMIT - user.daily_quiz_count)}/{DAILY_QUIZ_LIMIT}**"
            )
        else:
            user.gold = max(0, user.gold - 12)
            await session.commit()
            correct_text = options[correct_idx]
            text = (
                f"❌ **NOTO'G'RI JAVOB!**\n\n"
                f"To'g'ri javob: **{correct_text}** edi.\n"
                f"💰 Jarima: -12🪙 oltin\n"
                f"📊 Qolgan viktorinalar: **{max(0, DAILY_QUIZ_LIMIT - user.daily_quiz_count)}/{DAILY_QUIZ_LIMIT}**"
            )

        if user.daily_quiz_count >= DAILY_QUIZ_LIMIT:
            user.gold += 150
            user.iron += 75
            user.xp += 100
            await session.commit()
            text += (
                "\n\n🎉 **TABRIKLAYMIZ! KUNLIK VAZIFA BAJARILDI: Maester Saboqlari (5/5)!**\n"
                "🎁 Mukofot hisobingizga o'tkazildi: **+150🪙 Oltin, +75⛓️ Temir, +100 XP**"
            )

    buttons = [
        [InlineKeyboardButton("📚 Yana Bir Savol", callback_data="menu_citadel")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ============================================================
# ROYAL COUNCIL (QIROLLIK KENGASHI)
# ============================================================

async def council_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qirollik kengashi masalasi"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        await crud.check_and_reset_daily_limits(session, user)
        if user.daily_council_count >= DAILY_COUNCIL_LIMIT:
            await query.answer(f"⛔ Bugungi Kengash masalalari limitingiz ({DAILY_COUNCIL_LIMIT}/{DAILY_COUNCIL_LIMIT}) tugadi!\nYangi masalalar ertaga ko'rib chiqiladi.", show_alert=True)
            return
        rem = DAILY_COUNCIL_LIMIT - user.daily_council_count

    c_idx = random.randrange(len(COUNCIL_DILEMMAS))
    context.user_data["council_idx"] = c_idx

    q_text, options, correct_idx, reward = COUNCIL_DILEMMAS[c_idx]

    buttons = []
    for i, opt in enumerate(options):
        buttons.append([InlineKeyboardButton(opt, callback_data=f"coun_ans:{i}")])
    buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

    text = (
        f"👑 **QIROLLIK KENGASHI MASALASI**\n\n"
        f"📊 Bugungi imkoniyat: **{rem}/{DAILY_COUNCIL_LIMIT}**\n\n"
        f"📜 Vaziyat:\n_{q_text}_\n\n"
        f"💰 Dono qaror uchun mukofot: **+{reward}🪙 oltin**\n\n"
        f"Qaroringizni qabul qiling:"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def council_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kengash qarorini tekshirish"""
    query = update.callback_query
    await query.answer()

    user_ans = int(query.data.split(":")[1])
    c_idx = context.user_data.get("council_idx", 0)
    q_text, options, correct_idx, reward = COUNCIL_DILEMMAS[c_idx]

    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return

        user.daily_council_count += 1
        if user_ans == correct_idx:
            user.gold += reward
            user.prestige += 20
            await session.commit()
            text = (
                f"✅ **DONO QAROR!**\n\n"
                f"Lordlar sizning tadbirkorligingizga qoyil qolishdi.\n"
                f"💰 Xazinaga: **+{reward}🪙 oltin, +20 Prestige**\n"
                f"📊 Qolgan masalalar: **{max(0, DAILY_COUNCIL_LIMIT - user.daily_council_count)}/{DAILY_COUNCIL_LIMIT}**"
            )
        else:
            await session.commit()
            text = (
                "❌ **NOTO'G'RI QAROR!**\n\n"
                "Bu qaror aholi orasida norozilikka sabab bo'ldi. Mukofot berilmadi.\n"
                f"📊 Qolgan masalalar: **{max(0, DAILY_COUNCIL_LIMIT - user.daily_council_count)}/{DAILY_COUNCIL_LIMIT}**"
            )

        if user.daily_council_count >= DAILY_COUNCIL_LIMIT:
            user.gold += 100
            user.food += 200
            user.xp += 70
            await session.commit()
            text += (
                "\n\n🎉 **TABRIKLAYMIZ! KUNLIK VAZIFA BAJARILDI: Kengash Maslahati (2/2)!**\n"
                "🎁 Mukofot hisobingizga o'tkazildi: **+100🪙 Oltin, +200🌾 Oziq-ovqat, +70 XP**"
            )

    buttons = [
        [InlineKeyboardButton("👑 Yana Bir Masala", callback_data="menu_council")],
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ============================================================
# RANK-SPECIFIC DUTIES (LAVOZIM TOPSHIRIQLARI)
# ============================================================

RANK_DUTIES = {
    "king": {
        "title": "👑 Xonadon Lordi (King) Vazifalari",
        "tasks": [
            {
                "id": "king_tax",
                "title": "💰 Viloyat soliqlari va hisobotlarni qabul qilish",
                "desc": "Viloyat maesterlari va mirzaboshilari hisobotlarini ko'rib chiqasiz.",
                "reward_text": "+100🪙 Oltin, +25🏆 Prestige, +80 XP",
                "gold": 100, "food": 25, "iron": 12, "prestige": 25, "xp": 80
            },
            {
                "id": "king_fortify",
                "title": "🏰 Bosh Qal'a istehkomlarini mustahkamlash",
                "desc": "Mudofaa devorlarini ko'zdan kechirib, muhandislarga buyruq berasiz.",
                "reward_text": "+75🌾 Oziq, +38⛓️ Temir, +30🏆 Prestige",
                "gold": 25, "food": 75, "iron": 38, "prestige": 30, "xp": 70
            },
            {
                "id": "king_inspire",
                "title": "🗣️ Xonadon a'zolariga murojaat va qasamyod",
                "desc": "Xonadon a'zolari bilan uchrashib, ularga jangovar ruh bag'ishlaysiz.",
                "reward_text": "+125🪙 Oltin, +40🏆 Prestige, +100 XP",
                "gold": 125, "food": 50, "iron": 25, "prestige": 40, "xp": 100
            },
        ]
    },
    "commander": {
        "title": "⚔️ Harbiy Qo'mondon (Commander) Vazifalari",
        "tasks": [
            {
                "id": "cmd_drill",
                "title": "🛡️ Askar va otliqlarni harbiy mashg'ulotdan o'tkazish",
                "desc": "Piyoda va kamonchilarning saf intizomini yuqori darajaga ko'tarasiz.",
                "reward_text": "+62🪙 Oltin, +38⛓️ Temir, +25🏆 Prestige",
                "gold": 62, "food": 38, "iron": 38, "prestige": 25, "xp": 80
            },
            {
                "id": "cmd_scout",
                "title": "🗺️ Chegara chiziqlariga patrul razvedka yuborish",
                "desc": "Dushman xonadonlar harakatini kuzatib, harbiy xarita tuzasiz.",
                "reward_text": "+75🪙 Oltin, +50🌾 Oziq, +70 XP",
                "gold": 75, "food": 50, "iron": 12, "prestige": 20, "xp": 70
            },
            {
                "id": "cmd_arsenal",
                "title": "🗡️ Qurol-yarog' omborlarini to'ldirish",
                "desc": "Temirchilar ishini nazorat qilib, nayza va qilichlar zaxirasini tekshirasiz.",
                "reward_text": "+50⛓️ Temir, +38🪙 Oltin, +20🏆 Prestige",
                "gold": 38, "food": 25, "iron": 50, "prestige": 20, "xp": 75
            },
        ]
    },
    "knight": {
        "title": "🛡️ Xonadon Ritsari (Knight) Vazifalari",
        "tasks": [
            {
                "id": "knt_joust",
                "title": "🏇 Qirollik ritsarlar turnirida qatnashish",
                "desc": "Nayzabozlik maydonida xonadon bayrog'i sharafini himoya qilasiz.",
                "reward_text": "+88🪙 Oltin, +30🏆 Prestige, +90 XP",
                "gold": 88, "food": 25, "iron": 20, "prestige": 30, "xp": 90
            },
            {
                "id": "knt_bandits",
                "title": "⚔️ Qishloqni talonchi qaroqchilardan tozalash",
                "desc": "Qo'rqmasdan qaroqchilar to'dasiga zarba berib, xalqni qutqarasiz.",
                "reward_text": "+62🪙 Oltin, +62🌾 Oziq, +80 XP",
                "gold": 62, "food": 62, "iron": 25, "prestige": 25, "xp": 80
            },
            {
                "id": "knt_sword",
                "title": "⚔️ Qilichbozlik mahoratini oshirish",
                "desc": "Qal'a poligonida chempionlar bilan yakkama-yakka qilich charxlaysiz.",
                "reward_text": "+38⛓️ Temir, +15🏆 Prestige, +100 XP",
                "gold": 38, "food": 25, "iron": 38, "prestige": 15, "xp": 100
            },
        ]
    },
    "captain": {
        "title": "🏹 Soqchilar Boshlig'i (Captain) Vazifalari",
        "tasks": [
            {
                "id": "cpt_gate",
                "title": "🚪 Qal'a darvozalari va devor qorovulligi",
                "desc": "Tungi soqchilar hushyorligini ta'minlaysiz va shubhali shaxslarni ushlaysiz.",
                "reward_text": "+50🪙 Oltin, +38🌾 Oziq, +60 XP",
                "gold": 50, "food": 38, "iron": 20, "prestige": 15, "xp": 60
            },
            {
                "id": "cpt_spies",
                "title": "🕵️ Shahardagi ayg'oqchilarni aniqlash",
                "desc": "Mayxonalarda dushman josuslarining sirli izlarini fosh etasiz.",
                "reward_text": "+62🪙 Oltin, +20🏆 Prestige, +75 XP",
                "gold": 62, "food": 25, "iron": 12, "prestige": 20, "xp": 75
            },
            {
                "id": "cpt_convoy",
                "title": "📦 Savdo karvonlarini xavfsiz kuzatib borish",
                "desc": "Tog' dovonlaridan o'tuvchi oziq-ovqat karvonlarini himoya qilasiz.",
                "reward_text": "+75🌾 Oziq, +38🪙 Oltin, +70 XP",
                "gold": 38, "food": 75, "iron": 12, "prestige": 15, "xp": 70
            },
        ]
    },
    "member": {
        "title": "👤 Xonadon Qasamyodchisi (Member) Vazifalari",
        "tasks": [
            {
                "id": "mbr_harvest",
                "title": "🌾 Qishloq xo'jaligi va hosil yig'ishga yordam",
                "desc": "Xonadon omborlarini to'ldirishda dehqonlarga yordam berasiz.",
                "reward_text": "+88🌾 Oziq, +25🪙 Oltin, +50 XP",
                "gold": 25, "food": 88, "iron": 8, "prestige": 10, "xp": 50
            },
            {
                "id": "mbr_mine",
                "title": "⛏️ Temir konlarida ishlash va ma'dan qazish",
                "desc": "Xonadon qurollari uchun tog'lardan sof temir ma'danlarini qazib chiqarasiz.",
                "reward_text": "+45⛓️ Temir, +25🪙 Oltin, +50 XP",
                "gold": 25, "food": 12, "iron": 45, "prestige": 10, "xp": 50
            },
            {
                "id": "mbr_patrol",
                "title": "👣 Xonadon chegaralarida patrul xizmati",
                "desc": "Qal'a atrofidagi o'rmon yo'llarini ko'zdan kechirasiz.",
                "reward_text": "+38🪙 Oltin, +38🌾 Oziq, +50 XP",
                "gold": 38, "food": 38, "iron": 12, "prestige": 10, "xp": 50
            },
        ]
    },
}


async def quest_rank_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lavozim topshiriqlari menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user or not user.house:
            await query.answer("❌ Avval xonadonga qo'shiling!", show_alert=True)
            return

        await crud.check_and_reset_daily_limits(session, user)
        cnt = user.daily_rank_quest_count

        rank_key = user.rank if user.rank in RANK_DUTIES else "member"
        rank_data = RANK_DUTIES[rank_key]
        rank_title = RANKS.get(user.rank, {}).get("name", user.rank.title())

        text = (
            f"🎖️ **LAVOZIM TOPSHIRIQLARI: {escape_md(rank_title)}**\n\n"
            f"📊 Bugungi imkoniyat: **{max(0, 2 - cnt)}/2** ta vazifa\n\n"
            f"Sizning lavozimingiz xonadon oldida maxsus mas'uliyat yuklaydi. "
            f"Quyidagi vazifalarni bajarib, shaxsiy va xonadon boyligini oshiring!\n\n"
        )

        buttons = []
        for i, t in enumerate(rank_data["tasks"], 1):
            text += (
                f"**{i}. {t['title']}**\n"
                f"_{t['desc']}_\n"
                f"🎁 Mukofot: {t['reward_text']}\n\n"
            )
            buttons.append([InlineKeyboardButton(f"⚡ Bajarish: {t['title'][:25]}...", callback_data=f"qrank_do:{t['id']}")])

        buttons.append([InlineKeyboardButton("🔙 Questlarga Qaytish", callback_data="menu_quests")])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def quest_rank_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lavozim topshirig'ini bajarish (Kunlik max 2 ta)"""
    query = update.callback_query
    user_id = query.from_user.id
    task_id = query.data.split(":")[1]

    # Cooldown tekshirish (15 soniya)
    now = time.time()
    last_time = context.user_data.get("last_rank_duty_time", 0)
    diff = now - last_time
    if diff < 15:
        rem_sec = int(15 - diff)
        await query.answer(f"⏳ Askar va xizmatkorlaringiz dam olmoqda! Yangi topshiriq {rem_sec} soniyadan so'ng.", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        await crud.check_and_reset_daily_limits(session, user)
        if user.daily_rank_quest_count >= 2:
            await query.answer("❌ Bugungi 2 ta lavozim topshirig'i limitingiz tugadi! Ertaga yangi vazifalar ochiladi.", show_alert=True)
            return

        rank_key = user.rank if user.rank in RANK_DUTIES else "member"
        rank_data = RANK_DUTIES[rank_key]

        target_task = None
        for t in rank_data["tasks"]:
            if t["id"] == task_id:
                target_task = t
                break

        if not target_task:
            await query.answer("❌ Topshiriq topilmadi!", show_alert=True)
            return

        user.daily_rank_quest_count += 1
        user.gold += target_task["gold"]
        user.food += target_task["food"]
        user.iron += target_task["iron"]
        user.prestige += target_task["prestige"]
        user.xp += target_task["xp"]

        if user.house:
            user.house.prestige += (target_task["prestige"] // 2)

        from core.leveling import check_user_level_up
        lvl_up, new_lvl, lvl_msg = check_user_level_up(user)

        context.user_data["last_rank_duty_time"] = now
        await session.commit()

        extra = f"\n{lvl_msg}" if lvl_up else ""
        await query.answer(
            f"✅ Topshiriq bajarildi ({user.daily_rank_quest_count}/2)!\n+{target_task['gold']}🪙, +{target_task['food']}🌾, +{target_task['iron']}⛓️, +{target_task['prestige']}🏆 Prestige{extra}",
            show_alert=True
        )
        await quest_rank_callback(update, context)


def register_quest_handlers(app):
    app.add_handler(CommandHandler("quests", quest_command))
    app.add_handler(CallbackQueryHandler(quest_menu_callback, pattern="^menu_quests$"))
    app.add_handler(CallbackQueryHandler(quest_main_callback, pattern="^quest_main$"))
    app.add_handler(CallbackQueryHandler(quest_main_do_callback, pattern="^qmain_do:"))
    app.add_handler(CallbackQueryHandler(quest_daily_callback, pattern="^quest_daily$"))
    app.add_handler(CallbackQueryHandler(quest_secret_callback, pattern="^quest_secret$"))
    app.add_handler(CallbackQueryHandler(secret_choice_callback, pattern="^secret_choice:"))
    app.add_handler(CallbackQueryHandler(citadel_quiz_callback, pattern="^menu_citadel$"))
    app.add_handler(CallbackQueryHandler(citadel_answer_callback, pattern="^cit_ans:"))
    app.add_handler(CallbackQueryHandler(council_callback, pattern="^menu_council$"))
    app.add_handler(CallbackQueryHandler(council_answer_callback, pattern="^coun_ans:"))
    app.add_handler(CallbackQueryHandler(quest_rank_callback, pattern="^quest_rank$"))
    app.add_handler(CallbackQueryHandler(quest_rank_do_callback, pattern="^qrank_do:"))
