"""
The Iron Throne RPG - Balance & Economy Simulation Engine.
Performs 1,000 combat simulations across various military archetypes and
runs a 30-day macroeconomic progression simulation for Casual, Active, and Hardcore Lords.
"""
import os
import sys
import random
from typing import Dict, Any, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.balance import ECONOMY, BATTLE, UNITS_CONFIG, DRAGON, STREAK_REWARDS_CONFIG
from core.battle_engine import calculate_battle
from core.leveling import get_level_info


def run_combat_simulations(total_battles: int = 1000) -> Dict[str, Any]:
    print(f"\n" + "=" * 60)
    print(f"JANG BALANSI SIMULYATSIYASI ({total_battles} TA VIRTUAL JANG)")
    print("=" * 60)

    # 4 ta jangovar arxetip to'qnashuvi (har biri 250 ta jang)
    scenarios = [
        {
            "name": "1. Piyodalar Armiyasi vs Muvozanatli Armiya",
            "attacker": {"infantry": 350, "archers": 50, "cavalry": 0, "spearmen": 100, "special_troops": 0},
            "defender": {"infantry": 180, "archers": 140, "cavalry": 90, "spearmen": 90, "special_troops": 0},
            "castle_def": 400, "dragon": 0, "catapults": 2, "siege_towers": 1,
        },
        {
            "name": "2. Otliqlar Hamlasi vs Nayzadorlar Falanxi (RPS Anti-Cavalry)",
            "attacker": {"infantry": 80, "archers": 40, "cavalry": 280, "spearmen": 50, "special_troops": 0},
            "defender": {"infantry": 50, "archers": 100, "cavalry": 30, "spearmen": 270, "special_troops": 0},
            "castle_def": 300, "dragon": 0, "catapults": 0, "siege_towers": 0,
        },
        {
            "name": "3. Ajdar Hujumi (Adult Dragon) vs Kuchli Mudofaa Qal'asi",
            "attacker": {"infantry": 200, "archers": 100, "cavalry": 80, "spearmen": 70, "special_troops": 20},
            "defender": {"infantry": 250, "archers": 200, "cavalry": 80, "spearmen": 150, "special_troops": 20},
            "castle_def": 1200, "dragon": 2200, "dragon_tactic": "walls", "catapults": 4, "siege_towers": 2,
        },
        {
            "name": "4. Oliy Elita Gvardiya vs O'rtacha Garnizon",
            "attacker": {"infantry": 100, "archers": 50, "cavalry": 50, "spearmen": 50, "special_troops": 150},
            "defender": {"infantry": 220, "archers": 150, "cavalry": 80, "spearmen": 80, "special_troops": 10},
            "castle_def": 600, "dragon": 0, "catapults": 1, "siege_towers": 1,
        },
    ]

    battles_per_scenario = total_battles // len(scenarios)
    overall_results = []

    for sc in scenarios:
        att_wins = 0
        def_wins = 0
        tot_att_lost = 0
        tot_def_lost = 0
        tot_loot_gold = 0

        for _ in range(battles_per_scenario):
            res = calculate_battle(
                attacker_army=dict(sc["attacker"]),
                defender_garrison=dict(sc["defender"]),
                castle_defense=sc["castle_def"],
                dragon_power=sc.get("dragon", 0),
                dragon_tactic=sc.get("dragon_tactic", "none"),
                catapults=sc.get("catapults", 0),
                siege_towers=sc.get("siege_towers", 0),
            )
            if res["winner"] == "attacker":
                att_wins += 1
                tot_loot_gold += res.get("loot", {}).get("gold", 0)
            else:
                def_wins += 1

            tot_att_lost += sum(res["attacker_losses"].values())
            tot_def_lost += sum(res["defender_losses"].values())

        att_win_pct = (att_wins / battles_per_scenario) * 100
        avg_att_loss = tot_att_lost / battles_per_scenario
        avg_def_loss = tot_def_lost / battles_per_scenario
        avg_loot = tot_loot_gold / max(1, att_wins)

        sc_summary = {
            "scenario": sc["name"],
            "battles": battles_per_scenario,
            "att_win_rate": round(att_win_pct, 1),
            "def_win_rate": round(100 - att_win_pct, 1),
            "avg_attacker_losses": round(avg_att_loss, 1),
            "avg_defender_losses": round(avg_def_loss, 1),
            "avg_loot_gold": round(avg_loot, 1),
        }
        overall_results.append(sc_summary)

        print(f"\n⚔️ {sc['name']}:")
        print(f"   • Hujumchi G'alabasi: {att_win_pct:.1f}% | Mudofaa G'alabasi: {100 - att_win_pct:.1f}%")
        print(f"   • O'rtacha yo'qotishlar: Hujumchi {avg_att_loss:.1f} askar | Himoyachi {avg_def_loss:.1f} askar")
        print(f"   • G'alabadagi o'rtacha o'lja: {avg_loot:.1f} oltin")

    return {"scenarios": overall_results}


def run_economy_simulations(days: int = 30) -> Dict[str, Any]:
    print(f"\n" + "=" * 60)
    print(f"30 KUNLIK IQTISODIY O'SISH SIMULYATSIYASI (3 TA O'YINCHI MODELI)")
    print("=" * 60)

    # 3 ta o'yinchi profili
    # 1. Kazuallik (kuniga 1 marta kiradi, streak oladi, 1 ta kvest)
    # 2. O'rtacha Faol (kuniga 3 marta kiradi, 4 ta kvest, 1 qal'a solig'i)
    # 3. Hardkor Lord (barcha limitlarni to'liq bajaradi, 3 ta qal'a, faol harbiy o'yin)
    personas = [
        {"name": "Oddiy / Kazual Lord", "type": "casual", "hours_online": 2, "castles": 1, "daily_quests": 1},
        {"name": "Faol O'yinchi", "type": "active", "hours_online": 8, "castles": 2, "daily_quests": 4},
        {"name": "Hardkor Lord (Warlord)", "type": "hardcore", "hours_online": 16, "castles": 4, "daily_quests": 4},
    ]

    results = {}

    for p in personas:
        gold = ECONOMY.starting_gold
        food = ECONOMY.starting_food
        iron = ECONOMY.starting_iron
        xp = 0
        troops = 200  # boshlang'ich askarlar
        streak = 1

        snapshots = {}

        for day in range(1, days + 1):
            # 1. Streak bonusi
            st_reward = STREAK_REWARDS_CONFIG.get(streak, {})
            gold += st_reward.get("gold", 0)
            food += st_reward.get("food", 0)
            iron += st_reward.get("iron", 0)
            xp += st_reward.get("xp", 0)
            extra_tr = sum(st_reward.get("troops", {}).values())
            troops += extra_tr

            streak = (streak % 7) + 1

            # 2. Kunlik kvestlar
            q_cnt = p["daily_quests"]
            # Har bir kvest o'rtacha 350 oltin, 600 food, 200 iron, 25 xp beradi
            gold += q_cnt * 350
            food += q_cnt * 600
            iron += q_cnt * 200
            xp += q_cnt * 25
            if q_cnt == 4:
                # Grand chest
                gold += 2000
                food += 4000
                iron += 1500
                xp += 100
                troops += 5

            # 3. Soatlik iqtisodiyot (24 soat)
            # Har bir qal'a daromadi: ~25 gold, ~60 food, ~20 iron soatiga
            hourly_gold = ECONOMY.base_hourly_gold + (p["castles"] * 25)
            hourly_food = ECONOMY.base_hourly_food + (p["castles"] * 60)
            hourly_iron = ECONOMY.base_hourly_iron + (p["castles"] * 20)

            # Askar oziq-ovqat sarfi (o'rtacha 0.7 food/soat/askar)
            hourly_upkeep = troops * 0.70

            net_food_hour = hourly_food - hourly_upkeep
            daily_net_food = net_food_hour * 24

            gold += hourly_gold * 24
            food = max(0, food + int(daily_net_food))
            iron += hourly_iron * 24

            # 4. Askar yollash (iqtisodiy sarf)
            # O'yinchi har kuni ortiqcha oltin va temirining 40% ini armiya yollashga sarflaydi
            recruit_budget = int(gold * 0.40)
            recruited = recruit_budget // 3  # o'rtacha 3 oltin 1 askar
            iron_needed = recruited * 1
            if iron >= iron_needed:
                gold -= recruit_budget
                iron -= iron_needed
                troops += recruited

            # Jangdagi tasodifiy yo'qotishlar (faol o'yinchilarda)
            if p["type"] != "casual":
                casualties = int(troops * (0.05 if p["type"] == "active" else 0.08))
                troops = max(50, troops - casualties)

            level, title, _, _, _ = get_level_info(xp)

            if day in (1, 7, 14, 30):
                snapshots[f"Day_{day}"] = {
                    "day": day,
                    "level": level,
                    "gold": int(gold),
                    "food": int(food),
                    "iron": int(iron),
                    "troops": troops,
                }

        results[p["name"]] = snapshots

        print(f"\n👤 {p['name']}:")
        for d_key, data in snapshots.items():
            print(f"   • {d_key}: Daraja {data['level']} | Oltin: {data['gold']:,} | Oziq-ovqat: {data['food']:,} | Temir: {data['iron']:,} | Armiya: {data['troops']:,} askar")

    return results


if __name__ == "__main__":
    c_res = run_combat_simulations(1000)
    e_res = run_economy_simulations(30)
    print("\n" + "=" * 60)
    print("SIMULYATSIYA MUVAFFAQIYATLI YAKUNLANDI (100% DATA READY)")
    print("=" * 60)
