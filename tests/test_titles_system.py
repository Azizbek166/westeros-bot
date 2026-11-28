"""
Unit tests for Player Titles (Unvonlar) System, Profile/Leaderboard integration, and Campaign hook.
"""
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete

from database import crud, models
from database.db import AsyncSessionLocal, init_db
from handlers.profile_handler import format_user_profile_card
from handlers.ranking_handler import get_user_display_name
from handlers.title_handler import menu_titles_callback, titles_list_callback
from services.title_service import (
    equip_user_title,
    find_user_by_identifier,
    get_or_create_title,
    get_user_titles_overview,
    grant_title_to_user,
    seed_default_titles,
)


class TestTitlesSystem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.tg_id = 998877111
        async with AsyncSessionLocal() as session:
            u = await crud.get_user_by_telegram_id(session, self.tg_id)
            if not u:
                u = models.User(
                    telegram_id=self.tg_id,
                    username="title_tester",
                    full_name="Lord Jon",
                    house_id=1,
                    level=5,
                    gold=1000,
                )
                session.add(u)
                await session.commit()
            await session.execute(delete(models.UserTitle).where(models.UserTitle.user_id == u.id))
            u.active_title_id = None
            u.title = None
            await session.commit()

    async def test_01_seed_grant_equip_profile_and_leaderboard(self):
        async with AsyncSessionLocal() as session:
            titles = await seed_default_titles(session)
            names = {t.name for t in titles}
            for expected in ("Tergov Qo'li", "Shivirlar Ustasi", "Devor Qo‘riqchisi", "Temir Bank Hamkori"):
                self.assertIn(expected, names)

            user = await crud.get_user_by_telegram_id(session, self.tg_id)

            # Cannot equip a locked title
            whispers = next(t for t in titles if t.code == "master_of_whispers")
            ok_locked, _ = await equip_user_title(session, user.id, whispers.id)
            self.assertFalse(ok_locked)

            # Grant title (idempotent)
            ok1, newly1, t1 = await grant_title_to_user(session, user.id, title_code="master_of_whispers")
            self.assertTrue(ok1 and newly1 and t1.id == whispers.id)
            ok2, newly2, _ = await grant_title_to_user(session, user.id, title_code="master_of_whispers")
            self.assertTrue(ok2 and not newly2)

            # Equip title
            ok_eq, _ = await equip_user_title(session, user.id, whispers.id)
            self.assertTrue(ok_eq)
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            self.assertEqual(user.active_title_id, whispers.id)
            self.assertEqual(user.title, "Shivirlar Ustasi")

            # Profile card & leaderboard display equipped title
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload
            u_full = (
                await session.execute(
                    select(models.User)
                    .where(models.User.id == user.id)
                    .options(
                        selectinload(models.User.army),
                        selectinload(models.User.house),
                        selectinload(models.User.characters),
                    )
                )
            ).scalar_one()
            card_text, _, _, _, _ = await format_user_profile_card(u_full, session, is_group=False)
            self.assertIn("🕷️ \\[Shivirlar Ustasi\\] Lord Jon", card_text)
            rank_name = get_user_display_name(u_full)
            self.assertIn("[Shivirlar Ustasi]", rank_name)

            # Overview counts
            ov = await get_user_titles_overview(session, user)
            self.assertEqual(ov["unlocked_count"], 1)
            self.assertGreaterEqual(ov["total_count"], 4)
            self.assertEqual(ov["active_title"].id, whispers.id)

            # Unequip title
            ok_un, _ = await equip_user_title(session, user.id, None)
            self.assertTrue(ok_un)
            await session.refresh(user)
            self.assertIsNone(user.active_title_id)

    async def test_02_titles_panel_ui_and_admin_custom_grant(self):
        async with AsyncSessionLocal() as session:
            custom_t = await get_or_create_title(
                session,
                "Turnir Chempioni",
                icon="⚔️",
                rarity="AFSONAVIY",
                description="Maxsus turnir mukofoti",
            )
            found = await find_user_by_identifier(session, "@title_tester")
            self.assertIsNotNone(found)
            self.assertEqual(found.telegram_id, self.tg_id)
            ok_g, _, _ = await grant_title_to_user(session, found.id, title_id=custom_t.id)
            self.assertTrue(ok_g)

        q = MagicMock()
        q.from_user.id = self.tg_id
        q.data = "menu_titles"
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        q.message.reply_text = AsyncMock()
        await menu_titles_callback(MagicMock(callback_query=q), MagicMock(user_data={}))
        txt_unlocked = q.edit_message_text.call_args.args[0]
        self.assertIn("UNVONLARIM PANELI", txt_unlocked)
        self.assertIn("Turnir Chempioni", txt_unlocked)

        q.data = "titles_list:locked:0"
        q.edit_message_text.reset_mock()
        await titles_list_callback(MagicMock(callback_query=q), MagicMock(user_data={}))
        txt_locked = q.edit_message_text.call_args.args[0]
        self.assertIn("QULFLANGAN UNVONLAR", txt_locked)


if __name__ == "__main__":
    unittest.main()
