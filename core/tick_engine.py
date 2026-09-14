import json
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

                # Himoyachining ajdari (agar qal'a egasi lordining ajdari bo'lsa)
                def_dragon_pwr = 0
                def_lord_id = None
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

                # Jang hisoblash
                battle_res = calculate_battle(
                    attacker_army=att_army,
                    defender_garrison=def_garrison,
                    castle_defense=territory.defense,
                    dragon_power=dragon_pwr,
                    dragon_tactic=dragon_tactic,
                    defender_dragon_power=def_dragon_pwr,
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
                    tot_gold = battle_res["loot"]["gold"]
                    tot_food = battle_res["loot"]["food"]
                    tot_iron = battle_res["loot"]["iron"]

                    attacker.gold += int(tot_gold * 0.7)
                    attacker.food += int(tot_food * 0.7)
                    attacker.iron += int(tot_iron * 0.7)
                    attacker.prestige += 50
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
