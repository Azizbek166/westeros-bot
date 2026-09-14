import json
import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import models, AsyncSessionLocal
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

            # Ajdar tekshiruvi (faqat to'q bo'lsa jangda qatnashadi)
            dragon = await crud.get_user_dragon(session, attacker.id)
            dragon_pwr = 0
            if dragon and dragon.stage in ["baby", "adult"]:
                if dragon.hunger >= 20:
                    dragon_pwr = dragon.power
                    dragon.hunger = max(0, dragon.hunger - 25)  # Jangda kuch sarflaydi
                else:
                    logger.info(f"{dragon.name} juda och bo'lgani sababli jangda qatnasha olmadi.")

            # Jang hisoblash
            battle_res = calculate_battle(
                attacker_army=att_army,
                defender_garrison=def_garrison,
                castle_defense=territory.defense,
                dragon_power=dragon_pwr,
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

            # Agar hujumchi yutsa: Hududni egallash va o'lja (70% shaxsiy, 30% xonadon xazinasi)
            old_owner_house_id = territory.owner_house_id
            if battle_res["winner"] == "attacker":
                territory.owner_house_id = attacker.house_id
                tot_gold = battle_res["loot"]["gold"]
                tot_food = battle_res["loot"]["food"]
                tot_iron = battle_res["loot"]["iron"]

                attacker.gold += int(tot_gold * 0.7)
                attacker.food += int(tot_food * 0.7)
                attacker.iron += int(tot_iron * 0.7)
                attacker.prestige += 50

                att_house = await session.get(models.House, attacker.house_id)
                if att_house:
                    att_house.gold += int(tot_gold * 0.3)
                    att_house.food += int(tot_food * 0.3)
                    att_house.iron += int(tot_iron * 0.3)
                    att_house.prestige += 25

                # Himoyachiga ogohlantirish
                if bot_app and old_owner_house_id and old_owner_house_id != attacker.house_id:
                    def_h = await session.get(models.House, old_owner_house_id)
                    if def_h and def_h.lord_user_id:
                        try:
                            await bot_app.bot.send_message(
                                chat_id=def_h.lord_user_id,
                                text=f"🚨 **QAL'A BOY BERILDI!**\n\n{territory.name} ({territory.castle_name}) qal'asi dushman tomonidan zabt etildi!",
                                parse_mode="Markdown"
                            )
                        except Exception:
                            pass

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

            # Telegram orqali xabar yuborish
            if bot_app and attacker.telegram_id:
                try:
                    res_emoji = "🏆 G'alaba!" if battle_res["winner"] == "attacker" else "🛡️ Mag'lubiyat!"
                    msg = (
                        f"⚔️ **JANG HISOBOTI: {territory.name}**\n\n"
                        f"{res_emoji}\n"
                        f"{battle_res['details']}\n\n"
                        f"💰 O'lja: +{battle_res['loot']['gold']} oltin, +{battle_res['loot']['food']} oziq-ovqat, +{battle_res['loot']['iron']} temir\n\n"
                        f"Batafsil /battle orqali ko'ring."
                    )
                    await bot_app.bot.send_message(
                        chat_id=attacker.telegram_id,
                        text=msg,
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.warning(f"Xabar yuborishda xatolik: {e}")

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
