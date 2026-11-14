"""
Raven Messenger Service for Telegram Mini App.
Private scrolls between Lords with small postage fee.
"""
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud, models


async def get_raven_hub_data(session: AsyncSession, identifier: int) -> Optional[Dict[str, Any]]:
    """
    Qarg'alar pochtasi bosh sahifasi: Kelgan xabarlar arxivi.
    """
    user = await crud.get_user_any(session, identifier)
    if not user:
        return None

    inbox = await crud.get_inbox_ravens(session, user.id, limit=10)
    messages = []
    for r, sender_name in inbox:
        messages.append({
            "id": r.id,
            "sender_id": r.sender_id,
            "sender_name": sender_name or "Lord",
            "text": r.message or "",
            "message": r.message or "",
            "gold_attached": r.gold_attached or 0,
            "attached_gold": r.gold_attached or 0,
            "is_read": getattr(r, "is_read", True),
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "date": r.sent_at.strftime("%Y-%m-%d %H:%M") if r.sent_at else "",
        })

    return {
        "user_id": user.id,
        "user_gold": user.gold or 0,
        "raven_fee_gold": 50,
        "inbox_count": len(messages),
        "inbox": messages,
    }


async def send_raven_service(
    session: AsyncSession,
    identifier: int,
    recipient_identifier: str,
    message_text: str,
    gold_attached: int = 0,
) -> Tuple[bool, str]:
    """Qarg'a jo'natish"""
    user = await crud.get_user_any(session, identifier)
    if not user:
        return False, "Foydalanuvchi topilmadi."

    clean_text = message_text.strip()
    if not clean_text:
        return False, "Xabar matni bo'sh bo'lishi mumkin emas."

    return await crud.send_raven(
        session=session,
        sender_id=user.id,
        recipient_username_or_id=recipient_identifier.strip(),
        text=clean_text,
        gold=gold_attached,
    )
