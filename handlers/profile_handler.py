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

        upkeep = calculate_army_upkeep(user.army)
        income = await calculate_hourly_income(session, user)
        hero = user.characters[0] if user.characters else None

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
            f"⭐ Daraja: **{user.level}** (XP: {user.xp}/1000)\n"
            f"🏆 Prestige: **{user.prestige}**\n\n"
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

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=back_to_main_keyboard())
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_main_keyboard())


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


def register_profile_handlers(app):
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler(["daily", "bonus"], daily_bonus_callback))
    app.add_handler(CallbackQueryHandler(profile_callback, pattern="^menu_profile$"))
    app.add_handler(CallbackQueryHandler(daily_bonus_callback, pattern="^claim_daily_bonus$"))
