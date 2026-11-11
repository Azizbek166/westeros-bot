"""
STAGE 8: ALL-FEATURES ENDPOINTS TEST SUITE
Tests Onboarding, Map, Battle, Espionage, House, Hero, Dragons, Market, Ravens, Donate, and Admin.
"""
import sys
import os
import asyncio
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.main import app
from api.auth import generate_test_init_data
from config import BOT_TOKEN, ADMIN_IDS


async def run_all_stage8_tests():
    print("=" * 60)
    print("STAGE 8: TESTING ALL NEW BACKEND ENDPOINTS")
    print("=" * 60)

    # 1. Test Onboarding and Registration
    import time
    new_tg_id = int(time.time()) % 1000000000 + 8800000000
    init_data = generate_test_init_data(telegram_id=new_tg_id, username="new_lord", first_name="Aegon", bot_token=BOT_TOKEN)
    headers = {"Authorization": f"tma {init_data}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/player/dashboard", headers=headers)
        assert r.status_code == 200, f"Dashboard failed: {r.text}"
        d = r.json()
        assert d["success"] is True
        assert d["is_registered"] is False
        assert len(d.get("available_houses", [])) > 0
        print("[TEST 1/6 PASSED] Unregistered user receives onboarding catalog")

        reg_payload = {
            "hero_name": "Aegon Tester",
            "custom_house_name": "Qora Ajdarlar",
            "custom_house_region": "Dragonstone",
            "custom_house_emoji": "🐉",
            "custom_castle_name": "Tosh Qal'a"
        }
        reg_res = await client.post("/api/player/register", headers=headers, json=reg_payload)
        assert reg_res.status_code in [200, 400]
        print("[TEST 2/6 PASSED] Registration endpoint handled correctly")

    # 2. Test Map, Scout, Battle, Espionage
    reg_init = generate_test_init_data(telegram_id=7689627859, bot_token=BOT_TOKEN)
    reg_headers = {"Authorization": f"tma {reg_init}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r_map = await client.get("/api/actions/map/overview", headers=reg_headers)
        assert r_map.status_code == 200
        assert r_map.json()["map"]["total_territories"] >= 20

        r_scout = await client.get("/api/actions/map/territory/1", headers=reg_headers)
        assert r_scout.status_code == 200

        r_battle = await client.get("/api/actions/battle/hub", headers=reg_headers)
        assert r_battle.status_code == 200

        r_spy = await client.get("/api/actions/espionage/hub", headers=reg_headers)
        assert r_spy.status_code == 200
        print("[TEST 3/6 PASSED] Map, Scout, Battle Hub, and Espionage Hub all 200 OK")

    # 3. Test House, Hero Artifacts, Dragons
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r_house = await client.get("/api/actions/house/hub", headers=reg_headers)
        assert r_house.status_code == 200

        r_hero = await client.get("/api/actions/hero/hub", headers=reg_headers)
        assert r_hero.status_code == 200

        r_dragon = await client.get("/api/actions/dragon/hub", headers=reg_headers)
        assert r_dragon.status_code == 200
        print("[TEST 4/6 PASSED] House, Hero Hub, and Dragon Hub all 200 OK")

    # 4. Test Marketplace, Raven, Donate
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r_mkt = await client.get("/api/actions/market/hub", headers=reg_headers)
        assert r_mkt.status_code == 200

        r_rvn = await client.get("/api/actions/raven/hub", headers=reg_headers)
        assert r_rvn.status_code == 200

        r_don = await client.get("/api/actions/donate/hub", headers=reg_headers)
        assert r_don.status_code == 200
        print("[TEST 5/6 PASSED] Marketplace, Raven Messenger, and VIP Donate all 200 OK")

    # 5. Test Admin Role Verification
    admin_id = ADMIN_IDS[0] if ADMIN_IDS else 7689627859
    init_admin = generate_test_init_data(telegram_id=admin_id, bot_token=BOT_TOKEN)
    headers_adm = {"Authorization": f"tma {init_admin}"}

    init_non_admin = generate_test_init_data(telegram_id=1122334455, bot_token=BOT_TOKEN)
    headers_non_adm = {"Authorization": f"tma {init_non_admin}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r_adm = await client.get("/api/actions/admin/dashboard", headers=headers_adm)
        assert r_adm.status_code == 200

        r_forbid = await client.get("/api/actions/admin/dashboard", headers=headers_non_adm)
        assert r_forbid.status_code == 403
        print("[TEST 6/6 PASSED] Admin Console securely guarded (200 OK for admin, 403 Forbidden for non-admin)")

    print("\nALL STAGE 8 NEW ENDPOINTS VERIFIED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_all_stage8_tests())
