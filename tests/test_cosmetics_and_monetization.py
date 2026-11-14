"""
Test suite for Cosmetics, Noble VIP, Starter Pack, Gifting, Idempotent Payments,
and Strict Non-P2W Verification.
"""
import unittest
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
            else:
                user.vip_tier = "sovereign"
                await session.commit()

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
        """Test that unpaid instant cosmetic buy/gift is blocked and requires manual receipt approval."""
        from config import OWNER_ID
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

            # 1) Direct unpaid buy & gift must be blocked
            ok_buy, msg_buy, _ = await services.buy_cosmetic_service(
                session=session,
                user=sender,
                item_id="dragon_golden",
            )
            self.assertFalse(ok_buy)

            ok_gift, msg_gift = await services.gift_cosmetic_service(
                session=session,
                sender=sender,
                recipient_telegram_id=recipient_tg,
                item_id="dragon_golden",
            )
            self.assertFalse(ok_gift)

            # 2) Submit receipt and approve via admin
            ok_sub, msg_sub, req = await services.submit_donation_request_service(
                session=session,
                user=recipient,
                package_id="dragon_golden",
                receipt_file_id="receipt_dragon_golden_test",
            )
            self.assertTrue(ok_sub, msg_sub)
            ok_app, msg_app, _ = await services.approve_donation_request_service(
                session=session,
                request_id=req.id,
                admin_telegram_id=OWNER_ID,
            )
            self.assertTrue(ok_app, msg_app)

            recipient_cosms = await get_user_cosmetics(session, recipient.id)
            self.assertTrue(any(c.item_id == "dragon_golden" for c in recipient_cosms))

    async def test_manual_donation_workflow_security_and_pass_lifecycle(self):
        """
        To'liq qo'lda tasdiqlash oqimi tekshiruvi:
        1. Majburiy chek skrinshoti
        2. Pending so'rov spam oldini olish
        3. Server-side admin huquqi tekshiruvi
        4. Bitta so'rov faqat bir marta tasdiqlanishi (idempotency)
        5. Dinamik karta raqami va karta egasi sozlamasi
        6. Rad etish (sababi bilan)
        7. Premium Pass kunlik bonusi va muddat tugaganda resurslar qolishi
        """
        from datetime import datetime, timedelta
        from config import OWNER_ID

        async with AsyncSessionLocal() as session:
            tg_id = 9990077
            res = await session.execute(select(models.User).where(models.User.telegram_id == tg_id))
            user = res.scalar_one_or_none()
            if not user:
                user = models.User(
                    telegram_id=tg_id,
                    username="manual_don_tester",
                    full_name="Lord Manual Tester",
                    house_id=1,
                    gold=1000,
                    food=1000,
                    iron=500,
                    prestige=10,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

            # Clear any leftover pending requests for this test user
            old_reqs = await session.execute(
                select(models.DonationRequest).where(models.DonationRequest.telegram_id == tg_id)
            )
            for orq in old_reqs.scalars().all():
                await session.delete(orq)
            await session.commit()

            # 1) Karta rekvizitlarini faqat admin o'zgartira oladi
            ok_non_adm, _, _ = await services.update_payment_requisites_service(
                session, admin_telegram_id=123456, card_number="8600 0000 0000 0000", card_holder="HACKER"
            )
            self.assertFalse(ok_non_adm)

            ok_adm_card, _, card_data = await services.update_payment_requisites_service(
                session, admin_telegram_id=OWNER_ID, card_number="9860 5555 4444 3333", card_holder="VALYRIYA XAZINASI"
            )
            self.assertTrue(ok_adm_card)
            self.assertEqual(card_data["card_number"], "9860 5555 4444 3333")
            self.assertEqual(card_data["card_holder"], "VALYRIYA XAZINASI")

            reqs_fetched = await services.get_payment_requisites_service(session)
            self.assertEqual(reqs_fetched["card_number"], "9860 5555 4444 3333")
            self.assertEqual(reqs_fetched["card_holder"], "VALYRIYA XAZINASI")

            # 2) Chek rasmi bo'lmasa so'rov yaratilmaydi
            ok_no_img, _, _ = await services.submit_donation_request_service(
                session=session,
                user=user,
                package_id="premium_pass",
                receipt_file_id="   ",
            )
            self.assertFalse(ok_no_img)

            # 3) To'g'ri chek bilan so'rov yaratish
            ok_req1, _, req1 = await services.submit_donation_request_service(
                session=session,
                user=user,
                package_id="premium_pass",
                receipt_file_id="/static/uploads/receipts/test_check_1.jpg",
            )
            self.assertTrue(ok_req1)
            self.assertEqual(req1.package, "premium_pass")
            self.assertEqual(req1.amount, 25000)
            self.assertEqual(req1.status, "pending")

            # 4) Pending so'rov bor paytda ikkinchi so'rov yuborish (spam) bloklanadi
            ok_spam, msg_spam, _ = await services.submit_donation_request_service(
                session=session,
                user=user,
                package_id="vip_noble",
                receipt_file_id="/static/uploads/receipts/test_check_2.jpg",
            )
            self.assertFalse(ok_spam)
            self.assertIn("ko'rib chiqilayotgan so'rov mavjud", msg_spam)

            # 5) Admin bo'lmagan odam tasdiqlay yoki rad eta olmaydi
            ok_fake_app, _, _ = await services.approve_donation_request_service(
                session=session,
                request_id=req1.id,
                admin_telegram_id=7777777,
            )
            self.assertFalse(ok_fake_app)

            # 6) Admin rad etsa, status rejected bo'ladi va sabab yoziladi
            ok_rej, _, rej_req = await services.reject_donation_request_service(
                session=session,
                request_id=req1.id,
                admin_telegram_id=OWNER_ID,
                reason="Skrinshot xira",
            )
            self.assertTrue(ok_rej)
            self.assertEqual(rej_req.status, "rejected")
            self.assertEqual(rej_req.admin_notes, "Skrinshot xira")
            self.assertEqual(rej_req.reviewed_by, OWNER_ID)

            # 7) Rad etilgach foydalanuvchi yangi so'rov yubora oladi va Admin tasdiqlaydi
            ok_req2, _, req2 = await services.submit_donation_request_service(
                session=session,
                user=user,
                package_id="premium_pass",
                receipt_file_id="/static/uploads/receipts/test_check_valid.jpg",
            )
            self.assertTrue(ok_req2)

            gold_before = user.gold
            food_before = user.food
            iron_before = user.iron

            ok_app1, _, details1 = await services.approve_donation_request_service(
                session=session,
                request_id=req2.id,
                admin_telegram_id=OWNER_ID,
            )
            self.assertTrue(ok_app1)
            await session.refresh(user)
            self.assertEqual(user.gold, gold_before + 2500)
            self.assertEqual(user.food, food_before + 5000)
            self.assertEqual(user.iron, iron_before + 1500)
            self.assertIn(user.vip_tier, ("noble", "premium_pass"))
            self.assertIsNotNone(user.vip_until)

            # 8) Ikki marta tasdiqlash (idempotency): ikkinchi marta bosilganda rad etiladi va resurs ikki marta berilmaydi
            gold_after_first = user.gold
            ok_app2, msg_app2, _ = await services.approve_donation_request_service(
                session=session,
                request_id=req2.id,
                admin_telegram_id=OWNER_ID,
            )
            self.assertFalse(ok_app2)
            await session.refresh(user)
            self.assertEqual(user.gold, gold_after_first)

            # 9) Kunlik bonusda Premium Pass qo'shimcha mukofoti (+300 oltin, +600 bug'doy, +200 temir)
            from database import crud
            user.last_streak_date = "2020-01-01"
            await session.commit()
            ok_claim, claim_msg = await crud.claim_daily_bonus(session, user.id)
            self.assertTrue(ok_claim)
            self.assertIn("Premium Qo'shimcha Kunlik Bonus", claim_msg)
            self.assertIn("+300", claim_msg)

            # 10) Muddat (30 kun) tugagach status o'chadi, lekin yig'ilgan resurslar saqlanib qoladi
            await session.refresh(user)
            saved_gold = user.gold
            user.vip_until = datetime.utcnow() - timedelta(seconds=10)
            user.last_streak_date = "2020-01-01"
            await session.commit()

            ok_claim_exp, claim_msg_exp = await crud.claim_daily_bonus(session, user.id)
            self.assertTrue(ok_claim_exp)
            self.assertNotIn("Premium Qo'shimcha Kunlik Bonus", claim_msg_exp)
            await session.refresh(user)
            self.assertIsNone(user.vip_until)
            self.assertIn(user.vip_tier, (None, "free"))
            self.assertGreater(user.gold, saved_gold)


if __name__ == "__main__":
    unittest.main()
