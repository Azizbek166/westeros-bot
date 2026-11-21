import json
import logging
import random
from datetime import datetime

logger = logging.getLogger(__name__)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud, models
from keyboards.menus import back_to_main_keyboard
from config import escape_md
from sqlalchemy import select


async def get_or_create_event_state(session, event_name: str, default_data: dict) -> models.EventState:
    """EventState ni olish yoki yangi yaratish"""
    res = await session.execute(select(models.EventState).where(models.EventState.event_name == event_name))
    ev = res.scalars().first()
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


async def _safe_send_or_edit_events(target, text: str, markup: InlineKeyboardMarkup, is_message: bool):
    if is_message:
        try:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await target.message.reply_text(text.replace("*", "").replace("_", "").replace("`", ""), reply_markup=markup)
        return
    msg = getattr(target, "message", None)
    has_media = bool(msg and (msg.photo or msg.video or msg.animation or msg.audio or msg.document))
    if has_media:
        try:
            await msg.delete()
        except Exception:
            pass
        try:
            await msg.chat.send_message(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await msg.chat.send_message(text.replace("*", "").replace("_", "").replace("`", ""), reply_markup=markup)
        return
    try:
        await target.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        try:
            await target.edit_message_text(text.replace("*", "").replace("_", "").replace("`", ""), reply_markup=markup)
        except Exception:
            if msg and msg.chat:
                await msg.chat.send_message(text.replace("*", "").replace("_", "").replace("`", ""), reply_markup=markup)


async def show_events_hub(target, user_id: int, is_message: bool, last_report: str = ""):
    """Global hodisalar: Tun Qiroli (Oq Yuruvchilar), Vabo, Qaroqchilar va Temir Taxt"""
    try:
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_with_relations(session, user_id)
            if user:
                await crud.check_and_reset_daily_limits(session, user)

            kl_terr = await crud.get_territory_by_id(session, 8)  # King's Landing ID = 8
            kl_house = await session.get(models.House, kl_terr.owner_house_id) if (kl_terr and kl_terr.owner_house_id) else None
            kl_owner = f"{kl_house.emoji} {kl_house.name}" if kl_house else "Targaryen"

            # Tun Qiroli holati (To'lqin / Wave tizimi)
            ww_event = await get_or_create_event_state(
                session, "white_walkers", {"hp": 1000000, "max_hp": 1000000, "wave": 1, "status": "active"}
            )
            ww_data = json.loads(ww_event.data_json or "{}")
            wave = int(ww_data.get("wave", 1) or 1)
            max_hp = int(ww_data.get("max_hp", 1000000) or 1000000)
            hp = int(ww_data.get("hp", max_hp) or 0)
            if hp <= 0 and ww_data.get("status") == "defeated":
                wave += 1
                max_hp = 1000000 + (wave - 1) * 250000
                hp = max_hp
                ww_data.update({"wave": wave, "max_hp": max_hp, "hp": hp, "status": "active"})
                ww_event.data_json = json.dumps(ww_data)
                await session.commit()

            pct = max(0, min(100, int((hp / max(1, max_hp)) * 100)))
            bar_len = 10
            filled = int(bar_len * (pct / 100))
            progress_bar = "█" * filled + "░" * (bar_len - filled)

            ww_count = user.daily_ww_attack_count if user else 0
            plague_count = getattr(user, "daily_plague_count", 0) if user else 0
            bandit_count = getattr(user, "daily_bandit_count", 0) if user else 0

            my_dmg = 0
            has_adult_dragon = False
            if user:
                nk_res = await session.execute(
                    select(models.NightKingContribution).where(models.NightKingContribution.user_id == user.id)
                )
                my_dmg = sum((r.total_damage or 0) for r in nk_res.scalars().all())
                dragons = await crud.get_user_dragons(session, user.id)
                has_adult_dragon = any(d.stage == "adult" for d in dragons)

            report_block = f"\n━━━━━━━━━━━━━━━━━━━\n{last_report}\n" if last_report else ""
            text = (
                f"❄️ **OQ YURUVCHILAR — TUN QIROLI REYDI**\n\n"
                f"👑 **Temir Taxt sohibi:** {escape_md(kl_owner)} *(King's Landing + 800 Prestige)*\n\n"
                f"💀 **THE LONG NIGHT — {wave}-TO'LQIN (GLOBAL BOSS):**\n"
                f"• Zombi Armiyasi: **{hp:,} / {max_hp:,}** ({pct}%)\n"
                f"• Holat: `[{progress_bar}]`\n"
                f"• Bugungi janglaringiz: **{ww_count}/3** ta | Jami zararingiz: **{my_dmg:,}** ⚡\n\n"
                f"⚔️ **Jang Taktikalarini Tanlang:**\n"
                f"• ⚔️ *Oddiy Hujum:* 50+ askar (-12 talafot) | +500🪙, +400🌾, +250⛓️\n"
                f"• 🗡️ *Ajdar Shishasi:* -250🪙, -150⛓️ (-6 talafot) | 1.5x zarar (zirhni teshadi!)\n"
                f"• 🐉 *Ajdar Olovi:* Voyaga yetgan ajdar (-500🌾, **0 talafot!**) | 2.0x ajdar zarari"
                f"{report_block}"
            )

            buttons = [
                [InlineKeyboardButton(f"⚔️ Oddiy Hujum ({ww_count}/3)", callback_data="raid_nk:normal")],
                [InlineKeyboardButton(f"🗡️ Ajdar Shishasi Zarbasi (-250🪙/-150⛓️)", callback_data="raid_nk:dragonglass")],
            ]
            if has_adult_dragon:
                buttons.append([InlineKeyboardButton(f"🐉 Ajdar Olovi Zarbasi (-500🌾, 0 talafot)", callback_data="raid_nk:dragonfire")])
            buttons.extend([
                [InlineKeyboardButton("🏆 Tun Qiroli Ziyon Reytingi (Top 10)", callback_data="night_king_leaderboard")],
                [InlineKeyboardButton(f"☣️ Mintaqaviy Vabo ({plague_count}/2)", callback_data="event_plague"),
                 InlineKeyboardButton(f"🥷 Qaroqchilar ({bandit_count}/3)", callback_data="event_bandits")],
                [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")],
            ])
            await _safe_send_or_edit_events(target, text, InlineKeyboardMarkup(buttons), is_message)
    except Exception as ev_err:
        logger.error(f"show_events_hub error: {ev_err}", exc_info=True)
        err_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")]])
        await _safe_send_or_edit_events(target, f"❌ Oq Yuruvchilar panelini ochishda xatolik: {ev_err}", err_kb, is_message)


async def raid_night_king_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tun Qiroliga zarba berish (3 ta taktika, Kunlik limit: 3 ta)"""
    query = update.callback_query
    user_id = query.from_user.id
    mode = "normal"
    if query.data and ":" in query.data:
        mode = query.data.split(":", 1)[1]
    if mode not in ("normal", "dragonglass", "dragonfire"):
        mode = "normal"

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            await query.answer("Foydalanuvchi topilmadi!", show_alert=True)
            return

        await crud.check_and_reset_daily_limits(session, user)
        if user.daily_ww_attack_count >= 3:
            await query.answer("❌ Bugungi 3 ta Oq yuruvchilarga qarshi hujum limitingiz tugagan!", show_alert=True)
            return

        army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
        army = army_res.scalar_one_or_none()
        total_troops = ((army.infantry or 0) + (army.archers or 0) + (army.cavalry or 0) + (army.spearmen or 0)) if army else 0

        if mode != "dragonfire" and total_troops < 50:
            await query.answer("❌ Tun Qiroliga reyd qilish uchun kamida 50 ta askar kerak!", show_alert=True)
            return

        dragons = await crud.get_user_dragons(session, user.id)
        adult_dragons = [d for d in dragons if d.stage == "adult"]
        if mode == "dragonfire":
            if not adult_dragons:
                await query.answer("❌ Ajdar Olovi zarbasi uchun voyaga yetgan (adult) ajdar kerak!", show_alert=True)
                return
            if (user.food or 0) < 500:
                await query.answer("❌ Ajdarni uchirish uchun 500 🌾 bug'doy kerak!", show_alert=True)
                return
            user.food -= 500
        elif mode == "dragonglass":
            if (user.gold or 0) < 250 or (user.iron or 0) < 150:
                await query.answer("❌ Ajdar Shishasi uchun 250 🪙 oltin va 150 ⛓️ temir kerak!", show_alert=True)
                return
            user.gold -= 250
            user.iron -= 150

        # Talafot (dragonfire = 0, dragonglass = 6, normal = 12)
        troop_loss = 0 if mode == "dragonfire" else (6 if mode == "dragonglass" else 12)
        if troop_loss > 0 and army:
            lost_inf = min(army.infantry or 0, troop_loss // 2)
            army.infantry = (army.infantry or 0) - lost_inf
            rem = troop_loss - lost_inf
            lost_arc = min(army.archers or 0, max(1, rem // 2))
            army.archers = (army.archers or 0) - lost_arc
            rem -= lost_arc
            lost_sp = min(army.spearmen or 0, rem)
            army.spearmen = (army.spearmen or 0) - lost_sp

        # Zarar hisoblash (armiya kuchiga bog'liq + artefakt + ajdar + kritik zarba)
        army_bonus = min(1500, total_troops // 12)
        base_dmg = random.randint(450, 850) + army_bonus

        equipped = await crud.get_equipped_artifact(session, user.id)
        if equipped:
            from data.artifacts_data import ARTIFACTS_DATA
            art_data = ARTIFACTS_DATA.get(equipped.code, {})
            base_dmg = int(base_dmg * (1.0 + art_data.get("attack_bonus", 0.0)))

        dragon_dmg = 0
        if adult_dragons:
            best_dragon = max(adult_dragons, key=lambda d: d.power)
            dragon_mult = 2.0 if mode == "dragonfire" else 1.5
            dragon_dmg = int((best_dragon.power or 0) * dragon_mult)

        is_crit = random.random() < (0.30 if mode == "dragonglass" else 0.12)
        crit_mult = 1.4 if is_crit else 1.0

        # Oddiy hujumda 25% sovuq zirh; Ajdar Shishasi zirhni teshib 1.5x uradi!
        if mode == "dragonglass":
            total_dmg = max(100, int((base_dmg + dragon_dmg) * 1.5 * crit_mult))
        else:
            total_dmg = max(80, int((base_dmg + dragon_dmg) * 0.75 * crit_mult))

        ww_event = await get_or_create_event_state(
            session, "white_walkers", {"hp": 1000000, "max_hp": 1000000, "wave": 1, "status": "active"}
        )
        ww_data = json.loads(ww_event.data_json or "{}")
        wave = int(ww_data.get("wave", 1) or 1)
        max_hp = int(ww_data.get("max_hp", 1000000) or 1000000)
        old_hp = int(ww_data.get("hp", max_hp) or max_hp)
        new_hp = max(0, old_hp - total_dmg)
        ww_data["hp"] = new_hp

        user.daily_ww_attack_count += 1
        await crud.record_night_king_damage(session, user.id, total_dmg)

        # Mukofot
        if mode == "dragonglass":
            rw_g, rw_f, rw_i, rw_p, rw_xp = 650, 500, 300, 22, 280
        elif mode == "dragonfire":
            rw_g, rw_f, rw_i, rw_p, rw_xp = 700, 300, 320, 25, 300
        else:
            rw_g, rw_f, rw_i, rw_p, rw_xp = 500, 400, 250, 15, 200

        user.gold = (user.gold or 0) + rw_g
        user.food = (user.food or 0) + rw_f
        user.iron = (user.iron or 0) + rw_i
        user.prestige = (user.prestige or 0) + rw_p
        user.xp = (user.xp or 0) + rw_xp
        crud.track_user_gold_gain(user, rw_g)
        crud.track_user_prestige_gain(user, rw_p)

        victory_awarded = False
        if new_hp <= 0:
            v_res = await crud.award_night_king_victory(session, bot_app=context.application)
            victory_awarded = bool(v_res.get("awarded"))
            # Keyingi to'lqinga o'tish (Boss respawn)
            wave += 1
            max_hp = 1000000 + (wave - 1) * 250000
            ww_data["wave"] = wave
            ww_data["max_hp"] = max_hp
            ww_data["hp"] = max_hp
            ww_data["status"] = "active"

        ww_event.data_json = json.dumps(ww_data)

        from core.leveling import check_user_level_up
        lvl_up, _, lvl_msg = check_user_level_up(user)
        await session.commit()

    crit_tag = " 💥 **KRITIK ZARBA!**" if is_crit else ""
    drg_tag = f" (🔥 Ajdar: +{dragon_dmg:,})" if dragon_dmg > 0 else ""
    mode_lbl = {"normal": "⚔️ Oddiy Hujum", "dragonglass": "🗡️ Ajdar Shishasi", "dragonfire": "🐉 Ajdar Olovi"}[mode]
    last_report = (
        f"📢 **OXIRGI JANG ({mode_lbl}):**{crit_tag}\n"
        f"• Yetkazilgan zarar: **-{total_dmg:,}** HP{drg_tag}\n"
        f"• Talafot: **{troop_loss}** askar | Mukofot: +{rw_g}🪙, +{rw_f}🌾, +{rw_i}⛓️, +{rw_p}⭐, +{rw_xp}XP"
    )
    if victory_awarded:
        last_report += f"\n🏆 **TO'LQIN YENGILDI!** Top-1 jangchi mukofotlandi va **{wave}-To'lqin** boshlandi!"
    if lvl_up:
        last_report += f"\n{lvl_msg}"

    try:
        await query.answer(f"⚔️ -{total_dmg:,} zarar! ({user.daily_ww_attack_count}/3)", show_alert=False)
    except Exception:
        pass
    await show_events_hub(query, user_id, is_message=False, last_report=last_report)


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
            rows.append(f"{m} **{escape_md(char_name)}** ({escape_md(house_str)}) — **{dmg:,}** ziyon ({attacks} ta zarba)")

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
        [InlineKeyboardButton("⚔️ Oddiy Hujum", callback_data="raid_nk:normal"),
         InlineKeyboardButton("🗡️ Ajdar Shishasi", callback_data="raid_nk:dragonglass")],
        [InlineKeyboardButton("🔙 Voqealarga Qaytish", callback_data="menu_throne")],
    ]
    await _safe_send_or_edit_events(query, text, InlineKeyboardMarkup(buttons), is_message=False)


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
            user.prestige += 10
            user.xp += 100
            user.daily_plague_count = plague_count + 1

            lvl_up, new_lvl, lvl_msg = check_user_level_up(user)
            await session.commit()

            alert_msg = f"✅ Dorilar tayyorlandi! Vabo bartaraf etildi. (+10 Prestige, +100 XP, {user.daily_plague_count}/2)"
            result_note = f"✅ **Maesterlar dorivor giyohlar tayyorladi!**\nMintaqadagi vabo bartaraf etildi. Sizga +10🏆 Prestige va +100⚡ XP berildi."
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

            user.prestige += 3
            user.xp += 40
            user.daily_plague_count = plague_count + 1

            lvl_up, new_lvl, lvl_msg = check_user_level_up(user)
            await session.commit()

            loss_str = f"{dead_troops} ta askar qurbon bo'ldi" if dead_troops > 0 else "harbiy talafotsiz"
            alert_msg = f"🚪 Karantin joriy qilindi ({loss_str}). (+3 Prestige, +40 XP, {user.daily_plague_count}/2)"
            result_note = f"🚪 **Mintaqada qat'iy harbiy karantin o'rnatildi!**\n{loss_str.capitalize()}, ammo aholi saqlab qolindi. Sizga +3🏆 Prestige va +40⚡ XP berildi."
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
        f"1. **Hujum qilish:** Qaroqchilar bazasini tor-mor qilish (taxminan 5 ta askar yo'qotib, ularning xazinasidan +500🪙 oltin, +250🌾 oziq-ovqat va +100⛓️ temir olasiz).\n"
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

            user.gold += 450
            user.food += 350
            user.iron += 150
            user.prestige += 10
            user.xp += 120
            user.daily_bandit_count = b_cnt + 1

            from core.leveling import check_user_level_up
            lvl_up, new_lvl, lvl_msg = check_user_level_up(user)
            await session.commit()
            msg = f"🏆 G'alaba! Qaroqchilar tor-mor etildi: +450🪙 oltin, +350🌾 oziq-ovqat, +150⛓️ temir, +10 Prestige! ({user.daily_bandit_count}/3)"
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
    app.add_handler(CallbackQueryHandler(raid_night_king_callback, pattern="^raid_nk:"))
    app.add_handler(CallbackQueryHandler(night_king_leaderboard_callback, pattern="^night_king_leaderboard$"))
    app.add_handler(CallbackQueryHandler(event_plague_callback, pattern="^event_plague$"))
    app.add_handler(CallbackQueryHandler(plague_action_callback, pattern="^plague_(cure|quarantine)$"))
    app.add_handler(CallbackQueryHandler(plague_done_info_callback, pattern="^plague_done_info$"))
    app.add_handler(CallbackQueryHandler(event_bandits_callback, pattern="^event_bandits$"))
    app.add_handler(CallbackQueryHandler(bandits_action_callback, pattern="^bandits_"))
