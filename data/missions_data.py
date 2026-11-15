"""
The Iron Throne RPG — Haftalik va Ajdaho Missiyalari Ma'lumotlari.
Mukofotlar faqat resurs (oltin, bug'doy, temir), XP va kichik prestige beradi.
Hech qanday qo'shin, ajdaho yoki donat buyumi berilmaydi.
"""
from typing import Dict, Any, List


WEEKLY_MISSIONS: List[Dict[str, Any]] = [
    {
        "code": "wk_duel",
        "category": "weekly",
        "title": "⚔️ Duel Ustasi",
        "desc": "Hafta davomida 5 ta duelda g'alaba qozoning",
        "target": 5,
        "source": "db_duel",
        "gold": 1000,
        "food": 1500,
        "iron": 500,
        "xp": 250,
        "prestige": 15,
    },
    {
        "code": "wk_caravan",
        "category": "weekly",
        "title": "🐪 Karvon Himoyachisi",
        "desc": "3 ta savdo karvonini manzilga yetkazing",
        "target": 3,
        "source": "db_caravan",
        "gold": 900,
        "food": 1400,
        "iron": 450,
        "xp": 220,
        "prestige": 12,
    },
    {
        "code": "wk_spy",
        "category": "weekly",
        "title": "🕵️ Soya Ustasi",
        "desc": "3 ta josuslik topshirig'ini muvaffaqiyatli bajaring",
        "target": 3,
        "source": "db_spy",
        "gold": 950,
        "food": 1200,
        "iron": 500,
        "xp": 220,
        "prestige": 15,
    },
    {
        "code": "wk_recruit",
        "category": "weekly",
        "title": "🛡️ Yangi Lashkar",
        "desc": "Hafta davomida 500 ta askar yollang",
        "target": 500,
        "source": "event",
        "event_type": "recruit",
        "gold": 1100,
        "food": 1800,
        "iron": 600,
        "xp": 260,
        "prestige": 15,
    },
    {
        "code": "wk_march",
        "category": "weekly",
        "title": "🏰 Yurish Qahramoni",
        "desc": "2 ta harbiy yurishda g'alaba qozoning",
        "target": 2,
        "source": "db_march",
        "gold": 1400,
        "food": 2200,
        "iron": 800,
        "xp": 350,
        "prestige": 25,
    },
    {
        "code": "wk_quiz",
        "category": "weekly",
        "title": "📚 Maester Shogirdi",
        "desc": "15 ta Sitadel viktorinasi savoliga qatnashing",
        "target": 15,
        "source": "event",
        "event_type": "quiz",
        "gold": 850,
        "food": 1300,
        "iron": 400,
        "xp": 300,
        "prestige": 15,
    },
    {
        "code": "wk_secret",
        "category": "weekly",
        "title": "🕯️ Sir Izlovchi",
        "desc": "5 ta yashirin missiyani yakunlang",
        "target": 5,
        "source": "event",
        "event_type": "secret_quest",
        "gold": 1000,
        "food": 1500,
        "iron": 500,
        "xp": 250,
        "prestige": 15,
    },
    {
        "code": "dr_feed",
        "category": "dragon",
        "title": "🐉 Ajdar Parvarishchisi",
        "desc": "Ajdaringizni haftada 5 marta boqing",
        "target": 5,
        "source": "event",
        "event_type": "dragon_feed",
        "gold": 900,
        "food": 1600,
        "iron": 450,
        "xp": 240,
        "prestige": 15,
    },
    {
        "code": "dr_train",
        "category": "dragon",
        "title": "🔥 Ajdar Mashqchisi",
        "desc": "Ajdaringizni 2 marta mashq qildiring",
        "target": 2,
        "source": "event",
        "event_type": "dragon_train",
        "gold": 1100,
        "food": 1700,
        "iron": 550,
        "xp": 260,
        "prestige": 18,
    },
    {
        "code": "dr_duel",
        "category": "dragon",
        "title": "⚔️ Ajdar Jangchisi",
        "desc": "Ajdarlar duelida 3 ta g'alaba qozoning",
        "target": 3,
        "source": "db_dragon_duel",
        "gold": 1500,
        "food": 2400,
        "iron": 850,
        "xp": 380,
        "prestige": 25,
    },
]

WEEKLY_ALL_BONUS: Dict[str, Any] = {
    "code": "wk_all_bonus",
    "category": "bonus",
    "title": "🏆 Haftalik Katta Bonus",
    "desc": "Barcha 10 ta haftalik va ajdaho missiyasini bajarganingiz uchun mukofot",
    "target": len(WEEKLY_MISSIONS),
    "gold": 2500,
    "food": 4000,
    "iron": 1500,
    "xp": 600,
    "prestige": 40,
}

MISSIONS_BY_CODE: Dict[str, Dict[str, Any]] = {
    m["code"]: m for m in WEEKLY_MISSIONS
}
MISSIONS_BY_CODE[WEEKLY_ALL_BONUS["code"]] = WEEKLY_ALL_BONUS

EVENT_TO_MISSION: Dict[str, str] = {
    m["event_type"]: m["code"]
    for m in WEEKLY_MISSIONS
    if m.get("source") == "event" and m.get("event_type")
}
