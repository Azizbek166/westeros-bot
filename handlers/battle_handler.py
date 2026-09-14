import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from sqlalchemy import select, desc
from core.anti_cheat import can_attack_target
from keyboards.menus import back_to_main_keyboard
from config import BASE_MARCH_MINUTES, escape_md


async def battle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/battle yoki /war buyrug'i"""
    user_id = update.effective_user.id
    await show_battle_hub(update, user_id, is_message=True)


async def battle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_battle callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_battle_hub(query, user_id, is_message=False)


async def show_battle_hub(target, user_id: int, is_message: bool):
    """Harbiy amaliyotlar markazi: joriy yurishlar va hisobotlar"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            msg = "❌ Iltimos, avval /start ni bosing."
            if is_message:
                await target.message.reply_text(msg)
            else:
                await target.edit_message_text(msg)
            return

        # Faol yurishlar
        marches_res = await session.execute(
            select(models.BattleMarch).where(
                models.BattleMarch.attacker_user_id == user.id,
                models.BattleMarch.status == "marching",
            )
        )
        active_marches = marches_res.scalars().all()

        march_text = ""
        if active_marches:
            for m in active_marches:
                terr = await session.get(models.Territory, m.target_territory_id)
                rem_sec = max(0, int((m.arrival_time - datetime.utcnow()).total_seconds()))
                march_text += f"• 🎯 **{terr.name if terr else 'Qal\'a'}** sari yurish: {rem_sec // 60} daq {rem_sec % 60} soniya qoldi\n"
        else:
            march_text = "Hozirda faol harbiy yurishlar yo'q.\n"

        # So'nggi jang hisobotlari
        reports_res = await session.execute(
            select(models.BattleReport)
            .where(models.BattleReport.attacker_user_id == user.id)
            .order_by(desc(models.BattleReport.timestamp))
            .limit(3)
        )
        recent_reports = reports_res.scalars().all()

        reports_text = ""
        if recent_reports:
            for r in recent_reports:
                res_icon = "🏆 G'alaba" if r.result == "attacker_won" else "🛡️ Qaytarildi"
                reports_text += f"• {res_icon}: {r.details} (+{r.loot_gold}💰)\n"
        else:
            reports_text = "Janglar tarixi bo'sh.\n"

        buttons = [
            [InlineKeyboardButton("🗺️ Qal'a Tanlash (Xaritaga o'tish)", callback_data="menu_map")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ]

        text = (
            f"🛡️ **HARBIY AMALIYOTLAR MARKAZI**\n\n"
            f"⚔️ **FAOLLIK VA YURISHLAR:**\n{march_text}\n"
            f"📜 **SO'NGGI JANG HISOBOTLARI:**\n{reports_text}\n"
            f"Yangi qal'ani zabt etish uchun xaritadan nishonni tanlang:"
        )

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def march_prep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hujumga tayyorgarlik va armiya ulushini tanlash"""
    query = update.callback_query
    await query.answer()

    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            return

        is_allowed, err_msg = can_attack_target(user, terr)
        if not is_allowed:
            await query.answer(err_msg, show_alert=True)
            return

        total_army = (
            user.army.infantry
            + user.army.archers
            + user.army.cavalry
            + user.army.spearmen
            + user.army.special_troops
        )

        if total_army < 50:
            await query.answer("❌ Yurish uchun kamida 50 ta askar kerak! /army orqali yollang.", show_alert=True)
            return

        buttons = [
            [InlineKeyboardButton("⚔️ To'liq Armiya Bilan Yurish (100%)", callback_data=f"send_march:{terr.id}:100")],
            [InlineKeyboardButton("🛡️ Armiyaning Yarmi Bilan (50%)", callback_data=f"send_march:{terr.id}:50")],
            [InlineKeyboardButton("🔙 Bekor Qilish", callback_data=f"view_terr:{terr.id}")],
        ]

        text = (
            f"⚔️ **YURISH TAYYORGARLIGI: {terr.name.upper()}**\n\n"
            f"🏰 Nishon: **{terr.castle_name}** ({terr.region})\n"
            f"⏱️ Yurish vaqti: **{BASE_MARCH_MINUTES} daqiqa**\n\n"
            f"Sizning jami armiyangiz: **{total_army:,}** askar\n\n"
            f"⚠️ Hujum boshlangach, 3 kunlik Tinchlik Qalqoningiz bekor qilinadi!\n\n"
            f"Yuboriladigan qo'shin miqdorini tanlang:"
        )

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def send_march_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Armiyani manzil sari jo'natish"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    terr_id = int(parts[1])
    percent = int(parts[2])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            return

        ratio = percent / 100.0
        infantry = int(user.army.infantry * ratio)
        archers = int(user.army.archers * ratio)
        cavalry = int(user.army.cavalry * ratio)
        spearmen = int(user.army.spearmen * ratio)
        special = int(user.army.special_troops * ratio)

        total_sent = infantry + archers + cavalry + spearmen + special
        if total_sent <= 0:
            await query.answer("Askarlar soni yetarli emas.", show_alert=True)
            return

        # Qalqonni bekor qilish
        user.peace_shield_until = None

        march = await crud.create_battle_march(
            session=session,
            attacker_user_id=user.id,
            source_territory_id=terr.id,
            target_territory_id=terr.id,
            infantry=infantry,
            archers=archers,
            cavalry=cavalry,
            spearmen=spearmen,
            special_troops=special,
            character_id=user.characters[0].id if user.characters else None,
            duration_minutes=BASE_MARCH_MINUTES,
        )

        # Himoyachi xonadon Lordiga real-time ogohlantirish
        if terr.owner_house_id and terr.owner_house_id != user.house_id:
            target_house = await session.get(models.House, terr.owner_house_id)
            if target_house and target_house.lord_user_id and target_house.lord_user_id != user.telegram_id:
                try:
                    await context.bot.send_message(
                        chat_id=target_house.lord_user_id,
                        text=(
                            f"🚨 **QARG'A OGOHLANTIRISHI! QAL'AGA HUJUM!**\n\n"
                            f"🏰 **{user.house.emoji} {user.house.name}** armiyasi sizning **{terr.name} ({terr.castle_name})** qal'angizga yurish boshladi!\n"
                            f"⚔️ Hujumchilar: taxminan **{total_sent:,}** askar\n"
                            f"⏱️ Qamal boshlanishiga: **{BASE_MARCH_MINUTES} daqiqa**!\n\n"
                            f"Mudofaani kuchaytiring yoki /alliance orqali ittifoqchilardan yordam so'rang!"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

    text = (
        f"🚩 **QO'SHIN YURISHGA CHIQDI!**\n\n"
        f"🎯 Nishon: **{terr.name}** ({terr.castle_name})\n"
        f"⚔️ Safarbar etilgan askarlar: **{total_sent:,}** ta\n"
        f"⏱️ Yetib borish vaqti: **{BASE_MARCH_MINUTES} daqiqa**\n\n"
        f"Jang yakunlangach, bot sizga avtomatik jang hisobotini yuboradi!"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_main_keyboard())


def register_battle_handlers(app):
    app.add_handler(CommandHandler("battle", battle_command))
    app.add_handler(CommandHandler("war", battle_command))
    app.add_handler(CallbackQueryHandler(battle_callback, pattern="^menu_battle$"))
    app.add_handler(CallbackQueryHandler(march_prep_callback, pattern="^march_prep:"))
    app.add_handler(CallbackQueryHandler(send_march_callback, pattern="^send_march:"))
