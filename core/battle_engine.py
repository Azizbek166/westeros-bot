import random
from typing import Dict, Any, Tuple
from data.units_data import UNITS_DATA, RPS_ADVANTAGES


def calculate_battle(
    attacker_army: Dict[str, int],
    defender_garrison: Dict[str, int],
    attacker_hero: Dict[str, Any] = None,
    defender_hero: Dict[str, Any] = None,
    castle_defense: int = 500,
    dragon_power: int = 0,
) -> Dict[str, Any]:
    """
    Tosh-Qaychi-Qog'oz (RPS) asosida jang natijasi va yo'qotishlarni hisoblash.
    
    Qoidalar:
    - Otliq > Kamonchi (+40%)
    - Nayzachi > Otliq (+40%)
    - Kamonchi > Piyoda (+30%)
    - Piyoda > Nayzachi (+30%)
    - Ajdar olovli hujumi (Dracarys)
    """
    troop_types = ["infantry", "archers", "cavalry", "spearmen", "special_troops"]

    # 1. Boshlang'ich sonlar
    att_troops = {t: attacker_army.get(t, 0) for t in troop_types}
    def_troops = {t: defender_garrison.get(t, 0) for t in troop_types}

    total_att_count = sum(att_troops.values())
    total_def_count = sum(def_troops.values())

    # Ajdar dastlabki olovli zarbasi (balanslangan: garnizonning 10-15% idan oshmaydi)
    dragon_details = ""
    def_losses = {t: 0 for t in troop_types}
    if dragon_power > 0 and total_def_count > 0:
        max_dragon_kills = max(5, min(int(total_def_count * 0.15), 60))
        calculated_kills = int((dragon_power / 20) * random.uniform(0.8, 1.3))
        fire_kills = min(max_dragon_kills, calculated_kills)

        per_type_kill = max(1, fire_kills // len(troop_types))
        total_killed = 0
        for t in troop_types:
            killed = min(def_troops[t], per_type_kill)
            def_losses[t] += killed
            def_troops[t] -= killed
            total_killed += killed

        # Qal'a istehkomini 20% ga eritadi
        castle_defense = max(100, int(castle_defense * 0.80))
        dragon_details = f"🔥 **DRACARYS!** Ajdarning olovli zarbasi garnizondan {total_killed} askarni yoqdi va qal'a istehkomlarini eritdi!\n"

    if total_att_count <= 0:
        return {
            "winner": "defender",
            "attacker_losses": {t: 0 for t in troop_types},
            "defender_losses": {t: 0 for t in troop_types},
            "remaining_attacker": att_troops,
            "remaining_defender": def_troops,
            "loot": {"gold": 0, "food": 0, "iron": 0},
            "rounds": 0,
            "details": "Hujumchi armiya safarbar qilinmadi.",
        }

    if total_def_count <= 0:
        return {
            "winner": "attacker",
            "attacker_losses": {t: 0 for t in troop_types},
            "defender_losses": {t: 0 for t in troop_types},
            "remaining_attacker": att_troops,
            "remaining_defender": def_troops,
            "loot": {"gold": 1000, "food": 2000, "iron": 500},
            "rounds": 1,
            "details": "Qal'a garnizonsiz qoldirilgan. Hujumchilar oson g'alaba qozondi.",
        }

    # 2. Qahramon bonuslari
    att_lead_bonus = 1.0 + ((attacker_hero.get("leadership", 50) if attacker_hero else 50) / 200.0)
    def_lead_bonus = 1.0 + ((defender_hero.get("leadership", 50) if defender_hero else 50) / 200.0)

    # Qal'a mudofaa bonusi (masalan: 850 defense = +35% mudofaa)
    castle_mult = 1.0 + (min(castle_defense, 1500) / 2500.0)

    # 3. Jang raundlari (maksimal 3 raund)
    att_losses = {t: 0 for t in troop_types}
    if not def_losses:
        def_losses = {t: 0 for t in troop_types}

    rounds = 0
    while rounds < 3:
        rounds += 1

        curr_att_total = sum(att_troops.values())
        curr_def_total = sum(def_troops.values())

        if curr_att_total <= 0 or curr_def_total <= 0:
            break

        # Hujumchi kuchini hisoblash
        att_power = 0.0
        for a_type, a_count in att_troops.items():
            if a_count <= 0:
                continue
            unit_atk = UNITS_DATA[a_type]["attack"]

            # RPS multiplikatorini dominant himoyachiga nisbatan olish
            mult = 1.0
            for d_type, d_count in def_troops.items():
                if d_count > 0 and (a_type, d_type) in RPS_ADVANTAGES:
                    mult = max(mult, RPS_ADVANTAGES[(a_type, d_type)])

            att_power += a_count * unit_atk * mult

        att_power *= att_lead_bonus

        # Himoyachi kuchini hisoblash
        def_power = 0.0
        for d_type, d_count in def_troops.items():
            if d_count <= 0:
                continue
            unit_def = UNITS_DATA[d_type]["defense"]

            mult = 1.0
            for a_type, a_count in att_troops.items():
                if a_count > 0 and (d_type, a_type) in RPS_ADVANTAGES:
                    mult = max(mult, RPS_ADVANTAGES[(d_type, a_type)])

            def_power += d_count * unit_def * mult

        def_power *= def_lead_bonus * castle_mult

        # Raunddagi yo'qotishlarni hisoblash
        # Hujumchi zarar beradi -> Himoyachi yo'qotadi
        def_loss_ratio = min(0.60, (att_power / (def_power + att_power + 1.0)) * random.uniform(0.7, 1.0))
        for t in troop_types:
            lost = int(def_troops[t] * def_loss_ratio)
            def_losses[t] += lost
            def_troops[t] = max(0, def_troops[t] - lost)

        # Himoyachi zarba qaytaradi -> Hujumchi yo'qotadi
        att_loss_ratio = min(0.60, (def_power / (att_power + def_power + 1.0)) * random.uniform(0.7, 1.0))
        for t in troop_types:
            lost = int(att_troops[t] * att_loss_ratio)
            att_losses[t] += lost
            att_troops[t] = max(0, att_troops[t] - lost)

    # 4. G'olibni aniqlash
    final_att = sum(att_troops.values())
    final_def = sum(def_troops.values())

    if final_att > final_def:
        winner = "attacker"
        loot = {
            "gold": random.randint(300, 1200),
            "food": random.randint(500, 2000),
            "iron": random.randint(100, 400),
        }
        details = f"{dragon_details}🏆 **Hujumchilar qat'iy g'alabaga erishdi!** Qal'a egallandi."
    else:
        winner = "defender"
        loot = {"gold": 0, "food": 0, "iron": 0}
        details = f"{dragon_details}🛡️ **Himoyachilar hujumni qaytarishga muvaffaq bo'ldi!** Qal'a devorlari bardosh berdi."

    return {
        "winner": winner,
        "attacker_losses": att_losses,
        "defender_losses": def_losses,
        "remaining_attacker": att_troops,
        "remaining_defender": def_troops,
        "loot": loot,
        "rounds": rounds,
        "details": details,
    }
