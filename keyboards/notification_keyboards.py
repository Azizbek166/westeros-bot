"""
Telegram Bot Notification Keyboards with Mini App Deep-Links and Fallback Bot Buttons.
Stage 6: Connects game events (attacks, duels, daily rewards, quiz reminders, bank interest)
to the appropriate Telegram Mini App screen while preserving legacy bot menus as fallbacks.
"""
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from config import get_miniapp_url


def attack_alert_keyboard(territory_id: int) -> InlineKeyboardMarkup:
    """
    Qal'aga hujum boshlanganda himoyachi va ittifoqchilarga yuboriladigan ogohlantirish klaviaturasi.
    """
    buttons = [
        [
            InlineKeyboardButton(
                "🏰 Mini App'da Qal'ani Mudofaa Qilish 🛡️",
                web_app=WebAppInfo(url=get_miniapp_url("castles"))
            )
        ],
        [
            InlineKeyboardButton("🛡️ Botda Shoshilinch Askar Qo'shish", callback_data=f"def_rf_menu:{territory_id}"),
            InlineKeyboardButton("🤝 Ittifoqchilarni Chaqirish (SOS)", callback_data=f"def_sos:{territory_id}"),
        ],
        [
            InlineKeyboardButton("⚔️ Harbiy Markaz", callback_data="menu_battle"),
            InlineKeyboardButton("🔙 Bosh Menyu", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def duel_challenge_keyboard(duel_id: int) -> InlineKeyboardMarkup:
    """
    Boshqa o'yinchidan 1v1 PvP duel chaqiruvi kelganda yuboriladigan klaviatura.
    """
    buttons = [
        [
            InlineKeyboardButton(
                "⚔️ Mini App'da Duelga Kirish 🏆",
                web_app=WebAppInfo(url=get_miniapp_url("duel"))
            )
        ],
        [
            InlineKeyboardButton("⚔️ Botda Qabul Qilish", callback_data=f"pvp_acc:{duel_id}"),
            InlineKeyboardButton("❌ Rad Etish", callback_data=f"pvp_rej:{duel_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Bosh Menyu", callback_data="menu_main")
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def daily_reward_ready_keyboard() -> InlineKeyboardMarkup:
    """
    Kunlik 7 kunlik streak yoki kvestlar tayyor bo'lganda yuboriladigan eslatma.
    """
    buttons = [
        [
            InlineKeyboardButton(
                "🎁 Mini App'da Sovg'ani Olish ✨",
                web_app=WebAppInfo(url=get_miniapp_url("profile"))
            )
        ],
        [
            InlineKeyboardButton("🎁 Botda Tuhfani Olish", callback_data="claim_daily_bonus"),
            InlineKeyboardButton("📜 Vazifalar", callback_data="menu_quests"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def quiz_reminder_keyboard() -> InlineKeyboardMarkup:
    """
    Sitadel Maester viktorinasi imkoniyatlari yangilanganda yuboriladigan eslatma.
    """
    buttons = [
        [
            InlineKeyboardButton(
                "📚 Mini App'da Maester Saboqlari 🎓",
                web_app=WebAppInfo(url=get_miniapp_url("quiz"))
            )
        ],
        [
            InlineKeyboardButton("📚 Botda Viktorina Yechish", callback_data="menu_citadel"),
            InlineKeyboardButton("👑 Kengash Masalasi", callback_data="menu_council"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def bank_interest_ready_keyboard() -> InlineKeyboardMarkup:
    """
    Temir Bankda foiz daromadlari to'planganda yuboriladigan xabarnoma.
    """
    buttons = [
        [
            InlineKeyboardButton(
                "🏦 Mini App'da Foizni Yechib Olish 💰",
                web_app=WebAppInfo(url=get_miniapp_url("bank"))
            )
        ],
        [
            InlineKeyboardButton("🏦 Botda Temir Bank", callback_data="menu_bank"),
            InlineKeyboardButton("🔙 Bosh Menyu", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def guild_event_keyboard() -> InlineKeyboardMarkup:
    """
    Gildiya turniri, reydi yoki xazina e'lonlari xabarnomasi.
    """
    buttons = [
        [
            InlineKeyboardButton(
                "🛡️ Mini App'da Birodarlik Markazi ⚔️",
                web_app=WebAppInfo(url=get_miniapp_url("guild"))
            )
        ],
        [
            InlineKeyboardButton("🛡️ Botda Gildiya Menyu", callback_data="menu_guild"),
            InlineKeyboardButton("🔙 Bosh Menyu", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)
