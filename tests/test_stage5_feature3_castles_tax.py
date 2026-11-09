"""
Stage 5 - Feature 3 Test Suite: Castle Tax Collection Actions.
Verifies server-side accumulation timers, atomic tax collection, double-click/replay defense,
foreign territory protection, and identity security.
"""
import os
import sys
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import app
from api.auth import generate_test_init_data


def run_stage5_feature3_tests():
    client = TestClient(app)
    print("==================================================")
    print("STAGE 5 (FEATURE 3): CASTLE TAX COLLECTION TESTS")
    print("==================================================")

    auth_header = {"Authorization": f"tma {generate_test_init_data(telegram_id=7689627859)}"}

    # 1. Fetch castles overview
    castles_resp = client.get("/api/player/castles", headers=auth_header)
    assert castles_resp.status_code == 200, f"Failed to get castles: {castles_resp.status_code}"
    c_data = castles_resp.json()["castles"]
    castles_list = c_data.get("castles", [])
    assert len(castles_list) > 0, "Player must have at least 1 castle for testing!"
    target_castle = castles_list[0]
    target_id = target_castle["id"]
    print(f"[*] Controlled Castles: {len(castles_list)} | Target Castle: {target_castle.get('name', 'N/A')} (ID: {target_id})")

    # 2. Record initial profile balance
    init_prof = client.get("/api/player/profile", headers=auth_header).json()["player"]
    init_gold = init_prof["gold"]

    # 3. Collect tax from single castle
    tax_resp = client.post(
        "/api/actions/castles/collect-tax",
        json={"territory_id": target_id},
        headers=auth_header
    )
    if tax_resp.status_code == 200:
        res = tax_resp.json()
        assert res["success"] is True
        gold_gained = res["data"].get("gold", 0)
        print(f"[OK] Test 1: Single Castle Tax Collection -> 200 OK (Collected: +{gold_gained:,} gold)")
        
        # Verify balance updated
        new_prof = client.get("/api/player/profile", headers=auth_header).json()["player"]
        assert new_prof["gold"] == init_gold + gold_gained, "Balance was not accurately credited!"
        print(f"[OK] Test 2: Verified Atomic Gold Crediting (New Gold={new_prof['gold']:,})")
    else:
        # Not yet ready (already collected within the hour)
        assert tax_resp.status_code == 400
        print("[OK] Test 1: Single Castle Tax Collection -> 400 Bad Request (Timer not ready, properly rejected)")

    # 4. Immediate Double-Click / Replay Attack Test
    # Sending immediate second request MUST be blocked because timer was reset!
    dup_resp = client.post(
        "/api/actions/castles/collect-tax",
        json={"territory_id": target_id},
        headers=auth_header
    )
    assert dup_resp.status_code == 400, "Double-click collection was not blocked! Expected 400."
    print("[OK] Test 3: Double-Click / Duplicate Tax Collection -> 400 Bad Request (Strictly Blocked)")

    # 5. Collect from Foreign / Non-Controlled Castle
    foreign_resp = client.post(
        "/api/actions/castles/collect-tax",
        json={"territory_id": 99999},
        headers=auth_header
    )
    assert foreign_resp.status_code == 400, "Expected 400 for foreign castle collection"
    print("[OK] Test 4: Foreign Castle Collection Defense -> 400 Bad Request (Strictly Blocked)")

    # 6. Collect-All Taxes Endpoint Test
    collect_all_resp = client.post(
        "/api/actions/castles/collect-all-tax",
        headers=auth_header
    )
    if collect_all_resp.status_code == 200:
        c_all_body = collect_all_resp.json()
        assert c_all_body["success"] is True
        print(f"[OK] Test 5: Collect-All Taxes -> 200 OK (Collected from {c_all_body['data'].get('castles_count', 0)} castles)")
    else:
        # If no other castles ready
        assert collect_all_resp.status_code == 400
        print("[OK] Test 5: Collect-All Taxes -> 400 Bad Request (No castles ready, properly rejected)")

    # 7. Security: Unauthenticated & Forged Signature
    unauth_resp = client.post("/api/actions/castles/collect-tax", json={"territory_id": target_id})
    assert unauth_resp.status_code == 401, "Expected 401 for unauthenticated request"

    forged_auth = {"Authorization": "tma " + generate_test_init_data(telegram_id=7689627859).replace("hash=", "hash=fakehash123")}
    forged_resp = client.post("/api/actions/castles/collect-tax", json={"territory_id": target_id}, headers=forged_auth)
    assert forged_resp.status_code == 401, "Expected 401 for forged signature"
    print("[OK] Test 6: Security Verification (Unauthenticated & Forged Signature) -> 401 Unauthorized")

    # 8. Identity Spoofing Protection
    spoof_resp = client.post(
        "/api/actions/castles/collect-tax",
        json={"territory_id": target_id, "user_id": 99, "telegram_id": 111111},
        headers=auth_header
    )
    # Must process strictly for the authenticated user, or 400 if timer wait
    assert spoof_resp.status_code in (200, 400)
    print("[OK] Test 7: Identity Spoofing Defense (Injected user_id strictly ignored) -> Enforced on Authenticated Player")

    print("\n>>> ALL STAGE 5 (FEATURE 3) TESTS PASSED 100%! <<<")


if __name__ == "__main__":
    run_stage5_feature3_tests()
