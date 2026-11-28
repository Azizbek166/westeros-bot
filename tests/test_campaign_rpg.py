"""
Unit tests for Campaign RPG mechanics:
- min_level gate
- COMBAT_ENCOUNTER (defeat & victory using real RPG stats)
- RESOURCE_TRIBUTE (insufficient resources & payment)
- NARRATIVE_CHOICE with gold_penalty
- Grand Finale completion rewards (Gold, Title, Achievement) + anti-duplicate claim
- Admin stage delete & re-numbering
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select

from database import crud, models
from database.db import AsyncSessionLocal, init_db
from services.campaign_service import (
    add_campaign_mission,
    create_campaign,
    delete_campaign_mission,
    get_campaign_with_missions,
    submit_campaign_mission_action,
)


class TestCampaignRPG(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.tg_id = 998877330
        async with AsyncSessionLocal() as session:
            u = await crud.get_user_by_telegram_id(session, self.tg_id)
            if not u:
                u = models.User(
                    telegram_id=self.tg_id,
                    username="camp_rpg_tester",
                    full_name="Lord RPG Tester",
                    house_id=1,
                    level=1,
                    gold=100,
                    food=100,
                    iron=100,
                )
                session.add(u)
                await session.commit()
            await session.execute(
                delete(models.UserAchievement).where(
                    models.UserAchievement.user_id == u.id,
                    models.UserAchievement.achievement_code == "camp_rpg_test_ach",
                )
            )
            await session.commit()

    async def test_01_full_rpg_campaign_flow_and_edge_cases(self):
        t0 = datetime(2026, 12, 20, 10, 0, 0)
        async with AsyncSessionLocal() as session:
            camp = await create_campaign(
                session=session,
                title="Haunted Forest Expedition",
                description="4-stage RPG campaign test",
                status="published",
                min_level=3,
                default_cooldown_hours=0,  # 0h for fast sequential RPG test
                default_choice_cooldown_minutes=0,
                completion_rewards={
                    "gold": 5000,
                    "xp": 300,
                    "title": "Hand of the Investigation",
                    "achievement_code": "camp_rpg_test_ach",
                    "achievement_name": "Forest Investigator",
                },
            )
            # Ensure no orphan rows from prior SQLite test runs with reused campaign ID
            await session.execute(delete(models.CampaignMission).where(models.CampaignMission.campaign_id == camp.id))
            await session.execute(delete(models.UserCampaignProgress).where(models.UserCampaignProgress.campaign_id == camp.id))
            await session.commit()
            # Stage 1: RESOURCE_TRIBUTE (cost 500 gold)
            await add_campaign_mission(
                session, camp.id, 1, "Bribe the Guard", "Guard wants 500 gold.",
                mission_type="tribute",
                task_data={"cost_gold": 500},
                success_text="The guard whispers the secret route.",
                reward_xp=20,
            )
            # Stage 2: NARRATIVE_CHOICE with gold_penalty
            await add_campaign_mission(
                session, camp.id, 2, "Interrogate Suspect", "Pick the right tactic.",
                mission_type="narrative_choice",
                options=[
                    {"key": "bad", "text": "Threaten blindly", "is_correct": False, "gold_penalty": 200, "outcome": "You lost 200 gold in a trap!"},
                    {"key": "good", "text": "Show the silver seal", "is_correct": True, "outcome": "He confesses immediately!"},
                ],
                correct_answer="good",
                reward_gold=300,
            )
            # Stage 3: COMBAT_ENCOUNTER (enemy_power = 900)
            await add_campaign_mission(
                session, camp.id, 3, "Haunted Forest Ambush", "Bandits attack!",
                mission_type="combat",
                task_data={"enemy_name": "Wildling Ambush", "enemy_power": 900, "defeat_gold_penalty": 100},
                success_text="The ambush is crushed!",
                reward_gold=400,
            )
            # Stage 4: RIDDLE_INVESTIGATION (Finale)
            await add_campaign_mission(
                session, camp.id, 4, "Final Conspiracy", "Name the traitor.",
                mission_type="riddle",
                correct_answer="maester|meyster",
                task_data={"clue_text": "Look at the forged raven seal."},
                success_text="The traitor is exposed!",
                reward_gold=1000,
            )

            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            user.level = 1
            user.gold = 100
            await session.commit()

            # 1. Level gate blocks level 1 user (min_level=3)
            r_lvl = await submit_campaign_mission_action(session, user.id, camp.id, 1, "pay", now_utc=t0)
            self.assertFalse(r_lvl["ok"])
            self.assertEqual(r_lvl["code"], "level_too_low")

            # Raise level to 3 -> tribute fails due to insufficient gold (100 < 500)
            user.level = 3
            await session.commit()
            r_poor = await submit_campaign_mission_action(session, user.id, camp.id, 1, "pay", now_utc=t0)
            self.assertFalse(r_poor["ok"])
            self.assertEqual(r_poor["code"], "insufficient_resources")
            self.assertEqual(user.gold, 100)  # Gold untouched

            # Give 600 gold -> Stage 1 tribute succeeds (600 - 500 = 100)
            user.gold = 600
            await session.commit()
            r1 = await submit_campaign_mission_action(session, user.id, camp.id, 1, "pay", now_utc=t0)
            self.assertTrue(r1["ok"])
            await session.refresh(user)
            self.assertEqual(user.gold, 100)

            # Stage 2: Wrong choice deducts penalty capped at available gold (100, never negative)
            r2_bad = await submit_campaign_mission_action(session, user.id, camp.id, 2, "bad", now_utc=t0)
            self.assertFalse(r2_bad["ok"])
            await session.refresh(user)
            self.assertEqual(user.gold, 0)

            # Stage 2: Correct choice advances (+300 gold)
            r2_ok = await submit_campaign_mission_action(session, user.id, camp.id, 2, "good", now_utc=t0)
            self.assertTrue(r2_ok["ok"])
            await session.refresh(user)
            self.assertEqual(user.gold, 300)

            # Stage 3: Combat defeat at level 3 (power=450 < 900)
            r3_lose = await submit_campaign_mission_action(session, user.id, camp.id, 3, "fight", now_utc=t0)
            self.assertFalse(r3_lose["ok"])
            self.assertEqual(r3_lose["code"], "combat_defeat")
            await session.refresh(user)
            self.assertEqual(user.gold, 200)  # 300 - 100 defeat penalty

            # Level up to 8 (power=1200 >= 900) -> Combat victory (+400 gold => 600)
            user.level = 8
            await session.commit()
            r3_win = await submit_campaign_mission_action(session, user.id, camp.id, 3, "fight", now_utc=t0)
            self.assertTrue(r3_win["ok"])
            await session.refresh(user)
            self.assertEqual(user.gold, 600)

            # Stage 4: Finale riddle -> grants stage (1000) + grand rewards (5000 gold, Title, Achievement)
            r4 = await submit_campaign_mission_action(session, user.id, camp.id, 4, "maester", now_utc=t0)
            self.assertTrue(r4["ok"])
            self.assertTrue(r4["completed_campaign"])
            await session.refresh(user)
            self.assertEqual(user.gold, 6600)  # 600 + 1000 + 5000
            self.assertEqual(user.title, "Hand of the Investigation")

            achs = (
                await session.execute(
                    select(models.UserAchievement).where(
                        models.UserAchievement.user_id == user.id,
                        models.UserAchievement.achievement_code == "camp_rpg_test_ach",
                    )
                )
            ).scalars().all()
            self.assertEqual(len(achs), 1)

            # Duplicate completion claim attempt MUST be rejected
            r4_dup = await submit_campaign_mission_action(session, user.id, camp.id, 4, "maester", now_utc=t0 + timedelta(minutes=1))
            self.assertFalse(r4_dup["ok"])
            self.assertEqual(r4_dup["code"], "already_completed")
            await session.refresh(user)
            self.assertEqual(user.gold, 6600)

            # Admin delete stage 2 -> remaining stages re-numbered 1, 2, 3
            camp_ref = await get_campaign_with_missions(session, camp.id)
            m2 = next(m for m in camp_ref.missions if m.order_index == 2)
            ok_del, _ = await delete_campaign_mission(session, m2.id)
            self.assertTrue(ok_del)
            camp_after = await get_campaign_with_missions(session, camp.id)
            self.assertEqual([m.order_index for m in camp_after.missions], [1, 2, 3])

            # Cleanup temporary campaign and children
            await session.execute(delete(models.UserCampaignProgress).where(models.UserCampaignProgress.campaign_id == camp.id))
            await session.execute(delete(models.CampaignMission).where(models.CampaignMission.campaign_id == camp.id))
            await session.execute(delete(models.Campaign).where(models.Campaign.id == camp.id))
            await session.commit()


if __name__ == "__main__":
    unittest.main()
