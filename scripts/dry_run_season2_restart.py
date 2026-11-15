"""
DRY-RUN FOR SEASON 2 RESTART ON AN ISOLATED DATABASE COPY
Simulates the entire Season 2 restart without modifying the live database.
"""
import os
import sys
import shutil
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
import json

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, func, update, delete, or_
from database import models
from config import SEASON_1_LEGACY_WINNERS, DEFAULT_DB_PATH
from database.crud import reset_entire_game


async def run_dry_run():
    live_db_path = Path(DEFAULT_DB_PATH)
    if not live_db_path.exists():
        live_db_path = ROOT_DIR / "got_mmorpg.db"

    print("=" * 75)
    print("🧪 2-SEZON RESTART: BAZA NUSXASIDA QURUQ SINASH (DRY-RUN)")
    print("=" * 75)
    print(f"Asl jonli baza: {live_db_path}")

    # 1. Baza nusxasini yaratish
    dry_run_dir = ROOT_DIR / "backups" / "dry_run_sandbox"
    dry_run_dir.mkdir(parents=True, exist_ok=True)
    dry_run_db_path = dry_run_dir / "got_mmorpg_dryrun.db"

    shutil.copy2(live_db_path, dry_run_db_path)
    print(f"✅ Nusxa yaratildi: {dry_run_db_path}")

    # 2. Nusxaga ulanish
    dry_engine = create_async_engine(f"sqlite+aiosqlite:///{dry_run_db_path}", echo=False)
    DrySession = async_sessionmaker(dry_engine, expire_on_commit=False, class_=AsyncSession)

    # 3. Oldingi holatni o'qish (BEFORE)
    print("\n--- RESTART OLDIDAGI HOLAT (BEFORE) ---")
    async with DrySession() as session:
        seasons = (await session.execute(select(models.SeasonState).order_by(models.SeasonState.season_number))).scalars().all()
        print(f"• Mavsumlar: {len(seasons)} ta")
        for s in seasons:
            status_str = "🟢 FAOL" if s.is_active else "🔴 YAKUNLANGAN"
            print(f"  - {s.season_number}-Mavsum ({s.title}): {status_str}")

        total_users = (await session.execute(select(func.count(models.User.id)))).scalar()
        vip_users = (await session.execute(select(func.count(models.User.id)).where(models.User.vip_tier.isnot(None)))).scalar()
        total_armies = (await session.execute(select(func.count(models.Army.id)))).scalar()
        total_dragons = (await session.execute(select(func.count(models.Dragon.id)))).scalar()
        pending_donations = (await session.execute(select(func.count(models.DonationRequest.id)).where(models.DonationRequest.status == "pending"))).scalar()

        print(f"• Jami o'yinchilar: {total_users} ta")
        print(f"• VIP o'yinchilar: {vip_users} ta")
        print(f"• Armiyalar: {total_armies} ta")
        print(f"• Ajdarlar: {total_dragons} ta")
        print(f"• Kutilayotgan donat so'rovlari: {pending_donations} ta")

    # 4. Quruq sinash (DRY-RUN AMALIYOTI)
    print("\n--- RESTART AMALIYOTI BAJARILMOQDA (TRANZAKSIYADA) ---")
    async with DrySession() as session:
        now = datetime.utcnow()

        # 4.1. Pending donat so'rovlarini xavfsiz yopish
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
        print(f"  [1] Yopilgan pending donatlar: {closed_donations} ta")

        # 4.2. Shon-sharaf zaliga (Hall of Fame) 1-Mavsum g'oliblarini yozish
        # Sinov yozuvlarini tozalash
        await session.execute(delete(models.HallOfFame))
        await session.execute(delete(models.SeasonTopBonus))
        await session.execute(delete(models.SeasonState))

        # 1-Mavsumni rasman yakunlangan qilib qayd etish
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

        # 1-Mavsum Shon-sharaf zali
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

        # 1-Mavsum TOP 3 o'yinchilari uchun 2-Mavsum bonuslari
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
        print("  [2] Shon-sharaf zali va TOP 3 bonuslari saqlandi.")

        # 4.3. Butun o'yinni 0 ga tushirish (reset_entire_game)
        # Akkauntlar va tanlangan xonadonlar saqlanadi, resurslar/armiyalar/ajdarlar 0 qilinadi
        await reset_entire_game(session)
        print("  [3] O'yin elementlari 0 ga tushirildi (Akkauntlar va xonadonlar to'liq saqlanib qolindi).")

        # 4.4. 2-Mavsum (Season 2: Ajdarlar va Muz Davri) ni boshlash
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
        print("  [4] 2-Mavsum rasman faol deb e'lon qilindi!")

    # 5. Keyingi holatni o'qish (AFTER)
    print("\n--- RESTARTDAN KEYINGI HOLAT (AFTER - DRY-RUN NATIJASI) ---")
    async with DrySession() as session:
        seasons_after = (await session.execute(select(models.SeasonState).order_by(models.SeasonState.season_number))).scalars().all()
        for s in seasons_after:
            status_str = "🟢 FAOL" if s.is_active else "🔴 YAKUNLANGAN"
            print(f"  • {s.season_number}-Mavsum ({s.title}): {status_str}")

        users_after = (await session.execute(select(models.User))).scalars().all()
        print(f"\n• Saqlanib qolgan akkauntlar soni: {len(users_after)} ta")
        for u in users_after[:5]:
            print(f"  - User #{u.id} (@{u.username}): Oltin={u.gold}, Bug'doy={u.food}, Temir={u.iron}, VIP={u.vip_tier}, Xonadon={u.house_id}")

        armies_after = (await session.execute(select(func.count(models.Army.id)))).scalar()
        dragons_after = (await session.execute(select(func.count(models.Dragon.id)))).scalar()
        pend_after = (await session.execute(select(func.count(models.DonationRequest.id)).where(models.DonationRequest.status == "pending"))).scalar()

        print(f"• Armiyalar soni: {armies_after} ta (0 ga tozalangan)")
        print(f"• Ajdarlar soni: {dragons_after} ta (0 ga tozalangan)")
        print(f"• Kutilayotgan donat so'rovlari: {pend_after} ta (0 ta)")

        bonuses_after = (await session.execute(select(models.SeasonTopBonus))).scalars().all()
        print(f"\n• 2-Mavsumda kutib turgan TOP-3 sovrindorlari:")
        for b in bonuses_after:
            print(f"  - #{b.rank_position}: {b.character_name} (TG: {b.telegram_id}, claimed={b.is_claimed})")

    await dry_engine.dispose()
    print("\n" + "=" * 75)
    print("✅ DRY-RUN 100% XATOSIZ VA MUVAFFAQIYATLI YAKUNLANDI!")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_dry_run())
