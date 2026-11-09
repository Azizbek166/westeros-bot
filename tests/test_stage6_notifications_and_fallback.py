"""
STAGE 6: NOTIFICATIONS & BOT ROLE TEST SUITE
Tests notification keyboard builders, WebApp deep-linking URLs, and legacy bot menu fallbacks.
Ensures the bot acts as an effective notification channel and a robust fallback interface.
"""
import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import get_miniapp_url, MINI_APP_URL
from keyboards.notification_keyboards import (
    attack_alert_keyboard,
    duel_challenge_keyboard,
    daily_reward_ready_keyboard,
    quiz_reminder_keyboard,
    bank_interest_ready_keyboard,
    guild_event_keyboard,
)
from keyboards.menus import main_menu_keyboard


def run_tests():
    print("=" * 50)
    print("STAGE 6: NOTIFICATIONS & BOT ROLE TESTS")
    print("=" * 50)

    # -------------------------------------------------------------
    # TEST 1: Mini App Deep-Link URL Generator
    # -------------------------------------------------------------
    base_url = get_miniapp_url()
    assert base_url == MINI_APP_URL.rstrip("/"), f"Expected {MINI_APP_URL.rstrip('/')}, got {base_url}"

    castles_url = get_miniapp_url("castles")
    assert "startapp=castles" in castles_url
    duel_url = get_miniapp_url("duel")
    assert "startapp=duel" in duel_url
    quiz_url = get_miniapp_url("quiz")
    assert "startapp=quiz" in quiz_url
    bank_url = get_miniapp_url("bank")
    assert "startapp=bank" in bank_url
    guild_url = get_miniapp_url("guild")
    assert "startapp=guild" in guild_url
    print(f"[OK] Test 1: URL Generator -> Verified ({castles_url})")

    # -------------------------------------------------------------
    # TEST 2: Attack Alert Notification Keyboard
    # -------------------------------------------------------------
    atk_kb = attack_alert_keyboard(territory_id=5)
    # Check top row is WebApp button
    top_btn = atk_kb.inline_keyboard[0][0]
    assert top_btn.web_app is not None, "Top button must be a WebApp button"
    assert "startapp=castles" in top_btn.web_app.url
    # Check fallback buttons
    all_callbacks = [b.callback_data for row in atk_kb.inline_keyboard for b in row if b.callback_data]
    assert any("def_rf_menu:5" in c for c in all_callbacks)
    assert any("def_sos:5" in c for c in all_callbacks)
    print("[OK] Test 2: Attack Alert Keyboard -> WebApp Deep-Link + Fallback Buttons Verified")

    # -------------------------------------------------------------
    # TEST 3: Duel Challenge Notification Keyboard
    # -------------------------------------------------------------
    duel_kb = duel_challenge_keyboard(duel_id=42)
    top_btn = duel_kb.inline_keyboard[0][0]
    assert top_btn.web_app is not None
    assert "startapp=duel" in top_btn.web_app.url
    all_callbacks = [b.callback_data for row in duel_kb.inline_keyboard for b in row if b.callback_data]
    assert any("pvp_acc:42" in c for c in all_callbacks)
    assert any("pvp_rej:42" in c for c in all_callbacks)
    print("[OK] Test 3: Duel Challenge Keyboard -> WebApp Deep-Link + Fallback Buttons Verified")

    # -------------------------------------------------------------
    # TEST 4: Daily Reward Ready Notification Keyboard
    # -------------------------------------------------------------
    daily_kb = daily_reward_ready_keyboard()
    top_btn = daily_kb.inline_keyboard[0][0]
    assert top_btn.web_app is not None
    assert "startapp=profile" in top_btn.web_app.url
    all_callbacks = [b.callback_data for row in daily_kb.inline_keyboard for b in row if b.callback_data]
    assert "claim_daily_bonus" in all_callbacks
    print("[OK] Test 4: Daily Reward Keyboard -> WebApp Deep-Link + Fallback Buttons Verified")

    # -------------------------------------------------------------
    # TEST 5: Quiz Reminder Notification Keyboard
    # -------------------------------------------------------------
    quiz_kb = quiz_reminder_keyboard()
    top_btn = quiz_kb.inline_keyboard[0][0]
    assert top_btn.web_app is not None
    assert "startapp=quiz" in top_btn.web_app.url
    all_callbacks = [b.callback_data for row in quiz_kb.inline_keyboard for b in row if b.callback_data]
    assert "menu_citadel" in all_callbacks
    print("[OK] Test 5: Quiz Reminder Keyboard -> WebApp Deep-Link + Fallback Buttons Verified")

    # -------------------------------------------------------------
    # TEST 6: Bank Interest Ready Notification Keyboard
    # -------------------------------------------------------------
    bank_kb = bank_interest_ready_keyboard()
    top_btn = bank_kb.inline_keyboard[0][0]
    assert top_btn.web_app is not None
    assert "startapp=bank" in top_btn.web_app.url
    all_callbacks = [b.callback_data for row in bank_kb.inline_keyboard for b in row if b.callback_data]
    assert "menu_bank" in all_callbacks
    print("[OK] Test 6: Bank Interest Keyboard -> WebApp Deep-Link + Fallback Buttons Verified")

    # -------------------------------------------------------------
    # TEST 7: Guild Event Notification Keyboard
    # -------------------------------------------------------------
    guild_kb = guild_event_keyboard()
    top_btn = guild_kb.inline_keyboard[0][0]
    assert top_btn.web_app is not None
    assert "startapp=guild" in top_btn.web_app.url
    all_callbacks = [b.callback_data for row in guild_kb.inline_keyboard for b in row if b.callback_data]
    assert "menu_guild" in all_callbacks
    print("[OK] Test 7: Guild Event Keyboard -> WebApp Deep-Link + Fallback Buttons Verified")

    # -------------------------------------------------------------
    # TEST 8: Bot Main Menu Fallback Integrity Check
    # -------------------------------------------------------------
    from keyboards.menus import bot_fallback_keyboard, legacy_main_menu_keyboard
    main_kb = main_menu_keyboard(user_id=7689627859)
    # Check top row has WebApp button
    top_btn = main_kb.inline_keyboard[0][0]
    assert top_btn.web_app is not None
    assert top_btn.web_app.url.startswith(MINI_APP_URL.rstrip("/"))
    # Check fallback keyboard contains all critical legacy menus
    fb_kb = bot_fallback_keyboard(user_id=7689627859)
    all_callbacks = [b.callback_data for row in fb_kb.inline_keyboard for b in row if b.callback_data]
    required_fallbacks = [
        "menu_profile", "menu_house", "menu_army", "menu_castles",
        "menu_battle", "menu_quests", "menu_duel", "menu_citadel",
        "menu_council", "menu_bank", "menu_guild", "menu_rank"
    ]
    for rf in required_fallbacks:
        assert rf in all_callbacks, f"Fallback menu {rf} missing from bot_fallback_keyboard!"
    print(f"[OK] Test 8: Main Menu Fallback Integrity -> Verified ({len(all_callbacks)} Legacy Menus Intact)")

    # -------------------------------------------------------------
    # TEST 9: Mini App Deep-Link Client Router Script
    # -------------------------------------------------------------
    js_path = os.path.join(os.path.dirname(__file__), "..", "static", "js", "app.js")
    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()
    assert "handleDeepLinkRouting" in js_content
    assert "startapp" in js_content
    assert "openCitadelQuizModal" in js_content
    assert "openDuelModal" in js_content
    assert "openBankModal" in js_content
    assert "openGuildModal" in js_content
    print("[OK] Test 9: Mini App Client Deep-Link Router -> Verified in static/js/app.js")

    print("\n>>> ALL STAGE 6 NOTIFICATION & BOT ROLE TESTS PASSED 100%! <<<")

if __name__ == "__main__":
    run_tests()
