from __future__ import annotations
import json
import random
import logging
import asyncio
import html
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from database import models, AsyncSessionLocal, crud
from core.battle_engine import calculate_battle
from core.economy_engine import process_hourly_tick
from core.leveling import check_user_level_up
from core.notifier import notify_house_group, notify_owner
from data.artifacts_data import ARTIFACTS_DATA
from config import COMMUNITY_CHANNEL_ID, COMMUNITY_CHANNEL_URL

logger = logging.getLogger(__name__)


async def format_and_broadcast_major_battle_story(
    bot_app,
    session: AsyncSession,
    territory: models.Territory,
    attacker: models.User,
    att_house: Optional[models.House],
    old_owner_house_id: Optional[int],
    battle_res: dict,
    can_annex: bool,
    dragon_pwr: int = 0,
    def_dragon_pwr: int = 0,
    att_champion: Optional[str] = None,
    def_champion: Optional[str] = None,
    weather_type: str = "normal",
):
    """
    Katta urushlar va qal'a qamallari tugagach, Telegram kanalga (@northremembers1)
    chiroyli, qisqa va qiziqarli Vesteros solnoma-hikoyasini e'lon qilish.
    """
    if not bot_app:
        return

    att_losses = battle_res.get("attacker_losses", {})
    def_losses = battle_res.get("defender_losses", {})
    att_loss_cnt = sum(att_losses.values()) if isinstance(att_losses, dict) else 0
    def_loss_cnt = sum(def_losses.values()) if isinstance(def_losses, dict) else 0
    total_losses = att_loss_cnt + def_loss_cnt

    winner = battle_res.get("winner", "defender")
    is_conquest = (winner == "attacker" and can_annex)
    dragon_involved = (dragon_pwr > 0 or def_dragon_pwr > 0)
    wildfire_used = bool(battle_res.get("wildfire_used", 0) > 0)
    heavy_casualties = total_losses >= 60

    # Katta urush mezonlari:
    # 1. Qal'a egallandi (conquest)
    # 2. Ajdaho jangga kirdi
    # 3. Yovvoyi olov (Wildfire) portladi
    # 4. Katta talofat (kamida 60+ jangchi halok bo'ldi)
    if not (is_conquest or dragon_involved or wildfire_used or heavy_casualties):
        return

    att_house_name = att_house.name if att_house else "Vesteros Qo'shini"
    def_house_name = "Neytral Qorovullar"
    if old_owner_house_id:
        try:
            def_house = await session.get(models.House, old_owner_house_id)
            if def_house:
                def_house_name = def_house.name
        except Exception:
            pass

    # Sarlavha
    if is_conquest:
        title = "📜 ══════ ⚔️ **VESTEROS SOLNOMASI: QAL'A QULASHI!** ⚔️ ══════ 📜"
    elif winner == "attacker":
        title = "📜 ══════ ⚔️ **VESTEROS SOLNOMASI: QONLI QAMAL** ⚔️ ══════ 📜"
    else:
        title = "📜 ══════ 🛡️ **VESTEROS SOLNOMASI: ENGIQMAS MUDOFAA** 🛡️ ══════ 📜"

    castle_display = f"{territory.name} ({territory.castle_name})"
    att_name = attacker.full_name or "Jasur Lord"

    # Muqaddima (Ob-havo va hujum manzarasi)
    intro_variants = [
        f"Tun qorong'usi chekinib, {castle_display} osmonida jangovar burg'ular faryodi yangradi. **{att_house_name}** bayroqlari ostida Lord **{att_name}** qo'shini shiddatli qamalga kirdi.",
        f"{castle_display} osmonini quyuq tutun qopladi. **{att_house_name}** xonadoni jangchilari qal'a poydevoriga kuchli zarba berib, qonli qamalni boshladilar.",
        f"Vesteros yilnomachilari bugungi kunni qonli harflar bilan yozishadi: Lord **{att_name}** ({att_house_name}) ulkan lashkar bilan {castle_display} devorlari ostida saf tortdi.",
    ]
    if weather_type == "blizzard":
        intro = f"Qahraton qor bo'roni va ayozli izg'irin ostida Lord **{att_name}** ({att_house_name}) lashkari muzlagan {castle_display} devorlari tomon qonli hamlaga o'tdi."
    elif weather_type == "storm":
        intro = f"Chaqmoqlar chaqnashi va dahshatli bo'ron ichra **{att_house_name}** qo'shini {castle_display} darvozalariga qarshi shiddatli hujum boshladi."
    else:
        intro = random.choice(intro_variants)

    event_paragraphs = []

    # Ajdaho
    if dragon_pwr > 0 and def_dragon_pwr > 0:
        event_paragraphs.append("🔥🐲 **Ajdaholar Raqsi:** Osmonda ikki ulkan maxluq to'qnashdi! Qal'a uzra olov va qora dud bo'ronlari yog'ilib, jang maydoni qonli jahannamga aylandi.")
    elif dragon_pwr > 0:
        event_paragraphs.append(f"🔥 **Drakaris!** Hujumchi Lordning ajdahosi osmondan qanot qoqib, {castle_display} burjlariga halokatli olov yog'dirdi. Mudofaa minoralari qora tutunga burkandi!")
    elif def_dragon_pwr > 0:
        event_paragraphs.append("🐲 **Mudofaa Qahri:** Qal'a uyasidan ko'tarilgan himoyachi ajdaho dushman saflarini o't ichida qoldirib, qamalni to'xtatishga urindi.")

    # Wildfire
    if wildfire_used:
        event_paragraphs.append("🧪💥 **Yovvoyi Olov Portlashi!** Zovurlarda yashil sehrli olov chaqnadi. Alkimyogarlarning qadimiy quroli o'nlab jangchilarni bir lahzada kulga aylantirdi.")

    # Sarkardalar
    if att_champion and def_champion:
        event_paragraphs.append(f"⚔️ **Sarkardalar Kurashi:** Ikki mashhur pahlavon — hujumchi **{att_champion}** va mudofaa posboni **{def_champion}** yakkama-yakka to'qnashib, mislsiz jasorat ko'rsatishdi.")
    elif att_champion:
        event_paragraphs.append(f"🗡️ Maydon markazida sarkarda **{att_champion}** eng oldingi saflarda turib, dushman to'siqlarini qilich zarbasi bilan yorib o'tdi.")
    elif def_champion:
        event_paragraphs.append(f"🛡️ Qal'a darvozasi oldida jasur posbon **{def_champion}** dushman to'lqinlarini mardonavor qaytarib, himoyachilarga ruh bag'ishladi.")

    # Qamal va yakuniy bosqich (Kulminatsiya)
    if is_conquest:
        climax = (
            f"⚡ Mudofaa devorlari dushman bosimiga dosh berolmadi va darvozalar parchalab tashlandi! "
            f"**{def_house_name}** garnizoni batamom taslim etildi. "
            f"Qal'aning eng baland minorasiga **{att_house_name}** mag'rur bayrog'i tikildi! "
            f"👑 **{castle_display} endi {att_house_name} xonadoni tasarrufida!**"
        )
    elif winner == "attacker":
        climax = (
            f"⚡ Qonli to'qnashuvdan so'ng mudofaa chizig'i yorib o'tildi va qal'a xazinasi qo'lga kiritildi. "
            f"Biroq {att_house_name} xonadoni qal'a limitiga ega bo'lganligi sababli, faqat behisob o'ljalar bilan safga qaytildi!"
        )
    else:
        climax = (
            f"🛡️ Qal'a devorlari va **{def_house_name}** garnizonining temir irodasi sinmadi! "
            f"Lord **{att_name}** qamalining barcha urinishlari barbod bo'lib, omon qolgan hujumchilar chekinishga majbur bo'ldi. "
            f"🏰 **{castle_display} qat'iyat bilan o'z mustaqilligini saqlab qoldi!**"
        )

    loot_gold = battle_res.get("loot", {}).get("gold", 0)
    loot_food = battle_res.get("loot", {}).get("food", 0)
    loot_iron = battle_res.get("loot", {}).get("iron", 0)

    events_text = "\n\n".join(event_paragraphs)
    if events_text:
        events_text = "\n\n" + events_text

    winning_side = att_house_name if winner == "attacker" else def_house_name

    story = (
        f"{title}\n\n"
        f"🏰 **Hudud:** {castle_display}\n"
        f"👑 **Hujumchi:** Lord **{att_name}** ({att_house_name})\n"
        f"🛡️ **Himoyachi:** {def_house_name}\n\n"
        f"📖 **Jangnomadan:**\n"
        f"{intro}"
        f"{events_text}\n\n"
        f"{climax}\n\n"
        f"📊 **Jang Natijalari:**\n"
        f"• 💀 **Halok bo'lganlar:** Hujumchi: -{att_loss_cnt:,} | Qal'a: -{def_loss_cnt:,} (Jami: {total_losses:,})\n"
        f"• 📦 **Qo'lga olingan o'lja:** 🪙 +{loot_gold:,} oltin, 🌾 +{loot_food:,} g'alla, ⛓️ +{loot_iron:,} temir\n"
        f"• 🚩 **G'olib:** **{winning_side}**\n\n"
        f"❄️ _«Vesterosda qon to'kilmagan kun yo'q. Qish kelmoqda...»_\n"
        f"📢 **Rasmiy Kanal:** {COMMUNITY_CHANNEL_URL}"
    )

    try:
        from config import COMMUNITY_CHANNEL_ID
        bot = getattr(bot_app, "bot", bot_app)
        if not bot or not COMMUNITY_CHANNEL_ID:
            return

        try:
            await bot.send_message(
                chat_id=COMMUNITY_CHANNEL_ID,
                text=story,
                parse_mode="Markdown",
            )
            logger.info(f"Katta urush hikoyasi kanalga ({COMMUNITY_CHANNEL_ID}) muvaffaqiyatli jo'natildi: {territory.name}")
        except Exception as e_md:
            logger.warning(f"Kanalga Markdown jo'natishda xatolik ({e_md}), xom matnda yuborilmoqda...")
            clean_story = story.replace("**", "").replace("*", "").replace("`", "").replace("_", "")
            await bot.send_message(
                chat_id=COMMUNITY_CHANNEL_ID,
                text=clean_story,
                parse_mode=None,
            )
    except Exception as e:
        logger.error(f"Kanalga urush hikoyasini yuborishda xatolik: {e}")


async def process_due_marches(bot_app=None):
    """
    Manziliga yetib borgan barcha harbiy yurishlarni hisoblab yakunlash
    """
    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()
        result = await session.execute(
            select(models.BattleMarch).where(
                models.BattleMarch.status == "marching",
                models.BattleMarch.arrival_time <= now,
            )
        )
        marches = result.scalars().all()

        for march in marches:
            try:
                # Hujumchi va Hudud ma'lumotlari
                attacker = await session.get(models.User, march.attacker_user_id)
                territory = await session.get(models.Territory, march.target_territory_id)

                if not attacker or not territory:
                    march.status = "failed"
                    continue

                # Hujumchi tarkibi
                att_army = {
                    "infantry": march.infantry,
                    "archers": march.archers,
                    "cavalry": march.cavalry,
                    "spearmen": march.spearmen,
                    "special_troops": march.special_troops,
                }

                # Himoyachi garnizoni
                def_garrison = {
                    "infantry": territory.garrison_infantry or 0,
                    "archers": territory.garrison_archers or 0,
                    "cavalry": territory.garrison_cavalry or 0,
                    "spearmen": territory.garrison_spearmen or 0,
                    "special_troops": 0,
                }

                # Ajdar tekshiruvi (Hujumchi ajdari)
                march_dr_id = getattr(march, "dragon_id", None)
                if march_dr_id:
                    dragon = await session.get(models.Dragon, march_dr_id)
                else:
                    dragon = await crud.get_user_dragon(session, attacker.id)
                dragon_pwr = 0
                has_dragon = getattr(march, "has_dragon", True)
                dragon_tactic = getattr(march, "dragon_tactic", "balanced")

                if dragon and dragon.stage in ["baby", "adult"] and has_dragon:
                    if dragon.hunger >= 20:
                        dragon_pwr = dragon.power
                        dragon.hunger = max(0, dragon.hunger - 25)  # Drakarys 25 ochlik sarflaydi
                        max_p = crud.get_max_dragon_power(dragon.level, dragon.stage, dragon.artifact_code)
                        dragon.power = min(max_p, (dragon.power or 0) + 5)  # Tajriba oshishi
                    else:
                        logger.info(f"{dragon.name} och bo'lgani uchun jangda qatnasha olmadi.")

                # Himoyachining ajdari va artefakti (agar qal'a egasi lordining ajdari bo'lsa)
                def_dragon_pwr = 0
                def_lord_id = None
                def_lord_user = None
                def_house = None
                def_art_bonuses = {}
                old_owner_house_id = territory.owner_house_id
                if old_owner_house_id:
                    def_house = await session.get(models.House, old_owner_house_id)
                    if def_house and def_house.lord_user_id:
                        def_lord_id = def_house.lord_user_id
                        def_lord_user = await crud.get_user_by_telegram_id(session, def_house.lord_user_id)
                        if def_lord_user:
                            def_dragon = await crud.get_user_dragon(session, def_lord_user.id)
                            if def_dragon and def_dragon.stage in ["baby", "adult"] and def_dragon.hunger >= 20:
                                def_dragon_pwr = def_dragon.power
                                def_dragon.hunger = max(0, def_dragon.hunger - 20)
                            
                            def_art = await crud.get_equipped_artifact(session, def_lord_user.id)
                            if def_art:
                                def_art_bonuses = ARTIFACTS_DATA.get(def_art.code, {})

                # Qal'ada qo'riqchilik qilayotgan xonadon ajdari
                st_dr = crud.get_stationed_dragon_info(territory)
                if st_dr and st_dr.get("power", 0) > def_dragon_pwr:
                    def_dragon_pwr = st_dr["power"]

                # Hujumchining artefakti
                att_art_bonuses = {}
                att_art = await crud.get_equipped_artifact(session, attacker.id)
                if att_art:
                    att_art_bonuses = ARTIFACTS_DATA.get(att_art.code, {})

                march_catapults = getattr(march, "catapults", 0) or 0
                march_siege_towers = getattr(march, "siege_towers", 0) or 0
                terr_wildfire = getattr(territory, "wildfire_count", 0) or 0

                # Sarkardalar (Champion) - Async safe fetch
                att_army_obj = await crud.get_user_army(session, attacker.id)
                att_champion = getattr(march, "champion", None)
                if not att_champion and att_army_obj:
                    att_champion = getattr(att_army_obj, "champion", None)

                def_champion = None
                if def_lord_user:
                    def_lord_army = await crud.get_user_army(session, def_lord_user.id)
                    if def_lord_army:
                        def_champion = getattr(def_lord_army, "champion", None)

                # Josus tomonidan darvoza ochilganligini tekshirish
                gates_open = bool(
                    getattr(territory, "gates_compromised_until", None)
                    and territory.gates_compromised_until > datetime.utcnow()
                )

                # Ob-havoni olish
                weather_info = await crud.get_current_weather(session)
                weather_type = weather_info.get("weather_type", "normal")

                # Jang hisoblash
                battle_res = calculate_battle(
                    attacker_army=att_army,
                    defender_garrison=def_garrison,
                    castle_defense=territory.defense,
                    dragon_power=dragon_pwr,
                    dragon_tactic=dragon_tactic,
                    defender_dragon_power=def_dragon_pwr,
                    attacker_artifact_bonuses=att_art_bonuses,
                    defender_artifact_bonuses=def_art_bonuses,
                    catapults=march_catapults,
                    siege_towers=march_siege_towers,
                    wildfire_count=terr_wildfire,
                    attacker_champion=att_champion,
                    defender_champion=def_champion,
                    gates_compromised=gates_open,
                    weather_type=weather_type,
                )

                # Wildfire ishlatilgan bo'lsa, qal'a zaxirasidan kamaytirish
                if battle_res.get("wildfire_used", 0) > 0 and terr_wildfire > 0:
                    territory.wildfire_count = max(0, territory.wildfire_count - 1)

                # Qal'a mudofaasiga yetkazilgan talofatni hisobga olish
                castle_defense_dmg = battle_res.get("castle_defense_damage", 0)
                if castle_defense_dmg > 0:
                    territory.defense = max(50, territory.defense - castle_defense_dmg)

                # Tirik qolgan hujumchilarni armiyaga qaytarish
                attacker_army_obj = att_army_obj or (await crud.get_user_army(session, attacker.id))
                if attacker_army_obj:
                    attacker_army_obj.infantry = (attacker_army_obj.infantry or 0) + battle_res["remaining_attacker"]["infantry"]
                    attacker_army_obj.archers = (attacker_army_obj.archers or 0) + battle_res["remaining_attacker"]["archers"]
                    attacker_army_obj.cavalry = (attacker_army_obj.cavalry or 0) + battle_res["remaining_attacker"]["cavalry"]
                    attacker_army_obj.spearmen = (attacker_army_obj.spearmen or 0) + battle_res["remaining_attacker"]["spearmen"]
                    attacker_army_obj.special_troops = (attacker_army_obj.special_troops or 0) + battle_res["remaining_attacker"]["special_troops"]
                    survived_cats = max(0, march_catapults - battle_res.get("catapults_lost", 0))
                    survived_twrs = max(0, march_siege_towers - battle_res.get("siege_towers_lost", 0))
                    attacker_army_obj.catapults = (attacker_army_obj.catapults or 0) + survived_cats
                    attacker_army_obj.siege_towers = (attacker_army_obj.siege_towers or 0) + survived_twrs
                    session.add(attacker_army_obj)
                    await session.flush()

                # Garnizonni yangilash
                territory.garrison_infantry = battle_res["remaining_defender"]["infantry"]
                territory.garrison_archers = battle_res["remaining_defender"]["archers"]
                territory.garrison_cavalry = battle_res["remaining_defender"]["cavalry"]
                territory.garrison_spearmen = battle_res["remaining_defender"]["spearmen"]

                # Agar hujumchi yutsa: Hududni egallash va o'lja
                att_house = await session.get(models.House, attacker.house_id)
                att_house_name = att_house.name if att_house else "Vesteros Qo'shini"
                can_annex = False

                if battle_res["winner"] == "attacker":
                    # Xonadon qal'alar soni tekshiruvi (Maksimal 5 ta qal'a limiti)
                    attacker_castle_count = await crud.get_house_castle_count(session, attacker.house_id) if attacker.house_id else 0
                    can_annex = bool(attacker.house_id) and ((territory.owner_house_id == attacker.house_id) or (attacker_castle_count < crud.MAX_HOUSE_CASTLES))

                    if can_annex:
                        territory.owner_house_id = attacker.house_id
                        territory.conquered_by_user_id = attacker.id
                        # Zabt etilgan qal'a mudofaa devorlari shikastlangan
                        territory.defense = min(territory.defense or 0, 300)
                        territory.castle_level = 1
                        from data.map_data import TERRITORIES_DATA
                        canon_info = TERRITORIES_DATA.get(territory.code, {})
                        if canon_info:
                            territory.gold_income = canon_info.get("gold_income", territory.gold_income)
                            territory.food_income = canon_info.get("food_income", territory.food_income)
                            territory.iron_income = canon_info.get("iron_income", territory.iron_income)
                            territory.castle_tier = canon_info.get("castle_tier", territory.castle_tier)
                        else:
                            tier_val = getattr(territory, "castle_tier", 2) or 2
                            tier_defaults = {
                                1: {"gold": 1000, "food": 2000, "iron": 900},
                                2: {"gold": 600, "food": 1600, "iron": 520},
                                3: {"gold": 380, "food": 1100, "iron": 340},
                            }
                            d_inc = tier_defaults.get(tier_val, tier_defaults[2])
                            territory.gold_income = territory.gold_income or d_inc["gold"]
                            territory.food_income = territory.food_income or d_inc["food"]
                            territory.iron_income = territory.iron_income or d_inc["iron"]
                        # Qal'a egasi o'zgarganda mudofaadagi ajdar uyasiga qaytadi
                        if territory.reinforcements_json:
                            try:
                                r_json = json.loads(territory.reinforcements_json)
                                if "stationed_dragon" in r_json:
                                    del r_json["stationed_dragon"]
                                if "stationed_dragons" in r_json:
                                    del r_json["stationed_dragons"]
                                territory.reinforcements_json = json.dumps(r_json)
                            except Exception:
                                pass
                    else:
                        logger.info(f"Xonadon #{attacker.house_id} allaqachon {attacker_castle_count} ta qal'aga ega (max {crud.MAX_HOUSE_CASTLES}). Qal'a egallanmadi, faqat o'lja olindi.")

                    tot_gold = battle_res["loot"]["gold"]
                    tot_food = battle_res["loot"]["food"]
                    tot_iron = battle_res["loot"]["iron"]

                    attacker.gold += int(tot_gold * 0.7)
                    attacker.food += int(tot_food * 0.7)
                    attacker.iron += int(tot_iron * 0.7)
                    attacker.prestige += 12
                    attacker.xp += 250
                    check_user_level_up(attacker)

                    if dragon and dragon_pwr > 0:
                        max_p = crud.get_max_dragon_power(dragon.level, dragon.stage, dragon.artifact_code)
                        dragon.power = min(max_p, (dragon.power or 0) + 10)  # G'alaba bonusi

                    if att_house:
                        att_house.gold += int(tot_gold * 0.3)
                        att_house.food += int(tot_food * 0.3)
                        att_house.iron += int(tot_iron * 0.3)
                        att_house.prestige += 6

                    if can_annex:
                        await crud.log_player_activity(
                            session=session,
                            user_id=attacker.id,
                            action_type="conquer_castle",
                            details=(
                                f"⚔️ QAL'A ZABT ETILDI!\n"
                                f"👑 Hujumchi: {attacker.full_name} ({att_house_name})\n"
                                f"🏰 Qal'a: {territory.name} ({territory.castle_name})\n"
                                f"📦 O'lja: +{tot_gold:,}🪙, +{tot_food:,}🌾, +{tot_iron:,}⛓️"
                            ),
                            amount_gold=int(tot_gold * 0.7),
                            amount_food=int(tot_food * 0.7),
                            amount_iron=int(tot_iron * 0.7),
                            bot_app=bot_app,
                            notify_admin=True,
                        )

                    # Himoyachi o'yinchilarni (qal'a egasi, lord, a'zolar) aniqlash
                    defender_notify_ids = set()
                    if getattr(territory, "conquered_by_user_id", None):
                        c_usr = await session.get(models.User, territory.conquered_by_user_id)
                        if c_usr and c_usr.telegram_id and c_usr.telegram_id != attacker.telegram_id:
                            defender_notify_ids.add(c_usr.telegram_id)
                    if def_lord_id and def_lord_id != attacker.telegram_id:
                        defender_notify_ids.add(def_lord_id)
                    if old_owner_house_id and old_owner_house_id != attacker.house_id:
                        h_res = await session.execute(
                            select(models.User.telegram_id).where(models.User.house_id == old_owner_house_id)
                        )
                        for (h_tid,) in h_res.all():
                            if h_tid and h_tid != attacker.telegram_id:
                                defender_notify_ids.add(h_tid)

                    # Himoyachilarga boy berish xabari (faqat qal'a haqiqatda egallangan bo'lsa)
                    if can_annex and bot_app and defender_notify_ids:
                        def_lose_text = (
                            f"🚨 **QAL'A BOY BERILDI!**\n\n"
                            f"🏰 **{territory.name} ({territory.castle_name})** qal'asi **{att_house_name}** armiyasi tomonidan qamal qilinib, egallab olindi!\n\n"
                            f"{battle_res['details']}\n\n"
                            f"Qal'ani qaytarib olish uchun xonadoningiz bilan qarshi hujum uyushtiring!"
                        )
                        bot = getattr(bot_app, "bot", bot_app)
                        for d_tid in defender_notify_ids:
                            try:
                                send_lose = def_lose_text
                                if len(send_lose) > 3800:
                                    send_lose = send_lose[:3750] + "\n\n*(Batafsil /battle bo'limida...)*"
                                await bot.send_message(
                                    chat_id=d_tid,
                                    text=send_lose,
                                    parse_mode="Markdown",
                                )
                            except Exception as e_md:
                                try:
                                    clean_def = def_lose_text.replace("**", "").replace("*", "").replace("`", "")
                                    if len(clean_def) > 3800:
                                        clean_def = clean_def[:3750] + "\n\n(Batafsil /battle bo'limida...)"
                                    await bot.send_message(chat_id=d_tid, text=clean_def, parse_mode=None)
                                except Exception as e:
                                    logger.warning(f"Himoyachiga xabar yuborishda xatolik: {e}")

                    # Xonadon guruhlariga ham hisobot yuborish
                    if bot_app:
                        if can_annex and old_owner_house_id and old_owner_house_id != attacker.house_id:
                            grp_lose_text = (
                                f"🚨💀 <b>QAL'A BOY BERILDI!</b>\n\n"
                                f"🏰 <b>{html.escape(territory.name)}</b> ({html.escape(territory.castle_name)}) "
                                f"dushman <b>{html.escape(att_house_name)}</b> armiyasi tomonidan zabt etildi!\n\n"
                                f"⚔️ <i>Qal'ani qaytarib olish uchun xonadon a'zolari birlashib qarshi hujumga o'ting!</i>"
                            )
                            asyncio.create_task(notify_house_group(bot_app, old_owner_house_id, grp_lose_text, parse_mode="HTML"))

                        if attacker.house_id:
                            if can_annex:
                                grp_win_text = (
                                    f"🏆⚔️ <b>BUYUK ZAFAR! QAL'A EGALLANDI!</b>\n\n"
                                    f"🏰 Jasur lordimiz <b>{html.escape(attacker.full_name)}</b> "
                                    f"dushmanning <b>{html.escape(territory.name)}</b> ({html.escape(territory.castle_name)}) qal'asini zabt etdi!\n\n"
                                    f"• 🪙 Oltin: <b>+{int(tot_gold * 0.3):,}</b>\n"
                                    f"• 🌾 Oziq-ovqat: <b>+{int(tot_food * 0.3):,}</b>\n"
                                    f"• ⛓️ Temir: <b>+{int(tot_iron * 0.3):,}</b>\n"
                                    f"• 🏆 Xonadon Prestige: <b>+25</b>"
                                )
                            else:
                                grp_win_text = (
                                    f"🏆⚔️ <b>BUYUK ZAFAR! DUSHMAN TOR-MOR ETILDI!</b>\n\n"
                                    f"🏰 Lordimiz <b>{html.escape(attacker.full_name)}</b> "
                                    f"<b>{html.escape(territory.name)}</b> qal'asiga hujum qilib zafar quchdi va o'lja keltirdi!\n"
                                    f"<i>(Xonadonimiz 5/5 ta qal'a limitiga ega bo'lgani sababli qal'a egallanmadi)</i>\n\n"
                                    f"• 🪙 Oltin: <b>+{int(tot_gold * 0.3):,}</b>\n"
                                    f"• 🌾 Oziq-ovqat: <b>+{int(tot_food * 0.3):,}</b>\n"
                                    f"• ⛓️ Temir: <b>+{int(tot_iron * 0.3):,}</b>\n"
                                    f"• 🏆 Xonadon Prestige: <b>+25</b>"
                                )
                            asyncio.create_task(notify_house_group(bot_app, attacker.house_id, grp_win_text, parse_mode="HTML"))
                else:
                    # Himoyachi g'alaba qozondi
                    # Himoyachi o'yinchilarni aniqlash
                    defender_notify_ids = set()
                    if getattr(territory, "conquered_by_user_id", None):
                        c_usr = await session.get(models.User, territory.conquered_by_user_id)
                        if c_usr and c_usr.telegram_id and c_usr.telegram_id != attacker.telegram_id:
                            defender_notify_ids.add(c_usr.telegram_id)
                    if def_lord_id and def_lord_id != attacker.telegram_id:
                        defender_notify_ids.add(def_lord_id)
                    if old_owner_house_id and old_owner_house_id != attacker.house_id:
                        h_res = await session.execute(
                            select(models.User.telegram_id).where(models.User.house_id == old_owner_house_id)
                        )
                        for (h_tid,) in h_res.all():
                            if h_tid and h_tid != attacker.telegram_id:
                                defender_notify_ids.add(h_tid)

                    if bot_app and defender_notify_ids:
                        def_win_text = (
                            f"🛡️ **QAL'A MUVAFFAQIYATLI HIMOYALANDI!**\n\n"
                            f"🏰 **{territory.name} ({territory.castle_name})** qal'angizga bo'lgan dushman hujumi jasorat bilan qaytarildi!\n\n"
                            f"{battle_res['details']}\n"
                        )
                        bot = getattr(bot_app, "bot", bot_app)
                        for d_tid in defender_notify_ids:
                            try:
                                send_win = def_win_text
                                if len(send_win) > 3800:
                                    send_win = send_win[:3750] + "\n\n*(Batafsil /battle bo'limida...)*"
                                await bot.send_message(
                                    chat_id=d_tid,
                                    text=send_win,
                                    parse_mode="Markdown",
                                )
                            except Exception as e_md:
                                try:
                                    clean_win = def_win_text.replace("**", "").replace("*", "").replace("`", "")
                                    if len(clean_win) > 3800:
                                        clean_win = clean_win[:3750] + "\n\n(Batafsil /battle bo'limida...)"
                                    await bot.send_message(chat_id=d_tid, text=clean_win, parse_mode=None)
                                except Exception as e:
                                    logger.warning(f"Himoyachiga xabar yuborishda xatolik: {e}")

                    if bot_app and old_owner_house_id and old_owner_house_id != attacker.house_id:
                        grp_def_win_text = (
                            f"🛡️⚔️ <b>QAL'A MUDOFAASI G'ALABA BILAN YAKUNLANDI!</b>\n\n"
                            f"🏰 <b>{html.escape(territory.name)}</b> ({html.escape(territory.castle_name)}) qal'amizga dushman "
                            f"<b>{html.escape(att_house_name)}</b> hujumi mardonavor qaytarildi va qal'amiz omon qoldi!"
                        )
                        asyncio.create_task(notify_house_group(bot_app, old_owner_house_id, grp_def_win_text, parse_mode="HTML"))

                # Jang hisobotini saqlash
                report = models.BattleReport(
                    attacker_user_id=attacker.id,
                    defender_user_id=territory.owner_house_id,
                    territory_id=territory.id,
                    attacker_losses_json=json.dumps(battle_res["attacker_losses"]),
                    defender_losses_json=json.dumps(battle_res["defender_losses"]),
                    loot_gold=battle_res["loot"]["gold"],
                    loot_food=battle_res["loot"]["food"],
                    loot_iron=battle_res["loot"]["iron"],
                    result="attacker_won" if battle_res["winner"] == "attacker" else "defender_won",
                    details=battle_res["details"],
                )
                session.add(report)

                # Hujumchiga Telegram orqali xabar yuborish
                if bot_app and attacker.telegram_id:
                    troop_labels_uz = {
                        "infantry": "Piyoda",
                        "archers": "Kamonchi",
                        "cavalry": "Otliq",
                        "spearmen": "Nayzachi",
                        "special_troops": "Maxsus qo'shin",
                    }
                    att_loss_str = ", ".join(f"{troop_labels_uz.get(t, t)}: -{c:,}" for t, c in battle_res["attacker_losses"].items() if c > 0) or "Yo'qotishlar yo'q"
                    def_loss_str = ", ".join(f"{troop_labels_uz.get(t, t)}: -{c:,}" for t, c in battle_res["defender_losses"].items() if c > 0) or "Yo'qotishlar yo'q"

                    if battle_res["winner"] == "attacker":
                        if can_annex:
                            res_title = "🏆 **G'ALABA! QAL'A ZABT ETILDI!**"
                            res_outcome = (
                                f"🎉 Tabriklaymiz! **{territory.name} ({territory.castle_name})** qal'asi endi "
                                f"**{att_house_name}** xonadoni tasarrufiga o'tdi va '/castles' ro'yxatingizga qo'shildi!"
                            )
                        else:
                            res_title = "🏆 **G'ALABA! (O'LJA QO'LGA KIRITILDI)**"
                            res_outcome = (
                                f"⚔️ Dushman mag'lub etildi va o'ljalar qo'lga kiritildi! "
                                f"Biroq xonadoningiz allaqachon maksimal {crud.MAX_HOUSE_CASTLES} ta qal'aga ega bo'lgani tufayli qal'a xonadoningizga qo'shilmadi. "
                                f"Yangi qal'alarni zabt etish uchun /castles orqali keraksiz qal'alardan birini ozod qiling (egasiz neytral holatga keltiring)."
                            )
                    else:
                        res_title = "🛡️ **MAG'LUBIYAT! HUJUM QAYTARILDI.**"
                        res_outcome = (
                            f"⚠️ Dushman qal'asi mudofaa devorlari va kuchli garnizoni tufayli hujum qaytarildi. "
                            f"Qal'ani egallash uchun kattaroq qo'shin to'plang yoki ittifoqchilaringiz bilan qayta zarba bering!"
                        )

                    msg = (
                        f"⚔️ **JANG HISOBOTI: {territory.name.upper()} ({territory.castle_name})**\n\n"
                        f"{res_title}\n\n"
                        f"{res_outcome}\n\n"
                        f"{battle_res['details']}\n\n"
                        f"👥 **Talofatlar:**\n"
                        f"• Bizning armiya: {att_loss_str}\n"
                        f"• Qal'a garnizoni: {def_loss_str}\n\n"
                        f"💰 **Qo'lga kiritilgan o'lja:**\n"
                        f"🪙 +{battle_res['loot']['gold']:,} oltin | 🌾 +{battle_res['loot']['food']:,} g'alla | ⛓️ +{battle_res['loot']['iron']:,} temir\n\n"
                        f"Batafsil ma'lumot va janglar tarixini /battle bo'limida ko'rishingiz mumkin."
                    )
                    bot = getattr(bot_app, "bot", bot_app)
                    try:
                        send_msg = msg
                        if len(send_msg) > 3800:
                            send_msg = send_msg[:3750] + "\n\n*(Batafsil /battle bo'limida...)*"
                        await bot.send_message(
                            chat_id=attacker.telegram_id,
                            text=send_msg,
                            parse_mode="Markdown",
                        )
                    except Exception as e_md:
                        logger.warning(f"Markdown orqali xabar yuborishda xatolik ({e_md}), xom matn yuborilmoqda...")
                        try:
                            clean_msg = msg.replace("**", "").replace("*", "").replace("`", "")
                            if len(clean_msg) > 3800:
                                clean_msg = clean_msg[:3750] + "\n\n(Batafsil /battle bo'limida...)"
                            await bot.send_message(
                                chat_id=attacker.telegram_id,
                                text=clean_msg,
                                parse_mode=None,
                            )
                        except Exception as e_final:
                            logger.error(f"Hujumchiga xabar yuborish butunlay muvaffaqiyatsiz bo'ldi: {e_final}")

                    try:
                        from core.notifier import notify_owner
                        winner_uz = "G'ALABA (Qal'a olindi)" if battle_res["winner"] == "attacker" else "MAG'LUBIYAT (Qaytarildi)"
                        await notify_owner(
                            bot_app,
                            f"⚔️ *SERVER JANGI YAKUNLANDI*\n\n"
                            f"🏰 Qal'a: *{territory.name} ({territory.castle_name})*\n"
                            f"👤 Hujumchi: *{attacker.full_name}* ({att_house_name})\n"
                            f"📊 Natija: *{winner_uz}*\n"
                            f"🪙 O'lja: {battle_res['loot']['gold']:,} oltin, {battle_res['loot']['food']:,} oziq-ovqat"
                        )
                    except Exception:
                        pass

                    # Katta urush bo'yicha rasmiy kanalga hikoya jo'natish
                    try:
                        await format_and_broadcast_major_battle_story(
                            bot_app=bot_app,
                            session=session,
                            territory=territory,
                            attacker=attacker,
                            att_house=att_house,
                            old_owner_house_id=old_owner_house_id,
                            battle_res=battle_res,
                            can_annex=can_annex,
                            dragon_pwr=dragon_pwr,
                            def_dragon_pwr=def_dragon_pwr,
                            att_champion=att_champion,
                            def_champion=def_champion,
                            weather_type=weather_type,
                        )
                    except Exception as e_brd:
                        logger.error(f"Urush hikoyasini kanalga yuborishda xatolik: {e_brd}")

                # Yurish muvaffaqiyatli yakunlandi
                march.status = "resolved"
                session.add(march)
                session.add(territory)
                await session.flush()

            except Exception as e:
                logger.error(f"March {march.id} ni hisoblashda xatolik: {e}", exc_info=True)
                try:
                    if march.status == "marching":
                        march.status = "failed"
                        session.add(march)
                        if attacker:
                            army = await crud.get_user_army(session, attacker.id)
                            if army:
                                army.infantry = (army.infantry or 0) + (march.infantry or 0)
                                army.archers = (army.archers or 0) + (march.archers or 0)
                                army.cavalry = (army.cavalry or 0) + (march.cavalry or 0)
                                army.spearmen = (army.spearmen or 0) + (march.spearmen or 0)
                                army.special_troops = (army.special_troops or 0) + (march.special_troops or 0)
                                army.catapults = (army.catapults or 0) + (getattr(march, "catapults", 0) or 0)
                                army.siege_towers = (army.siege_towers or 0) + (getattr(march, "siege_towers", 0) or 0)
                                session.add(army)
                                logger.info(f"March {march.id} qo'shinlari o'yinchi {attacker.id} ga failsafe qaytarildi.")
                        await session.flush()
                except Exception as e_refund:
                    logger.error(f"March {march.id} qo'shinlarini failsafe qaytarishda xatolik: {e_refund}")

        await session.commit()


async def run_white_walkers_step():
    """White Walker global reydi holatini yangilash"""
    async with AsyncSessionLocal() as session:
        event = await session.get(models.EventState, 1)
        if not event:
            event = models.EventState(
                id=1,
                event_name="white_walkers",
                data_json=json.dumps({"army": 500000, "hp": 500000, "max_hp": 500000, "stage": 1, "status": "marching"}),
                is_active=True,
            )
            session.add(event)
            await session.commit()


async def process_npc_growth_and_raids(bot_app=None):
    """
    NPC xonadonlar va avtomatik bosqinlar butunlay to'xtatilgan (Foydalanuvchi talabi).
    Barcha 50 ta xonadon oddiy o'yinchilar ixtiyoriga berilgan, avtomatik NPC bosqinlari yo'q.
    """
    return



async def check_house_election_expiration(bot_app=None):
    """
    Har bir xonadonda 1 kishi bo'lib, u xonadonning yagona va mutlaq Lordi hisoblanadi.
    Shu sababli Lordlik muddati tugatilmaydi va o'zgarmaydi.
    """
    return


async def check_war_mode_expiration(bot_app=None):
    """Urush rejimi vaqti tugagan bo'lsa, uni avtomatik yopish va o'yinchilarga sulh e'lonini yuborish"""
    try:
        async with AsyncSessionLocal() as session:
            ev = await session.execute(
                select(models.EventState).where(models.EventState.event_name == "war_mode")
            )
            war_event = ev.scalar_one_or_none()
            if not war_event or not war_event.is_active:
                return

            data = {}
            try:
                data = json.loads(war_event.data_json or "{}")
            except Exception:
                data = {}

            auto_close_str = data.get("auto_close_at")
            if not auto_close_str:
                return

            try:
                auto_close_at = datetime.fromisoformat(auto_close_str)
            except Exception:
                return

            now = datetime.utcnow()
            if now >= auto_close_at:
                # Muddat tugadi, urushni yopamiz
                war_event.is_active = False
                data["closed_at"] = now.isoformat()
                data["auto_close_at"] = None
                war_event.data_json = json.dumps(data)
                await session.commit()

                logger.info("⚔️ Urush vaqti tugadi. Sulh rejimi kuchga kirdi.")

                if bot_app:
                    peace_announcement = (
                        "🕊️ **QIROL FARMONI: URUSH YAKUNLANDI (SULH BOSHLANDI)!**\n\n"
                        "Vesteros uzra belgilangan urush vaqti nihoyasiga yetdi.\n"
                        "Qirol farmoniga binoan barcha dushman qal'alariga hujumlar to'xtatildi!\n\n"
                        "🛡️ *Endi nima qilish kerak?*\n"
                        "• O'z qal'angiz mudofaasini tiklang va garnizonni to'ldiring\n"
                        "• Yangi askarlar yollang va don/temir to'plang\n"
                        "• Keyingi urush uchun kuch to'plang!\n\n"
                        "Keyingi harbiy holat admin tomonidan e'lon qilinadi."
                    )

                    users_res = await session.execute(select(models.User.telegram_id))
                    all_ids = users_res.scalars().all()
                    for tg_id in all_ids:
                        try:
                            await bot_app.bot.send_message(
                                chat_id=tg_id,
                                text=peace_announcement,
                                parse_mode="Markdown",
                            )
                        except Exception:
                            pass
    except Exception as e:
        logger.error(f"check_war_mode_expiration xatosi: {e}")


async def process_due_trade_caravans(bot_app=None):
    """
    Manziliga eson-omon yetib borgan barcha savdo karvonlarini hisoblash va foydani egasiga berish
    """
    try:
        async with AsyncSessionLocal() as session:
            now = datetime.utcnow()
            res = await session.execute(
                select(models.TradeCaravan).where(
                    models.TradeCaravan.status == "moving",
                    models.TradeCaravan.arrival_time <= now,
                )
            )
            caravans = res.scalars().all()
            if not caravans:
                return

            for caravan in caravans:
                caravan.status = "arrived"
                user_res = await session.execute(
                    select(models.User).where(models.User.id == caravan.owner_user_id)
                )
                owner = user_res.scalar_one_or_none()
                if not owner:
                    continue

                # Soqchilarni armiyaga qaytarish
                army_res = await session.execute(
                    select(models.Army).where(models.Army.user_id == owner.id)
                )
                army = army_res.scalar_one_or_none()
                if army:
                    army.cavalry += (caravan.escort_cavalry or 0)
                    army.infantry += (caravan.escort_infantry or 0)

                # Foydani berish (Savdo bozorida prestige berilmaydi)
                gold_gain = caravan.expected_gold_reward or 500
                owner.gold += gold_gain

                dest_name = "Savdo porti"
                dest_res = await session.get(models.Territory, caravan.destination_territory_id)
                if dest_res:
                    dest_name = dest_res.name

                logger.info(f"🐪 Savdo karvoni #{caravan.id} ({owner.username}) manzilga ({dest_name}) yetib bordi: +{gold_gain}G")

                if bot_app and owner.telegram_id:
                    msg = (
                        f"🐪💰 **SAVDO KARVONI MANZILGA YETIB BORDI!**\n\n"
                        f"Shahanshoh yo'llaridan o'tgan savdo karvoningiz xavfsiz ravishda **{dest_name}** savdo markaziga yetib bordi!\n\n"
                        f"📦 Sotilgan yuk: **{caravan.resource_amount:,}** {caravan.resource_type.capitalize()}\n"
                        f"💰 Sof daromad: **+{gold_gain:,}** Oltin\n"
                        f"🛡️ Qaytgan soqchilar: **{caravan.escort_cavalry}** Otliq, **{caravan.escort_infantry}** Piyoda armiyangiz safiga qaytdi."
                    )
                    try:
                        await bot_app.bot.send_message(
                            chat_id=owner.telegram_id,
                            text=msg,
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass

            await session.commit()
    except Exception as e:
        logger.error(f"process_due_trade_caravans xatosi: {e}")


# ============================================================
# KUNLIK 21:00 (UZT) URUSH VA FAOL NPC BOSQINLARI
# ============================================================

NPC_WAR_RAIDERS = [
    {"name": "Qirollik Temir Qo'shini (King's Landing)", "origin": "King's Landing", "emoji": "👑"},
    {"name": "Harrenhal Qarg'alari va Qora Ritsarlari", "origin": "Harrenhal", "emoji": "💀"},
    {"name": "Botqoqlik Xavfli Qaroqchilari", "origin": "Moat Cailin", "emoji": "🌿"},
    {"name": "Qonli Darvoza Tog' Qabilalari", "origin": "Bloody Gate", "emoji": "🦅"},
    {"name": "Qizil Reynlarning Qasoskor Otryadi", "origin": "Castamere", "emoji": "🩸"},
    {"name": "Dengiz Qaroqchilari Flotiliyasi", "origin": "White Harbor", "emoji": "⚓"},
    {"name": "G'arbiy Yollanma Qo'shin", "origin": "Lannisport", "emoji": "🦁"},
    {"name": "Daryo Bo'yi Talonchi Qaroqchilari", "origin": "Maidenpool", "emoji": "🐟"},
    {"name": "Beynfort Dengiz Bo'rilari", "origin": "Banefort", "emoji": "🌊"},
    {"name": "Sitadel Qasamyodchilari va Fanatiklar", "origin": "Oldtown", "emoji": "🏛️"},
    {"name": "Mance Rayderning Yovvoyi Armiyasi", "origin": "Devor Orti", "emoji": "🏹"},
    {"name": "Tun Qiroli va Oq Ko'lankalar", "origin": "Abadiy Qish", "emoji": "🧟"},
]


async def execute_daily_2100_war_and_npc_raids(bot_app=None, force: bool = False):
    """
    Har kuni soat 21:00 (O'zbekiston vaqti UTC+5) da avtomatik ishga tushadi:
    1. Urush rejimini (war_mode) 2 soatga (21:00 dan 23:00 gacha) ochadi.
    2. Barcha o'yinchilar va xonadon guruhlariga e'lon yuboradi.
    3. 10 ta NPC qal'asi va erkin NPC lashkarlari o'yinchi qal'alariga reyd (bosqin) uyushtiradi.
    4. Mudofaa janglari hisoblanadi, garnizon talofatlari va o'ljalar yozilib, Lordlarga hisobot beriladi.
    """
    try:
        async with AsyncSessionLocal() as session:
            uzb_now = datetime.utcnow() + timedelta(hours=5)
            today_str = uzb_now.strftime("%Y-%m-%d")

            # 1. Kunlik tekshiruv (agar force=False bo'lsa)
            ev_res = await session.execute(
                select(models.EventState).where(models.EventState.event_name == "daily_2100_war")
            )
            daily_ev = ev_res.scalar_one_or_none()
            if not daily_ev:
                daily_ev = models.EventState(
                    event_name="daily_2100_war",
                    data_json=json.dumps({"last_war_date": None, "history": []}),
                    is_active=True,
                )
                session.add(daily_ev)
                await session.flush()

            data = {}
            try:
                data = json.loads(daily_ev.data_json or "{}")
            except Exception:
                data = {}

            if not force and data.get("last_war_date") == today_str:
                logger.info(f"Bugungi ({today_str}) 21:00 urushi allaqachon o'tkazilgan.")
                return

            # Urush sanasini yangilaymiz
            data["last_war_date"] = today_str
            data["last_triggered_at"] = uzb_now.isoformat()
            daily_ev.data_json = json.dumps(data)
            await session.commit()

            logger.info(f"⚔️ KUNLIK URUSH VA NPC BOSQINLARI BOSHLANDI! ({today_str})")

            # 2. Urush rejimini 1.0 soatga ochamiz (1 soat davom etadi)
            await crud.set_war_status(session, is_active=True, duration_hours=1.0, opened_by=0)

            # 3. Server-wide broadcast (Barcha o'yinchilarga e'lon)
            war_announcement = (
                "⚔️🔥 **QIROL FARMONI: HARBIY HOLAT VA NPC BOSQINLARI BOSHLANDI!** 🔥⚔️\n\n"
                "Vesteros uzra qonli jang darvozalari 1 soatga keng ochildi!\n\n"
                "🏰 Barcha dushman qal'alariga harbiy yurishlar va qamallar boshlandi.\n"
                "👾 **OGOHLANTIRISH:** 10 ta NPC qo'rg'onlari va yovvoyi erkin qo'shinlar ham o'yinchilar qal'alariga qaqshatqich bosqin boshladi!\n\n"
                "🛡️ O'z qal'angizni himoya qiling, qo'shinlarni safarbar qiling va xonadoningiz sha'nini saqlang!\n\n"
                "*(Xaritadan dushman qal'asini tanlang va harbiy yurish boshlang! Urush 1 soat davom etadi)*"
            )

            if bot_app:
                users_res = await session.execute(select(models.User.telegram_id))
                all_ids = users_res.scalars().all()
                for tg_id in all_ids:
                    try:
                        await bot_app.bot.send_message(
                            chat_id=tg_id,
                            text=war_announcement,
                            parse_mode="Markdown",
                        )
                    except Exception:
                        pass

            # 4. NPC Qal'alarga avtomatik bosqinlar to'xtatilgan (Foydalanuvchi talabi)
            await session.commit()

            # Bosh egaga (Owner) hisobot
            try:
                await notify_owner(
                    bot_app,
                    f"👾 *KUNLIK URUSH & NPC BOSQINLARI O'TKAZILDI!*\n\n"
                    f"📅 Sana: `{today_str}` (UZT)\n"
                    f"⚔️ Hujumga uchragan qal'alar soni: *{raided_count}*\n"
                    f"⏱️ Urush rejimi: *1 soat davomida faol*"
                )
            except Exception:
                pass

    except Exception as e:
        logger.error(f"execute_daily_2100_war_and_npc_raids xatosi: {e}", exc_info=True)


async def check_and_trigger_daily_war_failsafe(bot_app=None):
    """
    Foydalanuvchi talabiga ko'ra: Kunlik urush va NPC bosqinlari avtomatik tarzda emas,
    faqat admin tomonidan boshqariladi. Shuning uchun avtomatik ishga tushirish o'chirilgan.
    """
    return



