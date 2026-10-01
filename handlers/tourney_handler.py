import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from config import ADMIN_IDS, OWNER_ID, escape_md
from sqlalchemy import select, desc
from core.battle_engine import get_fighter_perk

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    try:
        uid = int(user_id)
        return uid in [int(x) for x in ADMIN_IDS] or uid == int(OWNER_ID)
    except Exception:
        return False


async def _safe_edit_or_reply(query, update, text: str, reply_markup: InlineKeyboardMarkup = None, parse_mode: str = "Markdown"):
    """Xabarni xavfsiz tahrirlash yoki yuborish (photo xabarlar va parse xatolariga chidamli)"""
    if query:
        msg = query.message
        if getattr(msg, "photo", None):
            try:
                await msg.delete()
            except Exception:
                pass
            return await msg.chat.send_message(text, reply_markup=reply_markup, parse_mode=parse_mode)
        try:
            return await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            try:
                return await query.edit_message_text(text, reply_markup=reply_markup)
            except Exception:
                return await msg.reply_text(text, reply_markup=reply_markup)
    elif update and update.effective_message:
        try:
            return await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            return await update.effective_message.reply_text(text, reply_markup=reply_markup)


async def tourney_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ritsarlar turniri va stavkalar asosiy menyusi"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            msg = "❌ Siz hali ro'yxatdan o'tmagansiz. /start bosing."
            await _safe_edit_or_reply(query, update, msg)
            return

        tourney = await crud.get_active_tournament(session)

        # Agar faol turnir bo'lmasa, arena sukunati va so'nggi g'olibni ko'rsatish
        if not tourney:
            last_info = ""
            try:
                last_res = await session.execute(
                    select(models.Tournament)
                    .where(models.Tournament.status == "completed")
                    .order_by(desc(models.Tournament.id))
                    .limit(1)
                )
                last_t = last_res.scalar_one_or_none()
                if last_t and last_t.winner_name:
                    last_info = (
                        f"📜 **So'nggi Turnir:** {escape_md(str(last_t.name))}\n"
                        f"🥇 **Qirollik Chempioni:** {escape_md(str(last_t.winner_name))}\n"
                        f"💰 **Jamg'arma bo'lgan:** {last_t.prize_pool:,} Oltin\n\n"
                    )
            except Exception:
                pass

            text = (
                "🏇🏆 **QIROL QO'LI RITSARLAR TURNIRI**\n\n"
                "🕊️ *Hozirda arena sukunatda. Navbatdagi ritsarlar turniri Qirol yoki Bosh Administrator tomonidan e'lon qilinishi kutilmoqda!*\n\n"
                f"{last_info}"
                f"👤 Sizning boyligingiz: **{user.gold:,}** Oltin\n\n"
                "Yangi turnir e'lon qilinganida barcha lordlarga qarg'a xabari yuboriladi. Ungacha armiyangiz va sarkardangizni tayyorlab turing!"
            )

            buttons = [
                [InlineKeyboardButton("📜 Turnir Qoidalari", callback_data="tourney_rules")],
                [InlineKeyboardButton("🏛️ Chempionlar Zali (Turnir Tarixi)", callback_data="tourney_history")],
            ]
            if is_admin(tg_user.id):
                buttons.append([
                    InlineKeyboardButton("👑 Yangi Turnirni E'lon Qilish (Admin)", callback_data="admin_tourney_start")
                ])
            buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

            keyboard = InlineKeyboardMarkup(buttons)
            await _safe_edit_or_reply(query, update, text, reply_markup=keyboard)
            return

        # So'nggi yakunlangan turnir ma'lumotlarini olish (agar mavjud bo'lsa)
        last_info = ""
        try:
            last_res = await session.execute(
                select(models.Tournament)
                .where(models.Tournament.status == "completed")
                .order_by(desc(models.Tournament.id))
                .limit(1)
            )
            last_t = last_res.scalar_one_or_none()
            if last_t and last_t.winner_name:
                last_info = f"\n🎖️ **So'nggi Chempion:** {escape_md(str(last_t.winner_name))} ({last_t.prize_pool:,}💰)\n"
        except Exception:
            pass

        parts = tourney.participants or []
        n_parts = len(parts)
        if n_parts >= 8:
            readiness_badge = "\n🔥 **ARENA TO'LDI! Barcha 8 ritsar jangga tayyor!**\n"
        else:
            readiness_badge = f"\n⏳ *Qolgan {8 - n_parts} ta bo'sh o'rin afsonaviy NPC ritsarlar bilan to'ldiriladi.*\n"

        parts_list = ""
        if parts:
            parts_list = "\n🤺 **Ishtirokchi Ritsarlar:**\n"
            for idx, p in enumerate(parts, 1):
                clean_name = escape_md(str(p.fighter_name))
                parts_list += f"{idx}. **{clean_name}** — ⚡ {p.fighter_power} jang quvvati\n"
        else:
            parts_list = "\n_Hozircha jang maydoniga ritsarlar tushmagan._\n"

        user_is_entered = any(p.user_id == user.id for p in parts)
        status_label = "✅ Siz qatnashyapsiz" if user_is_entered else "❌ Qatnashmadingiz"

        # Foydalanuvchining joriy taktikasi va mahorati (agar qatnashayotgan bo'lsa)
        tactic_info = ""
        perk_info = ""
        if user_is_entered:
            user_part = next((p for p in parts if p.user_id == user.id), None)
            if user_part:
                cur_t = getattr(user_part, "tactic", "rock") or "rock"
                cur_seq = getattr(user_part, "tactics_seq", "") or ""
                icons = {"rock": "🪨 Tosh", "scissors": "✂️ Qaychi", "paper": "📜 Qog'oz", "random": "🎲 Tasodifiy"}
                if cur_seq and "," in cur_seq:
                    seq_items = [icons.get(x.strip().lower(), x) for x in cur_seq.split(",")[:3]]
                    seq_fmt = " ➔ ".join(seq_items)
                    tactic_info = f"\n🎯 **Sizning Taktikangiz:** {seq_fmt}\n"
                else:
                    tactic_labels = {
                        "rock": "🪨 Tosh (Og'ir Zarba)",
                        "scissors": "✂️ Qaychi (Epchil Hamla)",
                        "paper": "📜 Qog'oz (Qalqonli Mudofaa)",
                        "random": "🎲 Aralash / Tasodifiy",
                    }
                    tactic_info = f"\n🎯 **Sizning Taktikangiz:** {tactic_labels.get(cur_t, '🪨 Tosh')}\n"

                f_perk = get_fighter_perk(user_part.fighter_name)
                if f_perk:
                    perk_title = f_perk.get("title") or f_perk.get("name", "Mahorat")
                    perk_info = f"✨ **Maxsus Mahorat:** {perk_title} — _{f_perk['desc']}_\n"

        # Foydalanuvchining ushbu turnirdagi faol stavkalari
        user_bet_res = await session.execute(
            select(models.TournamentBet).where(
                models.TournamentBet.tournament_id == tourney.id,
                models.TournamentBet.user_id == user.id,
            )
        )
        user_bets = user_bet_res.scalars().all()
        bet_info = ""
        if user_bets:
            bet_lines = []
            for b in user_bets:
                part_match = next((p for p in parts if p.id == b.participant_id), None)
                f_name = part_match.fighter_name if part_match else "Jangchi"
                bet_lines.append(f"• **{escape_md(str(f_name))}** ga **{b.bet_gold:,}💰** (Kutilayotgan yutuq: **{int(b.bet_gold * 1.8):,}💰**)")
            bet_info = "\n🎰 **Sizning faol stavkalaringiz:**\n" + "\n".join(bet_lines) + "\n"

        text = (
            f"🏇🏆 **{escape_md(str(tourney.name))}**\n\n"
            f"Qirollikning 8 nafar eng dovyurak ritsarlari Tosh-Qaychi-Qog'oz saralash duellarida to'qnash keladi!\n\n"
            f"💰 **Umumiy Jamg'arma:** **{tourney.prize_pool:,}** Oltin\n"
            f"🥇 1-O'rin g'olibi: **70%** jamg'arma + **100** Nufuz + **'Qirollik Chempioni'** unvoni\n"
            f"🥈 2-O'rin sohibi: **30%** jamg'arma + **50** Nufuz\n"
            f"🎰 Stavka yutug'i: **1.8x** koeffitsiyent\n"
            f"👤 Sizning holatingiz: **{status_label}**\n"
            f"💰 Oltiningiz: **{user.gold:,}** Oltin"
            f"{tactic_info}"
            f"{perk_info}"
            f"{last_info}"
            f"{bet_info}"
            f"{readiness_badge}"
            f"{parts_list}"
        )

        buttons = []
        if not user_is_entered:
            buttons.append([InlineKeyboardButton("🤺 Turnirga kirish (2,000💰)", callback_data="tourney_enter_pick")])
        else:
            buttons.append([InlineKeyboardButton("⚙️ Taktikani Sozlash", callback_data="tourney_tactic_pick")])

        buttons.append([InlineKeyboardButton("📊 Turnir Setkasini Ko'rish", callback_data="tourney_bracket")])
        buttons.append([InlineKeyboardButton("🎰 Stavka tikish (1.8x)", callback_data="tourney_bet_pick")])
        buttons.append([InlineKeyboardButton("🏛️ Chempionlar Zali (Turnir Tarixi)", callback_data="tourney_history")])
        buttons.append([InlineKeyboardButton("📜 Qoidalar va Shartlar", callback_data="tourney_rules")])

        if is_admin(tg_user.id):
            buttons.append([
                InlineKeyboardButton("🏁 Turnirni Yakunlash / Duellar (Admin)", callback_data="admin_tourney_resolve"),
            ])

        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        keyboard = InlineKeyboardMarkup(buttons)
        await _safe_edit_or_reply(query, update, text, reply_markup=keyboard)


async def tourney_bracket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Turnir setkasini ko'rsatish"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    async with AsyncSessionLocal() as session:
        bracket_text = await crud.get_tournament_bracket_display(session)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏇 Turnir maydoniga qaytish", callback_data="menu_tourney")]
        ])
        await _safe_edit_or_reply(query, update, bracket_text, reply_markup=keyboard)


async def tourney_enter_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jangchi tanlash (O'zi yoki Bosh Sarkardasi)"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        tourney = await crud.get_active_tournament(session)
        if not tourney:
            await _safe_edit_or_reply(
                query, update,
                "❌ Hozirda faol ritsarlar turniri mavjud emas.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]])
            )
            return

        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
        army = army_res.scalar_one_or_none()
        has_champ = bool(army and army.champion)

        buttons = [
            [InlineKeyboardButton("👤 O'zim (Ritsar unvoni bilan)", callback_data="tourney_pick_tactic:self")]
        ]
        if has_champ:
            buttons.append([InlineKeyboardButton("🌟 Bosh Sarkardamni tushirish (Yuqori quvvat)", callback_data="tourney_pick_tactic:champ")])

        buttons.append([InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")])

        text = (
            "🤺 **TURNIR MAYDONIGA KIM CHIQADI?**\n\n"
            "Kirish to'lovi: **2,000** Oltin (turnir jamg'armasiga qo'shiladi).\n\n"
            "• *O'zingiz:* Nufuzingiz va tajribangiz asosida quvvat beriladi (120-200⚡).\n"
            "• *Bosh Sarkarda:* Jon Snow, Jaime Lannister kabi afsonaviy chempionlar eng yuqori quvvat (210-240⚡) bilan jang qiladi!"
        )
        await _safe_edit_or_reply(query, update, text, reply_markup=InlineKeyboardMarkup(buttons))


async def tourney_pick_tactic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Turnirga kirishdan avval taktika tanlash"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    target = query.data.split(":")[1]  # self yoki champ
    text = (
        "🎯 **JANG TAKTIKASINI TANLANG:**\n\n"
        "Turnir 3 raundlik Tosh-Qaychi-Qog'oz tizimida o'tadi:\n"
        "• 🪨 **Tosh (Og'ir Zarba):** ✂️ Qaychini yanchadi, 📜 Qog'ozga yutqazadi.\n"
        "• ✂️ **Qaychi (Epchil Hamla):** 📜 Qog'ozni kesadi, 🪨 Toshga yutqazadi.\n"
        "• 📜 **Qog'oz (Qalqonli Mudofaa):** 🪨 Toshni qaytaradi, ✂️ Qaychiga yutqazadi.\n"
        "• 🎲 **Aralash / Tasodifiy:** Har raundda kutilmagan usul qo'llaydi.\n\n"
        "Qaysi taktika bilan maydonga tushmoqchisiz? *(Jang boshlanguniga qadar taktikani erkin o'zgartirishingiz mumkin!)*"
    )
    buttons = [
        [
            InlineKeyboardButton("🛡️ Devor Mudofaasi (📜, 📜, 🪨)", callback_data=f"tourney_do_enter:{target}:wall"),
        ],
        [
            InlineKeyboardButton("⚔️ Shiddatli Hujum (🪨, ✂️, 🪨)", callback_data=f"tourney_do_enter:{target}:strike"),
        ],
        [
            InlineKeyboardButton("⚡ Ilon Hamlasi (✂️, ✂️, 📜)", callback_data=f"tourney_do_enter:{target}:viper"),
        ],
        [
            InlineKeyboardButton("🌪️ Girdob Taktikasi (🪨, ✂️, 📜)", callback_data=f"tourney_do_enter:{target}:whirlwind"),
        ],
        [
            InlineKeyboardButton("🪨 Tosh", callback_data=f"tourney_do_enter:{target}:rock"),
            InlineKeyboardButton("✂️ Qaychi", callback_data=f"tourney_do_enter:{target}:scissors"),
            InlineKeyboardButton("📜 Qog'oz", callback_data=f"tourney_do_enter:{target}:paper"),
        ],
        [
            InlineKeyboardButton("🎲 Aralash / Kutilmagan", callback_data=f"tourney_do_enter:{target}:random"),
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="tourney_enter_pick")],
    ]
    await _safe_edit_or_reply(query, update, text, reply_markup=InlineKeyboardMarkup(buttons))


async def tourney_tactic_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mavjud ishtirokchining taktikasini sozlash menyusi"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    text = (
        "⚙️ **JANG TAKTIKASINI SOZLASH:**\n\n"
        "Raqibingizning ehtimoliy harakatini oldindan hisobga olib, taktik shablon tanlang yoki har bir raund uchun shaxsiy ketma-ketlik tuzing!\n\n"
        "📋 **Taktik Shablonlar (3 Raund):**\n"
        "• 🛡️ **Devor Mudofaasi:** 📜 Qog'oz ➔ 📜 Qog'oz ➔ 🪨 Tosh\n"
        "• ⚔️ **Shiddatli Hujum:** 🪨 Tosh ➔ ✂️ Qaychi ➔ 🪨 Tosh\n"
        "• ⚡ **Ilon Hamlasi:** ✂️ Qaychi ➔ ✂️ Qaychi ➔ 📜 Qog'oz\n"
        "• 🌪️ **Girdob Taktikasi:** 🪨 Tosh ➔ ✂️ Qaychi ➔ 📜 Qog'oz\n"
        "• 🎲 **Aralash:** Har raundda tasodifiy kutilmagan harakat\n\n"
        "*(Durrang holatida ritsarlarning jang quvvati va afsonaviy chempion qobiliyatlari g'olibni hal qiladi!)*"
    )
    buttons = [
        [InlineKeyboardButton("🛡️ Devor Mudofaasi (📜, 📜, 🪨)", callback_data="tourney_set_tactic:wall")],
        [InlineKeyboardButton("⚔️ Shiddatli Hujum (🪨, ✂️, 🪨)", callback_data="tourney_set_tactic:strike")],
        [InlineKeyboardButton("⚡ Ilon Hamlasi (✂️, ✂️, 📜)", callback_data="tourney_set_tactic:viper")],
        [InlineKeyboardButton("🌪️ Girdob Taktikasi (🪨, ✂️, 📜)", callback_data="tourney_set_tactic:whirlwind")],
        [InlineKeyboardButton("🛠️ Shaxsiy Ketma-ketlik Terish (3 Raund)", callback_data="tourney_seq_r1")],
        [
            InlineKeyboardButton("🪨 Faqat Tosh", callback_data="tourney_set_tactic:rock"),
            InlineKeyboardButton("✂️ Faqat Qaychi", callback_data="tourney_set_tactic:scissors"),
            InlineKeyboardButton("📜 Faqat Qog'oz", callback_data="tourney_set_tactic:paper"),
        ],
        [InlineKeyboardButton("🎲 Aralash / Kutilmagan", callback_data="tourney_set_tactic:random")],
        [InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")],
    ]
    await _safe_edit_or_reply(query, update, text, reply_markup=InlineKeyboardMarkup(buttons))


async def tourney_set_tactic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Taktika o'zgarishini saqlash"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    tactic = query.data.split(":")[1]
    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        ok, msg = await crud.update_tournament_tactic(session, user.id, tactic)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏇 Turnir maydoniga qaytish", callback_data="menu_tourney")]
        ])
        await _safe_edit_or_reply(query, update, msg, reply_markup=keyboard)


async def tourney_seq_r1_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shaxsiy ketma-ketlik: 1-raund harakatini tanlash"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    text = (
        "🛠️ **SHAXSIY TAKTIKA TUZISH (1/3 RAUND):**\n\n"
        "1-Raund to'qnashuvi uchun asosiy zarbani tanlang:\n\n"
        "• 🪨 **Tosh:** ✂️ Qaychini yanchadi, 📜 Qog'ozga yutqazadi\n"
        "• ✂️ **Qaychi:** 📜 Qog'ozni kesadi, 🪨 Toshga yutqazadi\n"
        "• 📜 **Qog'oz:** 🪨 Toshni to'sadi, ✂️ Qaychiga yutqazadi"
    )
    buttons = [
        [
            InlineKeyboardButton("🪨 1-Raund: Tosh", callback_data="tourney_seq_r2:rock"),
            InlineKeyboardButton("✂️ 1-Raund: Qaychi", callback_data="tourney_seq_r2:scissors"),
        ],
        [InlineKeyboardButton("📜 1-Raund: Qog'oz", callback_data="tourney_seq_r2:paper")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="tourney_tactic_pick")],
    ]
    await _safe_edit_or_reply(query, update, text, reply_markup=InlineKeyboardMarkup(buttons))


async def tourney_seq_r2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shaxsiy ketma-ketlik: 2-raund harakatini tanlash"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    m1 = query.data.split(":")[1]
    icons = {"rock": "🪨 Tosh", "scissors": "✂️ Qaychi", "paper": "📜 Qog'oz"}
    text = (
        "🛠️ **SHAXSIY TAKTIKA TUZISH (2/3 RAUND):**\n\n"
        f"1-Raund: **{icons.get(m1, m1)}** ✅\n\n"
        "Endi 2-Raund uchun qaysi usulni qo'llaysiz?"
    )
    buttons = [
        [
            InlineKeyboardButton("🪨 2-Raund: Tosh", callback_data=f"tourney_seq_r3:{m1}:rock"),
            InlineKeyboardButton("✂️ 2-Raund: Qaychi", callback_data=f"tourney_seq_r3:{m1}:scissors"),
        ],
        [InlineKeyboardButton("📜 2-Raund: Qog'oz", callback_data=f"tourney_seq_r3:{m1}:paper")],
        [InlineKeyboardButton("🔙 Qayta boshlash", callback_data="tourney_seq_r1")],
    ]
    await _safe_edit_or_reply(query, update, text, reply_markup=InlineKeyboardMarkup(buttons))


async def tourney_seq_r3_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shaxsiy ketma-ketlik: 3-raund harakatini tanlash"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    parts = query.data.split(":")
    m1, m2 = parts[1], parts[2]
    icons = {"rock": "🪨 Tosh", "scissors": "✂️ Qaychi", "paper": "📜 Qog'oz"}
    text = (
        "🛠️ **SHAXSIY TAKTIKA TUZISH (3/3 RAUND):**\n\n"
        f"1-Raund: **{icons.get(m1, m1)}** ✅\n"
        f"2-Raund: **{icons.get(m2, m2)}** ✅\n\n"
        "Hal qiluvchi 3-Raund harakatini tanlang:"
    )
    buttons = [
        [
            InlineKeyboardButton("🪨 3-Raund: Tosh", callback_data=f"tourney_seq_save:{m1}:{m2}:rock"),
            InlineKeyboardButton("✂️ 3-Raund: Qaychi", callback_data=f"tourney_seq_save:{m1}:{m2}:scissors"),
        ],
        [InlineKeyboardButton("📜 3-Raund: Qog'oz", callback_data=f"tourney_seq_save:{m1}:{m2}:paper")],
        [InlineKeyboardButton("🔙 Qayta boshlash", callback_data="tourney_seq_r1")],
    ]
    await _safe_edit_or_reply(query, update, text, reply_markup=InlineKeyboardMarkup(buttons))


async def tourney_seq_save_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shaxsiy 3-raundlik ketma-ketlikni saqlash"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    parts = query.data.split(":")
    m1, m2, m3 = parts[1], parts[2], parts[3]
    seq_str = f"{m1},{m2},{m3}"

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        ok, msg = await crud.update_tournament_tactic(session, user.id, tactic=m1, tactics_seq=seq_str)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏇 Turnir maydoniga qaytish", callback_data="menu_tourney")]
        ])
        await _safe_edit_or_reply(query, update, msg, reply_markup=keyboard)


async def tourney_do_enter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Turnirga ro'yxatdan o'tishni amalga oshirish"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    parts = query.data.split(":")
    use_champ = (parts[1] == "champ")
    tactic = parts[2] if len(parts) > 2 else "rock"

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        ok, msg = await crud.enter_tournament(session, user.id, use_champion=use_champ, tactic=tactic)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Turnir Setkasi", callback_data="tourney_bracket")],
            [InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]
        ])
        await _safe_edit_or_reply(query, update, msg, reply_markup=keyboard)


async def tourney_bet_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stavka uchun jangchini tanlash"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    async with AsyncSessionLocal() as session:
        tourney = await crud.get_active_tournament(session)
        if not tourney:
            await _safe_edit_or_reply(
                query, update,
                "❌ Hozirda faol ritsarlar turniri mavjud emas.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]])
            )
            return
        if not tourney.participants:
            await _safe_edit_or_reply(
                query, update,
                "❌ Hozircha turnirda ishtirokchi jangchilar yo'q. Avval jangchilar maydonga tushishi kerak.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]])
            )
            return

        buttons = []
        for p in tourney.participants:
            clean_pname = escape_md(str(p.fighter_name))
            buttons.append([InlineKeyboardButton(f"🤺 {clean_pname} ({p.fighter_power}⚡)", callback_data=f"tourney_bet_fighter:{p.id}")])

        buttons.append([InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")])
        text = (
            "🎰 **QAYSI RITSAR G'ALABASIGA STAVKA TIKASIZ?**\n\n"
            "Turnir g'olibini to'g'ri topsangiz, tikkan miqdoringiz **1.8 baravar** (1.8x) ko'paytirib qaytariladi!"
        )
        await _safe_edit_or_reply(query, update, text, reply_markup=InlineKeyboardMarkup(buttons))


async def tourney_bet_amount_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stavka miqdorini tanlash"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    part_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        part = await session.get(models.TournamentParticipant, part_id)
        if not part:
            await _safe_edit_or_reply(query, update, "❌ Jangchi topilmadi.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]]))
            return

        clean_pname = escape_md(str(part.fighter_name))
        text = (
            f"💰 **STAVKA MIQDORINI TANLANG:**\n\n"
            f"Tanlangan ritsar: **{clean_pname}** (⚡ {part.fighter_power})\n"
            f"Agar ushbu jangchi turnir chempioni bo'lsa, yutug'ingiz 1.8x bo'ladi."
        )
        amounts = [500, 1000, 2500, 5000]
        buttons = []
        for amt in amounts:
            buttons.append([InlineKeyboardButton(f"💰 {amt:,} Oltin (Yutuq: {int(amt*1.8):,}💰)", callback_data=f"tourney_bet_do:{part_id}:{amt}")])

        buttons.append([InlineKeyboardButton("🔙 Jangchilar ro'yxati", callback_data="tourney_bet_pick")])
        await _safe_edit_or_reply(query, update, text, reply_markup=InlineKeyboardMarkup(buttons))


async def tourney_bet_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stavka tikishni tasdiqlash"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    parts = query.data.split(":")
    part_id = int(parts[1])
    amt = int(parts[2])

    tg_user = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user.id)
        if not user:
            return

        ok, msg = await crud.place_tournament_bet(session, user.id, part_id, amt)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]
        ])
        await _safe_edit_or_reply(query, update, msg, reply_markup=keyboard)


async def tourney_rules_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Turnir qoidalari (Tosh-Qaychi-Qog'oz va 8 talik setka)"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    text = (
        "📜 **QIROL QO'LI TURNIRI QOIDALARI:**\n\n"
        "1. **8 Talik Turnir Setkasi (Knockout):**\n"
        "Turnirda 8 nafar ritsar ishtirok etadi. Bosqichlar: 1/4 Chorak Final ➔ 1/2 Yarim Final ➔ Grand Final! Agar o'yinchilar 8 tadan kam bo'lsa, bo'sh o'rinlar Vesteros afsonaviy ritsarlari (Ser Arthur Dayne, Ser Gregor Clegane, Ser Jaime Lannister va b.) bilan to'ldiriladi.\n\n"
        "2. **Tosh-Qaychi-Qog'oz Duel Tizimi:**\n"
        "Har bir duel 3 raundlik to'qnashuvdan iborat:\n"
        "• 🪨 **Tosh (Og'ir Zarba):** ✂️ Qaychini yanchadi, 📜 Qog'ozga yutqazadi.\n"
        "• ✂️ **Qaychi (Epchil Hamla):** 📜 Qog'ozni kesadi, 🪨 Toshga yutqazadi.\n"
        "• 📜 **Qog'oz (Qalqonli Mudofaa):** 🪨 Toshni to'sadi, ✂️ Qaychiga yutqazadi.\n"
        "• 🎲 **Aralash / Tasodifiy:** Har raundda tasodifiy yurish qiladi.\n"
        "*(Bir xil taktika to'qnashganda, ritsarlarning sof quvvati sinovdan o'tadi!)*\n\n"
        "3. **Taktikani Sozlash:**\n"
        "Turnir boshlanguniga qadar istalgan vaqtda [⚙️ Taktikani Sozlash] orqali taktikangizni yangilashingiz mumkin.\n\n"
        "4. **G'oliblik va Sovrinlar:**\n"
        "• 🥇 1-O'rin (Chempion): Jamg'armaning **70%** ulushi + **100** Nufuz + **'Qirollik Chempioni'** unvoni!\n"
        "• 🥈 2-O'rin (Finalist): Jamg'armaning **30%** ulushi + **50** Nufuz!\n\n"
        "5. **Stavkalar:** Har bir ishtirokchiga 500 dan 5,000 Oltin stavka tikish mumkin. Chempion ritsarga tikilgan stavkalar **1.8 baravar** (1.8x) qaytariladi!"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Turnir Setkasini Ko'rish", callback_data="tourney_bracket")],
        [InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]
    ])
    await _safe_edit_or_reply(query, update, text, reply_markup=keyboard)


async def tourney_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'tgan turnirlar tarixi va chempionlar zali"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    async with AsyncSessionLocal() as session:
        history = await crud.get_tournament_history(session, limit=5)
        if not history:
            text = (
                "🏛️🏆 **CHEMPIONLAR ZALI (TURNIR TARIXI)**\n\n"
                "🕊️ *Hozircha yakunlangan turnirlar mavjud emas. Birinchi chempion nomi tez orada bu yerda oltin harflar bilan o'yib yoziladi!*"
            )
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")]])
            await _safe_edit_or_reply(query, update, text, reply_markup=keyboard)
            return

        lines = [
            "🏛️🏆 **CHEMPIONLAR ZALI (O'TGAN TURNIRLAR)**\n",
            "Qirollikning afsonaviy chempionlari va o'tgan turnir natijalari:\n"
        ]
        buttons = []
        for idx, h in enumerate(history, 1):
            w_name = escape_md(str(h["winner_name"]))
            t_name = escape_md(str(h["name"]))
            prize = f"{h['prize_pool']:,}"
            date_str = ""
            if h.get("concluded_at"):
                date_str = f" ({h['concluded_at'].strftime('%Y-%m-%d %H:%M')})"
            lines.append(f"{idx}. 👑 **{w_name}** — _{t_name}_{date_str}")
            lines.append(f"   💰 Jamg'arma: **{prize}** Oltin\n")
            buttons.append([InlineKeyboardButton(f"📊 #{h['id']} Turnir Setkasini Ko'rish", callback_data=f"tourney_bracket_past:{h['id']}")])

        buttons.append([InlineKeyboardButton("🔙 Turnir maydoni", callback_data="menu_tourney")])
        keyboard = InlineKeyboardMarkup(buttons)
        await _safe_edit_or_reply(query, update, "\n".join(lines), reply_markup=keyboard)


async def tourney_bracket_past_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'tgan turnir setkasini ko'rsatish"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    past_id = int(query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        bracket_text = await crud.get_tournament_bracket_display(session, tourney_id=past_id)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏛️ Chempionlar Zaliga qaytish", callback_data="tourney_history")],
            [InlineKeyboardButton("🏇 Turnir maydoniga qaytish", callback_data="menu_tourney")]
        ])
        await _safe_edit_or_reply(query, update, bracket_text, reply_markup=keyboard)


async def admin_tourney_resolve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin tomonidan turnirni hozir yakunlash"""
    query = update.callback_query
    if query:
        try:
            await query.answer("Turnir hisoblanmoqda...")
        except Exception:
            pass

    tg_user = update.effective_user
    if not is_admin(tg_user.id):
        if query:
            await query.answer("❌ Faqat Administrator turnirni yakunlay oladi!", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        ok, report = await crud.resolve_tournament(session, bot_app=context.application)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Turnir Setkasi", callback_data="tourney_bracket")],
            [InlineKeyboardButton("🏇 Turnir maydoniga qaytish", callback_data="menu_tourney")]
        ])
        await _safe_edit_or_reply(query, update, report, reply_markup=keyboard)


async def admin_tourney_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin tomonidan yangi turnirni boshlash"""
    query = update.callback_query
    if query:
        try:
            await query.answer("Turnir e'lon qilinmoqda...")
        except Exception:
            pass

    tg_user = update.effective_user
    if not is_admin(tg_user.id):
        if query:
            await query.answer("❌ Faqat Administrator turnir boshlay oladi!", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        ok, res_msg = await crud.admin_start_tournament(session, bot_app=context.application)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏇 Turnir maydoniga o'tish", callback_data="menu_tourney")]
        ])
        await _safe_edit_or_reply(query, update, res_msg, reply_markup=keyboard)


def register_tourney_handlers(app: Application):
    """Turnir handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["tourney", "tournament"], tourney_menu_callback))
    app.add_handler(CallbackQueryHandler(tourney_menu_callback, pattern="^menu_tourney$"))
    app.add_handler(CallbackQueryHandler(tourney_bracket_callback, pattern="^tourney_bracket$"))
    app.add_handler(CallbackQueryHandler(tourney_enter_pick_callback, pattern="^tourney_enter_pick$"))
    app.add_handler(CallbackQueryHandler(tourney_pick_tactic_callback, pattern="^tourney_pick_tactic:(self|champ)$"))
    app.add_handler(CallbackQueryHandler(tourney_do_enter_callback, pattern="^tourney_do_enter:(self|champ)(?::(rock|scissors|paper|random|wall|strike|viper|whirlwind))?$"))
    app.add_handler(CallbackQueryHandler(tourney_tactic_pick_callback, pattern="^tourney_tactic_pick$"))
    app.add_handler(CallbackQueryHandler(tourney_set_tactic_callback, pattern="^tourney_set_tactic:(rock|scissors|paper|random|wall|strike|viper|whirlwind)$"))
    app.add_handler(CallbackQueryHandler(tourney_seq_r1_callback, pattern="^tourney_seq_r1$"))
    app.add_handler(CallbackQueryHandler(tourney_seq_r2_callback, pattern="^tourney_seq_r2:(rock|scissors|paper)$"))
    app.add_handler(CallbackQueryHandler(tourney_seq_r3_callback, pattern="^tourney_seq_r3:(rock|scissors|paper):(rock|scissors|paper)$"))
    app.add_handler(CallbackQueryHandler(tourney_seq_save_callback, pattern="^tourney_seq_save:(rock|scissors|paper):(rock|scissors|paper):(rock|scissors|paper)$"))
    app.add_handler(CallbackQueryHandler(tourney_history_callback, pattern="^tourney_history$"))
    app.add_handler(CallbackQueryHandler(tourney_bracket_past_callback, pattern="^tourney_bracket_past:\\d+$"))
    app.add_handler(CallbackQueryHandler(tourney_bet_pick_callback, pattern="^tourney_bet_pick$"))
    app.add_handler(CallbackQueryHandler(tourney_bet_amount_callback, pattern="^tourney_bet_fighter:\\d+$"))
    app.add_handler(CallbackQueryHandler(tourney_bet_do_callback, pattern="^tourney_bet_do:\\d+:\\d+$"))
    app.add_handler(CallbackQueryHandler(tourney_rules_callback, pattern="^tourney_rules$"))
    app.add_handler(CallbackQueryHandler(admin_tourney_resolve_callback, pattern="^admin_tourney_resolve$"))
    app.add_handler(CallbackQueryHandler(admin_tourney_start_callback, pattern="^admin_tourney_start$"))
