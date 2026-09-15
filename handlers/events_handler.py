import json
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from keyboards.menus import back_to_main_keyboard
from config import escape_md
from sqlalchemy import select


async def get_or_create_event_state(session, event_name: str, default_data: dict) -> models.EventState:
    """EventState ni olish yoki yangi yaratish"""
    res = await session.execute(select(models.EventState).where(models.EventState.event_name == event_name))
    ev = res.scalar_one_or_none()
    if not ev:
        ev = models.EventState(
            event_name=event_name,
            data_json=json.dumps(default_data),
            is_active=True,
            started_at=datetime.utcnow(),
        )
        session.add(ev)
        await session.commit()
    return ev


async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/events buyrug'i"""
    user_id = update.effective_user.id
    await show_events_hub(update, user_id, is_message=True)


async def events_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_events callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await show_events_hub(query, user_id, is_message=False)


async def show_events_hub(target, user_id: int, is_message: bool):
    """Global hodisalar: Tun Qiroli, Vabo, Qaroqchilar va Temir Taxt"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if user:
            await crud.check_and_reset_daily_limits(session, user)

        kl_terr = await crud.get_territory_by_id(session, 8)  # King's Landing ID = 8
        kl_owner = f"{kl_terr.owner_house.emoji} {kl_terr.owner_house.name}" if (kl_terr and kl_terr.owner_house) else "Targaryen"

        # Tun Qiroli holati
        ww_event = await get_or_create_event_state(session, "white_walkers", {"hp": 250000, "max_hp": 250000, "status": "active"})
        ww_data = json.loads(ww_event.data_json)
        hp = ww_data.get("hp", 250000)
        max_hp = ww_data.get("max_hp", 250000)
        pct = max(0, int((hp / max_hp) * 100))
        bar_len = 10
        filled = int(bar_len * (pct / 100))
        progress_bar = "█" * filled + "░" * (bar_len - filled)

        ww_count = user.daily_ww_attack_count if user else 0

        text = (
            f"👑 **WESTEROS GLOBAL VOQEALARI VA TEMIR TAXT**\n\n"
            f"👑 **TEMIR TAXT HUKMRONLIGI:**\n"
            f"King's Landing hozirgi sohibi: **{escape_md(kl_owner)}**\n"
            f"Shartlar: Qal'ani egallash + 800 Prestige.\n\n"
            f"❄️ **THE LONG NIGHT — TUN QIROLI REYDI (GLOBAL BOSS):**\n"
            f"Zombi Armiyasi: **{hp:,} / {max_hp:,}** ({pct}%)\n"
            f"Holat: `[{progress_bar}]`\n"
            f"Bugungi janglaringiz: **{ww_count}/3** ta\n"
            f"Devor ortidan o'lim sharpasi yaqinlashmoqda. Barcha lordlar zarba berishi shart!\n\n"
            f"Harbiy harakatni tanlang:"
        )

        buttons = [
            [InlineKeyboardButton(f"⚔️ Tun Qiroliga Zarba Berish ({ww_count}/3)", callback_data="raid_night_king")],
            [InlineKeyboardButton("🏆 Tun Qiroli Ziyon Reytingi (Top 10)", callback_data="night_king_leaderboard")],
            [InlineKeyboardButton("☣️ Mintaqaviy Vabo Epidemiyasi", callback_data="event_plague")],
            [InlineKeyboardButton("🥷 Qaroqchilar Pistirmasiga Hujum", callback_data="event_bandits")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ]

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def raid_night_king_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tun Qiroliga zarba berish (Kunlik limit: 3 ta)"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        await crud.check_and_reset_daily_limits(session, user)
        if user.daily_ww_attack_count >= 3:
            await query.answer("❌ Bugungi 3 ta Oq yuruvchilarga qarshi hujum limitingiz tugagan! Ertaga yana reyd qilishingiz mumkin.", show_alert=True)
            return

        army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
        army = army_res.scalar_one_or_none()
        total_troops = (army.infantry + army.archers + army.cavalry + army.spearmen) if army else 0

        if total_troops < 25:
            await query.answer("❌ Tun Qiroliga reyd qilish uchun kamida 25 ta askar kerak!", show_alert=True)
            return

        # Zarba berish va talafot (5 askar yo'qotiladi, Tun Qiroli HP si kamayadi)
        if army.infantry >= 5:
            army.infantry -= 5
        else:
            army.archers = max(0, army.archers - 5)

        base_dmg = random.randint(400, 800)

        # Artefakt bonusi
        equipped = await crud.get_equipped_artifact(session, user.id)
        if equipped:
            from data.artifacts_data import ARTIFACTS_DATA
            art_data = ARTIFACTS_DATA.get(equipped.code, {})
            bonus = art_data.get("attack_bonus", 0.0)
            base_dmg = int(base_dmg * (1.0 + bonus))

        # Ajdar bonusi
        dragons = await crud.get_user_dragons(session, user.id)
        adult_dragons = [d for d in dragons if d.stage == "adult"]
        dragon_dmg = 0
        if adult_dragons:
            best_dragon = max(adult_dragons, key=lambda d: d.power)
            dragon_dmg = int(best_dragon.power * 1.5)

        total_dmg = base_dmg + dragon_dmg

        ww_event = await get_or_create_event_state(session, "white_walkers", {"hp": 250000, "max_hp": 250000})
        ww_data = json.loads(ww_event.data_json)
        ww_data["hp"] = max(0, ww_data.get("hp", 250000) - total_dmg)
        ww_event.data_json = json.dumps(ww_data)

        user.daily_ww_attack_count += 1

        # Ziyonni reytingga yozish
        await crud.record_night_king_damage(session, user.id, total_dmg)

        # Mukofot
        user.gold += 350
        user.iron += 180
        user.prestige += 50
        user.xp += 180

        from core.leveling import check_user_level_up
        lvl_up, new_lvl, lvl_msg = check_user_level_up(user)

        await session.commit()

        extra_note = f"\n{lvl_msg}" if lvl_up else ""

    dragon_msg = f" (🔥 Ajdar olovi: +{dragon_dmg})" if dragon_dmg > 0 else ""
    await query.answer(f"⚔️ Zarba berildi: -{total_dmg} wight!{dragon_msg} ({user.daily_ww_attack_count}/3)", show_alert=True)
    await show_events_hub(query, user_id, is_message=False)


async def night_king_leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tun Qiroli ziyon reytingi (Top 10)"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        top_list = await crud.get_night_king_leaderboard(session, limit=10)

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    rows = []
    if not top_list:
        rows.append("Hozircha hech kim Tun Qiroliga zarba bermagan. Birinchi bo'lib qahramonlik ko'rsating!")
    else:
        for idx, (char_name, house_str, dmg, attacks) in enumerate(top_list):
            m = medals[idx] if idx < len(medals) else f"{idx+1}."
            rows.append(f"{m} **{char_name}** ({house_str}) — **{dmg:,}** ziyon ({attacks} ta zarba)")

    list_str = "\n".join(rows)
    user_cnt = user.daily_ww_attack_count if user else 0

    text = (
        f"❄️ **TUN QIROLI ZIYON REYTINGI (TOP 10)**\n\n"
        f"Oq yuruvchilar armiyasiga eng katta talafot yetkazgan Vesteros xaloskorlari:\n\n"
        f"{list_str}\n\n"
        f"🎁 **REYTING MUKOFOTLARI (FASL YAKUNIDA):**\n"
        f"• 🥇 1-o'rin: +3,000🪙 Oltin, +500🏆 Prestige, 'Shimol Najotkori' unvoni\n"
        f"• 🥈 2-o'rin: +1,800🪙 Oltin, +300🏆 Prestige\n"
        f"• 🥉 3-o'rin: +1,000🪙 Oltin, +200🏆 Prestige\n"
        f"• 🎖️ 4-10 o'rinlar: +500🪙 Oltin, +100🏆 Prestige\n\n"
        f"Sizning bugungi hujumlaringiz: **{user_cnt}/3**"
    )

    buttons = [
        [InlineKeyboardButton("⚔️ Tun Qiroliga Zarba Berish", callback_data="raid_night_king")],
        [InlineKeyboardButton("🔙 Voqealarga Qaytish", callback_data="menu_throne")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def event_plague_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vabo hodisasi menyusi"""
    query = update.callback_query
    await query.answer()

    buttons = [
        [InlineKeyboardButton("🧪 Dorilar Tayyorlash (-300🪙, -100⛓️)", callback_data="plague_cure")],
        [InlineKeyboardButton("🚪 Shaharni Karantin Qilish (0 resurs)", callback_data="plague_quarantine")],
        [InlineKeyboardButton("🔙 Voqealarga Qaytish", callback_data="menu_throne")],
    ]

    text = (
        f"☣️ **MINTAQADA OG'IR VABO EPIDEMIYASI TARQALDI!**\n\n"
        f"Xalqingiz va askarlaringiz orasida sirli kasallik tarqalmoqda. "
        f"Maesterlar shoshilinch qaror qabul qilishingizni kutmoqda:\n\n"
        f"1. **Dorilar Tayyorlash:** 300 oltin va 100 temir sarflab epidemiyani yengasiz va xalq hurmatiga (+40 Prestige) sazovor bo'lasiz.\n"
        f"2. **Karantin:** Hech narsa sarflamaysiz, ammo 10 ta askar kasallikdan nobud bo'ladi."
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def plague_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vabo harakati natijasi"""
    query = update.callback_query
    await query.answer()

    action = query.data
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        if action == "plague_cure":
            if user.gold < 300 or user.iron < 100:
                await query.answer("❌ Dorilar tayyorlash uchun 300 oltin va 100 temir kerak!", show_alert=True)
                return
            user.gold -= 300
            user.iron -= 100
            user.prestige += 40
            user.xp += 100
            await session.commit()
            msg = "✅ Maesterlar dorilar tayyorladi! Vabo bartaraf etildi. (+40 Prestige)"
        else:
            army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
            army = army_res.scalar_one_or_none()
            if army and army.infantry >= 10:
                army.infantry -= 10
            elif army:
                army.archers = max(0, army.archers - 10)
            await session.commit()
            msg = "🚪 Qattiq karantin joriy qilindi. 10 ta askar nobud bo'ldi, biroq qolganlar saqlab qolindi."

    await query.answer(msg, show_alert=True)
    await show_events_hub(query, user_id, is_message=False)


async def event_bandits_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qaroqchilar hodisasi menyusi"""
    query = update.callback_query
    await query.answer()

    buttons = [
        [InlineKeyboardButton("⚔️ Qaroqchilarga Hujum Qilish (-5 askar)", callback_data="bandits_fight")],
        [InlineKeyboardButton("💰 O'lpon To'lab Qutulish (-200🪙 oltin)", callback_data="bandits_pay")],
        [InlineKeyboardButton("🔙 Voqealarga Qaytish", callback_data="menu_throne")],
    ]

    text = (
        f"🥷 **QAROQCHILAR VA ISYONCHILAR PISTIRMASI!**\n\n"
        f"Savdo yo'llaringizga tog' qaroqchilari hujum qildi va karvonlaringizni to'smoqda!\n\n"
        f"1. **Hujum qilish:** Qaroqchilar bazasini tor-mor qilish (taxminan 5 ta askar yo'qotib, ularning xazinasidan +800🪙 oltin va +300🌾 oziq-ovqat olasiz).\n"
        f"2. **O'lpon to'lash:** 200 tanga berib xavfdan qutulish."
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def bandits_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qaroqchilar harakati natijasi"""
    query = update.callback_query
    await query.answer()

    action = query.data
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        if action == "bandits_fight":
            army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
            army = army_res.scalar_one_or_none()
            if not army or (army.infantry + army.archers + army.cavalry + army.spearmen) < 10:
                await query.answer("❌ Qaroqchilarga qarshi chiqish uchun kamida 10 ta askar kerak!", show_alert=True)
                return
            if army.infantry >= 5:
                army.infantry -= 5
            else:
                army.archers = max(0, army.archers - 5)

            user.gold += 800
            user.food += 300
            user.prestige += 35
            user.xp += 120
            await session.commit()
            msg = "🏆 G'alaba! Qaroqchilar tor-mor etildi: +800🪙 oltin, +300🌾 oziq-ovqat, +35 Prestige!"
        else:
            user.gold = max(0, user.gold - 200)
            await session.commit()
            msg = "💰 200 tanga o'lpon to'landi. Qaroqchilar chekindi."

    await query.answer(msg, show_alert=True)
    await show_events_hub(query, user_id, is_message=False)


def register_events_handlers(app):
    app.add_handler(CommandHandler("events", events_command))
    app.add_handler(CommandHandler("throne", events_command))
    app.add_handler(CommandHandler("whitewalkers", events_command))
    app.add_handler(CallbackQueryHandler(events_callback, pattern="^menu_throne$"))
    app.add_handler(CallbackQueryHandler(raid_night_king_callback, pattern="^raid_night_king$"))
    app.add_handler(CallbackQueryHandler(night_king_leaderboard_callback, pattern="^night_king_leaderboard$"))
    app.add_handler(CallbackQueryHandler(event_plague_callback, pattern="^event_plague$"))
    app.add_handler(CallbackQueryHandler(plague_action_callback, pattern="^plague_"))
    app.add_handler(CallbackQueryHandler(event_bandits_callback, pattern="^event_bandits$"))
    app.add_handler(CallbackQueryHandler(bandits_action_callback, pattern="^bandits_"))
