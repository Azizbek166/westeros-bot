from typing import Optional, Dict, List, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from data.houses_data import HOUSES_DATA
from data.map_data import REGIONS_DATA, TERRITORIES_DATA


def persistent_reply_keyboard() -> ReplyKeyboardRemove:
    """Doimiy pastki klaviatura olib tashlangan - eski klaviaturalarni avtomatik tozalaydi"""
    return ReplyKeyboardRemove()



def main_menu_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    """Bosh menyu klaviaturasi (Admin tugmasi faqat ruxsat berilgan adminlar uchun chiqadi)"""
    from config import ADMIN_IDS
    buttons = [
        [
            InlineKeyboardButton("💎 VIP & Donate", callback_data="menu_donate"),
            InlineKeyboardButton("📢 Rasmiy Kanal & Guruh", callback_data="menu_community"),
        ],
        [
            InlineKeyboardButton("👤 Profil", callback_data="menu_profile"),
            InlineKeyboardButton("🏰 Xonadon", callback_data="menu_house"),
        ],
        [
            InlineKeyboardButton("⚔️ Armiya", callback_data="menu_army"),
            InlineKeyboardButton("🗺️ Xarita", callback_data="menu_map"),
        ],
        [
            InlineKeyboardButton("🛡️ Harbiy Yurish", callback_data="menu_battle"),
            InlineKeyboardButton("📜 Vazifalar", callback_data="menu_quests"),
        ],
        [
            InlineKeyboardButton("🐉 Ajdarlar", callback_data="menu_dragons"),
            InlineKeyboardButton("⚔️ Duellar (1v1)", callback_data="menu_duel"),
        ],
        [
            InlineKeyboardButton("📚 Viktorina", callback_data="menu_citadel"),
            InlineKeyboardButton("👑 Kengash", callback_data="menu_council"),
        ],
        [
            InlineKeyboardButton("🤝 Diplomatiya", callback_data="menu_diplomacy"),
            InlineKeyboardButton("🐦 Qarg'alar", callback_data="menu_raven"),
        ],
        [
            InlineKeyboardButton("🏆 Reyting", callback_data="menu_rank"),
            InlineKeyboardButton("✍️ Murojaat", callback_data="menu_support"),
        ],
        [
            InlineKeyboardButton("❄️ Oq Yuruvchilar", callback_data="menu_throne"),
            InlineKeyboardButton("🏦 Temir Bank", callback_data="menu_bank"),
        ],
        [
            InlineKeyboardButton("🌟 Mavsum & Shon-sharaf", callback_data="menu_season"),
            InlineKeyboardButton("🎖️ Qahramonlar", callback_data="menu_champions"),
        ],
        [
            InlineKeyboardButton("🕵️ Josuslik", callback_data="menu_espionage"),
            InlineKeyboardButton("🏇 Turnir & Stavka", callback_data="menu_tourney"),
        ],
        [
            InlineKeyboardButton("⚖️ Savdo Bozori", callback_data="menu_trade"),
            InlineKeyboardButton("🐪 Savdo Karvoni", callback_data="menu_caravan"),
        ],
        [
            InlineKeyboardButton("🌤️ Ob-havo", callback_data="menu_weather"),
            InlineKeyboardButton("🎁 Kunlik Tuhfalar", callback_data="menu_daily"),
        ],
    ]

    # Faqat bot egasi va ruxsat berilgan adminlar ko'ra oladi
    if user_id and user_id in ADMIN_IDS:
        buttons.append([
            InlineKeyboardButton("⚙️ Admin Paneli", callback_data="admin_panel"),
        ])

    return InlineKeyboardMarkup(buttons)



def back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Asosiy menyuga qaytish tugmasi"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")]
    ])


def regions_keyboard() -> InlineKeyboardMarkup:
    """Mintaqalar ro'yxati klaviaturasi"""
    buttons = []
    row = []
    for reg_name, reg_info in REGIONS_DATA.items():
        if reg_name == "Beyond the Wall":
            continue
        row.append(InlineKeyboardButton(f"{reg_info['emoji']} {reg_name}", callback_data=f"sel_reg:{reg_name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def houses_in_region_keyboard(region_name: str, member_counts: Optional[Dict[int, int]] = None) -> InlineKeyboardMarkup:
    """Tanlangan mintaqadagi xonadonlar ro'yxati (a'zolar soni ko'rsatiladi, max 5)"""
    buttons = []
    member_counts = member_counts or {}
    for h_code, h_info in HOUSES_DATA.items():
        if h_info["region"] == region_name and not h_info.get("is_npc", False):
            h_id = h_info.get("id", 0)
            count = member_counts.get(h_id, 0)
            count_label = f"({count}/5)" if count < 5 else "(5/5 To'lgan)"
            buttons.append([
                InlineKeyboardButton(
                    f"{h_info['emoji']} {h_info['name']} {count_label}",
                    callback_data=f"sel_house:{h_code}"
                )
            ])
    buttons.append([InlineKeyboardButton("🔙 Mintaqalarga Qaytish", callback_data="back_to_regions")])
    return InlineKeyboardMarkup(buttons)


def recruit_keyboard() -> InlineKeyboardMarkup:
    """Qo'shin yollash klaviaturasi (ixcham va qulay)"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛡️ +100 (200🪙)", callback_data="rec:infantry:100"),
            InlineKeyboardButton("🏹 +100 (300🪙)", callback_data="rec:archers:100"),
            InlineKeyboardButton("🐎 +50 (300🪙)", callback_data="rec:cavalry:50"),
        ],
        [
            InlineKeyboardButton("🗡️ +100 (200🪙)", callback_data="rec:spearmen:100"),
            InlineKeyboardButton("🔥 +25 (300🪙)", callback_data="rec:special_troops:25"),
            InlineKeyboardButton("✍️ Qo'lda Yollash", callback_data="rec_custom_menu"),
        ],
        [
            InlineKeyboardButton("🏹 Qamal Ustaxonasi", callback_data="siege_workshop_menu"),
            InlineKeyboardButton("🎖️ Bosh Qo'mondonlar", callback_data="menu_champions"),
        ],
        [
            InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")
        ],
    ])


def quests_menu_keyboard() -> InlineKeyboardMarkup:
    """Questlar bo'limi klaviaturasi"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📜 Asosiy Hikoya", callback_data="quest_main"),
            InlineKeyboardButton("⭐ Kunlik Vazifalar", callback_data="quest_daily"),
        ],
        [
            InlineKeyboardButton("🕵️ Yashirin Masalalar", callback_data="quest_secret"),
            InlineKeyboardButton("🎖️ Lavozim Topshiriqlari", callback_data="quest_rank"),
        ],
        [
            InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")
        ],
    ])


CUSTOM_HOUSE_EMOJI_PAGES = [
    # 1-sahifa: Maxluqlar, Yirtqichlar va Ajdarlar (24 ta)
    [
        "🐺", "🦁", "🐉", "🦌",
        "🦅", "🐙", "🐻", "🐗",
        "🦇", "🐍", "🦂", "🕷️",
        "🐊", "🦈", "🐎", "🐂",
        "🐏", "🦊", "🦉", "🦚",
        "🦖", "🦕", "🦄", "🐆",
    ],
    # 2-sahifa: Qurollar, Zirhlar va Jang san'ati (24 ta)
    [
        "⚔️", "🗡️", "🛡️", "🏹",
        "🔱", "🪓", "🔨", "⛏️",
        "⚡", "🔥", "❄️", "🌪️",
        "🌊", "☄️", "💀", "☠️",
        "🩸", "🏰", "🏯", "🗼",
        "👑", "💎", "⚜️", "⚓",
    ],
    # 3-sahifa: Tabiat, Fazoviy va Sehrli ramzlar (24 ta)
    [
        "☀️", "🌙", "⭐", "🪐",
        "🌲", "🌳", "🌴", "🍁",
        "🌹", "🥀", "🌺", "🌻",
        "🌾", "🍄", "🔮", "🧿",
        "🪬", "🕯️", "🎭", "🎪",
        "🕊️", "🪶", "📜", "🪙",
    ],
]


def custom_house_regions_keyboard() -> InlineKeyboardMarkup:
    """Yangi xonadon uchun mintaqa tanlash klaviaturasi"""
    buttons = []
    row = []
    for reg_name, reg_info in REGIONS_DATA.items():
        emoji = reg_info.get("emoji", "📍")
        row.append(InlineKeyboardButton(f"{emoji} {reg_name}", callback_data=f"reg_house_reg:{reg_name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def custom_house_emojis_keyboard(page: int = 1) -> InlineKeyboardMarkup:
    """Yangi xonadon gerbi/ramzini tanlash klaviaturasi (72+ ta ramz, 3 ta sahifa)"""
    total_pages = len(CUSTOM_HOUSE_EMOJI_PAGES)
    page_idx = max(0, min(page - 1, total_pages - 1))
    emojis = CUSTOM_HOUSE_EMOJI_PAGES[page_idx]

    buttons = []
    row = []
    for em in emojis:
        row.append(InlineKeyboardButton(em, callback_data=f"reg_house_emoji:{em}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Sahifalash (Pagination) tugmalari
    nav_row = []
    if page_idx > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"reg_emoji_page:{page_idx}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page_idx + 1}/{total_pages}", callback_data="noop"))
    if page_idx < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"reg_emoji_page:{page_idx + 2}"))
    buttons.append(nav_row)

    return InlineKeyboardMarkup(buttons)


def territories_keyboard(custom_territories: Optional[List[Any]] = None) -> InlineKeyboardMarkup:
    """Westeros hududlarini ko'rish klaviaturasi (yangi sulolalar qal'alari bilan)"""
    buttons = []
    row = []
    for t_code, t_info in TERRITORIES_DATA.items():
        row.append(InlineKeyboardButton(f"🏰 {t_info['name']}", callback_data=f"view_terr:{t_info['id']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if custom_territories:
        buttons.append([InlineKeyboardButton("🚩 YANGI SULOLALAR QAL'ALARI 🚩", callback_data="noop")])
        c_row = []
        for ct in custom_territories:
            c_name = getattr(ct, "castle_name", None) or getattr(ct, "name", "Qal'a")
            c_row.append(InlineKeyboardButton(f"🏰 {c_name}", callback_data=f"view_terr:{ct.id}"))
            if len(c_row) == 2:
                buttons.append(c_row)
                c_row = []
        if c_row:
            buttons.append(c_row)

    buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])
    return InlineKeyboardMarkup(buttons)
