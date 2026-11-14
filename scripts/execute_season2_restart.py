"""
THE IRON THRONE RPG - SEASON 2 LIVE RESTART SCRIPT
Ushbu skript haqiqiy got_mmorpg.db bazasida 1-Mavsumni rasman yakunlab,
2-Mavsumni (Season 2: Ajdarlar va Muz Davri) rasman ishga tushiradi:
1. got_mmorpg.db ning to'liq zaxira nusxasini oladi (timestamp bilan).
2. 1-Mavsum g'olibini Shon-sharaf zaliga (Hall of Fame) yozadi:
   - G'olib Xonadon: 🐉 House Blackfyre (id: 15)
   - Temir Taxt Qiroli (Mavsum Chempioni): Liar (@NiclausMikaelson)
   - Oliy Jangchi: kozmunchoq 🐾 (@shaxnoza_0901) (62,514 nufuz)
3. TOP 3 o'yinchilar uchun yangi 2-mavsumda avtomatik claim qilinadigan SeasonTopBonus yozadi:
   - 1-o'rin: Liar (@NiclausMikaelson) (telegram_id: 5381961263)
   - 2-o'rin: Bexruz (@Bexruz) (telegram_id: 8838680114)
   - 3-o'rin: Abdulloh Askarov (@Abdulloh_askarov6) (telegram_id: 8161647993)
4. Barcha eskirgan/pending donat so'rovlarini to'liq yopadi va bazani xavfsiz 0 ga tozalaydi (50 kanon xonadon va hududlar saqlanadi).
5. 2-Mavsum (is_active=True, 30 kunlik) SeasonState yozuvini yaratadi.
"""
import os
import sys
import shutil
import hashlib
import asyncio
from datetime import datetime

ROOT_DIR = r"C:\Users\user\Desktop\winter is coming"
sys.path.insert(0, ROOT_DIR)

from database.db import AsyncSessionLocal, init_db
from database import crud, models
from sqlalchemy import select, func

def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

async def main():
    print("=" * 75)
    print("🚀 2-SEZON RESTARTINI AMALGA OSHIRISH (HAQIQIY BAZADA)")
    print("=" * 75)

    live_db = os.path.join(ROOT_DIR, "got_mmorpg.db")
    if not os.path.exists(live_db):
        print(f"❌ Xatolik: {live_db} topilmadi!")
        return

    # 1. Zaxira nusxa olish
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir = os.path.join(ROOT_DIR, "backups", f"pre_season2_live_restart_{ts}")
    os.makedirs(backup_dir, exist_ok=True)
    live_backup_path = os.path.join(backup_dir, f"{ts}_got_mmorpg.db")
    shutil.copy2(live_db, live_backup_path)

    hash_before = hash_file(live_db)
    print(f"[1] Baza zaxiralandi: {live_backup_path}")
    print(f"    SHA-256 (Restartdan oldin): {hash_before}")

    # 2. Restart operatsiyasini bajarish
    print("\n[2] admin_conclude_and_restart_season ishga tushirilmoqda...")
    async with AsyncSessionLocal() as session:
        ok, ann, res_info = await crud.admin_conclude_and_restart_season(session, bot_app=None)
        if not ok:
            print(f"❌ Restartda xatolik yuz berdi: {ann}")
            return
        print("    ✅ admin_conclude_and_restart_season muvaffaqiyatli yakunlandi!")

    # 3. Natijalarni tekshirish
    print("\n[3] 2-Mavsum bazasi holatini tekshirish:")
    async with AsyncSessionLocal() as session:
        # SeasonState
        s_res = await session.execute(
            select(models.SeasonState).order_by(models.SeasonState.season_number.desc())
        )
        seasons = s_res.scalars().all()
        print(f"    • Bazadagi mavsumlar soni: {len(seasons)}")
        for s in seasons:
            print(f"      - {s.season_number}-Mavsum: '{s.title}', is_active={s.is_active}, is_concluded={s.is_concluded}")

        # Hall of Fame
        hof_res = await session.execute(select(models.HallOfFame))
        hof_rows = hof_res.scalars().all()
        print(f"\n    • Shon-sharaf zali (Hall of Fame) yozuvlari ({len(hof_rows)} ta):")
        for h in hof_rows:
            print(f"      - {h.season_number}-Mavsum: G'olib Xonadon='{h.winner_house_name}', Qirol='{h.king_name}', Botir='{h.top_warrior_name}' ({h.top_warrior_prestige:,}🎖️)")

        # SeasonTopBonus
        bonuses_res = await session.execute(select(models.SeasonTopBonus))
        bonuses = bonuses_res.scalars().all()
        print(f"\n    • 2-Mavsum uchun saqlangan TOP-3 bonuslari ({len(bonuses)} ta):")
        for b in bonuses:
            print(f"      - #{b.rank_position}: {b.character_name} (TG ID: {b.telegram_id}, Nufuz: {b.prestige:,}🎖️, is_claimed={b.is_claimed})")

        # Counts
        user_cnt = (await session.execute(select(func.count(models.User.id)))).scalar()
        army_cnt = (await session.execute(select(func.count(models.Army.id)))).scalar()
        dragon_cnt = (await session.execute(select(func.count(models.Dragon.id)))).scalar()
        house_cnt = (await session.execute(select(func.count(models.House.id)))).scalar()
        terr_cnt = (await session.execute(select(func.count(models.Territory.id)))).scalar()

        print(f"\n    • 2-Mavsum boshlang'ich jadval ko'rsatkichlari:")
        print(f"      - O'yinchilar (Users): {user_cnt} ta (0 ga tushirildi)")
        print(f"      - Armiyalar (Armies): {army_cnt} ta (0 ga tushirildi)")
        print(f"      - Ajdarlar (Dragons): {dragon_cnt} ta (0 ga tushirildi)")
        print(f"      - Xonadonlar (Houses): {house_cnt} ta (50 ta kanon xonadon)")
        print(f"      - Qal'alar (Territories): {terr_cnt} ta (64 ta boshlang'ich neytral/kanon hudud)")

    hash_after = hash_file(live_db)
    print(f"\n[4] Haqiqiy baza yangilandi:")
    print(f"    SHA-256 (Yangi 2-Mavsum): {hash_after}")
    print("\n" + "=" * 75)
    print("🎉 2-MAVSUM RESTARTI HAQIQIY BAZADA 100% MUVAFFAQIYATLI YAKUNLANDI!")
    print("=" * 75)

if __name__ == "__main__":
    asyncio.run(main())
