"""
THE IRON THRONE RPG - SEASON 2 LIVE RESTART SCRIPT
Ushbu skript haqiqiy got_mmorpg.db bazasida 1-Mavsumni rasman yakunlab,
2-Mavsumni (Season 2: Ajdarlar va Muz Davri) rasman ishga tushiradi:
1. got_mmorpg.db ning to'liq zaxira nusxasini oladi (timestamp bilan).
2. Pending donat so'rovlarini to'liq yopadi.
3. 1-Mavsum g'oliblarini Shon-sharaf zaliga (Hall of Fame) yozadi (SEASON_1_LEGACY_WINNERS dan).
4. TOP 3 o'yinchilar uchun yangi 2-mavsumda avtomatik claim qilinadigan SeasonTopBonus yozadi.
5. Bazani xavfsiz 0 ga tozalaydi (akkauntlar va tanlangan xonadonlar to'liq saqlanadi).
6. 2-Mavsum (is_active=True, 30 kunlik) SeasonState yozuvini yaratadi.
"""
import os
import sys
import shutil
import hashlib
import asyncio
import json
from pathlib import Path
from datetime import datetime, timedelta

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select, func, update, delete
from config import SEASON_1_LEGACY_WINNERS, DEFAULT_DB_PATH
from database.db import AsyncSessionLocal, init_db
from database import models
from database.crud import reset_entire_game


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


async def execute_live_season2_restart():
    live_db = Path(DEFAULT_DB_PATH)
    if not live_db.exists():
        live_db = ROOT_DIR / "got_mmorpg.db"

    print("=" * 75)
    print("🚀 2-SEZON RESTARTINI AMALGA OSHIRISH (HAQIQIY BAZADA)")
    print("=" * 75)

    if not live_db.exists():
        print(f"❌ Xatolik: {live_db} topilmadi!")
        return

    # 1. Zaxira nusxa olish
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir = ROOT_DIR / "backups" / f"pre_season2_live_restart_{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    live_backup_path = backup_dir / f"{ts}_got_mmorpg.db"
    shutil.copy2(live_db, live_backup_path)

    hash_before = hash_file(str(live_db))
    print(f"[1] Baza zaxiralandi: {live_backup_path}")
    print(f"    SHA-256 (Restartdan oldin): {hash_before}")

    # 2. Restart operatsiyasini bajarish (Bitta tranzaksiya ichida)
    print("\n[2] Tranzaksiya ichida 2-Mavsum restarti boshlanmoqda...")
    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()

        # 2.1. Pending donat so'rovlarini xavfsiz yopish
        res_pend = await session.execute(
            update(models.DonationRequest)
            .where(models.DonationRequest.status == "pending")
            .values(
                status="rejected",
                admin_notes="1-Mavsum yakunlandi — Season 2 restarti oldidan avtomatik yopildi.",
                reviewed_at=now,
            )
        )
        closed_donations = res_pend.rowcount
        print(f"    • Kutilayotgan donat so'rovlari yopildi: {closed_donations} ta")

        # 2.2. Test va eski sinov yozuvlarini tozalash
        await session.execute(delete(models.HallOfFame))
        await session.execute(delete(models.SeasonTopBonus))
        await session.execute(delete(models.SeasonState))

        # 2.3. 1-Mavsumni yakunlangan deb qayd etish
        s1 = models.SeasonState(
            season_number=1,
            title="1-Mavsum: Temir Taxt Qadami",
            theme_description="Vesterosda hukmronlik uchun kurashning ilk mavsumi.",
            start_date=now - timedelta(days=30),
            end_date=now,
            is_active=False,
            is_concluded=True,
            snapshot_data="{}",
            created_at=now - timedelta(days=30),
        )
        session.add(s1)

        # 2.4. 1-Mavsum Shon-sharaf zali (Hall of Fame)
        hof = models.HallOfFame(
            season_number=1,
            winner_house_id=SEASON_1_LEGACY_WINNERS["winner_house_id"],
            winner_house_name=SEASON_1_LEGACY_WINNERS["winner_house_name"],
            king_user_id=None,
            king_name=SEASON_1_LEGACY_WINNERS["king_name"],
            top_warrior_name=SEASON_1_LEGACY_WINNERS["top_warrior_name"],
            top_warrior_prestige=SEASON_1_LEGACY_WINNERS["top_warrior_prestige"],
            top_so_user_id=None,
            top_so_player_name=SEASON_1_LEGACY_WINNERS["king_name"],
            top_so_points=SEASON_1_LEGACY_WINNERS["top_warrior_prestige"],
            top_guild_name=SEASON_1_LEGACY_WINNERS["winner_house_name"],
            snapshot_json=json.dumps([
                {"rank": item["rank"], "name": item["name"], "house_name": item["house"], "prestige": item["prestige"]}
                for item in SEASON_1_LEGACY_WINNERS["top3"]
            ]),
            concluded_at=now,
        )
        session.add(hof)

        # 2.5. 1-Mavsum TOP 3 g'oliblariga 2-Mavsum bonuslari
        for item in SEASON_1_LEGACY_WINNERS["top3"]:
            b_entry = models.SeasonTopBonus(
                season_number=1,
                telegram_id=item["telegram_id"],
                character_name=item["name"],
                rank_position=item["rank"],
                prestige=item["prestige"],
                is_claimed=False,
                created_at=now,
            )
            session.add(b_entry)
        print("    • Shon-sharaf zali va TOP 3 sovrindorlari muhrlandi.")

        # 2.6. O'yin ma'lumotlarini 0 ga tushirish (Akkauntlar va xonadonlar saqlanadi!)
        await reset_entire_game(session)
        print("    • Butun o'yin 0 ga tushirildi (Akkauntlar va xonadonlar saqlandi).")

        # 2.7. 2-Mavsum (Season 2: Ajdarlar va Muz Davri) ni boshlash
        s2 = models.SeasonState(
            season_number=2,
            title="2-Mavsum: Ajdarlar va Muz Davri",
            theme_description="Qish kirib keldi. Vesterosda o't va muz to'qnashuvi boshlandi!",
            start_date=now,
            end_date=now + timedelta(days=30),
            is_active=True,
            is_concluded=False,
            created_at=now,
        )
        session.add(s2)

        await session.commit()
        print("    ✅ 2-Mavsum muvaffaqiyatli ishga tushirildi!")

    # 3. Natijalarni tekshirish
    print("\n[3] 2-Mavsum bazasi yakuniy ko'rsatkichlari:")
    async with AsyncSessionLocal() as session:
        seasons = (await session.execute(select(models.SeasonState).order_by(models.SeasonState.season_number))).scalars().all()
        for s in seasons:
            status_str = "🟢 FAOL" if s.is_active else "🔴 YAKUNLANGAN"
            print(f"    • {s.season_number}-Mavsum ({s.title}): {status_str}")

        user_cnt = (await session.execute(select(func.count(models.User.id)))).scalar()
        army_cnt = (await session.execute(select(func.count(models.Army.id)))).scalar()
        dragon_cnt = (await session.execute(select(func.count(models.Dragon.id)))).scalar()
        house_cnt = (await session.execute(select(func.count(models.House.id)))).scalar()
        terr_cnt = (await session.execute(select(func.count(models.Territory.id)))).scalar()
        pend_cnt = (await session.execute(select(func.count(models.DonationRequest.id)).where(models.DonationRequest.status == "pending"))).scalar()

        print(f"    • O'yinchilar (Users): {user_cnt} ta (Akkauntlar saqlanib qolindi)")
        print(f"    • Armiyalar (Armies): {army_cnt} ta (0 ga tushirildi)")
        print(f"    • Ajdarlar (Dragons): {dragon_cnt} ta (0 ga tushirildi)")
        print(f"    • Xonadonlar (Houses): {house_cnt} ta")
        print(f"    • Qal'alar (Territories): {terr_cnt} ta")
        print(f"    • Kutilayotgan donat so'rovlari: {pend_cnt} ta")

        bonuses = (await session.execute(select(models.SeasonTopBonus))).scalars().all()
        print(f"\n    • 2-Mavsumda bonus kutayotgan TOP-3:")
        for b in bonuses:
            print(f"      - #{b.rank_position}: {b.character_name} (TG ID: {b.telegram_id}, claimed={b.is_claimed})")

    hash_after = hash_file(str(live_db))
    print(f"\n[4] Haqiqiy baza yangilandi:")
    print(f"    SHA-256 (Yangi 2-Mavsum): {hash_after}")
    print("\n" + "=" * 75)
    print("🎉 2-MAVSUM RESTARTI HAQIQIY BAZADA 100% MUVAFFAQIYATLI YAKUNLANDI!")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(execute_live_season2_restart())
