"""
STEPS 1-5 COMPREHENSIVE AUDIT & VERIFICATION SUITE
Runs strictly against an isolated in-memory SQLite database (never touches live DB).
Tests:
1. Central config (6 dragons, buildings, donate tiers, anti-P2W)
2. Buildings Hub & Upgrade service (Temir koni, Don tegirmoni, Qal'a istehkomi)
3. 6-Dragon Species system (requirements, prices, hatch ritual, feed, train, max 2 limit)
4. Scorpion Anti-Dragon Counter-Tactic in Battle Engine (up to 60% damage reduction)
5. Manual Donation Approval Flow (pending lock, idempotency, first-donate +20% bonus, stats, history)
"""
import os
import sys
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from database import models, crud
from core.battle_engine import calculate_battle
import services


async def run_steps_1_to_5_tests():
    print("=" * 70)
    print("RUNNING STEPS 1-5 AUDIT & VERIFICATION TESTS (IN-MEMORY DB)")
    print("=" * 70)

    # 1. Verify Central Config
    assert len(config.DRAGON_SPECIES_CONFIG) == 6, "Must have 6 dragon species in config.py"
    for g, d_cfg in config.DRAGON_SPECIES_CONFIG.items():
        assert d_cfg["price_gold"] >= 15000
        assert d_cfg["attack"] > 0 and d_cfg["defense"] > 0 and d_cfg["hp"] > 0

    for t_id, t_cfg in config.DONATE_TIERS.items():
        bonus = t_cfg.get("bonus", {})
        assert "dragon" not in bonus, f"Donate tier {t_id} must NOT grant a direct dragon!"
        assert not t_cfg.get("is_troops"), f"Donate tier {t_id} must NOT grant direct troops!"
    print("[PASS 1/5] Central config verified (6 dragons, no P2W dragons/troops in DONATE_TIERS)")

    # Setup isolated in-memory DB
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with SessionLocal() as session:
        # Create test user & house & territory
        house = models.House(code="targaryen", name="Targaryen", region="Dragonstone", emoji="🐉")
        session.add(house)
        await session.flush()

        user = models.User(
            telegram_id=9900112233,
            username="daenerys_test",
            full_name="Daenerys Targaryen",
            house_id=house.id,
            level=1,
            gold=5000,
            iron=3000,
            food=4000,
            iron_mine_level=1,
            grain_mill_level=1,
        )
        session.add(user)
        await session.flush()

        terr = models.Territory(
            code="dragonstone_test",
            name="Dragonstone",
            castle_name="Dragonstone",
            region="Crownlands",
            owner_house_id=house.id,
            conquered_by_user_id=user.id,
            castle_level=1,
            defense=500,
            is_capital=True,
        )
        session.add(terr)
        await session.commit()

        # 2. Test Buildings Hub & Upgrades
        b_hub = await services.get_buildings_hub_data(session, user.id)
        assert b_hub is not None
        assert b_hub["summary"]["iron_mine_level"] == 1
        ok_m, msg_m, _ = await services.upgrade_building_service(session, user.id, "iron_mine")
        assert ok_m is True, f"Iron mine upgrade failed: {msg_m}"
        ok_g, msg_g, _ = await services.upgrade_building_service(session, user.id, "grain_mill")
        assert ok_g is True, f"Grain mill upgrade failed: {msg_g}"
        ok_c, msg_c, _ = await services.upgrade_building_service(session, user.id, "castle_keep", terr.id)
        assert ok_c is True, f"Castle keep upgrade failed: {msg_c}"
        print("[PASS 2/5] Buildings Hub & Upgrade (Temir Koni, Don Tegirmoni, Qal'a Istehkomi) verified")

        # 3. Test 6-Dragon System (Requirements, Prices, Hatch, Feed, Train)
        # Try claiming Balerion (SSS) at level 1 -> must fail requirements!
        ok_bal, msg_bal, _ = await services.claim_starter_dragon_egg_service(session, user.id, "Balerion", grade="SSS")
        assert ok_bal is False, "Balerion should require high level & buildings!"

        # Grant level & resources for Arrax (C) and Syrax (B)
        user.level = 5
        user.iron_mine_level = 3
        user.grain_mill_level = 3
        user.gold = 200000
        user.iron = 150000
        user.food = 150000
        await session.commit()

        ok_d1, msg_d1, d1_info = await services.claim_starter_dragon_egg_service(session, user.id, "Arrax", grade="C")
        assert ok_d1 is True, f"Claim Arrax failed: {msg_d1}"

        ok_hatch, msg_hatch = await services.hatch_dragon_service(session, user.id, d1_info["id"])
        assert ok_hatch is True, f"Hatch Arrax failed: {msg_hatch}"

        ok_train, msg_train = await services.train_dragon_service(session, user.id, d1_info["id"])
        assert ok_train is True, f"Train Arrax failed: {msg_train}"

        ok_feed, msg_feed = await services.feed_dragon_service(session, user.id, d1_info["id"])
        assert ok_feed is True, f"Feed Arrax failed: {msg_feed}"

        # Claim 2nd dragon (Syrax - B): first fails at Castle level 2, then succeeds at Castle level 3
        ok_d2_pre, msg_d2_pre, _ = await services.claim_starter_dragon_egg_service(session, user.id, "Syrax", grade="B")
        assert ok_d2_pre is False, "Syrax should require Castle level 3!"

        ok_c3, msg_c3, _ = await services.upgrade_building_service(session, user.id, "castle_keep", territory_id=terr.id)
        assert ok_c3 is True, f"Castle upgrade to lvl 3 failed: {msg_c3}"

        ok_d2, msg_d2, d2_info = await services.claim_starter_dragon_egg_service(session, user.id, "Syrax", grade="B")
        assert ok_d2 is True, f"Claim 2nd dragon Syrax failed: {msg_d2}"

        # Try claiming 3rd dragon -> must fail (max 2 limit)!
        ok_d3, msg_d3, _ = await services.claim_starter_dragon_egg_service(session, user.id, "Meleys", grade="A")
        assert ok_d3 is False, "Should not allow more than 2 dragons per player!"
        print("[PASS 3/5] 6-Dragon system (requirements, prices, hatch, feed, train, max 2 limit) verified")

        # 4. Test Battle Engine Scorpion Counter-Tactic
        att_troops = {"infantry": 200, "archers": 200, "cavalry": 100, "spearmen": 100}
        def_troops = {"infantry": 300, "archers": 800, "cavalry": 100, "spearmen": 800}
        # Castle defense 2000 (lvl 5 = 40% DR) + 1600 anti-air troops (24% DR) -> Scorpion DR caps at 60%
        res_battle = calculate_battle(
            attacker_army=att_troops,
            defender_garrison=def_troops,
            dragon_power=10000,
            dragon_tactic="dracarys",
            castle_defense=2000,
        )
        assert res_battle["scorpion_dr_pct"] == 60, f"Expected 60% Scorpion DR, got {res_battle['scorpion_dr_pct']}"
        assert res_battle["effective_dragon_power"] == 4000, f"Expected 4000 effective dragon power, got {res_battle['effective_dragon_power']}"
        print("[PASS 4/5] Scorpion Anti-Dragon Counter-Tactic (60% DR cap) verified")

        # 5. Test Manual Donation Approval, First-Donate Bonus, Idempotency & Stats
        gold_before = user.gold
        ok_req, msg_req, don_req = await services.submit_donation_request_service(
            session=session,
            user=user,
            package_id="lord",
            receipt_file_id="test_receipt_file_id_123",
        )
        assert ok_req is True and don_req is not None, f"Submit donation failed: {msg_req}"

        # Duplicate pending check
        ok_dup, _, _ = await services.submit_donation_request_service(
            session=session,
            user=user,
            package_id="knight",
            receipt_file_id="test_receipt_file_id_456",
        )
        assert ok_dup is False, "Duplicate pending request must be blocked!"

        # Approve by admin
        admin_tg_id = config.ADMIN_IDS[0] if config.ADMIN_IDS else config.OWNER_ID
        ok_app, msg_app, details = await services.approve_donation_request_service(
            session=session,
            request_id=don_req.id,
            admin_telegram_id=admin_tg_id,
        )
        assert ok_app is True, f"Approve failed: {msg_app}"
        # 'lord' base gold is 22,000; with +20% first donate bonus -> 26,400 gold
        assert details["first_donate_bonus_applied"] is True
        assert details["gold"] == int(22000 * 1.20)

        # Double approve check (idempotency)
        ok_app2, _, _ = await services.approve_donation_request_service(
            session=session,
            request_id=don_req.id,
            admin_telegram_id=admin_tg_id,
        )
        assert ok_app2 is False, "Double approval of the same request must be rejected!"

        stats_res = await services.get_admin_donation_stats_service(session)
        stats = stats_res.get("stats", stats_res)
        assert stats["daily_approved_count"] == 1
        assert stats["daily_approved_uzs"] == 25000

        hist = await services.get_user_donation_history_service(session, user)
        assert len(hist) == 1 and hist[0]["status"] == "approved"
        print("[PASS 5/5] Manual Donation Approval, First-Donate +20% Bonus, Idempotency & Stats verified")

    await engine.dispose()
    print("\nALL STEPS 1-5 VERIFICATION TESTS PASSED 100%!")


if __name__ == "__main__":
    asyncio.run(run_steps_1_to_5_tests())
