"""
Stage 3 API & Telegram initData Authentication Test Suite.
Verifies cryptographic validation, replay protection, rate limits, and identity spoofing defense.
"""
import os
import sys
import time
import json
import urllib.parse
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import BOT_TOKEN
from api.main import app
from api.auth import generate_test_init_data, validate_telegram_init_data


def run_stage3_auth_tests():
    client = TestClient(app)
    print("==================================================")
    print("STAGE 3: API & HMAC-SHA256 AUTHENTICATION TESTS")
    print("==================================================")

    # 1. Health check endpoint
    resp = client.get("/api/health")
    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    assert resp.json()["status"] == "ok"
    print("[OK] Test 1: Public Health Check (/api/health) -> 200 OK")

    # 2. Missing initData
    resp = client.get("/api/player/profile")
    assert resp.status_code == 401, f"Expected 401 for missing auth, got: {resp.status_code}"
    print("[OK] Test 2: Missing initData -> 401 Unauthorized")

    # 3. Forged initData (Tampered signature)
    valid_data = generate_test_init_data(telegram_id=7689627859)
    tampered_data = valid_data.replace("hash=", "hash=deadbeefcafe00112233445566778899")
    resp = client.get("/api/player/profile", headers={"Authorization": f"tma {tampered_data}"})
    assert resp.status_code == 401, f"Expected 401 for forged signature, got: {resp.status_code}"
    print("[OK] Test 3: Forged / Tampered HMAC Signature -> 401 Unauthorized")

    # 4. Tampered User Payload (Attacker tries changing user ID without bot token)
    parsed = dict(urllib.parse.parse_qsl(valid_data))
    user_obj = json.loads(parsed["user"])
    user_obj["id"] = 123456789  # Attacker changes ID
    parsed["user"] = json.dumps(user_obj, separators=(",", ":"))
    tampered_payload_data = urllib.parse.urlencode(parsed)
    resp = client.get("/api/player/profile", headers={"Authorization": f"tma {tampered_payload_data}"})
    assert resp.status_code == 401, f"Expected 401 for tampered payload, got: {resp.status_code}"
    print("[OK] Test 4: Tampered User ID in Payload -> 401 Unauthorized")

    # 5. Expired initData (Replay attack prevention)
    expired_time = int(time.time()) - 90000  # > 24 hours ago
    expired_data = generate_test_init_data(telegram_id=7689627859, auth_date=expired_time)
    resp = client.get("/api/player/profile", headers={"Authorization": f"tma {expired_data}"})
    assert resp.status_code == 401, f"Expected 401 for expired initData, got: {resp.status_code}"
    print("[OK] Test 5: Expired initData (> 24 hours old) -> 401 Unauthorized")

    # 6. Valid initData for existing player
    legit_data = generate_test_init_data(telegram_id=7689627859)
    resp = client.get("/api/player/profile", headers={"Authorization": f"tma {legit_data}"})
    assert resp.status_code == 200, f"Expected 200 for valid player, got: {resp.status_code} {resp.text}"
    body = resp.json()
    assert body["success"] is True
    assert body["authenticated_telegram_id"] == 7689627859
    assert "player" in body and body["player"]["user_id"] == 1
    print(f"[OK] Test 6: Valid initData for Player 7689627859 -> 200 OK (Profile: {body['player']['full_name']}, Gold: {body['player']['gold']})")

    # 7. Attacker injecting another player's ID in request body/params
    resp = client.get(
        "/api/player/profile?user_id=45&telegram_id=6716172850",
        headers={"Authorization": f"tma {legit_data}"}
    )
    assert resp.status_code == 200
    spoof_body = resp.json()
    # Must still return ONLY authenticated user (7689627859), ignoring query parameters!
    assert spoof_body["authenticated_telegram_id"] == 7689627859
    assert spoof_body["player"]["user_id"] == 1
    print("[OK] Test 7: Spoofing Attempt (injected user_id in params) -> Strictly Ignored (Only authenticated user returned)")

    # 8. Unregistered player attempting access
    unregistered_data = generate_test_init_data(telegram_id=9999999999)
    resp = client.get("/api/player/profile", headers={"Authorization": f"tma {unregistered_data}"})
    assert resp.status_code == 403, f"Expected 403 for unregistered user, got: {resp.status_code}"
    print("[OK] Test 8: Unregistered Telegram User -> 403 Forbidden")

    # 9. Rate limiting protection
    print("[*] Testing Rate Limiting (Rapid fire requests)...")
    rate_limited = False
    for _ in range(35):
        resp = client.get("/api/player/profile", headers={"Authorization": f"tma {legit_data}"})
        if resp.status_code == 429:
            rate_limited = True
            break
    assert rate_limited, "Rate limiter did not trigger 429 after 35 rapid requests!"
    print("[OK] Test 9: Rapid-Fire Rate Limiting -> 429 Too Many Requests (Triggered successfully)")

    print("\n>>> ALL STAGE 3 API & SECURITY TESTS PASSED 100%! <<<")


if __name__ == "__main__":
    run_stage3_auth_tests()
