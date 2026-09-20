import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from database.db import AsyncSessionLocal
from database import crud
from data.champions_data import LEGENDARY_CHAMPIONS

logger = logging.getLogger(__name__)


async def show_champions_menu(target, user_id: int):
    """Afsonaviy Sarkardalar (Legendary Champions) menyusi"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            if hasattr(target, "answer"):
                await target.answer("Foydalanuvchi topilmadi.", show_alert=True)
            return

        curr_champ = await crud.get_user_champion(session, user.id)
        u_gold = user.gold or 0
        u_prestige = user.prestige or 0

        active_str = "❌ *Hozirda bosh qo'mondon tayinlanmagan*"
        if curr_champ:
            active_str = f"✅ **{curr_champ['emoji']} {curr_champ['name']}**\n📜 _{curr_champ['description']}_"

        overview_lines = [
            "📋 **Sarkardalar harbiy qudrati va ustunliklari:**",
            "• 🦁 **Jaime:** Otliqlar zarbasi +25% | Turnir: 240⚡",
            "• 🐺 **Robb Stark:** Otliq/Piyoda +20%, Mudofaa +15% | Turnir: 235⚡",
            "• 🐍 **Oberyn:** Nayzachilar +30%, Otliqlarni falajlash | Turnir: 235⚡",
            "• 🦌 **Stannis:** Qal'a mudofaasi +25%, Piyoda +20%, Talofat -15% | Turnir: 230⚡",
            "• 🗡️ **Arya:** Kamonchi/Maxsus +20% kritik zarba | Turnir: 230⚡",
            "• 🐺 **Jon Snow:** Piyoda mudofaasi +20%, Oq Yuruvchilarga 2x | Turnir: 225⚡",
            "• 🛡️ **Brienne:** Umumiy mudofaa +15%, Talofat -15% | Turnir: 220⚡",
        ]
        overview_text = "\n".join(overview_lines)

        text = (
            "⚔️🎖️ **VESTEROSNING AFSONAVIY SARKARDALARI**\n\n"
            "Armiyangizga Yetti Qirollikning eng buyuk jangchilaridan birini Bosh Qo'mondon etib tayinlang! "
            "Har bir sarkarda qo'shiningizga xos jangovar taktika va halokatli bonuslar beradi.\n\n"
            f"👤 **Faol Sarkarda:**\n{active_str}\n\n"
            f"{overview_text}\n\n"
            f"💰 Sizning boyligingiz: **{u_gold:,}🪙 Oltin** | **{u_prestige:,}🎖️ Nufuz**\n\n"
            "Batafsil ma'lumot olish yoki tayinlash uchun tanlang:"
        )

        buttons = []
        for cid, cinfo in LEGENDARY_CHAMPIONS.items():
            is_active = curr_champ and (curr_champ.get("id") == cid)
            status_tag = " [FAOL ✅]" if is_active else ""
            t_pwr = cinfo.get("tourney_power", 200)
            buttons.append([
                InlineKeyboardButton(f"{cinfo['emoji']} {cinfo['name']} ({t_pwr}⚡){status_tag}", callback_data=f"champ_info:{cid}")
            ])
            if not is_active:
                buttons.append([
                    InlineKeyboardButton(f"   ↳ 🎖️ Tayinlash (10k🪙, 200🎖️)", callback_data=f"champ_rec:{cid}")
                ])
            else:
                buttons.append([
                    InlineKeyboardButton(f"   ↳ ❌ Vazifasidan Ozod Qilish", callback_data="champ_dismiss")
                ])

        buttons.append([InlineKeyboardButton("🔙 Armiya Sahifasi", callback_data="menu_army")])
        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        reply_markup = InlineKeyboardMarkup(buttons)
        if hasattr(target, "edit_message_text"):
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await target.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def champions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_champions_menu(update.message, update.effective_user.id)


async def champions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_champions_menu(query, update.effective_user.id)


async def champion_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cid = query.data.split(":")[1]
    if cid not in LEGENDARY_CHAMPIONS:
        await query.answer("Qahramon topilmadi.", show_alert=True)
        return

    c = LEGENDARY_CHAMPIONS[cid]
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        curr_champ = await crud.get_user_champion(session, user.id) if user else None

    is_active = curr_champ and (curr_champ.get("id") == cid)

    text = (
        f"{c['emoji']} **{c['name']}**\n"
        f"🎖️ _'{c['title']}'_\n\n"
        f"📖 **Tarixi va Fazilati:**\n{c['description']}\n\n"
        f"⚔️ **JANG KUCHI VA HARBIY USTUNLIKLARI:**\n"
        f"• ⚡ **Ritsarlar Turniri Quvvati:** **{c.get('tourney_power', 210)}⚡**\n"
        f"• ⚔️ **Hujum Taktikasi & Bonusi:** {c.get('atk_bonus_desc', 'Standart')}\n"
        f"• 🛡️ **Mudofaa & Himoya Bonusi:** {c.get('def_bonus_desc', 'Standart')}\n"
        f"• 🩸 **Talofat Qisqartirish:** {c.get('loss_reduction_desc', '0%')}\n"
        f"• 🌟 **Noyob Harbiy Xususiyati:**\n  _{c.get('special_trait', '-')}_\n\n"
        f"💵 **Xizmat haqi:** **{c['cost_gold']:,}🪙 Oltin** va **{c['cost_prestige']:,}🎖️ Nufuz**\n"
        f"👑 **Armiyaga ta'siri:** Ushbu sarkarda tayinlangach, uning ustunliklari qamal, maydon jangi va turnir duellarida avtomatik ishga tushadi!"
    )

    buttons = []
    if is_active:
        buttons.append([InlineKeyboardButton("❌ Vazifasidan Ozod Qilish", callback_data="champ_dismiss")])
    else:
        buttons.append([InlineKeyboardButton(f"🎖️ {c['name']}ni Tayinlash", callback_data=f"champ_rec:{cid}")])

    buttons.append([InlineKeyboardButton("🔙 Barcha Sarkardalar", callback_data="menu_champions")])
    buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def champion_recruit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cid = query.data.split(":")[1]
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            await query.answer("Foydalanuvchi topilmadi.", show_alert=True)
            return
        ok, msg = await crud.recruit_champion(session, user.id, cid)

    await query.answer(msg[:150], show_alert=True)
    await show_champions_menu(query, user_id)


async def champion_dismiss_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            await query.answer("Foydalanuvchi topilmadi.", show_alert=True)
            return
        ok, msg = await crud.dismiss_champion(session, user.id)

    await query.answer(msg[:150], show_alert=True)
    await show_champions_menu(query, user_id)


def register_champion_handlers(app):
    app.add_handler(CommandHandler(["champions", "heroes"], champions_command))
    app.add_handler(CallbackQueryHandler(champions_callback, pattern="^menu_champions$"))
    app.add_handler(CallbackQueryHandler(champion_info_callback, pattern="^champ_info:"))
    app.add_handler(CallbackQueryHandler(champion_recruit_callback, pattern="^champ_rec:"))
    app.add_handler(CallbackQueryHandler(champion_dismiss_callback, pattern="^champ_dismiss$"))
