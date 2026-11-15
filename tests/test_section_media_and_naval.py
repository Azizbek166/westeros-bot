import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.db import AsyncSessionLocal, init_db
from database import crud, models
from services.section_media_service import (
    set_user_section_media,
    get_user_section_media,
    clear_user_section_media,
)
from services.naval_service import (
    build_ships,
    calc_fleet_stats,
    get_or_create_fleet,
    raid_sea_zone,
    attack_player_fleet,
)


class TestSectionMediaAndNaval(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        self.tg1 = 99988101
        self.tg2 = 99988102
        async with AsyncSessionLocal() as session:
            for tg, name in ((self.tg1, "NavalLord1"), (self.tg2, "NavalLord2")):
                u = await crud.get_user_by_telegram_id(session, tg)
                if not u:
                    u = models.User(
                        telegram_id=tg,
                        username=name.lower(),
                        full_name=name,
                        gold=50000,
                        food=50000,
                        iron=50000,
                    )
                    session.add(u)
                    await session.flush()
                else:
                    u.gold = 50000
                    u.food = 50000
                    u.iron = 50000
                    u.vip_tier = None
                    u.vip_until = None
                    u.peace_shield_until = None
                    u.house_id = None
            await session.commit()

    async def test_section_media_vip_gating(self):
        async with AsyncSessionLocal() as session:
            ok, _ = await set_user_section_media(session, self.tg1, "dragon", "photo", "fid_1")
            self.assertFalse(ok)

            u = await crud.get_user_by_telegram_id(session, self.tg1)
            u.vip_tier = "noble"
            u.vip_until = datetime.utcnow() + timedelta(days=10)
            await session.commit()

            ok, _ = await set_user_section_media(session, self.tg1, "dragon", "photo", "fid_dragon_photo")
            self.assertTrue(ok)
            ok_vid, _ = await set_user_section_media(session, self.tg1, "castle", "video", "fid_vid")
            self.assertFalse(ok_vid)

            u.vip_tier = "lord"
            await session.commit()
            ok_vid2, _ = await set_user_section_media(session, self.tg1, "castle", "video", "fid_castle_vid")
            self.assertTrue(ok_vid2)

            got = await get_user_section_media(session, u, "dragon")
            self.assertEqual(got["file_id"], "fid_dragon_photo")

            u.vip_until = datetime.utcnow() - timedelta(days=1)
            await session.commit()
            self.assertIsNone(await get_user_section_media(session, u, "dragon"))

            ok_clr, _ = await clear_user_section_media(session, self.tg1, "dragon")
            self.assertTrue(ok_clr)

    async def test_naval_build_pve_and_pvp(self):
        async with AsyncSessionLocal() as session:
            ok, _ = await build_ships(session, self.tg1, "sloops", 3)
            self.assertTrue(ok)
            ok2, _ = await build_ships(session, self.tg1, "flagships", 1)
            self.assertTrue(ok2)

            u1 = await crud.get_user_by_telegram_id(session, self.tg1)
            f1 = await get_or_create_fleet(session, u1.id)
            st = calc_fleet_stats(f1)
            self.assertTrue(st["flagship_bonus"])
            self.assertGreaterEqual(st["power"], 500)

            ok_raid, msg_raid = await raid_sea_zone(session, self.tg1, "narrow_sea")
            self.assertTrue(ok_raid)
            self.assertTrue(len(msg_raid) > 0)

            ok_b2, _ = await build_ships(session, self.tg2, "sloops", 2)
            self.assertTrue(ok_b2)
            u2 = await crud.get_user_by_telegram_id(session, self.tg2)
            ok_pvp, _ = await attack_player_fleet(session, self.tg1, u2.id)
            self.assertTrue(ok_pvp)


if __name__ == "__main__":
    unittest.main()
