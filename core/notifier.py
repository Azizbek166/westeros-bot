import logging
from datetime import datetime
from config import OWNER_ID, escape_md

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
