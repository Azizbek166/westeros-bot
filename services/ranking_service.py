"""
Ranking Service - Independent of Telegram.
Provides top leaderboards for wealth, prestige, army power, castles, and houses.
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud


async def get_rankings_overview(
    session: AsyncSession,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Top reytinglar ro'yxati (Boylik, Nufuz, Armiya, Qal'alar va Xonadonlar).
    Faqat yuklangan skalyar maydonlar o'qiladi (lazy load xatolarisiz).
    """
    # 1. Top 10 Wealthy
    top_wealth_users = await crud.get_top_wealthy(session, limit=10)
    wealthy_list = []
    for rank, u in enumerate(top_wealth_users, start=1):
        h_name = u.house.name if getattr(u, "house", None) else "Mustaqil"
        h_emoji = u.house.emoji if getattr(u, "house", None) else "🛡️"
        wealthy_list.append({
            "rank": rank,
            "user_id": u.id,
            "name": u.full_name or u.username or "Lord",
            "house": f"{h_emoji} {h_name}",
            "value": u.gold or 0,
            "level": u.level or 1,
            "vip_tier": u.vip_tier or "",
        })

    # 2. Top 10 Prestige
    top_prestige_users = await crud.get_top10_prestige(session, period="all")
    prestige_list = []
    for rank, u in enumerate(top_prestige_users, start=1):
        h_name = u.house.name if getattr(u, "house", None) else "Mustaqil"
        h_emoji = u.house.emoji if getattr(u, "house", None) else "🛡️"
        prestige_list.append({
            "rank": rank,
            "user_id": u.id,
            "name": u.full_name or u.username or "Lord",
            "house": f"{h_emoji} {h_name}",
            "value": u.prestige or 0,
            "level": u.level or 1,
            "vip_tier": u.vip_tier or "",
        })

    # 3. Top 10 Armies
    detailed_armies = await crud.get_top10_armies_detailed(session)
    army_list = []
    for rank, item in enumerate(detailed_armies[:10], start=1):
        u = item.get("user")
        h = item.get("house")
        h_name = h.name if h else "Mustaqil"
        h_emoji = h.emoji if h else "🛡️"
        army_list.append({
            "rank": rank,
            "user_id": u.id if u else 0,
            "name": item.get("hero_name") or (u.full_name if u else "Lord"),
            "house": f"{h_emoji} {h_name}",
            "value": item.get("total_troops", 0),
            "level": u.level if u else 1,
            "vip_tier": u.vip_tier if u else "",
        })

    # 4. Top 10 Castles
    detailed_castles = await crud.get_top10_castles(session)
    castle_list = []
    for rank, item in enumerate(detailed_castles[:10], start=1):
        u = item.get("user")
        h = u.house if u else None
        h_name = h.name if h else "Mustaqil"
        h_emoji = h.emoji if h else "🛡️"
        c_count = item.get("castles_count", 0)
        c_score = item.get("score", 0)
        user_name = u.full_name or u.username or "Lord" if u else "Lord"
        castle_list.append({
            "rank": rank,
            "user_id": u.id if u else 0,
            "name": user_name,
            "house": f"{h_emoji} {h_name}",
            "value": c_count,
            "score": c_score,
        })

    # 5. Top 10 Houses
    top_houses = await crud.get_top_houses(session, limit=10)
    house_list = []
    for rank, h in enumerate(top_houses, start=1):
        house_list.append({
            "rank": rank,
            "house_id": h.id,
            "name": h.name,
            "emoji": h.emoji,
            "region": h.region,
            "value": h.prestige or 0,
            "gold": h.gold or 0,
        })

    # Current user's own ranking position (if user_id provided)
    my_ranks = {}
    if user_id:
        my_ranks["wealth"] = next((item["rank"] for item in wealthy_list if item["user_id"] == user_id), None)
        my_ranks["prestige"] = next((item["rank"] for item in prestige_list if item["user_id"] == user_id), None)
        my_ranks["army"] = next((item["rank"] for item in army_list if item["user_id"] == user_id), None)
        my_ranks["castles"] = next((item["rank"] for item in castle_list if item["user_id"] == user_id), None)

    return {
        "wealth": wealthy_list,
        "prestige": prestige_list,
        "army": army_list,
        "castles": castle_list,
        "houses": house_list,
        "my_ranks": my_ranks,
    }
