"""
Unit tests for Step 3: Weekly & Dragon Missions (data/missions_data.py, services/mission_service.py).
"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete
from database.db import AsyncSessionLocal, init_db
from database import models, crud
from data.missions_data import WEEKLY_MISSIONS, WEEKLY_ALL_BONUS
from services.mission_service import (
    get_current_week_bounds,
    track_event,
    get_missions_overview,
    claim_mission_reward,
)


class TestMissionsSystem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.tg_id = 998877662
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            if not user:
                user = models.User(
                    telegram_id=self.tg_id,
                    username="mission_tester",
                    full_name="Mission Tester",
                    house_id=1,
                    gold=100,
                    food=100,
                    iron=100,
                    xp=0,
                    prestige=0,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            else:
                user.gold = 100
                user.food = 100
                user.iron = 100
                user.xp = 0
                user.prestige = 0
                await session.commit()
            self.user_db_id = user.id

            await session.execute(delete(models.MissionClaim).where(models.MissionClaim.user_id == self.user_db_id))
            await session.execute(delete(models.MissionProgress).where(models.MissionProgress.user_id == self.user_db_id))
            await session.execute(delete(models.Duel).where(models.Duel.winner_id == self.user_db_id))
            await session.commit()

    async def test_01_no_p2w_rewards_in_missions(self):
        for m in WEEKLY_MISSIONS + [WEEKLY_ALL_BONUS]:
            self.assertNotIn("infantry", m)
            self.assertNotIn("dragon", m)
            self.assertGreater(m["gold"], 0)
            self.assertGreater(m["xp"], 0)

    async def test_02_progress_and_claim_and_double_claim_block(self):
        async with AsyncSessionLocal() as session:
            # Track 5 secret quests via track_event
            for _ in range(5):
                await track_event(self.user_db_id, "secret_quest", 1, session=session)
            await session.commit()

            overview = await get_missions_overview(session, self.tg_id)
            self.assertTrue(overview["found"])
            sec_item = next(x for x in overview["missions"] if x["code"] == "wk_secret")
            self.assertEqual(sec_item["current"], 5)
            self.assertEqual(sec_item["status"], "claimable")

            ok1, msg1, rew1 = await claim_mission_reward(session, self.tg_id, "wk_secret")
            self.assertTrue(ok1)
            self.assertEqual(rew1["gold"], sec_item["gold"])

            # Double claim must be blocked
            ok2, msg2, _ = await claim_mission_reward(session, self.tg_id, "wk_secret")
            self.assertFalse(ok2)
            self.assertIn("allaqachon", msg2)

    async def test_03_db_duel_progress_and_weekly_reset(self):
        period_key, week_start_utc, _, _ = get_current_week_bounds()
        async with AsyncSessionLocal() as session:
            for _ in range(5):
                session.add(models.Duel(
                    challenger_id=self.user_db_id,
                    opponent_id=self.user_db_id,
                    winner_id=self.user_db_id,
                    status="completed",
                    created_at=week_start_utc + timedelta(minutes=10),
                ))
            # Old duel from last week must not count
            session.add(models.Duel(
                challenger_id=self.user_db_id,
                opponent_id=self.user_db_id,
                winner_id=self.user_db_id,
                status="completed",
                created_at=week_start_utc - timedelta(days=2),
            ))
            await session.commit()

            overview = await get_missions_overview(session, self.tg_id)
            duel_item = next(x for x in overview["missions"] if x["code"] == "wk_duel")
            self.assertEqual(duel_item["current"], 5)
            self.assertEqual(duel_item["status"], "claimable")

            # Simulate next week period_key -> progress resets
            next_week_start = week_start_utc + timedelta(days=7)
            with patch(
                "services.mission_service.get_current_week_bounds",
                return_value=("2099-01-05", next_week_start, next_week_start + timedelta(days=7), "6 kun"),
            ):
                overview_next = await get_missions_overview(session, self.tg_id)
                duel_next = next(x for x in overview_next["missions"] if x["code"] == "wk_duel")
                self.assertEqual(duel_next["current"], 0)
                self.assertEqual(duel_next["status"], "in_progress")

    async def test_04_track_event_error_does_not_raise(self):
        with patch("services.mission_service.get_current_week_bounds", side_effect=RuntimeError("boom")):
            # Should swallow and log, never crash caller
            await track_event(self.user_db_id, "dragon_feed", 1)


if __name__ == "__main__":
    unittest.main()
