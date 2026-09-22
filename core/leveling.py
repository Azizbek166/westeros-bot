"""
Westeros MMORPG - Leveling Engine (Darajalar va Unvonlar Tizimi)
Foydalanuvchi darajasi 1 dan 30 gacha bo'ladi.
Har bir daraja shaxsiy Vesteros unvoni va mukofotlarni beradi.
"""

from typing import Tuple, Dict, Any, Optional

# 1 dan 30 gacha bo'lgan Vesteros unvonlari va kerakli XP
LEVEL_TITLES: Dict[int, Dict[str, Any]] = {
    1: {"title": "🌱 Yosh Lordling", "xp_req": 0, "bonus_desc": "Boshlang'ich daraja"},
    2: {"title": "🗡️ Qurolbardor (Squire)", "xp_req": 300, "bonus_desc": "+50🪙 oltin, +50🌾 g'alla"},
    3: {"title": "🛡️ Qasamyodli Ritsar", "xp_req": 1200, "bonus_desc": "+100🪙 oltin, +100⛓️ temir"},
    4: {"title": "🏹 Qal'a Soqchisi", "xp_req": 2700, "bonus_desc": "+150🪙 oltin, +15 ta piyoda"},
    5: {"title": "⚔️ Harbiy Kapitan", "xp_req": 4800, "bonus_desc": "+250🪙 oltin, +20 ta kamonchi"},
    6: {"title": "🏰 Qal'a Noziri (Castellan)", "xp_req": 7500, "bonus_desc": "+300🪙 oltin, +150⛓️ temir"},
    7: {"title": "🎖️ Bayroqdor Lord (Bannerman)", "xp_req": 10800, "bonus_desc": "+400🪙 oltin, +25 ta otliq"},
    8: {"title": "🐺 Shimol Himoyachisi", "xp_req": 14700, "bonus_desc": "+500🪙 oltin, +30 ta nayzachi"},
    9: {"title": "🦁 G'arb Qalqoni", "xp_req": 19200, "bonus_desc": "+600🪙 oltin, +250⛓️ temir"},
    10: {"title": "👑 Oliy Qo'mondon (High General)", "xp_req": 24300, "bonus_desc": "+800🪙 oltin, +50 ta elita askar, +50 Prestige"},
    11: {"title": "⚡ Bo'ron Yurtlari Hukmdori", "xp_req": 30000, "bonus_desc": "+900🪙 oltin, +300⛓️ temir"},
    12: {"title": "🌊 Qora Suv Admirali", "xp_req": 36300, "bonus_desc": "+1,000🪙 oltin, +50 ta kamonchi"},
    13: {"title": "🦅 Vodiy Qo'riqchisi", "xp_req": 43200, "bonus_desc": "+1,100🪙 oltin, +50 ta otliq"},
    14: {"title": "☀️ Janub Quyoshi Ritsari", "xp_req": 50700, "bonus_desc": "+1,200🪙 oltin, +400⛓️ temir"},
    15: {"title": "🗡️ Oq Qilich (Kingsguard)", "xp_req": 58800, "bonus_desc": "+1,500🪙 oltin, +75 ta elita askar, +75 Prestige"},
    16: {"title": "🐉 Valyria Qilichi Sohibi", "xp_req": 67500, "bonus_desc": "+1,600🪙 oltin, +500⛓️ temir"},
    17: {"title": "🏰 Qal'alar Fotihi", "xp_req": 76800, "bonus_desc": "+1,800🪙 oltin, +100 ta piyoda"},
    18: {"title": "📯 Ajdar Chavandozi (Dragonrider)", "xp_req": 86700, "bonus_desc": "+2,000🪙 oltin, +600⛓️ temir"},
    19: {"title": "🪙 Qirollik Xazinaboni", "xp_req": 97200, "bonus_desc": "+2,200🪙 oltin, +1,500🌾 g'alla"},
    20: {"title": "⚔️ Buyuk Strateg Lord", "xp_req": 108300, "bonus_desc": "+2,500🪙 oltin, +100 ta elita askar, +100 Prestige"},
    21: {"title": "🩸 Qadimgi Qon Vorisi", "xp_req": 120000, "bonus_desc": "+2,800🪙 oltin, +800⛓️ temir"},
    22: {"title": "🛡️ Vesteros Homiyi (Protector)", "xp_req": 132300, "bonus_desc": "+3,000🪙 oltin, +100 ta otliq"},
    23: {"title": "⚖️ Adolat Bosh Hakami", "xp_req": 145200, "bonus_desc": "+3,300🪙 oltin, +1,000⛓️ temir"},
    24: {"title": "🦅 Qirol O'ng Qo'li (Hand of the King)", "xp_req": 158700, "bonus_desc": "+3,800🪙 oltin, +150 ta elita askar, +150 Prestige"},
    25: {"title": "👑 Qirollik Regenti (Lord Regent)", "xp_req": 172800, "bonus_desc": "+4,200🪙 oltin, +1,200⛓️ temir"},
    26: {"title": "🔥 O'limdan Qaytgan Fathchi", "xp_req": 187500, "bonus_desc": "+4,600🪙 oltin, +150 ta otliq"},
    27: {"title": "❄️ Qishni Yenguvchi Afsona", "xp_req": 202800, "bonus_desc": "+5,000🪙 oltin, +1,500⛓️ temir"},
    28: {"title": "⚔️ Temir Taxt Da'vogari", "xp_req": 218700, "bonus_desc": "+6,000🪙 oltin, +200 ta elita askar, +200 Prestige"},
    29: {"title": "🌟 Yetti Qirollik Afsonasi", "xp_req": 235200, "bonus_desc": "+7,500🪙 oltin, +2,000⛓️ temir, +300 Prestige"},
    30: {"title": "👑 Vesterosning Mutlaq Qiroli (High King)", "xp_req": 252500, "bonus_desc": "+10,000🪙 oltin, +500 ta elita askar, +500 Prestige"},
}

MAX_LEVEL = 30


def get_level_info(xp: int) -> Tuple[int, str, int, int, float]:
    """
    XP asosida o'yinchi darajasini, unvonini va keyingi darajagacha progressni hisoblash.
    Qaytaradi: (level, title, current_level_xp, next_level_xp, progress_percentage)
    """
    level = 1
    for lvl in range(1, MAX_LEVEL + 1):
        if xp >= LEVEL_TITLES[lvl]["xp_req"]:
            level = lvl
        else:
            break

    curr_info = LEVEL_TITLES[level]
    title = curr_info["title"]
    curr_req = curr_info["xp_req"]

    if level >= MAX_LEVEL:
        next_req = curr_req
        progress = 100.0
    else:
        next_req = LEVEL_TITLES[level + 1]["xp_req"]
        diff = next_req - curr_req
        progress = min(100.0, max(0.0, ((xp - curr_req) / diff) * 100.0))

    return level, title, curr_req, next_req, progress


def check_user_level_up(user) -> Tuple[bool, int, str]:
    """
    O'yinchi XP sini tekshirib, agar darajasi ko'tarilgan bo'lsa darajasini yangilash va bonuslar berish.
    Qaytaradi: (leveled_up: bool, new_level: int, congratulation_message: str)
    """
    old_level = user.level or 1
    new_level, title, _, _, _ = get_level_info(user.xp or 0)

    if new_level > old_level:
        user.level = new_level
        # Bonuslarni hisoblash
        lvl_info = LEVEL_TITLES.get(new_level, {})
        bonus_gold = new_level * 37
        bonus_iron = new_level * 12
        bonus_prestige = new_level * 5

        user.gold += bonus_gold
        user.iron += bonus_iron
        user.prestige += bonus_prestige

        msg = (
            f"🎉 **TABRIKLAYMIZ! DARAJANGIZ OSHDI!**\n\n"
            f"⭐ Yangi daraja: **{new_level}-daraja**\n"
            f"🎖️ Yangi Unvon: **{title}**\n\n"
            f"🎁 **DARAJA MUKOFOTLARI:**\n"
            f"🪙 +{bonus_gold:,} oltin\n"
            f"⛓️ +{bonus_iron:,} temir\n"
            f"🏆 +{bonus_prestige} Prestige\n\n"
            f"O'z kuchingizni /profile bo'limida ko'ring!"
        )
        return True, new_level, msg

    return False, old_level, ""
