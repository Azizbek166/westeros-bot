"""
Player Titles (Unvonlar) Service for The Iron Throne RPG.
- Katalog (`Title`) va o'yinchining ochilgan unvonlari (`UserTitle`) boshqaruvi.
- Idempotent ochish, profilga taqish/yechish, kampaniya mukofotlari bilan integratsiya va admin unvon berish.
"""
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import models

RARITY_BADGES: Dict[str, str] = {
    "ODDIY": "⚪ Oddiy",
    "NOYOB": "🔵 Noyob",
    "AFSONAVIY": "🟡 Afsonaviy",
}

DEFAULT_TITLES: List[Dict[str, Any]] = [
    {
        "code": "hand_of_investigation",
        "name": "Tergov Qo'li",
        "icon": "🔍",
        "description": "«The Mystery of the Missing Lord» kampaniyasini yakunlaganlik uchun",
        "rarity": "NOYOB",
        "stat_bonus": None,
    },
    {
        "code": "master_of_whispers",
        "name": "Shivirlar Ustasi",
        "icon": "🕷️",
        "description": "«Qonli Ziyofat Soyasi» kampaniyasini yakunlaganlik uchun",
        "rarity": "AFSONAVIY",
        "stat_bonus": None,
    },
    {
        "code": "guardian_of_the_wall",
        "name": "Devor Qo‘riqchisi",
        "icon": "❄️",
        "description": "«Devor Ortida Qolgan Qarg‘a» kampaniyasini yakunlaganlik uchun",
        "rarity": "AFSONAVIY",
        "stat_bonus": None,
    },
    {
        "code": "iron_bank_partner",
        "name": "Temir Bank Hamkori",
        "icon": "🏦",
        "description": "«Valiriya Oltini Karvoni» kampaniyasini yakunlaganlik uchun",
        "rarity": "NOYOB",
        "stat_bonus": None,
    },
    {
        "code": "winter_child",
        "name": "Qish Farzandi",
        "icon": "🐺",
        "description": "Shimoliy yurishlar va maxsus tadbirlarda faol ishtirok uchun",
        "rarity": "ODDIY",
        "stat_bonus": None,
    },
    {
        "code": "dragon_hunter",
        "name": "Ajdar Ovchisi",
        "icon": "🐉",
        "description": "Buyuk ajdarlar janglarida g'olib bo'lganlik uchun",
        "rarity": "NOYOB",
        "stat_bonus": None,
    },
    {
        "code": "iron_throne_defender",
        "name": "Temir Taxt Himoyachisi",
        "icon": "👑",
        "description": "Qirollik urushlari va maxsus mavsumiy musobaqalarda jasorat uchun",
        "rarity": "AFSONAVIY",
        "stat_bonus": None,
    },
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def slugify_title_code(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (name or "").lower().replace("'", "").replace("‘", "").replace("’", "")).strip("_")
    return (cleaned or "custom_title")[:60]


def format_rarity_badge(rarity: Optional[str]) -> str:
    return RARITY_BADGES.get((rarity or "ODDIY").upper(), "⚪ Oddiy")


def parse_stat_bonus(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) and data else None
    except Exception:
        return None


def format_stat_bonus(raw: Optional[str]) -> str:
    bonus = parse_stat_bonus(raw)
    if not bonus:
        return "Kosmetik (0 Pay-To-Win)"
    labels = {"attack": "Hujum", "defense": "Himoya", "hp": "Jon", "gold": "Oltin"}
    parts = [f"+{v} {labels.get(k, k)}" for k, v in bonus.items()]
    return ", ".join(parts)


async def seed_default_titles(session: AsyncSession) -> List[models.Title]:
    """Kampaniya va asosiy unvonlarni idempotent tarzda bazaga kiritadi."""
    out: List[models.Title] = []
    for item in DEFAULT_TITLES:
        res = await session.execute(
            select(models.Title).where(
                or_(
                    models.Title.code == item["code"],
                    func.lower(models.Title.name) == item["name"].lower(),
                )
            )
        )
        existing = res.scalar_one_or_none()
        if existing:
            out.append(existing)
            continue
        t = models.Title(
            code=item["code"],
            name=item["name"],
            icon=item["icon"],
            description=item["description"],
            rarity=item["rarity"],
            stat_bonus_json=json.dumps(item["stat_bonus"], ensure_ascii=False) if item.get("stat_bonus") else None,
            created_at=_utc_now(),
        )
        session.add(t)
        await session.flush()
        out.append(t)
    await session.commit()
    return out


async def get_or_create_title(
    session: AsyncSession,
    name: str,
    *,
    code: Optional[str] = None,
    icon: str = "🏅",
    description: str = "",
    rarity: str = "NOYOB",
    stat_bonus: Optional[Dict[str, Any]] = None,
    commit: bool = True,
) -> models.Title:
    clean_name = (name or "").strip()[:100]
    clean_code = (code or slugify_title_code(clean_name))[:64]

    res = await session.execute(
        select(models.Title).where(
            or_(
                models.Title.code == clean_code,
                func.lower(models.Title.name) == clean_name.lower(),
            )
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        return existing

    # Ensure unique code if collision with different name
    code_chk = (await session.execute(select(models.Title).where(models.Title.code == clean_code))).scalar_one_or_none()
    if code_chk:
        clean_code = f"{clean_code[:54]}_{int(_utc_now().timestamp()) % 100000}"

    rar = (rarity or "NOYOB").upper()
    if rar not in RARITY_BADGES:
        rar = "NOYOB"

    t = models.Title(
        code=clean_code,
        name=clean_name,
        icon=(icon or "🏅").strip()[:16],
        description=(description or "").strip(),
        rarity=rar,
        stat_bonus_json=json.dumps(stat_bonus, ensure_ascii=False) if stat_bonus else None,
        created_at=_utc_now(),
    )
    session.add(t)
    await session.flush()
    if commit:
        await session.commit()
        await session.refresh(t)
    return t


async def grant_title_to_user(
    session: AsyncSession,
    user_id: int,
    *,
    title_id: Optional[int] = None,
    title_code: Optional[str] = None,
    title_name: Optional[str] = None,
    icon: str = "🏅",
    description: str = "",
    rarity: str = "NOYOB",
    stat_bonus: Optional[Dict[str, Any]] = None,
    commit: bool = True,
) -> Tuple[bool, bool, Optional[models.Title]]:
    """
    O'yinchiga unvon beradi (idempotent: bir unvon 2 marta ochilmaydi).
    Qaytaradi: (ok, newly_unlocked, title_obj)
    """
    title_obj: Optional[models.Title] = None
    if title_id is not None:
        title_obj = (await session.execute(select(models.Title).where(models.Title.id == int(title_id)))).scalar_one_or_none()
    elif title_code:
        title_obj = (await session.execute(select(models.Title).where(models.Title.code == title_code))).scalar_one_or_none()

    if title_obj is None and title_name:
        title_obj = await get_or_create_title(
            session,
            title_name,
            code=title_code,
            icon=icon,
            description=description,
            rarity=rarity,
            stat_bonus=stat_bonus,
            commit=False,
        )

    if not title_obj:
        return False, False, None

    ex = (
        await session.execute(
            select(models.UserTitle).where(
                models.UserTitle.user_id == int(user_id),
                models.UserTitle.title_id == title_obj.id,
            )
        )
    ).scalar_one_or_none()
    if ex:
        return True, False, title_obj

    session.add(
        models.UserTitle(
            user_id=int(user_id),
            title_id=title_obj.id,
            unlocked_at=_utc_now(),
        )
    )
    await session.flush()
    if commit:
        await session.commit()
    return True, True, title_obj


async def equip_user_title(
    session: AsyncSession,
    user_id: int,
    title_id: Optional[int],
) -> Tuple[bool, str]:
    """O'yinchining faol unvonini taqadi yoki yechadi (None)."""
    user = (await session.execute(select(models.User).where(models.User.id == int(user_id)))).scalar_one_or_none()
    if not user:
        return False, "❌ Foydalanuvchi topilmadi."

    if title_id is None:
        user.active_title_id = None
        user.title = None
        await session.commit()
        return True, "❌ Faol unvon profildan yechildi."

    ut = (
        await session.execute(
            select(models.UserTitle).where(
                models.UserTitle.user_id == user.id,
                models.UserTitle.title_id == int(title_id),
            )
        )
    ).scalar_one_or_none()
    if not ut or not ut.title:
        return False, "🔒 Ushbu unvon sizda hali ochilmagan!"

    user.active_title_id = ut.title.id
    user.title = ut.title.name
    await session.commit()
    return True, f"✨ Profilga unvon taqildi: {ut.title.icon} **«{ut.title.name}»**!"


async def get_user_active_title(session: AsyncSession, user: Optional[models.User]) -> Optional[models.Title]:
    if not user:
        return None
    atid = getattr(user, "active_title_id", None)
    if not atid:
        return None
    return (await session.execute(select(models.Title).where(models.Title.id == int(atid)))).scalar_one_or_none()


def format_titled_player_name(
    base_name: str,
    active_title: Optional[models.Title] = None,
    fallback_title_str: Optional[str] = None,
) -> str:
    """Profil, reyting va janglarda o'yinchi nomini faol unvoni bilan formatlaydi: `🕷️ [Shivirlar Ustasi] Lord Jon`."""
    if active_title is not None:
        return f"{active_title.icon} [{active_title.name}] {base_name}"
    if fallback_title_str:
        return f"[{fallback_title_str}] {base_name}"
    return base_name


async def list_all_titles(session: AsyncSession) -> List[models.Title]:
    res = await session.execute(select(models.Title).order_by(models.Title.id.asc()))
    return list(res.scalars().all())


async def get_user_titles_overview(session: AsyncSession, user: models.User) -> Dict[str, Any]:
    all_titles = await list_all_titles(session)
    ut_res = await session.execute(
        select(models.UserTitle)
        .where(models.UserTitle.user_id == user.id)
        .order_by(models.UserTitle.unlocked_at.desc())
    )
    user_titles = list(ut_res.scalars().all())
    unlocked_map = {ut.title_id: ut for ut in user_titles}

    unlocked_items = []
    locked_items = []
    active_title: Optional[models.Title] = None
    active_tid = getattr(user, "active_title_id", None)

    for t in all_titles:
        if t.id in unlocked_map:
            ut = unlocked_map[t.id]
            is_active = active_tid == t.id
            if is_active:
                active_title = t
            unlocked_items.append({
                "title": t,
                "unlocked_at": ut.unlocked_at,
                "is_active": is_active,
            })
        else:
            locked_items.append({"title": t})

    return {
        "active_title": active_title,
        "unlocked": unlocked_items,
        "locked": locked_items,
        "unlocked_count": len(unlocked_items),
        "total_count": len(all_titles),
    }


async def find_user_by_identifier(session: AsyncSession, raw: str) -> Optional[models.User]:
    val = (raw or "").strip()
    if not val:
        return None
    if val.startswith("@"):
        uname = val[1:].strip().lower()
        return (
            await session.execute(select(models.User).where(func.lower(models.User.username) == uname))
        ).scalar_one_or_none()
    if val.isdigit():
        num = int(val)
        u = (await session.execute(select(models.User).where(models.User.telegram_id == num))).scalar_one_or_none()
        if u:
            return u
        return (await session.execute(select(models.User).where(models.User.id == num))).scalar_one_or_none()
    return (
        await session.execute(select(models.User).where(func.lower(models.User.username) == val.lower()))
    ).scalar_one_or_none()
