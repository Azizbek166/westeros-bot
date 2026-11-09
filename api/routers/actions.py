"""
Action Endpoints for The Iron Throne Telegram Mini App.
Features implemented strictly one by one with atomic transactions and server-side validation.
"""
from typing import Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import models
from api.auth import get_current_player, get_db_session
import services

router = APIRouter(prefix="/api/actions", tags=["Actions"])


# ============================================================
# FEATURE 1: DAILY REWARDS & QUESTS (STREAK & ACTIVITY CHEST)
# ============================================================

class ClaimQuestRequest(BaseModel):
    quest_key: str = Field(..., description="Vazifa kodi (masalan: quiz, recruit, duel, collect_tax, grand_chest)")


class RecruitTroopsRequest(BaseModel):
    unit_type: str = Field(..., description="Askar turi: infantry, archers, cavalry, spearmen, special_troops")
    amount: int = Field(..., ge=1, le=100000, description="Yollanadigan askarlar miqdori (1 - 100,000)")


@router.get("/daily/hub")
async def get_daily_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Kunlik tuhfalar, 7 kunlik streak taqvimi va kunlik kvestlar holati.
    """
    user, _ = auth
    daily_data = await services.get_daily_hub_data(session, user.id)
    if not daily_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunlik ma'lumotlar topilmadi.")

    return {
        "success": True,
        "authenticated_telegram_id": user.telegram_id,
        "daily": daily_data
    }


@router.post("/daily/claim-streak")
async def claim_daily_streak_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    7 kunlik kirish (streak) mukofotini qabul qilish.
    Serverda takroriy bosish (double-click) va sanalar qat'iy tekshiriladi.
    """
    user, _ = auth
    ok, msg, res_data = await services.claim_daily_streak_service(session, user.id)
    
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )

    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


@router.post("/daily/claim-quest")
async def claim_daily_quest_endpoint(
    req: ClaimQuestRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Kunlik faollik vazifasi mukofotini qabul qilish.
    """
    user, _ = auth
    ok, msg, res_data = await services.claim_daily_quest_service(session, user.id, req.quest_key)
    
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )

    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


# ============================================================
# FEATURE 2: TROOP RECRUITMENT (ASKAR YOLLASH)
# ============================================================

@router.post("/military/recruit")
async def recruit_troops_endpoint(
    req: RecruitTroopsRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Qo'shin yollash: Askar turi va miqdori bo'yicha serverda balans va narxlarni atomik tekshirish.
    """
    user, _ = auth
    ok, msg, res_data = await services.recruit_troops_service(
        session=session,
        identifier=user.id,
        unit_type=req.unit_type,
        amount=req.amount
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


# ============================================================
# FEATURE 3: CASTLE TAX COLLECTION (QAL'ALARDAN O'LPON YIG'ISH)
# ============================================================

class CollectCastleTaxRequest(BaseModel):
    territory_id: int = Field(..., description="Qal'a (hudud) ID raqami")


@router.post("/castles/collect-tax")
async def collect_castle_tax_endpoint(
    req: CollectCastleTaxRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Bitta qal'adan to'plangan soatlik o'lponni yig'ib olish.
    """
    user, _ = auth
    ok, msg, res_data = await services.collect_castle_tax_service(session, user.id, req.territory_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


@router.post("/castles/collect-all-tax")
async def collect_all_castles_tax_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Barcha tayyor qal'alardan 1-bosishda bir vaqtning o'zida o'lpon yig'ib olish.
    """
    user, _ = auth
    ok, msg, res_data = await services.collect_all_castles_tax_service(session, user.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


# ============================================================
# FEATURE 4: CITADEL QUIZ & ROYAL COUNCIL QUESTS
# ============================================================

class CitadelQuizAnswerRequest(BaseModel):
    question_id: int = Field(..., ge=0, description="Savol indeksi")
    user_answer: int = Field(..., ge=0, le=5, description="Foydalanuvchi tanlagan javob indeksi")


class CouncilChoiceRequest(BaseModel):
    council_id: int = Field(..., ge=0, description="Kengash masalasi indeksi")
    user_choice: int = Field(..., ge=0, le=5, description="Foydalanuvchi tanlagan qaror indeksi")


@router.get("/quests/citadel-quiz")
async def get_citadel_quiz_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Sitadel Maester viktorinasi savoli va variantlarini olish.
    """
    user, _ = auth
    ok, msg, quiz_data = await services.get_citadel_quiz_question(session, user.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "quiz": quiz_data
    }


@router.post("/quests/citadel-quiz/answer")
async def submit_citadel_quiz_answer_endpoint(
    req: CitadelQuizAnswerRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Sitadel viktorinasi javobini tekshirish, atomik resurslarni yangilash va limitlarni oshirish.
    """
    user, _ = auth
    ok, msg, res_data = await services.submit_citadel_quiz_answer(
        session=session,
        identifier=user.id,
        question_id=req.question_id,
        user_answer=req.user_answer
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


@router.get("/quests/council")
async def get_council_question_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Qirollik Kengashi masalasini olish.
    """
    user, _ = auth
    ok, msg, council_data = await services.get_council_question(session, user.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "council": council_data
    }


@router.post("/quests/council/choice")
async def submit_council_choice_endpoint(
    req: CouncilChoiceRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Qirollik Kengashi qarorini tekshirish va mukofotlarni berish.
    """
    user, _ = auth
    ok, msg, res_data = await services.submit_council_choice(
        session=session,
        identifier=user.id,
        council_id=req.council_id,
        user_choice=req.user_choice
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


# ============================================================
# FEATURE 5: 1V1 DUELS & AI CHAMPIONS ARENA
# ============================================================

class FightAIChampionRequest(BaseModel):
    champion_name: str = Field(..., min_length=1, max_length=100, description="Chempion nomi")
    bet_gold: int = Field(0, ge=0, le=10000, description="Garov miqdori (0, 100, 250, 500)")
    player_tactic: str = Field(..., pattern=r"^(heavy|parry|agile)$", description="Jang taktikasi: heavy, parry, agile")


@router.get("/duels/hub")
async def get_duel_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Duellar arenasi bosh sahifasi (qahramon statistikasi, chempionlar ro'yxati, kunlik limit).
    """
    user, _ = auth
    hub_data = await services.get_duel_hub_data(session, user.id)
    if not hub_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Duel ma'lumotlari topilmadi."
        )
    return {
        "success": True,
        "authenticated_telegram_id": user.telegram_id,
        "duel_hub": hub_data
    }


@router.post("/duels/fight-ai")
async def fight_ai_champion_endpoint(
    req: FightAIChampionRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    AI Chempionga qarshi 1v1 duel jangini o'tkazish.
    Atomik hisob-kitob, limitlar va garov xavfsizligi ta'minlangan.
    """
    user, _ = auth
    res = await services.fight_ai_champion_service(
        session=session,
        identifier=user.id,
        champion_name=req.champion_name,
        bet_gold=req.bet_gold,
        player_tactic=req.player_tactic
    )
    if not res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.get("error", "Duel o'tkazishda xatolik yuz berdi.")
        )
    return {
        "success": True,
        "message": res.get("outcome", "Duel yakunlandi!"),
        "authenticated_telegram_id": user.telegram_id,
        "data": res
    }


# ============================================================
# FEATURE 6: IRON BANK OF BRAAVOS (BRAAVOS TEMIR BANKI)
# ============================================================

class BankAmountRequest(BaseModel):
    amount: int = Field(..., ge=1, le=50000, description="Oltin miqdori")


@router.get("/bank/hub")
async def get_bank_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Braavos Temir Banki omonat, foizlar va qarz ma'lumotlari.
    """
    user, _ = auth
    hub_data = await services.get_bank_hub_data(session, user.id)
    if not hub_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank ma'lumotlari topilmadi."
        )
    return {
        "success": True,
        "authenticated_telegram_id": user.telegram_id,
        "bank": hub_data
    }


@router.post("/bank/deposit")
async def deposit_gold_endpoint(
    req: BankAmountRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Temir Bankka omonat qo'yish (soatlik 1% daromad keltiradi).
    """
    user, _ = auth
    ok, msg, res_data = await services.deposit_gold_service(session, user.id, req.amount)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


@router.post("/bank/withdraw")
async def withdraw_deposit_endpoint(
    req: BankAmountRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Temir Bankdagi omonatdan oltin yechib olish.
    """
    user, _ = auth
    ok, msg, res_data = await services.withdraw_deposit_service(session, user.id, req.amount)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


@router.post("/bank/claim-interest")
async def claim_interest_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    To'plangan soatlik omonat foizlarini xazinaga qabul qilish.
    """
    user, _ = auth
    ok, msg, res_data = await services.claim_interest_service(session, user.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


@router.post("/bank/take-loan")
async def take_loan_endpoint(
    req: BankAmountRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Temir Bankdan kredit olish.
    """
    user, _ = auth
    ok, msg, res_data = await services.take_loan_service(session, user.id, req.amount)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


@router.post("/bank/repay-loan")
async def repay_loan_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Faol Temir Bank kreditini qaytarish.
    """
    user, _ = auth
    ok, msg, res_data = await services.repay_loan_service(session, user.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


# ============================================================
# FEATURE 7: GUILD SYSTEM & TREASURY ACTIONS
# ============================================================

class GuildDepositRequest(BaseModel):
    resource_type: str = Field(..., pattern=r"^(gold|iron)$", description="Resurs turi: gold yoki iron")
    amount: int = Field(..., ge=1, le=100000, description="O'tkaziladigan resurs miqdori")


class GuildBuffRequest(BaseModel):
    buff_type: str = Field(..., min_length=2, max_length=50, description="Buff turi (exp_boost, combat_boost va h.k.)")


@router.get("/guild/hub")
async def get_guild_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Gildiya markazi: foydalanuvchi a'zoligi, xazina, faol bufflar yoki ommaviy reyting.
    """
    user, _ = auth
    hub_data = await services.get_guild_hub_data(session, user.id)
    if not hub_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gildiya ma'lumotlari topilmadi."
        )
    return {
        "success": True,
        "authenticated_telegram_id": user.telegram_id,
        "guild_hub": hub_data
    }


@router.post("/guild/deposit")
async def deposit_guild_treasury_endpoint(
    req: GuildDepositRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Gildiya xazinasiga oltin yoki temir topshirish.
    """
    user, _ = auth
    ok, msg, res_data = await services.deposit_guild_treasury_service(
        session=session,
        identifier=user.id,
        resource_type=req.resource_type,
        amount=req.amount
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


@router.post("/guild/buff")
async def activate_guild_buff_endpoint(
    req: GuildBuffRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Gildiya xazinasi hisobidan 24 soatlik buffni yoqish (faqat rahbar yoki zobitlar uchun).
    """
    user, _ = auth
    ok, msg, res_data = await services.activate_guild_buff_service(
        session=session,
        identifier=user.id,
        buff_type=req.buff_type
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {
        "success": True,
        "message": msg,
        "authenticated_telegram_id": user.telegram_id,
        "data": res_data
    }


