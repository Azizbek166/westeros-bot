"""
Unit tests for Step 2: Secret Quests fixes in handlers/quest_handler.py
a) Insufficient gold prevents negative-gold choice, does not increment limit, and keeps quest active for another choice.
b) Missing current_secret_quest (after bot restart) shows expired message and grants nothing.
c) Double-click / daily limit exceeded blocks duplicate reward.
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from database.db import AsyncSessionLocal, init_db
from database import models, crud
from data.quests_data import SECRET_QUESTS
from handlers.quest_handler import secret_choice_callback
from config import DAILY_SECRET_QUEST_LIMIT


def _make_update_context(tg_id: int, choice_idx: int, user_data: dict):
    query = MagicMock()
    query.data = f"secret_choice:{choice_idx}"
    query.from_user = SimpleNamespace(id=tg_id)
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data=user_data)
    return update, context, query


class TestSecretQuestsFixes(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.tg_id = 998877661
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            if not user:
                user = models.User(
                    telegram_id=self.tg_id,
                    username="secret_tester",
                    full_name="Secret Tester",
                    house_id=1,
                    gold=10,
                    prestige=5,
                    xp=0,
                )
                session.add(user)
            else:
                user.gold = 10
                user.prestige = 5
                user.xp = 0
                user.daily_secret_quest_count = 0
                user.daily_limit_date = crud.get_game_today_str()
            await session.commit()

    async def test_a_insufficient_gold_blocks_costly_choice_and_keeps_quest(self):
        # SECRET_QUESTS[1] choice 0 has gold_reward = -250
        sq = SECRET_QUESTS[1]
        user_data = {"current_secret_quest": sq}
        update, context, query = _make_update_context(self.tg_id, 0, user_data)

        await secret_choice_callback(update, context)

        query.answer.assert_awaited()
        args, kwargs = query.answer.call_args
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("yetarli oltin yo'q", args[0])
        # Quest should still be in user_data so player can choose another option
        self.assertIn("current_secret_quest", context.user_data)

        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            self.assertEqual(user.daily_secret_quest_count, 0)
            self.assertEqual(user.gold, 10)
            self.assertEqual(user.xp, 0)

        # Now pick choice 2 (free, +50 gold)
        update2, context2, query2 = _make_update_context(self.tg_id, 2, context.user_data)
        await secret_choice_callback(update2, context2)
        query2.edit_message_text.assert_awaited()

        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            self.assertEqual(user.daily_secret_quest_count, 1)
            self.assertEqual(user.gold, 60)
            self.assertEqual(user.xp, 100)

    async def test_b_missing_quest_after_restart_gives_nothing(self):
        user_data = {}  # Empty after restart
        update, context, query = _make_update_context(self.tg_id, 0, user_data)

        await secret_choice_callback(update, context)

        query.answer.assert_awaited()
        args, kwargs = query.answer.call_args
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("muddati tugadi", args[0])

        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            self.assertEqual(user.daily_secret_quest_count, 0)
            self.assertEqual(user.gold, 10)
            self.assertEqual(user.xp, 0)

    async def test_c_double_click_and_daily_limit_protection(self):
        sq = SECRET_QUESTS[0]
        user_data = {"current_secret_quest": sq}
        update1, context1, query1 = _make_update_context(self.tg_id, 0, user_data)
        update2, context2, query2 = _make_update_context(self.tg_id, 0, user_data)

        # First click succeeds and pops current_secret_quest
        await secret_choice_callback(update1, context1)
        # Second click sees missing current_secret_quest
        await secret_choice_callback(update2, context2)

        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            self.assertEqual(user.daily_secret_quest_count, 1)
            self.assertEqual(user.gold, 160)
            self.assertEqual(user.xp, 100)

            # Now set count to limit and try a new quest
            user.daily_secret_quest_count = DAILY_SECRET_QUEST_LIMIT
            await session.commit()

        user_data_limit = {"current_secret_quest": sq}
        update3, context3, query3 = _make_update_context(self.tg_id, 0, user_data_limit)
        await secret_choice_callback(update3, context3)
        args, kwargs = query3.answer.call_args
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("tugadi", args[0])


if __name__ == "__main__":
    unittest.main()
