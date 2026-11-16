import os
import sys
import unittest
from sqlalchemy import delete, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from database.db import AsyncSessionLocal, init_db
from database import crud, models


class TestCastleDistribution(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        self.test_tgs = [99977101, 99977102, 99977103]
        self.test_houses = [1, 2, 49]  # Stark, Lannister, Free Folk (0 initial terr in map_data)
        async with AsyncSessionLocal() as session:
            # Clean any leftover test users & restore houses 1, 2, 49
            for tg in self.test_tgs:
                u = await crud.get_user_by_telegram_id(session, tg)
                if u:
                    await session.delete(u)
            await session.flush()
            for hid in self.test_houses:
                h = await session.get(models.House, hid)
                if h:
                    h.lord_user_id = None
                await session.execute(delete(models.HouseMember).where(models.HouseMember.house_id == hid))
            await session.commit()

    async def asyncTearDown(self):
        async with AsyncSessionLocal() as session:
            for tg in self.test_tgs:
                u = await crud.get_user_by_telegram_id(session, tg)
                if u:
                    await session.delete(u)
            await session.commit()

    async def test_01_three_players_different_houses_equal_starter_castles(self):
        async with AsyncSessionLocal() as session:
            created = []
            for idx, (tg, hid) in enumerate(zip(self.test_tgs, self.test_houses), 1):
                u = await crud.create_user(
                    session=session,
                    telegram_id=tg,
                    username=f"c_test_{idx}",
                    full_name=f"CastleTester{idx}",
                    house_id=hid,
                    character_name=f"HeroCastle{idx}_{tg}",
                )
                created.append(u)

            seen_terr_ids = set()
            for u in created:
                castles = await crud.get_user_and_house_castles(session, u)
                self.assertEqual(len(castles), config.START_CASTLES_PER_PLAYER)
                for c in castles:
                    self.assertEqual(c.owner_house_id, u.house_id)
                    self.assertEqual(c.castle_level, 1)
                    self.assertNotIn(c.id, seen_terr_ids)
                    seen_terr_ids.add(c.id)

            # Idempotent double call
            for u in created:
                again = await crud.assign_starter_castles_to_user(session, u)
                self.assertEqual(len(again), config.START_CASTLES_PER_PLAYER)
                castles_after = await crud.get_user_and_house_castles(session, u)
                self.assertEqual(len(castles_after), config.START_CASTLES_PER_PLAYER)

            # TOP 10 ranking check
            top10 = await crud.get_top10_castles(session)
            by_tg = {row["user"].telegram_id: row for row in top10}
            for u in created:
                if u.telegram_id in by_tg:
                    self.assertEqual(by_tg[u.telegram_id]["castles_count"], config.START_CASTLES_PER_PLAYER)

    async def test_02_excess_castle_refunds_upgrades_and_garrison(self):
        async with AsyncSessionLocal() as session:
            u = await crud.create_user(
                session=session,
                telegram_id=self.test_tgs[0],
                username="refund_tester",
                full_name="RefundTester",
                house_id=self.test_houses[0],
                character_name=f"RefundHero_{self.test_tgs[0]}",
            )
            # Assign an extra neutral territory to the same house, upgraded & garrisoned
            n_res = await session.execute(
                select(models.Territory).where(models.Territory.owner_house_id.is_(None)).limit(1)
            )
            extra = n_res.scalar_one()
            orig_inf = extra.garrison_infantry or 200
            orig_def = extra.defense or 500
            extra.owner_house_id = u.house_id
            extra.conquered_by_user_id = None
            extra.castle_level = 2
            extra.defense = orig_def + 300 + 200  # 1 keep lvl + 1 wall upgrade
            extra.garrison_infantry = orig_inf + 50
            await session.commit()

            gold_before = u.gold
            army_before = (await crud.get_user_army(session, u.id)).infantry

            res = await crud.audit_and_fix_castle_distribution(session, dry_run=False)
            self.assertEqual(res["released_count"], 1)

            await session.refresh(u)
            await session.refresh(extra)
            army_after = (await crud.get_user_army(session, u.id)).infantry
            self.assertGreater(u.gold, gold_before)  # upgrade gold refunded
            self.assertEqual(army_after, army_before + 50)  # +50 garrison refunded
            self.assertIsNone(extra.owner_house_id)
            self.assertEqual(extra.castle_level, 1)


if __name__ == "__main__":
    unittest.main()
