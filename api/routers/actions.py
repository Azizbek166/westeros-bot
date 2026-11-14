"""
Action Endpoints for The Iron Throne Telegram Mini App.
Features implemented strictly one by one with atomic transactions and server-side validation.
"""
from typing import Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import models
from api.auth import get_current_player, require_admin_player, get_db_session
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


# ============================================================
# HARBIY YURISH VA QAMALLAR (BATTLE MARCHES & SIEGES)
# ============================================================

class BattleMarchRequest(BaseModel):
    territory_id: int = Field(..., ge=1, description="Nishon qal'a ID si")
    percent: int = Field(50, ge=10, le=100, description="Yuboriladigan armiya ulushi foizda (10% - 100%)")
    dragon_tactic: str = Field("none", description="Ajdar taktikasi: none, aerial_support, breach_walls")


@router.get("/battle/hub")
async def get_battle_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Harbiy amaliyotlar markazi: faol yurishlar, kelayotgan hujumlar va jang hisobotlari"""
    user, _ = auth
    data = await services.get_battle_hub_data(session, user.id)
    return {"success": True, "battle_hub": data}


@router.post("/battle/march")
async def dispatch_battle_march_endpoint(
    req: BattleMarchRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Qal'aga harbiy yurish jo'natish (qamal qurollari va ajdar bilan)"""
    user, _ = auth
    ok, msg, march_data, def_tg_ids = await services.dispatch_march_service(
        session=session,
        identifier=user.id,
        territory_id=req.territory_id,
        percent=req.percent,
        dragon_tactic=req.dragon_tactic,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg, "march": march_data}


# ============================================================
# VESTEROS XARITASI (MAP & TERRITORIES)
# ============================================================

@router.get("/map/overview")
async def get_westeros_map_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Barcha 22 ta hudud va qal'alar interaktiv xaritasi"""
    user, _ = auth
    map_data = await services.get_westeros_map_data(session, user.id)
    territories_list = map_data.get("territories", []) if isinstance(map_data, dict) else []
    regions_map = map_data.get("regions", {}) if isinstance(map_data, dict) else {}
    return {
        "success": True,
        "map": map_data,
        "territories": territories_list,
        "regions": regions_map,
    }


@router.get("/map/territory/{territory_id}")
async def get_territory_scout_endpoint(
    territory_id: int,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Qal'aning jang oldidan razvedka holati"""
    user, _ = auth
    detail = await services.get_territory_scout_detail(session, user.id, territory_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Qal'a topilmadi.")
    return {"success": True, "scout": detail}


# ============================================================
# JOSUSLIK VA SABOTAJ (ESPIONAGE)
# ============================================================

class SpyMissionRequest(BaseModel):
    territory_id: int = Field(..., ge=1, description="Nishon qal'a ID si")
    mission_type: str = Field(..., pattern=r"^(scout|sabotage|open_gates)$", description="Operatsiya turi: scout, sabotage, open_gates")


@router.get("/espionage/hub")
async def get_espionage_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Josuslik markazi: kunlik limitlar va oxirgi hisobotlar"""
    user, _ = auth
    hub = await services.get_espionage_hub_data(session, user.id)
    return {"success": True, "espionage_hub": hub}


@router.post("/espionage/mission")
async def execute_spy_mission_endpoint(
    req: SpyMissionRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Dushman qal'asiga josus jo'natish"""
    user, _ = auth
    ok, msg, rep_data = await services.execute_spy_mission_service(
        session=session,
        identifier=user.id,
        territory_id=req.territory_id,
        mission_type=req.mission_type,
    )
    return {
        "success": ok,
        "message": msg,
        "report": rep_data,
    }


# ============================================================
# BUYUK XONADON (HOUSE & DYNASTY)
# ============================================================

class HouseDepositRequest(BaseModel):
    gold: Optional[int] = Field(0, ge=0, description="Oltin miqdori")
    food: Optional[int] = Field(0, ge=0, description="Oziq-ovqat miqdori")
    iron: Optional[int] = Field(0, ge=0, description="Temir miqdori")
    resource_type: Optional[str] = Field(None, description="Resurs turi: gold, iron, food")
    amount: Optional[int] = Field(0, ge=0, description="Miqdor")


@router.get("/house/hub")
async def get_house_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Xonadon saroyi, g'aznasi, a'zolari va boshqaruvi"""
    user, _ = auth
    data = await services.get_house_hub_data(session, user.id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xonadon ma'lumotlari topilmadi.")

    treasury = data.get("treasury", {}) if isinstance(data, dict) else {}
    return {
        "success": True,
        "house_hub": data,
        "house": {
            "id": data.get("house_id"),
            "name": data.get("name"),
            "emoji": data.get("emoji"),
            "region": data.get("region"),
            "motto": data.get("description"),
            "treasury_gold": treasury.get("gold", 0) if isinstance(treasury, dict) else 0,
            "treasury_iron": treasury.get("iron", 0) if isinstance(treasury, dict) else 0,
            "treasury_food": treasury.get("food", 0) if isinstance(treasury, dict) else 0,
        },
        "lord": {"full_name": str(data.get("lord_name") or "Hali saylanmagan")},
        "members": data.get("members", []),
    }


@router.post("/house/deposit")
async def deposit_house_treasury_endpoint(
    req: HouseDepositRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Xonadon umumiy g'aznasiga shaxsiy resurslarni ehson qilish"""
    user, _ = auth
    g = req.gold or 0
    f = req.food or 0
    i = req.iron or 0
    if req.amount and req.amount > 0 and req.resource_type:
        rt = req.resource_type.lower().strip()
        if rt == "gold":
            g = max(g, req.amount)
        elif rt == "iron":
            i = max(i, req.amount)
        elif rt == "food":
            f = max(f, req.amount)

    if g <= 0 and f <= 0 and i <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kamida 1 ta resurs miqdorini kiriting.")
    ok, msg = await services.deposit_to_house_treasury_service(
        session=session,
        identifier=user.id,
        gold=g,
        food=f,
        iron=i,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


# ============================================================
# QAHRAMON VA VALIRIYA ARTEFAKTLARI (HERO & ARTIFACTS)
# ============================================================

class ArtifactActionRequest(BaseModel):
    artifact_id: int = Field(..., ge=1, description="Artefakt ID si")


@router.get("/hero/hub")
async def get_hero_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Lord qahramoni va uning Valiriya anjomlari / inventari"""
    user, _ = auth
    data = await services.get_hero_hub_data(session, user.id)
    hero_dict = {
        "name": (data.get("hero_name") if data else None) or "Lord Chempioni",
        "attack": data.get("attack", 50) if data else 50,
        "defense": data.get("defense", 50) if data else 50,
        "level": data.get("level", 1) if data else 1,
        "health": data.get("health", 100) if data else 100,
    }
    return {
        "success": True,
        "hero_hub": data,
        "hero": hero_dict,
        "equipped_artifact": data.get("equipped_artifact") if data else None,
        "artifacts": data.get("inventory", []) if data else [],
    }


@router.post("/hero/equip-artifact")
async def equip_artifact_endpoint(
    req: ArtifactActionRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Artefaktni qahramonga taqish"""
    user, _ = auth
    ok, msg = await services.equip_artifact_service(session, user.id, req.artifact_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@router.post("/hero/unequip-artifact")
async def unequip_artifact_endpoint(
    req: ArtifactActionRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Artefaktni yechish"""
    user, _ = auth
    ok, msg = await services.unequip_artifact_service(session, user.id, req.artifact_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


# ============================================================
# AJDARLAR TIZIMI (DRAGONS)
# ============================================================

class ClaimDragonEggRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=32, description="Ajdar nomi")


class DragonActionRequest(BaseModel):
    dragon_id: Optional[int] = Field(None, ge=1, description="Ajdar ID si")
    food_amount: Optional[int] = Field(None, description="Ozuqa miqdori")


@router.get("/dragon/hub")
@router.get("/dragon/status")
async def get_dragon_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Ajdarlar uyasi (Dragon Roost) bosh sahifasi"""
    user, _ = auth
    data = await services.get_dragon_hub_data(session, user.id)
    first_dragon = None
    if data and data.get("dragons"):
        first_dragon = data["dragons"][0]
    return {
        "success": True,
        "dragon_hub": data,
        "dragon": first_dragon,
    }


@router.post("/dragon/claim-egg")
async def claim_dragon_egg_endpoint(
    req: ClaimDragonEggRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Ilk ajdaho tuxumini olish"""
    user, _ = auth
    ok, msg, d_info = await services.claim_starter_dragon_egg_service(session, user.id, req.name)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg, "dragon": d_info}


@router.post("/dragon/hatch")
async def hatch_dragon_endpoint(
    req: Optional[DragonActionRequest] = None,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Ajdaho tuxumini yorib go'dak ajdar olish"""
    user, _ = auth
    d_id = req.dragon_id if req else None
    ok, msg = await services.hatch_dragon_service(session, user.id, d_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@router.post("/dragon/feed")
async def feed_dragon_endpoint(
    req: Optional[DragonActionRequest] = None,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Ajdahoni oziqlantirish (Ozuqa sarflab quvvat oshirish)"""
    user, _ = auth
    d_id = req.dragon_id if req else None
    ok, msg = await services.feed_dragon_service(session, user.id, d_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@router.post("/dragon/train")
async def train_dragon_endpoint(
    req: Optional[DragonActionRequest] = None,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Ajdaho jangovar mashg'uloti"""
    user, _ = auth
    d_id = req.dragon_id if req else None
    ok, msg = await services.train_dragon_service(session, user.id, d_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


# ============================================================
# BOZOR VA SAVDO KARVONLARI (P2P MARKET & CARAVANS)
# ============================================================

class CreateTradeLotRequest(BaseModel):
    offer_resource: str = Field(..., pattern=r"^(gold|food|iron)$")
    offer_amount: int = Field(..., ge=10, le=1000000)
    request_resource: str = Field(..., pattern=r"^(gold|food|iron)$")
    request_amount: int = Field(..., ge=10, le=1000000)


class TradeLotActionRequest(BaseModel):
    trade_id: int = Field(..., ge=1)


@router.get("/market/hub")
async def get_market_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Bozor faol lotlari va karvonlar ro'yxati"""
    user, _ = auth
    data = await services.get_market_hub_data(session, user.id)
    return {"success": True, "market_hub": data}


@router.post("/market/create-lot")
async def create_trade_lot_endpoint(
    req: CreateTradeLotRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Bozorga resurs sotuvga qo'yish"""
    user, _ = auth
    if req.offer_resource == req.request_resource:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bir xil resursni almasha olmaysiz.")
    ok, msg = await services.create_trade_lot_service(
        session=session,
        identifier=user.id,
        offer_resource=req.offer_resource,
        offer_amount=req.offer_amount,
        request_resource=req.request_resource,
        request_amount=req.request_amount,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@router.post("/market/buy-lot")
async def buy_trade_lot_endpoint(
    req: TradeLotActionRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Bozordan boshqa o'yinchining lotini sotib olish"""
    user, _ = auth
    ok, msg = await services.buy_trade_lot_service(session, user.id, req.trade_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@router.post("/market/cancel-lot")
async def cancel_trade_lot_endpoint(
    req: TradeLotActionRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """O'z savdo lotini bekor qilish"""
    user, _ = auth
    ok, msg = await services.cancel_trade_lot_service(session, user.id, req.trade_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


# ============================================================
# QARG'ALAR POCHTASI (RAVEN MESSENGER)
# ============================================================

class SendRavenRequest(BaseModel):
    recipient: str = Field(..., min_length=1, description="Qabul qiluvchi username yoki Telegram ID si")
    message: str = Field(..., min_length=2, max_length=500, description="Xabar matni")
    gold_attached: int = Field(0, ge=0, description="Biriktirilgan oltin")


@router.get("/raven/hub")
async def get_raven_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Qarg'alar pochtasi bosh sahifasi va kelgan xabarlar"""
    user, _ = auth
    data = await services.get_raven_hub_data(session, user.id)
    return {"success": True, "raven_hub": data}


@router.post("/raven/send")
async def send_raven_endpoint(
    req: SendRavenRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Boshqa Lordga qarg'a orqali xat jo'natish"""
    user, _ = auth
    ok, msg = await services.send_raven_service(
        session=session,
        identifier=user.id,
        recipient_identifier=req.recipient,
        message_text=req.message,
        gold_attached=req.gold_attached,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


# ============================================================
# VIP & KOSMETIKA DO'KONI (COSMETICS & ETHICAL MONETIZATION)
# ============================================================

class EquipCosmeticRequest(BaseModel):
    item_id: str = Field(..., min_length=2, max_length=50)


class BuyCosmeticRequest(BaseModel):
    item_id: str = Field(..., min_length=2, max_length=50)
    payment_provider: str = Field("telegram_stars", max_length=30)
    idempotency_key: Optional[str] = Field(None, max_length=100)


class GiftCosmeticRequest(BaseModel):
    recipient_telegram_id: int = Field(..., ge=1)
    item_id: str = Field(..., min_length=2, max_length=50)
    payment_provider: str = Field("telegram_stars", max_length=30)
    idempotency_key: Optional[str] = Field(None, max_length=100)


class AdminRefundTransactionRequest(BaseModel):
    tx_id: int = Field(..., ge=1)


@router.get("/donate/hub")
@router.get("/cosmetics/hub")
async def get_donate_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Kosmetika do'koni, VIP imtiyozlari va o'yinchi jihozlari"""
    user, _ = auth
    data = await services.get_donate_hub_data(session, user.id)
    return {"success": True, "donate_hub": data, "cosmetics_hub": data}


@router.post("/cosmetics/equip")
async def equip_cosmetic_endpoint(
    req: EquipCosmeticRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Kosmetik buyumni taqish yoki yechish"""
    user, _ = auth
    ok, msg = await services.equip_user_cosmetic_service(session, user, req.item_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    hub_data = await services.get_donate_hub_data(session, user.id)
    return {"success": True, "message": msg, "donate_hub": hub_data}


@router.post("/cosmetics/buy")
async def buy_cosmetic_endpoint(
    req: BuyCosmeticRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Kosmetik buyumni xarid qilish (Telegram Stars / Idempotent)"""
    user, _ = auth
    ok, msg, details = await services.buy_cosmetic_service(
        session=session,
        user=user,
        item_id=req.item_id,
        payment_provider=req.payment_provider,
        idempotency_key=req.idempotency_key,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    hub_data = await services.get_donate_hub_data(session, user.id)
    return {"success": True, "message": msg, "details": details, "donate_hub": hub_data}


@router.post("/cosmetics/gift")
async def gift_cosmetic_endpoint(
    req: GiftCosmeticRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Do'stga yoki xonadon a'zosiga kosmetika sovg'a qilish"""
    user, _ = auth
    ok, msg = await services.gift_cosmetic_service(
        session=session,
        sender=user,
        recipient_telegram_id=req.recipient_telegram_id,
        item_id=req.item_id,
        payment_provider=req.payment_provider,
        idempotency_key=req.idempotency_key,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


# ============================================================
# ADMIN PANELI (ADMIN CONSOLE - PROTECTED)
# ============================================================

class AdminBanUserRequest(BaseModel):
    user_id: int = Field(..., ge=1)
    is_banned: bool = Field(...)


class AdminAdjustResourcesRequest(BaseModel):
    user_id: int = Field(..., ge=1)
    gold: int = Field(0)
    food: int = Field(0)
    iron: int = Field(0)


@router.get("/admin/dashboard")
async def get_admin_dashboard_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(require_admin_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Faqat Bosh Administratorlar uchun o'yin boshqaruv statistikasi"""
    data = await services.get_admin_dashboard_data(session)
    return {"success": True, "admin_data": data}


@router.post("/admin/ban-user")
async def admin_ban_user_endpoint(
    req: AdminBanUserRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(require_admin_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """O'yinchini bloklash yoki blokdan chiqarish"""
    ok, msg = await services.admin_set_ban_status_service(
        session=session,
        target_user_id=req.user_id,
        is_banned=req.is_banned,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@router.post("/admin/adjust-resources")
async def admin_adjust_resources_endpoint(
    req: AdminAdjustResourcesRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(require_admin_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """O'yinchiga resurs berish"""
    ok, msg = await services.admin_adjust_resources_service(
        session=session,
        target_user_id=req.user_id,
        gold=req.gold,
        food=req.food,
        iron=req.iron,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@router.get("/admin/transactions")
async def get_admin_transactions_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(require_admin_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Admin: So'nggi to'lovlar va xaridlar jurnali"""
    txs = await services.get_payment_transactions_history(session, limit=50)
    return {"success": True, "transactions": txs}


@router.post("/admin/refund")
async def post_admin_refund_endpoint(
    req: AdminRefundTransactionRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(require_admin_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Admin: Xaridni bekor qilish va pulini qaytarilgan deb belgilash"""
    admin_user, _ = auth
    ok, msg = await services.refund_payment_transaction(session, req.tx_id, admin_user.telegram_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


# ============================================================
# SEZON VA SEASON PASS (MAVSUM PASPORTI & SHON-SHARAF)
# ============================================================

class ClaimSeasonTierRequest(BaseModel):
    tier: int = Field(..., ge=1, le=20, description="Da'vo qilinayotgan tier raqami (1-20)")
    track: str = Field("free", description="'free' yoki 'premium'")


class BuySeasonPassRequest(BaseModel):
    payment_method: str = Field("stars", description="'stars' yoki 'card'")
    transaction_id: Optional[str] = Field(None, description="To'lov tranzaksiya identifikatori")


class AdminUpdateSeasonRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=150)
    theme_description: Optional[str] = Field(None)
    extend_days: Optional[int] = Field(None, ge=-30, le=90)


@router.get("/season/hub")
async def get_season_hub_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Joriy mavsum ma'lumotlari, Season Pass, SO reytingi va 20 ta tier holati"""
    user, _ = auth
    data = await services.get_season_hub_data(session, user.id)
    return {"success": True, "data": data}


@router.post("/season/claim-tier")
async def post_claim_season_tier_endpoint(
    req: ClaimSeasonTierRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Season Pass bitta tier mukofotini qabul qilish"""
    user, _ = auth
    ok, msg = await services.claim_season_pass_tier(session, user, req.tier, req.track)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@router.post("/season/claim-all")
async def post_claim_all_season_tiers_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Barcha erishilgan ochiq tier mukofotlarini bir zumda olish"""
    user, _ = auth
    count, items = await services.claim_all_available_pass_tiers(session, user)
    if count == 0:
        return {"success": True, "message": "Hozirda olinmagan yangi mukofotlar yo'q.", "claimed_count": 0}
    return {
        "success": True,
        "message": f"{count} ta tier mukofoti qabul qilindi!",
        "claimed_count": count,
        "items": items,
    }


@router.post("/season/buy-pass")
async def post_buy_season_pass_endpoint(
    req: BuySeasonPassRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Premium Season Pass xarid qilish (retroaktiv barcha o'tgan mukofotlar bilan)"""
    user, _ = auth
    ok, msg = await services.buy_premium_season_pass(
        session=session,
        user=user,
        payment_method=req.payment_method,
        telegram_charge_id=req.transaction_id,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@router.post("/admin/season/conclude")
async def post_admin_season_conclude_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(require_admin_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Admin: Mavsumni majburiy yakunlash, snapshot olish, mukofotlash va Soft-Reset"""
    ok, announcement, summary = await services.conclude_and_rollover_season(session, force=True)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=announcement)
    return {
        "success": True,
        "message": f"{summary.get('concluded_season_number')}-Mavsum muvaffaqiyatli yakunlandi va {summary.get('next_season_number')}-Mavsum boshlandi!",
        "summary": summary,
        "announcement": announcement,
    }


@router.post("/admin/season/update")
async def post_admin_season_update_endpoint(
    req: AdminUpdateSeasonRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(require_admin_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Admin: Mavsum sarlavhasi, mavzusi yoki muddatini o'zgartirish"""
    ok, msg, data = await services.admin_update_season_config(
        session=session,
        title=req.title,
        theme_description=req.theme_description,
        extend_days=req.extend_days,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg, "data": data}


# ============================================================
# FEATURE 12: AI COUNCIL ADVISOR ("KENGASH MASLAHATCHISI")
# ============================================================

class AIAskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=300, description="Kengash maslahatchisiga savol (maks 300 belgi)")


@router.get("/ai/status")
async def get_ai_status_endpoint(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Kengash Maslahatchisi uchun o'yinchi limiti va tavsiya etilgan savollar"""
    user, _ = auth
    status_data = await services.get_ai_advisor_status(session, user)
    return status_data


@router.post("/ai/ask")
async def post_ai_ask_endpoint(
    req: AIAskRequest,
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Kengash Maslahatchisiga savol berish (Server-side himoyalangan va kontekstli)"""
    user, _ = auth
    ok, answer, meta = await services.ask_council_advisor(
        session=session,
        user=user,
        query=req.query,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=answer)

    return {
        "success": True,
        "answer": answer,
        "metadata": meta,
    }





