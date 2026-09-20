import json
import random
import logging
import asyncio
import html
from datetime import datetime
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from database import models, AsyncSessionLocal, crud
from core.battle_engine import calculate_battle
from core.economy_engine import process_hourly_tick
from core.leveling import check_user_level_up
from core.notifier import notify_house_group
from data.artifacts_data import ARTIFACTS_DATA

logger = logging.getLogger(__name__)


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
                march.status = "resolved"

                # Hujumchi va Hudud ma'lumotlari
                attacker = await session.get(models.User, march.attacker_user_id)
                territory = await session.get(models.Territory, march.target_territory_id)

                if not attacker or not territory:
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
                    "infantry": territory.garrison_infantry,
                    "archers": territory.garrison_archers,
                    "cavalry": territory.garrison_cavalry,
                    "spearmen": territory.garrison_spearmen,
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
                        dragon.power += 5  # Tajriba oshishi
                    else:
                        logger.info(f"{dragon.name} och bo'lgani uchun jangda qatnasha olmadi.")

                # Himoyachining ajdari va artefakti (agar qal'a egasi lordining ajdari bo'lsa)
                def_dragon_pwr = 0
                def_lord_id = None
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

                att_champion = getattr(march, "champion", None)
                if not att_champion and attacker.army:
                    att_champion = getattr(attacker.army, "champion", None)

                def_champion = None
                if def_lord_user and def_lord_user.army:
                    def_champion = getattr(def_lord_user.army, "champion", None)

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

                # Tirik qolgan hujumchilarni qaytarish
                army_res = await session.execute(
                    select(models.Army).where(models.Army.user_id == attacker.id)
                )
                attacker_army_obj = army_res.scalar_one_or_none()
                if attacker_army_obj:
                    attacker_army_obj.infantry += battle_res["remaining_attacker"]["infantry"]
                    attacker_army_obj.archers += battle_res["remaining_attacker"]["archers"]
                    attacker_army_obj.cavalry += battle_res["remaining_attacker"]["cavalry"]
                    attacker_army_obj.spearmen += battle_res["remaining_attacker"]["spearmen"]
                    attacker_army_obj.special_troops += battle_res["remaining_attacker"]["special_troops"]
                    survived_cats = max(0, march_catapults - battle_res.get("catapults_lost", 0))
                    survived_twrs = max(0, march_siege_towers - battle_res.get("siege_towers_lost", 0))
                    attacker_army_obj.catapults = (attacker_army_obj.catapults or 0) + survived_cats
                    attacker_army_obj.siege_towers = (attacker_army_obj.siege_towers or 0) + survived_twrs

                # Garnizonni yangilash
                territory.garrison_infantry = battle_res["remaining_defender"]["infantry"]
                territory.garrison_archers = battle_res["remaining_defender"]["archers"]
                territory.garrison_cavalry = battle_res["remaining_defender"]["cavalry"]
                territory.garrison_spearmen = battle_res["remaining_defender"]["spearmen"]

                # Agar hujumchi yutsa: Hududni egallash va o'lja
                att_house = await session.get(models.House, attacker.house_id)
                att_house_name = att_house.name if att_house else "Vesteros Qo'shini"

                if battle_res["winner"] == "attacker":
                    territory.owner_house_id = attacker.house_id
                    territory.conquered_by_user_id = attacker.id
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

                    tot_gold = battle_res["loot"]["gold"]
                    tot_food = battle_res["loot"]["food"]
                    tot_iron = battle_res["loot"]["iron"]

                    attacker.gold += int(tot_gold * 0.7)
                    attacker.food += int(tot_food * 0.7)
                    attacker.iron += int(tot_iron * 0.7)
                    attacker.prestige += 50
                    attacker.xp += 250
                    check_user_level_up(attacker)

                    if dragon and dragon_pwr > 0:
                        dragon.power += 10  # G'alaba bonusi

                    if att_house:
                        att_house.gold += int(tot_gold * 0.3)
                        att_house.food += int(tot_food * 0.3)
                        att_house.iron += int(tot_iron * 0.3)
                        att_house.prestige += 25

                    # Himoyachi Lordiga boy berish xabari
                    if bot_app and def_lord_id and old_owner_house_id != attacker.house_id:
                        def_lose_text = (
                            f"🚨 **QAL'A BOY BERILDI!**\n\n"
                            f"🏰 **{territory.name} ({territory.castle_name})** qal'asi **{att_house_name}** armiyasi tomonidan qamal qilinib, egallab olindi!\n\n"
                            f"{battle_res['details']}\n\n"
                            f"Qal'ani qaytarib olish uchun xonadon a'zolaringiz bilan qarshi hujum uyushtiring!"
                        )
                        try:
                            await bot_app.bot.send_message(
                                chat_id=def_lord_id,
                                text=def_lose_text,
                                parse_mode="Markdown",
                            )
                        except Exception as e_md:
                            try:
                                clean_def = def_lose_text.replace("**", "").replace("*", "").replace("`", "")
                                await bot_app.bot.send_message(chat_id=def_lord_id, text=clean_def)
                            except Exception as e:
                                logger.warning(f"Himoyachiga xabar yuborishda xatolik: {e}")

                    # Xonadon guruhlariga ham hisobot yuborish
                    if bot_app:
                        if old_owner_house_id and old_owner_house_id != attacker.house_id:
                            grp_lose_text = (
                                f"🚨💀 <b>QAL'A BOY BERILDI!</b>\n\n"
                                f"🏰 <b>{html.escape(territory.name)}</b> ({html.escape(territory.castle_name)}) "
                                f"dushman <b>{html.escape(att_house_name)}</b> armiyasi tomonidan zabt etildi!\n\n"
                                f"⚔️ <i>Qal'ani qaytarib olish uchun xonadon a'zolari birlashib qarshi hujumga o'ting!</i>"
                            )
                            asyncio.create_task(notify_house_group(bot_app, old_owner_house_id, grp_lose_text, parse_mode="HTML"))

                        if attacker.house_id:
                            grp_win_text = (
                                f"🏆⚔️ <b>BUYUK ZAFAR! QAL'A EGALLANDI!</b>\n\n"
                                f"🏰 Jasur lordimiz <b>{html.escape(attacker.full_name)}</b> "
                                f"dushmanning <b>{html.escape(territory.name)}</b> ({html.escape(territory.castle_name)}) qal'asini zabt etdi!\n\n"
                                f"• 🪙 Oltin: <b>+{int(tot_gold * 0.3):,}</b>\n"
                                f"• 🌾 Oziq-ovqat: <b>+{int(tot_food * 0.3):,}</b>\n"
                                f"• ⛓️ Temir: <b>+{int(tot_iron * 0.3):,}</b>\n"
                                f"• 🏆 Xonadon Prestige: <b>+25</b>"
                            )
                            asyncio.create_task(notify_house_group(bot_app, attacker.house_id, grp_win_text, parse_mode="HTML"))
                else:
                    # Himoyachi g'alaba qozondi
                    if bot_app and def_lord_id and old_owner_house_id != attacker.house_id:
                        def_win_text = (
                            f"🛡️ **QAL'A MUVAFFAQIYATLI HIMOYALANDI!**\n\n"
                            f"🏰 **{territory.name} ({territory.castle_name})** qal'angizga bo'lgan dushman hujumi jasorat bilan qaytarildi!\n\n"
                            f"{battle_res['details']}\n"
                        )
                        try:
                            await bot_app.bot.send_message(
                                chat_id=def_lord_id,
                                text=def_win_text,
                                parse_mode="Markdown",
                            )
                        except Exception as e_md:
                            try:
                                clean_win = def_win_text.replace("**", "").replace("*", "").replace("`", "")
                                await bot_app.bot.send_message(chat_id=def_lord_id, text=clean_win)
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
                        res_title = "🏆 **G'ALABA! QAL'A ZABT ETILDI!**"
                        res_outcome = (
                            f"🎉 Tabriklaymiz! **{territory.name} ({territory.castle_name})** qal'asi endi "
                            f"**{att_house_name}** xonadoni tasarrufiga o'tdi va '/castles' ro'yxatingizga qo'shildi!"
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
                    try:
                        await bot_app.bot.send_message(
                            chat_id=attacker.telegram_id,
                            text=msg,
                            parse_mode="Markdown",
                        )
                    except Exception as e_md:
                        logger.warning(f"Markdown orqali xabar yuborishda xatolik ({e_md}), xom matn yuborilmoqda...")
                        try:
                            clean_msg = msg.replace("**", "").replace("*", "").replace("`", "")
                            await bot_app.bot.send_message(
                                chat_id=attacker.telegram_id,
                                text=clean_msg,
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

            except Exception as e:
                logger.error(f"March {march.id} ni hisoblashda xatolik: {e}", exc_info=True)

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
    5 ta tirik NPC xonadonlar (Bolton, Frey/Blackwood, Golden Company, Wildlings, White Walkers)
    uchun garnizon o'sishi va o'yinchilar qal'alariga vaqti-vaqti bilan bosqin (raid) uyushtirish.
    """
    async with AsyncSessionLocal() as session:
        # 1. NPC xonadonlarni aniqlash
        npc_houses_res = await session.execute(select(models.House).where(models.House.is_npc == True))
        npc_houses = npc_houses_res.scalars().all()
        if not npc_houses:
            return

        npc_house_ids = [h.id for h in npc_houses]

        # 2. NPC xonadonlariga tegishli hududlarda garnizonning tabiiy o'sishi
        npc_terrs_res = await session.execute(
            select(models.Territory).where(models.Territory.owner_house_id.in_(npc_house_ids))
        )
        npc_terrs = npc_terrs_res.scalars().all()

        for terr in npc_terrs:
            terr.garrison_infantry = min(1500, terr.garrison_infantry + random.randint(10, 20))
            terr.garrison_archers = min(1000, terr.garrison_archers + random.randint(8, 15))
            terr.garrison_cavalry = min(800, terr.garrison_cavalry + random.randint(4, 10))
            terr.garrison_spearmen = min(1000, terr.garrison_spearmen + random.randint(6, 12))

        # 3. O'yinchilar qal'alariga davriy bosqin (Raid)
        # Har bir tickda 35% ehtimol bilan bitta NPC xonadon hujum uyushtiradi
        if random.random() < 0.35 and npc_terrs:
            attacking_house = random.choice(npc_houses)

            # O'yinchilar egalik qilayotgan qal'alarni topamiz
            player_terrs_res = await session.execute(
                select(models.Territory).where(~models.Territory.owner_house_id.in_(npc_house_ids))
            )
            player_terrs = player_terrs_res.scalars().all()

            if player_terrs:
                target_terr = random.choice(player_terrs)
                def_house = await session.get(models.House, target_terr.owner_house_id) if target_terr.owner_house_id else None

                # Qalqon tekshiruvi: agar xonadon lordi tinchlik qalqonida bo'lsa, bosqin o'tkazilmaydi
                target_shielded = False
                def_lord_id = None
                if def_house and def_house.lord_user_id:
                    def_lord_id = def_house.lord_user_id
                    lord_user = await crud.get_user_by_telegram_id(session, def_house.lord_user_id)
                    if lord_user and lord_user.peace_shield_until and lord_user.peace_shield_until > datetime.utcnow():
                        target_shielded = True

                if not target_shielded:
                    # Bosqinchi armiya tuziladi
                    raid_infantry = random.randint(80, 160)
                    raid_archers = random.randint(40, 90)
                    raid_cavalry = random.randint(20, 50)
                    raid_spearmen = random.randint(30, 70)

                    att_army = {
                        "infantry": raid_infantry,
                        "archers": raid_archers,
                        "cavalry": raid_cavalry,
                        "spearmen": raid_spearmen,
                        "special_troops": 0,
                    }
                    def_garrison = {
                        "infantry": target_terr.garrison_infantry,
                        "archers": target_terr.garrison_archers,
                        "cavalry": target_terr.garrison_cavalry,
                        "spearmen": target_terr.garrison_spearmen,
                        "special_troops": 0,
                    }

                    # Qal'adagi himoyachi ajdar kuchi
                    def_dr_info = crud.get_stationed_dragon_info(target_terr)
                    def_dr_pwr = def_dr_info.get("power", 0) if def_dr_info else 0

                    # Josus tomonidan darvoza ochilganligini va ob-havoni olish
                    gates_open = bool(
                        getattr(target_terr, "gates_compromised_until", None)
                        and target_terr.gates_compromised_until > datetime.utcnow()
                    )
                    cur_weather = await crud.get_current_weather(session)
                    weather_type = cur_weather.get("weather_type", "normal")

                    battle_res = calculate_battle(
                        attacker_army=att_army,
                        defender_garrison=def_garrison,
                        castle_defense=target_terr.defense,
                        dragon_power=0,
                        defender_dragon_power=def_dr_pwr,
                        gates_compromised=gates_open,
                        weather_type=weather_type,
                    )

                    # Himoyachi talofatlari
                    target_terr.garrison_infantry = battle_res["remaining_defender"]["infantry"]
                    target_terr.garrison_archers = battle_res["remaining_defender"]["archers"]
                    target_terr.garrison_cavalry = battle_res["remaining_defender"]["cavalry"]
                    target_terr.garrison_spearmen = battle_res["remaining_defender"]["spearmen"]

                    # Oqibatlar
                    if battle_res["winner"] == "attacker":
                        # NPC bosqini muvaffaqiyatli bo'ldi - xonadondan o'lja ketadi
                        loot_gold = battle_res["loot"]["gold"]
                        loot_food = battle_res["loot"]["food"]
                        if def_house:
                            def_house.gold = max(0, def_house.gold - loot_gold)
                            def_house.food = max(0, def_house.food - loot_food)

                        if bot_app and def_lord_id:
                            try:
                                await bot_app.bot.send_message(
                                    chat_id=def_lord_id,
                                    text=(
                                        f"🚨 **DUSHMAN NPC BOSQINI!**\n\n"
                                        f"🏰 **{target_terr.name} ({target_terr.castle_name})** qal'angizga **{attacking_house.emoji} {attacking_house.name}** "
                                        f"bosqinchilari kutilmaganda hujum qildi!\n\n"
                                        f"{battle_res['details']}\n\n"
                                        f"💸 Boy berilgan o'lja: -{loot_gold:,} oltin, -{loot_food:,} g'alla.\n"
                                        f"Qal'a mudofaasini kuchaytiring va yangi qo'shin yuboring!"
                                    ),
                                    parse_mode="Markdown",
                                )
                            except Exception as e:
                                logger.warning(f"NPC raid alert xatosi: {e}")
                    else:
                        # Himoyachi g'alaba qozondi
                        if def_house:
                            def_house.prestige += 20

                        if bot_app and def_lord_id:
                            try:
                                await bot_app.bot.send_message(
                                    chat_id=def_lord_id,
                                    text=(
                                        f"🛡️ **NPC BOSQINI MUVAFFAQIYATLI QAYTARILDI!**\n\n"
                                        f"🏰 **{target_terr.name} ({target_terr.castle_name})** qal'angiz garnizoni **{attacking_house.emoji} {attacking_house.name}** "
                                        f"bosqinchilarining shafqatsiz hujumini jasorat bilan qaytardi!\n\n"
                                        f"{battle_res['details']}\n\n"
                                        f"🏆 Xonadonga +20 Prestige berildi."
                                    ),
                                    parse_mode="Markdown",
                                )
                            except Exception as e:
                                logger.warning(f"NPC raid defend alert xatosi: {e}")

                    try:
                        from core.notifier import notify_owner
                        raid_res_str = "Qal'a bosib olindi" if battle_res["winner"] == "attacker" else "Qaytarildi"
                        await notify_owner(
                            bot_app,
                            f"👾 *SERVER: NPC BOSQINI YAKUNLANDI*\n\n"
                            f"🏰 Qal'a: *{target_terr.name} ({target_terr.castle_name})*\n"
                            f"⚔️ Bosqinchi: *{attacking_house.name}*\n"
                            f"📊 Natija: *{raid_res_str}*"
                        )
                    except Exception:
                        pass

        await session.commit()


async def check_house_election_expiration(bot_app=None):
    """
    Lordlar saylovi har 10 kunda bo'lishi:
    Lord saylangandan 10 kundan keyin vakolat muddati tugaydi,
    avtomatik ravishda yangi saylov boshlanadi va xonadon a'zolariga xabar beriladi.
    """
    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()
        result = await session.execute(
            select(models.House).where(
                models.House.is_npc == False,
                models.House.lord_user_id.isnot(None),
                models.House.lord_elected_at.isnot(None),
            )
        )
        houses = result.scalars().all()

        for house in houses:
            try:
                elapsed_sec = (now - house.lord_elected_at).total_seconds()
                # 10 kun = 10 * 86400 = 864,000 soniya
                if elapsed_sec >= 10 * 86400:
                    old_lord_tg_id = house.lord_user_id
                    old_lord = await crud.get_user_by_telegram_id(session, old_lord_tg_id)
                    old_lord_name = old_lord.full_name if old_lord else "Lord"

                    # Oldingi lord unvonini a'zoga tushiramiz
                    if old_lord and old_lord.rank == "king":
                        old_lord.rank = "member"

                    # Lordlikni vakant qilamiz va elected_at ni yangilaymiz
                    house.lord_user_id = None
                    house.lord_elected_at = now

                    # Xonadondagi eski saylov ovozlarini tozalaymiz
                    await session.execute(
                        delete(models.HouseVote).where(models.HouseVote.house_id == house.id)
                    )

                    logger.info(f"🏰 {house.name} xonadoni Lordining 10 kunlik muddati tugadi. Yangi saylov boshlandi.")

                    # Xonadon a'zolariga yangi saylov haqida xabar yuborish
                    if bot_app:
                        members_res = await session.execute(
                            select(models.User).where(models.User.house_id == house.id).limit(50)
                        )
                        members = members_res.scalars().all()

                        announcement = (
                            f"🗳️ **{house.emoji} {house.name} — YANGI LORD SAYLOVI BOSHLANDI!**\n\n"
                            f"Oldingi Lord **{old_lord_name}** ning 10 kunlik vakolat muddati yakunlandi.\n\n"
                            f"👑 Xonadon Lordligi hozirda bo'sh (Vakant)!\n"
                            f"Barcha a'zolar o'z nomzodiga ovoz berishi yoki Lordlikni qabul qilishi mumkin.\n"
                            f"G'alaba qozonish uchun 50% dan ko'p ovoz kerak bo'ladi.\n\n"
                            f"👉 /house buyrug'i orqali **Lord Saylovi** bo'limiga kiring!"
                        )

                        for m in members:
                            try:
                                await bot_app.bot.send_message(
                                    chat_id=m.telegram_id,
                                    text=announcement,
                                    parse_mode="Markdown",
                                )
                            except Exception:
                                pass

                        try:
                            from core.notifier import notify_owner
                            await notify_owner(
                                bot_app,
                                f"🗳️ *SERVER: YANGI SAYLOV BOSHLANDI*\n\n"
                                f"🏰 Xonadon: *{house.emoji} {house.name}*\n"
                                f"👑 Sabab: Lord *{old_lord_name}* ning 10 kunlik vakolat muddati tugadi."
                            )
                        except Exception:
                            pass
            except Exception as e:
                logger.error(f"House election expiration error for house {house.id}: {e}")

        await session.commit()


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

                # Foyda va nufuzni berish
                gold_gain = caravan.expected_gold_reward or 2500
                prestige_gain = 15 if caravan.resource_amount < 10000 else (30 if caravan.resource_amount < 20000 else 60)
                owner.gold += gold_gain
                owner.prestige += prestige_gain

                dest_name = "Savdo porti"
                dest_res = await session.get(models.Territory, caravan.destination_territory_id)
                if dest_res:
                    dest_name = dest_res.name

                logger.info(f"🐪 Savdo karvoni #{caravan.id} ({owner.username}) manzilga ({dest_name}) yetib bordi: +{gold_gain}G, +{prestige_gain}P")

                if bot_app and owner.telegram_id:
                    msg = (
                        f"🐪💰 **SAVDO KARVONI MANZILGA YETIB BORDI!**\n\n"
                        f"Shahanshoh yo'llaridan o'tgan savdo karvoningiz xavfsiz ravishda **{dest_name}** savdo markaziga yetib bordi!\n\n"
                        f"📦 Sotilgan yuk: **{caravan.resource_amount:,}** {caravan.resource_type.capitalize()}\n"
                        f"💰 Sof daromad: **+{gold_gain:,}** Oltin\n"
                        f"🎖️ Nufuz: **+{prestige_gain}** ball\n"
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


