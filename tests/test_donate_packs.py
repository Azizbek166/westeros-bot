"""
Unit tests for Step 4: 5 New Zero-P2W Donate Packages.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ACTIVE_DONATE_TIERS, DONATE_TIERS
from core.balance import ECONOMY
from database.db import AsyncSessionLocal, init_db
from database import models, crud
from services.donate_service import resolve_package_info, approve_donation_request_service
from services.profile_extras_service import get_active_vip_tier, get_profile_extras_view


class TestDonatePacks(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.tg_id = 998877663
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            if not user:
                user = models.User(
                    telegram_id=self.tg_id,
                    username="donate_tester",
                    full_name="Donate Tester",
                    house_id=1,
                    gold=500,
                    food=500,
                    iron=500,
                )
                session.add(user)
                await session.commit()

    async def test_01_five_active_packs_zero_p2w(self):
        self.assertEqual(ACTIVE_DONATE_TIERS, ["noble", "knight", "lord", "dragonlord", "sovereign"])
        self.assertEqual(ECONOMY.sovereign_vip_income_mult, 1.0)
        for tid in ACTIVE_DONATE_TIERS:
            t = DONATE_TIERS[tid]
            self.assertEqual(t.get("infantry", 0), 0)
            self.assertEqual(t.get("archers", 0), 0)
            self.assertEqual(t.get("cavalry", 0), 0)
            self.assertEqual(t.get("spearmen", 0), 0)
            self.assertEqual(t.get("catapults", 0), 0)
            self.assertEqual(t.get("siege_towers", 0), 0)
            self.assertEqual(t.get("wildfire", 0), 0)
            self.assertEqual(t.get("prestige", 0), 0)
            self.assertEqual(t.get("duration_days", 0), 30)
            self.assertFalse(t.get("instant_dragon_heal", False))
            self.assertFalse(t.get("instant_egg_hatch_boost", False))
            self.assertLessEqual(t["gold"], 75000)
            self.assertGreater(t.get("daily_bonus_gold", 0), 0)

    async def test_02_legacy_packages_still_resolve(self):
        for old_id in ("premium_pass", "starter_pack", "speedup_pack", "vip_noble"):
            info = resolve_package_info(old_id)
            self.assertIsNotNone(info)
            self.assertEqual(info["package_id"], old_id)

    async def test_03_sovereign_grants_permanent_badge_and_expires_cleanly(self):
        async with AsyncSessionLocal() as session:
            ok, _, details = await crud.apply_donate_rewards(session, self.tg_id, "sovereign")
            self.assertTrue(ok)
            self.assertGreaterEqual(details.get("royal_decree_count", 0), 4)
            self.assertTrue(ok)
            self.assertEqual(details["vip_tier"], "sovereign")

            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            self.assertEqual(get_active_vip_tier(user), "sovereign")

            # Simulate VIP expiration
            user.vip_until = datetime.utcnow() - timedelta(days=1)
            await session.commit()
            self.assertEqual(get_active_vip_tier(user), "free")

            view = await get_profile_extras_view(session, user)
            self.assertIn("👑 Qirollik Homiysi", view["badges"])


if __name__ == "__main__":
    unittest.main()
