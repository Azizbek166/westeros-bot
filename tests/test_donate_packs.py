"""
Unit tests for Step 4: 5 New Zero-P2W Donate Packages.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from types import SimpleNamespace
from config import ACTIVE_DONATE_TIERS, DONATE_TIERS
from core.balance import ECONOMY
from database.db import AsyncSessionLocal, init_db
from database import models, crud
from handlers.donate_handler import _build_donate_intro_text
from services.donate_service import (
    resolve_package_info,
    submit_donation_request_service,
    approve_donation_request_service,
)
from services.profile_extras_service import (
    get_active_vip_tier,
    get_profile_extras_view,
    has_min_vip_tier,
    validate_vip_photo_message,
    validate_vip_video_message,
    MAX_VIP_PHOTO_BYTES,
    MAX_VIP_VIDEO_BYTES,
)
from services.section_media_service import set_user_section_media


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
            self.assertLessEqual(t["gold"], 500000)
            self.assertLessEqual(t["food"], 1000000)
            self.assertLessEqual(t["iron"], 350000)
            self.assertGreater(t.get("daily_bonus_gold", 0), 0)

            # Proportional ratio check against 90,000 so'm = 500k gold / 1M food / 350k iron
            price = t["price_uzs"]
            self.assertLessEqual(t["gold"] / price, 500000 / 90000 + 1e-6)
            self.assertLessEqual(t["food"] / price, 1000000 / 90000 + 1e-6)
            self.assertLessEqual(t["iron"] / price, 350000 / 90000 + 1e-6)

        self.assertEqual(DONATE_TIERS["noble"]["price_uzs"], 9000)
        self.assertEqual(DONATE_TIERS["knight"]["price_uzs"], 25000)
        self.assertEqual(DONATE_TIERS["lord"]["price_uzs"], 40000)
        self.assertEqual(DONATE_TIERS["dragonlord"]["price_uzs"], 63000)
        self.assertEqual(DONATE_TIERS["sovereign"]["price_uzs"], 90000)
        self.assertIn("video", DONATE_TIERS["knight"]["studio_perks"])
        self.assertIn("photo", DONATE_TIERS["knight"]["studio_perks"])

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

    async def test_04_menu_request_approve_all_five_packs(self):
        from unittest.mock import AsyncMock, patch
        from config import OWNER_ID
        from sqlalchemy import delete

        intro = await _build_donate_intro_text()
        for tid in ACTIVE_DONATE_TIERS:
            t = DONATE_TIERS[tid]
            self.assertIn(t["price_label"], intro)
            self.assertIn(f"{t['gold']:,}", intro)

        async with AsyncSessionLocal() as session:
            # Clean any leftover pending requests for this test user
            await session.execute(
                delete(models.DonationRequest).where(models.DonationRequest.telegram_id == self.tg_id)
            )
            await session.commit()

            with (
                patch("services.donate_service._notify_admins_new_donation", new_callable=AsyncMock),
                patch("services.donate_service._notify_user_donation_result", new_callable=AsyncMock),
            ):
                for idx, tid in enumerate(ACTIVE_DONATE_TIERS, 1):
                    t = DONATE_TIERS[tid]
                    user = await crud.get_user_by_telegram_id(session, self.tg_id)
                    user.gold = 0
                    user.food = 0
                    user.iron = 0
                    user.total_donated_uzs = 1000  # Base pack resources without +25% first-donate bonus
                    await session.commit()

                    ok_req, _, req = await submit_donation_request_service(
                        session=session,
                        user=user,
                        package_id=tid,
                        receipt_file_id=f"test_receipt_{tid}_{idx}",
                        bot=None,
                    )
                    self.assertTrue(ok_req, f"Request failed for {tid}")
                    self.assertEqual(req.price_uzs, t["price_uzs"])
                    self.assertEqual(req.price_label, t["price_label"])

                    ok_app, _, details = await approve_donation_request_service(
                        session=session,
                        request_id=req.id,
                        admin_telegram_id=OWNER_ID,
                        bot=None,
                    )
                    self.assertTrue(ok_app, f"Approve failed for {tid}")
                    mult = 1.25 if details.get("first_donate_bonus_applied") else 1.0
                    self.assertEqual(details["gold"], int(t["gold"] * mult))
                    self.assertEqual(details["food"], int(t["food"] * mult))
                    self.assertEqual(details["iron"], int(t["iron"] * mult))

    async def test_05_knight_photo_video_and_file_validation(self):
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            user.vip_tier = "knight"
            user.vip_until = datetime.utcnow() + timedelta(days=30)
            await session.commit()

            self.assertTrue(has_min_vip_tier(user, "noble"))
            self.assertTrue(has_min_vip_tier(user, "knight"))

            ok_sec, _ = await set_user_section_media(
                session, self.tg_id, "dragon", "video", "test_mp4_file_id_123"
            )
            self.assertTrue(ok_sec)

        # Valid JPG photo & document PNG/WEBP
        ok, fid, err = validate_vip_photo_message(
            SimpleNamespace(photo=[SimpleNamespace(file_id="p1", file_size=1024)], document=None)
        )
        self.assertTrue(ok and fid == "p1" and err is None)

        ok, fid, err = validate_vip_photo_message(
            SimpleNamespace(
                photo=None,
                document=SimpleNamespace(file_id="p2", mime_type="image/webp", file_name="a.webp", file_size=2048),
            )
        )
        self.assertTrue(ok and fid == "p2" and err is None)

        # Invalid image type & oversized image
        ok, _, err = validate_vip_photo_message(
            SimpleNamespace(
                photo=None,
                document=SimpleNamespace(file_id="bad", mime_type="image/bmp", file_name="a.bmp", file_size=1000),
            )
        )
        self.assertFalse(ok)
        self.assertIn("JPG, PNG yoki WEBP", err)

        ok, _, err = validate_vip_photo_message(
            SimpleNamespace(photo=[SimpleNamespace(file_id="big", file_size=MAX_VIP_PHOTO_BYTES + 1)], document=None)
        )
        self.assertFalse(ok)
        self.assertIn("10 MB", err)

        # Valid MP4 video & invalid AVI video & oversized video
        ok, fid, err = validate_vip_video_message(
            SimpleNamespace(
                video=SimpleNamespace(file_id="v1", mime_type="video/mp4", file_name="clip.mp4", file_size=5_000_000),
                video_note=None,
                animation=None,
                document=None,
            )
        )
        self.assertTrue(ok and fid == "v1" and err is None)

        ok, _, err = validate_vip_video_message(
            SimpleNamespace(
                video=None,
                video_note=None,
                animation=None,
                document=SimpleNamespace(file_id="vbad", mime_type="video/x-msvideo", file_name="clip.avi", file_size=1024),
            )
        )
        self.assertFalse(ok)
        self.assertIn("MP4", err)

        ok, _, err = validate_vip_video_message(
            SimpleNamespace(
                video=SimpleNamespace(file_id="vbig", mime_type="video/mp4", file_name="big.mp4", file_size=MAX_VIP_VIDEO_BYTES + 1),
                video_note=None,
                animation=None,
                document=None,
            )
        )
        self.assertFalse(ok)
        self.assertIn("50 MB", err)


if __name__ == "__main__":
    unittest.main()
