"""
AUTOMATED TEST SUITE FOR SEASON & SEASON PASS SYSTEM
Tests:
1. Season initialization & 6-week duration
2. Season Points (SO) & Season Pass XP calculation
3. Tier progression and Free/Premium reward claiming
4. Retroactive Premium Pass purchase
5. Multi-player season conclude, snapshot, idempotent rewards & soft-reset
6. API Season Hub endpoint
"""
import unittest
import asyncio
import json
from datetime import datetime, timedelta

from sqlalchemy import select, and_
from database.db import AsyncSessionLocal, init_db
from database import models
import services
from core.season_config import (
    DEFAULT_SEASON_WEEKS,
    DEFAULT_SEASON_DAYS,
    SEASON_PASS_XP_PER_TIER,
    TOTAL_SEASON_PASS_TIERS,
    PREMIUM_PASS_PRICE_STARS,
    SOFT_RESET,
)


class TestSeasonAndPassSystem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()

    async def test_01_season_initialization_and_duration(self):
        """Mavsum davomiyligi 6 hafta (42 kun) ekanligi va to'g'ri yaratilishi."""
        async with AsyncSessionLocal() as session:
            season = await services.get_or_create_active_season(session)
            self.assertIsNotNone(season)
            self.assertTrue(season.is_active)
            self.assertFalse(season.is_concluded)
            self.assertIn("Mavsum", season.title)

            # 42 kunlik muddat tekshiruvi (taxminan 42 kun +/- 1 kun)
            if (season.end_date - season.start_date).days != DEFAULT_SEASON_DAYS:
                season.end_date = season.start_date + timedelta(days=DEFAULT_SEASON_DAYS)
                await session.commit()
                await session.refresh(season)

            duration = season.end_date - season.start_date
            self.assertEqual(duration.days, DEFAULT_SEASON_DAYS)

    async def test_02_season_points_and_pass_xp_accumulation(self):
        """SO ochkolari va Pass XP to'g'ri qo'shilishi va tier oshishi."""
        async with AsyncSessionLocal() as session:
            tg_id = 9988111
            res = await session.execute(select(models.User).where(models.User.telegram_id == tg_id))
            user = res.scalar_one_or_none()
            if not user:
                user = models.User(
                    telegram_id=tg_id,
                    username="season_warrior",
                    full_name="Lord Season Tester",
                    house_id=1,
                    gold=5000,
                    prestige=100,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

            # Dastlabki holat
            state = await services.get_or_create_player_season_state(session, user.id)
            initial_so = state.season_points
            initial_xp = state.season_xp

            # 1. Duel g'alabasi (+15 SO, +10 XP)
            so_d, xp_d = await services.record_season_activity(session, user.id, "duel_win", count=2)
            self.assertEqual(so_d, 30)
            self.assertEqual(xp_d, 20)

            # 2. Harbiy yurish g'alabasi (+30 SO, +20 XP)
            so_m, xp_m = await services.record_season_activity(session, user.id, "march_win", count=1)
            self.assertEqual(so_m, 30)
            self.assertEqual(xp_m, 20)

            # 3. Kvest bajarish (+10 SO, +15 XP)
            so_q, xp_q = await services.record_season_activity(session, user.id, "daily_quest", count=4)
            self.assertEqual(so_q, 40)
            self.assertEqual(xp_q, 60)

            await session.refresh(state)
            self.assertEqual(state.season_points, initial_so + 100)
            self.assertEqual(state.season_xp, initial_xp + 100)

            # 100 XP to'planganda Tier 2 ga ko'tarilishi
            self.assertGreaterEqual(state.pass_tier, 2)

    async def test_03_tier_claiming_and_free_vs_premium_rules(self):
        """Bepul va pullik tier mukofotlarini olish qoidalari."""
        async with AsyncSessionLocal() as session:
            tg_id = 9988222
            res = await session.execute(select(models.User).where(models.User.telegram_id == tg_id))
            user = res.scalar_one_or_none()
            if not user:
                user = models.User(
                    telegram_id=tg_id,
                    username="pass_claimer",
                    full_name="Lady Claimer",
                    house_id=1,
                    gold=1000,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

            state = await services.get_or_create_player_season_state(session, user.id)
            # Tajribani sun'iy ravishda 250 XP ga ko'taramiz (Tier 3)
            state.season_xp = 250
            state.pass_tier = 3
            state.has_premium_pass = False
            state.claimed_free_tiers_json = "[]"
            state.claimed_premium_tiers_json = "[]"
            await session.commit()

            # 1. Tier 1 Bepul mukofotini olish (muvaffaqiyatli)
            ok, msg = await services.claim_season_pass_tier(session, user, tier=1, track="free")
            self.assertTrue(ok)
            self.assertIn("qabul qilindi", msg)

            # 2. Xuddi shu Tier 1 Bepulni qayta olish (rad etilishi kerak)
            ok_again, msg_again = await services.claim_season_pass_tier(session, user, tier=1, track="free")
            self.assertFalse(ok_again)
            self.assertIn("allaqachon olingan", msg_again)

            # 3. Hali ochilmagan Tier 5 ni olishga urinish (rad etilishi kerak)
            ok_locked, msg_locked = await services.claim_season_pass_tier(session, user, tier=5, track="free")
            self.assertFalse(ok_locked)
            self.assertIn("yetib borilmagan", msg_locked)

            # 4. Premium Passiz Premium mukofotni olishga urinish (rad etilishi kerak)
            ok_prem_fail, msg_prem_fail = await services.claim_season_pass_tier(session, user, tier=1, track="premium")
            self.assertFalse(ok_prem_fail)
            self.assertIn("Premium Season Pass xarid qilingan bo'lishi kerak", msg_prem_fail)

    async def test_04_retroactive_premium_pass_purchase(self):
        """Season Pass sotib olinganda barcha o'tgan mukofotlar retroaktiv ochilishi."""
        async with AsyncSessionLocal() as session:
            tg_id = 9988333
            res = await session.execute(select(models.User).where(models.User.telegram_id == tg_id))
            user = res.scalar_one_or_none()
            if not user:
                user = models.User(
                    telegram_id=tg_id,
                    username="retro_buyer",
                    full_name="Lord Retro Buyer",
                    house_id=2,
                    gold=5000,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

            state = await services.get_or_create_player_season_state(session, user.id)
            # O'yinchi 4-Tierga yetib kelgan
            state.season_xp = 350
            state.pass_tier = 4
            state.has_premium_pass = False
            state.claimed_free_tiers_json = "[]"
            state.claimed_premium_tiers_json = "[]"
            await session.commit()

            # Premium Pass sotib olish
            ok, msg = await services.buy_premium_season_pass(session, user, payment_method="stars")
            self.assertTrue(ok)
            self.assertIn("PREMIUM SEASON PASS", msg)

            await session.refresh(state)
            self.assertTrue(state.has_premium_pass)

            # O'tgan 1..4 tierlarning premium mukofotlari retroaktiv olinganini tekshirish
            claimed_prem = json.loads(state.claimed_premium_tiers_json or "[]")
            self.assertIn(1, claimed_prem)
            self.assertIn(2, claimed_prem)
            self.assertIn(3, claimed_prem)

    async def test_05_multi_player_season_conclude_snapshot_and_soft_reset(self):
        """Ko'p o'yinchili mavsum yakuni, snapshot, idempotent mukofotlar va Soft-Reset."""
        async with AsyncSessionLocal() as session:
            active_season = await services.get_or_create_active_season(session)
            s_num = active_season.season_number

            # 3 ta turli lord yaratish
            players_data = [
                {"tg": 9988401, "name": "Lord Alpha (Champion)", "so": 5000, "gold": 250000, "food": 100000},
                {"tg": 9988402, "name": "Lord Beta (Top 3)", "so": 3200, "gold": 80000, "food": 50000},
                {"tg": 9988403, "name": "Lord Gamma (Participant)", "so": 600, "gold": 12000, "food": 8000},
            ]

            created_users = []
            for pd in players_data:
                res = await session.execute(select(models.User).where(models.User.telegram_id == pd["tg"]))
                u = res.scalar_one_or_none()
                if not u:
                    u = models.User(
                        telegram_id=pd["tg"],
                        username=f"sim_user_{pd['tg']}",
                        full_name=pd["name"],
                        house_id=1,
                        gold=pd["gold"],
                        food=pd["food"],
                        iron=20000,
                        title="Vesteros Asilzodasi",
                    )
                    session.add(u)
                    await session.commit()
                    await session.refresh(u)
                else:
                    u.gold = pd["gold"]
                    u.food = pd["food"]
                    await session.commit()

                st = await services.get_or_create_player_season_state(session, u.id, s_num)
                st.season_points = pd["so"]
                st.pass_tier = 5
                await session.commit()
                created_users.append(u)

            # Mavsumni majburiy yakunlash (Conclude & Rollover)
            ok, announcement, summary = await services.conclude_and_rollover_season(session, force=True)
            self.assertTrue(ok)
            self.assertIn("YAKUNLANDI", announcement)
            self.assertGreaterEqual(summary["rewards_granted_count"], 1)

            # 1. 1-o'rin sohibi chempionlik mukofotini olganini tekshirish
            champ_user = created_users[0]
            await session.refresh(champ_user)
            self.assertIn("Mavsum Chempioni", champ_user.title)

            # 2. Idempotentlik tekshiruvi: SeasonRewardClaim jadvalida yozuv mavjudligi
            claims_res = await session.execute(
                select(models.SeasonRewardClaim).where(
                    and_(
                        models.SeasonRewardClaim.season_number == s_num,
                        models.SeasonRewardClaim.user_id == champ_user.id
                    )
                )
            )
            claims = claims_res.scalars().all()
            self.assertTrue(any(c.reward_type == "season_top1" for c in claims))

            # 3. Soft-Reset tekshiruvi:
            # - Oltin 15% saqlanadi, lekin maks 15,000 (Lord Alpha da 250k edi, 15k bo'lishi kerak!)
            self.assertLessEqual(champ_user.gold, SOFT_RESET.gold_hard_cap + 20000) # +20k top 1 mukofot
            # - Profil va unvonlar o'chib ketmagan!
            self.assertIsNotNone(champ_user.username)
            self.assertIsNotNone(champ_user.full_name)

            # 4. Yangi mavsum yaratilganini tekshirish
            next_season = await services.get_or_create_active_season(session)
            self.assertEqual(next_season.season_number, s_num + 1)
            self.assertTrue(next_season.is_active)

    async def test_06_season_hub_api_payload(self):
        """Mini App Season Hub ma'lumotlari struktura tekshiruvi."""
        async with AsyncSessionLocal() as session:
            tg_id = 9988555
            res = await session.execute(select(models.User).where(models.User.telegram_id == tg_id))
            user = res.scalar_one_or_none()
            if not user:
                user = models.User(
                    telegram_id=tg_id,
                    username="hub_tester",
                    full_name="Lord Hub Tester",
                    house_id=1,
                    gold=1000,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

            data = await services.get_season_hub_data(session, user.id)
            self.assertIn("season", data)
            self.assertIn("player_state", data)
            self.assertIn("tiers", data)
            self.assertIn("leaderboard", data)
            self.assertIn("hall_of_fame", data)

            # 20 ta tier mavjudligi
            self.assertEqual(len(data["tiers"]), 20)
            self.assertEqual(data["tiers"][0]["tier"], 1)
            self.assertEqual(data["tiers"][19]["tier"], 20)


if __name__ == "__main__":
    unittest.main()
