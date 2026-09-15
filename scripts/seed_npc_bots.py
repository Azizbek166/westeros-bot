"""
Westeros MMORPG - Seed NPC Bots Script
Creates 20 active lore-friendly NPC lords across Westeros houses with characters, armies, and dragons.
"""

import sys
import os
import asyncio
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from database import AsyncSessionLocal, models, init_db

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


NPC_BOTS_DATA = [
    {
        "tid": 990000001,
        "username": "tywin_lannister",
        "full_name": "Lord Tywin Lannister",
        "house_code": "lannister",
        "rank": "king",
        "level": 25,
        "xp": 18000,
        "gold": 35000,
        "food": 25000,
        "iron": 15000,
        "prestige": 950,
        "char_name": "Tywin Lannister",
        "attack": 85,
        "defense": 95,
        "leadership": 100,
        "infantry": 800,
        "archers": 600,
        "cavalry": 450,
        "spearmen": 500,
        "special": 80,
        "artifact": "widows_wail",
    },
    {
        "tid": 990000002,
        "username": "jaime_lannister",
        "full_name": "Ser Jaime Lannister",
        "house_code": "lannister",
        "rank": "commander",
        "level": 22,
        "xp": 14000,
        "gold": 12000,
        "food": 15000,
        "iron": 8000,
        "prestige": 750,
        "char_name": "Jaime Lannister",
        "attack": 96,
        "defense": 88,
        "leadership": 85,
        "infantry": 500,
        "archers": 400,
        "cavalry": 400,
        "spearmen": 300,
        "special": 60,
    },
    {
        "tid": 990000003,
        "username": "robb_stark",
        "full_name": "King Robb Stark",
        "house_code": "stark",
        "rank": "king",
        "level": 24,
        "xp": 16500,
        "gold": 18000,
        "food": 30000,
        "iron": 12000,
        "prestige": 900,
        "char_name": "Robb Stark",
        "attack": 90,
        "defense": 85,
        "leadership": 95,
        "infantry": 750,
        "archers": 550,
        "cavalry": 350,
        "spearmen": 450,
        "special": 70,
        "artifact": "ice",
    },
    {
        "tid": 990000004,
        "username": "jon_snow",
        "full_name": "Lord Commander Jon Snow",
        "house_code": "stark",
        "rank": "commander",
        "level": 21,
        "xp": 13000,
        "gold": 8000,
        "food": 18000,
        "iron": 6000,
        "prestige": 720,
        "char_name": "Jon Snow",
        "attack": 92,
        "defense": 90,
        "leadership": 90,
        "infantry": 450,
        "archers": 400,
        "cavalry": 250,
        "spearmen": 350,
        "special": 50,
        "artifact": "longclaw",
    },
    {
        "tid": 990000005,
        "username": "daenerys_targaryen",
        "full_name": "Queen Daenerys Targaryen",
        "house_code": "targaryen",
        "rank": "king",
        "level": 26,
        "xp": 20000,
        "gold": 28000,
        "food": 22000,
        "iron": 14000,
        "prestige": 1100,
        "char_name": "Daenerys Targaryen",
        "attack": 80,
        "defense": 80,
        "leadership": 98,
        "infantry": 700,
        "archers": 400,
        "cavalry": 300,
        "spearmen": 600,
        "special": 120,
        "dragon": ("Drogon", "A", 16, 750),
        "artifact": "dragonbinder",
    },
    {
        "tid": 990000006,
        "username": "daemon_targaryen",
        "full_name": "Prince Daemon Targaryen",
        "house_code": "targaryen",
        "rank": "commander",
        "level": 25,
        "xp": 17500,
        "gold": 16000,
        "food": 15000,
        "iron": 10000,
        "prestige": 900,
        "char_name": "Daemon Targaryen",
        "attack": 98,
        "defense": 86,
        "leadership": 92,
        "infantry": 500,
        "archers": 350,
        "cavalry": 300,
        "spearmen": 350,
        "special": 90,
        "dragon": ("Caraxes", "A", 15, 700),
    },
    {
        "tid": 990000007,
        "username": "stannis_baratheon",
        "full_name": "King Stannis Baratheon",
        "house_code": "baratheon",
        "rank": "king",
        "level": 23,
        "xp": 15000,
        "gold": 15000,
        "food": 20000,
        "iron": 11000,
        "prestige": 820,
        "char_name": "Stannis Baratheon",
        "attack": 88,
        "defense": 92,
        "leadership": 94,
        "infantry": 650,
        "archers": 500,
        "cavalry": 300,
        "spearmen": 400,
        "special": 60,
    },
    {
        "tid": 990000008,
        "username": "renly_baratheon",
        "full_name": "Lord Renly Baratheon",
        "house_code": "baratheon",
        "rank": "commander",
        "level": 18,
        "xp": 10000,
        "gold": 22000,
        "food": 25000,
        "iron": 9000,
        "prestige": 680,
        "char_name": "Renly Baratheon",
        "attack": 78,
        "defense": 80,
        "leadership": 86,
        "infantry": 450,
        "archers": 350,
        "cavalry": 350,
        "spearmen": 300,
        "special": 40,
    },
    {
        "tid": 990000009,
        "username": "olenna_tyrell",
        "full_name": "Lady Olenna Tyrell",
        "house_code": "tyrell",
        "rank": "king",
        "level": 25,
        "xp": 18500,
        "gold": 45000,
        "food": 60000,
        "iron": 12000,
        "prestige": 1050,
        "char_name": "Olenna Tyrell",
        "attack": 70,
        "defense": 90,
        "leadership": 99,
        "infantry": 850,
        "archers": 700,
        "cavalry": 500,
        "spearmen": 600,
        "special": 90,
    },
    {
        "tid": 990000010,
        "username": "loras_tyrell",
        "full_name": "Ser Loras Tyrell",
        "house_code": "tyrell",
        "rank": "commander",
        "level": 20,
        "xp": 12000,
        "gold": 14000,
        "food": 20000,
        "iron": 8000,
        "prestige": 700,
        "char_name": "Loras Tyrell",
        "attack": 94,
        "defense": 84,
        "leadership": 82,
        "infantry": 400,
        "archers": 350,
        "cavalry": 450,
        "spearmen": 300,
        "special": 50,
    },
    {
        "tid": 990000011,
        "username": "euron_greyjoy",
        "full_name": "King Euron Greyjoy",
        "house_code": "greyjoy",
        "rank": "king",
        "level": 24,
        "xp": 16000,
        "gold": 20000,
        "food": 14000,
        "iron": 16000,
        "prestige": 880,
        "char_name": "Euron Greyjoy",
        "attack": 95,
        "defense": 85,
        "leadership": 90,
        "infantry": 700,
        "archers": 450,
        "cavalry": 150,
        "spearmen": 550,
        "special": 85,
    },
    {
        "tid": 990000012,
        "username": "victarion_greyjoy",
        "full_name": "Lord Captain Victarion Greyjoy",
        "house_code": "greyjoy",
        "rank": "commander",
        "level": 22,
        "xp": 13500,
        "gold": 11000,
        "food": 12000,
        "iron": 10000,
        "prestige": 740,
        "char_name": "Victarion Greyjoy",
        "attack": 95,
        "defense": 92,
        "leadership": 84,
        "infantry": 500,
        "archers": 300,
        "cavalry": 100,
        "spearmen": 400,
        "special": 60,
    },
    {
        "tid": 990000013,
        "username": "doran_martell",
        "full_name": "Prince Doran Martell",
        "house_code": "martell",
        "rank": "king",
        "level": 23,
        "xp": 15500,
        "gold": 25000,
        "food": 18000,
        "iron": 11000,
        "prestige": 860,
        "char_name": "Doran Martell",
        "attack": 65,
        "defense": 94,
        "leadership": 96,
        "infantry": 600,
        "archers": 550,
        "cavalry": 350,
        "spearmen": 650,
        "special": 75,
    },
    {
        "tid": 990000014,
        "username": "oberyn_martell",
        "full_name": "Prince Oberyn Martell",
        "house_code": "martell",
        "rank": "commander",
        "level": 23,
        "xp": 15000,
        "gold": 13000,
        "food": 14000,
        "iron": 7500,
        "prestige": 800,
        "char_name": "Oberyn Martell",
        "attack": 98,
        "defense": 82,
        "leadership": 88,
        "infantry": 450,
        "archers": 400,
        "cavalry": 300,
        "spearmen": 500,
        "special": 70,
    },
    {
        "tid": 990000015,
        "username": "roose_bolton",
        "full_name": "Lord Roose Bolton",
        "house_code": "bolton",
        "rank": "king",
        "level": 22,
        "xp": 14500,
        "gold": 16000,
        "food": 16000,
        "iron": 9000,
        "prestige": 790,
        "char_name": "Roose Bolton",
        "attack": 84,
        "defense": 88,
        "leadership": 91,
        "infantry": 600,
        "archers": 450,
        "cavalry": 250,
        "spearmen": 400,
        "special": 55,
    },
    {
        "tid": 990000016,
        "username": "ramsay_bolton",
        "full_name": "Ramsay Bolton",
        "house_code": "bolton",
        "rank": "commander",
        "level": 19,
        "xp": 11000,
        "gold": 9000,
        "food": 12000,
        "iron": 7000,
        "prestige": 650,
        "char_name": "Ramsay Bolton",
        "attack": 90,
        "defense": 78,
        "leadership": 82,
        "infantry": 400,
        "archers": 350,
        "cavalry": 200,
        "spearmen": 300,
        "special": 50,
    },
    {
        "tid": 990000017,
        "username": "brynden_tully",
        "full_name": "Ser Brynden Tully (Blackfish)",
        "house_code": "tully",
        "rank": "commander",
        "level": 23,
        "xp": 15000,
        "gold": 12000,
        "food": 22000,
        "iron": 8500,
        "prestige": 820,
        "char_name": "Brynden Tully",
        "attack": 91,
        "defense": 94,
        "leadership": 94,
        "infantry": 500,
        "archers": 500,
        "cavalry": 300,
        "spearmen": 450,
        "special": 60,
    },
    {
        "tid": 990000018,
        "username": "edmute_tully",
        "full_name": "Lord Edmure Tully",
        "house_code": "tully",
        "rank": "king",
        "level": 20,
        "xp": 11500,
        "gold": 17000,
        "food": 28000,
        "iron": 9000,
        "prestige": 730,
        "char_name": "Edmure Tully",
        "attack": 76,
        "defense": 82,
        "leadership": 80,
        "infantry": 600,
        "archers": 450,
        "cavalry": 250,
        "spearmen": 400,
        "special": 45,
    },
    {
        "tid": 990000019,
        "username": "yohn_royce",
        "full_name": "Bronze Yohn Royce",
        "house_code": "arryn",
        "rank": "commander",
        "level": 22,
        "xp": 13800,
        "gold": 14000,
        "food": 19000,
        "iron": 11000,
        "prestige": 790,
        "char_name": "Yohn Royce",
        "attack": 92,
        "defense": 95,
        "leadership": 91,
        "infantry": 550,
        "archers": 400,
        "cavalry": 400,
        "spearmen": 400,
        "special": 65,
    },
    {
        "tid": 990000020,
        "username": "arthur_dayne",
        "full_name": "Ser Arthur Dayne",
        "house_code": "martell",
        "rank": "knight",
        "level": 25,
        "xp": 18000,
        "gold": 15000,
        "food": 15000,
        "iron": 10000,
        "prestige": 900,
        "char_name": "Arthur Dayne",
        "attack": 100,
        "defense": 98,
        "leadership": 88,
        "infantry": 400,
        "archers": 300,
        "cavalry": 350,
        "spearmen": 350,
        "special": 80,
        "artifact": "shield_morning",
    },
]


async def seed_npc_bots():
    print("🚀 Vesteros bo'ylab NPC Lordlarni yaratish boshlandi...")
    await init_db()
    async with AsyncSessionLocal() as session:
        # Xonadonlar xaritasini olish
        res = await session.execute(select(models.House))
        houses = res.scalars().all()
        house_map = {h.code.lower(): h for h in houses}

        created_count = 0
        updated_count = 0

        for b in NPC_BOTS_DATA:
            res = await session.execute(
                select(models.User).where(models.User.telegram_id == b["tid"])
            )
            user = res.scalar_one_or_none()

            # Xonadonni topish
            house = house_map.get(b["house_code"].lower())
            house_id = house.id if house else (houses[0].id if houses else None)

            if not user:
                user = models.User(
                    telegram_id=b["tid"],
                    username=b["username"],
                    full_name=b["full_name"],
                    house_id=house_id,
                    rank=b["rank"],
                    level=b["level"],
                    xp=b["xp"],
                    gold=b["gold"],
                    food=b["food"],
                    iron=b["iron"],
                    prestige=b["prestige"],
                )
                session.add(user)
                await session.flush()

                # Character
                hero = models.Character(
                    user_id=user.id,
                    house_id=house_id,
                    name=b["char_name"],
                    attack=b["attack"],
                    defense=b["defense"],
                    leadership=b["leadership"],
                )
                session.add(hero)

                # Army
                army = models.Army(
                    user_id=user.id,
                    infantry=b["infantry"],
                    archers=b["archers"],
                    cavalry=b["cavalry"],
                    spearmen=b["spearmen"],
                    special_troops=b["special"],
                )
                session.add(army)

                # Dragon (agar bo'lsa)
                if "dragon" in b:
                    d_name, d_grade, d_lvl, d_pwr = b["dragon"]
                    dragon = models.Dragon(
                        user_id=user.id,
                        name=d_name,
                        grade=d_grade,
                        stage="adult",
                        level=d_lvl,
                        power=d_pwr,
                        hunger=80,
                    )
                    session.add(dragon)

                # Artifact (agar bo'lsa)
                if "artifact" in b:
                    from data.artifacts_data import ARTIFACTS_DATA
                    art_code = b["artifact"]
                    if art_code in ARTIFACTS_DATA:
                        art = models.Artifact(
                            user_id=user.id,
                            code=art_code,
                            name=ARTIFACTS_DATA[art_code]["name"],
                            type=ARTIFACTS_DATA[art_code]["type"],
                            is_equipped=True,
                        )
                        session.add(art)
                        await session.flush()
                        user.equipped_artifact_id = art.id

                # HouseMember
                if house_id:
                    hm = models.HouseMember(
                        user_id=user.id,
                        house_id=house_id,
                        rank=b["rank"],
                        contribution_gold=b["gold"] // 3,
                        contribution_food=b["food"] // 3,
                        contribution_iron=b["iron"] // 3,
                    )
                    session.add(hm)

                created_count += 1
                print(f"  [+] Yaratildi: {b['full_name']} ({b['house_code'].title()}, Lv.{b['level']})")
            else:
                user.level = b["level"]
                user.xp = b["xp"]
                user.prestige = b["prestige"]
                updated_count += 1

        await session.commit()
        print(f"\n✅ Tugallandi! {created_count} ta yangi NPC lord yaratildi, {updated_count} ta yangilandi.")


if __name__ == "__main__":
    asyncio.run(seed_npc_bots())
