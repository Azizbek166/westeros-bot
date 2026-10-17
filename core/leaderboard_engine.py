import logging
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from database import models, AsyncSessionLocal
from config import COMMUNITY_CHANNEL_URL, COMMUNITY_GROUP_URL, escape_md

logger = logging.getLogger(__name__)

# Rasmiy kanal va guruh manzillari
CHANNEL_CHAT_ID = "@northremembers1"
GROUP_CHAT_ID = "@northremember2"


async def generate_weekly_rankings(session: AsyncSession) -> Dict[str, Any]:
    """Haftalik barcha asosiy parametrlar bo'yicha eng kuchlilarni hisoblash"""
    # 1. TOP 5 Nufuzli Lordlar (Prestige)
    prestige_res = await session.execute(
        select(models.User)
        .where(models.User.is_banned == False)
        .order_by(desc(models.User.prestige), desc(models.User.level))
        .limit(5)
    )
    top_prestige_users = prestige_res.scalars().all()

    # 2. TOP 5 Eng Boy Lordlar (Gold)
    wealth_res = await session.execute(
        select(models.User)
        .where(models.User.is_banned == False)
        .order_by(desc(models.User.gold), desc(models.User.iron))
        .limit(5)
    )
    top_wealth_users = wealth_res.scalars().all()

    # 3. TOP 5 Qudratli Armiyalar
    armies_res = await session.execute(
        select(models.Army, models.User)
        .join(models.User, models.Army.user_id == models.User.id)
        .where(models.User.is_banned == False)
    )
    army_list = []
    for army, user in armies_res.all():
        inf = army.infantry or 0
        arc = army.archers or 0
        cav = army.cavalry or 0
        spm = army.spearmen or 0
        spc = army.special_troops or 0
        cat = army.catapults or 0
        st = army.siege_towers or 0
        total_pwr = int(inf + arc * 1.2 + cav * 2.5 + spm * 1.5 + spc * 4.0 + cat * 25.0 + st * 20.0)
        total_troops = inf + arc + cav + spm + spc
        army_list.append({
            "user": user,
            "power": total_pwr,
            "troops": total_troops,
            "special": spc,
        })
    army_list.sort(key=lambda x: x["power"], reverse=True)
    top_armies = army_list[:5]

    # 4. TOP 5 Afsonaviy Ajdarlar
    dragons_res = await session.execute(
        select(models.Dragon, models.User)
        .join(models.User, models.Dragon.user_id == models.User.id)
        .where(models.User.is_banned == False)
        .order_by(desc(models.Dragon.power), desc(models.Dragon.level))
        .limit(5)
    )
    top_dragons = []
    for dragon, user in dragons_res.all():
        top_dragons.append({
            "dragon": dragon,
            "user": user,
        })

    # 5. TOP 3 Buyuk Xonadonlar (Nazorat qilinayotgan hududlar va a'zolar nufuzi)
    houses_res = await session.execute(select(models.House))
    houses = houses_res.scalars().all()
    house_stats = []
    for h in houses:
        # Hududlar soni
        terr_cnt_res = await session.execute(
            select(func.count(models.Territory.id)).where(models.Territory.owner_house_id == h.id)
        )
        terr_cnt = terr_cnt_res.scalar() or 0

        # A'zolar va nufuz
        m_res = await session.execute(
            select(func.count(models.User.id), func.sum(models.User.prestige))
            .where(models.User.house_id == h.id, models.User.is_banned == False)
        )
        m_row = m_res.first()
        member_cnt = m_row[0] or 0
        sum_prestige = m_row[1] or 0
        total_score = (terr_cnt * 500) + sum_prestige

        house_stats.append({
            "house": h,
            "territories": terr_cnt,
            "members": member_cnt,
            "prestige": sum_prestige,
            "score": total_score,
        })
    house_stats.sort(key=lambda x: x["score"], reverse=True)
    top_houses = house_stats[:3]

    # Hafta MVPsi: Nufuz va armiyada birinchi o'rindagi yetakchi
    mvp_user = top_prestige_users[0] if top_prestige_users else (top_wealth_users[0] if top_wealth_users else None)

    return {
        "top_prestige": top_prestige_users,
        "top_wealth": top_wealth_users,
        "top_armies": top_armies,
        "top_dragons": top_dragons,
        "top_houses": top_houses,
        "mvp": mvp_user,
        "generated_at": datetime.utcnow(),
    }


def format_weekly_leaderboard_post(data: Dict[str, Any]) -> str:
    """Rasmiy Telegram kanal va guruh uchun e'lon matnini tayyorlash"""
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    now_str = datetime.utcnow().strftime("%d.%m.%Y")

    lines = [
        "╔══════════════════════════════╗",
        "  👑 **WESTEROS BUYUK HAFTALIK REYTINGI** 🏆",
        "╚══════════════════════════════╝\n",
        f"📅 **Sana:** `{now_str}`",
        "Qirollik Saroyi va Temir Bank tomonidan Vesteros bo'yicha yakunlangan haftaning eng qudratli hukmdorlari va xonadonlari e'lon qilindi!\n",
    ]

    # 1. Nufuz
    lines.append("🏆 **TOP 5 ENG NUFUZLI LORDLAR:**")
    if data["top_prestige"]:
        for idx, u in enumerate(data["top_prestige"]):
            med = medals[idx] if idx < len(medals) else "▫️"
            uname = u.username or u.full_name or "Lord"
            vip_icon = "👑" if u.vip_tier == "sovereign" else ("🐉" if u.vip_tier == "dragonlord" else ("🏰" if u.vip_tier == "lord" else ""))
            lines.append(f"{med} **{uname}** {vip_icon} — `{u.prestige:,}` Nufuz | Lv.{u.level}")
    else:
        lines.append("_Hozircha ma'lumotlar yo'q_")
    lines.append("")

    # 2. Armiya
    lines.append("⚔️ **TOP 5 ENG QUDRATLI ARMIYALAR:**")
    if data["top_armies"]:
        for idx, entry in enumerate(data["top_armies"]):
            med = medals[idx] if idx < len(medals) else "▫️"
            u = entry["user"]
            uname = u.username or u.full_name or "Lord"
            lines.append(f"{med} **{uname}** — `{entry['troops']:,}` Askar (Jang kuchi: `{entry['power']:,}`⚡)")
    else:
        lines.append("_Hozircha armiya ma'lumotlari yo'q_")
    lines.append("")

    # 3. Boylik
    lines.append("💰 **TOP 5 ENG BOY LORDLAR:**")
    if data["top_wealth"]:
        for idx, u in enumerate(data["top_wealth"]):
            med = medals[idx] if idx < len(medals) else "▫️"
            uname = u.username or u.full_name or "Lord"
            lines.append(f"{med} **{uname}** — `{u.gold:,}`🪙 Oltin | `{u.food:,}`🌾 Oziq")
    else:
        lines.append("_Hozircha xazina ma'lumotlari yo'q_")
    lines.append("")

    # 4. Ajdarlar
    if data["top_dragons"]:
        lines.append("🐉 **TOP 5 AFSONAVIY AJDARLAR:**")
        for idx, entry in enumerate(data["top_dragons"]):
            med = medals[idx] if idx < len(medals) else "▫️"
            d = entry["dragon"]
            u = entry["user"]
            uname = u.username or u.full_name or "Lord"
            lines.append(f"{med} **{d.name}** (`{d.power:,}` quvvat) — Egasi: *{uname}* (Lv.{d.level})")
        lines.append("")

    # 5. Xonadonlar
    lines.append("🏰 **TOP 3 ENG KUCHLI BUYUK XONADONLAR:**")
    if data["top_houses"]:
        for idx, h_info in enumerate(data["top_houses"]):
            med = medals[idx] if idx < len(medals) else "▫️"
            h = h_info["house"]
            lines.append(f"{med} **{h.emoji} {h.name}** — `{h_info['territories']}` ta Hudud | `{h_info['members']}` ta Lord (`{h_info['prestige']:,}` P)")
    lines.append("")

    # MVP
    if data.get("mvp"):
        mvp = data["mvp"]
        mvp_name = mvp.username or mvp.full_name or "Lord"
        mvp_title = f" «{mvp.title}»" if getattr(mvp, "title", None) else ""
        lines.append("───────────────────────────────")
        lines.append(f"🌟 **HAFTA QAHRAMONI (WEEKLY MVP):**")
        lines.append(f"👑 **{mvp_name}**{mvp_title}")
        lines.append(f"Qahramonga Vesteros qiroli nomidan +100 Nufuz va sharaf beriladi!")
        lines.append("───────────────────────────────\n")

    lines.append("⚔️ Taxt sari shafqatsiz kurash davom etadi! O'z xonadoningiz bayrog'ini baland ko'taring!")
    lines.append(f"🎮 **O'yin boti:** @ironthrone_rpgbot")
    lines.append(f"💬 **Rasmiy Guruh:** {COMMUNITY_GROUP_URL}")
    lines.append(f"📢 **Rasmiy Kanal:** {COMMUNITY_CHANNEL_URL}")

    return "\n".join(lines)


async def broadcast_weekly_leaderboard(bot_app, force: bool = False) -> Tuple[bool, str]:
    """Haftalik TOP reytingni kanal va guruhga e'lon qilish"""
    if not bot_app:
        return False, "bot_app mavjud emas."

    bot = getattr(bot_app, "bot", bot_app)

    async with AsyncSessionLocal() as session:
        # Haftada faqat 1 marta yuborilishi (force bo'lmasa)
        now = datetime.utcnow()
        week_key = f"weekly_board_{now.strftime('%Y_%W')}"

        if not force:
            evt_res = await session.execute(
                select(models.EventState).where(models.EventState.event_name == week_key)
            )
            already_done = evt_res.scalar_one_or_none()
            if already_done:
                return False, "Ushbu hafta uchun reyting allaqachon e'lon qilingan."

        data = await generate_weekly_rankings(session)
        post_text = format_weekly_leaderboard_post(data)

        # Hafta MVP siga 100 nufuz berish
        if data.get("mvp"):
            mvp_user = await session.get(models.User, data["mvp"].id)
            if mvp_user:
                mvp_user.prestige = (mvp_user.prestige or 0) + 100

        # E'lon qilinganligini belgilash
        if not force:
            ev = models.EventState(event_name=week_key, current_value=now.strftime("%Y-%m-%d %H:%M:%S"))
            session.add(ev)

        await session.commit()

    # Kanal va Guruhga yuborish
    sent_targets = []
    errors = []

    # 1. Rasmiy Kanalga yuborish
    for target in [CHANNEL_CHAT_ID, GROUP_CHAT_ID]:
        try:
            await bot.send_message(
                chat_id=target,
                text=post_text,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            sent_targets.append(target)
        except Exception as e:
            logger.warning(f"Kanal/Guruh {target} ga haftalik reyting yuborishda xatolik: {e}")
            errors.append(f"{target}: {e}")

    summary = f"Haftalik reyting yuborildi: {', '.join(sent_targets)}."
    if errors:
        summary += f" Xatolar: {'; '.join(errors)}"
    return bool(sent_targets), summary
