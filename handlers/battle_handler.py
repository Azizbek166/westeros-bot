import json
import re
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
        if user.house_id:
            terr_ids_res = await session.execute(
                select(models.Territory.id).where(models.Territory.owner_house_id == user.house_id)
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
                        incoming_text += f"• 🚨 {dr_icon}**{t_name}** ga hujum kelmoqda: {rem_sec // 60} daq {rem_sec % 60} soniya qoldi!\n"

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
                defense_buttons.append([
                    InlineKeyboardButton(f"🚨 {t_name} Himoyasiga O'tish! ({rem_sec // 60}d {rem_sec % 60}s)", callback_data=f"defend_siege:{im.id}")
                ])

        buttons = []
        if defense_buttons:
            buttons.extend(defense_buttons)

        is_lord = user.house and ((user.house.lord_user_id == user.telegram_id) or user.rank == "king")
        if is_lord:
            buttons.append([InlineKeyboardButton("📢 Xonadonga Safarbarlik Chaqiruvi (SOS)", callback_data="call_to_arms_broadcast")])

        buttons.append([InlineKeyboardButton("🗺️ Qal'a Tanlash (Xaritaga o'tish)", callback_data="menu_map")])
        buttons.append([InlineKeyboardButton("🔄 Vaqtni Yangilash", callback_data="menu_battle")])
        buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])

        text = (
            f"🛡️ **HARBIY AMALIYOTLAR MARKAZI**\n\n"
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

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        terr = await crud.get_territory_by_id(session, terr_id)

        if not user or not terr:
            if query:
                await query.answer("Hudud topilmadi.", show_alert=True)
            return

        is_allowed, err_msg = can_attack_target(user, terr)
        if not is_allowed:
            if query:
                await query.answer(err_msg, show_alert=True)
                await query.edit_message_text(
                    f"{err_msg}\n\nO'z xonadoningiz qal'asiga hujum qilib bo'lmaydi. Xaritadan dushman xonadon qal'asini tanlang:",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗺️ Xaritaga Qaytish", callback_data="menu_map")]])
                )
            return

        total_army = (
            user.army.infantry
            + user.army.archers
            + user.army.cavalry
            + user.army.spearmen
            + user.army.special_troops
        )

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
                await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=markup)
            return

        dragon = await crud.get_user_dragon(session, user.id)
        can_use_dragon = dragon and dragon.stage in ["baby", "adult"] and dragon.hunger >= 20

        special_name = user.house.special_troop_name if user.house and user.house.special_troop_name else "Maxsus Qo'shin"

        draft_key = f"march_{terr.id}"
        if draft_key not in context.user_data:
            context.user_data[draft_key] = {
                "infantry": user.army.infantry,
                "archers": user.army.archers,
                "cavalry": user.army.cavalry,
                "spearmen": user.army.spearmen,
                "special": user.army.special_troops,
                "dragon_tactic": "balanced" if can_use_dragon else "none",
            }

        draft = context.user_data[draft_key]
        draft["infantry"] = max(0, min(draft.get("infantry", user.army.infantry), user.army.infantry))
        draft["archers"] = max(0, min(draft.get("archers", user.army.archers), user.army.archers))
        draft["cavalry"] = max(0, min(draft.get("cavalry", user.army.cavalry), user.army.cavalry))
        draft["spearmen"] = max(0, min(draft.get("spearmen", user.army.spearmen), user.army.spearmen))
        draft["special"] = max(0, min(draft.get("special", user.army.special_troops), user.army.special_troops))
        if not can_use_dragon:
            draft["dragon_tactic"] = "none"

        sel_inf = draft["infantry"]
        sel_arc = draft["archers"]
        sel_cav = draft["cavalry"]
        sel_sp = draft["spearmen"]
        sel_spc = draft["special"]
        total_selected = sel_inf + sel_arc + sel_cav + sel_sp + sel_spc

        tactic = draft.get("dragon_tactic", "none")
        tactic_display = {
            "balanced": "🔥 Yalpi Olovli Bo'ron",
            "walls": "🔥 Devorlarni Eritish",
            "ranged": "🔥 Merganlarni Yoqish",
            "none": "❌ Ajdarsiz",
        }.get(tactic, "❌ Ajdarsiz")

        dragon_info = ""
        if can_use_dragon:
            dragon_info = (
                f"🐉 **AJDARINGIZ JANGGA TAYYOR:**\n"
                f"• {dragon.name} ({dragon.stage.title()}) | Kuch: **{dragon.power}**⚡ | Qorin: **{dragon.hunger}%**🍗\n"
                f"• Drakarys taktikasi: **{tactic_display}**\n\n"
            )
        elif dragon:
            dragon_info = f"⚠️ *Ajdaringiz ({dragon.name}) och yoki tuxumda bo'lgani uchun qatnashmaydi.*\n\n"

        text = (
            f"⚔️ **HARBIY YURISH REJASI: {terr.name.upper()}**\n\n"
            f"🏰 Nishon: **{terr.castle_name}** ({terr.region})\n"
            f"⏱️ Yurish vaqti: **{BASE_MARCH_MINUTES} daqiqa**\n\n"
            f"📊 **QO'SHIN TARKIBI (Tanlangan / Mavjud):**\n"
            f"• 🛡️ Piyoda: **{sel_inf:,}** / {user.army.infantry:,}\n"
            f"• 🏹 Kamonchi: **{sel_arc:,}** / {user.army.archers:,}\n"
            f"• 🐎 Otliq: **{sel_cav:,}** / {user.army.cavalry:,}\n"
            f"• 🗡️ Nayzachi: **{sel_sp:,}** / {user.army.spearmen:,}\n"
            f"• 🔥 {special_name}: **{sel_spc:,}** / {user.army.special_troops:,}\n\n"
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
            [
                InlineKeyboardButton("✍️ Aniq Sonlarni Qo'lda Yozish", callback_data=f"march_custom_req:{terr.id}"),
            ],
        ]

        if can_use_dragon:
            buttons.append([
                InlineKeyboardButton(f"🐉 Ajdar Taktikasi: {tactic_display} 🔄", callback_data=f"m_drg:{terr.id}")
            ])

        buttons.append([
            InlineKeyboardButton(f"🚀 HUJUMNI BOSHLASH ({total_selected:,} askar)", callback_data=f"send_custom_march:{terr.id}")
        ])
        buttons.append([
            InlineKeyboardButton("🔙 Bekor Qilish", callback_data=f"view_terr:{terr.id}")
        ])

        reply_markup = InlineKeyboardMarkup(buttons)
        if query:
            try:
                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    pass
        elif update.message:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def march_prep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hujumga tayyorgarlik ekrani"""
    query = update.callback_query
    terr_id = int(query.data.split(":")[1])
    await query.answer()
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
            "inf": user.army.infantry,
            "arc": user.army.archers,
            "cav": user.army.cavalry,
            "sp": user.army.spearmen,
            "spc": user.army.special_troops,
        }
        unit_key_map = {
            "inf": "infantry",
            "arc": "archers",
            "cav": "cavalry",
            "sp": "spearmen",
            "spc": "special",
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
            "dragon_tactic": "balanced",
        })

        curr_val = draft.get(draft_key, max_val)

        if action in ["+100", "+25"]:
            delta = int(action)
            draft[draft_key] = min(max_val, curr_val + delta)
            await query.answer(f"{action} ({draft[draft_key]}/{max_val})")
        elif action in ["-100", "-25"]:
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
        await query.answer(f"{pct}% ga sozlandi")

    await render_march_prep(update, context, terr_id)


async def march_dragon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdar jangovar taktikasini o'zgartirish"""
    query = update.callback_query
    parts = query.data.split(":")
    terr_id = int(parts[1])

    tactics_cycle = ["balanced", "walls", "ranged", "none"]
    tactic_names = {
        "balanced": "Yalpi Olovli Bo'ron",
        "walls": "Devorlarni Eritish",
        "ranged": "Merganlarni Yoqish",
        "none": "Ajdarsiz",
    }

    draft = context.user_data.setdefault(f"march_{terr_id}", {})
    current_tactic = draft.get("dragon_tactic", "balanced")
    try:
        next_idx = (tactics_cycle.index(current_tactic) + 1) % len(tactics_cycle)
    except ValueError:
        next_idx = 0
    new_tactic = tactics_cycle[next_idx]
    draft["dragon_tactic"] = new_tactic
    await query.answer(f"🐉 Ajdar: {tactic_names[new_tactic]}")

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

        is_allowed, err_msg = can_attack_target(user, terr)
        if not is_allowed:
            await query.answer(err_msg, show_alert=True)
            return

        draft = context.user_data.get(f"march_{terr_id}")
        if not draft:
            draft = {
                "infantry": user.army.infantry,
                "archers": user.army.archers,
                "cavalry": user.army.cavalry,
                "spearmen": user.army.spearmen,
                "special": user.army.special_troops,
                "dragon_tactic": "balanced",
            }

        infantry = max(0, min(draft.get("infantry", 0), user.army.infantry))
        archers = max(0, min(draft.get("archers", 0), user.army.archers))
        cavalry = max(0, min(draft.get("cavalry", 0), user.army.cavalry))
        spearmen = max(0, min(draft.get("spearmen", 0), user.army.spearmen))
        special_troops = max(0, min(draft.get("special", 0), user.army.special_troops))
        total_sent = infantry + archers + cavalry + spearmen + special_troops

        if total_sent <= 0:
            await query.answer("❌ Hujum qilish uchun kamida 1 ta askar tanlang!", show_alert=True)
            return

        await query.answer("🚩 Qo'shin yo'lga chiqdi!")

        # Ajdarni tekshirish
        dragon = await crud.get_user_dragon(session, user.id)
        can_use_dragon = dragon and dragon.stage in ["baby", "adult"] and dragon.hunger >= 20
        raw_tactic = draft.get("dragon_tactic", "none")
        if not can_use_dragon or raw_tactic not in ["balanced", "walls", "ranged"]:
            raw_tactic = "none"
        has_dragon = (raw_tactic != "none")
        dragon_tactic = raw_tactic

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
            character_id=user.characters[0].id if user.characters else None,
            duration_minutes=BASE_MARCH_MINUTES,
            has_dragon=has_dragon,
            dragon_tactic=dragon_tactic,
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

        ratio = percent / 100.0
        infantry = int(user.army.infantry * ratio)
        archers = int(user.army.archers * ratio)
        cavalry = int(user.army.cavalry * ratio)
        spearmen = int(user.army.spearmen * ratio)
        special = int(user.army.special_troops * ratio)

        total_sent = infantry + archers + cavalry + spearmen + special
        if total_sent <= 0:
            await query.answer("❌ Askarlar soni yetarli emas.", show_alert=True)
            return

        await query.answer("🚩 Qo'shin yo'lga chiqdi!")

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
            has_dragon=has_dragon,
            dragon_tactic=dragon_tactic,
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
    """Himoyachi uchun tezkor garnizon kuchaytirish menyusi"""
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

        buttons = [
            [InlineKeyboardButton("🛡️ 50 ta Askar Yuborish", callback_data=f"def_send_rf:{terr.id}:50")],
            [InlineKeyboardButton("🛡️ 100 ta Askar Yuborish", callback_data=f"def_send_rf:{terr.id}:100")],
            [InlineKeyboardButton("🛡️ 250 ta Askar Yuborish", callback_data=f"def_send_rf:{terr.id}:250")],
            [InlineKeyboardButton("🛡️ Barcha Askarlarni Safarbar Qilish", callback_data=f"def_send_rf:{terr.id}:all")],
            [InlineKeyboardButton("✍️ Askar Sonini Qo'lda Kiritish", callback_data=f"def_custom_rf:{terr.id}")],
            [InlineKeyboardButton("🔙 Qal'aga Qaytish", callback_data=f"view_terr:{terr.id}")],
        ]

        text = (
            f"🛡️ **QAL'ANI HIMOYA QILISH: {terr.name.upper()}**\n\n"
            f"🏰 Qal'a garnizoni hozir: {terr.garrison_infantry + terr.garrison_archers + terr.garrison_cavalry + terr.garrison_spearmen:,} askar\n"
            f"👥 Sizning shaxsiy armiyangiz: **{total_army:,}** askar\n\n"
            f"Dushman yetib kelguncha qal'a garnizoniga qo'shiladigan askar sonini tanlang:"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def def_send_rf_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qal'a garnizoniga shoshilinch yordam askarlarini kiritish"""
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

        total_army = (
            user.army.infantry + user.army.archers + user.army.cavalry + user.army.spearmen
        )

        if total_army <= 0:
            await query.answer("❌ Sizda yuborish uchun bo'sh askar yo'q!", show_alert=True)
            return

        if count_type == "all":
            send_count = total_army
        else:
            send_count = min(int(count_type), total_army)

        ratio = send_count / float(total_army) if total_army > 0 else 0
        infantry = int(user.army.infantry * ratio)
        archers = int(user.army.archers * ratio)
        cavalry = int(user.army.cavalry * ratio)
        spearmen = int(user.army.spearmen * ratio)

        ok, msg = await crud.send_castle_reinforcements(
            session=session,
            user_id=user.id,
            target_territory_id=terr.id,
            infantry=infantry,
            archers=archers,
            cavalry=cavalry,
            spearmen=spearmen,
        )

    await query.answer(msg, show_alert=True)
    if ok:
        await show_battle_hub(query, user_id, is_message=False)


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
    if "awaiting_rf_input" in context.user_data and text.isdigit():
        data = context.user_data.pop("awaiting_rf_input")
        terr_id = data["terr_id"]
        count = int(text)

        async with AsyncSessionLocal() as session:
            user = await crud.get_user_with_relations(session, user_id)
            terr = await crud.get_territory_by_id(session, terr_id)
            if not user or not terr:
                return

            total_army = (
                user.army.infantry + user.army.archers + user.army.cavalry + user.army.spearmen
            )
            if count <= 0 or count > total_army:
                await update.message.reply_text(f"❌ Noto'g'ri miqdor! Sizda jami {total_army:,} ta askar mavjud.")
                return

            ratio = count / total_army if total_army > 0 else 0
            infantry = min(user.army.infantry, int(user.army.infantry * ratio))
            archers = min(user.army.archers, int(user.army.archers * ratio))
            cavalry = min(user.army.cavalry, int(user.army.cavalry * ratio))
            spearmen = min(user.army.spearmen, int(user.army.spearmen * ratio))

            rem = count - (infantry + archers + cavalry + spearmen)
            if rem > 0 and user.army.infantry >= infantry + rem:
                infantry += rem

            tot_sent = infantry + archers + cavalry + spearmen
            user.army.infantry -= infantry
            user.army.archers -= archers
            user.army.cavalry -= cavalry
            user.army.spearmen -= spearmen

            terr.garrison_infantry += infantry
            terr.garrison_archers += archers
            terr.garrison_cavalry += cavalry
            terr.garrison_spearmen += spearmen
            user.prestige += max(10, tot_sent // 5)
            await session.commit()

            await update.message.reply_text(
                f"✅ **GARNIZON KUCHAYTIRILDI!**\n\n"
                f"🏰 **{terr.name}** qal'asi mudofaasiga +{tot_sent:,} askar qo'shildi!\n"
                f"Qal'a jami garnizoni: {terr.garrison_infantry + terr.garrison_archers + terr.garrison_cavalry + terr.garrison_spearmen:,} askar."
            )
            return


def register_battle_handlers(app):
    app.add_handler(CommandHandler("battle", battle_command))
    app.add_handler(CommandHandler("war", battle_command))
    app.add_handler(CallbackQueryHandler(battle_callback, pattern="^menu_battle$"))
    app.add_handler(CallbackQueryHandler(march_prep_callback, pattern="^march_prep:"))
    app.add_handler(CallbackQueryHandler(march_custom_req_callback, pattern="^march_custom_req:"))
    app.add_handler(CallbackQueryHandler(march_adj_callback, pattern="^m_adj:"))
    app.add_handler(CallbackQueryHandler(march_preset_callback, pattern="^m_pre:"))
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
