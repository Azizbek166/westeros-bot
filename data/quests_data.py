# ============================================================
# QUEST TIZIMI — ASOSIY, KUNLIK VA YASHIRIN VAZIFALAR
# ============================================================

MAIN_QUESTS = [
    {
        "code": "main_1",
        "title": "📜 1-Bob: Temir Taxt Chaqirig'i",
        "description": "Westeros notinchlikda. Xonadoningiz bayrog'i ostida dastlabki 300 ta askarni yollang.",
        "requirement_type": "army_total",
        "requirement_amount": 300,
        "reward_gold": 1000,
        "reward_food": 2000,
        "reward_iron": 500,
        "reward_xp": 150,
    },
    {
        "code": "main_2",
        "title": "🏰 2-Bob: Qal'a Mudofaasi",
        "description": "Mintaqangizdagi birinchi hududni razvedka qiling va qal'ani mustahkamlang.",
        "requirement_type": "scout_territory",
        "requirement_amount": 1,
        "reward_gold": 1500,
        "reward_food": 3000,
        "reward_iron": 800,
        "reward_xp": 250,
    },
    {
        "code": "main_3",
        "title": "⚔️ 3-Bob: Birinchi Zafar",
        "description": "Boshqa hududga yoki qaroqchilarga qarshi harbiy yurish qilib, g'alaba qozoning.",
        "requirement_type": "win_battle",
        "requirement_amount": 1,
        "reward_gold": 2500,
        "reward_food": 4000,
        "reward_iron": 1200,
        "reward_xp": 400,
    },
    {
        "code": "main_4",
        "title": "👑 4-Bob: Temir Taxtga Yo'l",
        "description": "Prestigengizni 500 ga yetkazing va King's Landing'ga yurish uchun tayyorlaning.",
        "requirement_type": "prestige_reach",
        "requirement_amount": 500,
        "reward_gold": 5000,
        "reward_food": 10000,
        "reward_iron": 3000,
        "reward_xp": 1000,
    },
]

DAILY_QUESTS = [
    {
        "code": "daily_recruit",
        "title": "🛡️ Yangi Qon",
        "description": "Bugun xazinadan mablag' ajratib 100 ta askar yollang.",
        "reward_gold": 500,
        "reward_food": 1000,
        "reward_xp": 80,
    },
    {
        "code": "daily_quiz",
        "title": "📚 Maester Saboqlari",
        "description": "Citadel viktorinasida 5 ta savolga to'g'ri javob bering.",
        "reward_gold": 600,
        "reward_iron": 300,
        "reward_xp": 100,
    },
    {
        "code": "daily_council",
        "title": "👑 Kengash Maslahati",
        "description": "Qirollik kengashida 2 ta masalani ko'rib chiqing.",
        "reward_gold": 400,
        "reward_food": 800,
        "reward_xp": 70,
    },
]

SECRET_QUESTS = [
    {
        "code": "secret_spy",
        "title": "🐺 Yashirin Masala: Xonadon orasidagi josus",
        "situation": "Xonadoningiz xazinasidagi ma'lumotlar raqib lordga sizib chiqayotgani ma'lum bo'ldi. Josus topildi, ammo u begona emas...",
        "choices": [
            {
                "text": "1️⃣ Maxfiy ravishda so'roq qilib, dezinformatsiya tarqatish",
                "gold_reward": 800,
                "prestige_reward": 40,
                "outcome": "✅ Dono qaror! Raqib soxta xabarga ishonib tuzoqqa tushdi.",
            },
            {
                "text": "2️⃣ Butun xalq oldida jazolash va xazinani musodara qilish",
                "gold_reward": 1200,
                "prestige_reward": -20,
                "outcome": "⚠️ Xazina to'ldi, ammo lordlar orasida qo'rquv va norozilik paydo bo'ldi.",
            },
            {
                "text": "3️⃣ Unga katta pora berib, o'zimizning josusimizga aylantirish",
                "gold_reward": -300,
                "prestige_reward": 60,
                "outcome": "🕵️ Endi raqibning har bir rejasi sizga oldindan ma'lum!",
            },
        ],
    },
    {
        "code": "secret_dragon_egg",
        "title": "🐉 Yashirin Masala: Valeriya xarobalaridagi tuxum",
        "situation": "Savdogarlar sharqdan tosh qotgan qadimiy ajdar tuxumini keltirishdi. Uni sotib olish uchun xazina talab etiladi.",
        "choices": [
            {
                "text": "1️⃣ 1,000 tangaga sotib olib, Maesterlarga o'rganishga berish",
                "gold_reward": -1000,
                "prestige_reward": 150,
                "outcome": "🔥 Maesterlar tuxum tirik ekanini tasdiqlashdi! Xonadon obro'si ko'tarildi.",
            },
            {
                "text": "2️⃣ Savdogarni hibsga olib, tuxumni xonadonga tekinga olish",
                "gold_reward": 0,
                "prestige_reward": -50,
                "outcome": "⚔️ Savdogarlar gildiyasi sizdan norozi bo'ldi, ammo tuxum qo'lga kiritildi.",
            },
            {
                "text": "3️⃣ Xavfli sehrdan qochib, taklifni rad etish",
                "gold_reward": 200,
                "prestige_reward": 10,
                "outcome": "🛡️ Xazina tejaldi, xonadon tinchligi saqlandi.",
            },
        ],
    },
]
