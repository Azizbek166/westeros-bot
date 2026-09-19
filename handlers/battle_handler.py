import json
import re
import asyncio
import html
from datetime import datetime
from typing import Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
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
                t_name = terr.name if terr else "Qal'a"
                march_text += f"• 🎯 **{t_name}** sari yurish: {rem_sec // 60} daq {rem_sec % 60} soniya qoldi\n"
        else:
            march_text = "Hozirda faol harbiy yurishlar yo'q.\n"

        # Qal'amizga bo'layotgan dushman yurishlari (incoming attacks)
        incoming_text = ""
        inc_marches = []
        if user.house_id:
            relevant_house_ids = [user.house_id]
            al_res = await session.execute(
                select(models.Alliance).where(
                    models.Alliance.status == "active",
                    (models.Alliance.house_a_id == user.house_id) | (models.Alliance.house_b_id == user.house_id)
                )
            )
            alliances = al_res.scalars().all()
            for al in alliances:
                ally_id = al.house_b_id if al.house_a_id == user.house_id else al.house_a_id
                if ally_id not in relevant_house_ids:
                    relevant_house_ids.append(ally_id)

            terr_ids_res = await session.execute(
                select(models.Territory.id).where(models.Territory.owner_house_id.in_(relevant_house_ids))
            )
            house_terr_ids = terr_ids_res.scalars().all()
            if house_terr_ids:
                inc_res = await session.execute(
                    select(models.BattleMarch).where(
                        models.BattleMarch.target_territory_id.in_(house_terr_ids),
                        models.BattleMarch.status == "marching",
                    )
                )
                inc_marches = inc_res.scalars().all()
                if inc_marches:
                    for im in inc_marches:
                        terr = await session.get(models.Territory, im.target_territory_id)
                        rem_sec = max(0, int((im.arrival_time - datetime.utcnow()).total_seconds()))
                        t_name = terr.name if terr else "Qal'a"
                        dr_icon = "🔥🐉 " if getattr(im, "has_dragon", False) else ""
                        tag = "🤝 Ittifoqchimiz" if (terr and terr.owner_house_id != user.house_id) else "🚨 Qal'amiz"
                        incoming_text += f"• {tag}: {dr_icon}**{t_name}** ga hujum kelmoqda ({rem_sec // 60} daq {rem_sec % 60} soniya qoldi)!\n"

        # So'nggi jang hisobotlari
        reports_res = await session.execute(
            select(models.BattleReport)
            .where(
                (models.BattleReport.attacker_user_id == user.id) | 
                (models.BattleReport.defender_user_id == user.house_id)
            )
            .order_by(desc(models.BattleReport.timestamp))
            .limit(3)
        )
        recent_reports = reports_res.scalars().all()

        reports_text = ""
        if recent_reports:
            for r in recent_reports:
                res_icon = "🏆 G'alaba" if (r.result == "attacker_won" and r.attacker_user_id == user.id) or (r.result == "defender_won" and r.defender_user_id == user.house_id) else "🛡️ Talofat"
                reports_text += f"• {res_icon}: {r.details[:70]}...\n"
        else:
            reports_text = "Janglar tarixi bo'sh.\n"

        defense_buttons = []
        if inc_marches:
            for im in inc_marches:
                terr = await session.get(models.Territory, im.target_territory_id)
                rem_sec = max(0, int((im.arrival_time - datetime.utcnow()).total_seconds()))
                t_name = terr.name if terr else "Qal'a"
                tag = "🤝 Ittifoqchi" if (terr and terr.owner_house_id != user.house_id) else "🚨 Qal'amiz"
                defense_buttons.append([
                    InlineKeyboardButton(f"{tag}: {t_name} Himoyasiga O'tish! ({rem_sec // 60}d {rem_sec % 60}s)", callback_data=f"defend_siege:{im.id}")
                ])

        buttons = []
        if defense_buttons:
            buttons.extend(defense_buttons)

        is_lord = user.house and ((user.house.lord_user_id == user.telegram_id) or user.rank == "king")
        if is_lord:
            buttons.append([InlineKeyboardButton("📢 Xonadonga Safarbarlik Chaqiruvi (SOS)", callback_data="call_to_arms_broadcast")])

        buttons.append([InlineKeyboardButton("⚔️ Dushman Qal'asiga Yurish Boshlash (Xarita)", callback_data="menu_map")])
        buttons.append([InlineKeyboardButton("🔄 Vaqtni Yangilash", callback_data="menu_battle")])
        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        # Urush holati
        war_status = await crud.get_war_status(session)
        if war_status["is_active"]:
            rem_info = ""
            if war_status.get("remaining_seconds") is not None and war_status["remaining_seconds"] > 0:
                rem_h = war_status["remaining_seconds"] // 3600
                rem_m = (war_status["remaining_seconds"] % 3600) // 60
                rem_s = war_status["remaining_seconds"] % 60
                t_str = f"{rem_h} soat {rem_m} daq" if rem_h > 0 else f"{rem_m} daq {rem_s} soniya"
                rem_info = f" (⏱️ Qolgan vaqt: **{t_str}**)"
            war_banner = f"🟢 ⚔️ **HARBIY HOLAT: URUSH REJIMI OCHIQ!**{rem_info}\n*Barcha qal'alarga yurishlar va qamallar faol!*\n"
        else:
            war_banner = (
                "🕊️ 🛑 **SULH DAVRI: URUSH REJIMI VAQTINCHA YOPIQ!**\n"
                "*Qirol farmoniga binoan o'zaro urushlar to'xtatilgan. Hozirda dushman qal'alariga hujum qilib bo'lmaydi. Armiyangizni mustahkamlang!*\n"
            )

        text = (
            f"🛡️ **HARBIY AMALIYOTLAR MARKAZI**\n\n"
            f"{war_banner}\n"
            f"🚩 **BIZNING YURISHLAR:**\n{march_text}\n"
        )
        if incoming_text:
            text += f"🚨 **QAL'AMIZGA XAVF (HIMOYA TALAB):**\n{incoming_text}\n"

        text += (
            f"📜 **SO'NGGI JANG HISOBOTLARI:**\n{reports_text}\n"
            f"Yangi qal'ani zabt etish uchun xaritadan nishonni tanlang:"
        )

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


def extract_troop_val(names: list, text: str) -> Optional[int]:
    joined = "|".join(names)
    pattern_pre = rf'(?:^|[\s,;])(?:{joined})\s*[:=]?\s*(\d+)'
    m = re.search(pattern_pre, text, re.I)
    if m:
        return int(m.group(1))
    pattern_suf = rf'(\d+)\s*[:=]?\s*(?:{joined})(?:$|[\s,;])'
    m2 = re.search(pattern_suf, text, re.I)
    if m2:
        return int(m2.group(1))
    return None


def parse_march_troops(text: str, army: models.Army) -> Optional[dict]:
    p = extract_troop_val(['piyodalar', 'piyoda', 'p'], text)
    k = extract_troop_val(['kamonchilar', 'kamonchi', 'kam', 'k'], text)
    o = extract_troop_val(['otliqlar', 'otliq', 'ot', 'o'], text)
    n = extract_troop_val(['nayzachilar', 'nayzachi', 'nayza', 'n'], text)
    m = extract_troop_val(['maxsuslar', 'maxsus', 'special', 'spc', 'm'], text)

    has_named = any(x is not None for x in [p, k, o, n, m])
    if has_named:
        inf = p or 0
        arc = k or 0
        cav = o or 0
        sp = n or 0
        spc = m or 0
    else:
        nums = [int(x) for x in re.findall(r'\b\d+\b', text)]
        if not nums:
            return None
        if len(nums) >= 5:
            inf, arc, cav, sp, spc = nums[0], nums[1], nums[2], nums[3], nums[4]
        elif len(nums) == 4:
            inf, arc, cav, sp, spc = nums[0], nums[1], nums[2], nums[3], 0
        elif len(nums) == 3:
            inf, arc, cav, sp, spc = nums[0], nums[1], nums[2], 0, 0
        elif len(nums) == 2:
            inf, arc, cav, sp, spc = nums[0], nums[1], 0, 0, 0
        elif len(nums) == 1:
            total_req = nums[0]
            total_avail = army.infantry + army.archers + army.cavalry + army.spearmen + army.special_troops
            if total_avail == 0:
                return None
            ratio = min(1.0, total_req / total_avail)
            inf = int(army.infantry * ratio)
            arc = int(army.archers * ratio)
            cav = int(army.cavalry * ratio)
            sp = int(army.spearmen * ratio)
            spc = int(army.special_troops * ratio)
            rem = min(total_req, total_avail) - (inf + arc + cav + sp + spc)
            if rem > 0 and army.infantry >= inf + rem:
                inf += rem
            elif rem > 0 and army.archers >= arc + rem:
                arc += rem
        else:
            return None

    inf = max(0, min(inf, army.infantry))
    arc = max(0, min(arc, army.archers))
    cav = max(0, min(cav, army.cavalry))
    sp = max(0, min(sp, army.spearmen))
    spc = max(0, min(spc, army.special_troops))

    return {
        "infantry": inf,
        "archers": arc,
        "cavalry": cav,
        "spearmen": sp,
        "special": spc,
        "total": inf + arc + cav + sp + spc,
    }


async def render_march_prep(update: Update, context: ContextTypes.DEFAULT_TYPE, terr_id: int):
    """Hujumga tayyorgarlik interaktiv ekranini chizish"""
    query = update.callback_query
    user_id = update.effective_user.id
    chat_id = query.message.chat_id if (query and query.message) else (update.effective_chat.id if update.effective_chat else user_id)

    async def safe_reply(msg_text: str, markup=None):
        if query and query.message:
            if getattr(query.message, "photo", None):
                try:
                    await query.message.delete()
                except Exception:
                    pass
                try:
                    await context.bot.send_message(chat_id=chat_id, text=msg_text, parse_mode="Markdown", reply_markup=markup)
                    return
                except Exception:
                    clean = msg_text.replace("*", "").replace("_", "")
                    await context.bot.send_message(chat_id=chat_id, text=clean, reply_markup=markup)
                    return
            try:
                await query.edit_message_text(msg_text, parse_mode="Markdown", reply_markup=markup)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    clean = msg_text.replace("*", "").replace("_", "")
                    try:
                        await query.edit_message_text(clean, reply_markup=markup)
                    except Exception:
                        await context.bot.send_message(chat_id=chat_id, text=clean, reply_markup=markup)
        elif update.message:
            try:
                await update.message.reply_text(msg_text, parse_mode="Markdown", reply_markup=markup)
            except Exception:
                clean = msg_text.replace("*", "").replace("_", "")
                await update.message.reply_text(clean, reply_markup=markup)

    try:
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_with_relations(session, user_id)
            terr = await crud.get_territory_by_id(session, terr_id)

            if not user or not terr:
                if query:
                    await query.answer("Hudud yoki o'yinchi topilmadi.", show_alert=True)
                return

            if not user.army:
                army_res = await session.execute(select(models.Army).where(models.Army.user_id == user.id))
                user_army = army_res.scalar_one_or_none()
                if not user_army:
                    user_army = models.Army(
                        user_id=user.id,
                        infantry=0,
                        archers=0,
                        cavalry=0,
                        spearmen=0,
                        special_troops=0
                    )
                    session.add(user_army)
                    await session.commit()
                    await session.refresh(user_army)
                user.army = user_army

            if not user.house and user.house_id:
                user.house = await session.get(models.House, user.house_id)

            # Urush holati tekshiruvi (Sulh davrida hujum qilib bo'lmaydi)
            war_status = await crud.get_war_status(session)
            if not war_status["is_active"]:
                if query:
                    await query.answer("🕊️ Hozirda Vesterosda sulh davri! Urush rejimi yopiq.", show_alert=True)
                await safe_reply(
                    "🕊️ **HOZIRDA VESTEROSDA SULH DAVRI!**\n\n"
                    "Qirol farmoniga ko'ra urush rejimi yopiq. Hozirda dushman qal'alariga yangi harbiy yurish jo'natib bo'lmaydi.\n\n"
                    "🛡️ *Bu vaqtda nima qilish mumkin?*\n"
                    "• Armiyangizni to'ldiring va yangi askarlar yollang\n"
                    "• O'z qal'angiz devorlari va garnizonini mustahkamlang\n"
                    "• Ajdaringizni boqing va tayyorlang\n\n"
                    "Urush ochilishi haqida botda e'lon beriladi!",
                    InlineKeyboardMarkup([[InlineKeyboardButton("🗺️ Xaritaga Qaytish", callback_data="menu_map")]])
                )
                return

            is_allowed, err_msg = can_attack_target(user, terr)
            if not is_allowed:
                if query:
                    await query.answer(err_msg, show_alert=True)
                await safe_reply(
                    f"{err_msg}\n\nO'z xonadoningiz qal'asiga hujum qilib bo'lmaydi. Xaritadan dushman xonadon qal'asini tanlang:",
                    InlineKeyboardMarkup([[InlineKeyboardButton("🗺️ Xaritaga Qaytish", callback_data="menu_map")]])
                )
                return

            # Ittifoqchi xonadonga hujum qilish taqiqlanadi
            if user.house_id and terr.owner_house_id and user.house_id != terr.owner_house_id:
                allies = await crud.get_active_alliances_for_house(session, user.house_id)
                allied_ids = {a.house_a_id if a.house_b_id == user.house_id else a.house_b_id for a in allies}
                if terr.owner_house_id in allied_ids:
                    if query:
                        await query.answer("❌ Ushbu qal'a sizning rasmiy ittifoqchingizga tegishli! Ittifoqdoshga hujum qilib bo'lmaydi.", show_alert=True)
                    await safe_reply(
                        "❌ **Ittifoqdosh qal'asiga hujum qilib bo'lmaydi!**\n\n"
                        "Siz ushbu xonadon bilan sulh yoki harbiy ittifoq tuzgansiz. Faqat dushman qal'alariga yurish boshlashingiz mumkin.",
                        InlineKeyboardMarkup([[InlineKeyboardButton("🗺️ Xaritaga Qaytish", callback_data="menu_map")]])
                    )
                    return

            u_inf = (user.army.infantry if user.army else 0) or 0
            u_arc = (user.army.archers if user.army else 0) or 0
            u_cav = (user.army.cavalry if user.army else 0) or 0
            u_sp = (user.army.spearmen if user.army else 0) or 0
            u_spc = (user.army.special_troops if user.army else 0) or 0
            u_cat = (user.army.catapults if user.army else 0) or 0
            u_tow = (user.army.siege_towers if user.army else 0) or 0
            total_army = u_inf + u_arc + u_cav + u_sp + u_spc

            if total_army < 50:
                msg = (
                    f"❌ **Yurish uchun kamida 50 ta askar kerak!**\n\n"
                    f"Sizning armiyangiz: **{total_army}** ta askar.\n"
                    f"Armiya bo'limidan askar yollang:"
                )
                markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚔️ Armiya (Askar Yollash)", callback_data="menu_army")],
                    [InlineKeyboardButton("🔙 Xaritaga Qaytish", callback_data="menu_map")]
                ])
                if query:
                    await query.answer("❌ Yurish uchun kamida 50 ta askar kerak!", show_alert=True)
                await safe_reply(msg, markup)
                return

            user_dragons = await crud.get_user_dragons(session, user.id)
            dragon_items = []
            for d in user_dragons:
                if d.stage in ["baby", "adult"] and d.hunger >= 20:
                    d_st = await crud.get_dragon_deployment_status(session, d.id)
                    dragon_items.append({"dragon": d, "status": d_st})

            free_dragons = [di["dragon"] for di in dragon_items if di["status"]["type"] == "resting"]

            special_name = user.house.special_troop_name if user.house and user.house.special_troop_name else "Maxsus Qo'shin"

            draft_key = f"march_{terr.id}"
            if draft_key not in context.user_data:
                first_free = free_dragons[0] if free_dragons else None
                context.user_data[draft_key] = {
                    "infantry": u_inf,
                    "archers": u_arc,
                    "cavalry": u_cav,
                    "spearmen": u_sp,
                    "special": u_spc,
                    "catapults": u_cat,
                    "siege_towers": u_tow,
                    "dragon_id": first_free.id if first_free else None,
                    "dragon_tactic": "balanced" if first_free else "none",
                }

            draft = context.user_data[draft_key]
            draft["infantry"] = max(0, min(draft.get("infantry", u_inf) or 0, u_inf))
            draft["archers"] = max(0, min(draft.get("archers", u_arc) or 0, u_arc))
            draft["cavalry"] = max(0, min(draft.get("cavalry", u_cav) or 0, u_cav))
            draft["spearmen"] = max(0, min(draft.get("spearmen", u_sp) or 0, u_sp))
            draft["special"] = max(0, min(draft.get("special", u_spc) or 0, u_spc))
            draft["catapults"] = max(0, min(draft.get("catapults", u_cat) or 0, u_cat))
            draft["siege_towers"] = max(0, min(draft.get("siege_towers", u_tow) or 0, u_tow))

            sel_dr_id = draft.get("dragon_id")
            active_dragon = next((d for d in free_dragons if d.id == sel_dr_id), None)
            if not active_dragon:
                draft["dragon_id"] = None
                draft["dragon_tactic"] = "none"

            sel_inf = draft["infantry"]
            sel_arc = draft["archers"]
            sel_cav = draft["cavalry"]
            sel_sp = draft["spearmen"]
            sel_spc = draft["special"]
            sel_cat = draft["catapults"]
            sel_tow = draft["siege_towers"]
            total_selected = sel_inf + sel_arc + sel_cav + sel_sp + sel_spc

            tactic = draft.get("dragon_tactic", "none")
            tactic_display = {
                "balanced": "🔥 Yalpi Olovli Bo'ron",
                "walls": "🔥 Devorlarni Eritish",
                "ranged": "🔥 Merganlarni Yoqish",
                "frontline": "🔥 Old Qatorlarni Yoqish",
                "none": "❌ Ajdarsiz",
            }.get(tactic, "❌ Ajdarsiz")

            dragon_info = ""
            if dragon_items:
                dragon_info = "🐉 **SIZNING AJDARLARINGIZ HOLATI:**\n"
                for di in dragon_items:
                    d = di["dragon"]
                    dst = di["status"]
                    is_sel = (draft.get("dragon_id") == d.id)
                    sel_str = " ⚔️ **[HUJUMGA TANLANGAN]**" if is_sel else ""
                    if dst["type"] == "stationed":
                        status_str = f"🏰 {dst.get('territory_name', 'Qal\'a')} mudofaasida"
                    elif dst["type"] == "marching":
                        status_str = f"⚔️ {dst.get('target_name', 'Qal\'a')}ga yurishda"
                    else:
                        status_str = "🏠 Uyada (erkin)"
                    dragon_info += f"• **{d.name}** ({d.power}⚡, {d.hunger}%🍗) — {status_str}{sel_str}\n"

                if active_dragon:
                    dragon_info += f"• Tanlangan ajdar taktikasi: **{tactic_display}**\n\n"
                else:
                    dragon_info += f"• Tanlangan taktika: **❌ Ajdarsiz yurish**\n\n"
            else:
                dragon_info = "⚠️ *Sizda jangovar ajdar yo'q yoki qorni och.*\n\n"

            t_name = (terr.name or "Hudud").upper()
            c_name = terr.castle_name or terr.name or "Qal'a"
            reg = terr.region or "Vesteros"

            siege_lines = ""
            if u_cat > 0:
                siege_lines += f"• 🪨 Katapulta: **{sel_cat:,}** / {u_cat:,}\n"
            if u_tow > 0:
                siege_lines += f"• 🪜 Qamal minorasi: **{sel_tow:,}** / {u_tow:,}\n"

            text = (
                f"⚔️ **HARBIY YURISH REJASI: {t_name}**\n\n"
                f"🏰 Nishon: **{c_name}** ({reg})\n"
                f"⏱️ Yurish vaqti: **{BASE_MARCH_MINUTES} daqiqa**\n\n"
                f"📊 **QO'SHIN TARKIBI (Tanlangan / Mavjud):**\n"
                f"• 🛡️ Piyoda: **{sel_inf:,}** / {u_inf:,}\n"
                f"• 🏹 Kamonchi: **{sel_arc:,}** / {u_arc:,}\n"
                f"• 🐎 Otliq: **{sel_cav:,}** / {u_cav:,}\n"
                f"• 🗡️ Nayzachi: **{sel_sp:,}** / {u_sp:,}\n"
                f"• 🔥 {special_name}: **{sel_spc:,}** / {u_spc:,}\n"
                f"{siege_lines}\n"
                f"🎯 **Jami safarbar etilmoqda:** **{total_selected:,}** ta askar\n\n"
                f"{dragon_info}"
                f"⚠️ *Hujum boshlangach, 3 kunlik Tinchlik Qalqoningiz bekor bo'ladi!*\n\n"
                f"Tugmalar orqali sonlarni o'zgartiring yoki qo'lda yozing:"
            )

            buttons = [
                [
                    InlineKeyboardButton("⚔️ 100% (Hammasi)", callback_data=f"m_pre:{terr.id}:100"),
                    InlineKeyboardButton("🛡️ 50%", callback_data=f"m_pre:{terr.id}:50"),
                    InlineKeyboardButton("🗑️ 0 qilish", callback_data=f"m_pre:{terr.id}:0"),
                ],
                [
                    InlineKeyboardButton("-100", callback_data=f"m_adj:{terr.id}:inf:-100"),
                    InlineKeyboardButton(f"🛡️ Piyoda: {sel_inf:,}", callback_data=f"m_info:{terr.id}:inf"),
                    InlineKeyboardButton("+100", callback_data=f"m_adj:{terr.id}:inf:+100"),
                    InlineKeyboardButton("MAX", callback_data=f"m_adj:{terr.id}:inf:max"),
                ],
                [
                    InlineKeyboardButton("-100", callback_data=f"m_adj:{terr.id}:arc:-100"),
                    InlineKeyboardButton(f"🏹 Kamonchi: {sel_arc:,}", callback_data=f"m_info:{terr.id}:arc"),
                    InlineKeyboardButton("+100", callback_data=f"m_adj:{terr.id}:arc:+100"),
                    InlineKeyboardButton("MAX", callback_data=f"m_adj:{terr.id}:arc:max"),
                ],
                [
                    InlineKeyboardButton("-100", callback_data=f"m_adj:{terr.id}:cav:-100"),
                    InlineKeyboardButton(f"🐎 Otliq: {sel_cav:,}", callback_data=f"m_info:{terr.id}:cav"),
                    InlineKeyboardButton("+100", callback_data=f"m_adj:{terr.id}:cav:+100"),
                    InlineKeyboardButton("MAX", callback_data=f"m_adj:{terr.id}:cav:max"),
                ],
                [
                    InlineKeyboardButton("-100", callback_data=f"m_adj:{terr.id}:sp:-100"),
                    InlineKeyboardButton(f"🗡️ Nayzachi: {sel_sp:,}", callback_data=f"m_info:{terr.id}:sp"),
                    InlineKeyboardButton("+100", callback_data=f"m_adj:{terr.id}:sp:+100"),
                    InlineKeyboardButton("MAX", callback_data=f"m_adj:{terr.id}:sp:max"),
                ],
                [
                    InlineKeyboardButton("-25", callback_data=f"m_adj:{terr.id}:spc:-25"),
                    InlineKeyboardButton(f"🔥 {special_name[:14]}: {sel_spc:,}", callback_data=f"m_info:{terr.id}:spc"),
                    InlineKeyboardButton("+25", callback_data=f"m_adj:{terr.id}:spc:+25"),
                    InlineKeyboardButton("MAX", callback_data=f"m_adj:{terr.id}:spc:max"),
                ],
            ]

            if u_cat > 0:
                buttons.append([
                    InlineKeyboardButton("-5", callback_data=f"m_adj:{terr.id}:cat:-5"),
                    InlineKeyboardButton(f"🪨 Katapulta: {sel_cat:,}", callback_data=f"m_info:{terr.id}:cat"),
                    InlineKeyboardButton("+5", callback_data=f"m_adj:{terr.id}:cat:+5"),
                    InlineKeyboardButton("MAX", callback_data=f"m_adj:{terr.id}:cat:max"),
                ])
            if u_tow > 0:
                buttons.append([
                    InlineKeyboardButton("-5", callback_data=f"m_adj:{terr.id}:tow:-5"),
                    InlineKeyboardButton(f"🪜 Qamal min: {sel_tow:,}", callback_data=f"m_info:{terr.id}:tow"),
                    InlineKeyboardButton("+5", callback_data=f"m_adj:{terr.id}:tow:+5"),
                    InlineKeyboardButton("MAX", callback_data=f"m_adj:{terr.id}:tow:max"),
                ])

            buttons.append([
                InlineKeyboardButton("✍️ Aniq Sonlarni Qo'lda Yozish", callback_data=f"march_custom_req:{terr.id}"),
            ])

            if free_dragons:
                sel_name = active_dragon.name if active_dragon else "❌ Ajdarsiz"
                buttons.append([
                    InlineKeyboardButton(f"🐉 Ajdarni Tanlash: {sel_name} 🔄", callback_data=f"m_sel_drg:{terr.id}")
                ])
                if active_dragon:
                    buttons.append([
                        InlineKeyboardButton(f"🔥 Drakarys Taktikasi: {tactic_display} 🔄", callback_data=f"m_drg:{terr.id}")
                    ])

            buttons.append([
                InlineKeyboardButton(f"🚀 HUJUMNI BOSHLASH ({total_selected:,} askar)", callback_data=f"send_custom_march:{terr.id}")
            ])
            buttons.append([
                InlineKeyboardButton("🔙 Bekor Qilish", callback_data=f"view_terr:{terr.id}")
            ])

            reply_markup = InlineKeyboardMarkup(buttons)
            await safe_reply(text, reply_markup)

    except Exception as e:
        import traceback
        traceback.print_exc()
        if query:
            try:
                await query.answer(f"Xatolik: {str(e)[:50]}", show_alert=True)
            except Exception:
                pass


async def march_prep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hujumga tayyorgarlik ekrani"""
    query = update.callback_query
    terr_id = int(query.data.split(":")[1])
    try:
        await query.answer()
    except Exception:
        pass
    await render_march_prep(update, context, terr_id)


async def march_adj_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'shin sonini alohida birlik bo'yicha oshirish/kamaytirish"""
    query = update.callback_query
    parts = query.data.split(":")
    terr_id = int(parts[1])
    unit = parts[2]
    action = parts[3]
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            await query.answer("Foydalanuvchi topilmadi.", show_alert=True)
            return

        unit_max_map = {
            "inf": (user.army.infantry if user.army else 0) or 0,
            "arc": (user.army.archers if user.army else 0) or 0,
            "cav": (user.army.cavalry if user.army else 0) or 0,
            "sp": (user.army.spearmen if user.army else 0) or 0,
            "spc": (user.army.special_troops if user.army else 0) or 0,
            "cat": (user.army.catapults if user.army else 0) or 0,
            "tow": (user.army.siege_towers if user.army else 0) or 0,
        }
        unit_key_map = {
            "inf": "infantry",
            "arc": "archers",
            "cav": "cavalry",
            "sp": "spearmen",
            "spc": "special",
            "cat": "catapults",
            "tow": "siege_towers",
        }

        if unit not in unit_max_map:
            await query.answer()
            return

        max_val = unit_max_map[unit]
        draft_key = unit_key_map[unit]

        draft = context.user_data.setdefault(f"march_{terr_id}", {
            "infantry": user.army.infantry,
            "archers": user.army.archers,
            "cavalry": user.army.cavalry,
            "spearmen": user.army.spearmen,
            "special": user.army.special_troops,
            "catapults": getattr(user.army, 'catapults', 0) or 0,
            "siege_towers": getattr(user.army, 'siege_towers', 0) or 0,
            "dragon_tactic": "balanced",
        })

        curr_val = draft.get(draft_key, max_val)

        if action in ["+100", "+25", "+5"]:
            delta = int(action)
            draft[draft_key] = min(max_val, curr_val + delta)
            await query.answer(f"{action} ({draft[draft_key]}/{max_val})")
        elif action in ["-100", "-25", "-5"]:
            delta = int(action[1:])
            draft[draft_key] = max(0, curr_val - delta)
            await query.answer(f"-{delta} ({draft[draft_key]}/{max_val})")
        elif action == "max":
            if curr_val >= max_val and max_val > 0:
                draft[draft_key] = 0
                await query.answer(f"0 ga tenglandi (0/{max_val})")
            else:
                draft[draft_key] = max_val
                await query.answer(f"Maksimal qilindi ({max_val}/{max_val})")
        else:
            await query.answer()

    await render_march_prep(update, context, terr_id)


async def march_preset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Armiyaning foiz ulushini tanlash (100%, 50%, 0%)"""
    query = update.callback_query
    parts = query.data.split(":")
    terr_id = int(parts[1])
    pct = int(parts[2])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            await query.answer()
            return

        ratio = pct / 100.0
        draft = context.user_data.setdefault(f"march_{terr_id}", {})
        draft["infantry"] = int(user.army.infantry * ratio)
        draft["archers"] = int(user.army.archers * ratio)
        draft["cavalry"] = int(user.army.cavalry * ratio)
        draft["spearmen"] = int(user.army.spearmen * ratio)
        draft["special"] = int(user.army.special_troops * ratio)
        draft["catapults"] = int((getattr(user.army, 'catapults', 0) or 0) * ratio)
        draft["siege_towers"] = int((getattr(user.army, 'siege_towers', 0) or 0) * ratio)
        await query.answer(f"{pct}% ga sozlandi")

    await render_march_prep(update, context, terr_id)


async def march_select_dragon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Harbiy yurishga olib ketiladigan ajdarni tanlash / almashtirish"""
    query = update.callback_query
    parts = query.data.split(":")
    terr_id = int(parts[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return
        free_dragons = await crud.get_user_available_dragons(session, user.id)

    draft = context.user_data.setdefault(f"march_{terr_id}", {})
    cur_id = draft.get("dragon_id")

    cycle_opts = [None] + [d.id for d in free_dragons]
    try:
        cur_idx = cycle_opts.index(cur_id)
        next_idx = (cur_idx + 1) % len(cycle_opts)
    except ValueError:
        next_idx = 0

    new_id = cycle_opts[next_idx]
    draft["dragon_id"] = new_id

    if new_id is None:
        draft["dragon_tactic"] = "none"
        await query.answer("❌ Ajdarsiz hujum tanlandi.")
    else:
        chosen_d = next((d for d in free_dragons if d.id == new_id), None)
        d_name = chosen_d.name if chosen_d else "Ajdar"
        if draft.get("dragon_tactic", "none") == "none":
            draft["dragon_tactic"] = "balanced"
        await query.answer(f"🐉 {d_name} tanlandi!")

    await render_march_prep(update, context, terr_id)


async def march_dragon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdar jangovar taktikasini o'zgartirish"""
    query = update.callback_query
    parts = query.data.split(":")
    terr_id = int(parts[1])

    tactics_cycle = ["balanced", "walls", "ranged", "frontline"]
    tactic_names = {
        "balanced": "Yalpi Olovli Bo'ron",
        "walls": "Devorlarni Eritish",
        "ranged": "Merganlarni Yoqish",
        "frontline": "Old Qatorlarni Yoqish",
    }

    draft = context.user_data.setdefault(f"march_{terr_id}", {})
    current_tactic = draft.get("dragon_tactic", "balanced")
    try:
        next_idx = (tactics_cycle.index(current_tactic) + 1) % len(tactics_cycle)
    except ValueError:
        next_idx = 0
    new_tactic = tactics_cycle[next_idx]
    draft["dragon_tactic"] = new_tactic
    await query.answer(f"🐉 Taktika: {tactic_names[new_tactic]}")

    await render_march_prep(update, context, terr_id)


async def march_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'shin turi haqida ma'lumot beruvchi callback"""
    query = update.callback_query
    parts = query.data.split(":")
    unit = parts[2] if len(parts) > 2 else ""
    names = {
        "inf": "🛡️ Piyoda",
        "arc": "🏹 Kamonchi",
        "cav": "🐎 Otliq",
        "sp": "🗡️ Nayzachi",
        "spc": "🔥 Maxsus Qo'shin",
        "cat": "🪨 Katapulta (Devorni buzish)",
        "tow": "🪜 Qamal minorasi (Piyodalarni asrash)",
    }
    unit_name = names.get(unit, "Qo'shin")
    await query.answer(f"{unit_name}: Sonni o'zgartirish uchun yonidagi +/- yoki MAX tugmalaridan foydalaning.", show_alert=False)


async def send_custom_march_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan aniq askarlar bilan yurishni boshlash"""
    query = update.callback_query
    parts = query.data.split(":")
    terr_id = int(parts[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            await query.answer("Ma'lumot topilmadi.", show_alert=True)
            return

        # Urush holati tekshiruvi (Sulh davrida hujum bloklanadi)
        war_status = await crud.get_war_status(session)
        if not war_status["is_active"]:
            await query.answer("🕊️ Hozirda Vesterosda sulh davri! Urush rejimi yopiq. Hujum jo'natib bo'lmaydi.", show_alert=True)
            return

        is_allowed, err_msg = can_attack_target(user, terr)
        if not is_allowed:
            await query.answer(err_msg, show_alert=True)
            return

        if user.house_id and terr.owner_house_id and user.house_id != terr.owner_house_id:
            allies = await crud.get_active_alliances_for_house(session, user.house_id)
            allied_ids = {a.house_a_id if a.house_b_id == user.house_id else a.house_b_id for a in allies}
            if terr.owner_house_id in allied_ids:
                await query.answer("❌ Ushbu qal'a rasmiy ittifoqchingizga qarashli!", show_alert=True)
                return

        u_inf = (user.army.infantry if user.army else 0) or 0
        u_arc = (user.army.archers if user.army else 0) or 0
        u_cav = (user.army.cavalry if user.army else 0) or 0
        u_sp = (user.army.spearmen if user.army else 0) or 0
        u_spc = (user.army.special_troops if user.army else 0) or 0
        u_cat = getattr(user.army, 'catapults', 0) or 0
        u_tow = getattr(user.army, 'siege_towers', 0) or 0

        draft = context.user_data.get(f"march_{terr_id}")
        if not draft:
            draft = {
                "infantry": u_inf,
                "archers": u_arc,
                "cavalry": u_cav,
                "spearmen": u_sp,
                "special": u_spc,
                "catapults": u_cat,
                "siege_towers": u_tow,
                "dragon_tactic": "balanced",
            }

        infantry = max(0, min(draft.get("infantry", 0) or 0, u_inf))
        archers = max(0, min(draft.get("archers", 0) or 0, u_arc))
        cavalry = max(0, min(draft.get("cavalry", 0) or 0, u_cav))
        spearmen = max(0, min(draft.get("spearmen", 0) or 0, u_sp))
        special_troops = max(0, min(draft.get("special", 0) or 0, u_spc))
        catapults = max(0, min(draft.get("catapults", 0) or 0, u_cat))
        siege_towers = max(0, min(draft.get("siege_towers", 0) or 0, u_tow))
        total_sent = infantry + archers + cavalry + spearmen + special_troops

        if total_sent <= 0:
            await query.answer("❌ Hujum qilish uchun kamida 1 ta askar tanlang!", show_alert=True)
            return

        await query.answer("🚩 Qo'shin yo'lga chiqdi!")

        # Ajdarni tekshirish
        selected_dr_id = draft.get("dragon_id")
        dragon = None
        if selected_dr_id:
            dragon = await session.get(models.Dragon, selected_dr_id)
            if dragon and dragon.user_id != user.id:
                dragon = None

        can_use_dragon = dragon and dragon.stage in ["baby", "adult"] and dragon.hunger >= 20
        raw_tactic = draft.get("dragon_tactic", "none")
        if not can_use_dragon or raw_tactic not in ["balanced", "walls", "ranged", "frontline"]:
            raw_tactic = "none"
        has_dragon = (raw_tactic != "none" and dragon is not None)
        dragon_tactic = raw_tactic
        dragon_id_to_send = dragon.id if has_dragon else None

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
            special_troops=special_troops,
            catapults=catapults,
            siege_towers=siege_towers,
            character_id=user.characters[0].id if user.characters else None,
            duration_minutes=BASE_MARCH_MINUTES,
            has_dragon=has_dragon,
            dragon_tactic=dragon_tactic,
            dragon_id=dragon_id_to_send,
        )

        # Tozalash
        context.user_data.pop(f"march_{terr_id}", None)
        context.user_data.pop("awaiting_march_input", None)

        # Himoyachi xonadon Lordiga real-time ogohlantirish qarg'asi
        if terr.owner_house_id and terr.owner_house_id != user.house_id:
            target_house = await session.get(models.House, terr.owner_house_id)
            if target_house and target_house.lord_user_id and target_house.lord_user_id != user.telegram_id:
                dragon_text = " 🔥 va BAHAYBAT AJDAR 🐉" if has_dragon else ""
                def_buttons = [
                    [InlineKeyboardButton("⚔️ Harbiy Markaz (Himoyalanish)", callback_data="menu_battle")],
                    [InlineKeyboardButton("🛡️ Qal'aga Shoshilinch Askar Qo'shish", callback_data=f"def_rf_menu:{terr.id}")],
                    [InlineKeyboardButton("🐉 Ajdarni Mudofaaga Joylashtirish", callback_data=f"def_station_dragon:{terr.id}")],
                    [InlineKeyboardButton("🤝 Ittifoqchilarni Chaqirish (SOS)", callback_data=f"def_sos:{terr.id}")],
                ]
                try:
                    await context.bot.send_message(
                        chat_id=target_house.lord_user_id,
                        text=(
                            f"🚨 **QARG'A OGOHLANTIRISHI! QAL'AGA HUJUM BOSHLANDI!**\n\n"
                            f"🏰 **{user.house.emoji} {user.house.name}** armiyasi sizning **{terr.name} ({terr.castle_name})** qal'angiz sari shiddat bilan yurish boshladi!\n"
                            f"⚔️ Hujumchilar: taxminan **{total_sent:,}** askar{dragon_text}\n"
                            f"⏱️ Qamal boshlanishiga: **{BASE_MARCH_MINUTES} daqiqa** qoldi!\n\n"
                            f"🛡️ **MUDOFAA CHORALARI:**\n"
                            f"Zudlik bilan garnizonga o'z armiyangizdan askar safarbar qiling yoki ittifoqchi va vassallardan yordam so'rang!"
                        ),
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(def_buttons),
                    )
                except Exception:
                    pass

            # Himoyachi xonadon Telegram guruhiga signal yuborish
            from core.notifier import notify_house_group
            att_h_name = user.house.name if user.house else "Dushman"
            att_h_emoji = user.house.emoji if user.house else "⚔️"
            dr_html = " 🔥 <b>va Jangovar Drakarys Ajdari!</b>" if has_dragon else ""
            group_war_msg = (
                f"🚨🚨 <b>DIQQAT! QAL'AMIZGA DUSHMAN YURISH BOSHLADI!</b> 🚨🚨\n\n"
                f"⚔️ <b>{html.escape(att_h_emoji)} {html.escape(att_h_name)}</b> qo'shini "
                f"<b>{html.escape(terr.name)}</b> ({html.escape(terr.castle_name)}) qal'amiz sari harakatlanmoqda!\n\n"
                f"📊 <b>Dushman kuchi:</b> ~{total_sent:,} ta askar{dr_html}\n"
                f"⏱️ <b>Yetib kelish vaqti:</b> {BASE_MARCH_MINUTES} daqiqa!\n\n"
                f"🛡️ <i>Barcha xonadon a'zolari zudlik bilan botga kirib, mudofaani kuchaytirsin!</i>"
            )
            asyncio.create_task(notify_house_group(context.application, terr.owner_house_id, group_war_msg, parse_mode="HTML"))

    tactic_names = {
        "balanced": "Yalpi Olovli Bo'ron",
        "walls": "Devorlarni Eritish",
        "ranged": "Merganlarni Yoqish",
    }
    dr_msg = f"\n🐉 Ajdar taktikasi: **{tactic_names.get(dragon_tactic, '')}**" if has_dragon else ""
    special_name = user.house.special_troop_name if user.house and user.house.special_troop_name else "Maxsus Qo'shin"
    spc_str = f"\n• 🔥 {special_name}: **{special_troops:,}**" if special_troops > 0 else ""
    text = (
        f"🚩 **QO'SHIN YURISHGA CHIQDI!**\n\n"
        f"🎯 Nishon: **{terr.name}** ({terr.castle_name})\n"
        f"⚔️ **Safarbar etilgan askarlar:** **{total_sent:,}** ta askar\n"
        f"• 🛡️ Piyoda: **{infantry:,}**\n"
        f"• 🏹 Kamonchi: **{archers:,}**\n"
        f"• 🐎 Otliq: **{cavalry:,}**\n"
        f"• 🗡️ Nayzachi: **{spearmen:,}**{spc_str}{dr_msg}\n\n"
        f"⏱️ Yetib borish vaqti: **{BASE_MARCH_MINUTES} daqiqa**\n\n"
        f"Qamal boshlangach, bot sizga avtomatik jang hisobotini yuboradi!\n"
        f"Harbiy holatni /battle orqali kuzatib boring."
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_main_keyboard())


async def send_march_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Armiyani manzil sari jo'natish"""
    query = update.callback_query

    parts = query.data.split(":")
    terr_id = int(parts[1])
    percent = int(parts[2])
    dragon_tactic = parts[3] if len(parts) > 3 else "none"
    has_dragon = (dragon_tactic != "none")
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            await query.answer("Ma'lumot topilmadi.", show_alert=True)
            return

        # Urush holati tekshiruvi (Sulh davrida hujum bloklanadi)
        war_status = await crud.get_war_status(session)
        if not war_status["is_active"]:
            await query.answer("🕊️ Hozirda Vesterosda sulh davri! Urush rejimi yopiq. Hujum jo'natib bo'lmaydi.", show_alert=True)
            return

        is_allowed, err_msg = can_attack_target(user, terr)
        if not is_allowed:
            await query.answer(err_msg, show_alert=True)
            return

        if user.house_id and terr.owner_house_id and user.house_id != terr.owner_house_id:
            allies = await crud.get_active_alliances_for_house(session, user.house_id)
            allied_ids = {a.house_a_id if a.house_b_id == user.house_id else a.house_b_id for a in allies}
            if terr.owner_house_id in allied_ids:
                await query.answer("❌ Ushbu qal'a rasmiy ittifoqchingizga qarashli!", show_alert=True)
                return

        ratio = percent / 100.0
        u_inf = (user.army.infantry if user.army else 0) or 0
        u_arc = (user.army.archers if user.army else 0) or 0
        u_cav = (user.army.cavalry if user.army else 0) or 0
        u_sp = (user.army.spearmen if user.army else 0) or 0
        u_spc = (user.army.special_troops if user.army else 0) or 0
        u_cat = getattr(user.army, 'catapults', 0) or 0
        u_tow = getattr(user.army, 'siege_towers', 0) or 0

        infantry = int(u_inf * ratio)
        archers = int(u_arc * ratio)
        cavalry = int(u_cav * ratio)
        spearmen = int(u_sp * ratio)
        special = int(u_spc * ratio)
        catapults = int(u_cat * ratio)
        siege_towers = int(u_tow * ratio)

        total_sent = infantry + archers + cavalry + spearmen + special
        if total_sent <= 0:
            await query.answer("❌ Askarlar soni yetarli emas.", show_alert=True)
            return

        await query.answer("🚩 Qo'shin yo'lga chiqdi!")

        # Qalqonni bekor qilish
        user.peace_shield_until = None

        dragon_id_to_send = None
        if has_dragon:
            free_dragons = await crud.get_user_available_dragons(session, user.id)
            if free_dragons:
                dragon_id_to_send = free_dragons[0].id
            else:
                has_dragon = False
                dragon_tactic = "none"

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
            catapults=catapults,
            siege_towers=siege_towers,
            character_id=user.characters[0].id if user.characters else None,
            duration_minutes=BASE_MARCH_MINUTES,
            has_dragon=has_dragon,
            dragon_tactic=dragon_tactic,
            dragon_id=dragon_id_to_send,
        )

        # Himoyachi xonadon Lordiga real-time ogohlantirish qarg'asi
        if terr.owner_house_id and terr.owner_house_id != user.house_id:
            target_house = await session.get(models.House, terr.owner_house_id)
            if target_house and target_house.lord_user_id and target_house.lord_user_id != user.telegram_id:
                dragon_text = " 🔥 va BAHAYBAT AJDAR 🐉" if has_dragon else ""
                def_buttons = [
                    [InlineKeyboardButton("⚔️ Harbiy Markaz (Himoyalanish)", callback_data="menu_battle")],
                    [InlineKeyboardButton("🛡️ Qal'aga Shoshilinch Askar Qo'shish", callback_data=f"def_rf_menu:{terr.id}")],
                    [InlineKeyboardButton("🐉 Ajdarni Mudofaaga Joylashtirish", callback_data=f"def_station_dragon:{terr.id}")],
                    [InlineKeyboardButton("🤝 Ittifoqchilarni Chaqirish (SOS)", callback_data=f"def_sos:{terr.id}")],
                ]
                try:
                    await context.bot.send_message(
                        chat_id=target_house.lord_user_id,
                        text=(
                            f"🚨 **QARG'A OGOHLANTIRISHI! QAL'AGA HUJUM BOSHLANDI!**\n\n"
                            f"🏰 **{user.house.emoji} {user.house.name}** armiyasi sizning **{terr.name} ({terr.castle_name})** qal'angiz sari shiddat bilan yurish boshladi!\n"
                            f"⚔️ Hujumchilar: taxminan **{total_sent:,}** askar{dragon_text}\n"
                            f"⏱️ Qamal boshlanishiga: **{BASE_MARCH_MINUTES} daqiqa** qoldi!\n\n"
                            f"🛡️ **MUDOFAA CHORALARI:**\n"
                            f"Zudlik bilan garnizonga o'z armiyangizdan askar safarbar qiling yoki ittifoqchi va vassallardan yordam so'rang!"
                        ),
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(def_buttons),
                    )
                except Exception:
                    pass

            # Himoyachi xonadon Telegram guruhiga signal yuborish
            from core.notifier import notify_house_group
            att_h_name = user.house.name if user.house else "Dushman"
            att_h_emoji = user.house.emoji if user.house else "⚔️"
            dr_html = " 🔥 <b>va Jangovar Drakarys Ajdari!</b>" if has_dragon else ""
            group_war_msg = (
                f"🚨🚨 <b>DIQQAT! QAL'AMIZGA DUSHMAN YURISH BOSHLANDI!</b> 🚨🚨\n\n"
                f"⚔️ <b>{html.escape(att_h_emoji)} {html.escape(att_h_name)}</b> qo'shini "
                f"<b>{html.escape(terr.name)}</b> ({html.escape(terr.castle_name)}) qal'amiz sari harakatlanmoqda!\n\n"
                f"📊 <b>Dushman kuchi:</b> ~{total_sent:,} ta askar{dr_html}\n"
                f"⏱️ <b>Yetib kelish vaqti:</b> {BASE_MARCH_MINUTES} daqiqa!\n\n"
                f"🛡️ <i>Barcha xonadon a'zolari zudlik bilan botga kirib, mudofaani kuchaytirsin!</i>"
            )
            asyncio.create_task(notify_house_group(context.application, terr.owner_house_id, group_war_msg, parse_mode="HTML"))

    dr_msg = "\n🐉 Ajdarga Drakarys buyrug'i berildi!" if has_dragon else ""
    text = (
        f"🚩 **QO'SHIN YURISHGA CHIQDI!**\n\n"
        f"🎯 Nishon: **{terr.name}** ({terr.castle_name})\n"
        f"⚔️ Safarbar etilgan askarlar: **{total_sent:,}** ta{dr_msg}\n"
        f"⏱️ Yetib borish vaqti: **{BASE_MARCH_MINUTES} daqiqa**\n\n"
        f"Qamal boshlangach, bot sizga avtomatik jang hisobotini yuboradi!\n"
        f"Harbiy holatni /battle orqali kuzatib boring."
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_main_keyboard())


async def def_rf_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Himoyachi uchun garnizon kuchaytirish menyusi"""
    query = update.callback_query
    await query.answer()

    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            await query.answer("Ma'lumot topilmadi.", show_alert=True)
            return

        total_army = (
            user.army.infantry + user.army.archers + user.army.cavalry + user.army.spearmen
        )

        is_lord = (
            user.house
            and terr.owner_house_id == user.house_id
            and (
                user.house.lord_user_id == user.telegram_id
                or user.rank == "king"
            )
        )

        buttons = [
            [
                InlineKeyboardButton("🛡️ +50 Askar", callback_data=f"def_send_rf:{terr.id}:50"),
                InlineKeyboardButton("🛡️ +100 Askar", callback_data=f"def_send_rf:{terr.id}:100"),
            ],
            [
                InlineKeyboardButton("🛡️ +250 Askar", callback_data=f"def_send_rf:{terr.id}:250"),
                InlineKeyboardButton("🛡️ +500 Askar", callback_data=f"def_send_rf:{terr.id}:500"),
            ],
            [
                InlineKeyboardButton("🛡️ Barcha Askarlarni Joylashtirish", callback_data=f"def_send_rf:{terr.id}:all"),
            ],
        ]

        if is_lord:
            buttons.append([
                InlineKeyboardButton("↩️ Garnizondan Askarlarni Qaytarish", callback_data=f"def_withdraw_rf:{terr.id}"),
            ])

        buttons.extend([
            [
                InlineKeyboardButton("✍️ Askar Sonini Qo'lda Kiritish", callback_data=f"def_custom_rf:{terr.id}"),
            ],
            [
                InlineKeyboardButton("🔙 Qal'aga Qaytish", callback_data=f"my_c_detail:{terr.id}"),
            ],
        ])

        text = (
            f"🛡️ **QAL'AGA ASKAR JOYLASHTIRISH: {terr.name.upper()}**\n\n"
            f"🏰 **Qal'a garnizoni hozir:**\n"
            f"• 🛡️ Piyoda: {terr.garrison_infantry:,}\n"
            f"• 🏹 Kamonchi: {terr.garrison_archers:,}\n"
            f"• 🐎 Otliq: {terr.garrison_cavalry:,}\n"
            f"• 🗡️ Nayzachi: {terr.garrison_spearmen:,}\n"
            f"🎯 Jami: **{terr.garrison_infantry + terr.garrison_archers + terr.garrison_cavalry + terr.garrison_spearmen:,}** askar\n\n"
            f"👥 **Sizning shaxsiy armiyangiz:** **{total_army:,}** askar\n\n"
            f"Qal'a mudofaasiga qancha askar joylashtirmoqchisiz?"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def def_send_rf_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'a garnizoniga askarlarni joylashtirish"""
    query = update.callback_query

    parts = query.data.split(":")
    terr_id = int(parts[1])
    count_type = parts[2]
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            await query.answer("Ma'lumot topilmadi.", show_alert=True)
            return

        ok, msg, _ = await crud.send_castle_reinforcements_proportional(
            session=session,
            user_id=user.id,
            target_territory_id=terr.id,
            count=None if count_type == "all" else int(count_type),
            send_all=(count_type == "all"),
        )

    await query.answer(msg, show_alert=True)
    if ok:
        if terr.owner_house_id == user.house_id:
            from handlers.map_handler import show_my_castle_detail
            await show_my_castle_detail(query, user_id, terr_id)
        else:
            await def_rf_menu_callback(update, context)


async def def_sos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xonadon va ittifoqchilarga shoshilinch SOS qarg'asi uchirish"""
    query = update.callback_query
    await query.answer("📡 Ittifoqchilar va xonadon a'zolariga SOS qarg'alari uchirildi!", show_alert=True)

    terr_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            return

        # Xonadon a'zolariga yuborish
        members_res = await session.execute(
            select(models.User).where(
                models.User.house_id == user.house_id,
                models.User.telegram_id != user.telegram_id,
            ).limit(10)
        )
        members = members_res.scalars().all()

        sos_text = (
            f"🚨 **SHOSHILINCH SOS CHAQIRUV!**\n\n"
            f"🏰 Xonadonimizning **{terr.name} ({terr.castle_name})** qal'asiga dushman yurishi boshlandi!\n"
            f"⏱️ Qamal boshlanishiga sanoqli daqiqalar qoldi!\n\n"
            f"Lord {user.character_name} barcha ittifoqchi va vassallardan zudlik bilan yordam so'ramoqda!"
        )
        sos_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛡️ Qal'aga Yordam Yuborish", callback_data=f"def_rf_menu:{terr.id}")]
        ])

        for m in members:
            try:
                await context.bot.send_message(
                    chat_id=m.telegram_id,
                    text=sos_text,
                    parse_mode="Markdown",
                    reply_markup=sos_markup,
                )
            except Exception:
                pass


async def defend_siege_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'aga bo'layotgan faol qamalni ko'rish va himoyalanish choralarini ko'rish"""
    query = update.callback_query
    await query.answer()
    march_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        march = await session.get(models.BattleMarch, march_id)
        if not march or march.status != "marching":
            await query.answer("Qamal yakunlangan yoki bekor qilingan.", show_alert=True)
            await show_battle_hub(query, user_id, is_message=False)
            return

        terr = await session.get(models.Territory, march.target_territory_id)
        attacker = await session.get(models.User, march.attacker_user_id)
        att_house = await session.get(models.House, attacker.house_id) if (attacker and attacker.house_id) else None

        rem_sec = max(0, int((march.arrival_time - datetime.utcnow()).total_seconds()))
        att_name = attacker.characters[0].name if (attacker and attacker.characters) else (attacker.full_name if attacker else "Dushman")
        att_house_name = f"{att_house.emoji} {att_house.name}" if att_house else "Noma'lum"

        tot_enemy = march.infantry + march.archers + march.cavalry + march.spearmen + march.special_troops
        enemy_dragon_str = "🔥 Bor (Drakarys xavfi!)" if march.has_dragon else "Yo'q"

        # Qal'amiz garnizoni va mudofaasi
        garr_total = terr.garrison_infantry + terr.garrison_archers + terr.garrison_cavalry + terr.garrison_spearmen
        st_dragon = crud.get_stationed_dragon_info(terr)
        def_dragon_str = f"🔥 {st_dragon['dragon_name']} (Kuch: {st_dragon['power']})" if st_dragon else "Yo'q"

        buttons = [
            [InlineKeyboardButton("🛡️ Shoshilinch Askar Joylashtirish", callback_data=f"def_rf_menu:{terr.id}")],
            [InlineKeyboardButton("🐉 Ajdarni Mudofaaga Joylashtirish", callback_data=f"def_station_dragon:{terr.id}")],
            [InlineKeyboardButton("🤝 Xonadonga SOS Chaqiruvi", callback_data=f"def_sos:{terr.id}")],
            [InlineKeyboardButton("🔄 Qamal Holatini Yangilash", callback_data=f"defend_siege:{march.id}")],
            [InlineKeyboardButton("🔙 Harbiy Markazga Qaytish", callback_data="menu_battle")],
        ]

        text = (
            f"🚨 **FAOL QAMAL VA QAL'A HIMOYASI!**\n\n"
            f"🏰 Qal'a: **{terr.name} ({terr.castle_name})**\n"
            f"⏱️ Dushman yetib kelishiga: **{rem_sec // 60} daqiqa {rem_sec % 60} soniya** qoldi!\n\n"
            f"⚔️ **DUSHMAN QO'SHINI:**\n"
            f"• Qo'mondon: **{escape_md(att_name)}** ({escape_md(att_house_name)})\n"
            f"• Hujumchilar: taxminan **{tot_enemy:,}** askar\n"
            f"• Ajdar Hujumi: **{enemy_dragon_str}**\n\n"
            f"🛡️ **QAL'AMIZ MUDOFAASI:**\n"
            f"• Qal'a Devori: **{terr.defense}** ball\n"
            f"• Garnizon: **{garr_total:,}** askar (🛡️{terr.garrison_infantry} | 🏹{terr.garrison_archers} | 🐎{terr.garrison_cavalry} | 🗡️{terr.garrison_spearmen})\n"
            f"• Mudofaadagi Ajdar: **{def_dragon_str}**\n\n"
            f"Qal'a dushmanga boy berilmasligi uchun zudlik bilan himoyani kuchaytiring!"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def march_custom_req_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'lda kiritish uchun so'rov chiqarish"""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    terr_id = int(parts[1])

    context.user_data["awaiting_march_input"] = {"terr_id": terr_id}

    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

    if not user or not terr:
        return

    special_name = user.house.special_troop_name if user.house and user.house.special_troop_name else "Maxsus Qo'shin"

    buttons = [
        [InlineKeyboardButton("🔙 Sozlamalarga Qaytish", callback_data=f"march_prep:{terr_id}")],
    ]
    text = (
        f"✍️ **QO'SHIN TARKIBINI QO'LDA KIRITISH**\n\n"
        f"🏰 Nishon: **{terr.name} ({terr.castle_name})**\n\n"
        f"Qal'aga qancha askar yubormoqchisiz? Quyidagi formatlardan birida yozing:\n\n"
        f"1️⃣ **Ketma-ket sonlar probel bilan (Tavsiya etiladi):**\n"
        f"`500 300 150 200 50`\n"
        f"*(Tartibi: Piyoda Kamonchi Otliq Nayzachi Maxsus)*\n\n"
        f"2️⃣ **Qisqartma harflar bilan:**\n"
        f"`p 500 k 300 o 150 n 200 m 50`\n"
        f"*(p=piyoda, k=kamonchi, o=otliq, n=nayzachi, m=maxsus)*\n\n"
        f"3️⃣ **Yoki umumiy bitta son:**\n"
        f"`1000` *(mavjud qo'shiningizga qarab mutanosib taqsimlanadi)*\n\n"
        f"📊 **Sizdagi mavjud armiya:**\n"
        f"• 🛡️ Piyoda: {user.army.infantry:,}\n"
        f"• 🏹 Kamonchi: {user.army.archers:,}\n"
        f"• 🐎 Otliq: {user.army.cavalry:,}\n"
        f"• 🗡️ Nayzachi: {user.army.spearmen:,}\n"
        f"• 🔥 {special_name}: {user.army.special_troops:,}\n\n"
        f"Iltimos, sonlarni pastdagi xabar maydoniga yozib yuboring:"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def def_custom_rf_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Garnizonga qo'lda askar kiritish so'rovi"""
    query = update.callback_query
    await query.answer()
    terr_id = int(query.data.split(":")[1])
    context.user_data["awaiting_rf_input"] = {"terr_id": terr_id}

    buttons = [
        [InlineKeyboardButton("🔙 Bekor Qilish", callback_data=f"def_rf_menu:{terr_id}")],
    ]
    text = (
        "✍️ **GARNIZONGA QO'SHILADIGAN ASKARLAR SONI**\n\n"
        "Qal'a mudofaasiga qancha askaringizni joylashtirmoqchisiz?\n"
        "Iltimos, sonni xabar sifatida yozib yuboring:\n\n"
        "*(Masalan: `150` yoki `500`)*"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def handle_battle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yurish yoki garnizon uchun kiritilgan raqamli xabarni qabul qilish"""
    if not update.message or not update.message.text:
        return

    # Agar foydalanuvchi qahramon nomini kiritayotgan bo'lsa
    if context.user_data.get("awaiting_custom_name"):
        from handlers.start_handler import handle_custom_name_input
        await handle_custom_name_input(update, context)
        return

    # Agar foydalanuvchi askar sonini qo'lda kiritayotgan bo'lsa
    if "awaiting_recruit_input" in context.user_data:
        from handlers.army_handler import handle_recruit_text_input
        await handle_recruit_text_input(update, context)
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id

    # 1. Harbiy yurish uchun askar kiritish
    if "awaiting_march_input" in context.user_data:
        data = context.user_data.get("awaiting_march_input")
        terr_id = data["terr_id"]

        async with AsyncSessionLocal() as session:
            user = await crud.get_user_with_relations(session, user_id)
            terr = await crud.get_territory_by_id(session, terr_id)
            if not user or not terr:
                context.user_data.pop("awaiting_march_input", None)
                await update.message.reply_text("❌ Ma'lumot topilmadi.")
                return

            parsed = parse_march_troops(text, user.army)
            if not parsed or parsed["total"] <= 0:
                await update.message.reply_text(
                    "❌ Askar soni to'g'ri kiritilmadi!\n\n"
                    "Iltimos, sonlarni quyidagi formatlardan birida yozing:\n"
                    "• `500 300 150 200 50` (Piyoda Kamonchi Otliq Nayzachi Maxsus)\n"
                    "• `p 500 k 300 o 150 n 200 m 50`\n"
                    "• `1000` (Umumiy askarlar soni)",
                    parse_mode="Markdown"
                )
                return

            # Draftni yangilaymiz
            context.user_data.pop("awaiting_march_input", None)
            draft = context.user_data.setdefault(f"march_{terr_id}", {})
            draft["infantry"] = parsed["infantry"]
            draft["archers"] = parsed["archers"]
            draft["cavalry"] = parsed["cavalry"]
            draft["spearmen"] = parsed["spearmen"]
            draft["special"] = parsed["special"]

            tot = parsed["total"]
            special_name = user.house.special_troop_name if user.house and user.house.special_troop_name else "Maxsus Qo'shin"
            buttons = [
                [InlineKeyboardButton(f"🚀 HUJUMNI BOSHLASH ({tot:,} askar)", callback_data=f"send_custom_march:{terr_id}")],
                [InlineKeyboardButton("⚙️ Qo'shinni Qayta Sozlash", callback_data=f"march_prep:{terr_id}")],
                [InlineKeyboardButton("🔙 Bekor Qilish", callback_data=f"view_terr:{terr_id}")],
            ]
            msg = (
                f"✅ **QO'SHIN TARKIBI QABUL QILINDI!**\n\n"
                f"🏰 Nishon: **{terr.name} ({terr.castle_name})**\n\n"
                f"👥 **Siz tanlagan askarlar:**\n"
                f"• 🛡️ Piyoda: **{parsed['infantry']:,}** / {user.army.infantry:,}\n"
                f"• 🏹 Kamonchi: **{parsed['archers']:,}** / {user.army.archers:,}\n"
                f"• 🐎 Otliq: **{parsed['cavalry']:,}** / {user.army.cavalry:,}\n"
                f"• 🗡️ Nayzachi: **{parsed['spearmen']:,}** / {user.army.spearmen:,}\n"
                f"• 🔥 {special_name}: **{parsed['special']:,}** / {user.army.special_troops:,}\n\n"
                f"🎯 Jami: **{tot:,}** ta askar\n"
                f"⏱️ Yurish vaqti: **{BASE_MARCH_MINUTES} daqiqa**\n\n"
                f"Hujumni darhol boshlaysizmi yoki qayta sozlashni xohlaysizmi?"
            )
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            return

    # 2. Garnizonga askar kiritish
    if "awaiting_rf_input" in context.user_data:
        data = context.user_data.pop("awaiting_rf_input")
        terr_id = data["terr_id"]

        async with AsyncSessionLocal() as session:
            if text.lower() in ["all", "hamma", "barchasi"]:
                ok, msg, _ = await crud.send_castle_reinforcements_proportional(
                    session=session,
                    user_id=user_id,
                    target_territory_id=terr_id,
                    send_all=True,
                )
            elif text.isdigit():
                ok, msg, _ = await crud.send_castle_reinforcements_proportional(
                    session=session,
                    user_id=user_id,
                    target_territory_id=terr_id,
                    count=int(text),
                )
            else:
                ok, msg = False, "❌ Noto'g'ri qiymat! Iltimos, son (masalan: `100`) yoki 'all' deb yozing."

        buttons = [
            [InlineKeyboardButton("🏰 Qal'aga Qaytish", callback_data=f"my_c_detail:{terr_id}")],
        ]
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # 3. Garnizondan askar qaytarib olish
    if "awaiting_with_input" in context.user_data:
        data = context.user_data.pop("awaiting_with_input")
        terr_id = data["terr_id"]

        async with AsyncSessionLocal() as session:
            if text.lower() in ["all", "hamma", "barchasi"]:
                ok, msg, _ = await crud.withdraw_castle_reinforcements(
                    session=session,
                    user_id=user_id,
                    territory_id=terr_id,
                    withdraw_all=True,
                )
            elif text.isdigit():
                ok, msg, _ = await crud.withdraw_castle_reinforcements(
                    session=session,
                    user_id=user_id,
                    territory_id=terr_id,
                    count=int(text),
                )
            else:
                ok, msg = False, "❌ Noto'g'ri qiymat! Iltimos, son (masalan: `100`) yoki 'all' deb yozing."

        buttons = [
            [InlineKeyboardButton("🏰 Qal'aga Qaytish", callback_data=f"my_c_detail:{terr_id}")],
        ]
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return


def register_battle_handlers(app):
    app.add_handler(CommandHandler("battle", battle_command))
    app.add_handler(CommandHandler("war", battle_command))
    app.add_handler(CallbackQueryHandler(battle_callback, pattern="^menu_battle$"))
    app.add_handler(CallbackQueryHandler(march_prep_callback, pattern="^march_prep:"))
    app.add_handler(CallbackQueryHandler(march_custom_req_callback, pattern="^march_custom_req:"))
    app.add_handler(CallbackQueryHandler(march_adj_callback, pattern="^m_adj:"))
    app.add_handler(CallbackQueryHandler(march_preset_callback, pattern="^m_pre:"))
    app.add_handler(CallbackQueryHandler(march_select_dragon_callback, pattern="^m_sel_drg:"))
    app.add_handler(CallbackQueryHandler(march_dragon_callback, pattern="^m_drg:"))
    app.add_handler(CallbackQueryHandler(march_info_callback, pattern="^m_info:"))
    app.add_handler(CallbackQueryHandler(send_custom_march_callback, pattern="^send_custom_march:"))
    app.add_handler(CallbackQueryHandler(send_march_callback, pattern="^send_march:"))
    app.add_handler(CallbackQueryHandler(def_rf_menu_callback, pattern="^def_rf_menu:"))
    app.add_handler(CallbackQueryHandler(def_custom_rf_callback, pattern="^def_custom_rf:"))
    app.add_handler(CallbackQueryHandler(def_send_rf_callback, pattern="^def_send_rf:"))
    app.add_handler(CallbackQueryHandler(def_sos_callback, pattern="^def_sos:"))
    app.add_handler(CallbackQueryHandler(defend_siege_callback, pattern="^defend_siege:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_battle_text_input))
