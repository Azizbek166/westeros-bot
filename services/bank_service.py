from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models


async def get_bank_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Braavos Temir Banki omonat, foizlar va qarz holati to'liq ko'rinishi.
    """
    user = await crud.get_user_with_relations(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return None

    bank = await crud.get_or_create_iron_bank(session, user.id)

    dep_gold = bank.deposit_gold or 0
    hourly_yield = int(dep_gold * crud.HOURLY_INTEREST_RATE)

    now = datetime.utcnow()
    last_claim = bank.last_interest_claimed_at or bank.deposit_updated_at or now
    elapsed_sec = max(0, (now - last_claim).total_seconds())
    hours_ready = int(elapsed_sec // 3600)
    raw_accumulated = dep_gold * crud.HOURLY_INTEREST_RATE * hours_ready if hours_ready >= 1 else 0
    accumulated_interest = int(raw_accumulated)
    if accumulated_interest <= 0 and raw_accumulated >= 0.25:
        accumulated_interest = 1
    mins_left = max(1, int((3600 - (elapsed_sec % 3600)) // 60))

    loan_gold = bank.loan_gold or 0
    total_loan_due = int(loan_gold * 1.10) if loan_gold > 0 else 0
    loan_days_left = 0
    loan_hours_left = 0
    is_overdue = False

    if loan_gold > 0 and bank.loan_due_at:
        diff_sec = (bank.loan_due_at - now).total_seconds()
        if diff_sec > 0:
            loan_days_left = int(diff_sec // 86400)
            loan_hours_left = int((diff_sec % 86400) // 3600)
        else:
            is_overdue = True
            # Agar muddat o'tgan bo'lsa va reyd qilinmagan bo'lsa
            if not bank.last_golden_company_raid_at:
                await crud.execute_golden_company_debt_raid(session, bank)
                await session.refresh(bank)
                await session.refresh(user)
                loan_gold = bank.loan_gold or 0
                total_loan_due = int(loan_gold * 1.10) if loan_gold > 0 else 0

    return {
        "user_id": user.id,
        "user_gold": user.gold or 0,
        "deposit": {
            "current_gold": dep_gold,
            "max_deposit": 50000,
            "max_can_add": max(0, 50000 - dep_gold),
            "hourly_interest_rate_pct": 1.0,
            "hourly_yield": hourly_yield,
            "accumulated_interest": accumulated_interest,
            "hours_accumulated": hours_ready,
            "next_interest_in_minutes": mins_left,
        },
        "loan": {
            "principal_gold": loan_gold,
            "total_due_gold": total_loan_due,
            "interest_rate_pct": 10.0,
            "is_active": loan_gold > 0,
            "is_overdue": is_overdue,
            "days_left": loan_days_left,
            "hours_left": loan_hours_left,
            "due_at": bank.loan_due_at.isoformat() if bank.loan_due_at else None,
            "last_raid_at": bank.last_golden_company_raid_at.isoformat() if bank.last_golden_company_raid_at else None,
        },
    }


async def deposit_gold_service(
    session: AsyncSession,
    identifier: int,
    amount: int
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Temir Bankka omonat qo'yish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    ok, msg = await crud.deposit_to_iron_bank(session, user.telegram_id, amount)
    bank = await crud.get_or_create_iron_bank(session, user.id)
    return ok, msg, {
        "user_gold": user.gold,
        "deposit_gold": bank.deposit_gold or 0,
    }


async def withdraw_deposit_service(
    session: AsyncSession,
    identifier: int,
    amount: int
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Temir Bankdagi omonatni yechib olish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    ok, msg = await crud.withdraw_from_iron_bank(session, user.telegram_id, amount)
    bank = await crud.get_or_create_iron_bank(session, user.id)
    return ok, msg, {
        "user_gold": user.gold,
        "deposit_gold": bank.deposit_gold or 0,
    }


async def claim_interest_service(
    session: AsyncSession,
    identifier: int
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    To'plangan foiz daromadini hamyonga qabul qilish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    ok, msg = await crud.claim_iron_bank_interest(session, user.telegram_id)
    return ok, msg, {
        "user_gold": user.gold,
    }


async def take_loan_service(
    session: AsyncSession,
    identifier: int,
    amount: int
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Temir Bankdan kredit olish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    ok, msg = await crud.take_iron_bank_loan(session, user.telegram_id, amount)
    bank = await crud.get_or_create_iron_bank(session, user.id)
    return ok, msg, {
        "user_gold": user.gold,
        "loan_gold": bank.loan_gold or 0,
    }


async def repay_loan_service(
    session: AsyncSession,
    identifier: int
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Temir Bank qarzini qaytarish.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", {}

    ok, msg = await crud.repay_iron_bank_loan(session, user.telegram_id)
    bank = await crud.get_or_create_iron_bank(session, user.id)
    return ok, msg, {
        "user_gold": user.gold,
        "loan_gold": bank.loan_gold or 0,
    }
