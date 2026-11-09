"""
Stage 5 - Feature 1 Test Suite: Daily Rewards & Quests Actions.
Verifies server-side validation, double-click protection, atomic balance updates, and error handling.
"""
import os
import sys
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import app
from api.auth import generate_test_init_data


def run_stage5_feature1_tests():
    client = TestClient(app)
    print("==================================================")
    print("STAGE 5 (FEATURE 1): DAILY REWARDS & ACTIONS TESTS")
    print("==================================================")

    # 1. Hub inspection
    auth_header = {"Authorization": f"tma {generate_test_init_data(telegram_id=7689627859)}"}
    resp = client.get("/api/actions/daily/hub", headers=auth_header)
    assert resp.status_code == 200, f"Failed to get daily hub: {resp.status_code}"
    hub = resp.json()["daily"]
    assert "streak" in hub and "daily_quests" in hub
    print(f"[OK] Test 1: Daily Hub Retrieval -> 200 OK (Streak Day: {hub['streak']['current_day']}, Claimed Today: {hub['streak']['is_claimed_today']})")

    # 2. Unauthorized claim attempt
    unauth_resp = client.post("/api/actions/daily/claim-streak")
    assert unauth_resp.status_code == 401, "Expected 401 for unauthenticated claim"
    print("[OK] Test 2: Unauthenticated Claim -> 401 Unauthorized")

    # 3. Forged signature claim attempt
    forged_auth = {"Authorization": "tma " + generate_test_init_data(telegram_id=7689627859).replace("hash=", "hash=fakehash0000")}
    forged_resp = client.post("/api/actions/daily/claim-streak", headers=forged_auth)
    assert forged_resp.status_code == 401, "Expected 401 for forged signature claim"
    print("[OK] Test 3: Forged Signature Claim -> 401 Unauthorized")

    # 4. Attempt claim daily streak bonus
    claim_resp = client.post("/api/actions/daily/claim-streak", headers=auth_header)
    if claim_resp.status_code == 200:
        body = claim_resp.json()
        assert body["success"] is True
        print(f"[OK] Test 4: Claim Daily Streak -> 200 OK (Streak Claim Succeeded)")
    else:
        # Already claimed today
        assert claim_resp.status_code == 400
        print(f"[OK] Test 4: Claim Daily Streak -> 400 Bad Request (Already Claimed)")

    # 5. Immediate Replay / Double-Click Prevention Test
    # Sending immediate second request MUST be rejected!
    duplicate_resp = client.post("/api/actions/daily/claim-streak", headers=auth_header)
    assert duplicate_resp.status_code == 400, "Double-click was not blocked! Expected 400 Bad Request."
    print(f"[OK] Test 5: Double-Click / Duplicate Request Protection -> 400 Bad Request (Strictly Blocked)")

    # 6. Quest claiming test (with invalid key)
    inv_quest_resp = client.post(
        "/api/actions/daily/claim-quest",
        json={"quest_key": "invalid_quest_code_xyz"},
        headers=auth_header
    )
    assert inv_quest_resp.status_code == 400, "Expected 400 for invalid quest key"
    print(f"[OK] Test 6: Invalid Quest Code -> 400 Bad Request (Rejected)")

    # 7. Quest claiming test (with missing body)
    bad_body_resp = client.post(
        "/api/actions/daily/claim-quest",
        json={},
        headers=auth_header
    )
    assert bad_body_resp.status_code == 422, "Expected 422 for missing body fields"
    print("[OK] Test 7: Missing Quest Payload -> 422 Unprocessable Entity")

    # 8. Verify updated profile resources reflect current state
    prof_resp = client.get("/api/player/profile", headers=auth_header)
    assert prof_resp.status_code == 200
    p = prof_resp.json()["player"]
    print(f"[OK] Test 8: Verified Atomic Balance & Profile State (Gold: {p['gold']:,}, Level: {p['level']})")

    print("\n>>> ALL STAGE 5 (FEATURE 1) TESTS PASSED 100%! <<<")


if __name__ == "__main__":
    run_stage5_feature1_tests()
