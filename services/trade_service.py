"""
P2P Marketplace & Caravans Service for Telegram Mini App.
Allows Lords to list resources for trade, fulfill trades, and dispatch/raid trade caravans.
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models


async def get_market_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Bozor va savdo markazi ma'lumotlari: Faol savdo lotlari va shaxsiy lotlar.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        return None

    active_trades = await crud.get_active_house_trades(session)
    my_trades = await crud.get_user_active_trades(session, user.id)

    market_list = []
    for t in active_trades:
        seller = t.seller
        seller_name = seller.full_name or seller.username or "Lord" if seller else "Lord"
        h = seller.house if seller else None
        h_name = h.name if h else "Mustaqil"
        h_emoji = h.emoji if h else "🛡️"

        market_list.append({
            "id": t.id,
            "seller_id": t.user_id,
            "seller_name": seller_name,
            "seller_house": f"{h_emoji} {h_name}",
            "is_my_lot": (t.user_id == user.id),
            "offer_resource": t.offer_resource,
            "offer_amount": t.offer_amount,
            "request_resource": t.request_resource,
            "request_amount": t.request_amount,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    # Faol karvonlar
    caravans = await crud.get_active_trade_caravans(session)
    caravan_list = []
    now = datetime.utcnow()
    for c in caravans:
        rem_sec = max(0, int((c.arrival_time - now).total_seconds())) if c.arrival_time else 0
        owner_uid = getattr(c, "owner_user_id", getattr(c, "user_id", 0))
        caravan_list.append({
            "id": c.id,
            "owner_id": owner_uid,
            "is_my_caravan": (owner_uid == user.id),
            "resource_type": c.resource_type,
            "resource_amount": c.resource_amount,
            "expected_profit": getattr(c, "expected_gold_reward", 0) or 0,
            "seconds_remaining": rem_sec,
            "status": getattr(c, "status", "moving"),
            "is_raided": (getattr(c, "status", "") in ("raided", "looted")),
        })

    return {
        "user_id": user.id,
        "user_gold": user.gold or 0,
        "user_food": user.food or 0,
        "user_iron": user.iron or 0,
        "market_fee_pct": 5,
        "total_active_lots": len(market_list),
        "lots": market_list,
        "my_lots_count": len(my_trades),
        "active_caravans": caravan_list,
    }


async def create_trade_lot_service(
    session: AsyncSession,
    identifier: int,
    offer_resource: str,
    offer_amount: int,
    request_resource: str,
    request_amount: int,
) -> Tuple[bool, str]:
    """Bozorga yangi resurs loti qo'yish (Anti-cheat nisbat tekshiruvi bilan)"""
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    from core.anti_cheat import validate_market_trade_offer
    is_valid, err_msg = validate_market_trade_offer(
        offer_type=offer_resource,
        offer_amount=offer_amount,
        request_type=request_resource,
        request_amount=request_amount,
    )
    if not is_valid:
        return False, err_msg

    return await crud.create_house_trade(
        session=session,
        user_id=user.id,
        offer_resource=offer_resource,
        offer_amount=offer_amount,
        request_resource=request_resource,
        request_amount=request_amount,
    )


async def buy_trade_lot_service(session: AsyncSession, identifier: int, trade_id: int) -> Tuple[bool, str]:
    """Bozordan boshqa Lordning savdo lotini sotib olish"""
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    return await crud.fulfill_house_trade(session, user.id, trade_id)


async def cancel_trade_lot_service(session: AsyncSession, identifier: int, trade_id: int) -> Tuple[bool, str]:
    """O'z savdo lotini bekor qilish va resurslarni qaytarish"""
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    return await crud.cancel_house_trade(session, user.id, trade_id)
