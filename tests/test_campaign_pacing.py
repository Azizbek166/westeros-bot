"""
Unit tests for Campaign Mission Pacing System (Vaqt limitli kampaniya tizimi).
"""
import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select

from database import crud, models
from database.db import AsyncSessionLocal, init_db
from services.campaign_service import (
    add_campaign_mission,
    calculate_campaign_min_duration_hours,
    create_campaign,
    get_campaign_player_state,
    get_campaign_stats,
    get_campaign_with_missions,
    process_campaign_unlock_notifications,
    seed_sample_campaign,
    simulate_admin_test_step,
    submit_campaign_mission_action,
    toggle_campaign_notifications,
    update_campaign_settings,
)


class TestCampaignPacing(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.tg_id = 998877551
        self.tg_id_2 = 998877552
        async with AsyncSessionLocal() as session:
            for tid, uname in [(self.tg_id, "camp_tester_1"), (self.tg_id_2, "camp_tester_2")]:
                u = await crud.get_user_by_telegram_id(session, tid)
                if not u:
                    u = models.User(
                        telegram_id=tid,
                        username=uname,
                        full_name=f"Lord {uname}",
                        house_id=1,
                        gold=1000,
                        food=1000,
                        iron=1000,
                    )
                    session.add(u)
            await session.commit()
            self.sample_camp = await seed_sample_campaign(session)
            # Clean any prior progress for test users on sample campaign
            await session.execute(
                delete(models.UserCampaignProgress).where(
                    models.UserCampaignProgress.telegram_id.in_([self.tg_id, self.tg_id_2])
                )
            )
            await session.commit()

    async def test_01_sample_campaign_seeded_and_cooldown_locks_next(self):
        t0 = datetime(2026, 12, 1, 10, 0, 0)  # UTC (15:00 Tashkent)
        async with AsyncSessionLocal() as session:
            camp = await get_campaign_with_missions(session, self.sample_camp.id)
            self.assertEqual(camp.title, "The Mystery of the Missing Lord")
            self.assertEqual(len(camp.missions), 5)
            self.assertEqual(camp.default_cooldown_hours, 24)
            self.assertEqual(calculate_campaign_min_duration_hours(camp, camp.missions), 96)  # 4 transitions * 24h

            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            # Complete mission 1 (story)
            res1 = await submit_campaign_mission_action(
                session, user.id, camp.id, mission_order=1, action_value="continue", now_utc=t0
            )
            self.assertTrue(res1["ok"])
            self.assertEqual(res1["next_mission_order"], 2)
            self.assertEqual(res1["next_unlock_at"], t0 + timedelta(hours=24))

            # Mission 2 must be locked immediately after mission 1
            res2_early = await submit_campaign_mission_action(
                session, user.id, camp.id, mission_order=2, action_value="b", now_utc=t0 + timedelta(hours=5)
            )
            self.assertFalse(res2_early["ok"])
            self.assertEqual(res2_early["code"], "locked")

        # Simulate server restart by opening a brand-new session: unlock_at must persist!
        async with AsyncSessionLocal() as session2:
            user2 = await crud.get_user_by_telegram_id(session2, self.tg_id)
            st_before = await get_campaign_player_state(
                session2, user2, self.sample_camp.id, now_utc=t0 + timedelta(hours=23)
            )
            self.assertFalse(st_before["unlocked"])
            self.assertGreater(st_before["remaining_unlock_seconds"], 0)

            # Admin stats must count 1 player waiting on mission 2
            stats = await get_campaign_stats(session2, self.sample_camp.id, now_utc=t0 + timedelta(hours=23))
            self.assertEqual(stats["waiting_by_mission"][2], 1)

            # After 24h, mission 2 unlocks!
            st_after = await get_campaign_player_state(
                session2, user2, self.sample_camp.id, now_utc=t0 + timedelta(hours=24, seconds=1)
            )
            self.assertTrue(st_after["unlocked"])

    async def test_02_daily_attempts_choice_cooldown_and_tashkent_midnight_reset(self):
        # 2026-12-01 18:00 UTC == 2026-12-01 23:00 Asia/Tashkent
        t0 = datetime(2026, 12, 1, 18, 0, 0)
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            camp_id = self.sample_camp.id

            # Finish mission 1 at t0 - 25h so mission 2 (quiz) is unlocked at t0
            r1 = await submit_campaign_mission_action(
                session, user.id, camp_id, 1, "continue", now_utc=t0 - timedelta(hours=25)
            )
            self.assertTrue(r1["ok"])

            # Wrong choice #1 -> triggers 30m choice cooldown
            w1 = await submit_campaign_mission_action(session, user.id, camp_id, 2, "a", now_utc=t0)
            self.assertFalse(w1["ok"])
            self.assertEqual(w1["code"], "wrong_answer")
            self.assertEqual(w1["attempts_left"], 2)

            # Immediate retry during 30m cooldown must be blocked
            w_cd = await submit_campaign_mission_action(
                session, user.id, camp_id, 2, "c", now_utc=t0 + timedelta(minutes=5)
            )
            self.assertFalse(w_cd["ok"])
            self.assertEqual(w_cd["code"], "choice_cooldown")

            # Wrong choice #2 after 31m -> still same Tashkent day (23:31)
            w2 = await submit_campaign_mission_action(
                session, user.id, camp_id, 2, "c", now_utc=t0 + timedelta(minutes=31)
            )
            self.assertFalse(w2["ok"])
            self.assertEqual(w2["attempts_left"], 1)

            # Wrong choice #3 (test using direct time +25m? Wait, 30m cooldown would cross midnight!
            # So let's test at 10:00 UTC for all 3 attempts, then midnight at 19:01 UTC)
        t_day = datetime(2026, 12, 2, 10, 0, 0)  # 15:00 Tashkent (new Tashkent day => reset!)
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            camp_id = self.sample_camp.id
            st_reset = await get_campaign_player_state(session, user, camp_id, now_utc=t_day)
            self.assertEqual(st_reset["attempts_left"], 3)

            # Exhaust all 3 attempts on the same day
            for i in range(3):
                res = await submit_campaign_mission_action(
                    session, user.id, camp_id, 2, "a", now_utc=t_day + timedelta(minutes=35 * i)
                )
                self.assertFalse(res["ok"])
            self.assertEqual(res["code"], "wrong_and_limit_reached")

            # 4th attempt before Tashkent midnight (18:59 UTC == 23:59 Tashkent) must be blocked
            blocked = await submit_campaign_mission_action(
                session, user.id, camp_id, 2, "b", now_utc=datetime(2026, 12, 2, 18, 59, 0)
            )
            self.assertFalse(blocked["ok"])
            self.assertEqual(blocked["code"], "daily_limit_reached")

            # After Tashkent midnight (19:01 UTC == 00:01 Dec 3 Tashkent) -> attempts reset & correct answer succeeds!
            ok_next_day = await submit_campaign_mission_action(
                session, user.id, camp_id, 2, "b", now_utc=datetime(2026, 12, 2, 19, 1, 0)
            )
            self.assertTrue(ok_next_day["ok"])
            self.assertEqual(ok_next_day["next_mission_order"], 3)

    async def test_03_unlock_notification_sent_once_and_respects_toggle(self):
        t0 = datetime(2026, 12, 5, 8, 0, 0)
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            camp_id = self.sample_camp.id
            await submit_campaign_mission_action(session, user.id, camp_id, 1, "continue", now_utc=t0)

            mock_bot = AsyncMock()
            # Before unlock -> 0 notifications
            r_early = await process_campaign_unlock_notifications(
                session, bot=mock_bot, now_utc=t0 + timedelta(hours=12), rate_limit_delay=0
            )
            self.assertEqual(r_early["notified"], 0)
            mock_bot.send_message.assert_not_called()

            # After unlock -> 1 notification sent
            r_due = await process_campaign_unlock_notifications(
                session, bot=mock_bot, now_utc=t0 + timedelta(hours=25), rate_limit_delay=0
            )
            self.assertEqual(r_due["notified"], 1)
            self.assertEqual(mock_bot.send_message.call_count, 1)

            # Run again -> MUST NOT send duplicate notification!
            r_dup = await process_campaign_unlock_notifications(
                session, bot=mock_bot, now_utc=t0 + timedelta(hours=26), rate_limit_delay=0
            )
            self.assertEqual(r_dup["notified"], 0)
            self.assertEqual(mock_bot.send_message.call_count, 1)

            # Toggle notifications OFF -> returns False
            ok_t, enabled = await toggle_campaign_notifications(session, user, camp_id)
            self.assertTrue(ok_t)
            self.assertFalse(enabled)

    async def test_04_admin_test_mode_is_readonly_and_bypasses_wait(self):
        async with AsyncSessionLocal() as session:
            camp_id = self.sample_camp.id
            before_cnt = (
                await session.execute(
                    select(models.UserCampaignProgress).where(
                        models.UserCampaignProgress.campaign_id == camp_id,
                        models.UserCampaignProgress.telegram_id == self.tg_id,
                    )
                )
            ).scalars().all()
            self.assertEqual(len(before_cnt), 0)

            # Step through all 5 missions in admin test mode
            for order, ans in [(1, "continue"), (2, "b"), (3, "mercy"), (4, "qarg'a"), (5, "a")]:
                sim = await simulate_admin_test_step(session, camp_id, order, ans)
                self.assertTrue(sim["ok"])
                self.assertTrue(sim["test_mode"])
            self.assertTrue(sim["completed_campaign"])

            # Still zero rows written to UserCampaignProgress!
            after_cnt = (
                await session.execute(
                    select(models.UserCampaignProgress).where(
                        models.UserCampaignProgress.campaign_id == camp_id,
                        models.UserCampaignProgress.telegram_id == self.tg_id,
                    )
                )
            ).scalars().all()
            self.assertEqual(len(after_cnt), 0)

    async def test_05_calendar_mode_and_settings_update(self):
        async with AsyncSessionLocal() as session:
            cal_camp = await create_campaign(
                session=session,
                title="Calendar Test Campaign",
                description="Dates test",
                unlock_mode="calendar",
                default_cooldown_hours=24,
                status="published",
            )
            d1 = datetime(2026, 12, 10, 5, 0, 0)  # 10:00 Tashkent
            d2 = datetime(2026, 12, 12, 5, 0, 0)  # 2 days later
            await add_campaign_mission(session, cal_camp.id, 1, "M1", "Story 1", "story", calendar_unlock_at=d1)
            await add_campaign_mission(session, cal_camp.id, 2, "M2", "Story 2", "story", calendar_unlock_at=d2)

            user = await crud.get_user_by_telegram_id(session, self.tg_id)

            # Before d1 -> mission 1 locked
            r_pre = await submit_campaign_mission_action(
                session, user.id, cal_camp.id, 1, "continue", now_utc=d1 - timedelta(hours=1)
            )
            self.assertFalse(r_pre["ok"])
            self.assertEqual(r_pre["code"], "locked")

            # At d1 -> mission 1 succeeds, mission 2 locked until d2
            r_d1 = await submit_campaign_mission_action(session, user.id, cal_camp.id, 1, "continue", now_utc=d1)
            self.assertTrue(r_d1["ok"])
            self.assertEqual(r_d1["next_unlock_at"], d2)

            # Before d2 -> mission 2 locked
            r_mid = await submit_campaign_mission_action(
                session, user.id, cal_camp.id, 2, "continue", now_utc=d1 + timedelta(hours=30)
            )
            self.assertFalse(r_mid["ok"])
            self.assertEqual(r_mid["code"], "locked")

            # At d2 -> mission 2 succeeds
            r_d2 = await submit_campaign_mission_action(session, user.id, cal_camp.id, 2, "continue", now_utc=d2)
            self.assertTrue(r_d2["ok"])
            self.assertTrue(r_d2["completed_campaign"])

            # Updating settings on published campaign does not reset completed progress
            ok_u, _, _ = await update_campaign_settings(session, cal_camp.id, default_cooldown_hours=48)
            self.assertTrue(ok_u)
            st_done = await get_campaign_player_state(session, user, cal_camp.id, now_utc=d2)
            self.assertTrue(st_done["progress"].is_completed)

            # Cleanup temporary test campaign and children
            await session.execute(delete(models.UserCampaignProgress).where(models.UserCampaignProgress.campaign_id == cal_camp.id))
            await session.execute(delete(models.CampaignMission).where(models.CampaignMission.campaign_id == cal_camp.id))
            await session.execute(delete(models.Campaign).where(models.Campaign.id == cal_camp.id))
            await session.commit()

    async def test_06_bypass_attempts_old_button_and_double_click(self):
        t0 = datetime(2026, 12, 15, 10, 0, 0)
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id_2)
            user.gold = 0
            await session.commit()
            uid = user.id
            camp_id = self.sample_camp.id

        # Simulate concurrent double-click using two separate DB sessions at the exact same instant
        async def _submit_once():
            async with AsyncSessionLocal() as s:
                return await submit_campaign_mission_action(s, uid, camp_id, 1, "continue", now_utc=t0)

        res_a, res_b = await asyncio.gather(_submit_once(), _submit_once())
        ok_count = sum(1 for r in (res_a, res_b) if r["ok"])
        stale_count = sum(1 for r in (res_a, res_b) if r.get("code") == "stale_mission")
        self.assertEqual(ok_count, 1)
        self.assertEqual(stale_count, 1)

        # Verify mission 1 reward (1500 gold) was granted ONLY ONCE and clicking old mission 1 button fails
        async with AsyncSessionLocal() as session:
            u_after = await crud.get_user_by_telegram_id(session, self.tg_id_2)
            self.assertEqual(u_after.gold, 1500)
            old_btn = await submit_campaign_mission_action(session, uid, camp_id, 1, "continue", now_utc=t0 + timedelta(minutes=1))
            self.assertFalse(old_btn["ok"])
            self.assertEqual(old_btn["code"], "stale_mission")


if __name__ == "__main__":
    unittest.main()
