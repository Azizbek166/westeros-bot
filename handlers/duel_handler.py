from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from keyboards.menus import back_to_main_keyboard
from config import escape_md
from sqlalchemy import select
import html


CHAMPIONS_LIST = [
    ("Arthur Dayne", "🗡️ Ser Arthur Dayne (Tong Qilichi)", "Afsonaviy Qirollik soqchisi, 'Dawn' qilichi sohibi"),
    ("Jaime Lannister", "🦁 Ser Jaime Lannister (Qirol Qotili)", "Westerosning eng tezkor va epchil qilichbozi"),
    ("Daemon Targaryen", "🐉 Shahzoda Daemon Targaryen", "Dark Sister egasi, shafqatsiz jangchi"),
    ("Brienne of Tarth", "🛡️ Brienne of Tarth", "Matonatli, yengilmas va ulkan qalqonli jangchi"),
    ("Gregor Clegane", "💀 Ser Gregor Clegane (Tog')", "Og'ir sovutli, vahshiy qudrat egasi"),
    ("Oberyn Martell", "🐍 Oberyn Martell (Qizil Ilon)", "Zaharli nayza va chaqqon harakatlar ustasi"),
    ("Barristan Selmy", "👑 Ser Barristan Selmy (Jasur)", "Qirollik soqchilarining eng tajribali ritsari"),
    ("Sandor Clegane", "🐕 Sandor Clegane (Tog' Iti)", "Ayovsiz qilichboz va shafqatsiz jangchi"),
    ("Robb Stark", "🐺 Robb Stark (Yosh Bo'ri)", "Shimol Qiroli va mag'lub bo'lmas daho sarkarda"),
    ("Stannis Baratheon", "🦌 Stannis Baratheon (Temir Iroda)", "Ajdartoshi Hukmdori, qat'iyatli va sovuqqon sarkarda"),
    ("Bronn", "🗡️ Ser Bronn of the Blackwater", "Ayyor, tajribali va kutilmagan zarbalar ustasi"),
]


async def duel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/duel buyrug'i: /duel yoki /duel @username [garov]"""
    user_id = update.effective_user.id
    if context.args and len(context.args) >= 1:
        # Tezkor PvP duel taklifi: /duel @username [garov]
        await handle_quick_pvp_command(update, context)
        return

    await show_duel_hub(update, user_id, is_message=True)


async def duel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_duel callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_duel_hub(query, user_id, is_message=False)


async def show_duel_hub(target, user_id: int, is_message: bool):
    """Duellar arenasi markazi"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        await crud.check_and_reset_daily_limits(session, user)
        duel_cnt = getattr(user, "daily_duel_count", 0) or 0
        rem_duels = max(0, 10 - duel_cnt)

        hero = user.characters[0] if user.characters else None
        h_name = hero.name if hero else "Lord"
        h_atk = hero.attack if hero else 50
        h_def = hero.defense if hero else 50

        # Kutilayotgan PvP takliflari soni
        pending = await crud.get_pending_duels_for_user(session, user.id)
        pending_btn_txt = f"📥 Kutilayotgan Duel Takliflari ({len(pending)})" if pending else "📥 Kutilayotgan Duel Takliflari"

        buttons = [
            [InlineKeyboardButton("👥 Boshqa Lord Bilan Duel (PvP)", callback_data="duel_pvp_hub")],
            [InlineKeyboardButton(pending_btn_txt, callback_data="pvp_inbox")],
            [InlineKeyboardButton("⚔️ Mashg'ulot Jangi (Bepul / 0🪙)", callback_data="duel_champ:0")],
            [InlineKeyboardButton("⚔️ Arenada Jang (100🪙)", callback_data="duel_champ:100"),
             InlineKeyboardButton("⚔️ Arenada Jang (250🪙)", callback_data="duel_champ:250")],
            [InlineKeyboardButton("⚔️ Katta Garov (500🪙)", callback_data="duel_champ:500")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ]

        text = (
            f"⚔️ **WESTEROS DUELLAR VA RITSARLAR ARENASI**\n\n"
            f"👤 Jangchingiz: **{escape_md(h_name)}**\n"
            f"⚔️ Hujum: **{h_atk}** | 🛡️ Mudofaa: **{h_def}**\n"
            f"🪙 Xazinangiz: **{user.gold:,}** oltin\n"
            f"🎯 Bugungi duel limitingiz: **{rem_duels}/10** ta jang qoldi\n"
            f"🎁 G'alaba mukofoti: **+500🪙 Oltin, +3 Prestige, +15 XP**\n\n"
            f"Duel turlari:\n"
            f"• 👥 **PvP:** Haqiqiy o'yinchilarga duel e'lon qilish (`/duel @username`)\n"
            f"• ⚔️ **AI Chempionlar:** Vesteros afsonalari bilan jang (bepul yoki garovli)\n"
            f"• 🗡️ Taktika: Og'ir Zarba > Epchil Hamla > Qalqonli Mudofaa > Og'ir Zarba (+45% bonus)\n\n"
            f"Jang turini tanlang:"
        )

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            msg = target.message
            if getattr(msg, "photo", None):
                try:
                    await msg.delete()
                except Exception:
                    pass
                await msg.chat.send_message(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            else:
                try:
                    await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
                except Exception:
                    try:
                        await target.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
                    except Exception:
                        await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ============================================================
# AI CHAMPIONS DUEL FLOW
# ============================================================

async def duel_champ_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Raqib chempionni tanlash"""
    query = update.callback_query
    await query.answer()

    bet_gold = int(query.data.split(":")[1])
    context.user_data["duel_bet"] = bet_gold
    bet_str = "Bepul Mashg'ulot" if bet_gold == 0 else f"Garov: {bet_gold}🪙"

    buttons = []
    for code, title, desc in CHAMPIONS_LIST:
        buttons.append([InlineKeyboardButton(title, callback_data=f"duel_foe:{code}")])
    buttons.append([InlineKeyboardButton("🔙 Arenaga Qaytish", callback_data="menu_duel")])

    text = (
        f"⚔️ **RAQIBNI TANLANG ({bet_str})**\n\n"
        f"Arenada shon-sharaf qozonish uchun kimga qarshi jangga kirasiz?"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def duel_foe_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Taktika tanlash"""
    query = update.callback_query
    await query.answer()

    foe_name = query.data.split(":", 1)[1]
    context.user_data["duel_foe"] = foe_name
    bet_gold = context.user_data.get("duel_bet", 0)
    bet_str = "Bepul Mashg'ulot" if bet_gold == 0 else f"{bet_gold}🪙"

    buttons = [
        [InlineKeyboardButton("🗡️ Og'ir Qilich Zarbasi (Heavy Strike)", callback_data="duel_tactic:heavy")],
        [InlineKeyboardButton("🛡️ Qalqonli Himoya va Qarshi Zarba (Parry)", callback_data="duel_tactic:parry")],
        [InlineKeyboardButton("⚡ Epchil Flang Hamlasi (Agile Flank)", callback_data="duel_tactic:agile")],
        [InlineKeyboardButton("🔙 Arenaga Qaytish", callback_data="menu_duel")],
    ]

    text = (
        f"⚔️ **TAKTIKANGIZNI TANLANG!**\n\n"
        f"Raqib: **{foe_name}** | Garov: **{bet_str}**\n\n"
        f"Qanday jang taktikasini qo'llaysiz?"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def duel_execute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Duelni hisoblash va natijani ko'rsatish"""
    query = update.callback_query
    await query.answer()

    tactic = query.data.split(":")[1]
    foe_name = context.user_data.get("duel_foe", "Gregor Clegane")
    bet_gold = context.user_data.get("duel_bet", 0)
    tg_user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user_id)
        if not user:
            await query.edit_message_text("❌ Foydalanuvchi topilmadi. /start bosing.")
            return

        res = await crud.fight_ai_champion(
            session=session,
            user_id=user.id,
            champion_name=foe_name,
            bet_gold=bet_gold,
            player_tactic=tactic,
        )

    if not res["success"]:
        await query.edit_message_text(f"❌ {res.get('error', 'Xatolik yuz berdi')}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Arenaga Qaytish", callback_data="menu_duel")]]))
        return

    won = res["won"]
    tactic_names = {"heavy": "🗡️ Og'ir Zarba", "parry": "🛡️ Qalqonli Mudofaa", "agile": "⚡ Epchil Hamla"}

    if won:
        gold_line = "🪙 Oltin: **+500 tanga**\n"
        prestige_line = "🏆 Prestige: **+3**\n"
        xp_line = "⭐ XP: **+15 XP**"
    else:
        loss_gold = f"-{bet_gold} tanga" if bet_gold > 0 else "0 tanga"
        gold_line = f"🪙 Oltin: **{loss_gold}**\n"
        prestige_line = "🏆 Prestige: **+0**\n"
        xp_line = "⭐ XP: **+5 XP**"

    text = (
        f"{res['outcome']}\n\n"
        f"👤 Sizning Qahramoningiz: **{escape_md(res['hero_name'])}** ({tactic_names.get(tactic, tactic)})\n"
        f"💀 Raqib: **{escape_md(res['champion_name'])}** ({tactic_names.get(res['champ_tactic'], res['champ_tactic'])})\n\n"
        f"📊 **NATIJA:**\n"
        f"{gold_line}"
        f"{prestige_line}"
        f"{xp_line}"
    )

    buttons = [
        [InlineKeyboardButton("⚔️ Yana Bir Duel", callback_data="menu_duel")],
        [InlineKeyboardButton("🔙 Bosh Menyu", callback_data="menu_main")],
    ]
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ============================================================
# PLAYER VS PLAYER (PvP) DUEL SYSTEM
# ============================================================

async def duel_pvp_hub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PvP markazi va raqiblarni tanlash"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        # Boshqa lordlar ro'yxatini olish (o'zidan boshqa so'nggi faol 8 ta o'yinchi)
        res = await session.execute(
            select(models.User).where(models.User.id != user.id).limit(8)
        )
        other_players = res.scalars().all()

        buttons = []
        for p in other_players:
            p_name = p.username if p.username else p.full_name
            buttons.append([InlineKeyboardButton(f"⚔️ {p.full_name} (@{p_name})", callback_data=f"pvp_pick_user:{p.id}")])

        buttons.append([InlineKeyboardButton("📥 Kutilayotgan Takliflar", callback_data="pvp_inbox")])
        buttons.append([InlineKeyboardButton("🔙 Arenaga Qaytish", callback_data="menu_duel")])

        text = (
            "👥 **LORDLARARO 1V1 PVP DUELLAR**\n\n"
            "Vesterosning boshqa lordlariga qarshi real vaqtda duel e'lon qiling!\n\n"
            "📜 **Qanday e'lon qilinadi?**\n"
            "1. Quyidagi lordlardan birini tanlang yoki buyruq yozing:\n"
            "`/duel @foydalanuvchi [garov]`\n"
            "Masalan: `/duel @lord_stark 250` yoki `/duel @lord_stark 0` (bepul)\n\n"
            "2. Taktikangizni yashirincha tanlaysiz.\n"
            "3. Raqibingizga Telegram orqali duel taklifi yetib boradi. U qabul qilib, o'z taktikasini tanlagach, g'olib aniqlanadi!"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def pvp_pick_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan o'yinchiga garov miqdorini tanlash"""
    query = update.callback_query
    await query.answer()

    target_user_id = int(query.data.split(":")[1])
    context.user_data["pvp_target_id"] = target_user_id

    buttons = [
        [InlineKeyboardButton("⚔️ Bepul Mashg'ulot (0🪙)", callback_data=f"pvp_bet:{target_user_id}:0")],
        [InlineKeyboardButton("⚔️ 100🪙 Garov", callback_data=f"pvp_bet:{target_user_id}:100"),
         InlineKeyboardButton("⚔️ 250🪙 Garov", callback_data=f"pvp_bet:{target_user_id}:250")],
        [InlineKeyboardButton("⚔️ 500🪙 Garov", callback_data=f"pvp_bet:{target_user_id}:500")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="duel_pvp_hub")],
    ]

    text = "Ushbu lord bilan qancha garov tikib duel qilmoqchisiz?"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def pvp_bet_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Garov tanlangach, o'z taktikasini tanlash"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    target_user_id = int(parts[1])
    bet = int(parts[2])
    context.user_data["pvp_target_id"] = target_user_id
    context.user_data["pvp_bet"] = bet

    buttons = [
        [InlineKeyboardButton("🗡️ Og'ir Zarba (Heavy Strike)", callback_data=f"pvp_send:{target_user_id}:{bet}:heavy")],
        [InlineKeyboardButton("🛡️ Qalqonli Himoya (Parry)", callback_data=f"pvp_send:{target_user_id}:{bet}:parry")],
        [InlineKeyboardButton("⚡ Epchil Flang Hamlasi (Agile)", callback_data=f"pvp_send:{target_user_id}:{bet}:agile")],
        [InlineKeyboardButton("🔙 Bekor Qilish", callback_data="duel_pvp_hub")],
    ]

    bet_txt = "Bepul" if bet == 0 else f"{bet}🪙 oltin"
    text = (
        f"⚔️ **YASHIRIN TAKTIKANGIZNI BELGILANG!**\n\n"
        f"Garov: **{bet_txt}**\n"
        f"Raqibingiz siz qaysi taktikani tanlaganingizni ko'ra olmaydi. "
        f"Taktikangizni tanlang va chaqiriq raqibga yuboriladi:"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def pvp_send_challenge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chaqiriqni yuborish"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    target_user_id = parts[1]
    bet = int(parts[2])
    tactic = parts[3]
    sender_tg_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        sender = await crud.get_user_by_telegram_id(session, sender_tg_id)
        if not sender:
            return

        ok, msg, duel, opp_tg_id = await crud.create_pvp_duel(
            session=session,
            challenger_tg_or_id=sender.id,
            opponent_target=target_user_id,
            bet_gold=bet,
            tactic=tactic
        )

    if not ok:
        await query.edit_message_text(f"❌ {msg}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="duel_pvp_hub")]]))
        return

    # Challenger ga tasdiq
    bet_txt = "Bepul" if bet == 0 else f"{bet}🪙"
    await query.edit_message_text(
        f"✅ **DUEL CHAQIRIG'I YUBORILDI!**\n\n"
        f"Garov: **{bet_txt}**\n"
        f"Raqib taklifni qabul qilib, o'z taktikasini tanlashi bilan jang hisoboti keladi.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Arenaga Qaytish", callback_data="menu_duel")]])
    )

    # Opponent ga Telegram xabari
    if opp_tg_id:
        try:
            alert_text = (
                f"⚔️ **SIZGA 1V1 DUEL E'LON QILINDI!**\n\n"
                f"Kimdan: **{sender.full_name}** ({sender.house.name if sender.house else 'Lord'})\n"
                f"🪙 Garov: **{bet_txt}**\n\n"
                f"Qilichingizni sug'urib, jangga kirasizmi?"
            )
            buttons = [
                [InlineKeyboardButton("✅ Qabul Qilish & Taktika Tanlash", callback_data=f"pvp_accept:{duel.id}")],
                [InlineKeyboardButton("❌ Rad Etish", callback_data=f"pvp_reject:{duel.id}")],
            ]
            await context.bot.send_message(chat_id=opp_tg_id, text=alert_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            pass


async def handle_quick_pvp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/duel @username [garov] orqali chaqirish"""
    sender_tg_id = update.effective_user.id
    target_str = context.args[0]
    bet = 0
    if len(context.args) >= 2 and context.args[1].isdigit():
        bet = int(context.args[1])

    async with AsyncSessionLocal() as session:
        sender = await crud.get_user_by_telegram_id(session, sender_tg_id)
        if not sender:
            await update.message.reply_text("❌ Avval /start ni bosing.")
            return

    # Taktika tanlashni so'rash
    buttons = [
        [InlineKeyboardButton("🗡️ Og'ir Zarba", callback_data=f"pvp_cmd_send:{target_str}:{bet}:heavy")],
        [InlineKeyboardButton("🛡️ Qalqonli Mudofaa", callback_data=f"pvp_cmd_send:{target_str}:{bet}:parry")],
        [InlineKeyboardButton("⚡ Epchil Hamla", callback_data=f"pvp_cmd_send:{target_str}:{bet}:agile")],
    ]
    bet_txt = "Bepul" if bet == 0 else f"{bet}🪙"
    await update.message.reply_text(
        f"⚔️ **{target_str} ga qarshi duel (Garov: {bet_txt})**\n\nTaktikangizni tanlang:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def pvp_cmd_send_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buyruq orqali taktikani yuborish"""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    target_str = parts[1]
    bet = int(parts[2])
    tactic = parts[3]
    sender_tg_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        sender = await crud.get_user_by_telegram_id(session, sender_tg_id)
        if not sender:
            return

        ok, msg, duel, opp_tg_id = await crud.create_pvp_duel(
            session=session,
            challenger_tg_or_id=sender.id,
            opponent_target=target_str,
            bet_gold=bet,
            tactic=tactic
        )

    if not ok:
        await query.edit_message_text(f"❌ {msg}")
        return

    bet_txt = "Bepul" if bet == 0 else f"{bet}🪙"
    await query.edit_message_text(f"✅ Chaqiriq muvaffaqiyatli yuborildi! (Garov: {bet_txt})")

    if opp_tg_id:
        try:
            alert_text = (
                f"⚔️ **SIZGA 1V1 DUEL E'LON QILINDI!**\n\n"
                f"Kimdan: **{sender.full_name}**\n"
                f"🪙 Garov: **{bet_txt}**\n\n"
                f"Qabul qilasizmi?"
            )
            buttons = [
                [InlineKeyboardButton("✅ Qabul Qilish & Taktika Tanlash", callback_data=f"pvp_accept:{duel.id}")],
                [InlineKeyboardButton("❌ Rad Etish", callback_data=f"pvp_reject:{duel.id}")],
            ]
            await context.bot.send_message(chat_id=opp_tg_id, text=alert_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            pass


async def pvp_inbox_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kutilayotgan duel takliflarini ko'rish"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        pending = await crud.get_pending_duels_for_user(session, user.id)

    if not pending:
        text = "📭 Hozircha sizga hech kim duel chaqirig'i yubormagan."
        buttons = [[InlineKeyboardButton("🔙 Arenaga Qaytish", callback_data="menu_duel")]]
    else:
        text = "📬 **SIZGA KELGAN DUEL CHAQIRIQLARI:**\n\n"
        buttons = []
        for duel, challenger_name in pending:
            bet_str = "Bepul" if duel.bet_gold == 0 else f"{duel.bet_gold}🪙"
            text += f"• ⚔️ **{challenger_name}** | Garov: **{bet_str}**\n"
            buttons.append([
                InlineKeyboardButton(f"✅ Qabul: {challenger_name}", callback_data=f"pvp_accept:{duel.id}"),
                InlineKeyboardButton("❌ Rad", callback_data=f"pvp_reject:{duel.id}"),
            ])
        buttons.append([InlineKeyboardButton("🔙 Arenaga Qaytish", callback_data="menu_duel")])

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def pvp_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Raqib duelni qabul qilganda taktika tanlashi"""
    query = update.callback_query
    await query.answer()

    duel_id = int(query.data.split(":")[1])

    buttons = [
        [InlineKeyboardButton("🗡️ Og'ir Qilich Zarbasi", callback_data=f"pvp_resolve:{duel_id}:heavy")],
        [InlineKeyboardButton("🛡️ Qalqonli Mudofaa", callback_data=f"pvp_resolve:{duel_id}:parry")],
        [InlineKeyboardButton("⚡ Epchil Hamla", callback_data=f"pvp_resolve:{duel_id}:agile")],
        [InlineKeyboardButton("🔙 Rad Etish", callback_data=f"pvp_reject:{duel_id}")],
    ]

    text = (
        "⚔️ **DUELNI QABUL QILDINGIZ!**\n\n"
        "O'z taktikangizni tanlang — shundan so'ng jang darhol hisoblanadi:"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def pvp_resolve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Raqib taktika tanladi va jang hal bo'ladi"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    duel_id = int(parts[1])
    opponent_tactic = parts[2]
    tg_user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user_id)
        if not user:
            return

        res = await crud.resolve_pvp_duel(
            session=session,
            duel_id=duel_id,
            opponent_tg_or_id=user.id,
            opponent_tactic=opponent_tactic
        )

    if not res["success"]:
        await query.edit_message_text(f"❌ {res['error']}")
        return

    # Opponent (hozirgi o'yinchi) ga natija
    outcome_text = res["outcome"]
    buttons = [
        [InlineKeyboardButton("⚔️ Duellar Arenasi", callback_data="menu_duel")],
        [InlineKeyboardButton("🔙 Bosh Menyu", callback_data="menu_main")],
    ]
    await query.edit_message_text(outcome_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    # Challenger ga xabar yuborish
    challenger_tg = res["challenger_tg_id"]
    if challenger_tg and challenger_tg != tg_user_id:
        try:
            alert = f"🔔 **SIZ E'LON QILGAN DUEL YAKUNLANDI!**\n\n{outcome_text}"
            await context.bot.send_message(chat_id=challenger_tg, text=alert, parse_mode="Markdown")
        except Exception:
            pass


async def pvp_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Duelni rad etish"""
    query = update.callback_query
    await query.answer()

    duel_id = int(query.data.split(":")[1])
    tg_user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, tg_user_id)
        if not user:
            return
        ok, msg, challenger_tg = await crud.reject_pvp_duel(session, duel_id, user.id)

    await query.edit_message_text("❌ Duel chaqirig'i rad etildi.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Arenaga Qaytish", callback_data="menu_duel")]]))

    if challenger_tg:
        try:
            await context.bot.send_message(chat_id=challenger_tg, text=f"ℹ️ Sizning duel taklifingiz {user.full_name} tomonidan rad etildi.")
        except Exception:
            pass


def register_duel_handlers(app):
    app.add_handler(CommandHandler("duel", duel_command))
    app.add_handler(CallbackQueryHandler(duel_callback, pattern="^menu_duel$"))
    app.add_handler(CallbackQueryHandler(duel_champ_pick_callback, pattern="^duel_champ:"))
    app.add_handler(CallbackQueryHandler(duel_foe_pick_callback, pattern="^duel_foe:"))
    app.add_handler(CallbackQueryHandler(duel_execute_callback, pattern="^duel_tactic:"))
    app.add_handler(CallbackQueryHandler(duel_pvp_hub_callback, pattern="^duel_pvp_hub$"))
    app.add_handler(CallbackQueryHandler(pvp_pick_user_callback, pattern="^pvp_pick_user:"))
    app.add_handler(CallbackQueryHandler(pvp_bet_pick_callback, pattern="^pvp_bet:"))
    app.add_handler(CallbackQueryHandler(pvp_send_challenge_callback, pattern="^pvp_send:"))
    app.add_handler(CallbackQueryHandler(pvp_cmd_send_callback, pattern="^pvp_cmd_send:"))
    app.add_handler(CallbackQueryHandler(pvp_inbox_callback, pattern="^pvp_inbox$"))
    app.add_handler(CallbackQueryHandler(pvp_accept_callback, pattern="^pvp_accept:"))
    app.add_handler(CallbackQueryHandler(pvp_resolve_callback, pattern="^pvp_resolve:"))
    app.add_handler(CallbackQueryHandler(pvp_reject_callback, pattern="^pvp_reject:"))
