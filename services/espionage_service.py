"""
Espionage Service for Telegram Mini App.
Scout, Sabotage, and Open Gates operations with daily limits and reports.
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models


async def get_espionage_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Josuslik markazi ma'lumotlari: Kunlik limitlar, so'nggi hisobotlar.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        return None

    await crud.check_and_reset_daily_limits(session, user)
    scout_cnt = getattr(user, "daily_spy_scout_count", 0) or 0
    sabotage_cnt = getattr(user, "daily_spy_sabotage_count", 0) or 0
    gates_cnt = getattr(user, "daily_spy_gates_count", 0) or 0

    reports_db = await crud.get_user_spy_reports(session, user.id, limit=5)
    reports = []
    for r in reports_db:
        t_name = r.target_territory.name if (r.target_territory and getattr(r.target_territory, "name", None)) else f"Qal'a #{r.target_territory_id}"
        reports.append({
            "id": r.id,
            "mission_type": r.mission_type,
            "target_territory_name": t_name,
            "status": r.status,
            "gold_spent": r.gold_spent or 0,
            "report_summary": r.report_text or "",
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {
        "user_id": user.id,
        "user_gold": user.gold or 0,
        "limits": {
            "scout": {"used": scout_cnt, "max": 2, "cost": 100, "base_odds": 85},
            "sabotage": {"used": sabotage_cnt, "max": 2, "cost": 400, "base_odds": 65},
            "open_gates": {"used": gates_cnt, "max": 2, "cost": 800, "base_odds": 55},
        },
        "recent_reports": reports,
    }


async def execute_spy_mission_service(
    session: AsyncSession,
    identifier: int,
    territory_id: int,
    mission_type: str,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Josuslik amaliyotini bajarish.
    mission_type: 'scout', 'sabotage', 'open_gates'
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi.", None

    terr = await session.get(models.Territory, territory_id)
    if not terr:
        return False, "Nishon qal'a topilmadi.", None

    if user.house_id and terr.owner_house_id == user.house_id:
        return False, "O'z xonadoningiz qal'asiga josus jo'nata olmaysiz!", None

    success, report_text, rep_data = await crud.send_spy_mission(
        session=session,
        user_id=user.id,
        target_territory_id=terr.id,
        mission_type=mission_type,
    )

    clean_report = report_text.replace("*", "").replace("`", "").strip()
    return success, clean_report, rep_data
