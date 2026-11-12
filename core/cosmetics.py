"""
Cosmetics & Ethical Monetization System for The Iron Throne RPG.
STRICT RULE: Zero Pay-To-Win. No purchased item may grant troop counts,
combat stats, damage boosts, or core resource advantages.
All offerings are strictly aesthetic (skins, frames, titles, effects) or
non-combat quality-of-life (e.g. 1-click tax collection, live profile video).
"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import models


# ============================================================
# 1. KOSMETIKA VA QULAYLIKLAR KATALOGI
# ============================================================
COSMETICS_CATALOG: Dict[str, Dict[str, Any]] = {
    # --- A. QAL'A SKINLARI (CASTLE SKINS) ---
    "castle_ice": {
        "id": "castle_ice",
        "name": "❄️ Qishki Muz Qasri (Winter Citadel)",
        "category": "castle_skin",
        "rarity": "nodir",
        "rarity_label": "Nodir (Rare)",
        "price_stars": 75,
        "price_uzs": 15000,
        "is_permanent": True,
        "icon": "❄️",
        "description": "Shimolning abadiy ayozida qad ko'targan sirli muz qasri ko'rinishi. Qal'angiz xaritada va mini appda muzli zangori tusda tovlanadi.",
    },
    "castle_valyrian": {
        "id": "castle_valyrian",
        "name": "🔥 Valiriya Qora Bazalti (Valyrian Fortress)",
        "category": "castle_skin",
        "rarity": "afsonaviy",
        "rarity_label": "Afsonaviy (Legendary)",
        "price_stars": 150,
        "price_uzs": 30000,
        "is_permanent": True,
        "icon": "🔥",
        "description": "Valiriya ajdaho olovida toblangan vulqon bazalti qal'asi. Qora silliq toshlar va qizg'in olovli mash'allar bilan bezatilgan.",
    },
    "castle_golden": {
        "id": "castle_golden",
        "name": "👑 Casterly Oltin Saroyi (Golden Palace)",
        "category": "castle_skin",
        "rarity": "afsonaviy",
        "rarity_label": "Afsonaviy (Legendary)",
        "price_stars": 200,
        "price_uzs": 40000,
        "is_permanent": True,
        "icon": "👑",
        "description": "Lannisterlar boyligi va qudrati ramzi. Quyosh nurlarida olmosdek porlovchi oltin minora va hashamatli ayvonlar.",
    },
    "castle_shadow": {
        "id": "castle_shadow",
        "name": "🌑 Qora Qoya Qal'asi (Shadow Keep)",
        "category": "castle_skin",
        "rarity": "nodir",
        "rarity_label": "Nodir (Rare)",
        "price_stars": 100,
        "price_uzs": 20000,
        "is_permanent": True,
        "icon": "🌑",
        "description": "Tuman va soyalar orasiga yashiringan mistik qal'a. Dushman yuragiga vahima soluvchi qorong'u qoya arxitekturasi.",
    },

    # --- B. AJDAR KO'RINISHLARI (DRAGON SKINS) ---
    "dragon_shadow": {
        "id": "dragon_shadow",
        "name": "🌑 Qora Soyalar Ajdari (Shadow Drake)",
        "category": "dragon_skin",
        "rarity": "afsonaviy",
        "rarity_label": "Afsonaviy (Legendary)",
        "price_stars": 150,
        "price_uzs": 30000,
        "is_permanent": True,
        "icon": "🐉",
        "description": "Afsonaviy Balerion avlodi kabi qora tungi rang, qorong'u olov va ko'mirday porlovchi ko'zlar.",
    },
    "dragon_crimson": {
        "id": "dragon_crimson",
        "name": "🩸 Qonli Qizil Alov (Crimson Fury)",
        "category": "dragon_skin",
        "rarity": "nodir",
        "rarity_label": "Nodir (Rare)",
        "price_stars": 100,
        "price_uzs": 20000,
        "is_permanent": True,
        "icon": "🔥",
        "description": "Caraxes kabi qon-qizil rangdagi qanotlar va alangali qizil tangachalar ko'rinishi.",
    },
    "dragon_emerald": {
        "id": "dragon_emerald",
        "name": "💚 Zumrad Ajdaho (Emerald Wyrm)",
        "category": "dragon_skin",
        "rarity": "nodir",
        "rarity_label": "Nodir (Rare)",
        "price_stars": 100,
        "price_uzs": 20000,
        "is_permanent": True,
        "icon": "💚",
        "description": "Zumrad toshiday yashil tusda yaltirovchi tangachalar va yashil nafas ko'rinishi.",
    },
    "dragon_golden": {
        "id": "dragon_golden",
        "name": "✨ Oltin Ajdaho (Sunfyre Gleam)",
        "category": "dragon_skin",
        "rarity": "afsonaviy",
        "rarity_label": "Afsonaviy (Legendary)",
        "price_stars": 150,
        "price_uzs": 30000,
        "is_permanent": True,
        "icon": "✨",
        "description": "Oltin sarig'i qanotlar, osmonda quyosh kabi porlovchi afsonaviy Sunfyre ko'rinishi.",
    },

    # --- C. PROFIL RAMKALARI (AVATAR FRAMES) ---
    "frame_iron": {
        "id": "frame_iron",
        "name": "⛓️ Temir Qasamyod Ramkasi",
        "category": "avatar_frame",
        "rarity": "oddiy",
        "rarity_label": "Oddiy (Common)",
        "price_stars": 30,
        "price_uzs": 6000,
        "is_permanent": True,
        "icon": "⛓️",
        "description": "Temir Taxt qilichlari va zanjirlaridan ilhomlangan qat'iyatli po'lat ramka.",
    },
    "frame_flame": {
        "id": "frame_flame",
        "name": "🔥 Valiriya Olovi Ramkasi",
        "category": "avatar_frame",
        "rarity": "nodir",
        "rarity_label": "Nodir (Rare)",
        "price_stars": 50,
        "price_uzs": 10000,
        "is_permanent": True,
        "icon": "🔥",
        "description": "Ajdaho olovi alangasi bilan nurlanuvchi qizil-oltin dinamik profil hoshiyasi.",
    },
    "frame_sovereign": {
        "id": "frame_sovereign",
        "name": "👑 Oliy Imperatorlik Toji Ramkasi",
        "category": "avatar_frame",
        "rarity": "afsonaviy",
        "rarity_label": "Afsonaviy (Legendary)",
        "price_stars": 100,
        "price_uzs": 20000,
        "is_permanent": True,
        "icon": "👑",
        "description": "Haqiqiy shohona toj va qimmatbaho javohirlar bilan bezatilgan eng nufuzli ramka.",
    },

    # --- D. FAXRIY UNVONLAR (TITLES) ---
    "title_dragonrider": {
        "id": "title_dragonrider",
        "name": "🐉 Ajdar Chavandozi",
        "category": "title",
        "rarity": "nodir",
        "rarity_label": "Nodir (Rare)",
        "price_stars": 40,
        "price_uzs": 8000,
        "is_permanent": True,
        "icon": "📜",
        "description": "Profil va bot xabarlarida ismingiz yonida turuvchi faxriy unvon: «Ajdar Chavandozi».",
    },
    "title_kingsguard": {
        "id": "title_kingsguard",
        "name": "⚔️ Qirollik Soqchisi",
        "category": "title",
        "rarity": "nodir",
        "rarity_label": "Nodir (Rare)",
        "price_stars": 40,
        "price_uzs": 8000,
        "is_permanent": True,
        "icon": "⚔️",
        "description": "Vesterosning eng mard va sadoqatli ritsarlari unvoni: «Qirollik Soqchisi».",
    },
    "title_ironthrone": {
        "id": "title_ironthrone",
        "name": "👑 Temir Taxt Da'vogari",
        "category": "title",
        "rarity": "afsonaviy",
        "rarity_label": "Afsonaviy (Legendary)",
        "price_stars": 80,
        "price_uzs": 16000,
        "is_permanent": True,
        "icon": "👑",
        "description": "Yetti Qirollik toji uchun da'vogar ekaningizni bildiruvchi eksklyuziv unvon.",
    },
    "title_legacy_founder": {
        "id": "title_legacy_founder",
        "name": "🌟 Faxriy Asl Hukmdor (Legacy Founder)",
        "category": "title",
        "rarity": "afsonaviy",
        "rarity_label": "Eksklyuziv (Founder)",
        "price_stars": 0,
        "price_uzs": 0,
        "is_permanent": True,
        "icon": "🌟",
        "description": "O'yinning ilk mavsumida hissa qo'shgan faxriy donaterlar uchun maxsus kompensatsiya unvoni.",
    },

    # --- E. XABAR VA CHAT EFFEKTLARI (MESSAGE EFFECTS) ---
    "effect_fire": {
        "id": "effect_fire",
        "name": "🔥 Olovli Muhr Effekti",
        "category": "message_effect",
        "rarity": "nodir",
        "rarity_label": "Nodir (Rare)",
        "price_stars": 50,
        "price_uzs": 10000,
        "is_permanent": True,
        "icon": "🔥",
        "description": "Xonadon qarg'alari va chat xabarlarida ismingiz ostida alangalovchi olovli muhr belgisi.",
    },
    "effect_ice": {
        "id": "effect_ice",
        "name": "❄️ Qor Bo'roni Effekti",
        "category": "message_effect",
        "rarity": "nodir",
        "rarity_label": "Nodir (Rare)",
        "price_stars": 50,
        "price_uzs": 10000,
        "is_permanent": True,
        "icon": "❄️",
        "description": "Profil va xabarlarda qish nafasini aks ettiruvchi qor bo'roni vizual effekti.",
    },

    # --- F. STARTER PACK (BIRINCHI XARIDGA SOVG'A) ---
    "starter_pack": {
        "id": "starter_pack",
        "name": "🎁 Boshlang'ich Lord To'plami (Starter Pack)",
        "category": "starter_pack",
        "rarity": "maxsus",
        "rarity_label": "Maxsus Taklif",
        "price_stars": 25,
        "price_uzs": 5000,
        "is_permanent": True,
        "icon": "🎁",
        "description": "Birinchi xarid uchun maxsus to'plam: «🗡️ Yosh Ritsar Ramkasi» + «🎖️ Boshlang'ich Lord» unvoni + 7 kunlik VIP qulaylik. (Faqat 1 marta xarid qilinadi).",
    },

    # --- G. NOBLE VIP (HALOL QULAYLIKLAR VA ESTETIKA - P2W EMAS!) ---
    "vip_noble": {
        "id": "vip_noble",
        "name": "👑 Oliyjanob Lord (Noble VIP - 30 kun)",
        "category": "vip_subscription",
        "rarity": "nodir",
        "rarity_label": "VIP Obuna (30 kun)",
        "price_stars": 75,
        "price_uzs": 15000,
        "is_permanent": False,
        "duration_days": 30,
        "icon": "👑",
        "description": (
            "Zararsiz qulayliklar to'plami:\n"
            "• ⚡ Barcha qal'alardan 1-bosishda soliq yig'ish (Collect All)\n"
            "• 🎥 Profilga dumaloq video yoki video-gif qo'yish huquqi\n"
            "• 👑 Ism yonida zarhal [VIP] nishoni\n"
            "• 📊 Kengaytirilgan jang statistikasi va harakatlar tarixi filtri\n"
            "• 🚫 Diqqat: Jangda HECH QANDAY armiya yoki kuch ustunligi bermaydi!"
        ),
    },
}


def get_cosmetic_item(item_id: str) -> Optional[Dict[str, Any]]:
    """Katalogdan ma'lum bir buyumni olish"""
    return COSMETICS_CATALOG.get(item_id)


def get_all_cosmetics_grouped() -> Dict[str, List[Dict[str, Any]]]:
    """Kategoriyalar bo'yicha guruhlangan kosmetika ro'yxati"""
    grouped = {
        "castle_skins": [],
        "dragon_skins": [],
        "avatar_frames": [],
        "titles": [],
        "message_effects": [],
        "special_and_vip": [],
    }

    cat_map = {
        "castle_skin": "castle_skins",
        "dragon_skin": "dragon_skins",
        "avatar_frame": "avatar_frames",
        "title": "titles",
        "message_effect": "message_effects",
        "starter_pack": "special_and_vip",
        "vip_subscription": "special_and_vip",
    }

    for item_id, item in COSMETICS_CATALOG.items():
        grp_key = cat_map.get(item.get("category"), "special_and_vip")
        grouped[grp_key].append(item)

    return grouped


# ============================================================
# 2. XARID VA INVENTARNI BOSHQARISH
# ============================================================

async def get_user_cosmetics(session: AsyncSession, user_id: int) -> List[models.UserCosmetic]:
    """O'yinchiga tegishli barcha kosmetik buyumlar"""
    res = await session.execute(
        select(models.UserCosmetic).where(models.UserCosmetic.user_id == user_id)
    )
    return list(res.scalars().all())


async def equip_cosmetic(
    session: AsyncSession,
    user: models.User,
    item_id: str,
) -> Tuple[bool, str]:
    """Kosmetik buyumni kiyish yoki yechish"""
    item = get_cosmetic_item(item_id)
    if not item:
        return False, "Bunday kosmetika topilmadi."

    # Egaligini tekshirish
    res = await session.execute(
        select(models.UserCosmetic).where(
            models.UserCosmetic.user_id == user.id,
            models.UserCosmetic.item_id == item_id,
        )
    )
    user_cosm = res.scalar_one_or_none()
    if not user_cosm:
        return False, "Sizda ushbu kosmetik buyum mavjud emas."

    cat = item["category"]

    # Agar allaqachon taqilgan bo'lsa -> yechish (unequip)
    if user_cosm.is_equipped:
        user_cosm.is_equipped = False
        if cat == "avatar_frame" and user.avatar_frame == item_id:
            user.avatar_frame = None
        elif cat == "castle_skin" and user.castle_skin == item_id:
            user.castle_skin = None
        elif cat == "dragon_skin" and user.dragon_skin == item_id:
            user.dragon_skin = None
        elif cat == "message_effect" and user.message_effect == item_id:
            user.message_effect = None
        elif cat == "title" and user.title == item["name"]:
            user.title = None

        await session.commit()
        return True, f"«{item['name']}» muvaffaqiyatli yechildi."

    # Boshqa shu toifadagi jihozlarni yechish
    all_same_cat = await session.execute(
        select(models.UserCosmetic).where(
            models.UserCosmetic.user_id == user.id,
            models.UserCosmetic.category == cat,
        )
    )
    for c in all_same_cat.scalars().all():
        c.is_equipped = False

    # Yangisini taqish
    user_cosm.is_equipped = True
    if cat == "avatar_frame":
        user.avatar_frame = item_id
    elif cat == "castle_skin":
        user.castle_skin = item_id
    elif cat == "dragon_skin":
        user.dragon_skin = item_id
    elif cat == "message_effect":
        user.message_effect = item_id
    elif cat == "title":
        user.title = item["name"]

    await session.commit()
    return True, f"«{item['name']}» muvaffaqiyatli taqildi!"


async def grant_cosmetic_item(
    session: AsyncSession,
    user: models.User,
    item_id: str,
    is_gift: bool = False,
    gifted_by_telegram_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """Foydalanuvchiga kosmetik buyum taqdim etish (idempotent)"""
    item = get_cosmetic_item(item_id)
    if not item:
        return False, "Noto'g'ri buyum kodi."

    cat = item["category"]

    # VIP obuna bo'lsa
    if cat == "vip_subscription":
        now = datetime.utcnow()
        current_vip = user.vip_until if (user.vip_until and user.vip_until > now) else now
        user.vip_tier = "noble"
        user.vip_until = current_vip + timedelta(days=item.get("duration_days", 30))
        await session.commit()
        return True, f"«{item['name']}» 30 kunga faollashtirildi!"

    # Starter pack bo'lsa
    if cat == "starter_pack":
        user.has_starter_pack = True
        # Frame va title sovg'a
        await grant_cosmetic_item(session, user, "frame_iron")
        await grant_cosmetic_item(session, user, "title_kingsguard")
        now = datetime.utcnow()
        current_vip = user.vip_until if (user.vip_until and user.vip_until > now) else now
        user.vip_tier = "noble"
        user.vip_until = current_vip + timedelta(days=7)
        await session.commit()
        return True, "Starter Pack muvaffaqiyatli qabul qilindi!"

    # Tekshirish: allaqachon bormi?
    res = await session.execute(
        select(models.UserCosmetic).where(
            models.UserCosmetic.user_id == user.id,
            models.UserCosmetic.item_id == item_id,
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        return True, f"Sizda allaqachon «{item['name']}» mavjud."

    new_cosm = models.UserCosmetic(
        user_id=user.id,
        item_id=item_id,
        category=cat,
        is_equipped=False,
        is_gift=is_gift,
        gifted_by_telegram_id=gifted_by_telegram_id,
        acquired_at=datetime.utcnow(),
    )
    session.add(new_cosm)
    await session.commit()
    return True, f"«{item['name']}» inventaringizga qo'shildi!"


# ============================================================
# 3. TO'LOV TRANZAKSIYASINI QAYD ETISH VA IDEMPOTENTLIK
# ============================================================

async def record_payment_transaction(
    session: AsyncSession,
    telegram_id: int,
    item_id: str,
    provider: str,
    idempotency_key: str,
    amount_stars: int = 0,
    amount_uzs: int = 0,
    is_gift: bool = False,
    recipient_telegram_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> Tuple[bool, str, Optional[models.PaymentTransaction]]:
    """To'lov tranzaksiyasini takroriy yozilishdan himoyalangan (idempotent) tarzda qayd etish"""
    # 1. Idempotency tekshiruvi
    res = await session.execute(
        select(models.PaymentTransaction).where(models.PaymentTransaction.idempotency_key == idempotency_key)
    )
    existing = res.scalar_one_or_none()
    if existing:
        return True, "Tranzaksiya allaqachon bajarilgan.", existing

    item = get_cosmetic_item(item_id)
    item_name = item["name"] if item else item_id

    tx = models.PaymentTransaction(
        user_id=user_id,
        telegram_id=telegram_id,
        item_id=item_id,
        item_name=item_name,
        provider=provider,
        amount_stars=amount_stars,
        amount_uzs=amount_uzs,
        status="completed",
        idempotency_key=idempotency_key,
        is_gift=is_gift,
        recipient_telegram_id=recipient_telegram_id,
        created_at=datetime.utcnow(),
    )
    session.add(tx)
    await session.commit()
    return True, "To'lov muvaffaqiyatli qayd etildi.", tx


# ============================================================
# 4. ESKI DONATERLARGA KOMPENSATSIYA REJASI
# ============================================================

async def apply_legacy_vip_compensation(session: AsyncSession, user: models.User) -> Tuple[bool, str]:
    """
    Eski Pay-To-Win VIP paketlarini xarid qilgan foydalanuvchilarga adolatli
    va sharafli eksklyuziv kosmetika to'plamini kompensatsiya sifatida berish.
    """
    old_vip = getattr(user, "vip_tier", None)
    if not old_vip or old_vip in ("free", "noble"):
        return False, "Kompensatsiya talab etilmaydi."

    # Eksklyuziv sovg'alar
    await grant_cosmetic_item(session, user, "title_legacy_founder")
    await grant_cosmetic_item(session, user, "frame_sovereign")
    await grant_cosmetic_item(session, user, "castle_valyrian")

    # 30 kunlik Noble VIP
    now = datetime.utcnow()
    current_vip = user.vip_until if (user.vip_until and user.vip_until > now) else now
    user.vip_tier = "noble"
    user.vip_until = current_vip + timedelta(days=30)
    await session.commit()

    msg = (
        "👑 **VAXT-KORONA KOMPENSATSIYA TUHFASI!**\n\n"
        "Hurmatli Lord! O'yinda barcha jangovar ustunliklar adolatli balansga o'tkazildi. "
        "Sizning ilgari qo'shgan hissangiz sharafiga quyidagi eksklyuziv sovg'alar berildi:\n"
        "• 🌟 Faxriy Unvon: «Faxriy Asl Hukmdor (Legacy Founder)»\n"
        "• 👑 Oliy Imperatorlik Toji Ramkasi (Avatar Frame)\n"
        "• 🔥 Valiriya Qora Bazalti Qal'a Skini\n"
        "• 👑 30 kunlik Noble VIP obunasi (Barcha qulayliklar bilan)!\n\n"
        "Sizga cheksiz minnatdorchilik bildiramiz!"
    )
    return True, msg
