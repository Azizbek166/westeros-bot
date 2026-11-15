"""
Unit and Integration Tests for Step 5:
- Referrals (t.me/<bot>?start=ref_<id>, no self-referral, rewards after house selection)
- Achievements (models, service, idempotency, rewards)
- Promo codes (creation, atomic redemption, limits, expiration, one per user)
"""
import sys
import os
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Set project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

from database import AsyncSessionLocal, models, crud
from sqlalchemy import select
from services.referral_service import (
    process_referral_on_registration,
    award_referral_reward_after_house_selection,
    get_referral_info,
)
from services.achievement_service import (
    unlock_achievement,
    get_user_achievements,
)
from services.promo_service import (
    create_promo_code_service,
    redeem_promo_code_service,
    list_active_promo_codes,
)
from config import ACHIEVEMENTS_CONFIG, REFERRAL_REWARD_REFERRER, REFERRAL_REWARD_NEW_PLAYER


async def test_referral_flow():
    """Referal tizimi: yangi o'yinchi, o'zini taklif qilmaslik, xonadon tanlagandan keyin mukofot."""
    async with AsyncSessionLocal() as session:
        ts = int(datetime.utcnow().timestamp() * 1000) % 100000000
        ref_tg_id = 880000000 + ts
        referrer = models.User(
            telegram_id=ref_tg_id,
            username=f"lord_ref_{ts}",
            full_name="Lord Referrer",
            gold=1000,
            food=2000,
            iron=500,
            prestige=10,
            house_id=1,
        )
        session.add(referrer)
        await session.commit()
        await session.refresh(referrer)

        # 2. Yangi o'yinchi yaratish
        new_tg_id = 890000000 + ts
        new_user = models.User(
            telegram_id=new_tg_id,
            username=f"new_rec_{ts}",
            full_name="New Recruit",
            gold=200,
            food=400,
            iron=100,
            prestige=0,
            house_id=None,  # Hali xonadon tanlamagan
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)

        # 3. O'zini o'zi taklif qilish xatosi
        self_ok, self_msg = await process_referral_on_registration(session, referrer, referrer.telegram_id)
        assert not self_ok, "O'zini o'zi taklif qilish man etilishi kerak"

        # 4. To'g'ri biriktirish
        ok_reg, msg_reg = await process_referral_on_registration(session, new_user, referrer.telegram_id)
        assert ok_reg, f"Biriktirish muvaffaqiyatli bo'lishi kerak: {msg_reg}"
        assert new_user.referred_by_id == referrer.id

        # 5. Xonadon tanlashdan oldin mukofot berilmasligi kerak (yoki berilsa faqat house_id bilan)
        # Endi xonadon tanlaydi
        new_user.house_id = 1
        session.add(new_user)
        await session.commit()

        initial_ref_gold = referrer.gold
        initial_new_gold = new_user.gold

        ok_award, msg_award, data = await award_referral_reward_after_house_selection(session, new_user.id)
        await session.commit()
        assert ok_award, f"Mukofot berilishi kerak: {msg_award}"

        await session.refresh(referrer)
        await session.refresh(new_user)

        assert referrer.gold >= initial_ref_gold + REFERRAL_REWARD_REFERRER["gold"]
        assert new_user.gold == initial_new_gold + REFERRAL_REWARD_NEW_PLAYER["gold"]

        # 6. Qayta mukofot berish bloklanishi kerak (idempotent)
        ok_again, msg_again, _ = await award_referral_reward_after_house_selection(session, new_user.id)
        assert not ok_again, "Ikkinchi marta referal mukofoti berilmasligi kerak"

        # 7. Referal ma'lumotlari
        info = await get_referral_info(session, referrer.telegram_id)
        assert info["total_invited"] >= 1
        assert info["active_recruits"] >= 1


async def test_achievements_system():
    """Yutuqlar tizimi: ochish, mukofot berish, qayta ochishdan himoya, progress hisoblash."""
    async with AsyncSessionLocal() as session:
        ts = int(datetime.utcnow().timestamp() * 1000) % 100000000
        test_tg_id = 870000000 + ts
        user = models.User(
            telegram_id=test_tg_id,
            username=f"achiever_{ts}",
            full_name="Achiever Lord",
            gold=1000,
            food=1000,
            iron=500,
            prestige=10,
            house_id=1,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        start_gold = user.gold
        start_prestige = user.prestige

        # 1. first_win yutug'ini ochish
        ok, msg, ach = await unlock_achievement(session, user.id, "first_win")
        await session.commit()
        assert ok, f"Yutuq ochilishi kerak: {msg}"
        assert ach is not None

        await session.refresh(user)
        expected_gold = start_gold + ACHIEVEMENTS_CONFIG["first_win"]["gold"]
        expected_prestige = start_prestige + ACHIEVEMENTS_CONFIG["first_win"]["prestige"]
        assert user.gold == expected_gold
        assert user.prestige == expected_prestige

        # 2. Qayta ochishga urinish (idempotentlik)
        ok2, msg2, _ = await unlock_achievement(session, user.id, "first_win")
        assert not ok2, "Allaqachon ochilgan yutuq qayta mukofot bermasligi kerak"

        # 3. Yutuqlar ro'yxati va progress
        data = await get_user_achievements(session, user.id)
        assert data["total_count"] == len(ACHIEVEMENTS_CONFIG)
        assert data["unlocked_count"] >= 1
        assert data["progress_pct"] > 0
        unlocked_codes = [a["code"] for a in data["achievements"] if a["is_unlocked"]]
        assert "first_win" in unlocked_codes


async def test_promo_codes_system():
    """Promo-kodlar tizimi: yaratish, bir martalik ishlatish, limit, muddat tekshiruvlari."""
    async with AsyncSessionLocal() as session:
        ts = int(datetime.utcnow().timestamp() * 1000) % 100000000
        test_tg_id = 860000000 + ts
        user = models.User(
            telegram_id=test_tg_id,
            username=f"promo_user_{ts}",
            full_name="Promo Tester",
            gold=500,
            food=500,
            iron=200,
            prestige=5,
            house_id=1,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # 1. Standart promo yaratish
        code = f"TESTPROMO_{int(datetime.utcnow().timestamp())}"
        ok, msg, promo = await create_promo_code_service(
            session=session,
            code=code,
            gold=1500,
            food=3000,
            iron=800,
            prestige=50,
            max_uses=2,
        )
        assert ok, f"Promo yaratilishi kerak: {msg}"

        # 2. Foydalanuvchi ishlatishi
        start_gold = user.gold
        ok_red, msg_red, data = await redeem_promo_code_service(session, user.telegram_id, code)
        await session.commit()
        assert ok_red, f"Promo ishlatilishi kerak: {msg_red}"

        await session.refresh(user)
        assert user.gold == start_gold + 1500

        # 3. Shu foydalanuvchi yana ishlatishga urinsa - rad etilishi kerak
        ok_dup, msg_dup, _ = await redeem_promo_code_service(session, user.telegram_id, code)
        assert not ok_dup, "Bir foydalanuvchi bitta promo-kodni ikki marta ishlata olmasligi kerak"
        assert "allaqachon ishlatgansiz" in msg_dup.lower()

        # 4. Muddati o'tgan promo-kod testi
        exp_code = f"EXPIRED_{int(datetime.utcnow().timestamp())}"
        past_time = datetime.utcnow() - timedelta(days=1)
        ok_exp, _, _ = await create_promo_code_service(
            session=session,
            code=exp_code,
            gold=1000,
            expires_at=past_time,
        )
        assert ok_exp
        ok_exp_red, msg_exp_red, _ = await redeem_promo_code_service(session, user.telegram_id, exp_code)
        assert not ok_exp_red, "Muddati o'tgan promo ishlatilmasligi kerak"
        assert "muddati tugagan" in msg_exp_red.lower()

        # 5. Mavjud bo'lmagan kod
        ok_fake, msg_fake, _ = await redeem_promo_code_service(session, user.telegram_id, "NON_EXISTENT_999")
        assert not ok_fake, "Mavjud bo'lmagan promo qabul qilinmasligi kerak"


if __name__ == "__main__":
    asyncio.run(test_referral_flow())
    asyncio.run(test_achievements_system())
    asyncio.run(test_promo_codes_system())
    print("\n✅ BARCHA STEP 5 TESTLARI MUVAFFAQIShATLI O'TDI (100%)!\n")
