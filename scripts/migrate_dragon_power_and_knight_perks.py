"""
Bir martalik migratsiya skripti:
1. Ajdaho kuchi (Dragon Power): eski xatolik (Arrax 12,300 cap) tufayli quvvati pasayib ketgan
   barcha ajdarlarning quvvatini ularning haqiqiy turi, darajasi va taqilgan artefaktiga qarab tiklaydi.
2. 25,000 so'mlik Donate Pack (Ritsar Homiy / knight) va yuqori paketlar egalariga
   profil rasm, video/GIF va shior imtiyozlarini (vip_tier, vip_until, cosmetics) avtomatik tiklaydi.

Ishga tushirish:
    python scripts/migrate_dragon_power_and_knight_perks.py
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import DONATE_TIERS
from data.artifacts_data import ARTIFACTS_DATA
from database import crud, models

logger = logging.getLogger(__name__)

VIP_RANKS = {
    "noble": 1,
    "knight": 2,
    "lord": 3,
    "dragonlord": 4,
    "sovereign": 5,
}


async def restore_dragons_power(session: AsyncSession) -> Dict[str, Any]:
    """
    Bazada xatolik tufayli kuchi 12,300 (yoki Arrax limitiga) tushib qolgan barcha ajdarlarning
    kuchini ularning haqiqiy turi, darajasi va taqilgan artefaktlariga qarab qayta hisoblab tiklaydi.
    """
    res = await session.execute(select(models.Dragon))
    dragons = res.scalars().all()

    checked = 0
    restored = 0
    clamped = 0
    changes = []

    for drg in dragons:
        checked += 1
        lvl = max(1, drg.level or 1)
        stage = getattr(drg, "stage", "adult") or "adult"
        name = getattr(drg, "name", None)
        grade = getattr(drg, "grade", "C") or "C"
        art_code = getattr(drg, "artifact_code", None)

        species_base = crud.get_base_dragon_power_for_level(lvl, stage, name=name, grade=grade)
        art_bonus = float(ARTIFACTS_DATA.get(art_code, {}).get("dragon_bonus", 0.0) or 0.0) if art_code else 0.0
        expected_min = int(round(species_base * (1.0 + art_bonus)))
        max_p = crud.get_max_dragon_power(lvl, stage, art_code, name=name, grade=grade)
        old_arrax_cap = crud.get_max_dragon_power(lvl, stage, art_code, name=None, grade="C")

        old_pwr = drg.power or 0
        was_bug_capped = (old_pwr in (12300, old_arrax_cap)) and (expected_min > old_pwr)

        if old_pwr < expected_min or was_bug_capped:
            new_pwr = min(max_p, expected_min)
            drg.power = new_pwr
            restored += 1
            changes.append({
                "dragon_id": drg.id,
                "user_id": drg.user_id,
                "name": name,
                "grade": grade,
                "level": lvl,
                "artifact_code": art_code,
                "old_power": old_pwr,
                "new_power": new_pwr,
                "action": "restored",
            })
        elif old_pwr > max_p:
            drg.power = max_p
            clamped += 1
            changes.append({
                "dragon_id": drg.id,
                "user_id": drg.user_id,
                "name": name,
                "grade": grade,
                "level": lvl,
                "artifact_code": art_code,
                "old_power": old_pwr,
                "new_power": max_p,
                "action": "clamped",
            })

    await session.flush()
    return {
        "checked": checked,
        "restored": restored,
        "clamped": clamped,
        "changes": changes,
    }


async def restore_25k_knight_pack_perks(session: AsyncSession) -> Dict[str, Any]:
    """
    Avvalroq 25,000 so'mlik pack (knight / Ritsar Homiy) yoki undan yuqori VIP paket sotib olgan
    barcha mavjud foydalanuvchilarni bazadan aniqlab, ularning vip_tier va vip_until imtiyozlarini
    (rasm, video, GIF, shior) faollashtirib tiklaydi.
    """
    now = datetime.utcnow()
    req_res = await session.execute(
        select(models.DonationRequest).where(models.DonationRequest.status == "approved")
    )
    approved_reqs = req_res.scalars().all()

    # Har bir foydalanuvchi uchun eng yuqori tasdiqlangan VIP darajasi va so'nggi xarid sanasini aniqlash
    user_best: Dict[int, Dict[str, Any]] = {}

    for req in approved_reqs:
        tid = (req.tier_id or "").strip().lower()
        price = int(req.price_uzs or 0)

        target_tier = None
        if tid in VIP_RANKS:
            target_tier = tid
        elif price == 25000:
            target_tier = "knight"

        if not target_tier or VIP_RANKS.get(target_tier, 0) < VIP_RANKS["knight"]:
            continue

        user = None
        if req.user_id:
            user = await session.get(models.User, req.user_id)
        if not user and req.telegram_id:
            user = await crud.get_user_by_telegram_id(session, req.telegram_id)
        if not user:
            continue

        rank = VIP_RANKS[target_tier]
        req_time = req.reviewed_at or req.created_at or now
        existing = user_best.get(user.id)
        if not existing or rank > existing["rank"] or (rank == existing["rank"] and req_time > existing["req_time"]):
            user_best[user.id] = {
                "user": user,
                "tier": target_tier,
                "rank": rank,
                "req_time": req_time,
            }

    updated_users = []
    for uid, info in user_best.items():
        user = info["user"]
        target_tier = info["tier"]
        target_rank = info["rank"]
        req_time = info["req_time"]

        old_tier = user.vip_tier
        old_until = user.vip_until
        cur_rank = VIP_RANKS.get((old_tier or "").lower(), 0)
        changed = False

        if cur_rank < target_rank:
            user.vip_tier = target_tier
            changed = True

        # Agar VIP muddati yo'q yoki tugagan bo'lsa va xarid yaqinda (60 kun ichida) bo'lgan bo'lsa,
        # xatolik tufayli imtiyozdan foydalana olmagani uchun 30 kunlik faol muddatni ta'minlaymiz
        tier_cfg = DONATE_TIERS.get(user.vip_tier or target_tier, {})
        duration_days = int(tier_cfg.get("duration_days", 30) or 30)
        if not user.vip_until or user.vip_until <= now:
            if (now - req_time).days <= 60:
                user.vip_until = now + timedelta(days=duration_days)
                changed = True

        # Paket kosmetikalarini ham kafolatlash
        from core.cosmetics import grant_cosmetic_item
        for cid in tier_cfg.get("cosmetics", []):
            try:
                await grant_cosmetic_item(session, user, cid)
            except Exception as c_err:
                logger.warning(f"Knight migration cosmetic ({cid}) xatosi (user={user.id}): {c_err}")

        if changed:
            updated_users.append({
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "full_name": user.full_name,
                "old_tier": old_tier,
                "new_tier": user.vip_tier,
                "old_until": old_until.isoformat() if old_until else None,
                "new_until": user.vip_until.isoformat() if user.vip_until else None,
            })

    await session.flush()
    return {
        "matched_buyers": len(user_best),
        "updated_count": len(updated_users),
        "updated_users": updated_users,
    }


async def run_all_migrations() -> Dict[str, Any]:
    from database.db import AsyncSessionLocal, init_db
    await init_db()
    async with AsyncSessionLocal() as session:
        dragon_res = await restore_dragons_power(session)
        knight_res = await restore_25k_knight_pack_perks(session)
        await session.commit()
    return {
        "dragons": dragon_res,
        "knight_perks": knight_res,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    result = asyncio.run(run_all_migrations())
    print("=== MIGRATSIYA NATIJASI ===")
    print(f"Ajdarlar tekshirildi: {result['dragons']['checked']}")
    print(f"Ajdarlar tiklandi:    {result['dragons']['restored']}")
    print(f"Ajdarlar normallandi: {result['dragons']['clamped']}")
    for ch in result["dragons"]["changes"]:
        print(f"  - Dragon #{ch['dragon_id']} ({ch['name']} Lv.{ch['level']}, art={ch['artifact_code']}): {ch['old_power']:,} -> {ch['new_power']:,} ({ch['action']})")

    print(f"\n25,000+ pack egalari topildi: {result['knight_perks']['matched_buyers']}")
    print(f"VIP imtiyozlari yangilandi:   {result['knight_perks']['updated_count']}")
    for u in result["knight_perks"]["updated_users"]:
        print(f"  - User #{u['user_id']} (tg={u['telegram_id']}, {u['full_name']}): tier {u['old_tier']} -> {u['new_tier']}, until={u['new_until']}")
