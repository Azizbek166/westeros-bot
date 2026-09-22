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
        ww_event = await get_or_create_event_state(session, "white_walkers", {"hp": 500000, "max_hp": 500000, "status": "active"})
        ww_data = json.loads(ww_event.data_json)
        hp = ww_data.get("hp", 500000)
        max_hp = ww_data.get("max_hp", 500000)
        pct = max(0, int((hp / max_hp) * 100))
        bar_len = 10
        filled = int(bar_len * (pct / 100))
        progress_bar = "█" * filled + "░" * (bar_len - filled)

        ww_count = user.daily_ww_attack_count if user else 0
        plague_count = getattr(user, "daily_plague_count", 0) if user else 0
        bandit_count = getattr(user, "daily_bandit_count", 0) if user else 0

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
            [InlineKeyboardButton(f"☣️ Mintaqaviy Vabo Epidemiyasi ({plague_count}/2)", callback_data="event_plague")],
            [InlineKeyboardButton(f"🥷 Qaroqchilar Pistirmasiga Hujum ({bandit_count}/3)", callback_data="event_bandits")],
            [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
        ]

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def raid_night_king_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tun Qiroliga zarba berish (Kunlik limit: 3 ta)"""
    query = update.callback_query
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            try:
                await query.answer("Foydalanuvchi topilmadi!", show_alert=True)
            except Exception:
                pass
            return

        await crud.check_and_reset_daily_limits(session, user)
        if user.daily_ww_attack_count >= 3:
            try:
                await query.answer("❌ Bugungi 3 ta Oq yuruvchilarga qarshi hujum limitingiz tugagan! Ertaga yana reyd qilishingiz mumkin.", show_alert=True)
            except Exception:
                pass
            return

        army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
        army = army_res.scalar_one_or_none()
        total_troops = (army.infantry + army.archers + army.cavalry + army.spearmen) if army else 0

        if total_troops < 25:
            try:
                await query.answer("❌ Tun Qiroliga reyd qilish uchun kamida 25 ta askar kerak!", show_alert=True)
            except Exception:
                pass
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

        ww_event = await get_or_create_event_state(session, "white_walkers", {"hp": 500000, "max_hp": 500000, "status": "active"})
        ww_data = json.loads(ww_event.data_json)
        old_hp = ww_data.get("hp", 500000)
        new_hp = max(0, old_hp - total_dmg)
        ww_data["hp"] = new_hp
        ww_data["max_hp"] = 500000
        ww_event.data_json = json.dumps(ww_data)

        user.daily_ww_attack_count += 1

        # Ziyonni reytingga yozish
        await crud.record_night_king_damage(session, user.id, total_dmg)

        # Mukofot
        user.gold += 88
        user.iron += 45
        user.prestige += 50
        user.xp += 180

        # Agar Tun Qiroli yengilgan bo'lsa (HP == 0), Top 1 ga "Shimol Najotkori" unvoni va +500 Prestige beriladi
        victory_awarded = False
        if new_hp <= 0 and ww_data.get("status") != "defeated":
            ww_data["status"] = "defeated"
            ww_event.data_json = json.dumps(ww_data)
            v_res = await crud.award_night_king_victory(session, bot_app=context.application)
            victory_awarded = bool(v_res.get("awarded"))

        from core.leveling import check_user_level_up
        lvl_up, new_lvl, lvl_msg = check_user_level_up(user)

        await session.commit()

        extra_note = f"\n{lvl_msg}" if lvl_up else ""

    dragon_msg = f" (🔥 Ajdar olovi: +{dragon_dmg})" if dragon_dmg > 0 else ""
    if victory_awarded:
        alert_text = f"🏆 TUN QIROLI YENGILDI! Siz {total_dmg} ziyon yetkazdingiz! Top 1 jangchiga 'Shimol Najotkori' unvoni va +500 Prestige berildi!"
    else:
        alert_text = f"⚔️ Zarba berildi: -{total_dmg} wight!{dragon_msg} ({user.daily_ww_attack_count}/3)"
    try:
        await query.answer(alert_text, show_alert=True)
    except Exception:
        pass
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
        f"• 🥇 1-o'rin: +750🪙 Oltin, +500🏆 Prestige, 'Shimol Najotkori' unvoni\n"
        f"• 🥈 2-o'rin: +450🪙 Oltin, +300🏆 Prestige\n"
        f"• 🥉 3-o'rin: +250🪙 Oltin, +200🏆 Prestige\n"
        f"• 🎖️ 4-10 o'rinlar: +125🪙 Oltin, +100🏆 Prestige\n\n"
        f"Sizning bugungi hujumlaringiz: **{user_cnt}/3**"
    )

    buttons = [
        [InlineKeyboardButton("⚔️ Tun Qiroliga Zarba Berish", callback_data="raid_night_king")],
        [InlineKeyboardButton("🔙 Voqealarga Qaytish", callback_data="menu_throne")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ============================================================
# MINTAQAVIY VABO EPIDEMIYASI
# ============================================================

async def render_plague_screen(session, user: models.User, last_action_msg: str = None) -> tuple[str, InlineKeyboardMarkup]:
    """Mintaqaviy vabo ekrani matni va tugmalarini tayyorlash"""
    await crud.check_and_reset_daily_limits(session, user)

    # Agar user.house yuklanmagan bo'lsa
    if user.house_id and not user.house:
        user.house = await session.get(models.House, user.house_id)

    from data.map_data import REGIONS_DATA
    if user.house and user.house.region:
        reg_name = user.house.region
        reg_info = REGIONS_DATA.get(reg_name, {})
        reg_emoji = reg_info.get("emoji", "📍")
        reg_display = f"{reg_emoji} **{reg_name}** ({user.house.emoji} {user.house.name})"
        desc = reg_info.get("description", "Vesterosning aholi zich joylashgan hududi.")
    else:
        reg_display = "🗺️ **Westeros Sayyohlik Qarorgohi** (Xonadonsiz)"
        desc = "Mintaqaviy mustahkam qarorgohingiz yo'q, ammo atrofingizda qora o'lat xavfi kezmoqda."

    # Armiya holati
    army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
    army = army_res.scalar_one_or_none()
    tot_troops = ((army.infantry or 0) + (army.archers or 0) + (army.cavalry or 0) + (army.spearmen or 0)) if army else 0

    plague_count = getattr(user, "daily_plague_count", 0) or 0
    rem_actions = max(0, 2 - plague_count)

    if plague_count >= 2:
        status_str = "⚠️ **Bugungi barcha choralar ko'rildi (2/2 ta).**\nErtangi kunga qadar mintaqangiz nazorat ostida saqlanadi."
    else:
        status_str = f"📊 Bugungi choralar: **{plague_count}/2 ta** (Yana {rem_actions} ta chora ko'rishingiz mumkin)"

    text = (
        f"☣️ **MINTAQAVIY VABO EPIDEMIYASI**\n\n"
        f"📍 Mintaqangiz: {reg_display}\n"
        f"📜 _{desc}_\n"
        f"☣️ Epidemiya holati: **Xavfli O'choq (Qora O'lat)**\n\n"
        f"Mintaqangiz xalqi va garnizon askarlari orasida qora o'lat tarqalmoqda. "
        f"Maesterlar shoshilinch chora ko'rishingizni so'ramoqda:\n\n"
        f"💰 Shaxsiy hisobingiz: **{user.gold:,}**🪙 oltin, **{user.iron:,}**⛓️ temir\n"
        f"🛡️ Garnizon askarlaringiz: **{tot_troops:,}** ta jangchi\n\n"
        f"{status_str}\n\n"
        f"1. 🧪 **Dorilar Tayyorlash:** Maesterlar shifobaxsh giyohlar va eliksirlar tayyorlaydi (-300🪙, -100⛓️). "
        f"Vabo to'liq yengiladi (+40🏆 Prestige, +100⚡ XP).\n\n"
        f"2. 🚪 **Hududni Karantin Qilish:** 0 resurs sarflanadi. Qat'iy karantin o'rnatiladi, "
        f"ammo kasallangan 10 ta askar yo'qotiladi (+15🏆 Prestige, +40⚡ XP)."
    )

    if last_action_msg:
        text += f"\n\n📢 **Oxirgi qaror:**\n{last_action_msg}"

    buttons = []
    if plague_count < 2:
        buttons.append([InlineKeyboardButton("🧪 Dorilar Tayyorlash (-300🪙, -100⛓️)", callback_data="plague_cure")])
        buttons.append([InlineKeyboardButton("🚪 Hududni Karantin Qilish (-10 askar)", callback_data="plague_quarantine")])
    else:
        buttons.append([InlineKeyboardButton("✅ Bugungi Barcha Choralar Ko'rildi (2/2)", callback_data="plague_done_info")])

    buttons.append([InlineKeyboardButton("🔙 Voqealarga Qaytish", callback_data="menu_throne")])
    buttons.append([InlineKeyboardButton("🏰 Asosiy Menyu", callback_data="menu_main")])

    return text, InlineKeyboardMarkup(buttons)


async def event_plague_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vabo hodisasi menyusi (Kunlik limit 2 marta)"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        text, reply_markup = await render_plague_screen(session, user)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def plague_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vabo harakati natijasi (Maksimal 2 marta)"""
    query = update.callback_query
    action = query.data
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            try:
                await query.answer("Foydalanuvchi topilmadi!", show_alert=True)
            except Exception:
                pass
            return

        await crud.check_and_reset_daily_limits(session, user)

        plague_count = getattr(user, "daily_plague_count", 0) or 0
        if plague_count >= 2:
            try:
                await query.answer("❌ Bugungi vabo harakati limitingiz (2/2) tugagan! Ertaga qayta urinib ko'ring.", show_alert=True)
            except Exception:
                pass
            text, reply_markup = await render_plague_screen(session, user)
            try:
                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
            except Exception:
                pass
            return

        from core.leveling import check_user_level_up

        if action == "plague_cure":
            if user.gold < 300 or user.iron < 100:
                shortage = []
                if user.gold < 300:
                    shortage.append(f"{300 - user.gold:,}🪙 oltin")
                if user.iron < 100:
                    shortage.append(f"{100 - user.iron:,}⛓️ temir")
                alert_err = f"❌ Dorilar tayyorlash uchun resurs yetarli emas! Sizga yana {', '.join(shortage)} kerak."
                try:
                    await query.answer(alert_err, show_alert=True)
                except Exception:
                    pass
                text, reply_markup = await render_plague_screen(session, user, last_action_msg=alert_err)
                try:
                    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
                except Exception:
                    pass
                return

            user.gold -= 300
            user.iron -= 100
            user.prestige += 40
            user.xp += 100
            user.daily_plague_count = plague_count + 1

            lvl_up, new_lvl, lvl_msg = check_user_level_up(user)
            await session.commit()

            alert_msg = f"✅ Dorilar tayyorlandi! Vabo bartaraf etildi. (+40 Prestige, +100 XP, {user.daily_plague_count}/2)"
            result_note = f"✅ **Maesterlar dorivor giyohlar tayyorladi!**\nMintaqadagi vabo bartaraf etildi. Sizga +40🏆 Prestige va +100⚡ XP berildi."
            if lvl_up:
                result_note += f"\n🎉 {lvl_msg}"

        elif action == "plague_quarantine":
            army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
            army = army_res.scalar_one_or_none()

            dead_troops = 0
            if army:
                to_remove = 10
                for attr in ["infantry", "archers", "spearmen", "cavalry"]:
                    val = getattr(army, attr, 0) or 0
                    if val > 0:
                        take = min(val, to_remove)
                        setattr(army, attr, val - take)
                        to_remove -= take
                        dead_troops += take
                    if to_remove <= 0:
                        break

            user.prestige += 15
            user.xp += 40
            user.daily_plague_count = plague_count + 1

            lvl_up, new_lvl, lvl_msg = check_user_level_up(user)
            await session.commit()

            loss_str = f"{dead_troops} ta askar qurbon bo'ldi" if dead_troops > 0 else "harbiy talafotsiz"
            alert_msg = f"🚪 Karantin joriy qilindi ({loss_str}). (+15 Prestige, +40 XP, {user.daily_plague_count}/2)"
            result_note = f"🚪 **Mintaqada qat'iy harbiy karantin o'rnatildi!**\n{loss_str.capitalize()}, ammo aholi saqlab qolindi. Sizga +15🏆 Prestige va +40⚡ XP berildi."
            if lvl_up:
                result_note += f"\n🎉 {lvl_msg}"

        else:
            return

        try:
            await query.answer(alert_msg, show_alert=True)
        except Exception:
            pass

        text, reply_markup = await render_plague_screen(session, user, last_action_msg=result_note)
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception:
            pass


async def plague_done_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bugungi 2 ta chora to'liq ko'rilgani haqida popup bildirishnoma"""
    query = update.callback_query
    try:
        await query.answer(
            "✅ Siz bugun o'z mintaqangizda vaboga qarshi 2 ta zaruriy chorani to'liq ko'rdingiz!\n\n"
            "Ertangi kunga qadar mintaqangiz xavfsiz holatda saqlanadi. Ertaga yangi kunda yana chora ko'rishingiz mumkin.",
            show_alert=True
        )
    except Exception:
        pass


# ============================================================
# QAROQCHILAR VA ISYONCHILAR
# ============================================================

async def event_bandits_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qaroqchilar hodisasi menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if user:
            await crud.check_and_reset_daily_limits(session, user)
        b_count = getattr(user, "daily_bandit_count", 0) if user else 0

    buttons = [
        [InlineKeyboardButton(f"⚔️ Qaroqchilarga Hujum Qilish ({b_count}/3)", callback_data="bandits_fight")],
        [InlineKeyboardButton("💰 O'lpon To'lab Qutulish (-50🪙 oltin)", callback_data="bandits_pay")],
        [InlineKeyboardButton("🔙 Voqealarga Qaytish", callback_data="menu_throne")],
    ]

    text = (
        f"🥷 **QAROQCHILAR VA ISYONCHILAR PISTIRMASI!**\n\n"
        f"Savdo yo'llaringizga tog' qaroqchilari hujum qildi va karvonlaringizni to'smoqda!\n\n"
        f"1. **Hujum qilish:** Qaroqchilar bazasini tor-mor qilish (taxminan 5 ta askar yo'qotib, ularning xazinasidan +200🪙 oltin va +75🌾 oziq-ovqat olasiz).\n"
        f"2. **O'lpon to'lash:** 50 tanga berib xavfdan qutulish.\n\n"
        f"Bugungi hujumlaringiz: **{b_count}/3** ta"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def bandits_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qaroqchilar harakati natijasi"""
    query = update.callback_query
    action = query.data
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            try:
                await query.answer("Foydalanuvchi topilmadi!", show_alert=True)
            except Exception:
                pass
            return

        await crud.check_and_reset_daily_limits(session, user)

        if action == "bandits_fight":
            b_cnt = getattr(user, "daily_bandit_count", 0) or 0
            if b_cnt >= 3:
                try:
                    await query.answer("❌ Bugungi 3 ta qaroqchilar pistirmasiga hujum limitingiz tugagan! Ertaga yana urinib ko'rishingiz mumkin.", show_alert=True)
                except Exception:
                    pass
                return

            army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
            army = army_res.scalar_one_or_none()
            if not army or (army.infantry + army.archers + army.cavalry + army.spearmen) < 10:
                try:
                    await query.answer("❌ Qaroqchilarga qarshi chiqish uchun kamida 10 ta askar kerak!", show_alert=True)
                except Exception:
                    pass
                return
            if army.infantry >= 5:
                army.infantry -= 5
            else:
                army.archers = max(0, army.archers - 5)

            user.gold += 200
            user.food += 75
            user.prestige += 35
            user.xp += 120
            user.daily_bandit_count = b_cnt + 1

            from core.leveling import check_user_level_up
            lvl_up, new_lvl, lvl_msg = check_user_level_up(user)
            await session.commit()
            msg = f"🏆 G'alaba! Qaroqchilar tor-mor etildi: +200🪙 oltin, +75🌾 oziq-ovqat, +35 Prestige! ({user.daily_bandit_count}/3)"
        else:
            user.gold = max(0, user.gold - 50)
            await session.commit()
            msg = "💰 50 tanga o'lpon to'landi. Qaroqchilar chekindi."

    try:
        await query.answer(msg, show_alert=True)
    except Exception:
        pass
    await show_events_hub(query, user_id, is_message=False)


def register_events_handlers(app):
    app.add_handler(CommandHandler("events", events_command))
    app.add_handler(CommandHandler("throne", events_command))
    app.add_handler(CommandHandler("whitewalkers", events_command))
    app.add_handler(CallbackQueryHandler(events_callback, pattern="^menu_throne$"))
    app.add_handler(CallbackQueryHandler(raid_night_king_callback, pattern="^raid_night_king$"))
    app.add_handler(CallbackQueryHandler(night_king_leaderboard_callback, pattern="^night_king_leaderboard$"))
    app.add_handler(CallbackQueryHandler(event_plague_callback, pattern="^event_plague$"))
    app.add_handler(CallbackQueryHandler(plague_action_callback, pattern="^plague_(cure|quarantine)$"))
    app.add_handler(CallbackQueryHandler(plague_done_info_callback, pattern="^plague_done_info$"))
    app.add_handler(CallbackQueryHandler(event_bandits_callback, pattern="^event_bandits$"))
    app.add_handler(CallbackQueryHandler(bandits_action_callback, pattern="^bandits_"))
