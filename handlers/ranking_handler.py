from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud
from keyboards.menus import back_to_main_keyboard
from config import escape_md


async def ranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/rank buyrug'i"""
    user_id = update.effective_user.id
    await show_ranking_hub(update, user_id, is_message=True)


async def ranking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_rank callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_ranking_hub(query, user_id, is_message=False)


async def show_ranking_hub(target, user_id: int, is_message: bool):
    """1-Mavsum reyting jadvali: Nufuz, Boylik va Armiya"""
    async with AsyncSessionLocal() as session:
        top_houses = await crud.get_top_houses(session, limit=5)
        top_players = await crud.get_top_players(session, limit=5)
        top_wealthy = await crud.get_top_wealthy(session, limit=5)

        houses_text = ""
        for i, h in enumerate(top_houses, 1):
            houses_text += f"{i}. {h.emoji} **{h.name}** — {h.prestige:,} 🏆\n"

        players_text = ""
        for i, p in enumerate(top_players, 1):
            h_name = p.house.name if p.house else "Mustaqil"
            hero_name = p.characters[0].name if p.characters else p.full_name
            players_text += f"{i}. **{escape_md(hero_name)}** ({escape_md(h_name)}) — {p.level}-daraja | {p.prestige:,} 🏆\n"

        wealth_text = ""
        for i, w in enumerate(top_wealthy, 1):
            h_name = w.house.name if w.house else "Mustaqil"
            wealth_text += f"{i}. **{escape_md(w.full_name)}** ({escape_md(h_name)}) — {w.gold:,} 🪙\n"

        ht = houses_text or "Ma'lumot yo'q"
        pt = players_text or "Hozircha lordlar yo'q"
        wt = wealth_text or "Hozircha ma'lumot yo'q"

        text = (
            f"🏆 **1-MAVSUM: BESH QIROL URUSHI REYTINGI**\n\n"
            f"🏰 **ENG NAFIS VA QUDRATLI XONADONLAR:**\n{ht}\n"
            f"👑 **ENG MASHHUR LORDLAR (PRESTIGE):**\n{pt}\n"
            f"💰 **ENG BOY XONADON EGALARI:**\n{wt}\n\n"
            f"Mavsum yakunida Temir Taxt sohibi va peshqadamlar maxsus sovrinlar bilan taqdirlanadi!"
        )

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=back_to_main_keyboard())
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_main_keyboard())


def register_ranking_handlers(app):
    app.add_handler(CommandHandler("rank", ranking_command))
    app.add_handler(CommandHandler("ranking", ranking_command))
    app.add_handler(CallbackQueryHandler(ranking_callback, pattern="^menu_rank$"))
