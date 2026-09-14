# ============================================================
# QO'SHIN TURLARI VA TOSH-QAYCHI-QOG'OZ (RPS) FORMULASI
# ============================================================

UNITS_DATA = {
    "infantry": {
        "name": "🛡️ Piyoda Askar (Infantry)",
        "code": "infantry",
        "attack": 10,
        "defense": 15,
        "gold_cost": 2,
        "iron_cost": 1,
        "food_upkeep": 0.5,
        "description": "Zirhli qalqonli jangchilar. Nayzachilarga qarshi kuchli.",
    },
    "archers": {
        "name": "🏹 Kamonchi (Archers)",
        "code": "archers",
        "attack": 16,
        "defense": 6,
        "gold_cost": 3,
        "iron_cost": 1,
        "food_upkeep": 0.6,
        "description": "Masofadan zarba beruvchilar. Piyodalarga qarshi ustun.",
    },
    "cavalry": {
        "name": "🐎 Otliq (Cavalry)",
        "code": "cavalry",
        "attack": 22,
        "defense": 12,
        "gold_cost": 6,
        "iron_cost": 3,
        "food_upkeep": 1.2,
        "description": "Tezkor va halokatli zarba. Kamonchilarni tor-mor qiladi.",
    },
    "spearmen": {
        "name": "🗡️ Nayzachi (Spearmen)",
        "code": "spearmen",
        "attack": 12,
        "defense": 16,
        "gold_cost": 2,
        "iron_cost": 2,
        "food_upkeep": 0.5,
        "description": "Uzun nayzalar devori. Otliqlar hujumini qaytaradi.",
    },
    "special_troops": {
        "name": "🔥 Maxsus Xonadon Asqari (Special)",
        "code": "special_troops",
        "attack": 30,
        "defense": 25,
        "gold_cost": 12,
        "iron_cost": 6,
        "food_upkeep": 1.5,
        "description": "Har bir xonadonning elita askarlari (Direwolf Guard, Rose Knights va h.k.).",
    },
}

# ============================================================
# TOSH-QAYCHI-QOG'OZ AVZALLIKLARI (ADVANTAGES)
# ============================================================

# (Hujumchi turi, Himoyachi turi): Multiplikator
RPS_ADVANTAGES = {
    # Otliq > Kamonchi (+40%)
    ("cavalry", "archers"): 1.40,
    # Nayzachi > Otliq (+40%)
    ("spearmen", "cavalry"): 1.40,
    # Kamonchi > Piyoda (+30%)
    ("archers", "infantry"): 1.30,
    # Piyoda > Nayzachi (+30%)
    ("infantry", "spearmen"): 1.30,

    # Teskari ta'sir (Kamayish)
    ("archers", "cavalry"): 0.70,
    ("cavalry", "spearmen"): 0.70,
    ("infantry", "archers"): 0.80,
    ("spearmen", "infantry"): 0.80,
}
