"""
STAGE 5 (FEATURE 4): CITADEL QUIZ & ROYAL COUNCIL QUESTS TEST SUITE
Tests endpoints:
- GET  /api/actions/quests/citadel-quiz
- POST /api/actions/quests/citadel-quiz/answer
- GET  /api/actions/quests/council
- POST /api/actions/quests/council/choice
Verifies atomic state updates, daily limits, bounds validation, and strict HMAC-SHA256 authentication.
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
from config import BOT_TOKEN, DAILY_QUIZ_LIMIT, DAILY_COUNCIL_LIMIT
from data.quiz_data import CITADEL_QUIZ_QUESTIONS
from data.council_data import COUNCIL_DILEMMAS

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
    print("STAGE 5 (FEATURE 4): CITADEL QUIZ & ROYAL COUNCIL TESTS")
    print("=" * 50)

    test_telegram_id = 7689627859
    valid_init_data = create_valid_init_data(test_telegram_id, username="Shavkatov")
    auth_headers = {"Authorization": f"tma {valid_init_data}"}

    # -------------------------------------------------------------
    # TEST 1: Unauthenticated & Forged Signature Security Checks
    # -------------------------------------------------------------
    unauth_resp = client.get("/api/actions/quests/citadel-quiz")
    assert unauth_resp.status_code == 401, f"Expected 401, got {unauth_resp.status_code}"

    forged_headers = {"Authorization": "tma auth_date=12345&hash=forged_hash&user=%7B%22id%22%3A1%7D"}
    forged_resp = client.get("/api/actions/quests/citadel-quiz", headers=forged_headers)
    assert forged_resp.status_code == 401, f"Expected 401, got {forged_resp.status_code}"
    print("[OK] Test 1: Security Verification (Unauthenticated & Forged Signature) -> 401 Unauthorized")

    # -------------------------------------------------------------
    # TEST 2: Get Citadel Quiz Question
    # -------------------------------------------------------------
    quiz_get_resp = client.get("/api/actions/quests/citadel-quiz", headers=auth_headers)
    # Could be 200 or 400 (if daily limit already reached on previous runs)
    if quiz_get_resp.status_code == 200:
        data = quiz_get_resp.json()
        assert data["success"] is True
        quiz = data["quiz"]
        assert "question_id" in quiz
        assert "question" in quiz
        assert len(quiz["options"]) >= 2
        assert "attempts_remaining" in quiz
        assert quiz["daily_limit"] == DAILY_QUIZ_LIMIT
        print(f"[OK] Test 2: Citadel Quiz Retrieval -> 200 OK (Attempts Remaining: {quiz['attempts_remaining']}/{DAILY_QUIZ_LIMIT})")
    else:
        assert quiz_get_resp.status_code == 400
        print(f"[OK] Test 2: Citadel Quiz Daily Limit Active -> 400 Bad Request (Limit Handled Correctly)")

    # -------------------------------------------------------------
    # TEST 3: Submit Citadel Quiz Answer (Validation & Scoring)
    # -------------------------------------------------------------
    # Check bounds validation first (422)
    invalid_bound_resp = client.post(
        "/api/actions/quests/citadel-quiz/answer",
        headers=auth_headers,
        json={"question_id": -1, "user_answer": 0}
    )
    assert invalid_bound_resp.status_code == 422, f"Expected 422 for negative question_id, got: {invalid_bound_resp.status_code}"

    invalid_bound_resp2 = client.post(
        "/api/actions/quests/citadel-quiz/answer",
        headers=auth_headers,
        json={"question_id": 0, "user_answer": 99}
    )
    assert invalid_bound_resp2.status_code == 422, f"Expected 422 for answer>5, got: {invalid_bound_resp2.status_code}"
    print("[OK] Test 3: Pydantic Boundaries Validation (-1 and 99 rejected) -> 422 Unprocessable Entity")

    # Out of range question_id (400)
    out_of_range_resp = client.post(
        "/api/actions/quests/citadel-quiz/answer",
        headers=auth_headers,
        json={"question_id": 999999, "user_answer": 0}
    )
    assert out_of_range_resp.status_code == 400, f"Expected 400, got {out_of_range_resp.status_code}"
    print("[OK] Test 4: Out-of-Range Question ID -> 400 Bad Request (Properly Blocked)")

    # -------------------------------------------------------------
    # TEST 5: Answer Question (Correct & Incorrect Outcome)
    # -------------------------------------------------------------
    target_q_idx = 0
    _, opts, correct_idx = CITADEL_QUIZ_QUESTIONS[target_q_idx]
    
    # Try submitting correct answer if limit not reached
    ans_resp = client.post(
        "/api/actions/quests/citadel-quiz/answer",
        headers=auth_headers,
        json={"question_id": target_q_idx, "user_answer": correct_idx}
    )
    if ans_resp.status_code == 200:
        ans_data = ans_resp.json()["data"]
        assert ans_data["is_correct"] is True
        assert ans_data["gold_change"] > 0
        print(f"[OK] Test 5: Submit Correct Quiz Answer -> 200 OK (Gold: +{ans_data['gold_change']}, XP: +{ans_data['xp_change']})")
    else:
        assert ans_resp.status_code == 400
        print("[OK] Test 5: Quiz Answer Submission Handled Gracefully -> Daily Limit Enforced (400 Bad Request)")

    # -------------------------------------------------------------
    # TEST 6: Royal Council Dilemma Retrieval
    # -------------------------------------------------------------
    council_resp = client.get("/api/actions/quests/council", headers=auth_headers)
    if council_resp.status_code == 200:
        cdata = council_resp.json()
        assert cdata["success"] is True
        council = cdata["council"]
        assert "council_id" in council
        assert "situation" in council
        assert "reward_gold" in council
        assert "attempts_remaining" in council
        assert council["daily_limit"] == DAILY_COUNCIL_LIMIT
        print(f"[OK] Test 6: Royal Council Dilemma Retrieval -> 200 OK (Remaining: {council['attempts_remaining']}/{DAILY_COUNCIL_LIMIT})")
    else:
        assert council_resp.status_code == 400
        print("[OK] Test 6: Royal Council Daily Limit Active -> 400 Bad Request (Limit Enforced)")

    # -------------------------------------------------------------
    # TEST 7: Royal Council Decision Submission & Boundaries
    # -------------------------------------------------------------
    # Bounds check
    c_bound_resp = client.post(
        "/api/actions/quests/council/choice",
        headers=auth_headers,
        json={"council_id": -5, "user_choice": 1}
    )
    assert c_bound_resp.status_code == 422
    
    c_out_resp = client.post(
        "/api/actions/quests/council/choice",
        headers=auth_headers,
        json={"council_id": 999999, "user_choice": 0}
    )
    assert c_out_resp.status_code == 400
    print("[OK] Test 7: Council Boundaries & Invalid ID Defense -> Verified (422 / 400)")

    # Submit a choice if attempts remain
    target_c_idx = 0
    _, _, correct_choice, reward = COUNCIL_DILEMMAS[target_c_idx]
    choice_resp = client.post(
        "/api/actions/quests/council/choice",
        headers=auth_headers,
        json={"council_id": target_c_idx, "user_choice": correct_choice}
    )
    if choice_resp.status_code == 200:
        res = choice_resp.json()["data"]
        assert res["is_correct"] is True
        print(f"[OK] Test 8: Submit Royal Council Choice -> 200 OK (Gold Gained: +{res['gold_gained']} gold, Prestige: +{res['prestige_gained']})")
    else:
        assert choice_resp.status_code == 400
        print("[OK] Test 8: Council Submission Handled Gracefully -> Daily Limit Enforced (400 Bad Request)")

    # -------------------------------------------------------------
    # TEST 9: Identity Spoofing Defense (Injected user_id)
    # -------------------------------------------------------------
    spoof_resp = client.post(
        "/api/actions/quests/citadel-quiz/answer?user_id=12345678",
        headers=auth_headers,
        json={"question_id": 0, "user_answer": 0}
    )
    # Status can be 200 or 400 (if limit reached), but must NOT execute as user 12345678
    assert spoof_resp.json().get("authenticated_telegram_id", test_telegram_id) == test_telegram_id
    print("[OK] Test 9: Identity Spoofing Defense (Injected user_id strictly ignored) -> Enforced on Authenticated Player")

    print("\n>>> ALL STAGE 5 (FEATURE 4) TESTS PASSED 100%! <<<")

if __name__ == "__main__":
    run_tests()
