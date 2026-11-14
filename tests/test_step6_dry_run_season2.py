import asyncio
import hashlib
import os
import shutil
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

import config
from database import models, crud
import services


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


async def run_step6_dry_run():
    print("=" * 72)
    print("6-QADAM: RESTARTDAN OLDINGI YAKUNIY TEKSHIRUV VA DRY-RUN (BAZA NUSXASIDA)")
    print("=" * 72)

    live_db_path = os.path.abspath("got_mmorpg.db")
    dry_run_dir = os.path.abspath(os.path.join("backups", "dry_run_test"))
    os.makedirs(dry_run_dir, exist_ok=True)
    dry_run_db_path = os.path.join(dry_run_dir, "dry_run_got_mmorpg.db")

    # 1. Live DB hash before dry-run
    live_hash_before = sha256_file(live_db_path)
    for ext in ("", "-wal", "-shm"):
        p = dry_run_db_path + ext
        if os.path.exists(p):
            os.remove(p)
    shutil.copy2(live_db_path, dry_run_db_path)
    print(f"[1] Haqiqiy baza nusxasi olindi: {dry_run_db_path}")
    print(f"    Live DB SHA-256 (oldin): {live_hash_before}")

    engine = create_async_engine(f"sqlite+aiosqlite:///{dry_run_db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with SessionLocal() as session:
        # 2. Check pending donation requests in live DB copy
        pend_res = await session.execute(
            select(models.DonationRequest).where(models.DonationRequest.status == "pending")
        )
        pending_list = list(pend_res.scalars().all())
        app_cnt = (await session.execute(
            select(func.count(models.DonationRequest.id)).where(models.DonationRequest.status == "approved")
        )).scalar() or 0
        rej_cnt = (await session.execute(
            select(func.count(models.DonationRequest.id)).where(models.DonationRequest.status == "rejected")
        )).scalar() or 0
        print(f"\n[2] Donat so'rovlari holati (Baza nusxasida):")
        print(f"    • Kutilayotgan (pending): {len(pending_list)} ta")
        print(f"    • Tasdiqlangan (approved): {app_cnt} ta")
        print(f"    • Rad etilgan (rejected): {rej_cnt} ta")
        assert len(pending_list) == 0, "Haqiqiy bazada ko'rib chiqilmagan pending so'rov qolmasligi kerak!"

        # Inject a simulated leftover pending request from Season 1 to test auto-close on restart
        mock_old_req = models.DonationRequest(
            user_id=1,
            telegram_id=7689627859,
            user_full_name="Test Old Season User",
            user_username="old_season_user",
            tier_id="knight",
            tier_name="Kichik Resurs Paketi",
            price_uzs=10000,
            price_label="10,000 so'm",
            receipt_file_id="old_season_receipt_1",
            status="pending",
            created_at=datetime.utcnow() - timedelta(days=5),
        )
        session.add(mock_old_req)
        await session.commit()
        await session.refresh(mock_old_req)
        mock_old_req_id = mock_old_req.id

        # 3. Check Season 1 Summary before restart
        summary_before = await crud.get_season_status_summary(session)
        print(f"\n[3] 1-Mavsum yakuniy holati (Restartdan oldin):")
        print(f"    • Faol mavsum: {summary_before['season_number']}-Mavsum")
        print(f"    • G'olib Xonadon: {summary_before['winner_house_emoji']} {summary_before['winner_house_name']}")
        print(f"    • Mavsum Chempioni (Qirol): {summary_before['king_name']}")
        print(f"    • TOP 3 Haqiqiy Lordlar:")
        for p in summary_before["top3_players"]:
            print(f"      #{p['rank']}: {p['name']} (ID: {p['telegram_id']}, Xonadon: {p['house']}, Daraja: {p['level']}, Nufuz: {p['prestige']}🎖️)")

        # 4. Execute Season 1 -> Season 2 Conclude & Restart on DRY-RUN DB
        ok_rst, announcement, rst_info = await crud.admin_conclude_and_restart_season(session, bot_app=None)
        assert ok_rst is True, "admin_conclude_and_restart_season failed!"
        print(f"\n[4] Dry-Run Restart bajarildi: {rst_info['season_number']}-Mavsum -> {rst_info['next_season_number']}-Mavsum!")

        # 5. Verify post-restart state on DRY-RUN DB
        active_season = await crud.get_active_season(session)
        assert active_season.season_number == 2 and active_season.is_active is True

        users_after = (await session.execute(select(func.count(models.User.id)))).scalar() or 0
        armies_after = (await session.execute(select(func.count(models.Army.id)))).scalar() or 0
        dragons_after = (await session.execute(select(func.count(models.Dragon.id)))).scalar() or 0
        houses_after = (await session.execute(select(func.count(models.House.id)))).scalar() or 0
        terrs_after = (await session.execute(select(func.count(models.Territory.id)))).scalar() or 0
        max_castle_lvl = (await session.execute(select(func.max(models.Territory.castle_level)))).scalar() or 1
        hof_list = await crud.get_hall_of_fame(session)
        bonuses_list = list((await session.execute(select(models.SeasonTopBonus))).scalars().all())

        print(f"\n[5] 2-Mavsum (Dry-Run) tekshiruv natijalari:")
        print(f"    • Faol mavsum raqami: {active_season.season_number}-Mavsum (is_active={active_season.is_active})")
        print(f"    • Foydalanuvchilar soni (Users): {users_after} (0 ga tushdi)")
        print(f"    • Armiyalar soni (Armies): {armies_after} (0 ga tushdi)")
        print(f"    • Ajdarlar soni (Dragons): {dragons_after} (0 ga tushdi)")
        print(f"    • Kanon Xonadonlar soni (Houses): {houses_after} (50 ta kanon xonadon boshlang'ich holatda)")
        print(f"    • Hududlar/Qal'alar soni (Territories): {terrs_after} (barchasi 1-daraja, max_level={max_castle_lvl})")
        print(f"    • Shon-sharaf zali (Hall of Fame) yozuvlari: {len(hof_list)} ta -> G'olib: {hof_list[0].king_name} ({hof_list[0].winner_house_name})")
        print(f"    • TOP 3 Yangi Mavsum Bonuslari (SeasonTopBonus): {len(bonuses_list)} ta saqlandi")

        assert users_after == 0
        assert armies_after == 0
        assert dragons_after == 0
        assert houses_after == 50
        assert terrs_after == 64
        assert max_castle_lvl == 1
        assert len(hof_list) == 1
        assert len(bonuses_list) == 3

        # 6. Verify old season donation request is closed and cannot be approved in Season 2
        old_req_after = await crud.get_donation_request_by_id(session, mock_old_req_id)
        assert old_req_after.status == "rejected", f"Expected old pending req to be rejected, got {old_req_after.status}"

        # Force status back to pending in dry-run to test the server-side Season 2 approval guard
        old_req_after.status = "pending"
        await session.commit()
        admin_id = config.ADMIN_IDS[0] if config.ADMIN_IDS else config.OWNER_ID
        ok_old_app, msg_old_app, _ = await services.approve_donation_request_service(session, mock_old_req_id, admin_id)
        assert ok_old_app is False, "Old season donation request must NOT be approvable in Season 2!"
        print(f"    • Eski mavsum donat so'rovini tasdiqlash himoyasi: ISHLADI ({msg_old_app})")

        # 7. Simulate Top 1 Winner registering in Season 2 and claiming Top 1 Bonus
        top1_tg_id = bonuses_list[0].telegram_id
        ok_reg, msg_reg, new_u = await services.register_player_service(
            session=session,
            telegram_id=top1_tg_id,
            username="Tom_2508x",
            full_name="Shavkatov",
            hero_name="Owner",
            house_code="lannister",
        )
        assert ok_reg is True, f"Season 2 registration failed: {msg_reg}"
        await session.refresh(new_u)
        assert new_u.title == "🏆 1-Mavsum Chempioni", f"Expected champion title, got {new_u.title}"
        print(f"    • 1-o'rin g'olibi 2-mavsumda ro'yxatdan o'tganda avtomatik unvon va bonus oldi: Unvon='{new_u.title}', Oltin={new_u.gold:,}🪙, Nufuz={new_u.prestige}🎖️")

    await engine.dispose()

    # 8. Verify live DB is 100% untouched!
    live_hash_after = sha256_file(live_db_path)
    print(f"\n[6] Haqiqiy baza (got_mmorpg.db) daxlsizligi tekshiruvi:")
    print(f"    • Live DB SHA-256 (oldin): {live_hash_before}")
    print(f"    • Live DB SHA-256 (keyin): {live_hash_after}")
    assert live_hash_before == live_hash_after, "CRITICAL: Live DB was modified during dry-run!"
    print("    ✅ TASDIQLANDI: Haqiqiy baza 100% daxlsiz (o'zgarishsiz) qoldi!")


if __name__ == "__main__":
    asyncio.run(run_step6_dry_run())
