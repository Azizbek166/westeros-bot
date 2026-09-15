import json
import random
import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import models, AsyncSessionLocal, crud
from core.battle_engine import calculate_battle
from core.economy_engine import process_hourly_tick

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
                                from data.artifacts_data import ARTIFACTS_DATA
                                def_art_bonuses = ARTIFACTS_DATA.get(def_art.code, {})

                # Qal'ada qo'riqchilik qilayotgan xonadon ajdari
                st_dr = crud.get_stationed_dragon_info(territory)
                if st_dr and st_dr.get("power", 0) > def_dragon_pwr:
                    def_dragon_pwr = st_dr["power"]

                # Hujumchining artefakti
                att_art_bonuses = {}
                att_art = await crud.get_equipped_artifact(session, attacker.id)
                if att_art:
                    from data.artifacts_data import ARTIFACTS_DATA
                    att_art_bonuses = ARTIFACTS_DATA.get(att_art.code, {})

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
                )

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
                    # Qal'a egasi o'zgarganda mudofaadagi ajdar uyasiga qaytadi
                    if territory.reinforcements_json:
                        try:
                            import json
                            r_json = json.loads(territory.reinforcements_json)
                            if "stationed_dragon" in r_json:
                                del r_json["stationed_dragon"]
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
                    from core.leveling import check_user_level_up
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
                        try:
                            await bot_app.bot.send_message(
                                chat_id=def_lord_id,
                                text=(
                                    f"🚨 **QAL'A BOY BERILDI!**\n\n"
                                    f"🏰 **{territory.name} ({territory.castle_name})** qal'asi **{att_house_name}** armiyasi tomonidan qamal qilinib, egallab olindi!\n\n"
                                    f"{battle_res['details']}\n\n"
                                    f"Qal'ani qaytarib olish uchun xonadon a'zolaringiz bilan qarshi hujum uyushtiring!"
                                ),
                                parse_mode="Markdown",
                            )
                        except Exception as e:
                            logger.warning(f"Himoyachiga xabar yuborishda xatolik: {e}")
                else:
                    # Himoyachi g'alaba qozondi
                    if bot_app and def_lord_id and old_owner_house_id != attacker.house_id:
                        try:
                            await bot_app.bot.send_message(
                                chat_id=def_lord_id,
                                text=(
                                    f"🛡️ **QAL'A MUVAFFAQIYATLI HIMOYALANDI!**\n\n"
                                    f"🏰 **{territory.name} ({territory.castle_name})** qal'angizga bo'lgan dushman hujumi jasorat bilan qaytarildi!\n\n"
                                    f"{battle_res['details']}\n"
                                ),
                                parse_mode="Markdown",
                            )
                        except Exception as e:
                            logger.warning(f"Himoyachiga xabar yuborishda xatolik: {e}")

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
                    try:
                        res_emoji = "🏆 **G'ALABA! QAL'A ZABT ETILDI!**" if battle_res["winner"] == "attacker" else "🛡️ **MAG'LUBIYAT! HUJUM QAYTARILDI.**"
                        att_loss_str = ", ".join(f"{t}: {c}" for t, c in battle_res["attacker_losses"].items() if c > 0) or "Yo'qotishlar yo'q"
                        def_loss_str = ", ".join(f"{t}: {c}" for t, c in battle_res["defender_losses"].items() if c > 0) or "Yo'qotishlar yo'q"

                        msg = (
                            f"⚔️ **JANG HISOBOTI: {territory.name.upper()} ({territory.castle_name})**\n\n"
                            f"{res_emoji}\n\n"
                            f"{battle_res['details']}\n\n"
                            f"👥 **Talofatlar:**\n"
                            f"• Bizning armiya: {att_loss_str}\n"
                            f"• Qal'a garnizoni: {def_loss_str}\n\n"
                            f"💰 **Qo'lga kiritilgan o'lja:**\n"
                            f"🪙 +{battle_res['loot']['gold']} oltin | 🌾 +{battle_res['loot']['food']} g'alla | ⛓️ +{battle_res['loot']['iron']} temir\n\n"
                            f"Batafsil ma'lumotni /battle bo'limida ko'rishingiz mumkin."
                        )
                        await bot_app.bot.send_message(
                            chat_id=attacker.telegram_id,
                            text=msg,
                            parse_mode="Markdown",
                        )
                    except Exception as e:
                        logger.warning(f"Hujumchiga xabar yuborishda xatolik: {e}")

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
                data_json=json.dumps({"army": 250000, "stage": 1, "status": "marching"}),
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

                    battle_res = calculate_battle(
                        attacker_army=att_army,
                        defender_garrison=def_garrison,
                        castle_defense=target_terr.defense,
                        dragon_power=0,
                        defender_dragon_power=def_dr_pwr,
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

        await session.commit()

