"""
Yakuniy QA testlari:
1. Ajdaho kuchi (Dragon Power) va Artefaktlar (equip / replace / unequip / 12,300 migratsiya tiklash)
2. 25,000 so'mlik Donate Pack (knight / Ritsar Homiy) imtiyozlari (Rasm, Video, GIF, Shior, permission check, validatsiya, eski egalarga migratsiya)
"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import Base
from database import models, crud
from handlers.profile_handler import (
    format_user_profile_card,
    _send_profile_media_bot,
    _send_profile_media_reply,
)
from services.profile_extras_service import (
    get_active_vip_tier,
    has_min_vip_tier,
    validate_vip_photo_message,
    validate_vip_video_message,
)
from services.donate_service import get_donate_hub_data
from scripts.migrate_dragon_power_and_knight_perks import (
    restore_dragons_power,
    restore_25k_knight_pack_perks,
)


class TestDragonPowerAnd25kPackFixes(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    # =========================================================================
    # 1. AJDAHO KUCHI VA ARTEFAKTLAR TESTLARI
    # =========================================================================

    async def test_01_high_power_dragon_equip_replace_unequip_no_12300_drop(self):
        async with self.SessionLocal() as session:
            user = models.User(
                telegram_id=100001,
                username="dragon_lord",
                full_name="Aegon Targaryen",
                gold=500000,
                iron=500000,
                food=500000,
                level=20,
            )
            session.add(user)
            await session.flush()

            # Balerion (S-grade, Lv.20) 25,000 bazaviy kuch bilan
            balerion = models.Dragon(
                user_id=user.id,
                name="Balerion",
                grade="S",
                stage="adult",
                level=20,
                hunger=100,
                power=25000,
            )
            session.add(balerion)
            await session.commit()

            # 1) +40% artefakt (dragon_armor) taqish -> 25,000 * 1.40 = 35,000
            ok, msg = await crud.equip_dragon_artifact(session, user.id, balerion.id, "dragon_armor")
            self.assertTrue(ok, msg)
            await session.refresh(balerion)
            self.assertEqual(balerion.artifact_code, "dragon_armor")
            self.assertEqual(balerion.power, 35000)
            self.assertGreater(balerion.power, 25000)

            # 2) +50% artefakt (fire_ruby) ga almashtirish -> 25,000 * 1.50 = 37,500 (12,300 ga tushmasligi shart!)
            ok2, msg2 = await crud.equip_dragon_artifact(session, user.id, balerion.id, "fire_ruby")
            self.assertTrue(ok2, msg2)
            await session.refresh(balerion)
            self.assertEqual(balerion.artifact_code, "fire_ruby")
            self.assertEqual(balerion.power, 37500)

            # 3) Artefaktni yechish -> qaytib 25,000 bazaviy kuchga tushishi kerak
            ok3, msg3 = await crud.unequip_dragon_artifact(session, user.id, balerion.id)
            self.assertTrue(ok3, msg3)
            await session.refresh(balerion)
            self.assertIsNone(balerion.artifact_code)
            self.assertEqual(balerion.power, 25000)

    async def test_02_vhagar_18500_equip_and_migration_restores_12300_bug(self):
        async with self.SessionLocal() as session:
            user = models.User(
                telegram_id=100002,
                username="vhagar_rider",
                full_name="Aemond",
                gold=200000,
                iron=200000,
            )
            session.add(user)
            await session.flush()

            # Xatolik tufayli kuchi 12,300 (Arrax Lv.20 * 1.50) ga tushib qolgan Balerion va Vhagar
            corrupted_balerion = models.Dragon(
                user_id=user.id,
                name="Balerion",
                grade="S",
                stage="adult",
                level=20,
                hunger=100,
                power=12300,
                artifact_code="fire_ruby",  # +50%
            )
            corrupted_vhagar = models.Dragon(
                user_id=user.id,
                name="Vhagar",
                grade="A+",
                stage="adult",
                level=20,
                hunger=100,
                power=11480,  # Arrax Lv.20 * 1.40 eski cap
                artifact_code="dragon_armor",  # +40%
            )
            session.add_all([corrupted_balerion, corrupted_vhagar])
            await session.commit()

            mig = await restore_dragons_power(session)
            await session.commit()

            self.assertEqual(mig["checked"], 2)
            self.assertEqual(mig["restored"], 2)

            await session.refresh(corrupted_balerion)
            await session.refresh(corrupted_vhagar)
            self.assertEqual(corrupted_balerion.power, 37500)  # 25,000 * 1.50
            self.assertEqual(corrupted_vhagar.power, 25900)    # 18,500 * 1.40

    # =========================================================================
    # 2. 25,000 LIK DONATE PACK (KNIGHT) IMTIYOZLARI TESTLARI
    # =========================================================================

    async def test_03_knight_25k_pack_photo_video_gif_motto_and_free_user_blocked(self):
        async with self.SessionLocal() as session:
            # 25,000 pack (knight) egasi
            knight_user = models.User(
                telegram_id=200001,
                username="knight_patron",
                full_name="Ser Barristan",
                gold=1000,
                food=1000,
                iron=1000,
            )
            # Oddiy (free) o'yinchi
            free_user = models.User(
                telegram_id=200002,
                username="peasant",
                full_name="Oddiy Askari",
            )
            session.add_all([knight_user, free_user])
            await session.commit()

            # 25,000 lik knight paketini qo'llash
            ok_rew, _, details = await crud.apply_donate_rewards(session, knight_user.telegram_id, "knight")
            self.assertTrue(ok_rew)
            self.assertEqual(details["vip_tier"], "knight")
            await session.refresh(knight_user)
            self.assertEqual(get_active_vip_tier(knight_user), "knight")
            self.assertTrue(has_min_vip_tier(knight_user, "knight"))

            # get_donate_hub_data knight darajasini noble ga tushirib yubormasligini tekshirish
            hub = await get_donate_hub_data(session, knight_user.telegram_id)
            self.assertEqual(hub["current_vip_tier"], "knight")
            await session.refresh(knight_user)
            self.assertEqual(knight_user.vip_tier, "knight")

            # Knight foydalanuvchi: Rasm, Video, GIF, Shior hammasi ishlashi shart
            ok_p, msg_p = await crud.update_user_custom_photo(session, knight_user.id, "photo_fid_123")
            self.assertTrue(ok_p, msg_p)

            ok_v, msg_v = await crud.update_user_custom_video(session, knight_user.id, "video_fid_456")
            self.assertTrue(ok_v, msg_v)

            ok_g, msg_g = await crud.update_user_custom_video(session, knight_user.id, "anim:gif_fid_789")
            self.assertTrue(ok_g, msg_g)

            ok_s, msg_s = await crud.update_user_custom_status(session, knight_user.id, "Olov va Qon — Ritsar Shiori!")
            self.assertTrue(ok_s, msg_s)

            # Profil kartasida shior va GIF file_id ko'rinishini tekshirish
            knight_full = await crud.get_user_with_relations(session, knight_user.telegram_id)
            text, photo_id, _, _, video_id = await format_user_profile_card(knight_full, session)
            self.assertIn("Olov va Qon", text)
            self.assertEqual(photo_id, "photo_fid_123")
            self.assertEqual(video_id, "anim:gif_fid_789")

            # GIF yuborilganda send_animation / reply_animation chaqirilishini tekshirish (send_video emas!)
            mock_bot = SimpleNamespace(
                send_animation=AsyncMock(),
                send_video=AsyncMock(),
                send_photo=AsyncMock(),
            )
            sent = await _send_profile_media_bot(mock_bot, 12345, video_id, photo_id, text)
            self.assertTrue(sent)
            mock_bot.send_animation.assert_awaited_once()
            mock_bot.send_video.assert_not_awaited()
            call_kwargs = mock_bot.send_animation.call_args.kwargs
            self.assertEqual(call_kwargs["animation"], "gif_fid_789")
            self.assertIn("Olov va Qon", call_kwargs["caption"])

            # Oddiy (free) foydalanuvchi: barchasi rad etilishi shart
            ok_fp, _ = await crud.update_user_custom_photo(session, free_user.id, "photo_fid_free")
            ok_fv, _ = await crud.update_user_custom_video(session, free_user.id, "video_fid_free")
            ok_fs, _ = await crud.update_user_custom_status(session, free_user.id, "Free shior")
            self.assertFalse(ok_fp)
            self.assertFalse(ok_fv)
            self.assertFalse(ok_fs)

            # Noto'g'ri uzun shior va havola validatsiyasi
            ok_long, err_long = await crud.update_user_custom_status(session, knight_user.id, "A" * 120)
            self.assertFalse(ok_long)
            self.assertIn("uzun", err_long.lower())

            ok_url, err_url = await crud.update_user_custom_status(session, knight_user.id, "https://t.me/spam")
            self.assertFalse(ok_url)
            self.assertIn("havola", err_url.lower())

            # Noto'g'ri fayl turi validatsiyasi (PDF hujjat rasm/video sifatida)
            bad_doc_msg = SimpleNamespace(
                photo=None, video=None, video_note=None, animation=None,
                document=SimpleNamespace(mime_type="application/pdf", file_name="test.pdf", file_size=1024, file_id="pdf_1"),
            )
            ok_bp, _, err_bp = validate_vip_photo_message(bad_doc_msg)
            ok_bv, _, err_bv = validate_vip_video_message(bad_doc_msg)
            self.assertFalse(ok_bp)
            self.assertIsNotNone(err_bp)
            self.assertFalse(ok_bv)
            self.assertIsNotNone(err_bv)

    async def test_04_existing_25k_pack_buyers_migration(self):
        async with self.SessionLocal() as session:
            # Avvalroq 25,000 so'mlik pack olgan, ammo vip_tier noble ga tushib qolgan yoki None bo'lgan o'yinchi
            old_buyer = models.User(
                telegram_id=300001,
                username="old_knight",
                full_name="Eski Ritsar",
                vip_tier="noble",  # eski bug tufayli tushib qolgan
                vip_until=None,
            )
            session.add(old_buyer)
            await session.flush()

            req = models.DonationRequest(
                user_id=old_buyer.id,
                telegram_id=old_buyer.telegram_id,
                user_full_name=old_buyer.full_name,
                tier_id="knight",
                tier_name="🗡️ Ritsar Homiy (30 kun)",
                price_uzs=25000,
                price_label="25,000 so'm",
                status="approved",
                created_at=datetime.utcnow() - timedelta(days=5),
                reviewed_at=datetime.utcnow() - timedelta(days=5),
            )
            session.add(req)
            await session.commit()

            mig = await restore_25k_knight_pack_perks(session)
            await session.commit()

            self.assertEqual(mig["matched_buyers"], 1)
            self.assertEqual(mig["updated_count"], 1)

            await session.refresh(old_buyer)
            self.assertEqual(old_buyer.vip_tier, "knight")
            self.assertIsNotNone(old_buyer.vip_until)
            self.assertGreater(old_buyer.vip_until, datetime.utcnow())

            # Migratsiyadan so'ng darhol video/GIF, rasm va shior o'rnata olishi kerak
            ok_v, _ = await crud.update_user_custom_video(session, old_buyer.id, "anim:old_buyer_gif")
            ok_p, _ = await crud.update_user_custom_photo(session, old_buyer.id, "old_buyer_photo")
            ok_s, _ = await crud.update_user_custom_status(session, old_buyer.id, "Qaytib kelgan Ritsar!")
            self.assertTrue(ok_v and ok_p and ok_s)


if __name__ == "__main__":
    unittest.main()
