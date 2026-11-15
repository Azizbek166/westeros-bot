"""
Unit tests for Step 5: Profile Extras Studio (services/profile_extras_service.py, handlers/profile_handler.py).
"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import AsyncSessionLocal, init_db
from database import models, crud
from handlers.profile_handler import format_user_profile_card
from services.profile_extras_service import (
    sanitize_profile_text,
    set_castle_name,
    set_victory_message,
    set_profile_theme,
    admin_clear_user_profile_text,
    has_min_vip_tier,
)


class TestProfileExtras(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.tg_id = 998877664
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            if not user:
                user = models.User(
                    telegram_id=self.tg_id,
                    username="pfx_tester",
                    full_name="Profile Tester",
                    house_id=1,
                    vip_tier="sovereign",
                    vip_until=datetime.utcnow() + timedelta(days=10),
                )
                session.add(user)
            else:
                user.vip_tier = "sovereign"
                user.vip_until = datetime.utcnow() + timedelta(days=10)
            await session.commit()

    async def test_01_sanitize_and_length_limits(self):
        ok_url, _ = sanitize_profile_text("https://t.me/spam", 50)
        self.assertFalse(ok_url)
        ok_at, _ = sanitize_profile_text("Salom @username", 50)
        self.assertFalse(ok_at)
        ok_len, _ = sanitize_profile_text("A" * 25, 24)
        self.assertFalse(ok_len)
        ok_good, cleaned = sanitize_profile_text("  Winterfell  ", 24)
        self.assertTrue(ok_good)
        self.assertEqual(cleaned, "Winterfell")

    async def test_02_vip_tier_hierarchy_and_admin_clear(self):
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, self.tg_id)
            self.assertTrue(has_min_vip_tier(user, "knight"))
            self.assertTrue(has_min_vip_tier(user, "sovereign"))

            ok_t, _ = await set_profile_theme(session, self.tg_id, "fire")
            ok_c, _ = await set_castle_name(session, self.tg_id, "Qora Qasr")
            ok_v, _ = await set_victory_message(session, self.tg_id, "Shimol eslaydi!")
            self.assertTrue(ok_t and ok_c and ok_v)

            ok_clr, _ = await admin_clear_user_profile_text(session, self.tg_id, "all")
            self.assertTrue(ok_clr)

    async def test_03_profile_card_fallback_on_extras_error(self):
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_with_relations(session, self.tg_id)
            with patch("services.profile_extras_service.get_profile_extras_view", side_effect=RuntimeError("db err")):
                text, _, _, _, _ = await format_user_profile_card(user, session)
                self.assertIn("Xazina", text)


if __name__ == "__main__":
    unittest.main()
