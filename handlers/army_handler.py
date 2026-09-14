from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud
from core.economy_engine import calculate_army_upkeep
from core.anti_cheat import validate_recruitment
from keyboards.menus import recruit_keyboard, back_to_main_keyboard
from data.units_data import UNITS_DATA


async def army_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/army buyrug'i"""
    user_id = update.effective_user.id
    await show_army(update, user_id, is_message=True)


async def army_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_army callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_army(query, user_id, is_message=False)


async def show_army(target, user_id: int, is_message: bool):
    """Armiya holati va yollash menyusini chiqarish"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            msg = "❌ Siz hali ro'yxatdan o'tmagansiz. /start ni bosing."
            if is_message:
                await target.message.reply_text(msg)
            else:
                await target.edit_message_text(msg)
            return

        army = user.army
        upkeep = calculate_army_upkeep(army)
        special_name = user.house.special_troop_name if user.house else "Special Guard"

        text = (
            f"⚔️ **ARMIYA QARORGOHI**\n\n"
            f"🪙 Oltin: **{user.gold:,}** | 🌾 Oziq-ovqat: **{user.food:,}** | ⛓️ Temir: **{user.iron:,}**\n\n"
            f"📊 **MAVJUD QO'SHIN:**\n"
            f"🛡️ Piyodalar (Infantry): **{army.infantry:,}**\n"
            f"🏹 Kamonchilar (Archers): **{army.archers:,}**\n"
            f"🐎 Otliqlar (Cavalry): **{army.cavalry:,}**\n"
            f"🗡️ Nayzachilar (Spearmen): **{army.spearmen:,}**\n"
            f"🔥 {special_name}: **{army.special_troops:,}**\n\n"
            f"🌾 Armiyaning soatlik oziq-ovqat iste'moli: **{int(upkeep)}** / soat\n\n"
            f"📐 **JANG FOYDASI (RPS):**\n"
            f"• 🐎 Otliq > 🏹 Kamonchi (+40%)\n"
            f"• 🗡️ Nayzachi > 🐎 Otliq (+40%)\n"
            f"• 🏹 Kamonchi > 🛡️ Piyoda (+30%)\n"
            f"• 🛡️ Piyoda > 🗡️ Nayzachi (+30%)\n\n"
            f"Yangi askarlar yollash uchun tugmani tanlang:"
        )

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=recruit_keyboard())
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=recruit_keyboard())


async def recruit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'shin yollash tugmasi bosilganda"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    unit_type = parts[1]
    amount = int(parts[2])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        is_valid, gold_cost, iron_cost, err_msg = validate_recruitment(user, unit_type, amount)
        if not is_valid:
            await query.answer(err_msg, show_alert=True)
            return

        success = await crud.recruit_troops(
            session=session,
            user_id=user.id,
            unit_type=unit_type,
            amount=amount,
            gold_cost=gold_cost,
            iron_cost=iron_cost,
        )

        if success:
            unit_name = UNITS_DATA[unit_type]["name"]
            await query.answer(f"✅ +{amount} ta {unit_name} safga qo'shildi!", show_alert=True)
            await show_army(query, user_id, is_message=False)
        else:
            await query.answer("❌ Xatolik yuz berdi.", show_alert=True)


def register_army_handlers(app):
    app.add_handler(CommandHandler("army", army_command))
    app.add_handler(CallbackQueryHandler(army_callback, pattern="^menu_army$"))
    app.add_handler(CallbackQueryHandler(recruit_callback, pattern="^rec:"))
