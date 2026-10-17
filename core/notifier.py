import logging
from datetime import datetime
from config import OWNER_ID, ADMIN_IDS, escape_md

logger = logging.getLogger(__name__)


async def notify_owner(bot_app, text: str) -> bool:
    """Bosh egaga (OWNER_ID) telegram bildirishnoma yuborish (xavfsiz va xatosiz)"""
    if not bot_app or not OWNER_ID:
        return False

    try:
        bot = getattr(bot_app, "bot", bot_app)
        await bot.send_message(
            chat_id=OWNER_ID,
            text=text,
            parse_mode="Markdown",
        )
        return True
    except Exception as e:
        logger.warning(f"Owner notify xatosi: {e}")
        return False


async def notify_admins(bot_app, text: str, parse_mode: str = "Markdown", reply_markup=None) -> int:
    """Barcha adminlarga (OWNER_ID va ADMIN_IDS) telegram bildirishnoma yuborish"""
    if not bot_app:
        return 0

    targets = set()
    if OWNER_ID:
        try:
            targets.add(int(OWNER_ID))
        except Exception:
            pass

    for adm in (ADMIN_IDS or []):
        try:
            targets.add(int(adm))
        except Exception:
            pass

    if not targets:
        return 0

    bot = getattr(bot_app, "bot", bot_app)
    sent_count = 0
    for adm_id in targets:
        try:
            await bot.send_message(
                chat_id=adm_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            sent_count += 1
        except Exception as e:
            logger.warning(f"notify_admins xatosi (admin={adm_id}): {e}")
    return sent_count


async def notify_house_group(bot_app, house_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """Xonadonning ulangan Telegram guruhiga xabarnoma yuborish (xavfsiz va xatosiz)"""
    if not bot_app or not house_id:
        return False

    try:
        from database.db import AsyncSessionLocal
        from database import models
        async with AsyncSessionLocal() as session:
            house = await session.get(models.House, house_id)
            if not house or not house.group_chat_id:
                return False
            chat_id = house.group_chat_id

        bot = getattr(bot_app, "bot", bot_app)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
            )
            return True
        except Exception as pe:
            logger.warning(f"notify_house_group parse_mode error: {pe}, retrying without parse_mode")
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=None,
            )
            return True
    except Exception as e:
        logger.warning(f"notify_house_group xatosi (house_id={house_id}): {e}")
        return False
