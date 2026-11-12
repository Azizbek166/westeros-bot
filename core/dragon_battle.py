import random
from typing import Dict, Any, Tuple, List
from core.balance import DRAGON

LEGENDARY_NPC_DRAGONS = [
    {"name": "🐉 Balerion (Qora Dahshat)", "grade": "A", "stage": "adult", "level": 20, "power": 3800, "user_name": "Eygon Targaryen"},
    {"name": "🐉 Vhagar (Qadimgi Malika)", "grade": "A", "stage": "adult", "level": 19, "power": 3600, "user_name": "Eymond Targaryen"},
    {"name": "🐉 Caraxes (Qonli Ajdar)", "grade": "B", "stage": "adult", "level": 18, "power": 3300, "user_name": "Deymon Targaryen"},
    {"name": "🐉 Meleys (Qizil Malika)", "grade": "B", "stage": "adult", "level": 17, "power": 3100, "user_name": "Reynis Targaryen"},
    {"name": "🐉 Vermithor (Bronza Qahr)", "grade": "B", "stage": "adult", "level": 16, "power": 2900, "user_name": "Xyu Qalbaki"},
    {"name": "🐉 Sunfyre (Oltin Porloq)", "grade": "C", "stage": "adult", "level": 15, "power": 2700, "user_name": "Eygon II Targaryen"},
    {"name": "🐉 Silverwing (Kumush Qanot)", "grade": "C", "stage": "adult", "level": 14, "power": 2500, "user_name": "Ulf Oq"},
    {"name": "🐉 Syrax (Oltin Malika)", "grade": "C", "stage": "adult", "level": 13, "power": 2400, "user_name": "Reynira Targaryen"},
]


def calculate_dragon_power(dragon: Dict[str, Any]) -> int:
    """Ajdarning xususiyatlari asosida jangovar quvvatini hisoblash"""
    base_power = dragon.get("power", 100) or 100
    grade = str(dragon.get("grade", "C")).upper()
    stage = str(dragon.get("stage", "adult")).lower()
    level = int(dragon.get("level", 1) or 1)

    grade_mult = DRAGON.grade_multipliers.get(grade, 1.0)
    stage_mult = DRAGON.stage_multipliers.get(stage, 1.05)
    level_mult = 1.0 + (level * DRAGON.level_growth_rate)

    return int(base_power * grade_mult * stage_mult * level_mult)


def simulate_dragon_battle(d1: Dict[str, Any], d2: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ikki ajdar o'rtasida 3 raundlik shiddatli havo jangini simulyatsiya qilish.
    Natijalar faqat bitta ajdarning doimiy ustunligiga bog'lanib qolmasligi uchun
    dinamik shanslar va raundlar hisobga olingan.
    """
    p1_eff = calculate_dragon_power(d1)
    p2_eff = calculate_dragon_power(d2)

    d1_name = d1.get("name", "Ajdar 1")
    d2_name = d2.get("name", "Ajdar 2")
    u1_name = d1.get("user_name", "Lord 1")
    u2_name = d2.get("user_name", "Lord 2")

    rounds_info = [
        ("1-Raund: Osmon Hukmronligi va Olov Purkash", "🔥", "balandlikdan sho'ng'ib ulkan olov purkadi"),
        ("2-Raund: Bulutlar Arasida Changal To'qnashuvi", "⚡", "o'tkir changallari bilan havoda shiddatli hujum qildi"),
        ("3-Raund: Hal Qiluvchi Apokalipsis Zarbasi", "💥", "butun quvvatini to'plab hal qiluvchi olovli zarba berdi"),
    ]

    d1_score = 0
    d2_score = 0
    d1_total_dmg = 0
    d2_total_dmg = 0
    logs: List[str] = []

    logs.append(f"⚔️ **AJDARLAR TO'QNASHUVI BOSHLANDI!**")
    logs.append(f"🐉 **{d1_name}** ({u1_name}) — Quvvat: **{p1_eff:,}**")
    logs.append(f"🐉 **{d2_name}** ({u2_name}) — Quvvat: **{p2_eff:,}**\n")

    for idx, (title, icon, action_desc) in enumerate(rounds_info, 1):
        # Shiddatli dinamik zarba (0.78 dan 1.22 gacha tasodifiy omil)
        roll1 = int(p1_eff * random.uniform(0.78, 1.22))
        roll2 = int(p2_eff * random.uniform(0.78, 1.22))

        d1_total_dmg += roll1
        d2_total_dmg += roll2

        if roll1 >= roll2:
            d1_score += 1
            round_winner = d1_name
            r_msg = f"{icon} **{title}**\n• {d1_name} {action_desc} ({roll1:,} zarar)!\n• {d2_name} javob berdi ({roll2:,} zarar).\n👉 *Raund g'olibi:* **{round_winner}**"
        else:
            d2_score += 1
            round_winner = d2_name
            r_msg = f"{icon} **{title}**\n• {d2_name} {action_desc} ({roll2:,} zarar)!\n• {d1_name} javob berdi ({roll1:,} zarar).\n👉 *Raund g'olibi:* **{round_winner}**"

        logs.append(r_msg)

    if d1_score > d2_score:
        winner = d1
        loser = d2
        winner_score = d1_score
        loser_score = d2_score
    elif d2_score > d1_score:
        winner = d2
        loser = d1
        winner_score = d2_score
        loser_score = d1_score
    else:
        # Raundlar teng kelsa jami yetkazilgan zararga qarab aniqlanadi
        if d1_total_dmg >= d2_total_dmg:
            winner = d1
            loser = d2
            winner_score = d1_score
            loser_score = d2_score
        else:
            winner = d2
            loser = d1
            winner_score = d2_score
            loser_score = d1_score

    w_name = winner.get("name", "G'olib Ajdar")
    l_name = loser.get("name", "Mag'lub Ajdar")
    w_user = winner.get("user_name", "Lord")

    logs.append(f"\n🏆 **JANG YAKUNLANDI: G'OLIB — {w_name}!**")
    logs.append(f"👑 Hukmdor: **{w_user}**")
    logs.append(f"📊 Hisob: **{winner_score} : {loser_score}** (Raundlar)")

    return {
        "winner": winner,
        "loser": loser,
        "winner_score": winner_score,
        "loser_score": loser_score,
        "duel_log": "\n".join(logs),
    }
