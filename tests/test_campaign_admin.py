"""
Unit tests for Admin Campaign Management & Analytics Panel.
"""
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import OWNER_ID
from database import crud, models
from database.db import AsyncSessionLocal, init_db
from handlers.campaign_handler import (
    _clear_admin_campaign_fsm,
    admin_camp_new_callback,
    admin_camp_stats_callback,
    admin_campaigns_callback,
    campaign_text_input_handler,
)
from services.campaign_service import (
    add_campaign_mission,
    create_campaign,
    delete_campaign,
    get_campaign_stats,
    list_campaigns,
    submit_campaign_mission_action,
    update_campaign_info,
    update_campaign_settings,
    update_mission_details,
)


class TestCampaignAdminPanel(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.tg_id_a = 998877201
        self.tg_id_b = 998877202
        async with AsyncSessionLocal() as session:
            for tid, uname in [(self.tg_id_a, "adm_stat_a"), (self.tg_id_b, "adm_stat_b")]:
                u = await crud.get_user_by_telegram_id(session, tid)
                if not u:
                    session.add(models.User(
                        telegram_id=tid,
                        username=uname,
                        full_name=f"Lord {uname}",
                        house_id=1,
                        level=10,
                        gold=5000,
                    ))
            await session.commit()

    async def test_01_publish_guard_edit_analytics_and_delete(self):
        t0 = datetime(2026, 12, 25, 10, 0, 0)
        async with AsyncSessionLocal() as session:
            from sqlalchemy import delete as sa_delete
            camp = await create_campaign(
                session=session,
                title="Admin Test Campaign",
                description="Draft description",
                status="draft",
                min_level=2,
                default_cooldown_hours=0,
                completion_rewards={"gold": 1200, "title": "Test Master"},
            )
            await session.execute(sa_delete(models.CampaignMission).where(models.CampaignMission.campaign_id == camp.id))
            await session.execute(sa_delete(models.UserCampaignProgress).where(models.UserCampaignProgress.campaign_id == camp.id))
            await session.commit()
            # 1. Cannot publish a campaign with 0 stages
            ok_pub0, msg_pub0, _ = await update_campaign_settings(session, camp.id, status="published")
            self.assertFalse(ok_pub0)
            self.assertIn("Kamida 1 ta bosqich", msg_pub0)

            # Not visible in player list while draft
            pub_ids = [c.id for c in await list_campaigns(session, include_drafts=False)]
            self.assertNotIn(camp.id, pub_ids)

            # 2. Add 2 stages, edit stage 1, edit campaign info, then publish
            m1 = await add_campaign_mission(session, camp.id, 1, "S1", "Story 1", "story", reward_gold=100, reward_xp=50)
            await add_campaign_mission(session, camp.id, 2, "S2", "Story 2", "story", reward_gold=200, reward_xp=100)

            ok_ed, _, _ = await update_campaign_info(session, camp.id, title="Admin Edited Campaign", min_level=3)
            self.assertTrue(ok_ed)
            ok_me, _, _ = await update_mission_details(session, m1.id, story_text="Updated Story 1", reward_gold=150)
            self.assertTrue(ok_me)

            ok_pub1, _, _ = await update_campaign_settings(session, camp.id, status="published")
            self.assertTrue(ok_pub1)

            # Immediately visible in player's campaigns list
            pub_ids_after = [c.id for c in await list_campaigns(session, include_drafts=False)]
            self.assertIn(camp.id, pub_ids_after)

            # 3. Simulate 2 players: A finishes both stages (Completed), B finishes stage 1 (In Progress at stage 2)
            ua = await crud.get_user_by_telegram_id(session, self.tg_id_a)
            ub = await crud.get_user_by_telegram_id(session, self.tg_id_b)
            await submit_campaign_mission_action(session, ua.id, camp.id, 1, "continue", now_utc=t0)
            await submit_campaign_mission_action(session, ua.id, camp.id, 2, "continue", now_utc=t0)
            await submit_campaign_mission_action(session, ub.id, camp.id, 1, "continue", now_utc=t0)

            # 4. Analytics check
            stats = await get_campaign_stats(session, camp.id, now_utc=t0)
            self.assertEqual(stats["total_players"], 2)
            self.assertEqual(stats["in_progress_players"], 1)
            self.assertEqual(stats["completed_players"], 1)
            self.assertEqual(stats["completion_rate_pct"], 50.0)
            self.assertEqual(stats["in_progress_by_mission"][2], 1)
            self.assertEqual(len(stats["recent_completers"]), 1)
            self.assertEqual(stats["recent_completers"][0]["username"], "adm_stat_a")

            # Render admin stats & admin campaigns list callbacks
            q = MagicMock()
            q.from_user.id = OWNER_ID
            q.data = f"admin_camp_stats:{camp.id}"
            q.answer = AsyncMock()
            q.edit_message_text = AsyncMock()
            q.message.reply_text = AsyncMock()
            await admin_camp_stats_callback(MagicMock(callback_query=q), MagicMock(user_data={}))
            stats_txt = q.edit_message_text.call_args.args[0]
            self.assertIn("50.0%", stats_txt)
            self.assertIn("adm\\_stat\\_a", stats_txt)

            q.data = "admin_campaigns"
            q.edit_message_text.reset_mock()
            await admin_campaigns_callback(MagicMock(callback_query=q), MagicMock(user_data={}))
            list_txt = q.edit_message_text.call_args.args[0]
            self.assertIn("Admin Edited Campaign", list_txt)
            self.assertIn("2 bosqich | 2 o'yinchi", list_txt)

            # 5. Delete campaign cleanly
            ok_del, _ = await delete_campaign(session, camp.id)
            self.assertTrue(ok_del)
            pub_ids_final = [c.id for c in await list_campaigns(session, include_drafts=True)]
            self.assertNotIn(camp.id, pub_ids_final)

    async def test_02_wizard_numeric_validation_and_cancel_cleanup(self):
        ctx = MagicMock()
        ctx.user_data = {}

        # Start wizard
        q = MagicMock()
        q.from_user.id = OWNER_ID
        q.data = "admin_camp_new"
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        await admin_camp_new_callback(MagicMock(callback_query=q), ctx)
        self.assertEqual(ctx.user_data["admin_camp_wizard"]["step"], "title")

        # Send title & description
        async def send_text(val: str):
            msg = MagicMock()
            msg.text = val
            msg.reply_text = AsyncMock()
            upd = MagicMock(message=msg)
            upd.effective_user.id = OWNER_ID
            await campaign_text_input_handler(upd, ctx)
            return msg.reply_text

        await send_text("Test Wizard Camp")
        await send_text("Test lore description")
        self.assertEqual(ctx.user_data["admin_camp_wizard"]["step"], "min_level")

        # Invalid numeric input -> stays on min_level with Uzbek error
        rep = await send_text("abc")
        self.assertEqual(ctx.user_data["admin_camp_wizard"]["step"], "min_level")
        self.assertIn("Noto'g'ri son", rep.call_args.args[0])

        # Valid numeric input -> advances to reward_gold
        await send_text("5")
        self.assertEqual(ctx.user_data["admin_camp_wizard"]["step"], "reward_gold")
        self.assertEqual(ctx.user_data["admin_camp_wizard"]["min_level"], 5)

        # /cancel clears all FSM keys cleanly
        await send_text("/cancel")
        self.assertNotIn("admin_camp_wizard", ctx.user_data)
        _clear_admin_campaign_fsm(ctx.user_data)


if __name__ == "__main__":
    unittest.main()
