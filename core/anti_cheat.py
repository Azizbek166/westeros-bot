"""
Anti-Cheat, Fair Play & Player Protection Engine for The Iron Throne RPG.
Protects against multi-accounting, resource dumping, suspicious stat spikes,
and provides Newbie Peace Shield and Catch-Up mechanics.
"""
import time
import logging
from datetime import datetime
from typing import Tuple, Optional, Dict, Any, List
from collections import defaultdict

from database import models
from data.units_data import UNITS_DATA
from core.balance import PROTECTION, ANTI_CHEAT

logger = logging.getLogger(__name__)

# Xotirada so'nggi IP va User-Agent izlarini saqlash (Multi-account detection)
# {ip_address: {user_agent: [(telegram_id, timestamp)]}}
_ip_user_footprints: Dict[str, Dict[str, List[Tuple[int, float]]]] = defaultdict(lambda: defaultdict(list))

# So'nggi 1 soatdagi g'ayritabiiy o'sishlar hisobi
_hourly_growth_tracker: Dict[int, Dict[str, int]] = defaultdict(lambda: {"gold": 0, "last_reset": time.time()})


# ============================================================
# 1. NEWBIE PROTECTION & ATTACK VALIDATION
# ============================================================

def can_attack_target(
    attacker: models.User,
    territory: models.Territory,
    is_war_active: bool = False,
) -> Tuple[bool, str]:
    """
    Qal'aga harbiy yurish qilish mumkinligini serverda qat'iy tekshirish.
    Tinchlik qalqoni, darajalar tafovuti va xonadon qoidalarini inobatga oladi.
    """
    if not attacker or not territory:
        return False, "O'yinchi yoki hudud topilmadi."

    # 1. O'z xonadoniga hujum qila olmaydi
    if attacker.house_id and attacker.house_id == territory.owner_house_id:
        return False, "❌ O'z xonadoningizga qarashli qal'aga hujum qila olmaysiz!"

    # 2. Kamida min_attack_army_size (50 ta) askar kerak
    tot_army = 0
    if attacker.army:
        tot_army = (
            (attacker.army.infantry or 0)
            + (attacker.army.archers or 0)
            + (attacker.army.cavalry or 0)
            + (attacker.army.spearmen or 0)
            + (attacker.army.special_troops or 0)
        )
    if tot_army < 50:
        return False, "❌ Harbiy yurish boshlash uchun armiyangizda kamida 50 ta askar bo'lishi kerak!"

    # 3. Hujumchining o'zida tinchlik qalqoni bo'lsa - hujum qilganda u bekor bo'lishi haqida ogohlantirish
    # (Baza crud yurish paytida shieldni bekor qiladi)

    # 4. Agar nishon qal'a alohida o'yinchiga tegishli bo'lsa va egalik qiluvchi lord tinchlik qalqonida bo'lsa
    now = datetime.utcnow()
    conquered_by = getattr(territory, "conquered_by_user", None)
    if conquered_by:
        # Yangi o'yinchi tinchlik qalqoni (Peace Shield) tekshiruvi
        if conquered_by.peace_shield_until and conquered_by.peace_shield_until > now:
            rem_h = int((conquered_by.peace_shield_until - now).total_seconds() // 3600)
            return False, f"🛡️ Ushbu lord Tinchlik Qalqoni (Peace Shield) himoyasida! ({rem_h} soat qoldi)"

        # Darajalar tafovuti (Level Gap Protection) - agar umumiy qonli urush ketmayotgan bo'lsa
        if not is_war_active:
            att_lvl = attacker.level or 1
            def_lvl = conquered_by.level or 1
            max_gap = PROTECTION.max_level_gap_for_attack
            if (att_lvl - def_lvl) > max_gap:
                return (
                    False,
                    f"⚖️ Darajalar tafovuti juda katta! Siz ({att_lvl}-daraja) {def_lvl}-darajadagi zaifroq lordga "
                    f"hujum qila olmaysiz (Maksimal ruxsat etilgan farq: {max_gap} daraja)."
                )

    return True, "OK"


def can_attack_player(
    attacker: models.User,
    defender: models.User,
    is_war_active: bool = False,
) -> Tuple[bool, str]:
    """O'yinchi to'g'ridan-to'g'ri o'yinchiga hujum qilganda himoyani tekshirish"""
    if not attacker or not defender:
        return False, "O'yinchi topilmadi."

    if attacker.id == defender.id:
        return False, "O'zingizga hujum qila olmaysiz."

    now = datetime.utcnow()
    # Tinchlik qalqoni
    if defender.peace_shield_until and defender.peace_shield_until > now:
        rem_min = int((defender.peace_shield_until - now).total_seconds() // 60)
        return False, f"🛡️ Himoyachi Tinchlik Qalqoniga ega ({rem_min} daqiqa qoldi)!"

    # Level Gap Protection
    if not is_war_active:
        att_lvl = attacker.level or 1
        def_lvl = defender.level or 1
        max_gap = PROTECTION.max_level_gap_for_attack
        if (att_lvl - def_lvl) > max_gap:
            return (
                False,
                f"⚖️ Adolatli o'yin qoidasi: Siz ({att_lvl}-daraja) {def_lvl}-darajadagi lordga hujum qila olmaysiz."
            )

    return True, "OK"


# ============================================================
# 2. CATCH-UP BOOSTER (QUVIB YETISH TIZIMI)
# ============================================================

def get_catchup_multiplier(user_level: int, server_average_level: int = 10) -> Tuple[float, bool]:
    """
    Yangi yoki ortda qolayotgan o'yinchilar uchun catch-up bonusi.
    Agar o'yinchi darajasi server o'rtacha darajasidan 3+ daraja past bo'lsa,
    unga kunlik vazifalar va XP ga +35% bonus beriladi.
    """
    if not PROTECTION.enable_catchup_mechanic:
        return 1.0, False

    threshold = PROTECTION.catchup_level_threshold
    if (server_average_level - user_level) >= threshold:
        return PROTECTION.catchup_bonus_multiplier, True

    return 1.0, False


# ============================================================
# 3. RECRUITMENT & TRANSACTION VALIDATION
# ============================================================

def validate_recruitment(
    user: models.User,
    unit_type: str,
    amount: int,
) -> Tuple[bool, int, int, str]:
    """Askarlarni yollash tranzaksiyasini tekshirish"""
    if unit_type not in UNITS_DATA:
        return False, 0, 0, "Noto'g'ri askar turi."

    if amount <= 0 or amount > 10_000_000:
        return False, 0, 0, "Noto'g'ri miqdor (1 dan 10,000,000 gacha bo'lishi kerak)."

    unit_info = UNITS_DATA[unit_type]
    req_gold = unit_info["gold_cost"] * amount
    req_iron = unit_info["iron_cost"] * amount

    if user.gold < req_gold:
        return False, req_gold, req_iron, f"❌ Oltin yetarli emas! Kerak: {req_gold:,}, mavjud: {user.gold:,}"

    if user.iron < req_iron:
        return False, req_gold, req_iron, f"❌ Temir yetarli emas! Kerak: {req_iron:,}, mavjud: {user.iron:,}"

    return True, req_gold, req_iron, "OK"


# ============================================================
# 4. MARKET PRICING & RESOURCE DUMPING PROTECTION
# ============================================================

# Resurslarning shartli qiymat indeksi (Oltin = 3.0, Temir = 1.5, Oziq-ovqat = 0.5)
RESOURCE_VALUE_INDEX = {
    "gold": 3.0,
    "iron": 1.5,
    "food": 0.5,
}

def validate_market_trade_offer(
    offer_type: str,
    offer_amount: int,
    request_type: str,
    request_amount: int,
) -> Tuple[bool, str]:
    """
    Bozordagi sun'iy transfertlar (multi-akkauntdan asosiy akkauntga tekinga resurs o'tkazish)ni to'xtatish.
    Resurslar qiymati nisbati 0.20 dan kam yoki 5.00 dan ko'p bo'lmasligi shart.
    """
    if offer_amount <= 0 or request_amount <= 0:
        return False, "Miqdorlar 0 dan katta bo'lishi kerak."

    if offer_type not in RESOURCE_VALUE_INDEX or request_type not in RESOURCE_VALUE_INDEX:
        return False, "Noma'lum resurs turi."

    if offer_type == request_type:
        return False, "Bir xil resursni bir-biriga almashtirib bo'lmaydi."

    # Nominal qiymatlarni hisoblash
    offer_value = offer_amount * RESOURCE_VALUE_INDEX[offer_type]
    request_value = request_amount * RESOURCE_VALUE_INDEX[request_type]

    ratio = offer_value / request_value
    min_ratio = ANTI_CHEAT.min_trade_rate_ratio
    max_ratio = ANTI_CHEAT.max_trade_rate_ratio

    if ratio < min_ratio or ratio > max_ratio:
        return (
            False,
            f"❌ Bozor qoidasi: Savdo nisbati nomutanosib ({ratio:.2f})! "
            f"Resurslar qiymati o'rtasidagi farq me'yordan oshib ketgan."
        )

    return True, "OK"


# ============================================================
# 5. ABNORMAL WEALTH SPIKE DETECTION
# ============================================================

def detect_abnormal_growth(
    user_telegram_id: int,
    delta_amount: int,
    resource_type: str = "gold",
    source: str = "unknown"
) -> bool:
    """
    1 soat ichida g'ayritabiiy katta miqdorda resurs paydo bo'lishini monitoring qilish.
    Agar 100,000+ oltin anomal tarzda qo'shilsa True qaytaradi.
    """
    if delta_amount <= 0:
        return False

    now = time.time()
    user_tracker = _hourly_growth_tracker[user_telegram_id]

    if now - user_tracker["last_reset"] > 3600:
        user_tracker["gold"] = 0
        user_tracker["last_reset"] = now

    if resource_type == "gold":
        user_tracker["gold"] += delta_amount
        if user_tracker["gold"] > ANTI_CHEAT.abnormal_gold_spike_1h:
            logger.warning(
                f"[ANTI_CHEAT_ALERT] O'yinchi TG:{user_telegram_id} so'nggi 1 soatda {user_tracker['gold']:,} oltin to'pladi! "
                f"Oxirgi manba: {source}"
            )
            return True

    return False


# ============================================================
# 6. MULTI-ACCOUNT FOOTPRINT CHECK
# ============================================================

def check_multi_account_footprint(
    telegram_id: int,
    ip_address: Optional[str],
    user_agent: Optional[str],
) -> Tuple[bool, int]:
    """
    Bir xil IP va User-Agent ostida 10 daqiqa ichida bir nechta akkaunt faoliyatini tekshiradi.
    Qaytaradi: (is_suspicious, shared_accounts_count)
    """
    if not ip_address or ip_address in ("127.0.0.1", "localhost", "::1"):
        return False, 1

    ua_clean = (user_agent or "unknown")[:60]
    now = time.time()

    footprints = _ip_user_footprints[ip_address][ua_clean]
    # 10 daqiqadan eski yozuvlarni tozalash
    valid_fps = [(uid, ts) for uid, ts in footprints if now - ts < 600]
    valid_fps.append((telegram_id, now))
    _ip_user_footprints[ip_address][ua_clean] = valid_fps

    # Unikal foydalanuvchilar soni
    unique_users = set(uid for uid, _ in valid_fps)
    if len(unique_users) >= 4:
        logger.warning(
            f"[ANTI_CHEAT_MULTI] Bitta IP ({ip_address}) da 10 daqiqada {len(unique_users)} ta turli hisob aniqlandi: {unique_users}"
        )
        return True, len(unique_users)

    return False, len(unique_users)
