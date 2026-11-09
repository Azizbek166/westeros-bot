"""
Stage 5 - Feature 2 Test Suite: Troop Recruitment Actions.
Verifies server-side validation, resource deduction, atomic database updates,
input boundaries, and identity protection.
"""
import os
import sys
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import app
from api.auth import generate_test_init_data


def run_stage5_feature2_tests():
    client = TestClient(app)
    print("==================================================")
    print("STAGE 5 (FEATURE 2): TROOP RECRUITMENT TESTS")
    print("==================================================")

    auth_header = {"Authorization": f"tma {generate_test_init_data(telegram_id=7689627859)}"}

    # 1. Check initial balances & troops
    init_prof_resp = client.get("/api/player/profile", headers=auth_header)
    assert init_prof_resp.status_code == 200
    init_player = init_prof_resp.json()["player"]
    init_gold = init_player["gold"]
    init_iron = init_player["iron"]

    init_army_resp = client.get("/api/player/army", headers=auth_header)
    assert init_army_resp.status_code == 200
    init_infantry = init_army_resp.json()["army"]["troops"]["infantry"]

    print(f"[*] Initial State: Gold={init_gold:,}, Iron={init_iron:,}, Infantry={init_infantry:,}")

    # 2. Valid Recruitment: Recruit 5 Infantry (Cost: 10 gold, 5 iron)
    recruit_resp = client.post(
        "/api/actions/military/recruit",
        json={"unit_type": "infantry", "amount": 5},
        headers=auth_header
    )
    assert recruit_resp.status_code == 200, f"Recruitment failed: {recruit_resp.status_code} {recruit_resp.text}"
    rec_body = recruit_resp.json()
    assert rec_body["success"] is True
    assert rec_body["data"]["amount"] == 5
    assert rec_body["data"]["gold_spent"] == 10
    assert rec_body["data"]["iron_spent"] == 5
    print("[OK] Test 1: Valid Troop Recruitment (5 Infantry) -> 200 OK (Cost: 10 gold, 5 iron)")

    # 3. Verify Database Balance & Troops Atomicity
    after_prof_resp = client.get("/api/player/profile", headers=auth_header)
    after_player = after_prof_resp.json()["player"]
    assert after_player["gold"] == init_gold - 10, "Gold was not accurately deducted!"
    assert after_player["iron"] == init_iron - 5, "Iron was not accurately deducted!"

    after_army_resp = client.get("/api/player/army", headers=auth_header)
    after_infantry = after_army_resp.json()["army"]["troops"]["infantry"]
    assert after_infantry == init_infantry + 5, "Infantry count was not incremented by 5!"
    print(f"[OK] Test 2: Verified Balance & Troop Count Atomicity (New Gold={after_player['gold']:,}, New Infantry={after_infantry:,})")

    # 4. Insufficient Resources Test (Attempting to recruit 50,000 cavalry costing 300,000 gold)
    poor_resp = client.post(
        "/api/actions/military/recruit",
        json={"unit_type": "cavalry", "amount": 50000},
        headers=auth_header
    )
    assert poor_resp.status_code == 400, f"Expected 400 for insufficient gold, got: {poor_resp.status_code}"
    print("[OK] Test 3: Insufficient Resources Check -> 400 Bad Request (Properly Rejected)")

    # 5. Invalid Unit Type
    fake_unit_resp = client.post(
        "/api/actions/military/recruit",
        json={"unit_type": "fake_dragon_gargoyle", "amount": 10},
        headers=auth_header
    )
    assert fake_unit_resp.status_code == 400, "Expected 400 for unknown unit type"
    print("[OK] Test 4: Unknown Unit Type -> 400 Bad Request (Strictly Rejected)")

    # 6. Invalid Amount Boundaries
    zero_amt_resp = client.post(
        "/api/actions/military/recruit",
        json={"unit_type": "infantry", "amount": 0},
        headers=auth_header
    )
    assert zero_amt_resp.status_code == 422, "Expected 422 for amount=0"

    neg_amt_resp = client.post(
        "/api/actions/military/recruit",
        json={"unit_type": "infantry", "amount": -15},
        headers=auth_header
    )
    assert neg_amt_resp.status_code == 422, "Expected 422 for negative amount"
    print("[OK] Test 5: Amount Boundary Validation (0 and -15 rejected) -> 422 Unprocessable Entity")

    # 7. Unauthenticated & Forged Signature
    unauth_resp = client.post("/api/actions/military/recruit", json={"unit_type": "infantry", "amount": 10})
    assert unauth_resp.status_code == 401, "Expected 401 for unauthenticated request"

    forged_auth = {"Authorization": "tma " + generate_test_init_data(telegram_id=7689627859).replace("hash=", "hash=invalidhash")}
    forged_resp = client.post(
        "/api/actions/military/recruit",
        json={"unit_type": "infantry", "amount": 10},
        headers=forged_auth
    )
    assert forged_resp.status_code == 401, "Expected 401 for forged signature"
    print("[OK] Test 6: Security Verification (Unauthenticated & Forged Signature) -> 401 Unauthorized")

    # 8. Identity Spoofing Protection (Passing another user_id in body)
    spoof_resp = client.post(
        "/api/actions/military/recruit",
        json={"unit_type": "infantry", "amount": 1, "user_id": 45, "target_id": 99},
        headers=auth_header
    )
    assert spoof_resp.status_code == 200
    assert spoof_resp.json()["authenticated_telegram_id"] == 7689627859
    assert spoof_resp.json()["data"]["user_id"] == 1
    print("[OK] Test 7: Identity Spoofing Defense (Injected user_id strictly ignored) -> 200 OK for Authenticated Player")

    print("\n>>> ALL STAGE 5 (FEATURE 2) TESTS PASSED 100%! <<<")


if __name__ == "__main__":
    run_stage5_feature2_tests()
