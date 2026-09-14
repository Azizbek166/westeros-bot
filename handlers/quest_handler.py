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
    """Asosiy hikoyaviy questlar ro'yxati"""
    query = update.callback_query
    await query.answer()

    text = "📜 **ASOSIY HIKOYA QUESTLARI:**\n\n"
    for q in MAIN_QUESTS:
        text += (
            f"**{q['title']}**\n"
            f"_{q['description']}_\n"
            f"🎁 Mukofot: +{q['reward_gold']}🪙, +{q['reward_food']}🌾, +{q['reward_iron']}⛓️, +{q['reward_xp']} XP\n\n"
        )

    buttons = [[InlineKeyboardButton("🔙 Questlarga Qaytish", callback_data="menu_quests")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def quest_daily_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kunlik vazifalar ro'yxati"""
    query = update.callback_query
    await query.answer()

    text = "⭐ **BUGUNGI KUNLIK VAZIFALAR:**\n\n"
    for q in DAILY_QUESTS:
        text += (
            f"**{q['title']}**\n"
            f"_{q['description']}_\n"
            f"🎁 Mukofot: +{q['reward_gold']}🪙, +{q.get('reward_food', 0)}🌾, +{q['reward_xp']} XP\n\n"
        )

    buttons = [[InlineKeyboardButton("🔙 Questlarga Qaytish", callback_data="menu_quests")]]
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
        f"To'g'ri javob uchun: **+300🪙 oltin, +100⛓️ temir va +50 XP**\n\n"
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
            user.gold += 300
            user.iron += 100
            user.xp += 50
            await session.commit()
            text = (
                "✅ **TO'G'RI JAVOB!**\n\n"
                "Maesterlar bilimingizni yuqori baholashdi.\n"
                f"💰 Mukofot: **+300🪙 oltin, +100⛓️ temir, +50 XP**\n"
                f"📊 Qolgan viktorinalar: **{max(0, DAILY_QUIZ_LIMIT - user.daily_quiz_count)}/{DAILY_QUIZ_LIMIT}**"
            )
        else:
            user.gold = max(0, user.gold - 50)
            await session.commit()
            correct_text = options[correct_idx]
            text = (
                f"❌ **NOTO'G'RI JAVOB!**\n\n"
                f"To'g'ri javob: **{correct_text}** edi.\n"
                f"💰 Jarima: -50🪙 oltin\n"
                f"📊 Qolgan viktorinalar: **{max(0, DAILY_QUIZ_LIMIT - user.daily_quiz_count)}/{DAILY_QUIZ_LIMIT}**"
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
                "reward_text": "+400🪙 Oltin, +25🏆 Prestige, +80 XP",
                "gold": 400, "food": 100, "iron": 50, "prestige": 25, "xp": 80
            },
            {
                "id": "king_fortify",
                "title": "🏰 Bosh Qal'a istehkomlarini mustahkamlash",
                "desc": "Mudofaa devorlarini ko'zdan kechirib, muhandislarga buyruq berasiz.",
                "reward_text": "+300🌾 Oziq, +150⛓️ Temir, +30🏆 Prestige",
                "gold": 100, "food": 300, "iron": 150, "prestige": 30, "xp": 70
            },
            {
                "id": "king_inspire",
                "title": "🗣️ Xonadon a'zolariga murojaat va qasamyod",
                "desc": "Xonadon a'zolari bilan uchrashib, ularga jangovar ruh bag'ishlaysiz.",
                "reward_text": "+500🪙 Oltin, +40🏆 Prestige, +100 XP",
                "gold": 500, "food": 200, "iron": 100, "prestige": 40, "xp": 100
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
                "reward_text": "+250🪙 Oltin, +150⛓️ Temir, +25🏆 Prestige",
                "gold": 250, "food": 150, "iron": 150, "prestige": 25, "xp": 80
            },
            {
                "id": "cmd_scout",
                "title": "🗺️ Chegara chiziqlariga patrul razvedka yuborish",
                "desc": "Dushman xonadonlar harakatini kuzatib, harbiy xarita tuzasiz.",
                "reward_text": "+300🪙 Oltin, +200🌾 Oziq, +70 XP",
                "gold": 300, "food": 200, "iron": 50, "prestige": 20, "xp": 70
            },
            {
                "id": "cmd_arsenal",
                "title": "🗡️ Qurol-yarog' omborlarini to'ldirish",
                "desc": "Temirchilar ishini nazorat qilib, nayza va qilichlar zaxirasini tekshirasiz.",
                "reward_text": "+200⛓️ Temir, +150🪙 Oltin, +20🏆 Prestige",
                "gold": 150, "food": 100, "iron": 200, "prestige": 20, "xp": 75
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
                "reward_text": "+350🪙 Oltin, +30🏆 Prestige, +90 XP",
                "gold": 350, "food": 100, "iron": 80, "prestige": 30, "xp": 90
            },
            {
                "id": "knt_bandits",
                "title": "⚔️ Qishloqni talonchi qaroqchilardan tozalash",
                "desc": "Qo'rqmasdan qaroqchilar to'dasiga zarba berib, xalqni qutqarasiz.",
                "reward_text": "+250🪙 Oltin, +250🌾 Oziq, +80 XP",
                "gold": 250, "food": 250, "iron": 100, "prestige": 25, "xp": 80
            },
            {
                "id": "knt_sword",
                "title": "⚔️ Qilichbozlik mahoratini oshirish",
                "desc": "Qal'a poligonida chempionlar bilan yakkama-yakka qilich charxlaysiz.",
                "reward_text": "+150⛓️ Temir, +15🏆 Prestige, +100 XP",
                "gold": 150, "food": 100, "iron": 150, "prestige": 15, "xp": 100
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
                "reward_text": "+200🪙 Oltin, +150🌾 Oziq, +60 XP",
                "gold": 200, "food": 150, "iron": 80, "prestige": 15, "xp": 60
            },
            {
                "id": "cpt_spies",
                "title": "🕵️ Shahardagi ayg'oqchilarni aniqlash",
                "desc": "Mayxonalarda dushman josuslarining sirli izlarini fosh etasiz.",
                "reward_text": "+250🪙 Oltin, +20🏆 Prestige, +75 XP",
                "gold": 250, "food": 100, "iron": 50, "prestige": 20, "xp": 75
            },
            {
                "id": "cpt_convoy",
                "title": "📦 Savdo karvonlarini xavfsiz kuzatib borish",
                "desc": "Tog' dovonlaridan o'tuvchi oziq-ovqat karvonlarini himoya qilasiz.",
                "reward_text": "+300🌾 Oziq, +150🪙 Oltin, +70 XP",
                "gold": 150, "food": 300, "iron": 50, "prestige": 15, "xp": 70
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
                "reward_text": "+350🌾 Oziq, +100🪙 Oltin, +50 XP",
                "gold": 100, "food": 350, "iron": 30, "prestige": 10, "xp": 50
            },
            {
                "id": "mbr_mine",
                "title": "⛏️ Temir konlarida ishlash va ma'dan qazish",
                "desc": "Xonadon qurollari uchun tog'lardan sof temir ma'danlarini qazib chiqarasiz.",
                "reward_text": "+180⛓️ Temir, +100🪙 Oltin, +50 XP",
                "gold": 100, "food": 50, "iron": 180, "prestige": 10, "xp": 50
            },
            {
                "id": "mbr_patrol",
                "title": "👣 Xonadon chegaralarida patrul xizmati",
                "desc": "Qal'a atrofidagi o'rmon yo'llarini ko'zdan kechirasiz.",
                "reward_text": "+150🪙 Oltin, +150🌾 Oziq, +50 XP",
                "gold": 150, "food": 150, "iron": 50, "prestige": 10, "xp": 50
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

        rank_key = user.rank if user.rank in RANK_DUTIES else "member"
        rank_data = RANK_DUTIES[rank_key]
        rank_title = RANKS.get(user.rank, {}).get("name", user.rank.title())

        text = (
            f"🎖️ **LAVOZIM TOPSHIRIQLARI: {escape_md(rank_title)}**\n\n"
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
    """Lavozim topshirig'ini bajarish"""
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

        user.gold += target_task["gold"]
        user.food += target_task["food"]
        user.iron += target_task["iron"]
        user.prestige += target_task["prestige"]
        user.xp += target_task["xp"]

        if user.house:
            user.house.prestige += (target_task["prestige"] // 2)

        context.user_data["last_rank_duty_time"] = now
        await session.commit()

        await query.answer(
            f"✅ Topshiriq muvaffaqiyatli bajarildi!\n+{target_task['gold']}🪙, +{target_task['food']}🌾, +{target_task['iron']}⛓️, +{target_task['prestige']}🏆 Prestige",
            show_alert=True
        )
        await quest_rank_callback(update, context)


def register_quest_handlers(app):
    app.add_handler(CommandHandler("quests", quest_command))
    app.add_handler(CallbackQueryHandler(quest_menu_callback, pattern="^menu_quests$"))
    app.add_handler(CallbackQueryHandler(quest_main_callback, pattern="^quest_main$"))
    app.add_handler(CallbackQueryHandler(quest_daily_callback, pattern="^quest_daily$"))
    app.add_handler(CallbackQueryHandler(quest_secret_callback, pattern="^quest_secret$"))
    app.add_handler(CallbackQueryHandler(secret_choice_callback, pattern="^secret_choice:"))
    app.add_handler(CallbackQueryHandler(citadel_quiz_callback, pattern="^menu_citadel$"))
    app.add_handler(CallbackQueryHandler(citadel_answer_callback, pattern="^cit_ans:"))
    app.add_handler(CallbackQueryHandler(council_callback, pattern="^menu_council$"))
    app.add_handler(CallbackQueryHandler(council_answer_callback, pattern="^coun_ans:"))
    app.add_handler(CallbackQueryHandler(quest_rank_callback, pattern="^quest_rank$"))
    app.add_handler(CallbackQueryHandler(quest_rank_do_callback, pattern="^qrank_do:"))
