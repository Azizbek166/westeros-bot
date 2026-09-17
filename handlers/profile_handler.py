from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud
from core.economy_engine import calculate_army_upkeep, calculate_hourly_income
from keyboards.menus import back_to_main_keyboard
from config import escape_md


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/profile buyrug'i"""
    user_id = update.effective_user.id
    await show_profile(update, user_id, is_message=True)


async def profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_profile callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_profile(query, user_id, is_message=False)


async def show_profile(target, user_id: int, is_message: bool):
    """Profil ma'lumotlarini formatlab chiqarish"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            msg = "❌ Siz hali ro'yxatdan o'tmagansiz. /start ni bosing."
            if is_message:
                await target.message.reply_text(msg)
            else:
                await target.edit_message_text(msg)
            return

        from core.leveling import get_level_info, check_user_level_up
        leveled_up, new_lvl, lvl_msg = check_user_level_up(user)
        if leveled_up:
            await session.commit()

        lvl, title, curr_req, next_req, progress = get_level_info(user.xp or 0)
        prog_bar = "█" * int(progress // 10) + "░" * (10 - int(progress // 10))

        upkeep = calculate_army_upkeep(user.army) if user.army else 0
        income = await calculate_hourly_income(session, user)
        hero = user.characters[0] if user.characters else None

        # Taqilgan artefakt
        equipped_art = await crud.get_equipped_artifact(session, user.id)
        art_str = f"🗡️ Taqilgan Artefakt: **{equipped_art.name}**\n" if equipped_art else "🗡️ Taqilgan Artefakt: *Mavjud emas*\n"

        # Qalqon holati
        shield_str = "❌ Faol emas"
        if user.peace_shield_until and user.peace_shield_until > datetime.utcnow():
            diff = user.peace_shield_until - datetime.utcnow()
            hours = int(diff.total_seconds() // 3600)
            shield_str = f"🛡️ Faol ({hours} soat qoldi)"

        house_str = f"{user.house.emoji} {user.house.name} ({user.house.region})" if user.house else "Tanlanmagan"
        inf_cnt = user.army.infantry if user.army else 0
        arc_cnt = user.army.archers if user.army else 0
        cav_cnt = user.army.cavalry if user.army else 0
        spm_cnt = user.army.spearmen if user.army else 0
        spc_cnt = user.army.special_troops if user.army else 0

        net_food = income['food'] - int(upkeep)
        net_food_str = f"+{net_food}" if net_food >= 0 else f"{net_food}"
        art_line = f"🗡️ Artefakt: **{equipped_art.name}**\n" if equipped_art else ""

        text = (
            f"👤 **LORD PROFILI**\n\n"
            f"👑 **{escape_md(hero.name if hero else user.full_name)}** | {house_str}\n"
            f"🎖️ {user.rank.title()} | ⭐ Lv.{lvl}/30 ({title}) | 🏆 {user.prestige:,} Prestige\n"
            f"📈 `[{prog_bar}]` {user.xp:,}/{next_req:,} XP ({int(progress)}%)\n"
            f"{art_line}"
            f"🔰 Qalqon: {shield_str}\n\n"
            f"📊 **Xazina:** 🪙**{user.gold:,}** (+{income['gold']}/s) | 🌾**{user.food:,}** ({net_food_str}/s) | ⛓️**{user.iron:,}** (+{income['iron']}/s)\n"
            f"⚔️ **Qo'shin:** 🛡️{inf_cnt:,} | 🏹{arc_cnt:,} | 🐎{cav_cnt:,} | 🗡️{spm_cnt:,} | 🔥{spc_cnt:,}"
        )

        buttons = [
            [InlineKeyboardButton("⛏️ Kon, 🌾 Tegirmon & Bozor", callback_data="menu_iron_mine")],
            [InlineKeyboardButton("🗡️ Afsonaviy Artefaktlar (Armory)", callback_data="menu_artifacts")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ]

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def daily_bonus_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kunlik sovg'ani olish"""
    query = update.callback_query if update.callback_query else None
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            if query:
                await query.answer("❌ Avval /start bosing.", show_alert=True)
            else:
                await update.message.reply_text("❌ Avval /start bosing.")
            return

        ok, msg = await crud.claim_daily_bonus(session, user.id)

    if query:
        await query.answer(msg, show_alert=True)
        if ok:
            await show_profile(query, user_id, is_message=False)
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")


async def show_artifacts_menu(target, user_id: int, is_message: bool = False, page: int = 0):
    """Afsonaviy artefaktlar qurolxonasi menyusi (ixcham va sahifalangan)"""
    from data.artifacts_data import ARTIFACTS_DATA
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        user_arts = await crud.get_user_artifacts(session, user.id)
        equipped = await crud.get_equipped_artifact(session, user.id)

    owned_map = {a.code: a for a in user_arts}

    eq_str = "_Hech narsa taqilmagan_"
    if equipped and equipped.code in ARTIFACTS_DATA:
        info = ARTIFACTS_DATA[equipped.code]
        eq_str = f"**{info['name']}**"

    all_items = list(ARTIFACTS_DATA.items())
    PAGE_SIZE = 4
    total_pages = max(1, (len(all_items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_items = all_items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    text = (
        f"🗡️ **AFSONAVIY ARTEFAKTLAR (ARMORY)**\n"
        f"⚔️ **Taqilgan:** {eq_str}\n"
        f"💰 **Xazina:** **{user.gold:,}**🪙 Oltin | **{user.iron:,}**⛓️ Temir\n"
        f"📄 Sahifa: **{page + 1} / {total_pages}**\n\n"
    )

    buttons = []
    for code, data in page_items:
        is_owned = code in owned_map
        is_eq = is_owned and owned_map[code].is_equipped
        bonus_desc = []
        if data.get("duel_bonus", 0) > 0:
            bonus_desc.append(f"Duel +{int(data['duel_bonus']*100)}%")
        if data.get("attack_bonus", 0) > 0:
            bonus_desc.append(f"Hujum +{int(data['attack_bonus']*100)}%")
        if data.get("defense_bonus", 0) > 0:
            bonus_desc.append(f"Mudofaa +{int(data['defense_bonus']*100)}%")
        if data.get("dragon_bonus", 0) > 0:
            bonus_desc.append(f"Drakarys +{int(data['dragon_bonus']*100)}%")

        bonus_str = ", ".join(bonus_desc) if bonus_desc else "Maxsus afzallik"
        status_tag = "✅ Sizda bor" if is_owned else f"{data['price_gold']:,}🪙/{data['price_iron']:,}⛓️"

        text += (
            f"• **{data['name']}** ({status_tag})\n"
            f"  ⚡ *{bonus_str}*\n"
        )

        if is_owned:
            art_id = owned_map[code].id
            if is_eq:
                buttons.append([InlineKeyboardButton(f"🚫 {data['name'][:20]} (Yechish)", callback_data=f"unequip_art:{page}")])
            else:
                buttons.append([InlineKeyboardButton(f"⚡ {data['name'][:20]} (Taqish)", callback_data=f"equip_art_{art_id}:{page}")])
        else:
            buttons.append([InlineKeyboardButton(f"🛒 Xarid: {data['name'][:18]} ({data['price_gold']:,}🪙)", callback_data=f"buy_art_{code}:{page}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"menu_art_pg:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"menu_art_pg:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("🔙 Profilga Qaytish", callback_data="menu_profile")])

    if is_message:
        await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def show_iron_mine_menu(target, user_id: int, is_message: bool = False):
    """Temir koni va oltin-temir savdo karvoni menyusi (ixcham ko'rinish)"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return

        mine_lvl = user.iron_mine_level or 1
        curr_prod = mine_lvl * 50
        next_prod = (mine_lvl + 1) * 50
        gold_cost = mine_lvl * 1500
        food_cost = mine_lvl * 800

        mill_lvl = getattr(user, "grain_mill_level", 1) or 1
        mill_prod = mill_lvl * 75
        mill_next_prod = (mill_lvl + 1) * 75
        mill_gold_cost = mill_lvl * 1200
        mill_iron_cost = mill_lvl * 600

        text = (
            f"⛏️ **KON, TEGIRMON VA BOZOR**\n"
            f"💰 **Xazina:** {user.gold:,}🪙 | {user.food:,}🌾 | {user.iron:,}⛓️\n\n"
            f"⛏️ **Kon:** Lv.{mine_lvl}/10 (+{curr_prod}⛓️/s)"
        )
        if mine_lvl < 10:
            text += f" | Keyingi: {gold_cost:,}🪙 {food_cost:,}🌾\n"
        else:
            text += " (MAX)\n"

        text += f"🌾 **Tegirmon:** Lv.{mill_lvl}/10 (+{mill_prod}🌾/s)"
        if mill_lvl < 10:
            text += f" | Keyingi: {mill_gold_cost:,}🪙 {mill_iron_cost:,}⛓️\n\n"
        else:
            text += " (MAX)\n\n"

        text += (
            f"🌾 **Oziq-ovqat Bozori (Don):**\n"
            f"• Xarid: 300🪙➡️390🌾 | 500🪙➡️700🌾 | 1k🪙➡️1,500🌾\n"
            f"• Sotish: 500🌾➡️250🪙 | 1k🌾➡️500🪙 | 5k🌾➡️2,500🪙 `(/sellfood 1000)`\n\n"
            f"⛓️ **Temir Bozori:**\n"
            f"• Xarid: 500🪙➡️300⛓️ | 1k🪙➡️700⛓️ | 2.5k🪙➡️1,900⛓️\n"
            f"• Sotish: 300⛓️➡️300🪙 | 700⛓️➡️700🪙 | 1.5k⛓️➡️1,500🪙 `(/selliron 500)`\n\n"
            f"⚖️ **Xonadonlararo Savdo:** Boshqa xonadonlar bilan savdo qilish uchun `/trade` bosing!"
        )

        buttons = []
        up_row = []
        if mine_lvl < 10:
            up_row.append(InlineKeyboardButton(f"⛏️ Kon Lv.{mine_lvl + 1}", callback_data="upgrade_iron_mine"))
        if mill_lvl < 10:
            up_row.append(InlineKeyboardButton(f"🌾 Tegirmon Lv.{mill_lvl + 1}", callback_data="upgrade_grain_mill"))
        if up_row:
            buttons.append(up_row)

        buttons.append([
            InlineKeyboardButton("🌾 390 (300🪙)", callback_data="buy_food:food_1"),
            InlineKeyboardButton("🌾 700 (500🪙)", callback_data="buy_food:food_2"),
            InlineKeyboardButton("🌾 1.5k (1k🪙)", callback_data="buy_food:food_3"),
        ])
        buttons.append([
            InlineKeyboardButton("🌾 4k (2.5k🪙)", callback_data="buy_food:food_4"),
            InlineKeyboardButton("🌾 9k (5k🪙)", callback_data="buy_food:food_5"),
        ])
        buttons.append([
            InlineKeyboardButton("⛓️ 300 (500🪙)", callback_data="buy_iron:pack_1"),
            InlineKeyboardButton("⛓️ 700 (1k🪙)", callback_data="buy_iron:pack_2"),
        ])
        buttons.append([
            InlineKeyboardButton("⛓️ 1.9k (2.5k🪙)", callback_data="buy_iron:pack_3"),
            InlineKeyboardButton("⛓️ 4.2k (5k🪙)", callback_data="buy_iron:pack_4"),
        ])
        buttons.append([
            InlineKeyboardButton("💰 500🌾➡️250🪙", callback_data="sell_res:food:500"),
            InlineKeyboardButton("💰 1k🌾➡️500🪙", callback_data="sell_res:food:1000"),
            InlineKeyboardButton("💰 5k🌾➡️2.5k🪙", callback_data="sell_res:food:5000"),
        ])
        buttons.append([
            InlineKeyboardButton("💰 300⛓️➡️300🪙", callback_data="sell_res:iron:300"),
            InlineKeyboardButton("💰 700⛓️➡️700🪙", callback_data="sell_res:iron:700"),
            InlineKeyboardButton("💰 1.5k⛓️➡️1.5k🪙", callback_data="sell_res:iron:1500"),
        ])
        buttons.append([
            InlineKeyboardButton("⚖️ Xonadonlararo Savdo Birjasi", callback_data="menu_trade"),
        ])
        buttons.append([
            InlineKeyboardButton("🔙 Profilga Qaytish", callback_data="menu_profile"),
            InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main"),
        ])

    if is_message:
        await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def iron_mine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mine, /iron, /kon buyruqlari"""
    user_id = update.effective_user.id
    await show_iron_mine_menu(update, user_id, is_message=True)


async def buy_food_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/buyfood, /food, /oziq, /bozor buyruqlari"""
    user_id = update.effective_user.id
    if context.args and len(context.args) > 0:
        arg = context.args[0].strip()
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, user_id)
            if not user:
                await update.message.reply_text("❌ Avval /start bosing.")
                return
            ok, msg = await crud.buy_food_with_gold(session, user.id, arg)
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

    await show_iron_mine_menu(update, user_id, is_message=True)


async def iron_mine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_iron_mine callback"""
    query = update.callback_query
    await query.answer()
    await show_iron_mine_menu(query, query.from_user.id, is_message=False)


async def upgrade_mine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Temir konini yangilash callback"""
    query = update.callback_query
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.upgrade_iron_mine(session, user.id)

    await query.answer(msg, show_alert=True)
    await show_iron_mine_menu(query, user_id, is_message=False)


async def upgrade_grain_mill_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Don tegirmonini yangilash callback"""
    query = update.callback_query
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.upgrade_grain_mill(session, user.id)

    await query.answer(msg, show_alert=True)
    await show_iron_mine_menu(query, user_id, is_message=False)


async def buy_iron_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oltin evaziga temir xarid qilish callback"""
    query = update.callback_query
    pack_code = query.data.replace("buy_iron:", "")
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.buy_iron_with_gold(session, user.id, pack_code)

    await query.answer(msg, show_alert=True)
    await show_iron_mine_menu(query, user_id, is_message=False)


async def buy_food_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oltin evaziga oziq-ovqat xarid qilish callback"""
    query = update.callback_query
    pack_code = query.data.replace("buy_food:", "")
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.buy_food_with_gold(session, user.id, pack_code)

    await query.answer(msg, show_alert=True)
    await show_iron_mine_menu(query, user_id, is_message=False)


async def sell_res_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resurslarni oltinga sotish callback"""
    query = update.callback_query
    parts = query.data.split(":")
    res_type = parts[1]
    amount = int(parts[2])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        if res_type == "food":
            ok, msg = await crud.sell_food_for_gold(session, user.id, amount)
        else:
            ok, msg = await crud.sell_iron_for_gold(session, user.id, amount)

    try:
        await query.answer(msg.replace("**", "").replace("*", ""), show_alert=True)
    except Exception:
        pass
    await show_iron_mine_menu(query, user_id, is_message=False)


async def sell_food_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sellfood <miqdor> buyrug'i"""
    user_id = update.effective_user.id
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("ℹ️ Don sotish uchun miqdorni yozing: `/sellfood 1000`\n(Kurs: 2 Don = 1 Oltin)", parse_mode="Markdown")
        return
    try:
        amt = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("❌ Miqdor faqat son bo'lishi kerak! Masalan: `/sellfood 1000`", parse_mode="Markdown")
        return

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        ok, msg = await crud.sell_food_for_gold(session, user.id, amt)
    await update.message.reply_text(msg, parse_mode="Markdown")


async def sell_iron_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/selliron <miqdor> buyrug'i"""
    user_id = update.effective_user.id
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("ℹ️ Temir sotish uchun miqdorni yozing: `/selliron 500`\n(Kurs: 1 Temir = 1 Oltin)", parse_mode="Markdown")
        return
    try:
        amt = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("❌ Miqdor faqat son bo'lishi kerak! Masalan: `/selliron 500`", parse_mode="Markdown")
        return

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        ok, msg = await crud.sell_iron_for_gold(session, user.id, amt)
    await update.message.reply_text(msg, parse_mode="Markdown")


async def artifacts_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_artifacts_menu(query, query.from_user.id, is_message=False, page=0)


async def artifacts_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split(":")[1]) if ":" in query.data else 0
    await show_artifacts_menu(query, query.from_user.id, is_message=False, page=page)


async def buy_artifact_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    raw = query.data.replace("buy_art_", "")
    parts = raw.split(":")
    code = parts[0]
    page = int(parts[1]) if len(parts) > 1 else 0
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.buy_artifact(session, user.id, code)

    await query.answer(msg, show_alert=True)
    await show_artifacts_menu(query, user_id, is_message=False, page=page)


async def equip_artifact_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    raw = query.data.replace("equip_art_", "")
    parts = raw.split(":")
    art_id = int(parts[0])
    page = int(parts[1]) if len(parts) > 1 else 0
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.equip_artifact(session, user.id, art_id)

    await query.answer(msg, show_alert=True)
    await show_artifacts_menu(query, user_id, is_message=False, page=page)


async def unequip_artifact_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split(":")
    page = int(parts[1]) if len(parts) > 1 else 0
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if user:
            user.equipped_artifact_id = None
            arts = await crud.get_user_artifacts(session, user.id)
            for a in arts:
                a.is_equipped = False
            await session.commit()

    await query.answer("🛡️ Artefakt qurolxonaga olib qo'yildi.", show_alert=True)
    await show_artifacts_menu(query, user_id, is_message=False, page=page)


def register_profile_handlers(app):
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler(["daily", "bonus"], daily_bonus_callback))
    app.add_handler(CommandHandler(["mine", "iron", "kon", "tegirmon"], iron_mine_command))
    app.add_handler(CommandHandler(["buyfood", "food", "oziq", "bozor"], buy_food_command))
    app.add_handler(CommandHandler(["sellfood", "don_sotish"], sell_food_command))
    app.add_handler(CommandHandler(["selliron", "temir_sotish"], sell_iron_command))
    app.add_handler(CallbackQueryHandler(profile_callback, pattern="^menu_profile$"))
    app.add_handler(CallbackQueryHandler(daily_bonus_callback, pattern="^claim_daily_bonus$"))
    app.add_handler(CallbackQueryHandler(artifacts_menu_callback, pattern="^menu_artifacts$"))
    app.add_handler(CallbackQueryHandler(artifacts_page_callback, pattern="^menu_art_pg:"))
    app.add_handler(CallbackQueryHandler(buy_artifact_callback, pattern="^buy_art_"))
    app.add_handler(CallbackQueryHandler(equip_artifact_callback, pattern="^equip_art_"))
    app.add_handler(CallbackQueryHandler(unequip_artifact_callback, pattern="^unequip_art(:[0-9]+)?$"))
    app.add_handler(CallbackQueryHandler(iron_mine_callback, pattern="^menu_iron_mine$"))
    app.add_handler(CallbackQueryHandler(upgrade_mine_callback, pattern="^upgrade_iron_mine$"))
    app.add_handler(CallbackQueryHandler(upgrade_grain_mill_callback, pattern="^upgrade_grain_mill$"))
    app.add_handler(CallbackQueryHandler(buy_iron_callback, pattern="^buy_iron:"))
    app.add_handler(CallbackQueryHandler(buy_food_callback, pattern="^buy_food:"))
    app.add_handler(CallbackQueryHandler(sell_res_callback, pattern="^sell_res:"))
