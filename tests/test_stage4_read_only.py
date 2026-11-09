"""
Stage 4 Read-Only Screens & Static Frontend Test Suite.
Verifies static files delivery, all read-only API endpoints, and data structure consistency.
"""
import os
import sys
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import app
from api.auth import generate_test_init_data


def run_stage4_tests():
    client = TestClient(app)
    print("==================================================")
    print("STAGE 4: READ-ONLY SCREENS & FRONTEND TESTS")
    print("==================================================")

    # 1. Static SPA HTML
    resp = client.get("/")
    assert resp.status_code == 200, f"Failed to serve index.html: {resp.status_code}"
    assert "The Iron Throne RPG" in resp.text
    assert "telegram-web-app.js" in resp.text
    assert "bottom-nav" in resp.text
    print("[OK] Test 1: Frontend SPA HTML (GET /) -> 200 OK")

    # 2. Static CSS
    resp = client.get("/css/app.css")
    assert resp.status_code == 200, f"Failed to serve app.css: {resp.status_code}"
    assert "--gold-primary" in resp.text
    print("[OK] Test 2: Westeros Theme Stylesheet (GET /css/app.css) -> 200 OK")

    # 3. Static JS
    resp = client.get("/js/app.js")
    assert resp.status_code == 200, f"Failed to serve app.js: {resp.status_code}"
    assert "fetchDashboard" in resp.text
    print("[OK] Test 3: Client Application Script (GET /js/app.js) -> 200 OK")

    # 4. Generate valid auth for testing player endpoints
    auth_header = {"Authorization": f"tma {generate_test_init_data(telegram_id=7689627859)}"}

    # 5. Army endpoint
    resp = client.get("/api/player/army", headers=auth_header)
    assert resp.status_code == 200, f"Army endpoint failed: {resp.status_code}"
    body = resp.json()
    assert body["success"] is True
    assert "troops" in body["army"]
    assert "siege_weapons" in body["army"]
    print(f"[OK] Test 4: Military & Troops Endpoint (/api/player/army) -> 200 OK (Total Troops: {body['army']['troops']['total']})")

    # 6. Castles endpoint
    resp = client.get("/api/player/castles", headers=auth_header)
    assert resp.status_code == 200, f"Castles endpoint failed: {resp.status_code}"
    body = resp.json()
    assert body["success"] is True
    assert "castles" in body["castles"]
    print(f"[OK] Test 5: Castles & Territories Endpoint (/api/player/castles) -> 200 OK (Castles Count: {body['castles']['total_castles']})")

    # 7. Rankings endpoint
    resp = client.get("/api/player/rankings", headers=auth_header)
    assert resp.status_code == 200, f"Rankings endpoint failed: {resp.status_code}"
    body = resp.json()
    assert body["success"] is True
    assert "wealth" in body["rankings"]
    assert "prestige" in body["rankings"]
    assert "army" in body["rankings"]
    assert "castles" in body["rankings"]
    print(f"[OK] Test 6: Leaderboard & Rankings Endpoint (/api/player/rankings) -> 200 OK (Top Wealthy: {len(body['rankings']['wealth'])} lords)")

    # 8. World Events endpoint
    resp = client.get("/api/player/events", headers=auth_header)
    assert resp.status_code == 200, f"Events endpoint failed: {resp.status_code}"
    body = resp.json()
    assert body["success"] is True
    assert "weather" in body["world"]
    assert "events" in body["world"]
    print(f"[OK] Test 7: World Events & Weather Endpoint (/api/player/events) -> 200 OK (Weather: {body['world']['weather'].get('name', 'N/A')})")

    # 9. Consolidated Dashboard (Single roundtrip for mobile networks)
    resp = client.get("/api/player/dashboard", headers=auth_header)
    assert resp.status_code == 200, f"Dashboard endpoint failed: {resp.status_code}"
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert "profile" in data and "army" in data and "castles" in data and "rankings" in data and "world" in data
    print("[OK] Test 8: Consolidated Mobile Dashboard (/api/player/dashboard) -> 200 OK (5-in-1 Payload Verified)")

    # 10. Security check: unauthenticated calls to all endpoints must be blocked
    for endpoint in ["/api/player/army", "/api/player/castles", "/api/player/rankings", "/api/player/events", "/api/player/dashboard"]:
        unauth_resp = client.get(endpoint)
        assert unauth_resp.status_code == 401, f"Expected 401 on {endpoint}, got: {unauth_resp.status_code}"
    print("[OK] Test 9: Security Verification: All 5 endpoints strictly reject unauthenticated requests -> 401 Unauthorized")

    print("\n>>> ALL STAGE 4 FRONTEND & READ-ONLY TESTS PASSED 100%! <<<")


if __name__ == "__main__":
    run_stage4_tests()
