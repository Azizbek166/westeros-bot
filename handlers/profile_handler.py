from datetime import datetime
from telegram import Update
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
        await check_user_level_up(session, user)
        lvl, title, curr_req, next_req, progress = get_level_info(user.xp or 0)
        prog_bar = "█" * int(progress // 10) + "░" * (10 - int(progress // 10))

        upkeep = calculate_army_upkeep(user.army)
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

        text = (
            f"👤 **LORD PROFILI**\n\n"
            f"👑 Ism: **{escape_md(hero.name if hero else user.full_name)}**\n"
            f"🏰 Xonadon: **{user.house.emoji} {user.house.name}** ({user.house.region})\n"
            f"🎖️ Lavozim: **{user.rank.title()}**\n"
            f"⭐ Daraja: **{lvl} / 30** — **{title}**\n"
            f"📈 Tajriba: `[{prog_bar}]` **{user.xp:,} / {next_req:,} XP** ({int(progress)}%)\n"
            f"{art_str}"
            f"🏆 Prestige: **{user.prestige:,}**\n\n"
            f"📊 **XAZINA VA IQTISOD:**\n"
            f"🪙 Oltin: **{user.gold:,}** (+{income['gold']}/soat)\n"
            f"🌾 Oziq-ovqat: **{user.food:,}** (+{income['food']}/soat, Upkeep: -{int(upkeep)}/soat)\n"
            f"⛓️ Temir: **{user.iron:,}** (+{income['iron']}/soat)\n\n"
            f"⚔️ **ARMIYA TARKIBI:**\n"
            f"🛡️ Piyodalar: **{user.army.infantry:,}**\n"
            f"🏹 Kamonchilar: **{user.army.archers:,}**\n"
            f"🐎 Otliqlar: **{user.army.cavalry:,}**\n"
            f"🗡️ Nayzachilar: **{user.army.spearmen:,}**\n"
            f"🔥 Maxsus Qo'shin: **{user.army.special_troops:,}**\n\n"
            f"🔰 **TINCHLIK QALQONI:** {shield_str}"
        )

        buttons = [
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

    eq_text = "⚔️ **Hozir taqilgan:** Yo'q\n"
    if equipped and equipped.code in ARTIFACTS_DATA:
        info = ARTIFACTS_DATA[equipped.code]
        eq_text = (
            f"⚔️ **Hozir taqilgan:** {info['name']}\n"
            f"✨ _{info['description']}_\n"
        )

    text = (
        f"🗡️ **VESTEROS AFSONAVIY ARTEFAKTLARI (ARMORY)**\n\n"
        f"{eq_text}\n"
        f"O'zingizga munosib qurol yoki relikni taqing! Har bir artefakt janglarda, duellarda va ajdar quvvatida ulkan afzallik beradi.\n\n"
        f"💰 Sizning boyligingiz: **{user.gold:,}**🪙 Oltin, **{user.iron:,}**⛓️ Temir\n\n"
        f"📜 **KATALOG:**\n"
    )

    buttons = []
    for code, data in ARTIFACTS_DATA.items():
        is_owned = code in owned_map
        is_eq = is_owned and owned_map[code].is_equipped
        bonus_desc = []
        if data.get("duel_bonus", 0) > 0:
            bonus_desc.append(f"+{int(data['duel_bonus']*100)}% Duel")
        if data.get("attack_bonus", 0) > 0:
            bonus_desc.append(f"+{int(data['attack_bonus']*100)}% Hujum")
        if data.get("defense_bonus", 0) > 0:
            bonus_desc.append(f"+{int(data['defense_bonus']*100)}% Mudofaa")
        if data.get("dragon_bonus", 0) > 0:
            bonus_desc.append(f"+{int(data['dragon_bonus']*100)}% Ajdar")

        bonus_str = ", ".join(bonus_desc)
        status_str = "✅ [Sizda bor]" if is_owned else f"{data['price_gold']:,}🪙 / {data['price_iron']:,}⛓️"
        text += f"• **{data['name']}** ({status_str})\n  _{bonus_str}_\n"

        if is_owned:
            art_id = owned_map[code].id
            if is_eq:
                buttons.append([InlineKeyboardButton(f"🚫 {data['name'][:22]} (Yechish)", callback_data="unequip_art")])
            else:
                buttons.append([InlineKeyboardButton(f"⚡ {data['name'][:22]} (Taqish)", callback_data=f"equip_art_{art_id}")])
        else:
            buttons.append([InlineKeyboardButton(f"🛒 {data['name'][:20]} ({data['price_gold']:,}🪙)", callback_data=f"buy_art_{code}")])

    buttons.append([InlineKeyboardButton("🔙 Profilga Qaytish", callback_data="menu_profile")])

    if is_message:
        await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


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
    app.add_handler(CallbackQueryHandler(profile_callback, pattern="^menu_profile$"))
    app.add_handler(CallbackQueryHandler(daily_bonus_callback, pattern="^claim_daily_bonus$"))
    app.add_handler(CallbackQueryHandler(artifacts_menu_callback, pattern="^menu_artifacts$"))
    app.add_handler(CallbackQueryHandler(buy_artifact_callback, pattern="^buy_art_"))
    app.add_handler(CallbackQueryHandler(equip_artifact_callback, pattern="^equip_art_"))
    app.add_handler(CallbackQueryHandler(unequip_artifact_callback, pattern="^unequip_art$"))
