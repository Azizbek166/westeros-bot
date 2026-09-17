from datetime import datetime
from typing import Tuple
from database import models
from data.units_data import UNITS_DATA


def can_attack_target(attacker: models.User, territory: models.Territory) -> Tuple[bool, str]:
    """Hujum qilish mumkinligini serverda qat'iy tekshirish"""
    if not attacker or not territory:
        return False, "O'yinchi yoki hudud topilmadi."

    # O'z xonadoniga hujum qila olmaydi
    if attacker.house_id and attacker.house_id == territory.owner_house_id:
        return False, "❌ O'z xonadoningizga qarashli qal'aga hujum qila olmaysiz!"

    # Kamida 50 ta askar kerakligini tekshirish
    if attacker.army:
        tot_army = (
            attacker.army.infantry
            + attacker.army.archers
            + attacker.army.cavalry
            + attacker.army.spearmen
            + attacker.army.special_troops
        )
        if tot_army < 50:
            return False, "❌ Harbiy yurish boshlash uchun armiyangizda kamida 50 ta askar bo'lishi kerak!"

    return True, "OK"


def validate_recruitment(
    user: models.User,
    unit_type: str,
    amount: int,
) -> Tuple[bool, int, int, str]:
    """Askarlarni yollash tranzaksiyasini tekshirish"""
    if unit_type not in UNITS_DATA:
        return False, 0, 0, "Noto'g'ri askar turi."

    if amount <= 0 or amount > 50000:
        return False, 0, 0, "Noto'g'ri miqdor."

    unit_info = UNITS_DATA[unit_type]
    req_gold = unit_info["gold_cost"] * amount
    req_iron = unit_info["iron_cost"] * amount

    if user.gold < req_gold:
        return False, req_gold, req_iron, f"❌ Oltin yetarli emas! Kerak: {req_gold}, mavjud: {user.gold}"

    if user.iron < req_iron:
        return False, req_gold, req_iron, f"❌ Temir yetarli emas! Kerak: {req_iron}, mavjud: {user.iron}"

    return True, req_gold, req_iron, "OK"
