"""
Test suite for Cosmetics, Noble VIP, Starter Pack, Gifting, Idempotent Payments,
and Strict Non-P2W Verification.
"""
import unittest
import asyncio
import uuid
from datetime import datetime, timedelta
from sqlalchemy import select

from database.db import AsyncSessionLocal, init_db
from database import models
from core.cosmetics import (
    COSMETICS_CATALOG,
    get_cosmetic_item,
    get_all_cosmetics_grouped,
    get_user_cosmetics,
    equip_cosmetic,
    grant_cosmetic_item,
    record_payment_transaction,
    apply_legacy_vip_compensation,
)
import services


class TestCosmeticsAndMonetization(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()

    async def test_cosmetics_catalog_zero_p2w(self):
        """Verify that NO item in the catalog grants troops, combat power, attack, defense, or resources."""
        self.assertGreaterEqual(len(COSMETICS_CATALOG), 15)
        for item_id, item in COSMETICS_CATALOG.items():
            self.assertNotIn("infantry", item)
            self.assertNotIn("archers", item)
            self.assertNotIn("cavalry", item)
            self.assertNotIn("spearmen", item)
            self.assertNotIn("attack_boost", item)
            self.assertNotIn("defense_boost", item)
            self.assertNotIn("power", item)
            self.assertNotIn("gold_bonus", item)
            self.assertGreaterEqual(item.get("price_stars", 0), 0)

    async def test_equip_and_unequip_cosmetics(self):
        """Test equipping and unequipping skins, frames, titles."""
        async with AsyncSessionLocal() as session:
            tg_id = 9990001
            res = await session.execute(select(models.User).where(models.User.telegram_id == tg_id))
            user = res.scalar_one_or_none()
            if not user:
                user = models.User(
                    telegram_id=tg_id,
                    username="test_lord_cosm",
                    full_name="Lord Cosmetics",
                    house_id=1,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

            # Grant castle skin
            ok, msg = await grant_cosmetic_item(session, user, "castle_valyrian")
            self.assertTrue(ok)

            # Equip castle skin
            ok, msg = await equip_cosmetic(session, user, "castle_valyrian")
            self.assertTrue(ok)
            self.assertEqual(user.castle_skin, "castle_valyrian")

            # Unequip castle skin
            ok, msg = await equip_cosmetic(session, user, "castle_valyrian")
            self.assertTrue(ok)
            self.assertIsNone(user.castle_skin)

    async def test_starter_pack_and_vip(self):
        """Test Starter Pack one-time purchase and Noble VIP 30-day activation."""
        async with AsyncSessionLocal() as session:
            tg_id = 9990002
            res = await session.execute(select(models.User).where(models.User.telegram_id == tg_id))
            user = res.scalar_one_or_none()
            if not user:
                user = models.User(
                    telegram_id=tg_id,
                    username="test_starter",
                    full_name="Starter Lord",
                    house_id=1,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

            # Grant starter pack
            ok, msg = await grant_cosmetic_item(session, user, "starter_pack")
            self.assertTrue(ok)
            self.assertTrue(user.has_starter_pack)
            self.assertEqual(user.vip_tier, "noble")
            self.assertIsNotNone(user.vip_until)

            # Grant 30 days Noble VIP
            ok, msg = await grant_cosmetic_item(session, user, "vip_noble")
            self.assertTrue(ok)
            self.assertEqual(user.vip_tier, "noble")

    async def test_payment_idempotency(self):
        """Test that duplicate payment transactions with same idempotency key are rejected/deduplicated."""
        async with AsyncSessionLocal() as session:
            idem_key = f"test_idem_{uuid.uuid4().hex}"
            tg_id = 9990003

            # First attempt
            ok1, msg1, tx1 = await record_payment_transaction(
                session=session,
                telegram_id=tg_id,
                item_id="castle_ice",
                provider="telegram_stars",
                idempotency_key=idem_key,
                amount_stars=75,
            )
            self.assertTrue(ok1)
            self.assertIsNotNone(tx1)

            # Second attempt with same key
            ok2, msg2, tx2 = await record_payment_transaction(
                session=session,
                telegram_id=tg_id,
                item_id="castle_ice",
                provider="telegram_stars",
                idempotency_key=idem_key,
                amount_stars=75,
            )
            self.assertTrue(ok2)
            self.assertIn("allaqachon", msg2.lower())
            self.assertEqual(tx2.id, tx1.id)

    async def test_legacy_vip_compensation(self):
        """Test legacy donors transition with founder title, sovereign frame, valyrian castle."""
        async with AsyncSessionLocal() as session:
            tg_id = 9990004
            res = await session.execute(select(models.User).where(models.User.telegram_id == tg_id))
            user = res.scalar_one_or_none()
            if not user:
                user = models.User(
                    telegram_id=tg_id,
                    username="legacy_whale",
                    full_name="Legacy Lord",
                    house_id=1,
                    vip_tier="sovereign",  # Old P2W tier
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

            ok, msg = await apply_legacy_vip_compensation(session, user)
            self.assertTrue(ok)
            self.assertEqual(user.vip_tier, "noble")
            self.assertIn("KOMPENSATSIYA", msg)

            cosms = await get_user_cosmetics(session, user.id)
            item_ids = [c.item_id for c in cosms]
            self.assertIn("title_legacy_founder", item_ids)
            self.assertIn("frame_sovereign", item_ids)
            self.assertIn("castle_valyrian", item_ids)

    async def test_gifting_cosmetics(self):
        """Test sending a cosmetic gift from User A to User B."""
        async with AsyncSessionLocal() as session:
            sender_tg = 9990005
            recipient_tg = 9990006

            res_s = await session.execute(select(models.User).where(models.User.telegram_id == sender_tg))
            sender = res_s.scalar_one_or_none()
            if not sender:
                sender = models.User(telegram_id=sender_tg, username="sender_lord", full_name="Sender", house_id=1)
                session.add(sender)

            res_r = await session.execute(select(models.User).where(models.User.telegram_id == recipient_tg))
            recipient = res_r.scalar_one_or_none()
            if not recipient:
                recipient = models.User(telegram_id=recipient_tg, username="receiver_lord", full_name="Receiver", house_id=1)
                session.add(recipient)

            await session.commit()
            await session.refresh(sender)
            await session.refresh(recipient)

            ok, msg = await services.gift_cosmetic_service(
                session=session,
                sender=sender,
                recipient_telegram_id=recipient_tg,
                item_id="dragon_golden",
            )
            self.assertTrue(ok)
            self.assertIn("muvaffaqiyatli yetkazildi", msg)

            recipient_cosms = await get_user_cosmetics(session, recipient.id)
            self.assertTrue(any(c.item_id == "dragon_golden" and c.is_gift for c in recipient_cosms))


if __name__ == "__main__":
    unittest.main()
