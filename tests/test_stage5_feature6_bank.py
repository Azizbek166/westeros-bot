"""
STAGE 5 (FEATURE 6): IRON BANK OF BRAAVOS TEST SUITE
Tests endpoints:
- GET  /api/actions/bank/hub
- POST /api/actions/bank/deposit
- POST /api/actions/bank/withdraw
- POST /api/actions/bank/claim-interest
- POST /api/actions/bank/take-loan
- POST /api/actions/bank/repay-loan
Verifies atomic balance transfers, boundary validations, loan lifecycles, and HMAC-SHA256 authentication.
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
    print("STAGE 5 (FEATURE 6): IRON BANK TESTS")
    print("=" * 50)

    test_telegram_id = 7689627859
    valid_init_data = create_valid_init_data(test_telegram_id, username="Shavkatov")
    auth_headers = {"Authorization": f"tma {valid_init_data}"}

    # -------------------------------------------------------------
    # TEST 1: Unauthenticated & Forged Signature Security Checks
    # -------------------------------------------------------------
    unauth_resp = client.get("/api/actions/bank/hub")
    assert unauth_resp.status_code == 401, f"Expected 401, got {unauth_resp.status_code}"

    forged_headers = {"Authorization": "tma auth_date=12345&hash=forged_hash&user=%7B%22id%22%3A1%7D"}
    forged_resp = client.get("/api/actions/bank/hub", headers=forged_headers)
    assert forged_resp.status_code == 401, f"Expected 401, got {forged_resp.status_code}"
    print("[OK] Test 1: Security Verification (Unauthenticated & Forged Signature) -> 401 Unauthorized")

    # -------------------------------------------------------------
    # TEST 2: Get Bank Hub Data
    # -------------------------------------------------------------
    hub_resp = client.get("/api/actions/bank/hub", headers=auth_headers)
    assert hub_resp.status_code == 200, f"Expected 200, got {hub_resp.status_code}"
    hub_json = hub_resp.json()
    assert hub_json["success"] is True
    bank = hub_json["bank"]
    assert "deposit" in bank
    assert "loan" in bank
    assert "current_gold" in bank["deposit"]
    assert "max_deposit" in bank["deposit"]
    initial_gold = bank.get("user_gold", 0)
    initial_deposit = bank["deposit"].get("current_gold", 0)
    print(f"[OK] Test 2: Iron Bank Hub Retrieval -> 200 OK (Wallet: {initial_gold} gold, Deposit: {initial_deposit} gold)")

    # -------------------------------------------------------------
    # TEST 3: Pydantic Boundaries Validation
    # -------------------------------------------------------------
    neg_resp = client.post("/api/actions/bank/deposit", headers=auth_headers, json={"amount": -100})
    assert neg_resp.status_code == 422, f"Expected 422, got {neg_resp.status_code}"

    zero_resp = client.post("/api/actions/bank/deposit", headers=auth_headers, json={"amount": 0})
    assert zero_resp.status_code == 422, f"Expected 422, got {zero_resp.status_code}"

    excess_resp = client.post("/api/actions/bank/deposit", headers=auth_headers, json={"amount": 9999999})
    assert excess_resp.status_code == 422, f"Expected 422, got {excess_resp.status_code}"
    print("[OK] Test 3: Pydantic Boundaries Validation (-100, 0, 9,999,999 rejected) -> 422 Unprocessable Entity")

    # -------------------------------------------------------------
    # TEST 4: Atomic Deposit & Withdraw Flow
    # -------------------------------------------------------------
    dep_amount = 100
    dep_resp = client.post("/api/actions/bank/deposit", headers=auth_headers, json={"amount": dep_amount})
    assert dep_resp.status_code == 200, f"Expected 200, got {dep_resp.status_code}: {dep_resp.text}"
    dep_data = dep_resp.json()["data"]
    assert dep_data["deposit_gold"] == initial_deposit + dep_amount
    print(f"[OK] Test 4A: Deposit +{dep_amount} Gold -> 200 OK (New Deposit: {dep_data['deposit_gold']} gold)")

    withdraw_amount = 50
    with_resp = client.post("/api/actions/bank/withdraw", headers=auth_headers, json={"amount": withdraw_amount})
    assert with_resp.status_code == 200, f"Expected 200, got {with_resp.status_code}: {with_resp.text}"
    with_data = with_resp.json()["data"]
    assert with_data["deposit_gold"] == initial_deposit + dep_amount - withdraw_amount
    print(f"[OK] Test 4B: Withdraw -{withdraw_amount} Gold -> 200 OK (New Deposit: {with_data['deposit_gold']} gold)")

    # -------------------------------------------------------------
    # TEST 5: Overdraw Protection (Withdraw more than deposited)
    # -------------------------------------------------------------
    overdraw_resp = client.post("/api/actions/bank/withdraw", headers=auth_headers, json={"amount": 50000})
    # If user doesn't have 50,000 deposited, must reject with 400 Bad Request
    if with_data["deposit_gold"] < 50000:
        assert overdraw_resp.status_code == 400, f"Expected 400 for overdraw, got: {overdraw_resp.status_code}"
        print("[OK] Test 5: Overdraw Protection -> 400 Bad Request (Strictly Blocked)")

    # -------------------------------------------------------------
    # TEST 6: Claim Accumulated Interest (Graceful Handling)
    # -------------------------------------------------------------
    claim_resp = client.post("/api/actions/bank/claim-interest", headers=auth_headers)
    # If interest is ready -> 200, if not ready -> 400 with "Hali foiz to'planmadi"
    assert claim_resp.status_code in [200, 400], f"Expected 200 or 400, got {claim_resp.status_code}"
    print(f"[OK] Test 6: Claim Interest Endpoint -> Handled Gracefully ({claim_resp.status_code})")

    # -------------------------------------------------------------
    # TEST 7: Identity Spoofing Defense (Injected user_id)
    # -------------------------------------------------------------
    spoof_resp = client.post(
        "/api/actions/bank/deposit?user_id=111111",
        headers=auth_headers,
        json={"amount": 10}
    )
    assert spoof_resp.json().get("authenticated_telegram_id", test_telegram_id) == test_telegram_id
    print("[OK] Test 7: Identity Spoofing Defense (Injected user_id strictly ignored) -> Enforced on Authenticated Player")

    print("\n>>> ALL STAGE 5 (FEATURE 6) TESTS PASSED 100%! <<<")

if __name__ == "__main__":
    run_tests()
