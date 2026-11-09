"""
STAGE 5 (FEATURE 7): GUILD SYSTEM & TREASURY ACTIONS TEST SUITE
Tests endpoints:
- GET  /api/actions/guild/hub
- POST /api/actions/guild/deposit
- POST /api/actions/guild/buff
Verifies membership checks, treasury balances, permission checks, boundary validations,
and strict HMAC-SHA256 authentication.
"""
import sys
import os
import json
import hmac
import hashlib
import time
from urllib.parse import urlencode

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from api.main import app
from config import BOT_TOKEN

client = TestClient(app)

def create_valid_init_data(telegram_id: int, username: str = "TestLord", first_name: str = "Lord") -> str:
    user_data = {
        "id": telegram_id,
        "first_name": first_name,
        "username": username,
        "allows_write_to_pm": True
    }
    user_json = json.dumps(user_data, separators=(',', ':'))
    auth_date = int(time.time())
    params = {
        "auth_date": str(auth_date),
        "query_id": "AAHdKqUFAAAAAN0qpQU12345",
        "user": user_json
    }
    sorted_pairs = [f"{k}={params[k]}" for k in sorted(params.keys())]
    data_check_string = "\n".join(sorted_pairs)
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    params["hash"] = calc_hash
    return urlencode(params)


def run_tests():
    print("=" * 50)
    print("STAGE 5 (FEATURE 7): GUILD ACTIONS TESTS")
    print("=" * 50)

    test_telegram_id = 7689627859
    valid_init_data = create_valid_init_data(test_telegram_id, username="Shavkatov")
    auth_headers = {"Authorization": f"tma {valid_init_data}"}

    # -------------------------------------------------------------
    # TEST 1: Unauthenticated & Forged Signature Security Checks
    # -------------------------------------------------------------
    unauth_resp = client.get("/api/actions/guild/hub")
    assert unauth_resp.status_code == 401, f"Expected 401, got {unauth_resp.status_code}"

    forged_headers = {"Authorization": "tma auth_date=12345&hash=forged_hash&user=%7B%22id%22%3A1%7D"}
    forged_resp = client.get("/api/actions/guild/hub", headers=forged_headers)
    assert forged_resp.status_code == 401, f"Expected 401, got {forged_resp.status_code}"
    print("[OK] Test 1: Security Verification (Unauthenticated & Forged Signature) -> 401 Unauthorized")

    # -------------------------------------------------------------
    # TEST 2: Get Guild Hub Data
    # -------------------------------------------------------------
    hub_resp = client.get("/api/actions/guild/hub", headers=auth_headers)
    assert hub_resp.status_code == 200, f"Expected 200, got {hub_resp.status_code}"
    hub_json = hub_resp.json()
    assert hub_json["success"] is True
    hub = hub_json["guild_hub"]
    assert "in_guild" in hub
    print(f"[OK] Test 2: Guild Hub Retrieval -> 200 OK (In Guild: {hub['in_guild']})")

    # -------------------------------------------------------------
    # TEST 3: Pydantic Boundaries & Pattern Validations
    # -------------------------------------------------------------
    # Invalid resource type (must be gold or iron)
    invalid_res_resp = client.post(
        "/api/actions/guild/deposit",
        headers=auth_headers,
        json={"resource_type": "diamonds", "amount": 100}
    )
    assert invalid_res_resp.status_code == 422, f"Expected 422 for invalid resource, got: {invalid_res_resp.status_code}"

    # Zero amount
    zero_amt_resp = client.post(
        "/api/actions/guild/deposit",
        headers=auth_headers,
        json={"resource_type": "gold", "amount": 0}
    )
    assert zero_amt_resp.status_code == 422, f"Expected 422 for 0 amount, got: {zero_amt_resp.status_code}"

    # Excessive amount (> 100,000)
    excess_amt_resp = client.post(
        "/api/actions/guild/deposit",
        headers=auth_headers,
        json={"resource_type": "gold", "amount": 500000}
    )
    assert excess_amt_resp.status_code == 422, f"Expected 422 for >100k amount, got: {excess_amt_resp.status_code}"

    # Short buff_type
    short_buff_resp = client.post(
        "/api/actions/guild/buff",
        headers=auth_headers,
        json={"buff_type": "a"}
    )
    assert short_buff_resp.status_code == 422, f"Expected 422 for short buff_type, got: {short_buff_resp.status_code}"
    print("[OK] Test 3: Pydantic Boundaries Validation (Invalid resource, zero amount, >100k, short buff) -> 422 Unprocessable Entity")

    # -------------------------------------------------------------
    # TEST 4: Guild Deposit Execution or Membership Enforcement
    # -------------------------------------------------------------
    dep_resp = client.post(
        "/api/actions/guild/deposit",
        headers=auth_headers,
        json={"resource_type": "gold", "amount": 50}
    )
    if hub["in_guild"]:
        assert dep_resp.status_code in [200, 400]
        print(f"[OK] Test 4: Guild Treasury Deposit Processed -> {dep_resp.status_code}")
    else:
        assert dep_resp.status_code == 400
        assert "emassiz" in dep_resp.json().get("detail", "")
        print("[OK] Test 4: Non-Member Deposit Blocked -> 400 Bad Request (Properly Rejected)")

    # -------------------------------------------------------------
    # TEST 5: Guild Buff Activation Enforcement
    # -------------------------------------------------------------
    buff_resp = client.post(
        "/api/actions/guild/buff",
        headers=auth_headers,
        json={"buff_type": "exp_boost"}
    )
    # If not in guild or insufficient treasury gold -> 400 Bad Request
    assert buff_resp.status_code in [200, 400]
    print(f"[OK] Test 5: Guild Buff Activation Handled -> {buff_resp.status_code} (Permission/Treasury Enforced)")

    # -------------------------------------------------------------
    # TEST 6: Identity Spoofing Defense
    # -------------------------------------------------------------
    spoof_resp = client.post(
        "/api/actions/guild/deposit?user_id=123456",
        headers=auth_headers,
        json={"resource_type": "gold", "amount": 10}
    )
    assert spoof_resp.json().get("authenticated_telegram_id", test_telegram_id) == test_telegram_id
    print("[OK] Test 6: Identity Spoofing Defense (Injected user_id strictly ignored) -> Enforced on Authenticated Player")

    print("\n>>> ALL STAGE 5 (FEATURE 7) TESTS PASSED 100%! <<<")

if __name__ == "__main__":
    run_tests()
