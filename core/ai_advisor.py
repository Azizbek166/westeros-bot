"""
The Iron Throne RPG — AI Council Advisor ("Kengash Maslahatchisi") & Bug Triage Engine.
Provides intelligent, state-aware strategic guidance to players in authentic Uzbek,
with dual-mode operation (Google Gemini REST API + Westeros Heuristic Lore Engine fallback),
strict rate limiting, anti-injection safeguards, query caching, and automated bug triage.
"""
import os
import re
import time
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List

import httpx

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    AI_USER_DAILY_LIMIT,
    AI_VIP_DAILY_LIMIT,
    AI_GLOBAL_DAILY_LIMIT,
    AI_MAX_RESPONSE_TOKENS,
    AI_CACHE_TTL_SECONDS,
)

logger = logging.getLogger(__name__)

# ============================================================
# IN-MEMORY CACHE & GLOBAL DAILY RATE TRACKING
# ============================================================
# Cache: md5(normalized_query) -> (answer, timestamp)
_ai_query_cache: Dict[str, Tuple[str, float]] = {}

# Global daily request tracker: { "date_str": "YYYY-MM-DD", "count": int }
_global_daily_tracker: Dict[str, Any] = {
    "date": "",
    "count": 0,
}


def _get_today_str() -> str:
    """Toshkent vaqti (UTC+5) bo'yicha sana"""
    return (datetime.utcnow() + timedelta(hours=5)).strftime("%Y-%m-%d")


def check_and_increment_global_limit() -> bool:
    """Umumiy server kunlik byudjet chegarasini tekshirish va oshirish"""
    today = _get_today_str()
    if _global_daily_tracker["date"] != today:
        _global_daily_tracker["date"] = today
        _global_daily_tracker["count"] = 0

    if _global_daily_tracker["count"] >= AI_GLOBAL_DAILY_LIMIT:
        return False

    _global_daily_tracker["count"] += 1
    return True


def get_cached_answer(query: str) -> Optional[str]:
    """Keshlangan javobni tekshirish (TTL asosida)"""
    norm = query.strip().lower()
    h = hashlib.md5(norm.encode("utf-8")).hexdigest()
    if h in _ai_query_cache:
        ans, cached_time = _ai_query_cache[h]
        if time.time() - cached_time < AI_CACHE_TTL_SECONDS:
            return ans
        else:
            del _ai_query_cache[h]
    return None


def store_cached_answer(query: str, answer: str) -> None:
    """Javobni keshga yozish"""
    norm = query.strip().lower()
    h = hashlib.md5(norm.encode("utf-8")).hexdigest()
    _ai_query_cache[h] = (answer, time.time())
    # Kesh hajmini cheklash (maks 500 ta yozuv)
    if len(_ai_query_cache) > 500:
        oldest = min(_ai_query_cache.keys(), key=lambda k: _ai_query_cache[k][1])
        _ai_query_cache.pop(oldest, None)


# ============================================================
# MODERATION & PROMPT INJECTION DEFENSE
# ============================================================
PROFANITY_PATTERNS = [
    r"\b(jalap|sikay|sikey|am|qo[\'ʼ`]?toq|itvachcha|onangni|dalbayob|blyad|suka|xuy|pizda)\b",
    r"\b(fuck|shit|bitch|asshole|bastard|dick|cunt)\b",
]

INJECTION_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"system prompt",
    r"admin privileges",
    r"drop (database|table)",
    r"select\s+\*\s+from",
    r"menga (oltin|resurs|armiya|admin) ber",
    r"men adminman",
    r"parollarni (k[o‘o']rsat|ber)",
    r"exec\(|eval\(|<script",
]


def moderate_user_input(text: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Foydalanuvchi so'rovini tekshiradi.
    Qaytaradi: (is_safe, refusal_message, category)
    """
    cleaned = text.strip().lower()

    # 1. Haqorat va so'kinishlarni tekshirish
    for pat in PROFANITY_PATTERNS:
        if re.search(pat, cleaned, re.IGNORECASE):
            refusal = (
                "🏛️ **Buyuk Meyster:**\n"
                "Lordim, Qirollik Kengashi zallarida odob va ehtirom saqlanadi. "
                "Iltimos, Vesteros qonun-qoidalari va olijanoblikka munosib ohangda savol bering."
            )
            return False, refusal, "profanity"

    # 2. Prompt injection va buzish urinishlarini tekshirish
    for pat in INJECTION_PATTERNS:
        if re.search(pat, cleaned, re.IGNORECASE):
            refusal = (
                "🛡️ **Kengash Himoyachisi:**\n"
                "Lordim, sizning bu farmoyishingiz Qirollik Qonunlariga ziddir! "
                "Men faqat qoidalar, harbiy strategiya va rivojlanish bo'yicha maslahat beruvchi Kengash Meysteriman. "
                "O'yin xazinasi va ma'lumotlar bazasiga aralashishga hech kimning haqqi yo'q."
            )
            return False, refusal, "injection"

    return True, None, None


# ============================================================
# STATE-AWARE CONTEXT FORMATTING
# ============================================================
def format_player_context_text(player_state: Dict[str, Any]) -> str:
    """O'yinchining serverdagi joriy holatini LLM uchun matn ko'rinishida tayyorlash"""
    return (
        f"- O'yinchi / Lord: {player_state.get('username', 'Lord')}\n"
        f"- Xonadon: {player_state.get('house_name', 'Xonadonsiz')} (Kuchi: {player_state.get('house_power', 0)})\n"
        f"- Daraja: {player_state.get('level', 1)}, Unvoni: {player_state.get('title', 'Zodagon')}\n"
        f"- Xazina: {player_state.get('gold', 0):,}🪙 Oltin, {player_state.get('food', 0):,}🌾 Oziq-ovqat, {player_state.get('iron', 0):,}⛓️ Temir, {player_state.get('prestige', 0)}⭐ Shon-sharaf\n"
        f"- Armiya tarkibi: {player_state.get('infantry', 0)} Piyoda, {player_state.get('archers', 0)} Kamonchi, {player_state.get('cavalry', 0)} Otliq, {player_state.get('spearmen', 0)} Nayzador, {player_state.get('catapults', 0)} Katapulta, {player_state.get('siege_towers', 0)} Qamal minorasi\n"
        f"- Qal'alari / Hududlari: {player_state.get('castles_count', 0)} ta qal'a\n"
        f"- Ajdaho: {player_state.get('dragon_name', 'Mavjud emas')} (Daraja: {player_state.get('dragon_level', 0)}, Ochlik: {player_state.get('dragon_hunger', 0)}%)\n"
        f"- Tinchlik qalqoni: {player_state.get('shield_status', 'Qalqon yoqilmagan')}\n"
        f"- Joriy Mavsum: {player_state.get('season_number', 1)}-mavsum, To'plangan Season Ochkolari: {player_state.get('season_points', 0)} SO\n"
        f"- Bugungi faollik: Duel={player_state.get('daily_duel_count', 0)}/10, Quiz={player_state.get('daily_quiz_count', 0)}/5, Karvon={player_state.get('daily_caravan_count', 0)}/2"
    )


# ============================================================
# WESTEROS HEURISTIC LORE & STRATEGY ENGINE (FALLBACK)
# ============================================================
def generate_heuristic_advice(query: str, player_state: Dict[str, Any]) -> str:
    """
    Gemini API mavjud bo'lmaganda yoki limit yetganda
    o'yinchining real server holatiga asoslangan aqlli Vesteros maslahatchisi.
    """
    q = query.strip().lower()

    # Holat ko'rsatkichlari
    gold = player_state.get("gold", 0)
    food = player_state.get("food", 0)
    iron = player_state.get("iron", 0)
    lvl = player_state.get("level", 1)
    castles = player_state.get("castles_count", 0)
    dragon_name = player_state.get("dragon_name")
    dragon_hunger = player_state.get("dragon_hunger", 0)
    duel_cnt = player_state.get("daily_duel_count", 0)
    quiz_cnt = player_state.get("daily_quiz_count", 0)
    shield_status = player_state.get("shield_status", "")

    # 1. "NIMA QILAY?" / "KEYINGI QADAM" SAVOLLARI
    if any(k in q for k in ["nima qilay", "nima qilsam", "keyingi qadam", "maslahat ber", "qayerdan boshlay", "tavsiya"]):
        tips = []
        if food < 500:
            tips.append("🌾 **Oziq-ovqat yetishmovchiligi:** Oziq-ovqatingiz juda kam! Don tegirmonini yangilang yoki bozordan don xarid qiling, aks holda armiya ozuqasiz qoladi.")
        if iron > 1000 and player_state.get("spearmen", 0) < 50:
            tips.append("⛓️ **Temir zaxirangiz mo'l:** Xazinangizdagi temirni sarflab, Nayzadorlar (Spearmen) va Katapultalar yasang.")
        if not dragon_name or dragon_name == "Mavjud emas":
            tips.append("🐉 **Ajdaho Tuxumi:** Ajdaho uyasiga o'tib, ilk ajdaho tuxumingizni oching. Ajdaho jangga mislsiz kuch beradi.")
        elif dragon_hunger > 50:
            tips.append("🍖 **Ajdahoni Boqish:** Ajdahongiz och qolgan. Uni zudlik bilan go'sht bilan boqing!")
        if duel_cnt < 5:
            tips.append(f"⚔️ **Arenada Duel:** Bugun yana {10 - duel_cnt} ta duel qilishingiz mumkin. Bu qahramoningizga tajriba va oltin keltiradi.")
        if quiz_cnt < 3:
            tips.append("📚 **Sitadel Saboqlari:** Sitadel meysterlarining savollariga javob berib, bepul bilim va resurslar oling.")
        if castles == 0:
            tips.append("🏰 **Ilk Qal'ani Egallash:** Xaritaga qarang va bo'sh yoki kuchsiz qal'alarga marsh yuboring!")

        if not tips:
            tips.append("🛡️ **Armiya Quvvatini Oshirish:** Qal'a himoyasini kuchaytiring va ko'proq kamonchilar yollang.")
            tips.append("🌟 **Mavsum Vazifalari:** Season Pass bo'limidagi haftalik topshiriqlarni bajarib, Season ochkolarini to'plang.")

        advice_body = "\n".join([f"• {t}" for t in tips[:3]])
        return (
            f"🧙‍♂️ **Kengash Meysteri:**\n"
            f"Lordim! Joriy ahvolingizni o'rganib chiqdim (Darajangiz: {lvl}, Xazinangiz: {gold:,}🪙 Oltin):\n\n"
            f"{advice_body}\n\n"
            f"💡 *Esda tuting: To'g'ri strategiya va sabr — Temir Taxt kalitidir!*"
        )

    # 2. ARMIYA VA JANG STRATEGIYASI
    if any(k in q for k in ["armiya", "jang", "taktika", "nayzador", "otliq", "kamonchi", "katapulta", "qamal"]):
        return (
            "⚔️ **Vesteros Harbiy Taktikasi:**\n"
            "Armiyada har bir askar turining o'z ustunligi va nozik nuqtasi bor:\n\n"
            "• 🐎 **Otliqlar (Cavalry)** ➔ Kamonchilarga qiron keltiradi.\n"
            "• 🗡️ **Nayzadorlar (Spearmen)** ➔ Otliqlar hujumini sindiradi (Antikavaleriy).\n"
            "• 🏹 **Kamonchilar (Archers)** ➔ Piyodalarni masofadan yo'q qiladi.\n"
            "• 🛡️ **Piyodalar (Infantry)** ➔ Qalqon devori bilan nayzadorlarni tor-mor etadi.\n"
            "• ☄️ **Katapultalar & Qamal Minoralari** ➔ Qal'a devorlarini buzish uchun shart!\n\n"
            "💡 *Maslahat: Hech qachon faqat bitta turdagi askar bilan jangga kirmang, muvozanatli qo'shin tuzing.*"
        )

    # 3. AJDAHO STRATEGIYASI VA KUCHAYTIRISH
    if any(k in q for k in ["ajdaho", "ajdar", "jdar", "dragon", "drogon", "reyd", "tuxum", "oziq", "boqish", "parvarish", "kuchaytir"]):
        return (
            "🐉 **Ajdahoni Boqish, Parvarishlash va Kuchaytirish Sirlari:**\n"
            "Valyriyaning eng dahshatli va qudratli kuchi — bu sizning Ajdahongizdir!\n\n"
            "1. 🥚 **Tuxum ochish:** Mini App yoki botdagi «🐉 Ajdaho Uyasi» bo'limiga kiring. Tuxumga olov/issiqlik berib, uni yorib chiqing.\n"
            "2. 🍖 **Muntazam Boqish (Oziqlantirish):** Ajdahoni muntazam go'sht (oziq-ovqat) bilan boqing. Ochlik darajasini 0% ga yaqin tuting. Och qolgan ajdaho (Ochlik > 80%) jangga uchmaydi va kuchsizlanadi!\n"
            "3. ⚡ **Kuchaytirish & Mashq (Training):** Har kuni mashg'ulot o'tkazing — uning Olov Quvvati (Firepower), Darajasi (Level) va Qalqoni muttasil o'sib boradi.\n"
            "4. 🗡️ **Valyriya Artefakti:** Ajdahongizga noyob Valyriya artefaktini taqing, bu unga maxsus afsonaviy jangovar bufflar beradi.\n"
            "5. 🏰 **Qal'alar Urushi (21:00):** Qal'a qamaliga ajdahoni qo'shing. U dushman devorlarini eritib, dushman garnizonini yakson qiladi!"
        )

    # 4. IQTISOD, BANK VA BOZOR
    if any(k in q for k in ["oltin", "resurs", "bank", "kredit", "foiz", "karvon", "bozor"]):
        return (
            "💰 **Qirollik Iqtisodiyoti & Xazina:**\n"
            "Urushlarni oltin yutadi, qon emas:\n\n"
            "• 🏦 **Temir Bank:** Oltiningizni depozitga qo'ying — har kuni foiz keltiradi va talon-torojdan saqlanadi.\n"
            "• 🐪 **Savdo Karvonlari:** Shaharlararo karvon jo'nating. Qancha ko'p soqchi qo'shsangiz, foyda shuncha xavfsiz keladi.\n"
            "• 🏰 **Qal'a Soliqlari:** O'z qal'alaringizdan har bir necha soatda shaxsiy soliq yig'ib oling.\n"
            "• ⛏️ **Konlar & Tegirmonlar:** Temir koni va Don tegirmonini 10-darajagacha oshiring."
        )

    # 5. MAVSUM VA SEASON PASS
    if any(k in q for k in ["mavsum", "season", "pass", "so ", "ball", "reset"]):
        return (
            "🌟 **Mavsum (Season) & Season Pass Tizimi:**\n\n"
            "• Mavsum 6 hafta davom etadi. G'olib boylik bilan emas, **Season Ochkolari (SO)** bilan aniqlanadi.\n"
            "• SO jang g'alabalari, kunlik vazifalar, qal'alar va gildiya hissasi uchun beriladi.\n"
            "• **Season Pass:** 20 ta bosqich (Tier). Bepul va Premium yo'llarida unikal kosmetikalar va resurslar mavjud.\n"
            "• **Soft Reset:** Mavsum tugagach, reyting yangilanadi, ammo qahramon, unvonlar, skinlar va yutuqlar DOIMIY qoladi!"
        )

    # 6. GILDIYA VA ITTIFOQ
    if any(k in q for k in ["gildiya", "guild", "ittifoq", "klan"]):
        return (
            "🏛️ **Gildiyalar va Hamkorlik:**\n\n"
            "• Yakkaxon lord Vesterosda uzoq yashay olmaydi. Kuchli gildiyaga a'zo bo'ling!\n"
            "• Gildiya xazinasiga oltin va temir qo'shib, umumiy armiya bufflarini (+10% hujum, +10% mudofaa) faollashtiring.\n"
            "• 21:00 da o'tadigan Qal'alar Urushida gildiyadoshlar bilan birga qamal qiling."
        )

    # DEFAULT WESTEROS LORE GREETING
    return (
        f"🧙‍♂️ **Buyuk Meyster:**\n"
        f"Lordim, sizning xizmatingizdaman! Qirollik Kengashi sizga Vesteros qonunlari, harbiy taktikalar, "
        f"armiya balansi, ajdaho parvarishi yoki iqtisodiy rivojlanish bo'yicha yo'l ko'rsatishga doim tayyor.\n\n"
        f"Menga masalan shunday savol berishingiz mumkin:\n"
        f"• *«Hozir nima qilay?»*\n"
        f"• *«Armiyada qaysi askarni ko'proq yollay?»*\n"
        f"• *«Ajdahoni qanday kuchaytiraman?»*\n"
        f"• *«Ko'proq oltin topish sirlari qanday?»*"
    )


# ============================================================
# GEMINI REST API ADVISOR CALL
# ============================================================
async def call_gemini_advisor_api(
    user_query: str,
    player_state: Dict[str, Any],
) -> Optional[str]:
    """
    Google Gemini REST API ga to'g'ridan-to'g'ri so'rov jo'natish.
    Xavfsiz, prompt-injection izolyatsiyalangan va o'yinchining server ma'lumotlari bilan boyitilgan.
    """
    if not GEMINI_API_KEY:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

    state_text = format_player_context_text(player_state)

    system_instruction = (
        "Siz 'Iron Throne RPG' (Vesteros va Taxtlar O'yini asosidagi o'zbekcha Telegram MMORPG) "
        "o'yinining Qirollik Kengashi Bosh Maslahatchisi va Buyuk Meysterisiz.\n\n"
        "VAZIFANGIZ VA QOIDALAR:\n"
        "1. O'yinchining (Lordning) savollariga samimiy, dono, ehtiromli va o'rta asr Vesteros muhitiga mos o'zbek tilida (lotin) javob bering.\n"
        "2. O'yinchiga faqat o'yin qoidalari, rivojlanish strategiyasi, askar turlari, ajdaho parvarishi, iqtisod va qal'alar bo'yicha maslahat bering.\n"
        "3. Sizda o'yin ma'lumotlar bazasini o'zgartirish, o'yinchiga oltin/resurs berish, admin imtiyozlarini berish vakolati MUTLAQO YO'Q. "
        "Agar o'yinchi shunday narsa so'rasa, muloyim va keskin rad qiling.\n"
        "4. Har doim o'yinchining joriy ko'rsatkichlarini (resurslar, armiya, daraja) tahlil qilib, aniq va amaliy maslahat bering.\n"
        "5. Javobingiz ixcham (maksimum 120-180 so'z), lo'nda va o'qishga qulay punktlar bilan bo'lsin. Hech qachon o'ylab topilgan bema'ni qoidalarni aytmang."
    )

    clean_query = user_query[:300].strip()

    prompt_content = (
        f"O'YINCHINING JORIY HOLATI (Server ma'lumotlari):\n"
        f"{state_text}\n\n"
        f"O'YINCHINING SAVOLI:\n"
        f"<user_query>\n{clean_query}\n</user_query>\n\n"
        f"Iltimos, Buyuk Meyster sifatida unga aniq strategik maslahat bering:"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt_content}],
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "generationConfig": {
            "maxOutputTokens": AI_MAX_RESPONSE_TOKENS,
            "temperature": 0.4,
            "topP": 0.85,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        ans = parts[0]["text"].strip()
                        return ans
            else:
                logger.warning(f"Gemini API xatoligi {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Gemini API so'rovida tarmoq xatoligi: {e}")

    return None


# ============================================================
# AUTOMATED BUG REPORT CLASSIFIER (SUB-FEATURE)
# ============================================================
async def classify_bug_report(report_text: str) -> Dict[str, Any]:
    """
    O'yinchilar yuborgan nosozlik / shikoyat matnini tahlil qiladi.
    Jiddiylik darajasi (Severity) va Tizim bo'limi (Category) ni aniqlaydi.
    """
    clean_text = report_text.strip().lower()

    # Default tasnif
    severity = "MINOR"
    category = "BOSHQA"
    badge_icon = "⚪"

    # 1. CRITICAL: Baza, pul/stars, login, crash, to'lov xatosi
    if any(k in clean_text for k in ["baza", "crash", "qotib qoldi", "to'lov", "pulim ketdi", "stars", "ban", "server 500", "database"]):
        severity = "CRITICAL"
        badge_icon = "🔴"
    # 2. MAJOR: Jang hisoblanmadi, armiya yo'qoldi, resurs tushmadi
    elif any(k in clean_text for k in ["jang hisoblanmadi", "yutqazdim", "armiya yo'qoldi", "askar tushmadi", "resurs bermadi", "ishlamayapti", "ochilmadi"]):
        severity = "MAJOR"
        badge_icon = "🟡"
    # 3. FEATURE REQUEST: Taklif, yangi g'oya
    elif any(k in clean_text for k in ["taklif", "qo'shilsa", "bo'lsa zo'r bo'lardi", "yangi fikr"]):
        severity = "FEATURE_REQUEST"
        badge_icon = "💡"

    # Bo'limni aniqlash
    if any(k in clean_text for k in ["jang", "armiya", "marsh", "hujum", "duel", "askar"]):
        category = "JANG & ARMIYA"
    elif any(k in clean_text for k in ["oltin", "oziq", "temir", "bank", "karvon", "bozor", "soliq"]):
        category = "IQTISOD & RESURSLAR"
    elif any(k in clean_text for k in ["ajdaho", "dragon", "tuxum", "oziqlantirish"]):
        category = "AJDARHO"
    elif any(k in clean_text for k in ["qal'a", "shahar", "xarita", "hudud", "devor"]):
        category = "QAL'A & HUDUD"
    elif any(k in clean_text for k in ["gildiya", "ittifoq"]):
        category = "GILDIYA"
    elif any(k in clean_text for k in ["vip", "donate", "stars", "xarid", "skin"]):
        category = "TO'LOV & DONAT"
    elif any(k in clean_text for k in ["tugma", "matn", "dizayn", "mini app", "web app"]):
        category = "UI / MINI APP"

    return {
        "severity": severity,
        "category": category,
        "badge": f"{badge_icon} [{severity} | {category}]",
        "summary": f"{severity} darajali {category} murojaati",
    }
