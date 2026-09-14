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
    dragon_tactic: str = "none",
    defender_dragon_power: int = 0,
) -> Dict[str, Any]:
    """
    Tosh-Qaychi-Qog'oz (RPS) va Strategik Drakarys asosida jang natijasi va yo'qotishlarni hisoblash.
    
    Qoidalar:
    - Otliq > Kamonchi (+40%)
    - Nayzachi > Otliq (+40%)
    - Kamonchi > Piyoda (+30%)
    - Piyoda > Nayzachi (+30%)
    - Ajdarlar jangi va Drakarys Taktikalari (devorlar, kamonchilar, old qatorlar, yalpi zarba)
    """
    troop_types = ["infantry", "archers", "cavalry", "spearmen", "special_troops"]

    # 1. Boshlang'ich sonlar
    att_troops = {t: attacker_army.get(t, 0) for t in troop_types}
    def_troops = {t: defender_garrison.get(t, 0) for t in troop_types}

    total_att_count = sum(att_troops.values())
    total_def_count = sum(def_troops.values())

    # ============================================================
    # DRAKARYS VA AJDARLARNING STRATEGIK HUJUMI
    # ============================================================
    dragon_details = ""
    def_losses = {t: 0 for t in troop_types}

    # Havoda ajdarlar to'qnashuvi (agar har ikki tomonda ajdar bo'lsa)
    eff_att_dragon = dragon_power
    if dragon_power > 0 and defender_dragon_power > 0:
        clash_diff = dragon_power - defender_dragon_power
        if clash_diff > 0:
            eff_att_dragon = int(dragon_power * 0.55)
            dragon_details += (
                f"🐉⚔️ **OSMONDA AJDARLAR JANGI!**\n"
                f"Himoyachi ajdari hujumchiga qattiq qarshilik ko'rsatdi, biroq hujumchi ajdar osmon hukmronligini qo'lga kiritdi!\n"
            )
        else:
            eff_att_dragon = int(dragon_power * 0.20)
            dragon_details += (
                f"🐉🛡️ **OSMONDA AJDARLAR JANGI!**\n"
                f"Qal'a uzra uchayotgan himoyachi ajdar hujumchining olovli zarbasini jilovladi va qal'ani himoya qildi!\n"
            )

    if eff_att_dragon > 0 and total_def_count > 0:
        total_killed = 0
        if dragon_tactic == "walls":
            # 1. Devorlarni eritish taktikasi
            melt_ratio = random.uniform(0.40, 0.55)
            castle_defense = max(50, int(castle_defense * (1.0 - melt_ratio)))
            max_kills = max(5, min(int(total_def_count * 0.10), 50))
            fire_kills = min(max_kills, int((eff_att_dragon / 25) * random.uniform(0.8, 1.2)))
            per_type = max(1, fire_kills // len(troop_types))
            for t in troop_types:
                k = min(def_troops[t], per_type)
                def_losses[t] += k
                def_troops[t] -= k
                total_killed += k
            dragon_details += (
                f"🔥🏰 **DRACARYS! (Qal'a devorlarini yoqish)**\n"
                f"Ajdar istehkomlarga olov yog'dirdi: Qal'a mudofaasi -{int(melt_ratio*100)}% ga eridi va devor ustidagi {total_killed} ta askar yondirildi!\n"
            )

        elif dragon_tactic == "ranged":
            # 2. Kamonchi va nayzachilarni nishonga olish
            target_types = ["archers", "spearmen"]
            ranged_total = sum(def_troops[t] for t in target_types)
            max_kills = max(5, min(int(ranged_total * 0.35), 75)) if ranged_total > 0 else 0
            fire_kills = min(max_kills, int((eff_att_dragon / 18) * random.uniform(0.9, 1.3)))
            if target_types and fire_kills > 0:
                per_t = max(1, fire_kills // len(target_types))
                for t in target_types:
                    k = min(def_troops[t], per_t)
                    def_losses[t] += k
                    def_troops[t] -= k
                    total_killed += k
            castle_defense = max(100, int(castle_defense * 0.85))
            dragon_details += (
                f"🔥🏹 **DRACARYS! (Kamonchilar va Nayzachilarni yoqish)**\n"
                f"Ajdar devor ustidagi merganlarni nishonga oldi: {total_killed} ta kamonchi va nayzachi kulga aylandi!\n"
            )

        elif dragon_tactic == "frontline":
            # 3. Piyoda va otliq qismlarni yoqish
            target_types = ["infantry", "cavalry"]
            front_total = sum(def_troops[t] for t in target_types)
            max_kills = max(5, min(int(front_total * 0.35), 75)) if front_total > 0 else 0
            fire_kills = min(max_kills, int((eff_att_dragon / 18) * random.uniform(0.9, 1.3)))
            if target_types and fire_kills > 0:
                per_t = max(1, fire_kills // len(target_types))
                for t in target_types:
                    k = min(def_troops[t], per_t)
                    def_losses[t] += k
                    def_troops[t] -= k
                    total_killed += k
            castle_defense = max(100, int(castle_defense * 0.85))
            dragon_details += (
                f"🔥🐎 **DRACARYS! (Old qatorlar — Piyoda va Otliqlarga zarba)**\n"
                f"Ajdar qanot yozib, old qatorlarni olov domiga soldi: {total_killed} ta og'ir askar safdan chiqarildi!\n"
            )

        else:
            # 4. Balanced / Yalpi zarba
            max_kills = max(5, min(int(total_def_count * 0.20), 80))
            fire_kills = min(max_kills, int((eff_att_dragon / 20) * random.uniform(0.8, 1.2)))
            per_type = max(1, fire_kills // len(troop_types))
            for t in troop_types:
                k = min(def_troops[t], per_type)
                def_losses[t] += k
                def_troops[t] -= k
                total_killed += k
            castle_defense = max(100, int(castle_defense * 0.75))
            dragon_details += (
                f"🔥⚡ **DRACARYS! (Yalpi Olovli Bo'ron)**\n"
                f"Ajdar butun qal'a bo'ylab olov purkadi: {total_killed} ta dushman askari yoqildi va mudofaa zaiflashtirildi!\n"
            )

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
