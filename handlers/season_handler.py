import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database import crud, models
from config import escape_md

logger = logging.getLogger(__name__)


async def show_season_menu(target, user_id: int, is_message: bool = False, is_group: bool = False):
    """Mavsum holati, Temir Taxt egasi va g'olib nomzod haqida ma'lumot"""
    async with AsyncSessionLocal() as session:
        season = await crud.get_active_season(session)
        now = datetime.utcnow()

        rem_seconds = max(0, int((season.end_date - now).total_seconds())) if season else 0
        rem_days = rem_seconds // 86400
        rem_hours = (rem_seconds % 86400) // 3600
        rem_mins = (rem_seconds % 3600) // 60

        champ = await crud.get_season_champion_candidate(session)
        champion_user = champ.get("user")
        winner_house = champ.get("house")
        held_kl = champ.get("kings_landing_held", False)
        score = champ.get("score", 0)

        king_name = "Noma'lum Hukmdor"
        if champion_user:
            hero_name = champion_user.characters[0].name if getattr(champion_user, "characters", None) and len(champion_user.characters) > 0 else champion_user.full_name
            uname = f" (@{champion_user.username})" if getattr(champion_user, "username", None) else ""
            t_title = f" «{champion_user.title}»" if getattr(champion_user, "title", None) else ""
            king_name = f"{hero_name}{uname}{t_title}"

        winner_house_name = f"{winner_house.emoji} {winner_house.name}" if winner_house else "Mustaqil Lord"

        # Top 1 Nufuzli o'yinchi
        top_u_res = await session.execute(
            select(models.User).order_by(models.User.prestige.desc()).limit(1)
        )
        top_user = top_u_res.scalar_one_or_none()
        top_user_name = top_user.full_name if top_user else "Noma'lum"
        top_user_pres = top_user.prestige if top_user else 0

        status_text = "🏰 King's Landing qal'asini qo'lda ushlab turibdi!" if held_kl else f"📊 Umumiy Mavsum Balli: **{score:,}** ball"

        text = (
            f"🌟 **{season.season_number}-MAVSUM: TEMIR TAXT UCHUN JANG**\n\n"
            f"⏱️ **Mavsum tugashiga:** **{rem_days} kun {rem_hours} soat {rem_mins} daqiqa** qoldi\n\n"
            f"👑 **Temir Taxt Sohibi (G'olib Nomzod):**\n"
            f"• Hukmdor: **{escape_md(king_name)}**\n"
            f"• Xonadon: **{escape_md(winner_house_name)}**\n"
            f"• Holat: {status_text}\n\n"
            f"⚔️ **Mavsum Nufuz Yetakchisi:** **{escape_md(top_user_name)}** ({top_user_pres:,} 🏆)\n\n"
            "📜 **Mavsum va G'olibni Aniqlash Qoidalari:**\n"
            "• Mavsum 30 kun davom etadi.\n"
            "• King's Landing qal'asini zabt etgan Lord mavsum yakunida birinchi darajali **Temir Taxt Qiroli (Mavsum G'olibi)** deb e'lon qilinadi.\n"
            "• Agar King's Landing neytral bo'lsa, umumiy ko'rsatkichlar (`Nufuz*2 + Oltin//50 + Armiya//5 + Qal'alar*500`) bo'yicha eng kuchli Lord g'olib bo'ladi!\n"
            "• G'olib Shon-sharaf Zaliga kiritiladi, unga maxsus «👑 Temir Taxt Sohibi» unvoni va qirollik oltinlari beriladi!"
        )

        if is_group:
            clean_kb = ReplyKeyboardRemove()
            try:
                await target.reply_text(text, parse_mode="Markdown", reply_markup=clean_kb)
            except Exception:
                await target.reply_text(text, parse_mode=None, reply_markup=clean_kb)
            return

        buttons = [
            [InlineKeyboardButton("🏆 Mavsum G'olibi Batafsil", callback_data="rank_cat:champion:all")],
            [InlineKeyboardButton("🏛️ Shon-sharaf Zali (Hall of Fame)", callback_data="menu_halloffame")],
            [InlineKeyboardButton("🔄 Yangilash", callback_data="menu_season")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ]

        reply_markup = InlineKeyboardMarkup(buttons)
        if hasattr(target, "edit_message_text") and not is_message:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await target.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def show_hall_of_fame_menu(target, user_id: int):
    """Shon-sharaf Zali (O'tgan mavsumlar chempionlari)"""
    async with AsyncSessionLocal() as session:
        fame_entries = await crud.get_hall_of_fame(session, limit=10)

        fame_text = ""
        if fame_entries:
            for entry in fame_entries:
                date_str = entry.concluded_at.strftime("%d.%m.%Y") if entry.concluded_at else ""
                winner_person = entry.king_name or entry.top_warrior_name or "Noma'lum"
                fame_text += (
                    f"🏆 **{entry.season_number}-MAVSUM CHEMPIONI:**\n"
                    f"👑 **G'olib Qirol:** **{winner_person}** ({entry.winner_house_name} xonadoni)\n"
                    f"⚔️ **Bosh Botir:** {entry.top_warrior_name} ({entry.top_warrior_prestige:,}🎖️)\n"
                    f"📅 _Tarixiy sana: {date_str}_\n"
                    f"{'—'*25}\n"
                )
        else:
            fame_text = (
                "🏛️ Hozirda 1-Mavsum qizg'in davom etmoqda!\n"
                "Mavsum yakuniga yetgach, birinchi chempion xonadon va Qirol nomi ushbu zaldan joy oladi."
            )

        text = (
            "🏛️📜 **VESTEROS SHON-SHARAF ZALI (HALL OF FAME)**\n\n"
            "Buyuk Vesteros solnomasi: Temir Taxtni zabt etgan va o'z nomini abadiylikka muhrlagan hukmdorlar:\n\n"
            f"{fame_text}"
        )

        buttons = [
            [InlineKeyboardButton("🌟 Joriy Mavsum Holati", callback_data="menu_season")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ]

        reply_markup = InlineKeyboardMarkup(buttons)
        if hasattr(target, "edit_message_text"):
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await target.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def season_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    is_group = bool(chat and chat.type in ["group", "supergroup"])
    await show_season_menu(msg, update.effective_user.id, is_message=True, is_group=is_group)


async def winner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mavsum g'olibi va Temir Taxt nomzodini ko'rish"""
    msg = update.effective_message
    chat = update.effective_chat
    is_group = bool(chat and chat.type in ["group", "supergroup"])

    async with AsyncSessionLocal() as session:
        from handlers.ranking_handler import format_champion_text
        text = await format_champion_text(session)

    if is_group:
        clean_kb = ReplyKeyboardRemove()
        try:
            await msg.reply_text(text, parse_mode="Markdown", reply_markup=clean_kb)
        except Exception:
            await msg.reply_text(text, parse_mode=None, reply_markup=clean_kb)
    else:
        buttons = [
            [InlineKeyboardButton("🏆 Barcha Reytinglar", callback_data="menu_rank")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ]
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def halloffame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_hall_of_fame_menu(update.message, update.effective_user.id)


async def season_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_season_menu(query, update.effective_user.id, is_message=False, is_group=False)


async def halloffame_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_hall_of_fame_menu(query, update.effective_user.id)


def register_season_handlers(app):
    app.add_handler(CommandHandler(["season", "mavsum"], season_command))
    app.add_handler(CommandHandler(["winner", "chempion", "golib", "taxt", "king"], winner_command))
    app.add_handler(CommandHandler(["halloffame", "shonsharaf"], halloffame_command))
    app.add_handler(CallbackQueryHandler(season_callback, pattern="^menu_season$"))
    app.add_handler(CallbackQueryHandler(halloffame_callback, pattern="^menu_halloffame$"))
