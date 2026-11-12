"""
Test Suite for Game Balance, Anti-Cheat, Newbie Protection, and Catch-Up Mechanics.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.balance import (
    ECONOMY,
    BATTLE,
    DRAGON,
    DAILY_LIMITS,
    PROTECTION,
    ANTI_CHEAT,
    UNITS_CONFIG,
    RPS_ADVANTAGES,
    get_all_balance_summary,
)
from core.anti_cheat import (
    can_attack_target,
    can_attack_player,
    get_catchup_multiplier,
    validate_market_trade_offer,
    detect_abnormal_growth,
    check_multi_account_footprint,
)
from core.battle_engine import calculate_battle
from core.dragon_battle import calculate_dragon_power
from core.economy_engine import calculate_army_upkeep
from database import models


def test_balance_configuration():
    print("\n--- Test 1: Centralized Game Balance Configuration ---")
    summary = get_all_balance_summary()
    assert "economy" in summary
    assert "units" in summary
    assert "battle" in summary
    assert "dragon" in summary
    assert "protection" in summary
    assert "anti_cheat" in summary

    assert ECONOMY.starting_gold == 500
    assert ECONOMY.starting_food == 1000
    assert ECONOMY.starting_iron == 300
    assert PROTECTION.newbie_peace_shield_hours == 72
    assert PROTECTION.max_level_gap_for_attack == 5

    assert UNITS_CONFIG["infantry"]["attack"] == 10
    assert UNITS_CONFIG["archers"]["defense"] == 8
    assert UNITS_CONFIG["cavalry"]["attack"] == 24
    print("[PASS] Centralized balance config exports valid parameters.")


def test_newbie_protection_and_level_gap():
    print("\n--- Test 2: Newbie Protection & Level Gap Defense ---")
    now = datetime.utcnow()

    # 1. Target with active Peace Shield
    attacker = models.User(id=1, level=10, house_id=1)
    defender = models.User(id=2, level=6, house_id=2, peace_shield_until=now + timedelta(hours=24))

    ok_pvp, msg_pvp = can_attack_player(attacker, defender)
    assert ok_pvp is False, "Attacked shielded player!"
    assert "Tinchlik Qalqoni" in msg_pvp

    # 2. Level Gap Protection: Level 15 attacker vs Level 3 defender (gap = 12 > 5)
    high_attacker = models.User(id=3, level=15, house_id=1)
    low_defender = models.User(id=4, level=3, house_id=2, peace_shield_until=None)

    ok_gap, msg_gap = can_attack_player(high_attacker, low_defender)
    assert ok_gap is False, "Allowed attack across excessive level gap!"
    assert "Darajalar tafovuti" in msg_gap or "Adolatli o'yin" in msg_gap

    # 3. Fair level matchup: Level 8 attacker vs Level 6 defender (gap = 2 <= 5)
    fair_attacker = models.User(id=5, level=8, house_id=1)
    ok_fair, _ = can_attack_player(fair_attacker, defender)
    # If defender has no shield
    defender.peace_shield_until = None
    ok_fair2, _ = can_attack_player(fair_attacker, defender)
    assert ok_fair2 is True, "Fair attack was blocked!"

    print("[PASS] Newbie peace shield and level gap defense verified.")


def test_catchup_mechanic():
    print("\n--- Test 3: Catch-Up Booster for Underleveled Lords ---")
    server_median = 10

    # New player (Level 2 vs Server Median 10, diff = 8 >= 3)
    mult_new, is_active_new = get_catchup_multiplier(user_level=2, server_average_level=server_median)
    assert is_active_new is True
    assert mult_new == 1.35, f"Expected 1.35x booster, got {mult_new}"

    # Veteran player (Level 12 vs Server Median 10, diff = -2 < 3)
    mult_vet, is_active_vet = get_catchup_multiplier(user_level=12, server_average_level=server_median)
    assert is_active_vet is False
    assert mult_vet == 1.0

    print("[PASS] Catch-up 1.35x multiplier correctly activates for underleveled lords.")


def test_anti_cheat_market_and_growth():
    print("\n--- Test 4: Market Dumping & Wealth Spike Detection ---")
    # Fair trade: 100 gold (value: 300) for 200 iron (value: 300) -> ratio 1.0
    ok_fair, _ = validate_market_trade_offer("gold", 100, "iron", 200)
    assert ok_fair is True

    # Dumping trade: 50,000 gold (value: 150,000) for 10 food (value: 5) -> ratio 30,000 >> 5.0
    ok_dump, msg_dump = validate_market_trade_offer("gold", 50000, "food", 10)
    assert ok_dump is False
    assert "Savdo nisbati nomutanosib" in msg_dump

    # Abnormal wealth spike: +200,000 gold in 1h
    spike1 = detect_abnormal_growth(user_telegram_id=888888, delta_amount=150_000, resource_type="gold")
    assert spike1 is True, "Failed to flag 150k gold spike!"

    # Multi-account footprint test
    ip = "198.51.100.42"
    ua = "Mozilla/5.0 Telegram-MiniApp Android"
    check_multi_account_footprint(101, ip, ua)
    check_multi_account_footprint(102, ip, ua)
    check_multi_account_footprint(103, ip, ua)
    is_susp, count = check_multi_account_footprint(104, ip, ua)
    assert is_susp is True, f"Failed to detect 4 accounts on same IP! count={count}"

    print("[PASS] Market dumping and multi-account footprint checks verified.")


def test_combat_and_dragon_formulas():
    print("\n--- Test 5: Combat & Dragon Formulas ---")
    dragon_data = {"power": 1000, "grade": "A", "stage": "adult", "level": 10}
    # Grade A: 1.20, Adult: 1.30, Level 10: 1.0 + 10*0.025 = 1.25 -> 1000 * 1.20 * 1.30 * 1.25 = 1950
    eff_power = calculate_dragon_power(dragon_data)
    assert eff_power == 1950, f"Expected 1950, got {eff_power}"

    # Army upkeep calculation
    army = models.Army(infantry=100, archers=50, cavalry=20, spearmen=30, special_troops=10)
    upkeep = calculate_army_upkeep(army)
    # 100*0.5 + 50*0.6 + 20*1.2 + 30*0.5 + 10*1.5 = 50 + 30 + 24 + 15 + 15 = 134.0
    assert abs(upkeep - 134.0) < 0.01, f"Expected 134.0 upkeep, got {upkeep}"

    # Battle simulation sanity check
    res = calculate_battle(
        attacker_army={"infantry": 100, "archers": 50, "cavalry": 25, "spearmen": 25, "special_troops": 0},
        defender_garrison={"infantry": 100, "archers": 50, "cavalry": 25, "spearmen": 25, "special_troops": 0},
        castle_defense=300,
    )
    assert res["winner"] in ("attacker", "defender")
    assert sum(res["attacker_losses"].values()) >= 0
    assert sum(res["defender_losses"].values()) >= 0

    print("[PASS] Dragon power, army upkeep, and battle formulas verified.")


def run_all_balance_tests():
    print("==================================================")
    print("RUNNING GAME BALANCE & FAIR PLAY TEST SUITE")
    print("==================================================")
    test_balance_configuration()
    test_newbie_protection_and_level_gap()
    test_catchup_mechanic()
    test_anti_cheat_market_and_growth()
    test_combat_and_dragon_formulas()
    print("\n==================================================")
    print("ALL BALANCE & FAIR PLAY TESTS PASSED (100%)!")
    print("==================================================")


if __name__ == "__main__":
    run_all_balance_tests()
