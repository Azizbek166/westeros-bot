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


async def send_armies_audit_report(bot_app, target_chat_id: int = OWNER_ID) -> bool:
    """Barcha o'yinchilar, xonadonlar, armiyalar va qal'a garnizonlari to'liq auditi hisoboti"""
    from database.db import AsyncSessionLocal
    from database import models
    from sqlalchemy import select
    from core.leaderboard_engine import send_safe_telegram_chunk

    bot = getattr(bot_app, "bot", bot_app)
    if not bot or not target_chat_id:
        return False

    try:
        async with AsyncSessionLocal() as session:
            users_res = await session.execute(
                select(models.User).where(models.User.is_banned == False).order_by(models.User.id)
            )
            users = users_res.scalars().all()

            houses_res = await session.execute(select(models.House))
            houses = {h.id: h for h in houses_res.scalars().all()}

            terrs_res = await session.execute(select(models.Territory))
            all_terrs = terrs_res.scalars().all()

            lines = [
                "╔══════════════════════════════╗",
                "  📊 **VESTEROS HARBIY KUCHLARI AUDITI** ⚔️",
                "╚══════════════════════════════╝\n",
                "Barcha faol o'yinchilar, xonadonlar va qal'alar aktual holati:\n",
            ]

            active_count = 0
            for u in users:
                h = houses.get(u.house_id)
                h_name = f"{h.emoji} {h.name}" if h else "Mustaqil"

                army_res = await session.execute(select(models.Army).where(models.Army.user_id == u.id))
                army = army_res.scalar_one_or_none()
                tot_a = 0
                inf, arc, cav, sp = 0, 0, 0, 0
                if army:
                    inf = army.infantry or 0
                    arc = army.archers or 0
                    cav = army.cavalry or 0
                    sp = army.spearmen or 0
                    tot_a = inf + arc + cav + sp

                # Agar foydalanuvchida hech narsa bo'lmasa va xonadonsiz bo'lsa, auditni ortiqcha to'ldirmaymiz
                if tot_a == 0 and not u.house_id and u.telegram_id != OWNER_ID:
                    continue

                active_count += 1
                u_terrs = [t for t in all_terrs if t.conquered_by_user_id == u.id or (u.house_id and t.owner_house_id == u.house_id)]
                t_str = ""
                if u_terrs:
                    t_list = []
                    for t in u_terrs:
                        tot_g = (t.garrison_infantry or 0) + (t.garrison_archers or 0) + (t.garrison_cavalry or 0) + (t.garrison_spearmen or 0)
                        t_list.append(f"{t.name} (Garnizon: {tot_g:,})")
                    t_str = "\n     └ 🏰 " + ", ".join(t_list)

                uname = f"@{u.username}" if u.username else f"ID: `{u.telegram_id}`"
                rank_emoji = "👑" if u.rank in ["king", "commander"] or (h and h.lord_user_id == u.telegram_id) or u.telegram_id == OWNER_ID else "🛡️"

                lines.append(
                    f"{rank_emoji} **{escape_md(u.full_name)}** ({uname}) | [{escape_md(h_name)}]\n"
                    f"     ↳ ⚔️ Armiya: **{tot_a:,}** askar (🛡️{inf:,} | 🏹{arc:,} | 🐎{cav:,} | 🔱{sp:,})"
                    f"{t_str}\n"
                )

            if active_count == 0:
                lines.append("_Hozircha birorta faol armiya topilmadi._")

            full_text = "\n".join(lines)
            await send_safe_telegram_chunk(bot, target_chat_id, full_text)
            return True
    except Exception as e:
        logger.warning(f"send_armies_audit_report xatosi: {e}", exc_info=True)
        return False
