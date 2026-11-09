from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models
from config import DAILY_DUEL_LIMIT


CHAMPIONS_DATA = [
    {"id": "Arthur Dayne", "name": "🗡️ Ser Arthur Dayne (Tong Qilichi)", "desc": "Afsonaviy Qirollik soqchisi, 'Dawn' qilichi sohibi"},
    {"id": "Jaime Lannister", "name": "🦁 Ser Jaime Lannister (Qirol Qotili)", "desc": "Westerosning eng tezkor va epchil qilichbozi"},
    {"id": "Daemon Targaryen", "name": "🐉 Shahzoda Daemon Targaryen", "desc": "Dark Sister egasi, shafqatsiz jangchi"},
    {"id": "Brienne of Tarth", "name": "🛡️ Brienne of Tarth", "desc": "Matonatli, yengilmas va ulkan qalqonli jangchi"},
    {"id": "Gregor Clegane", "name": "💀 Ser Gregor Clegane (Tog')", "desc": "Og'ir sovutli, vahshiy qudrat egasi"},
    {"id": "Oberyn Martell", "name": "🐍 Oberyn Martell (Qizil Ilon)", "desc": "Zaharli nayza va chaqqon harakatlar ustasi"},
    {"id": "Barristan Selmy", "name": "👑 Ser Barristan Selmy (Jasur)", "desc": "Qirollik soqchilarining eng tajribali ritsari"},
    {"id": "Sandor Clegane", "name": "🐕 Sandor Clegane (Tog' Iti)", "desc": "Ayovsiz qilichboz va shafqatsiz jangchi"},
    {"id": "Robb Stark", "name": "🐺 Robb Stark (Yosh Bo'ri)", "desc": "Shimol Qiroli va mag'lub bo'lmas daho sarkarda"},
    {"id": "Stannis Baratheon", "name": "🦌 Stannis Baratheon (Temir Iroda)", "desc": "Ajdartoshi Hukmdori, qat'iyatli va sovuqqon sarkarda"},
    {"id": "Bronn", "name": "🗡️ Ser Bronn of the Blackwater", "desc": "Ayyor, tajribali va kutilmagan zarbalar ustasi"},
]


async def get_duel_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Duellar arenasi holati (qahramon statistikasi, kunlik limit, kutilayotgan takliflar).
    """
    user = await crud.get_user_with_relations(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return None

    await crud.check_and_reset_daily_limits(session, user)
    duel_cnt = getattr(user, "daily_duel_count", 0) or 0
    rem_duels = max(0, DAILY_DUEL_LIMIT - duel_cnt)

    hero = user.characters[0] if user.characters else None
    pending = await crud.get_pending_duels_for_user(session, user.id)

    return {
        "user_id": user.id,
        "user_gold": user.gold or 0,
        "hero": {
            "name": hero.name if hero else "Lord",
            "attack": hero.attack if hero else 50,
            "defense": hero.defense if hero else 50,
            "health": getattr(hero, "health", 100) if hero else 100,
            "level": getattr(hero, "level", 1) if hero else 1,
        },
        "duels_limit": {
            "used_today": duel_cnt,
            "remaining": rem_duels,
            "max_daily": DAILY_DUEL_LIMIT,
        },
        "pending_pvp_count": len(pending),
        "available_champions": CHAMPIONS_DATA,
        "allowed_bets": [0, 100, 250, 500],
        "tactics": [
            {"id": "heavy", "name": "🗡️ Og'ir Zarba (Heavy Strike)", "beats": "agile"},
            {"id": "parry", "name": "🛡️ Qalqonli Mudofaa (Parry)", "beats": "heavy"},
            {"id": "agile", "name": "⚡ Epchil Hamla (Agile Flank)", "beats": "parry"},
        ],
    }


async def fight_ai_champion_service(
    session: AsyncSession,
    identifier: int,
    champion_name: str,
    bet_gold: int,
    player_tactic: str
) -> Dict[str, Any]:
    """
    AI Chempionga qarshi duel jangini hisoblash.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return {"success": False, "error": "Foydalanuvchi topilmadi."}

    await crud.check_and_reset_daily_limits(session, user)
    duel_cnt = getattr(user, "daily_duel_count", 0) or 0
    if duel_cnt >= DAILY_DUEL_LIMIT:
        return {"success": False, "error": f"⛔ Bugungi duel limitingiz ({DAILY_DUEL_LIMIT}/{DAILY_DUEL_LIMIT}) tugadi!"}

    if bet_gold > 0 and (user.gold or 0) < bet_gold:
        return {"success": False, "error": f"❌ Garov uchun oltin yetarli emas! Sizda: {user.gold:,}🪙"}

    res = await crud.fight_ai_champion(
        session=session,
        user_id=user.id,
        champion_name=champion_name,
        bet_gold=bet_gold,
        player_tactic=player_tactic,
    )
    return res


async def get_pending_pvp_duels_service(
    session: AsyncSession,
    identifier: int
) -> List[Dict[str, Any]]:
    """
    Foydalanuvchiga yuborilgan kutilayotgan PvP duel takliflari ro'yxati.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        user = await crud.get_user_by_telegram_id(session, identifier)
    if not user:
        return []

    duels = await crud.get_pending_duels_for_user(session, user.id)
    res = []
    for d in duels:
        challenger = await crud.get_user_any(session, d.challenger_id)
        res.append({
            "duel_id": d.id,
            "challenger_id": d.challenger_id,
            "challenger_name": challenger.full_name if challenger else f"Lord #{d.challenger_id}",
            "bet_gold": d.bet_amount or 0,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })
    return res
