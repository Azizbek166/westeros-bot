import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database import crud, models

logger = logging.getLogger(__name__)


async def show_season_menu(target, user_id: int):
    """Mavsum holati va qolgan vaqt haqida ma'lumot"""
    async with AsyncSessionLocal() as session:
        season = await crud.get_active_season(session)
        now = datetime.utcnow()

        rem_seconds = max(0, int((season.end_date - now).total_seconds())) if season else 0
        rem_days = rem_seconds // 86400
        rem_hours = (rem_seconds % 86400) // 3600
        rem_mins = (rem_seconds % 3600) // 60

        # King's Landing qal'asining egasi
        kl_res = await session.execute(
            select(models.Territory).where(models.Territory.code == "kings_landing")
        )
        kl_terr = kl_res.scalar_one_or_none()
        winner_house = None
        if kl_terr and kl_terr.owner_house_id:
            winner_house = await session.get(models.House, kl_terr.owner_house_id)

        if not winner_house:
            top_h_res = await session.execute(
                select(models.House).order_by(models.House.prestige.desc()).limit(1)
            )
            winner_house = top_h_res.scalar_one_or_none()

        winner_house_name = winner_house.name if winner_house else "Vesteros Ittifoqi"
        king_name = "Noma'lum Lord"
        if winner_house and winner_house.lord_user_id:
            king_u = await crud.get_user_by_telegram_id(session, winner_house.lord_user_id)
            if king_u:
                king_name = king_u.full_name

        # Eng nufuzli o'yinchi
        top_u_res = await session.execute(
            select(models.User).order_by(models.User.prestige.desc()).limit(1)
        )
        top_user = top_u_res.scalar_one_or_none()
        top_user_name = top_user.full_name if top_user else "Noma'lum"
        top_user_pres = top_user.prestige if top_user else 0

        text = (
            f"🌟 **{season.season_number}-MAVSUM: TEMIR TAXT UCHUN JANG**\n\n"
            f"⏱️ **Mavsum tugashiga:** **{rem_days} kun {rem_hours} soat {rem_mins} daqiqa** qoldi\n\n"
            f"🏰 **Amaldagi Temir Taxt Sohibi:** **{winner_house_name}** xonadoni\n"
            f"👑 **Vesteros Qiroli:** **{king_name}**\n"
            f"⚔️ **Mavsum Yetakchisi (Top 1):** **{top_user_name}** ({top_user_pres:,}🎖️ Nufuz)\n\n"
            "📜 **Mavsum Qoidalari:**\n"
            "• Mavsum 30 kun davom etadi.\n"
            "• Yakunda King's Landingni ushlab turgan xonadon va eng kuchli jangchilar **Shon-sharaf Zali (Hall of Fame)**ga abadiy muhrlanadi!\n"
            "• Yangi mavsumda qal'alar qayta taqsimlanadi, ammo sizning **Darajangiz, Oltinlaringiz, Unvonlaringiz, Ajdarlaringiz va Artefaktlaringiz** to'liq saqlanib qoladi!"
        )

        buttons = [
            [InlineKeyboardButton("🏛️ Shon-sharaf Zali (Hall of Fame)", callback_data="menu_halloffame")],
            [InlineKeyboardButton("🔄 Yangilash", callback_data="menu_season")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ]

        reply_markup = InlineKeyboardMarkup(buttons)
        if hasattr(target, "edit_message_text"):
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
                    f"👑 **G'olib:** **{winner_person}** ({entry.winner_house_name} xonadoni)\n"
                    f"🎖️ **Nufuz:** {entry.top_warrior_prestige:,}🎖️\n"
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
            "Buyuk Vesteros solnomasi: Temir Taxtni zabt etgan va o'z nomini abadiylikka muhrlagan xonadonlar:\n\n"
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
    await show_season_menu(update.message, update.effective_user.id)


async def halloffame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_hall_of_fame_menu(update.message, update.effective_user.id)


async def season_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_season_menu(query, update.effective_user.id)


async def halloffame_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_hall_of_fame_menu(query, update.effective_user.id)


def register_season_handlers(app):
    app.add_handler(CommandHandler(["season", "mavsum"], season_command))
    app.add_handler(CommandHandler(["halloffame", "shonsharaf"], halloffame_command))
    app.add_handler(CallbackQueryHandler(season_callback, pattern="^menu_season$"))
    app.add_handler(CallbackQueryHandler(halloffame_callback, pattern="^menu_halloffame$"))
