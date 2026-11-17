import os
import sys
import unittest
from sqlalchemy import delete, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.db import AsyncSessionLocal, init_db
from database import crud, models


class TestTrimNonDonorTroops(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        self.tgs = [99966101, 99966102, 99966103]
        self.houses = [10, 11, 12]
        async with AsyncSessionLocal() as session:
            for tg in self.tgs:
                u = await crud.get_user_by_telegram_id(session, tg)
                if u:
                    await session.delete(u)
            await session.flush()
            for hid in self.houses:
                h = await session.get(models.House, hid)
                if h:
                    h.lord_user_id = None
                await session.execute(delete(models.HouseMember).where(models.HouseMember.house_id == hid))
            await session.commit()

    async def asyncTearDown(self):
        async with AsyncSessionLocal() as session:
            for tg in self.tgs:
                u = await crud.get_user_by_telegram_id(session, tg)
                if u:
                    await session.delete(u)
            await session.commit()

    async def test_trim_only_non_donors_above_2_castles(self):
        async with AsyncSessionLocal() as session:
            # u1: 3 castles, non-donor -> SHOULD BE TRIMMED 80% (keep 20%)
            u1 = await crud.create_user(session, self.tgs[0], "nd3", "NonDonor3", self.houses[0], f"ND3_{self.tgs[0]}")
            # u2: 3 castles, donor (vip_tier='noble') -> MUST NOT BE TOUCHED
            u2 = await crud.create_user(session, self.tgs[1], "d3", "Donor3", self.houses[1], f"D3_{self.tgs[1]}")
            u2.vip_tier = "noble"
            # u3: 1 castle, non-donor -> MUST NOT BE TOUCHED
            u3 = await crud.create_user(session, self.tgs[2], "nd1", "NonDonor1", self.houses[2], f"ND1_{self.tgs[2]}")

            # Give armies = 1000 infantry each
            for u in (u1, u2, u3):
                a = await crud.get_user_army(session, u.id)
                a.infantry = 1000
                a.archers = 0
                a.cavalry = 0
                a.spearmen = 0

            # Give u1 and u2 2 extra conquered castles each (total 3 each)
            neutrals = (
                await session.execute(
                    select(models.Territory).where(models.Territory.owner_house_id.is_(None)).limit(4)
                )
            ).scalars().all()
            for idx, t in enumerate(neutrals):
                owner = u1 if idx < 2 else u2
                t.owner_house_id = owner.house_id
                t.conquered_by_user_id = owner.id
                t.garrison_infantry = 500
                t.garrison_archers = 0
                t.garrison_cavalry = 0
                t.garrison_spearmen = 0
            await session.commit()
            before_c1 = len(await crud.get_user_and_house_castles(session, u1))

            # Dry-run first: must NOT modify DB
            dry = await crud.audit_and_trim_non_donor_troops(session, dry_run=True)
            self.assertEqual(dry["affected_count"], 1)
            self.assertEqual(dry["affected"][0]["user_id"], u1.id)
            self.assertEqual(dry["affected"][0]["army_before"], 1000)
            self.assertEqual(dry["affected"][0]["army_after"], 200)

            a1_still = await crud.get_user_army(session, u1.id)
            self.assertEqual(a1_still.infantry, 1000)

            # Apply
            applied = await crud.audit_and_trim_non_donor_troops(session, dry_run=False)
            self.assertEqual(applied["affected_count"], 1)

            a1 = await crud.get_user_army(session, u1.id)
            a2 = await crud.get_user_army(session, u2.id)
            a3 = await crud.get_user_army(session, u3.id)
            self.assertEqual(a1.infantry, 200)   # 80% removed -> 20% kept
            self.assertEqual(a2.infantry, 1000)  # donor untouched
            self.assertEqual(a3.infantry, 1000)  # <=2 castles untouched

            # Check u1's castles still exist (not deleted) and garrisons trimmed 80%
            u1_castles = await crud.get_user_and_house_castles(session, u1)
            self.assertEqual(len(u1_castles), before_c1)
            for t in neutrals[:2]:
                await session.refresh(t)
                self.assertEqual(t.garrison_infantry, 100)  # 500 * 0.20 = 100

            # Restore neutral territories
            for t in neutrals:
                t.owner_house_id = None
                t.conquered_by_user_id = None
            await session.commit()


if __name__ == "__main__":
    unittest.main()
