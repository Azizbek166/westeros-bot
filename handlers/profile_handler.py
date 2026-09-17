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

        text = (
            f"👤 **LORD PROFILI**\n\n"
            f"👑 Ism: **{escape_md(hero.name if hero else user.full_name)}**\n"
            f"🏰 Xonadon: **{house_str}**\n"
            f"🎖️ Lavozim: **{user.rank.title()}**\n"
            f"⭐ Daraja: **{lvl} / 30** — **{title}**\n"
            f"📈 Tajriba: `[{prog_bar}]` **{user.xp:,} / {next_req:,} XP** ({int(progress)}%)\n"
            f"{art_str}"
            f"🏆 Prestige: **{user.prestige:,}**\n\n"
            f"📊 **XAZINA VA IQTISOD:**\n"
            f"🪙 Oltin: **{user.gold:,}** (+{income['gold']}/soat)\n"
            f"🌾 Oziq-ovqat: **{user.food:,}** (+{income['food']}/soat, Upkeep: -{int(upkeep)}/soat)\n"
            f"⛓️ Temir: **{user.iron:,}** (+{income['iron']}/soat)\n"
            f"⛏️ Temir Koni: **Lv.{getattr(user, 'iron_mine_level', 1) or 1}** (+{(getattr(user, 'iron_mine_level', 1) or 1) * 50}⛓️/soat)\n"
            f"🌾 Don Tegirmoni: **Lv.{getattr(user, 'grain_mill_level', 1) or 1}** (+{(getattr(user, 'grain_mill_level', 1) or 1) * 75}🌾/soat)\n\n"
            f"⚔️ **ARMIYA TARKIBI:**\n"
            f"🛡️ Piyodalar: **{inf_cnt:,}**\n"
            f"🏹 Kamonchilar: **{arc_cnt:,}**\n"
            f"🐎 Otliqlar: **{cav_cnt:,}**\n"
            f"🗡️ Nayzachilar: **{spm_cnt:,}**\n"
            f"🔥 Maxsus Qo'shin: **{spc_cnt:,}**\n\n"
            f"🔰 **TINCHLIK QALQONI:** {shield_str}"
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


async def show_artifacts_menu(target, user_id: int, is_message: bool = False):
    """Afsonaviy artefaktlar qurolxonasi menyusi"""
    from data.artifacts_data import ARTIFACTS_DATA
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        user_arts = await crud.get_user_artifacts(session, user.id)
        equipped = await crud.get_equipped_artifact(session, user.id)

    owned_map = {a.code: a for a in user_arts}

    eq_text = "⚔️ **Hozir taqilgan:** _Hech narsa taqilmagan_\n"
    if equipped and equipped.code in ARTIFACTS_DATA:
        info = ARTIFACTS_DATA[equipped.code]
        eq_text = (
            f"⚔️ **Hozir taqilgan:** **{info['name']}**\n"
            f"📖 _{info['description']}_\n"
        )

    text = (
        f"🗡️ **VESTEROS AFSONAVIY ARTEFAKTLARI (ARMORY)**\n\n"
        f"{eq_text}\n"
        f"O'zingizga munosib afsonaviy qurol yoki relikni taqing! Har bir artefakt janglarda, duellarda va ajdar quvvatida ulkan afzallik beradi.\n\n"
        f"💰 Sizning boyligingiz: **{user.gold:,}**🪙 Oltin, **{user.iron:,}**⛓️ Temir\n\n"
        f"📜 **ARTEFAKTLAR RO'YXATI VA KUCHLARI:**\n\n"
    )

    buttons = []
    for code, data in ARTIFACTS_DATA.items():
        is_owned = code in owned_map
        is_eq = is_owned and owned_map[code].is_equipped
        bonus_desc = []
        if data.get("duel_bonus", 0) > 0:
            bonus_desc.append(f"⚔️ Duelda +{int(data['duel_bonus']*100)}%")
        if data.get("attack_bonus", 0) > 0:
            bonus_desc.append(f"🗡️ Hujumda +{int(data['attack_bonus']*100)}%")
        if data.get("defense_bonus", 0) > 0:
            bonus_desc.append(f"🛡️ Mudofaada +{int(data['defense_bonus']*100)}%")
        if data.get("dragon_bonus", 0) > 0:
            bonus_desc.append(f"🔥 Drakarysda +{int(data['dragon_bonus']*100)}%")

        bonus_str = " | ".join(bonus_desc) if bonus_desc else "Maxsus afzallik"
        status_str = "✅ [Sizda bor]" if is_owned else f"Narxi: {data['price_gold']:,}🪙 / {data['price_iron']:,}⛓️"
        text += (
            f"• **{data['name']}**\n"
            f"  📌 {status_str}\n"
            f"  ⚡ Kuchlari: **{bonus_str}**\n"
            f"  📖 _{data['description']}_\n\n"
        )

        if is_owned:
            art_id = owned_map[code].id
            if is_eq:
                buttons.append([InlineKeyboardButton(f"🚫 {data['name'][:22]} (Yechish)", callback_data="unequip_art")])
            else:
                buttons.append([InlineKeyboardButton(f"⚡ {data['name'][:22]} (Taqish)", callback_data=f"equip_art_{art_id}")])
        else:
            buttons.append([InlineKeyboardButton(f"🛒 Xarid: {data['name'][:18]} ({data['price_gold']:,}🪙)", callback_data=f"buy_art_{code}")])

    buttons.append([InlineKeyboardButton("🔙 Profilga Qaytish", callback_data="menu_profile")])

    if is_message:
        await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def show_iron_mine_menu(target, user_id: int, is_message: bool = False):
    """Temir koni va oltin-temir savdo karvoni menyusi"""
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
            f"⛏️ **TEMIR KONI, DON TEGIRMONI VA BOZOR**\n\n"
            f"Vesterosda armiyani boqish uchun don (oziq-ovqat) va sovut-qurollar uchun temir eng muhim manba hisoblanadi!\n\n"
            f"⛏️ **Temir Koni:**\n"
            f"• Darajasi: **Lv.{mine_lvl} / 10**\n"
            f"• Hosildorlik: **+{curr_prod}⛓️ Temir / soat**\n"
        )
        if mine_lvl < 10:
            text += f"• Yangilash (Lv.{mine_lvl + 1}): **{gold_cost:,}🪙 Oltin | {food_cost:,}🌾 Oziq** (+{next_prod}⛓️/soat)\n\n"
        else:
            text += "• 🏆 *Kon maksimal darajaga yetgan!*\n\n"

        text += (
            f"🌾 **Don Tegirmoni (Grain Mill):**\n"
            f"• Darajasi: **Lv.{mill_lvl} / 10**\n"
            f"• Hosildorlik: **+{mill_prod}🌾 Oziq-ovqat / soat**\n"
        )
        if mill_lvl < 10:
            text += f"• Yangilash (Lv.{mill_lvl + 1}): **{mill_gold_cost:,}🪙 Oltin | {mill_iron_cost:,}⛓️ Temir** (+{mill_next_prod}🌾/soat)\n\n"
        else:
            text += "• 🏆 *Tegirmon maksimal darajaga yetgan!*\n\n"

        text += (
            f"💰 **Xazinangiz:** **{user.gold:,}**🪙 Oltin | **{user.food:,}**🌾 Oziq-ovqat | **{user.iron:,}**⛓️ Temir\n\n"
            f"🐪 **SAVDO KARVONLARI (OLTINGA TEMIR XARID QILISH):**\n"
            f"• 1-To'plam: 500🪙 ➡️ **300⛓️ Temir**\n"
            f"• 2-To'plam: 1,000🪙 ➡️ **700⛓️ Temir** (+100 bonus)\n"
            f"• 3-To'plam: 2,500🪙 ➡️ **1,900⛓️ Temir** (+400 bonus)\n"
            f"• 4-To'plam: 5,000🪙 ➡️ **4,200⛓️ Temir** (+1,200 bonus)\n"
        )

        buttons = []
        if mine_lvl < 10:
            buttons.append([
                InlineKeyboardButton(f"⛏️ Konni Yangilash (Lv.{mine_lvl + 1})", callback_data="upgrade_iron_mine")
            ])
        if mill_lvl < 10:
            buttons.append([
                InlineKeyboardButton(f"🌾 Tegirmonni Yangilash (Lv.{mill_lvl + 1})", callback_data="upgrade_grain_mill")
            ])

        buttons.append([
            InlineKeyboardButton("🛒 300⛓️ (500🪙)", callback_data="buy_iron:pack_1"),
            InlineKeyboardButton("🛒 700⛓️ (1,000🪙)", callback_data="buy_iron:pack_2"),
        ])
        buttons.append([
            InlineKeyboardButton("🛒 1,900⛓️ (2,500🪙)", callback_data="buy_iron:pack_3"),
            InlineKeyboardButton("🛒 4,200⛓️ (5,000🪙)", callback_data="buy_iron:pack_4"),
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


async def artifacts_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_artifacts_menu(query, query.from_user.id, is_message=False)


async def buy_artifact_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    code = query.data.replace("buy_art_", "")
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.buy_artifact(session, user.id, code)

    await query.answer(msg, show_alert=True)
    await show_artifacts_menu(query, user_id, is_message=False)


async def equip_artifact_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    art_id = int(query.data.replace("equip_art_", ""))
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.equip_artifact(session, user.id, art_id)

    await query.answer(msg, show_alert=True)
    await show_artifacts_menu(query, user_id, is_message=False)


async def unequip_artifact_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
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
    await show_artifacts_menu(query, user_id, is_message=False)


def register_profile_handlers(app):
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler(["daily", "bonus"], daily_bonus_callback))
    app.add_handler(CommandHandler(["mine", "iron", "kon"], iron_mine_command))
    app.add_handler(CallbackQueryHandler(profile_callback, pattern="^menu_profile$"))
    app.add_handler(CallbackQueryHandler(daily_bonus_callback, pattern="^claim_daily_bonus$"))
    app.add_handler(CallbackQueryHandler(artifacts_menu_callback, pattern="^menu_artifacts$"))
    app.add_handler(CallbackQueryHandler(buy_artifact_callback, pattern="^buy_art_"))
    app.add_handler(CallbackQueryHandler(equip_artifact_callback, pattern="^equip_art_"))
    app.add_handler(CallbackQueryHandler(unequip_artifact_callback, pattern="^unequip_art$"))
    app.add_handler(CallbackQueryHandler(iron_mine_callback, pattern="^menu_iron_mine$"))
    app.add_handler(CallbackQueryHandler(upgrade_mine_callback, pattern="^upgrade_iron_mine$"))
    app.add_handler(CallbackQueryHandler(upgrade_grain_mill_callback, pattern="^upgrade_grain_mill$"))
    app.add_handler(CallbackQueryHandler(buy_iron_callback, pattern="^buy_iron:"))
