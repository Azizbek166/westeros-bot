"""
VIP & Premium Donate Service for Telegram Mini App.
Presents VIP tiers, bonuses, and subscription status.
"""
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models


VIP_TIERS_INFO = {
    "lord": {
        "name": "Lord (Zukko Hukmdor)",
        "badge": "⭐ LORD",
        "price_stars": 150,
        "price_uzs": "25,000 so'm",
        "duration_days": 30,
        "perks": [
            "⚡ O'lpon yig'ish vaqti 4 soatdan 3 soatga qisqaradi",
            "🌾 Oziq-ovqat ishlab chiqarish +15%",
            "🛡️ Mudofaa quvvati +10%",
            "💬 Chatda maxsus [LORD] belgisi",
        ],
    },
    "knight": {
        "name": "Knight (Qudratli Ritsar)",
        "badge": "🛡️ KNIGHT",
        "price_stars": 350,
        "price_uzs": "55,000 so'm",
        "duration_days": 30,
        "perks": [
            "⚡ O'lpon yig'ish vaqti 2.5 soatga tushadi",
            "🪙 Oltin va temir daromadi +20%",
            "⚔️ Harbiy yurish tezligi +25%",
            "🐉 Ajdarlar mashg'uloti uchun +15 Quvvat bonusi",
            "💬 Chatda maxsus [KNIGHT] ramzi",
        ],
    },
    "sovereign": {
        "name": "Sovereign (Imperator / Temir Taxt Sohibi)",
        "badge": "👑 SOVEREIGN",
        "price_stars": 750,
        "price_uzs": "120,000 so'm",
        "duration_days": 30,
        "perks": [
            "⚡ O'lpon yig'ish 2 soatga tushadi (Maksimal tezlik)",
            "👑 Barcha resurslar soatlik daromadi +35%",
            "⚔️ Armiya hujum va mudofaa kuchi +20%",
            "🛡️ Shaxsiy 7 kunlik Tinchlik Qalqoni uzaytirish huquqi",
            "🐉 Ajdarga kunlik bepul Valiriya go'shti",
            "👑 Chatda oltin tojli [SOVEREIGN] unvoni",
        ],
    },
}


async def get_donate_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    VIP do'koni ma'lumotlari va joriy maqom.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        return None

    current_vip = user.vip_tier or "free"
    vip_expires = getattr(user, "vip_expires_at", None)

    return {
        "user_id": user.id,
        "current_vip_tier": current_vip,
        "vip_expires_at": vip_expires.isoformat() if vip_expires else None,
        "is_vip_active": (current_vip in VIP_TIERS_INFO),
        "tiers": VIP_TIERS_INFO,
    }
