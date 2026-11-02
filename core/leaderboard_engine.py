import logging
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from database import models, AsyncSessionLocal, crud
from config import (
    COMMUNITY_CHANNEL_URL,
    COMMUNITY_GROUP_URL,
    COMMUNITY_CHANNEL_ID,
    COMMUNITY_GROUP_ID,
    escape_md,
)

logger = logging.getLogger(__name__)

CHANNEL_CHAT_ID = COMMUNITY_CHANNEL_ID
GROUP_CHAT_ID = COMMUNITY_GROUP_ID
MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


async def generate_weekly_rankings(session: AsyncSession) -> Dict[str, Any]:
    """Haftalik barcha asosiy parametrlar bo'yicha TOP 10 natijalarni hisoblash"""
    # 1. TOP 10 Haftalik Nufuzli Lordlar (Weekly Prestige)
    top_prestige_users = await crud.get_top10_prestige(session, period="weekly")

    # 2. TOP 10 Eng Tajribali Lordlar (XP va Daraja)
    top_xp_users = await crud.get_top10_xp(session)

    # 3. TOP 10 Haftalik Eng Boy Lordlar (Weekly Gold Earned)
    top_wealth_users = await crud.get_top10_wealth(session, period="weekly")

    # 3. TOP 10 Qudratli Armiyalar
    top_armies = await crud.get_top10_armies_detailed(session)

    # 4. TOP 10 Afsonaviy Ajdarlar
    top_dragons = await crud.get_top10_dragons(session)

    # 5. TOP 5 Buyuk Xonadonlar (Hududlar va a'zolar nufuzi)
    houses_res = await session.execute(select(models.House))
    houses = houses_res.scalars().all()
    house_stats = []
    for h in houses:
        terr_cnt_res = await session.execute(
            select(func.count(models.Territory.id)).where(models.Territory.owner_house_id == h.id)
        )
        terr_cnt = terr_cnt_res.scalar() or 0

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
    top_houses = house_stats[:5]

    # 6. Mavsum G'olibi / Temir Taxt Nomzodi
    champ = await crud.get_season_champion_candidate(session)

    # Hafta MVPsi: Haftalik nufuzda 1-o'rindagi lord
    mvp_user = top_prestige_users[0] if top_prestige_users else (top_wealth_users[0] if top_wealth_users else None)

    return {
        "top_prestige": top_prestige_users,
        "top_xp": top_xp_users,
        "top_wealth": top_wealth_users,
        "top_armies": top_armies,
        "top_dragons": top_dragons,
        "top_houses": top_houses,
        "champion": champ,
        "mvp": mvp_user,
        "generated_at": datetime.utcnow(),
    }


def format_weekly_leaderboard_parts(data: Dict[str, Any]) -> List[str]:
    """Haftalik reytingni Telegram 4096 belgilik chekloviga mos 2 ta xavfsiz qismga ajratish"""
    now_str = datetime.utcnow().strftime("%d.%m.%Y")

    # 1-QISM: TOP LORDLAR (NUFUZ, TAJRIBA VA BOYLIK)
    part1_lines = [
        "╔══════════════════════════════╗",
        "  👑 **WESTEROS HAFTALIK REYTINGI (1-QISM)** 🏆",
        "╚══════════════════════════════╝\n",
        f"📅 **Sana:** `{now_str}`",
        "Qirollik Saroyi va Temir Bank tomonidan yakunlangan haftaning eng qudratli hukmdorlari e'lon qilindi!\n",
        "🏆 **HAFTALIK TOP 10 NUFUZLI LORDLAR:**"
    ]
    if data.get("top_prestige"):
        for idx, u in enumerate(data["top_prestige"][:10]):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            hero_name = escape_md(u.characters[0].name if getattr(u, "characters", None) and len(u.characters) > 0 else u.full_name)
            uname = f" (@{escape_md(u.username)})" if getattr(u, "username", None) else ""
            h_str = f"[{u.house.emoji} {escape_md(u.house.name)}]" if u.house else "[Mustaqil]"
            pts = getattr(u, "weekly_prestige_earned", 0) or 0
            part1_lines.append(f"{med} **{hero_name}**{uname} {h_str}\n     ↳ **+{pts:,} 🏆** bu hafta | Jami: `{u.prestige:,}` Nufuz")
    else:
        part1_lines.append("_Hozircha ma'lumotlar yo'q_")
    part1_lines.append("")

    part1_lines.append("🌟 **TOP 10 ENG TAJRIBALI LORDLAR (DARAJA VA XP):**")
    if data.get("top_xp"):
        from core.leveling import LEVEL_TITLES
        for idx, u in enumerate(data["top_xp"][:10]):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            hero_name = escape_md(u.characters[0].name if getattr(u, "characters", None) and len(u.characters) > 0 else u.full_name)
            uname = f" (@{escape_md(u.username)})" if getattr(u, "username", None) else ""
            h_str = f"[{u.house.emoji} {escape_md(u.house.name)}]" if u.house else "[Mustaqil]"
            lvl = u.level or 1
            xp = u.xp or 0
            lvl_title = LEVEL_TITLES.get(lvl, {}).get("title", f"Lord Lv.{lvl}")
            part1_lines.append(f"{med} **{hero_name}**{uname} {h_str}\n     ↳ **{lvl}-daraja** (`{xp:,} XP`) | *{lvl_title}*")
    else:
        part1_lines.append("_Hozircha ma'lumotlar yo'q_")
    part1_lines.append("")

    part1_lines.append("💰 **HAFTALIK TOP 10 ENG KO'P OLTIN TOPGAN LORDLAR:**")
    if data.get("top_wealth"):
        for idx, u in enumerate(data["top_wealth"][:10]):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            hero_name = escape_md(u.characters[0].name if getattr(u, "characters", None) and len(u.characters) > 0 else u.full_name)
            uname = f" (@{escape_md(u.username)})" if getattr(u, "username", None) else ""
            h_str = f"[{u.house.emoji} {escape_md(u.house.name)}]" if u.house else "[Mustaqil]"
            gold_pts = getattr(u, "weekly_gold_earned", 0) or 0
            part1_lines.append(f"{med} **{hero_name}**{uname} {h_str}\n     ↳ **+{gold_pts:,} 🪙** bu hafta | Xazina: `{u.gold:,}` 🪙")
    else:
        part1_lines.append("_Hozircha xazina ma'lumotlari yo'q_")

    # 2-QISM: HARBIY KUCHLAR, AJDARLAR, XONADONLAR VA TEMIR TAXT
    part2_lines = [
        "╔══════════════════════════════╗",
        "  ⚔️ **WESTEROS HAFTALIK REYTINGI (2-QISM)** 🏆",
        "╚══════════════════════════════╝\n",
        "⚔️ **TOP 5 ENG QUDRATLI ARMIYALAR:**"
    ]
    if data.get("top_armies"):
        for idx, entry in enumerate(data["top_armies"][:5]):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            u = entry["user"]
            hero_name = escape_md(u.characters[0].name if getattr(u, "characters", None) and len(u.characters) > 0 else u.full_name)
            part2_lines.append(f"{med} **{hero_name}** — `{entry['total_troops']:,}` Askar (Jang kuchi: `{entry['power']:,}` ⚡)")
    else:
        part2_lines.append("_Hozircha armiya ma'lumotlari yo'q_")
    part2_lines.append("")

    if data.get("top_dragons"):
        part2_lines.append("🐉 **TOP 5 AFSONAVIY AJDARLAR:**")
        for idx, entry in enumerate(data["top_dragons"][:5]):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            d = entry["dragon"]
            u = entry["user"]
            part2_lines.append(f"{med} 🐲 **{escape_md(d.name)}** (`{d.power:,}` quvvat) — Egasi: *{escape_md(u.full_name)}* (Lv.{d.level})")
        part2_lines.append("")

    part2_lines.append("🏰 **TOP 5 ENG KUCHLI BUYUK XONADONLAR:**")
    if data.get("top_houses"):
        for idx, h_info in enumerate(data["top_houses"][:5]):
            med = MEDALS[idx] if idx < len(MEDALS) else f"{idx+1}."
            h = h_info["house"]
            part2_lines.append(f"{med} **{h.emoji} {escape_md(h.name)}** — `{h_info['territories']}` ta Hudud | `{h_info['members']}` ta Lord (`{h_info['prestige']:,}` P)")
    part2_lines.append("")

    champ = data.get("champion", {})
    if champ.get("user"):
        c_u = champ["user"]
        c_h = champ.get("house")
        h_name = f"{c_h.emoji} {escape_md(c_h.name)}" if c_h else "Mustaqil"
        how = "🏰 King's Landing qal'asi sohibi!" if champ.get("kings_landing_held") else f"📊 Mavsum Balli: `{champ.get('score', 0):,}`"
        part2_lines.append("───────────────────────────────")
        part2_lines.append("👑 **TEMIR TAXTNING JORIY SOHIBI (MAVSUM G'OLIBI):**")
        part2_lines.append(f"🏰 Hukmdor: **{escape_md(c_u.full_name)}** ({h_name})")
        part2_lines.append(f"📌 Holat: {how}")
        part2_lines.append("───────────────────────────────\n")

    if data.get("mvp"):
        mvp = data["mvp"]
        mvp_name = escape_md(mvp.username or mvp.full_name or "Lord")
        part2_lines.append("🎖️ **HAFTA QAHRAMONI (WEEKLY MVP):**")
        part2_lines.append(f"👑 **{mvp_name}**")
        part2_lines.append("Qahramonga Vesteros saroyi nomidan **+100 🏆 Nufuz** va **+2,500 🪙 Oltin** berildi!\n")

    part2_lines.append("⚔️ Taxt sari shafqatsiz kurash davom etadi! O'z xonadoningiz bayrog'ini baland ko'taring!")
    part2_lines.append(f"🎮 **O'yin boti:** @ironthrone_rpgbot")
    part2_lines.append(f"💬 **Rasmiy Guruh:** {COMMUNITY_GROUP_URL}")
    part2_lines.append(f"📢 **Rasmiy Kanal:** {COMMUNITY_CHANNEL_URL}")

    return ["\n".join(part1_lines), "\n".join(part2_lines)]


def format_weekly_leaderboard_post(data: Dict[str, Any]) -> str:
    """Rasmiy Telegram kanal va guruh uchun haftalik reyting posti (birlashtirilgan to'liq matn)"""
    parts = format_weekly_leaderboard_parts(data)
    return "\n\n───────────────────────────────\n\n".join(parts)


async def send_safe_telegram_chunk(bot, chat_id: Union[int, str], text: str, parse_mode: str = "Markdown", disable_web_page_preview: bool = True):
    """Xabarni 4000 belgidan oshirmasdan xavfsiz jo'natish"""
    chunks = []
    if len(text) <= 3900:
        chunks = [text]
    else:
        lines = text.split("\n")
        cur_chunk = []
        cur_len = 0
        for l in lines:
            if cur_len + len(l) + 1 > 3800:
                chunks.append("\n".join(cur_chunk))
                cur_chunk = [l]
                cur_len = len(l)
            else:
                cur_chunk.append(l)
                cur_len += len(l) + 1
        if cur_chunk:
            chunks.append("\n".join(cur_chunk))

    for c in chunks:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=c,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
        except Exception as e_md:
            logger.warning(f"send_message markdown error for {chat_id}: {e_md}, falling back to plain text")
            clean_c = c.replace("**", "").replace("*", "").replace("`", "")
            await bot.send_message(
                chat_id=chat_id,
                text=clean_c,
                disable_web_page_preview=disable_web_page_preview
            )
        await asyncio.sleep(0.4)


async def broadcast_weekly_leaderboard(bot_app, force: bool = False) -> Tuple[bool, str]:
    """Haftalik TOP reytingni kanal va guruhga e'lon qilish va g'oliblarni taqdirlash"""
    if not bot_app:
        return False, "bot_app mavjud emas."

    bot = getattr(bot_app, "bot", bot_app)

    async with AsyncSessionLocal() as session:
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
        post_parts = format_weekly_leaderboard_parts(data)
        full_text = "\n\n───────────────────────────────\n\n".join(post_parts)

        # Hafta yetakchilarini taqdirlash (Top 1, 2, 3)
        rewards = [
            (100, 2500),  # 1-o'rin: 100 prestige, 2500 gold
            (50, 1500),   # 2-o'rin: 50 prestige, 1500 gold
            (25, 1000),   # 3-o'rin: 25 prestige, 1000 gold
        ]
        if data.get("top_prestige"):
            for idx, u in enumerate(data["top_prestige"][:3]):
                p_bonus, g_bonus = rewards[idx]
                target_user = await session.get(models.User, u.id)
                if target_user:
                    target_user.prestige = (target_user.prestige or 0) + p_bonus
                    target_user.gold = (target_user.gold or 0) + g_bonus

        # O'tgan hafta sarhisobini doimiy saqlab qo'yish (foydalanuvchilar botda ko'rishi uchun)
        last_ev_res = await session.execute(
            select(models.EventState).where(models.EventState.event_name == "last_weekly_leaderboard")
        )
        last_ev = last_ev_res.scalar_one_or_none()
        if not last_ev:
            last_ev = models.EventState(event_name="last_weekly_leaderboard", data_json=full_text, is_active=True)
            session.add(last_ev)
        else:
            last_ev.data_json = full_text
            last_ev.is_active = True

        if not force:
            ev = models.EventState(event_name=week_key, data_json=now.strftime("%Y-%m-%d %H:%M:%S"))
            session.add(ev)

        await session.commit()

    # Kanal va Guruhga xavfsiz qismlarga bo'lib yuborish
    sent_targets = []
    errors = []

    for target in [CHANNEL_CHAT_ID, GROUP_CHAT_ID]:
        try:
            for part in post_parts:
                await send_safe_telegram_chunk(bot, target, part, parse_mode="Markdown")
            sent_targets.append(str(target))
        except Exception as e:
            logger.warning(f"Kanal/Guruh {target} ga haftalik reyting yuborishda xatolik: {e}")
            errors.append(f"{target}: {e}")

    summary = f"Haftalik reyting yuborildi: {', '.join(sent_targets)}."
    if errors:
        summary += f" Xatolar: {'; '.join(errors)}"
    return bool(sent_targets), summary
