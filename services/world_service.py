"""
World & Events Service - Independent of Telegram.
Provides weather conditions, active realm events, and season schedule.
"""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud


async def get_world_events_overview(
    session: AsyncSession,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Vesteros dunyosi holati: Ob-havo, faol hodisalar va kunlik tadbirlar jadvali.
    """
    # 1. Ob-havo (Weather)
    try:
        weather_data = await crud.get_current_weather(session)
    except Exception:
        weather_data = {
            "name": "Mo''tadil kuz",
            "emoji": "🍂",
            "description": "Vesteros bo'ylab mayin shamol esmoqda. Qish yaqinlashmoqda.",
            "effect_army": "Normal",
            "effect_economy": "Normal",
        }

    # 2. Kunlik vaqti (Toshkent vaqti)
    now_tashkent = datetime.utcnow() + timedelta(hours=5)
    current_hour = now_tashkent.hour

    # 3. Faol va kutilayotgan tadbirlar
    events_schedule = [
        {
            "id": "morning_harvest",
            "name": "Ertalabki Hosil",
            "emoji": "🌾",
            "time": "08:00 - 09:00",
            "description": "Don tegirmonlari va qishloqlarda oziq-ovqat ishlab chiqarish +25%",
            "is_active": (8 <= current_hour < 9),
        },
        {
            "id": "caravan",
            "name": "Savdogarlar Karvoni",
            "emoji": "🐪",
            "time": "12:00 - 13:00 & 16:00 - 17:00",
            "description": "Katta savdo yo'llarida karvon qatnovi va pistirmalar vaqti",
            "is_active": (12 <= current_hour < 13) or (16 <= current_hour < 17),
        },
        {
            "id": "tourney",
            "name": "Qirollik Ritsarlar Turniri",
            "emoji": "🏇",
            "time": "18:00 - 20:00",
            "description": "Eng mohir jangchilar maydonda bellashib, shon-sharaf qozonadi",
            "is_active": (18 <= current_hour < 20),
        },
        {
            "id": "night_watch",
            "name": "Devordagi Qorovul & Ayoz",
            "emoji": "❄️",
            "time": "22:00 - 04:00",
            "description": "Oq Yuruvchilar faollashadi. Shimoliy mudofaani mustahkamlang!",
            "is_active": (current_hour >= 22 or current_hour < 4),
        },
    ]

    active_count = sum(1 for e in events_schedule if e["is_active"])

    # 4. Mavsum holati va Shon-sharaf zali (Database orqali dinamik)
    try:
        active_season = await crud.get_active_season(session)
        now_utc = datetime.utcnow()
        rem_days = 14
        s_num = active_season.season_number if active_season else 2
        if active_season and active_season.end_date:
            rem_seconds = max(0, int((active_season.end_date - now_utc).total_seconds()))
            rem_days = rem_seconds // 86400

        hall_entries = await crud.get_hall_of_fame(session, limit=5)
        hall_of_fame = []
        for h in hall_entries:
            date_str = h.concluded_at.strftime("%d.%m.%Y") if getattr(h, "concluded_at", None) else ""
            hall_of_fame.append({
                "season_number": h.season_number,
                "king_name": h.king_name or h.top_warrior_name or "Noma'lum Hukmdor",
                "winner_house": h.winner_house_name or "Mustaqil",
                "top_warrior": h.top_warrior_name or "",
                "top_warrior_prestige": getattr(h, "top_warrior_prestige", 0) or 0,
                "date": date_str,
            })

        season_data = {
            "season_number": s_num,
            "name": f"{s_num}-Mavsum: Temir Taxt Qadami",
            "status": "Faol",
            "days_left": rem_days,
            "previous_season_concluded": True,
            "hall_of_fame": hall_of_fame,
        }
    except Exception:
        season_data = {
            "season_number": 2,
            "name": "2-Mavsum: Temir Taxt Qadami",
            "status": "Faol",
            "days_left": 14,
            "previous_season_concluded": True,
            "hall_of_fame": [],
        }

    return {
        "server_time_tashkent": now_tashkent.strftime("%H:%M:%S"),
        "weather": weather_data,
        "events": events_schedule,
        "active_events_count": active_count,
        "season": season_data,
    }
