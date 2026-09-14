# ============================================================
# WESTEROS XARITASI VA HUDUDLARI
# ============================================================

REGIONS_DATA = {
    "The North": {"emoji": "🐺", "capital": "Winterfell", "description": "Cheksiz qor va sovuq o'lka."},
    "Westerlands": {"emoji": "🦁", "capital": "Casterly Rock", "description": "Tilla konlari va boy tepaliklar."},
    "Crownlands": {"emoji": "👑", "capital": "King's Landing", "description": "Temir Taxt va qirollik markazi."},
    "The Reach": {"emoji": "🌹", "capital": "Highgarden", "description": "Hosilga to'la yerlar va yashil vodiylar."},
    "Dorne": {"emoji": "☀️", "capital": "Sunspear", "description": "Qizg'in sahrolar va qizil tog'lar."},
    "The Vale": {"emoji": "🦅", "capital": "The Eyrie", "description": "O'tib bo'lmas baland qoyalar."},
    "Riverlands": {"emoji": "🐟", "capital": "Riverrun", "description": "Uchta daryo kesishgan markaziy yerlar."},
    "Iron Islands": {"emoji": "🐙", "capital": "Pyke", "description": "Bo'ronli dengiz orollari."},
    "Stormlands": {"emoji": "🦌", "capital": "Storm's End", "description": "Momaqaldiroqli bo'ronlar yurti."},
    "Beyond the Wall": {"emoji": "❄️", "capital": "Castle Black", "description": "Devor orti abadiy muzliklari."},
}

TERRITORIES_DATA = {
    # --------------------------------------------------------
    # THE NORTH
    # --------------------------------------------------------
    "winterfell": {
        "id": 1,
        "name": "Winterfell",
        "region": "The North",
        "castle": "Winterfell Qal'asi",
        "initial_owner_id": 1,  # Stark
        "population": 80000,
        "gold_income": 450,
        "food_income": 1200,
        "iron_income": 250,
        "defense": 850,
        "garrison_infantry": 600,
        "garrison_archers": 400,
        "garrison_cavalry": 200,
        "garrison_spearmen": 200,
        "is_capital": True,
    },
    "white_harbor": {
        "id": 2,
        "name": "White Harbor",
        "region": "The North",
        "castle": "New Castle",
        "initial_owner_id": 1,
        "population": 65000,
        "gold_income": 600,
        "food_income": 900,
        "iron_income": 150,
        "defense": 650,
        "garrison_infantry": 400,
        "garrison_archers": 300,
        "garrison_cavalry": 100,
        "garrison_spearmen": 150,
        "is_capital": False,
    },
    "moat_cailin": {
        "id": 3,
        "name": "Moat Cailin",
        "region": "The North",
        "castle": "Moat Cailin Minoralari",
        "initial_owner_id": 1,
        "population": 15000,
        "gold_income": 200,
        "food_income": 300,
        "iron_income": 100,
        "defense": 1200,  # O'tib bo'lmas mudofaa
        "garrison_infantry": 300,
        "garrison_archers": 500,
        "garrison_cavalry": 50,
        "garrison_spearmen": 400,
        "is_capital": False,
    },
    "the_wall": {
        "id": 4,
        "name": "The Wall",
        "region": "Beyond the Wall",
        "castle": "Castle Black",
        "initial_owner_id": 48,  # Night's Watch
        "population": 10000,
        "gold_income": 150,
        "food_income": 600,
        "iron_income": 300,
        "defense": 2000,
        "garrison_infantry": 500,
        "garrison_archers": 800,
        "garrison_cavalry": 100,
        "garrison_spearmen": 600,
        "is_capital": True,
    },

    # --------------------------------------------------------
    # WESTERLANDS
    # --------------------------------------------------------
    "casterly_rock": {
        "id": 5,
        "name": "Casterly Rock",
        "region": "Westerlands",
        "castle": "The Rock Qal'asi",
        "initial_owner_id": 8,  # Lannister
        "population": 90000,
        "gold_income": 1500,  # Tilla koni
        "food_income": 800,
        "iron_income": 600,
        "defense": 950,
        "garrison_infantry": 800,
        "garrison_archers": 400,
        "garrison_cavalry": 400,
        "garrison_spearmen": 300,
        "is_capital": True,
    },
    "lannisport": {
        "id": 6,
        "name": "Lannisport",
        "region": "Westerlands",
        "castle": "Lannisport Bandargohi",
        "initial_owner_id": 8,
        "population": 120000,
        "gold_income": 1100,
        "food_income": 700,
        "iron_income": 300,
        "defense": 600,
        "garrison_infantry": 500,
        "garrison_archers": 400,
        "garrison_cavalry": 200,
        "garrison_spearmen": 200,
        "is_capital": False,
    },
    "golden_tooth": {
        "id": 7,
        "name": "Golden Tooth",
        "region": "Westerlands",
        "castle": "Golden Tooth Qal'asi",
        "initial_owner_id": 11,  # Lefford
        "population": 25000,
        "gold_income": 700,
        "food_income": 400,
        "iron_income": 400,
        "defense": 1000,
        "garrison_infantry": 400,
        "garrison_archers": 300,
        "garrison_cavalry": 100,
        "garrison_spearmen": 300,
        "is_capital": False,
    },

    # --------------------------------------------------------
    # CROWNLANDS (TEMIR TAXT)
    # --------------------------------------------------------
    "kings_landing": {
        "id": 8,
        "name": "King's Landing",
        "region": "Crownlands",
        "castle": "Red Keep (Temir Taxt)",
        "initial_owner_id": 13,  # Targaryen / Royal
        "population": 300000,
        "gold_income": 2000,
        "food_income": 1000,
        "iron_income": 500,
        "defense": 1100,
        "garrison_infantry": 1200,
        "garrison_archers": 800,
        "garrison_cavalry": 500,
        "garrison_spearmen": 600,
        "is_capital": True,
    },
    "dragonstone": {
        "id": 9,
        "name": "Dragonstone",
        "region": "Crownlands",
        "castle": "Dragonstone Ajdar Qal'asi",
        "initial_owner_id": 13,
        "population": 35000,
        "gold_income": 400,
        "food_income": 400,
        "iron_income": 700,  # Dragonglass / Temir
        "defense": 900,
        "garrison_infantry": 500,
        "garrison_archers": 400,
        "garrison_cavalry": 100,
        "garrison_spearmen": 300,
        "is_capital": False,
    },

    # --------------------------------------------------------
    # THE REACH
    # --------------------------------------------------------
    "highgarden": {
        "id": 10,
        "name": "Highgarden",
        "region": "The Reach",
        "castle": "Highgarden Qal'asi",
        "initial_owner_id": 17,  # Tyrell
        "population": 150000,
        "gold_income": 800,
        "food_income": 2500,  # Eng katta g'alla ombori
        "iron_income": 300,
        "defense": 750,
        "garrison_infantry": 800,
        "garrison_archers": 500,
        "garrison_cavalry": 600,
        "garrison_spearmen": 400,
        "is_capital": True,
    },
    "oldtown": {
        "id": 11,
        "name": "Oldtown",
        "region": "The Reach",
        "castle": "Hightower Minora & Citadel",
        "initial_owner_id": 18,  # Hightower
        "population": 220000,
        "gold_income": 1300,
        "food_income": 1500,
        "iron_income": 400,
        "defense": 850,
        "garrison_infantry": 700,
        "garrison_archers": 600,
        "garrison_cavalry": 300,
        "garrison_spearmen": 300,
        "is_capital": False,
    },
    "horn_hill": {
        "id": 12,
        "name": "Horn Hill",
        "region": "The Reach",
        "castle": "Horn Hill Qal'asi",
        "initial_owner_id": 19,  # Tarly
        "population": 45000,
        "gold_income": 400,
        "food_income": 1100,
        "iron_income": 350,
        "defense": 700,
        "garrison_infantry": 500,
        "garrison_archers": 300,
        "garrison_cavalry": 300,
        "garrison_spearmen": 300,
        "is_capital": False,
    },

    # --------------------------------------------------------
    # DORNE
    # --------------------------------------------------------
    "sunspear": {
        "id": 13,
        "name": "Sunspear",
        "region": "Dorne",
        "castle": "Sunspear Qal'asi",
        "initial_owner_id": 22,  # Martell
        "population": 85000,
        "gold_income": 600,
        "food_income": 700,
        "iron_income": 300,
        "defense": 800,
        "garrison_infantry": 600,
        "garrison_archers": 400,
        "garrison_cavalry": 500,
        "garrison_spearmen": 500,
        "is_capital": True,
    },
    "starfall": {
        "id": 14,
        "name": "Starfall",
        "region": "Dorne",
        "castle": "Starfall Qal'asi",
        "initial_owner_id": 23,  # Dayne
        "population": 40000,
        "gold_income": 450,
        "food_income": 600,
        "iron_income": 500,
        "defense": 750,
        "garrison_infantry": 400,
        "garrison_archers": 300,
        "garrison_cavalry": 300,
        "garrison_spearmen": 300,
        "is_capital": False,
    },

    # --------------------------------------------------------
    # THE VALE
    # --------------------------------------------------------
    "eyrie": {
        "id": 15,
        "name": "The Eyrie",
        "region": "The Vale",
        "castle": "The Eyrie (Burgut uyasi)",
        "initial_owner_id": 27,  # Arryn
        "population": 30000,
        "gold_income": 500,
        "food_income": 900,
        "iron_income": 350,
        "defense": 1500,  # Qoyali yengilmas qal'a
        "garrison_infantry": 400,
        "garrison_archers": 600,
        "garrison_cavalry": 200,
        "garrison_spearmen": 400,
        "is_capital": True,
    },
    "gulltown": {
        "id": 16,
        "name": "Gulltown",
        "region": "The Vale",
        "castle": "Gulltown Porti",
        "initial_owner_id": 27,
        "population": 90000,
        "gold_income": 850,
        "food_income": 750,
        "iron_income": 200,
        "defense": 650,
        "garrison_infantry": 400,
        "garrison_archers": 350,
        "garrison_cavalry": 150,
        "garrison_spearmen": 200,
        "is_capital": False,
    },

    # --------------------------------------------------------
    # RIVERLANDS
    # --------------------------------------------------------
    "riverrun": {
        "id": 17,
        "name": "Riverrun",
        "region": "Riverlands",
        "castle": "Riverrun Suv Qal'asi",
        "initial_owner_id": 31,  # Tully
        "population": 70000,
        "gold_income": 550,
        "food_income": 1300,
        "iron_income": 250,
        "defense": 800,
        "garrison_infantry": 500,
        "garrison_archers": 400,
        "garrison_cavalry": 300,
        "garrison_spearmen": 300,
        "is_capital": True,
    },
    "the_twins": {
        "id": 18,
        "name": "The Twins",
        "region": "Riverlands",
        "castle": "The Twins Ko'prigi",
        "initial_owner_id": 32,  # Frey
        "population": 40000,
        "gold_income": 700,  # Boj to'lovlari
        "food_income": 800,
        "iron_income": 200,
        "defense": 900,
        "garrison_infantry": 600,
        "garrison_archers": 500,
        "garrison_cavalry": 100,
        "garrison_spearmen": 400,
        "is_capital": False,
    },
    "harrenhal": {
        "id": 19,
        "name": "Harrenhal",
        "region": "Riverlands",
        "castle": "Harrenhal Qora Qal'asi",
        "initial_owner_id": 31,
        "population": 50000,
        "gold_income": 600,
        "food_income": 1000,
        "iron_income": 400,
        "defense": 1000,
        "garrison_infantry": 700,
        "garrison_archers": 500,
        "garrison_cavalry": 200,
        "garrison_spearmen": 400,
        "is_capital": False,
    },

    # --------------------------------------------------------
    # IRON ISLANDS
    # --------------------------------------------------------
    "pyke": {
        "id": 20,
        "name": "Pyke",
        "region": "Iron Islands",
        "castle": "Pyke Dengiz Qal'asi",
        "initial_owner_id": 36,  # Greyjoy
        "population": 45000,
        "gold_income": 400,
        "food_income": 500,
        "iron_income": 600,
        "defense": 750,
        "garrison_infantry": 600,
        "garrison_archers": 300,
        "garrison_cavalry": 50,
        "garrison_spearmen": 400,
        "is_capital": True,
    },

    # --------------------------------------------------------
    # STORMLANDS
    # --------------------------------------------------------
    "storms_end": {
        "id": 21,
        "name": "Storm's End",
        "region": "Stormlands",
        "castle": "Storm's End Sehrli Qal'asi",
        "initial_owner_id": 40,  # Baratheon
        "population": 75000,
        "gold_income": 600,
        "food_income": 950,
        "iron_income": 450,
        "defense": 1200,  # Qalin bo'ron devorlari
        "garrison_infantry": 700,
        "garrison_archers": 400,
        "garrison_cavalry": 300,
        "garrison_spearmen": 400,
        "is_capital": True,
    },
}
