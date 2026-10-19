import re
import logging
from datetime import datetime
from typing import Tuple, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from database import AsyncSessionLocal, crud, models
from core.economy_engine import calculate_army_upkeep, calculate_hourly_income
from keyboards.menus import back_to_main_keyboard
from config import escape_md, COMMUNITY_CHANNEL_URL, COMMUNITY_GROUP_URL

logger = logging.getLogger(__name__)

GOT_AUDIO_PRESETS = {
    "got_main": {
        "title": "Game of Thrones: Main Theme",
        "desc": "🏰 Westeros Buyuk Asosiy Gimni",
    },
    "rains": {
        "title": "The Rains of Castamere",
        "desc": "🦁 Lannisterlar Shon-Sharafi",
    },
    "light": {
        "title": "Light of the Seven",
        "desc": "🕯️ Qirollik Va Sitadel Kuylari",
    },
    "dragon": {
        "title": "Blood of the Dragon",
        "desc": "🐉 Valyriya Ajdaho Olovi",
    },
    "night_king": {
        "title": "The Night King Theme",
        "desc": "❄️ Shimol Va Qish Sovuqligi",
    },
}


async def format_user_profile_card(user: models.User, session, is_group: bool = False) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    O'yinchi profil kartasini (shaxsiy chat yoki guruh uchun) VIP darajasiga qarab yaltiroq va boy formatda tayyorlash.
    Qaytaradi: (text, photo_file_id, audio_file_id, audio_title)
    """
    from core.leveling import get_level_info, check_user_level_up
    leveled_up, new_lvl, lvl_msg = check_user_level_up(user)
    if leveled_up:
        await session.commit()

    lvl, lvl_title, curr_req, next_req, progress = get_level_info(user.xp or 0)
    prog_bar = "█" * int(progress // 10) + "░" * (10 - int(progress // 10))

    upkeep = calculate_army_upkeep(user.army) if user.army else 0
    income = await calculate_hourly_income(session, user)
    hero = user.characters[0] if user.characters else None

    # Taqilgan artefakt
    equipped_art = await crud.get_equipped_artifact(session, user.id)
    art_str = f"🗡️ Artefakt: **{equipped_art.name}**\n" if equipped_art else ""

    # Qalqon holati
    shield_str = "❌ Faol emas"
    if user.peace_shield_until and user.peace_shield_until > datetime.utcnow():
        diff = user.peace_shield_until - datetime.utcnow()
        hours = int(diff.total_seconds() // 3600)
        shield_str = f"🛡️ Faol ({hours} soat qoldi)"

    house_str = f"{user.house.emoji} {user.house.name} ({user.house.region})" if user.house else "Tanlanmagan"
    inf_cnt = user.army.infantry if user.army else 0
    arc_cnt = user.army.archers if user.army else 0
    cav_cnt = user.army.cavalry if user.army else 0
    spm_cnt = user.army.spearmen if user.army else 0
    spc_cnt = user.army.special_troops if user.army else 0

    net_food = income["food"] - int(upkeep)
    net_food_str = f"+{net_food}" if net_food >= 0 else f"{net_food}"

    raw_name = hero.name if hero else (user.full_name or "Lord")
    user_display_name = escape_md(raw_name)
    username_str = f" (@{escape_md(user.username)})" if user.username else ""

    # Ajdaho
    dragons = await crud.get_user_dragons(session, user.id)
    dragon_line = ""
    if dragons:
        best_d = max(dragons, key=lambda d: d.power)
        dragon_line = f"🐉 **Ajdaho:** {best_d.name} ({best_d.level}-daraja, {best_d.power:,} quvvat)\n"

    vip = user.vip_tier

    # 1. TEMIR TAXT SOHIBI (SOVEREIGN) - Mutlaq Oliy Imperatorlik Dizayni
    if vip == "sovereign":
        status_line = f"📜 Imperator Shiori: «*{escape_md(user.custom_status)}*»\n" if user.custom_status else ""
        audio_line = f"🎵 Qirollik Gimni: 🎶 *{escape_md(user.custom_audio_title or 'Westeros Imperatorlik Gimni')}*\n" if (user.custom_audio_file_id or user.custom_audio_title) else ""
        decree_cnt = getattr(user, "royal_decree_count", 0) or 0

        text = (
            f"👑════════════════════════════👑\n"
            f"   ⚔️  **TEMIR TAXT HUKMDORI**  ⚔️\n"
            f"👑════════════════════════════👑\n\n"
            f"⚡ Buyuk Imperator: **{user_display_name}**{username_str} | {house_str}\n"
            f"{status_line}"
            f"👑 Oliy Titul: «**{escape_md(user.title or 'Vesteros Himoyachisi')}**»\n"
            f"{audio_line}"
            f"🎖️ {user.rank.title()} | ⭐ Lv.{lvl}/30 ({lvl_title}) | 🏆 {user.prestige:,} Prestige\n"
            f"📈 `[{prog_bar}]` {user.xp:,}/{next_req:,} XP ({int(progress)}%)\n"
            f"{art_str}"
            f"🔰 Qalqon: {shield_str}\n\n"
            f"📊 **Xazina:** 🪙**{user.gold:,}** (+{income['gold']}/s 👑+25%) | 🌾**{user.food:,}** ({net_food_str}/s) | ⛓️**{user.iron:,}** (+{income['iron']}/s)\n"
            f"⚔️ **Qo'shin:** 🛡️{inf_cnt:,} | 🏹{arc_cnt:,} | 🐎{cav_cnt:,} | 🗡️{spm_cnt:,} | 🔥{spc_cnt:,}\n"
            f"{dragon_line}"
            f"👑 **Imperatorlik Imtiyozlari:**\n"
            f"• 💰 Barcha hudud va konlardan +25% doimiy daromad\n"
            f"• 📜 Qirollik Farmoni: **{decree_cnt} ta** huquq mavjud\n\n"
            f"👑✨🌟⚡🌟✨👑"
        )

    # 2. VALYRIYA MEROSI (DRAGONLORD) - Olovli Afsonaviy Dizayn
    elif vip == "dragonlord":
        status_line = f"📜 Shior: «*{escape_md(user.custom_status)}*»\n" if user.custom_status else ""
        audio_line = f"🎵 Fon Musiqasi: 🎶 *{escape_md(user.custom_audio_title or 'Valyriya Kuylari')}*\n" if (user.custom_audio_file_id or user.custom_audio_title) else ""

        text = (
            f"⚜️════════════════════════════⚜️\n"
            f"   🐉  **VALYRIYA OLOVLI MEROSI**  🐉\n"
            f"⚜️════════════════════════════⚜️\n\n"
            f"🔥 Lord: **{user_display_name}**{username_str} | {house_str}\n"
            f"{status_line}"
            f"🎖️ Sharafli Unvon: «**{escape_md(user.title or 'Ajdaho Hukmdori')}**»\n"
            f"{audio_line}"
            f"🎖️ {user.rank.title()} | ⭐ Lv.{lvl}/30 ({lvl_title}) | 🏆 {user.prestige:,} Prestige\n"
            f"📈 `[{prog_bar}]` {user.xp:,}/{next_req:,} XP ({int(progress)}%)\n"
            f"{art_str}"
            f"🔰 Qalqon: {shield_str}\n\n"
            f"📊 **Xazina:** 🪙**{user.gold:,}** (+{income['gold']}/s) | 🌾**{user.food:,}** ({net_food_str}/s) | ⛓️**{user.iron:,}** (+{income['iron']}/s)\n"
            f"⚔️ **Qo'shin:** 🛡️{inf_cnt:,} | 🏹{arc_cnt:,} | 🐎{cav_cnt:,} | 🗡️{spm_cnt:,} | 🔥{spc_cnt:,}\n"
            f"{dragon_line}\n"
            f"⚜️🌌✨ _Valyriya xazinasi va olovi barhayotdir_ ✨🌌⚜️"
        )

    # 3. LORDLAR XAZINASI (LORD) - Yaltiroq Olmosli Dizayn
    elif vip == "lord":
        status_line = f"📜 Shior: «*{escape_md(user.custom_status)}*»\n" if user.custom_status else ""
        audio_line = f"🎵 Fon Musiqasi: 🎶 *{escape_md(user.custom_audio_title or 'Lord Gimni')}*\n" if (user.custom_audio_file_id or user.custom_audio_title) else ""

        text = (
            f"✨════════════════════════════✨\n"
            f"   🏰  **LORDLAR XAZINASI SOVUTI**  🏰\n"
            f"✨════════════════════════════✨\n\n"
            f"🌟 Lord: **{user_display_name}**{username_str} | {house_str}\n"
            f"{status_line}"
            f"🎖️ Sharafli Unvon: «**{escape_md(user.title or 'Saxiy Lord')}**»\n"
            f"{audio_line}"
            f"🎖️ {user.rank.title()} | ⭐ Lv.{lvl}/30 ({lvl_title}) | 🏆 {user.prestige:,} Prestige\n"
            f"📈 `[{prog_bar}]` {user.xp:,}/{next_req:,} XP ({int(progress)}%)\n"
            f"{art_str}"
            f"🔰 Qalqon: {shield_str}\n\n"
            f"📊 **Xazina:** 🪙**{user.gold:,}** (+{income['gold']}/s) | 🌾**{user.food:,}** ({net_food_str}/s) | ⛓️**{user.iron:,}** (+{income['iron']}/s)\n"
            f"⚔️ **Qo'shin:** 🛡️{inf_cnt:,} | 🏹{arc_cnt:,} | 🐎{cav_cnt:,} | 🗡️{spm_cnt:,} | 🔥{spc_cnt:,}\n"
            f"{dragon_line}\n"
            f"✨💎✨ _Lordlar Xazinasi bilan qurollangan_ ✨💎✨"
        )

    # 4. STANDART LORD PROFILI (KNIGHT / BEPUL)
    else:
        title_badge = f"🎖️ Sharafli Unvon: **{escape_md(user.title)}**\n" if getattr(user, "title", None) else ""
        status_line = f"📜 Shior: «*{escape_md(user.custom_status)}*»\n" if user.custom_status else ""
        text = (
            f"👤 **LORD PROFILI**\n\n"
            f"👑 **{user_display_name}**{username_str} | {house_str}\n"
            f"{title_badge}"
            f"{status_line}"
            f"🎖️ {user.rank.title()} | ⭐ Lv.{lvl}/30 ({lvl_title}) | 🏆 {user.prestige:,} Prestige\n"
            f"📈 `[{prog_bar}]` {user.xp:,}/{next_req:,} XP ({int(progress)}%)\n"
            f"{art_str}"
            f"🔰 Qalqon: {shield_str}\n\n"
            f"📊 **Xazina:** 🪙**{user.gold:,}** (+{income['gold']}/s) | 🌾**{user.food:,}** ({net_food_str}/s) | ⛓️**{user.iron:,}** (+{income['iron']}/s)\n"
            f"⚔️ **Qo'shin:** 🛡️{inf_cnt:,} | 🏹{arc_cnt:,} | 🐎{cav_cnt:,} | 🗡️{spm_cnt:,} | 🔥{spc_cnt:,}\n"
            f"{dragon_line}"
        )

    photo_id = user.custom_photo_file_id if vip in ["lord", "dragonlord", "sovereign"] else None
    audio_id = user.custom_audio_file_id if vip in ["lord", "dragonlord", "sovereign"] else None
    audio_title = user.custom_audio_title if vip in ["lord", "dragonlord", "sovereign"] else None

    return text, photo_id, audio_id, audio_title


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/profile, /profil, /me buyrug'i (Guruh yoki Shaxsiy chat)"""
    chat = update.effective_chat
    if chat and chat.type in ["group", "supergroup"]:
        await group_profile_handler(update, context)
        return

    user_id = update.effective_user.id
    await show_profile(update, user_id, is_message=True)


async def group_profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruhda o'yinchi profilini ko'rsatish (Reply qilingan bo'lsa suhbatdosh, aks holda yozgan lord)"""
    msg = update.effective_message
    if not msg:
        return

    target_tg = update.effective_user
    is_reply = False
    if msg.reply_to_message and msg.reply_to_message.from_user:
        if not msg.reply_to_message.from_user.is_bot:
            target_tg = msg.reply_to_message.from_user
            is_reply = True

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, target_tg.id)
        if not user:
            reply_who = f"**{escape_md(target_tg.full_name)}**" if is_reply else "Siz"
            await msg.reply_text(
                f"❌ {reply_who} hali Westeros olamida ro'yxatdan o'tmagan.\n"
                f"🎮 O'yinni boshlash uchun botga kiring: @ironthrone_rpgbot",
                parse_mode="Markdown"
            )
            return

        if target_tg.username and user.username != target_tg.username:
            user.username = target_tg.username
            await session.commit()

        text, photo_id, audio_id, audio_title = await format_user_profile_card(user, session, is_group=True)

    # Guruhda pastki qotib qolgan klaviaturani butunlay yo'qotish:
    from telegram import ReplyKeyboardRemove
    clean_kb = ReplyKeyboardRemove()

    # Guruhga rasm yoki matn bilan yuborish
    if photo_id:
        try:
            await msg.reply_photo(photo=photo_id, caption=text, parse_mode="Markdown", reply_markup=clean_kb)
        except Exception as e:
            logger.warning(f"Guruhga rasm bilan profil yuborish xatosi: {e}")
            await msg.reply_text(text, parse_mode="Markdown", reply_markup=clean_kb)
    else:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=clean_kb)

    # Agar o'yinchi musiqasi bo'lsa audio ham yuboriladi
    if audio_id:
        try:
            await msg.reply_audio(
                audio=audio_id,
                title=audio_title or "Lord Gimni",
                performer=user.full_name or "Westeros Lord"
            )
        except Exception as e:
            logger.warning(f"Guruhga audio yuborish xatosi: {e}")


async def group_show_my_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruhda inline tugma orqali har bir lord o'z profilini chaqirishi"""
    query = update.callback_query
    await query.answer()

    clicker_tg = query.from_user
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, clicker_tg.id)
        if not user:
            await query.answer("❌ Siz hali Westerosda ro'yxatdan o'tmagansiz!", show_alert=True)
            return

        if clicker_tg.username and user.username != clicker_tg.username:
            user.username = clicker_tg.username
            await session.commit()

        text, photo_id, audio_id, audio_title = await format_user_profile_card(user, session, is_group=True)

    from telegram import ReplyKeyboardRemove
    clean_kb = ReplyKeyboardRemove()

    if photo_id:
        try:
            await query.message.reply_photo(photo=photo_id, caption=text, parse_mode="Markdown", reply_markup=clean_kb)
        except Exception:
            await query.message.reply_text(text, parse_mode="Markdown", reply_markup=clean_kb)
    else:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=clean_kb)


async def clean_keyboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruh yoki shaxsiy chatdagi qolib ketgan pastki tugmalarni tozalash"""
    from telegram import ReplyKeyboardRemove
    await update.effective_message.reply_text(
        "🧹 Pastki klaviatura muvaffaqiyatli tozalandi va olib tashlandi!",
        reply_markup=ReplyKeyboardRemove()
    )

    if audio_id:
        try:
            await query.message.reply_audio(
                audio=audio_id,
                title=audio_title or "Lord Gimni",
                performer=user.full_name or "Westeros Lord"
            )
        except Exception:
            pass


async def profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_profile callback"""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("awaiting_char_name_change", None)
    user_id = query.from_user.id
    await show_profile(query, user_id, is_message=False)


async def show_profile(target, user_id: int, is_message: bool):
    """Profil ma'lumotlarini formatlab chiqarish (Shaxsiy chat)"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            msg = "❌ Siz hali ro'yxatdan o'tmagansiz. /start ni bosing."
            if is_message:
                await target.message.reply_text(msg)
            else:
                await target.edit_message_text(msg)
            return

        text, photo_id, audio_id, audio_title = await format_user_profile_card(user, session, is_group=False)

    buttons = []
    # VIP bo'lsa profil studiyasi tugmasi chiqadi
    if getattr(user, "vip_tier", None) in ["lord", "dragonlord", "sovereign"]:
        buttons.append([InlineKeyboardButton("✨ VIP Profil Studiyasi", callback_data="menu_vip_custom")])

    buttons.append([InlineKeyboardButton("✏️ Ismni O'zgartirish", callback_data="profile_change_name")])
    buttons.append([InlineKeyboardButton("⛏️ Kon & 🌾 Tegirmon", callback_data="menu_iron_mine")])
    buttons.append([InlineKeyboardButton("🗡️ Afsonaviy Artefaktlar (Armory)", callback_data="menu_artifacts")])
    buttons.append([InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")])
    markup = InlineKeyboardMarkup(buttons)

    if is_message:
        if photo_id:
            try:
                await target.message.reply_photo(photo=photo_id, caption=text, parse_mode="Markdown", reply_markup=markup)
                return
            except Exception:
                pass
        await target.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        msg_obj = getattr(target, "message", None)
        if msg_obj and getattr(msg_obj, "photo", None):
            try:
                await target.edit_message_caption(caption=text, parse_mode="Markdown", reply_markup=markup)
                return
            except Exception:
                pass
        try:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


# ============================================================
# VIP PROFIL SOZLAMALARI STUDIYASI (STUDIO & CUSTOMIZATION)
# ============================================================

async def vip_custom_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """VIP Profil Studiyasi Menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user or not user.vip_tier or user.vip_tier == "knight":
            await query.answer("❌ Ushbu bo'lim faqat VIP (Lord, Valyriya, Temir Taxt) egalari uchundir!", show_alert=True)
            return

        tier_names = {
            "lord": "🏰 Lordlar Xazinasi",
            "dragonlord": "🐉 Valyriya Merosi",
            "sovereign": "👑 Temir Taxt Sohibi"
        }
        tier_title = tier_names.get(user.vip_tier, user.vip_tier)

        photo_status = "✅ O'rnatilgan" if user.custom_photo_file_id else "❌ O'rnatilmagan"
        status_status = f"«{escape_md(user.custom_status)}»" if user.custom_status else "❌ O'rnatilmagan"
        audio_status = f"🎶 «{escape_md(user.custom_audio_title)}»" if (user.custom_audio_file_id or user.custom_audio_title) else "❌ O'rnatilmagan"

        decree_line = ""
        if user.vip_tier == "sovereign":
            decree_line = f"• 📜 Qirollik Farmoni huquqi: **{user.royal_decree_count or 0} ta**\n"

        text = (
            f"✨👑 **VIP PROFIL SOZLAMALARI STUDIYASI** 👑✨\n\n"
            f"Sizning VIP maqomingiz: **{tier_title}**\n\n"
            f"📸 **Profil fotosurati:** {photo_status}\n"
            f"✍️ **Shaxsiy shior / status:** {status_status}\n"
            f"🎵 **Fon musiqasi / gimn:** {audio_status}\n"
            f"{decree_line}\n"
            f"Quyidagi tugmalar orqali profilingizni bezating va sozlang:"
        )

        buttons = []

        # Rasm (Lord, Valyriya, Sovereign)
        buttons.append([InlineKeyboardButton("📸 Profil Rasmini O'rnatish / Yangilash", callback_data="vip_set_photo")])
        if user.custom_photo_file_id:
            buttons.append([InlineKeyboardButton("🗑️ Rasmni Olib Tashlash", callback_data="vip_remove_photo")])

        # Status & Audio (Lord, Dragonlord, Sovereign)
        if user.vip_tier in ["lord", "dragonlord", "sovereign"]:
            buttons.append([InlineKeyboardButton("✍️ Shaxsiy Shior Yozish", callback_data="vip_set_status")])
            if user.custom_status:
                buttons.append([InlineKeyboardButton("🗑️ Shiorni Olib Tashlash", callback_data="vip_remove_status")])
            buttons.append([InlineKeyboardButton("🎵 Fon Musiqasi / Gimn Tanlash", callback_data="vip_set_audio")])

        # Qirollik Farmoni (Sovereign)
        if user.vip_tier == "sovereign":
            buttons.append([InlineKeyboardButton("📢 Butun Vesterosga Qirol Farmoni Chiqarish", callback_data="vip_decree_prompt")])

        buttons.append([InlineKeyboardButton("👁️ Yaltiroq Profil Ko'rinishini Sinash", callback_data="vip_preview")])
        buttons.append([InlineKeyboardButton("🔙 Profilga Qaytish", callback_data="menu_profile")])

        markup = InlineKeyboardMarkup(buttons)
        msg_obj = getattr(query, "message", None)
        if msg_obj and getattr(msg_obj, "photo", None):
            await query.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
        else:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")


async def vip_set_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rasm yuklashni boshlash"""
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_vip_photo"] = True
    context.user_data.pop("awaiting_vip_status", None)
    context.user_data.pop("awaiting_vip_audio", None)
    context.user_data.pop("awaiting_vip_decree", None)

    text = (
        "📸 **PROFIL FOTOSURATINI YUKLASH**\n\n"
        "Hurmatli Lord! O'z profilingiz uchun fotosuratni (rasm shaklida) botga yuboring.\n"
        "Yuborilgan fotosurat guruhda va botda profilingiz chaqirilganda porlab chiqadi!\n\n"
        "💡 _Bekor qilish uchun /cancel deb yozing._"
    )
    await query.message.reply_text(text, parse_mode="Markdown")


async def vip_remove_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rasmni olib tashlash"""
    query = update.callback_query
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if user:
            await crud.update_user_custom_photo(session, user.id, None)

    await query.answer("🗑️ Profil fotosurati olib tashlandi.", show_alert=True)
    await vip_custom_menu_callback(update, context)


async def vip_set_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shaxsiy shior / status kiritishni boshlash"""
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_vip_status"] = True
    context.user_data.pop("awaiting_vip_photo", None)
    context.user_data.pop("awaiting_vip_audio", None)
    context.user_data.pop("awaiting_vip_decree", None)

    text = (
        "✍️ **SHAXSIY SHIOR / STATUS YOZISH**\n\n"
        "Profilingizda aks etuvchi shaxsiy shior yoki matnni yozib yuboring (maksimal 100 belgi).\n"
        "Masalan: _«Qish yaqinlashmoqda, olov esa bizning qonimizda!»_\n\n"
        "💡 _Bekor qilish uchun /cancel deb yozing._"
    )
    await query.message.reply_text(text, parse_mode="Markdown")


async def vip_remove_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statusni olib tashlash"""
    query = update.callback_query
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if user:
            await crud.update_user_custom_status(session, user.id, None)

    await query.answer("🗑️ Shaxsiy shior olib tashlandi.", show_alert=True)
    await vip_custom_menu_callback(update, context)


async def vip_set_audio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fon musiqasi tanlash menyusi"""
    query = update.callback_query
    await query.answer()

    text = (
        "🎵 **PROFIL FON MUSIQASI VA GIMNI**\n\n"
        "Guruhda profilingiz so'ralganda, profilingiz bilan birga o'ziga xos audio trek ham ijro etiladi!\n\n"
        "Quyidagi mashhur Game of Thrones kuylaridan birini tanlang yoki o'zingizning shaxsiy MP3 audio faylingizni yuboring:"
    )

    buttons = []
    for k, v in GOT_AUDIO_PRESETS.items():
        buttons.append([InlineKeyboardButton(f"{v['desc']}", callback_data=f"vip_audio_pick:{k}")])

    buttons.append([InlineKeyboardButton("📤 O'z MP3 Audio Faylingizni Yuklash", callback_data="vip_audio_upload_prompt")])
    buttons.append([InlineKeyboardButton("🗑️ Musiqani Olib Tashlash", callback_data="vip_audio_remove")])
    buttons.append([InlineKeyboardButton("🔙 VIP Studiyaga Qaytish", callback_data="menu_vip_custom")])

    markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")


async def vip_audio_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kutubxonadan tayyor trek tanlash"""
    query = update.callback_query
    preset_key = query.data.split(":")[1]
    user_id = query.from_user.id

    preset = GOT_AUDIO_PRESETS.get(preset_key)
    if not preset:
        await query.answer("Xatolik.")
        return

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if user:
            await crud.update_user_custom_audio(session, user.id, None, preset["title"])

    await query.answer(f"🎵 «{preset['title']}» treki biriktirildi!", show_alert=True)
    try:
        await query.message.reply_text(
            f"🎵 **GIMN BIRIKTIRILDI: «{escape_md(preset['title'])}»**\n\n"
            f"Profilingiz va guruh kartochkangizda ushbu gimn nomi porlab turadi.\n\n"
            f"💡 _Eslatma: Guruhda profilingiz so'ralganda to'liq musiqa fayli (audio) yangrashini xohlasangiz, "
            f"istalgan MP3 yoki ovozli xabarni botga yuborishingiz mumkin!_",
            parse_mode="Markdown"
        )
    except Exception:
        pass
    await vip_custom_menu_callback(update, context)


async def vip_audio_upload_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'z audio faylini yuklashni so'rash"""
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_vip_audio"] = True
    context.user_data.pop("awaiting_vip_photo", None)
    context.user_data.pop("awaiting_vip_status", None)
    context.user_data.pop("awaiting_vip_decree", None)

    text = (
        "📤 **SHAXSIY MP3 AUDIO YUKLASH**\n\n"
        "Hurmatli Lord! Telegram orqali istalgan musiqa faylini (audio yoki ovozli xabar) shu yerga yuboring.\n"
        "Guruhda profilingiz chaqirilganda ushbu musiqangiz tantanali ravishda ijro etiladi!\n\n"
        "💡 _Bekor qilish uchun /cancel deb yozing._"
    )
    await query.message.reply_text(text, parse_mode="Markdown")


async def vip_audio_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Musiqani o'chirish"""
    query = update.callback_query
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if user:
            await crud.update_user_custom_audio(session, user.id, None, None)

    await query.answer("🗑️ Fon musiqasi olib tashlandi.", show_alert=True)
    await vip_custom_menu_callback(update, context)


async def vip_decree_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qirollik Farmoni chiqarish oynasi (Sovereign)"""
    query = update.callback_query
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user or user.vip_tier != "sovereign":
            await query.answer("❌ Bu huquq faqat «👑 Temir Taxt Sohibi» imperatorlariga xosdir!", show_alert=True)
            return

        cnt = getattr(user, "royal_decree_count", 0) or 0
        if cnt <= 0:
            await query.answer("❌ Sizda mavjud Qirollik Farmoni chiqarish huquqlari qolmagan.", show_alert=True)
            return

    await query.answer()
    context.user_data["awaiting_vip_decree"] = True
    context.user_data.pop("awaiting_vip_photo", None)
    context.user_data.pop("awaiting_vip_status", None)
    context.user_data.pop("awaiting_vip_audio", None)

    text = (
        f"👑📜 **BUYUK VESTEROS QIROLLIK FARMONI** 📜👑\n\n"
        f"Buyuk Hukmdor! Siz butun Vesteros xonadonlari, rasmiy kanal ({COMMUNITY_CHANNEL_URL}) "
        f"va guruhga ({COMMUNITY_GROUP_URL}) o'z nomingizdan imperatorlik farmonini e'lon qilishingiz mumkin!\n\n"
        f"Sizda qolgan farmonlar: **{cnt} ta**\n\n"
        f"Farmon matnini yozib yuboring (yoki bekor qilish uchun /cancel deb yozing):"
    )
    await query.message.reply_text(text, parse_mode="Markdown")


async def vip_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yaltiroq profil ko'rinishini sinovdan o'tkazish"""
    query = update.callback_query
    await query.answer("✨ Profil aulasi sinovdan o'tkazilmoqda...")
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return
        text, photo_id, audio_id, audio_title = await format_user_profile_card(user, session, is_group=False)

    if photo_id:
        try:
            await query.message.reply_photo(photo=photo_id, caption=text, parse_mode="Markdown")
        except Exception:
            await query.message.reply_text(text, parse_mode="Markdown")
    else:
        await query.message.reply_text(text, parse_mode="Markdown")

    if audio_id:
        try:
            await query.message.reply_audio(
                audio=audio_id,
                title=audio_title or "Lord Gimni",
                performer=user.full_name or "Westeros Lord"
            )
        except Exception:
            pass


async def profile_change_name_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qahramon ismini o'zgartirish oynasi"""
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_char_name_change"] = True
    context.user_data.pop("awaiting_vip_photo", None)
    context.user_data.pop("awaiting_vip_status", None)
    context.user_data.pop("awaiting_vip_audio", None)
    context.user_data.pop("awaiting_vip_decree", None)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Bekor qilish", callback_data="menu_profile")]
    ])
    text = (
        "✏️ **QAHRAMON ISMINGIZNI O'ZGARTIRISH**\n\n"
        "O'zingiz yoki qahramoningiz uchun yangi ism kiriting (2 tadan 30 tagacha belgi):\n"
        "Masalan: `Aegon Targaryen`, `Jon Snow`, `Daenerys`\n\n"
        "💡 _Bekor qilish uchun quyidagi tugmani bosing yoki /cancel deb yozing._"
    )
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def change_name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/rename yoki /ism buyrug'i"""
    user_id = update.effective_user.id
    if not context.args or len(context.args) == 0:
        context.user_data["awaiting_char_name_change"] = True
        context.user_data.pop("awaiting_vip_photo", None)
        context.user_data.pop("awaiting_vip_status", None)
        context.user_data.pop("awaiting_vip_audio", None)
        context.user_data.pop("awaiting_vip_decree", None)

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Bekor qilish", callback_data="menu_profile")]
        ])
        await update.message.reply_text(
            "✏️ **QAHRAMON ISMINGIZNI O'ZGARTIRISH**\n\n"
            "O'zingiz yoki qahramoningiz uchun yangi ism kiriting (2 tadan 30 tagacha belgi):\n"
            "Masalan: `Aegon Targaryen`, `Jon Snow`, `Daenerys`\n\n"
            "💡 _Yoki to'g'ridan-to'g'ri: `/rename Yangi Ism`_",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return

    new_name = " ".join(context.args).strip()
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        ok, res_msg = await crud.change_character_name(session, user.id, new_name)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Profilni Ko'rish", callback_data="menu_profile")]
    ])
    if ok:
        await update.message.reply_text(
            f"🎉 **Qahramon ismingiz muvaffaqiyatli «{escape_md(res_msg)}» ga o'zgartirildi!**",
            reply_markup=kb,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(res_msg, reply_markup=kb, parse_mode="Markdown")


async def vip_input_receiver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """VIP Profil sozlamalari va ism o'zgartirish bo'yicha foydalanuvchi kiritmalarini qabul qilish"""
    msg = update.effective_message
    if not msg:
        return

    user_id = update.effective_user.id
    u_data = context.user_data

    # 0. Qahramon ismini o'zgartirish
    if u_data.get("awaiting_char_name_change"):
        if msg.text and msg.text.lower() in ["/cancel", "bekor"]:
            u_data.pop("awaiting_char_name_change", None)
            await msg.reply_text("❌ Ismni o'zgartirish bekor qilindi.", reply_markup=back_to_main_keyboard())
            return
        elif msg.text and not msg.text.startswith("/"):
            new_name = msg.text.strip()
            async with AsyncSessionLocal() as session:
                user = await crud.get_user_by_telegram_id(session, user_id)
                if not user:
                    u_data.pop("awaiting_char_name_change", None)
                    return
                ok, res_msg = await crud.change_character_name(session, user.id, new_name)

            if ok:
                u_data.pop("awaiting_char_name_change", None)
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("👤 Profilni Ko'rish", callback_data="menu_profile")],
                    [InlineKeyboardButton("🔙 Asosiy Menyu", callback_data="menu_main")]
                ])
                await msg.reply_text(
                    f"🎉 **QAHRAMON ISMI MUVOFAQIYATLI O'ZGARTIRILDI!**\n\nYangi ismingiz: **{escape_md(res_msg)}**",
                    reply_markup=kb,
                    parse_mode="Markdown"
                )
            else:
                await msg.reply_text(f"{res_msg}\n\nIltimos, boshqa ism yuboring yoki /cancel deb yozing.")
            return

    # 1. Rasm kiritish
    if u_data.get("awaiting_vip_photo"):
        photo_file_id = None
        if msg.photo:
            photo_file_id = msg.photo[-1].file_id
        elif msg.document and (msg.document.mime_type or "").startswith("image/"):
            photo_file_id = msg.document.file_id

        if photo_file_id:
            async with AsyncSessionLocal() as session:
                user = await crud.get_user_by_telegram_id(session, user_id)
                if user:
                    ok, res_msg = await crud.update_user_custom_photo(session, user.id, photo_file_id)
            u_data.pop("awaiting_vip_photo", None)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✨ VIP Studiyaga Qaytish", callback_data="menu_vip_custom")],
                [InlineKeyboardButton("👤 Profilni Ko'rish", callback_data="menu_profile")],
            ])
            await msg.reply_text(f"🎉 **AJOYIB!**\n\n{res_msg}", reply_markup=kb, parse_mode="Markdown")
            return
        elif msg.text and msg.text.lower() in ["/cancel", "bekor"]:
            u_data.pop("awaiting_vip_photo", None)
            await msg.reply_text("❌ Rasm o'rnatish bekor qilindi.", reply_markup=back_to_main_keyboard())
            return
        else:
            await msg.reply_text("⚠️ Iltimos, fotosurat (rasm) yuboring yoki bekor qilish uchun /cancel deb yozing.")
            return

    # 2. Status / Shior kiritish
    if u_data.get("awaiting_vip_status"):
        if msg.text and not msg.text.startswith("/"):
            async with AsyncSessionLocal() as session:
                user = await crud.get_user_by_telegram_id(session, user_id)
                if user:
                    ok, res_msg = await crud.update_user_custom_status(session, user.id, msg.text)
                else:
                    ok, res_msg = False, "Foydalanuvchi topilmadi."
            u_data.pop("awaiting_vip_status", None)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✨ VIP Studiyaga Qaytish", callback_data="menu_vip_custom")],
                [InlineKeyboardButton("👤 Profilni Ko'rish", callback_data="menu_profile")],
            ])
            try:
                await msg.reply_text(f"🎉 **STATUS SAQLANDI!**\n\n{escape_md(res_msg)}", reply_markup=kb, parse_mode="Markdown")
            except Exception:
                await msg.reply_text(f"🎉 STATUS SAQLANDI!\n\n{res_msg}", reply_markup=kb)
            return
        elif msg.text and msg.text.lower() in ["/cancel", "bekor"]:
            u_data.pop("awaiting_vip_status", None)
            await msg.reply_text("❌ Shior o'rnatish bekor qilindi.", reply_markup=back_to_main_keyboard())
            return

    # 3. Audio kiritish (yoki to'g'ridan-to'g'ri audio yuborish)
    is_audio_msg = bool(
        msg.audio or msg.voice or (
            msg.document and (
                (msg.document.mime_type or "").startswith("audio/")
                or (msg.document.file_name or "").lower().endswith((".mp3", ".m4a", ".ogg", ".wav"))
            )
        )
    )

    if u_data.get("awaiting_vip_audio") or is_audio_msg:
        audio_file_id = None
        audio_title = "Lord Gimni"
        if msg.audio:
            audio_file_id = msg.audio.file_id
            audio_title = msg.audio.title or msg.audio.file_name or "Lord Shaxsiy Gimni"
        elif msg.voice:
            audio_file_id = msg.voice.file_id
            audio_title = "Lord Ovozli Gimni"
        elif msg.document and (
            (msg.document.mime_type or "").startswith("audio/")
            or (msg.document.file_name or "").lower().endswith((".mp3", ".m4a", ".ogg", ".wav"))
        ):
            audio_file_id = msg.document.file_id
            audio_title = msg.document.file_name or "Lord Audio Gimni"

        if audio_file_id:
            async with AsyncSessionLocal() as session:
                user = await crud.get_user_by_telegram_id(session, user_id)
                if user and user.vip_tier in ["lord", "dragonlord", "sovereign"]:
                    ok, res_msg = await crud.update_user_custom_audio(session, user.id, audio_file_id, audio_title)
                    u_data.pop("awaiting_vip_audio", None)
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("✨ VIP Studiyaga Qaytish", callback_data="menu_vip_custom")],
                        [InlineKeyboardButton("👤 Profilni Ko'rish", callback_data="menu_profile")],
                    ])
                    try:
                        await msg.reply_text(f"🎉 **FON MUSIQASI O'RNATILDI!**\n\n{escape_md(res_msg)}", reply_markup=kb, parse_mode="Markdown")
                    except Exception:
                        await msg.reply_text(f"🎉 FON MUSIQASI O'RNATILDI!\n\n{res_msg}", reply_markup=kb)
                    return
                elif user:
                    if u_data.get("awaiting_vip_audio"):
                        u_data.pop("awaiting_vip_audio", None)
                        await msg.reply_text("❌ Shaxsiy audio yuklash uchun VIP maqomi kerak.")
                        return
        elif u_data.get("awaiting_vip_audio"):
            if msg.text and msg.text.lower() in ["/cancel", "bekor"]:
                u_data.pop("awaiting_vip_audio", None)
                await msg.reply_text("❌ Musiqa yuklash bekor qilindi.", reply_markup=back_to_main_keyboard())
                return
            else:
                await msg.reply_text("⚠️ Iltimos, audio musiqa fayli yoki ovozli xabar yuboring (bekor qilish: /cancel).")
                return

    # 4. Qirollik Farmoni kiritish (Sovereign)
    if u_data.get("awaiting_vip_decree"):
        if msg.text and not msg.text.startswith("/"):
            decree_text = msg.text.strip()
            async with AsyncSessionLocal() as session:
                user = await crud.get_user_by_telegram_id(session, user_id)
                if not user or user.vip_tier != "sovereign" or (user.royal_decree_count or 0) <= 0:
                    u_data.pop("awaiting_vip_decree", None)
                    await msg.reply_text("❌ Qirollik farmoni chiqarish huquqingiz qolmagan.")
                    return
                await crud.use_royal_decree(session, user.id)
                h_name = user.house.name if user.house else "Qirollik"
                u_name = user.username or user.full_name or "Imperator"

            u_data.pop("awaiting_vip_decree", None)
            now_str = datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")

            decree_post = (
                f"╔══════════════════════════════╗\n"
                f"  👑 **VESTEROS OLIY QIROLLIK FARMONI** 📜\n"
                f"╚══════════════════════════════╝\n\n"
                f"Temir Taxt Sohibi va Vesteros Imperatori **{escape_md(u_name)}** ({escape_md(h_name)}) ning barcha lordlar va xonadonlarga Oliy Farmoni:\n\n"
                f"«*{escape_md(decree_text)}*»\n\n"
                f"👑 **Imzo:** Imperator {escape_md(u_name)}\n"
                f"🏛️ **Muhrlangan:** {now_str}\n"
                f"📢 **Rasmiy Kanal:** {COMMUNITY_CHANNEL_URL}"
            )

            clean_decree = (
                f"👑 VESTEROS OLIY QIROLLIK FARMONI 📜\n\n"
                f"Temir Taxt Sohibi va Vesteros Imperatori {u_name} ({h_name}) ning barcha lordlar va xonadonlarga Oliy Farmoni:\n\n"
                f"«{decree_text}»\n\n"
                f"👑 Imzo: Imperator {u_name}\n"
                f"🏛️ Muhrlangan: {now_str}\n"
                f"📢 Rasmiy Kanal: {COMMUNITY_CHANNEL_URL}"
            )

            chat_targets = set()
            async with AsyncSessionLocal() as session:
                h_res = await session.execute(
                    select(models.House.group_chat_id).where(models.House.group_chat_id.isnot(None))
                )
                for g_id in h_res.scalars().all():
                    if g_id:
                        chat_targets.add(g_id)

            for ch in ["@northremembers1", "@northremember2"]:
                chat_targets.add(ch)

            sent_count = 0
            for chat_target in chat_targets:
                try:
                    await context.bot.send_message(
                        chat_id=chat_target,
                        text=decree_post,
                        parse_mode="Markdown"
                    )
                    sent_count += 1
                except Exception:
                    try:
                        await context.bot.send_message(
                            chat_id=chat_target,
                            text=clean_decree
                        )
                        sent_count += 1
                    except Exception as e:
                        logger.warning(f"Farmonni {chat_target} ga yuborishda xatolik: {e}")

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✨ VIP Studiyaga Qaytish", callback_data="menu_vip_custom")],
                [InlineKeyboardButton("👤 Profilni Ko'rish", callback_data="menu_profile")],
            ])
            success_msg = (
                f"🎉 **QIROLLIK FARMONINGIZ BUTUN WESTEROSGA E'LON QILINDI!**\n\n"
                f"📜 Farmon **{sent_count} ta** manzilga (xonadon guruhlari va rasmiy kanallar) muvaffaqiyatli yetkazildi!"
            )
            try:
                await msg.reply_text(success_msg, reply_markup=kb, parse_mode="Markdown")
            except Exception:
                await msg.reply_text(success_msg, reply_markup=kb)
            return
        elif msg.text and msg.text.lower() in ["/cancel", "bekor"]:
            u_data.pop("awaiting_vip_decree", None)
            await msg.reply_text("❌ Farmon chiqarish bekor qilindi.", reply_markup=back_to_main_keyboard())
            return


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status <shior> yoki /shior <shior> buyrug'i"""
    user_id = update.effective_user.id
    if not context.args:
        context.user_data["awaiting_vip_status"] = True
        context.user_data.pop("awaiting_vip_photo", None)
        context.user_data.pop("awaiting_vip_audio", None)
        context.user_data.pop("awaiting_vip_decree", None)
        await update.message.reply_text(
            "✍️ **SHAXSIY SHIOR / STATUS YOZISH**\n\n"
            "Profilingizda aks etuvchi shaxsiy shior yoki matnni yozib yuboring:\n"
            "Masalan: `Qish yaqinlashmoqda, olov esa qalbimizda!`",
            parse_mode="Markdown"
        )
        return

    text = " ".join(context.args).strip()
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await update.message.reply_text("❌ Avval /start bosing.")
            return
        ok, res_msg = await crud.update_user_custom_status(session, user.id, text)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Profilni Ko'rish", callback_data="menu_profile")],
        [InlineKeyboardButton("✨ VIP Studiya", callback_data="menu_vip_custom")],
    ])
    try:
        await update.message.reply_text(f"🎉 **STATUS SAQLANDI!**\n\n{escape_md(res_msg)}", reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(f"🎉 STATUS SAQLANDI!\n\n{res_msg}", reply_markup=kb)


async def decree_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/farmon <matn> yoki /decree <matn> buyrug'i"""
    user_id = update.effective_user.id
    if not context.args:
        context.user_data["awaiting_vip_decree"] = True
        context.user_data.pop("awaiting_vip_photo", None)
        context.user_data.pop("awaiting_vip_status", None)
        context.user_data.pop("awaiting_vip_audio", None)
        await update.message.reply_text(
            "👑📜 **BUYUK VESTEROS QIROLLIK FARMONI** 📜👑\n\n"
            "Butun Vesteros xonadonlari guruhlariga e'lon qilmoqchi bo'lgan farmoningiz matnini yozib yuboring:",
            parse_mode="Markdown"
        )
        return

    decree_text = " ".join(context.args).strip()
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user or user.vip_tier != "sovereign" or (user.royal_decree_count or 0) <= 0:
            await update.message.reply_text("❌ Qirollik farmoni chiqarish huquqingiz yo'q yoki limit tugagan (Faqat Sovereign uchun).")
            return
        await crud.use_royal_decree(session, user.id)
        h_name = user.house.name if user.house else "Qirollik"
        u_name = user.username or user.full_name or "Imperator"

    now_str = datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")
    decree_post = (
        f"╔══════════════════════════════╗\n"
        f"  👑 **VESTEROS OLIY QIROLLIK FARMONI** 📜\n"
        f"╚══════════════════════════════╝\n\n"
        f"Temir Taxt Sohibi va Vesteros Imperatori **{escape_md(u_name)}** ({escape_md(h_name)}) ning barcha lordlar va xonadonlarga Oliy Farmoni:\n\n"
        f"«*{escape_md(decree_text)}*»\n\n"
        f"👑 **Imzo:** Imperator {escape_md(u_name)}\n"
        f"🏛️ **Muhrlangan:** {now_str}\n"
        f"📢 **Rasmiy Kanal:** {COMMUNITY_CHANNEL_URL}"
    )

    clean_decree = (
        f"👑 VESTEROS OLIY QIROLLIK FARMONI 📜\n\n"
        f"Temir Taxt Sohibi va Vesteros Imperatori {u_name} ({h_name}) ning barcha lordlar va xonadonlarga Oliy Farmoni:\n\n"
        f"«{decree_text}»\n\n"
        f"👑 Imzo: Imperator {u_name}\n"
        f"🏛️ Muhrlangan: {now_str}\n"
        f"📢 Rasmiy Kanal: {COMMUNITY_CHANNEL_URL}"
    )

    chat_targets = set()
    async with AsyncSessionLocal() as session:
        h_res = await session.execute(
            select(models.House.group_chat_id).where(models.House.group_chat_id.isnot(None))
        )
        for g_id in h_res.scalars().all():
            if g_id:
                chat_targets.add(g_id)

    for ch in ["@northremembers1", "@northremember2"]:
        chat_targets.add(ch)

    sent_count = 0
    for chat_target in chat_targets:
        try:
            await context.bot.send_message(
                chat_id=chat_target,
                text=decree_post,
                parse_mode="Markdown"
            )
            sent_count += 1
        except Exception:
            try:
                await context.bot.send_message(
                    chat_id=chat_target,
                    text=clean_decree
                )
                sent_count += 1
            except Exception as e:
                logger.warning(f"Farmonni {chat_target} ga yuborishda xatolik: {e}")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ VIP Studiyaga Qaytish", callback_data="menu_vip_custom")],
        [InlineKeyboardButton("👤 Profilni Ko'rish", callback_data="menu_profile")],
    ])
    await update.message.reply_text(
        f"🎉 **QIROLLIK FARMONINGIZ BUTUN WESTEROSGA E'LON QILINDI!**\n\n"
        f"📜 Farmon **{sent_count} ta** manzilga (xonadon guruhlari va rasmiy kanallar) muvaffaqiyatli yetkazildi!",
        reply_markup=kb,
        parse_mode="Markdown"
    )



async def daily_bonus_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kunlik sovg'alar markaziga yo'naltirish"""
    from handlers.daily_handler import daily_menu_callback
    await daily_menu_callback(update, context)



async def show_artifacts_menu(target, user_id: int, is_message: bool = False, page: int = 0):
    """Afsonaviy artefaktlar qurolxonasi menyusi (ixcham va sahifalangan)"""
    from data.artifacts_data import ARTIFACTS_DATA
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        user_arts = await crud.get_user_artifacts(session, user.id)
        equipped = await crud.get_equipped_artifact(session, user.id)

    owned_map = {a.code: a for a in user_arts}

    eq_str = "_Hech narsa taqilmagan_"
    if equipped and equipped.code in ARTIFACTS_DATA:
        info = ARTIFACTS_DATA[equipped.code]
        eq_str = f"**{info['name']}**"

    all_items = list(ARTIFACTS_DATA.items())
    PAGE_SIZE = 4
    total_pages = max(1, (len(all_items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_items = all_items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    text = (
        f"🗡️ **AFSONAVIY ARTEFAKTLAR (ARMORY)**\n"
        f"⚔️ **Taqilgan:** {eq_str}\n"
        f"💰 **Xazina:** **{user.gold:,}**🪙 Oltin | **{user.iron:,}**⛓️ Temir\n"
        f"📄 Sahifa: **{page + 1} / {total_pages}**\n\n"
    )

    buttons = []
    for code, data in page_items:
        is_owned = code in owned_map
        is_eq = is_owned and owned_map[code].is_equipped
        bonus_desc = []
        if data.get("duel_bonus", 0) > 0:
            bonus_desc.append(f"Duel +{int(data['duel_bonus']*100)}%")
        if data.get("attack_bonus", 0) > 0:
            bonus_desc.append(f"Hujum +{int(data['attack_bonus']*100)}%")
        if data.get("defense_bonus", 0) > 0:
            bonus_desc.append(f"Mudofaa +{int(data['defense_bonus']*100)}%")
        if data.get("dragon_bonus", 0) > 0:
            bonus_desc.append(f"Drakarys +{int(data['dragon_bonus']*100)}%")

        bonus_str = ", ".join(bonus_desc) if bonus_desc else "Maxsus afzallik"
        status_tag = "✅ Sizda bor" if is_owned else f"{data['price_gold']:,}🪙/{data['price_iron']:,}⛓️"

        text += (
            f"• **{data['name']}** ({status_tag})\n"
            f"  ⚡ *{bonus_str}*\n"
        )

        if is_owned:
            art_id = owned_map[code].id
            if is_eq:
                buttons.append([InlineKeyboardButton(f"🚫 {data['name'][:20]} (Yechish)", callback_data=f"unequip_art:{page}")])
            else:
                buttons.append([InlineKeyboardButton(f"⚡ {data['name'][:20]} (Taqish)", callback_data=f"equip_art_{art_id}:{page}")])
        else:
            buttons.append([InlineKeyboardButton(f"🛒 Xarid: {data['name'][:18]} ({data['price_gold']:,}🪙)", callback_data=f"buy_art_{code}:{page}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"menu_art_pg:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"menu_art_pg:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("🔙 Profilga Qaytish", callback_data="menu_profile")])

    if is_message:
        await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def show_iron_mine_menu(target, user_id: int, is_message: bool = False):
    """Temir koni va oltin-temir savdo karvoni menyusi (ixcham ko'rinish)"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return

        mine_lvl = user.iron_mine_level or 1
        curr_prod = mine_lvl * 50
        next_prod = (mine_lvl + 1) * 50
        gold_cost = mine_lvl * 400
        food_cost = mine_lvl * 250

        mill_lvl = getattr(user, "grain_mill_level", 1) or 1
        mill_prod = mill_lvl * 75
        mill_next_prod = (mill_lvl + 1) * 75
        mill_gold_cost = mill_lvl * 350
        mill_iron_cost = mill_lvl * 200

        text = (
            f"⛏️ **TEMIR KONI VA DON TEGIRMONI**\n"
            f"💰 **Xazina:** {user.gold:,}🪙 | {user.food:,}🌾 | {user.iron:,}⛓️\n\n"
            f"⛏️ **Kon:** Lv.{mine_lvl}/10 (+{curr_prod}⛓️/s)"
        )
        if mine_lvl < 10:
            text += f" | Keyingi: {gold_cost:,}🪙 {food_cost:,}🌾\n"
        else:
            text += " (MAX)\n"

        text += f"🌾 **Tegirmon:** Lv.{mill_lvl}/10 (+{mill_prod}🌾/s)"
        if mill_lvl < 10:
            text += f" | Keyingi: {mill_gold_cost:,}🪙 {mill_iron_cost:,}⛓️\n\n"
        else:
            text += " (MAX)\n\n"

        text += (
            f"🌾 **Oziq-ovqat Zaxirasi (Don):**\n"
            f"• Xarid: 300🪙➡️390🌾 | 500🪙➡️700🌾 | 1k🪙➡️1,500🌾\n"
            f"• Sotish: 500🌾➡️250🪙 | 1k🌾➡️500🪙 | 5k🌾➡️2,500🪙 `(/sellfood 1000)`\n\n"
            f"⛓️ **Temir Zaxirasi:**\n"
            f"• Xarid: 500🪙➡️300⛓️ | 1k🪙➡️700⛓️ | 2.5k🪙➡️1,900⛓️\n"
            f"• Sotish: 300⛓️➡️300🪙 | 700⛓️➡️700🪙 | 1.5k⛓️➡️1,500🪙 `(/selliron 500)`\n"
        )

        buttons = []
        up_row = []
        if mine_lvl < 10:
            up_row.append(InlineKeyboardButton(f"⛏️ Kon Lv.{mine_lvl + 1}", callback_data="upgrade_iron_mine"))
        if mill_lvl < 10:
            up_row.append(InlineKeyboardButton(f"🌾 Tegirmon Lv.{mill_lvl + 1}", callback_data="upgrade_grain_mill"))
        if up_row:
            buttons.append(up_row)

        buttons.append([
            InlineKeyboardButton("🌾 390 (300🪙)", callback_data="buy_food:food_1"),
            InlineKeyboardButton("🌾 700 (500🪙)", callback_data="buy_food:food_2"),
            InlineKeyboardButton("🌾 1.5k (1k🪙)", callback_data="buy_food:food_3"),
        ])
        buttons.append([
            InlineKeyboardButton("🌾 4k (2.5k🪙)", callback_data="buy_food:food_4"),
            InlineKeyboardButton("🌾 9k (5k🪙)", callback_data="buy_food:food_5"),
        ])
        buttons.append([
            InlineKeyboardButton("⛓️ 300 (500🪙)", callback_data="buy_iron:pack_1"),
            InlineKeyboardButton("⛓️ 700 (1k🪙)", callback_data="buy_iron:pack_2"),
        ])
        buttons.append([
            InlineKeyboardButton("⛓️ 1.9k (2.5k🪙)", callback_data="buy_iron:pack_3"),
            InlineKeyboardButton("⛓️ 4.2k (5k🪙)", callback_data="buy_iron:pack_4"),
        ])
        buttons.append([
            InlineKeyboardButton("💰 500🌾➡️250🪙", callback_data="sell_res:food:500"),
            InlineKeyboardButton("💰 1k🌾➡️500🪙", callback_data="sell_res:food:1000"),
            InlineKeyboardButton("💰 5k🌾➡️2.5k🪙", callback_data="sell_res:food:5000"),
        ])
        buttons.append([
            InlineKeyboardButton("💰 300⛓️➡️300🪙", callback_data="sell_res:iron:300"),
            InlineKeyboardButton("💰 700⛓️➡️700🪙", callback_data="sell_res:iron:700"),
            InlineKeyboardButton("💰 1.5k⛓️➡️1.5k🪙", callback_data="sell_res:iron:1500"),
        ])
        buttons.append([
            InlineKeyboardButton("🔙 Profilga Qaytish", callback_data="menu_profile"),
            InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main"),
        ])

    if is_message:
        await target.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def iron_mine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mine, /iron, /kon buyruqlari"""
    user_id = update.effective_user.id
    await show_iron_mine_menu(update, user_id, is_message=True)


async def buy_food_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/buyfood, /food, /oziq, /bozor buyruqlari"""
    user_id = update.effective_user.id
    if context.args and len(context.args) > 0:
        arg = context.args[0].strip()
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, user_id)
            if not user:
                await update.message.reply_text("❌ Avval /start bosing.")
                return
            ok, msg = await crud.buy_food_with_gold(session, user.id, arg)
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

    await show_iron_mine_menu(update, user_id, is_message=True)


async def iron_mine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_iron_mine callback"""
    query = update.callback_query
    await query.answer()
    await show_iron_mine_menu(query, query.from_user.id, is_message=False)


async def upgrade_mine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Temir konini yangilash callback"""
    query = update.callback_query
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.upgrade_iron_mine(session, user.id)

    await query.answer(msg, show_alert=True)
    await show_iron_mine_menu(query, user_id, is_message=False)


async def upgrade_grain_mill_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Don tegirmonini yangilash callback"""
    query = update.callback_query
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.upgrade_grain_mill(session, user.id)

    await query.answer(msg, show_alert=True)
    await show_iron_mine_menu(query, user_id, is_message=False)


async def buy_iron_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oltin evaziga temir xarid qilish callback"""
    query = update.callback_query
    pack_code = query.data.replace("buy_iron:", "")
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.buy_iron_with_gold(session, user.id, pack_code)

    await query.answer(msg, show_alert=True)
    await show_iron_mine_menu(query, user_id, is_message=False)


async def buy_food_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oltin evaziga oziq-ovqat xarid qilish callback"""
    query = update.callback_query
    pack_code = query.data.replace("buy_food:", "")
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.buy_food_with_gold(session, user.id, pack_code)

    await query.answer(msg, show_alert=True)
    await show_iron_mine_menu(query, user_id, is_message=False)


async def sell_res_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resurslarni oltinga sotish callback"""
    query = update.callback_query
    parts = query.data.split(":")
    res_type = parts[1]
    amount = int(parts[2])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        if res_type == "food":
            ok, msg = await crud.sell_food_for_gold(session, user.id, amount)
        else:
            ok, msg = await crud.sell_iron_for_gold(session, user.id, amount)

    try:
        await query.answer(msg.replace("**", "").replace("*", ""), show_alert=True)
    except Exception:
        pass
    await show_iron_mine_menu(query, user_id, is_message=False)


async def sell_food_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sellfood <miqdor> buyrug'i"""
    user_id = update.effective_user.id
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("ℹ️ Don sotish uchun miqdorni yozing: `/sellfood 1000`\n(Kurs: 2 Don = 1 Oltin)", parse_mode="Markdown")
        return
    try:
        amt = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("❌ Miqdor faqat son bo'lishi kerak! Masalan: `/sellfood 1000`", parse_mode="Markdown")
        return

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        ok, msg = await crud.sell_food_for_gold(session, user.id, amt)
    await update.message.reply_text(msg, parse_mode="Markdown")


async def sell_iron_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/selliron <miqdor> buyrug'i"""
    user_id = update.effective_user.id
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("ℹ️ Temir sotish uchun miqdorni yozing: `/selliron 500`\n(Kurs: 1 Temir = 1 Oltin)", parse_mode="Markdown")
        return
    try:
        amt = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("❌ Miqdor faqat son bo'lishi kerak! Masalan: `/selliron 500`", parse_mode="Markdown")
        return

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            return
        ok, msg = await crud.sell_iron_for_gold(session, user.id, amt)
    await update.message.reply_text(msg, parse_mode="Markdown")


async def artifacts_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_artifacts_menu(query, query.from_user.id, is_message=False, page=0)


async def artifacts_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split(":")[1]) if ":" in query.data else 0
    await show_artifacts_menu(query, query.from_user.id, is_message=False, page=page)


async def buy_artifact_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    raw = query.data.replace("buy_art_", "")
    parts = raw.split(":")
    code = parts[0]
    page = int(parts[1]) if len(parts) > 1 else 0
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.buy_artifact(session, user.id, code)

    await query.answer(msg, show_alert=True)
    await show_artifacts_menu(query, user_id, is_message=False, page=page)


async def equip_artifact_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    raw = query.data.replace("equip_art_", "")
    parts = raw.split(":")
    art_id = int(parts[0])
    page = int(parts[1]) if len(parts) > 1 else 0
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if not user:
            await query.answer("❌ Avval /start bosing.", show_alert=True)
            return
        ok, msg = await crud.equip_artifact(session, user.id, art_id)

    await query.answer(msg, show_alert=True)
    await show_artifacts_menu(query, user_id, is_message=False, page=page)


async def unequip_artifact_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split(":")
    page = int(parts[1]) if len(parts) > 1 else 0
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, user_id)
        if user:
            user.equipped_artifact_id = None
            arts = await crud.get_user_artifacts(session, user.id)
            for a in arts:
                a.is_equipped = False
            await session.commit()

    await query.answer("🛡️ Artefakt qurolxonaga olib qo'yildi.", show_alert=True)
    await show_artifacts_menu(query, user_id, is_message=False, page=page)


def register_profile_handlers(app):
    # Buyruqlar (Guruh va Shaxsiy)
    app.add_handler(CommandHandler(["profile", "profil", "me"], profile_command))
    app.add_handler(CommandHandler(["rename", "ism", "changename"], change_name_command))
    app.add_handler(CommandHandler(["status", "shior", "motto"], status_command))
    app.add_handler(CommandHandler(["farmon", "decree"], decree_command))
    app.add_handler(CommandHandler(["mine", "iron", "kon", "tegirmon"], iron_mine_command))
    app.add_handler(CommandHandler(["buyfood", "food", "oziq"], buy_food_command))
    app.add_handler(CommandHandler(["sellfood", "don_sotish"], sell_food_command))
    app.add_handler(CommandHandler(["selliron", "temir_sotish"], sell_iron_command))
    app.add_handler(CommandHandler(["cleankeyboard", "tozalash", "removekeyboard"], clean_keyboard_command))

    # Callbacklar
    app.add_handler(CallbackQueryHandler(profile_callback, pattern="^menu_profile$"))
    app.add_handler(CallbackQueryHandler(profile_change_name_callback, pattern="^profile_change_name$"))
    app.add_handler(CallbackQueryHandler(group_show_my_profile_callback, pattern="^group_show_my_profile$"))
    app.add_handler(CallbackQueryHandler(vip_custom_menu_callback, pattern="^menu_vip_custom$"))
    app.add_handler(CallbackQueryHandler(vip_set_photo_callback, pattern="^vip_set_photo$"))
    app.add_handler(CallbackQueryHandler(vip_remove_photo_callback, pattern="^vip_remove_photo$"))
    app.add_handler(CallbackQueryHandler(vip_set_status_callback, pattern="^vip_set_status$"))
    app.add_handler(CallbackQueryHandler(vip_remove_status_callback, pattern="^vip_remove_status$"))
    app.add_handler(CallbackQueryHandler(vip_set_audio_callback, pattern="^vip_set_audio$"))
    app.add_handler(CallbackQueryHandler(vip_audio_pick_callback, pattern="^vip_audio_pick:"))
    app.add_handler(CallbackQueryHandler(vip_audio_upload_prompt_callback, pattern="^vip_audio_upload_prompt$"))
    app.add_handler(CallbackQueryHandler(vip_audio_remove_callback, pattern="^vip_audio_remove$"))
    app.add_handler(CallbackQueryHandler(vip_decree_prompt_callback, pattern="^vip_decree_prompt$"))
    app.add_handler(CallbackQueryHandler(vip_preview_callback, pattern="^vip_preview$"))

    # Qurolxona va Kon callbacklari
    app.add_handler(CallbackQueryHandler(artifacts_menu_callback, pattern="^menu_artifacts$"))
    app.add_handler(CallbackQueryHandler(artifacts_page_callback, pattern="^menu_art_pg:"))
    app.add_handler(CallbackQueryHandler(buy_artifact_callback, pattern="^buy_art_"))
    app.add_handler(CallbackQueryHandler(equip_artifact_callback, pattern="^equip_art_"))
    app.add_handler(CallbackQueryHandler(unequip_artifact_callback, pattern="^unequip_art(:[0-9]+)?$"))
    app.add_handler(CallbackQueryHandler(iron_mine_callback, pattern="^menu_iron_mine$"))
    app.add_handler(CallbackQueryHandler(upgrade_mine_callback, pattern="^upgrade_iron_mine$"))
    app.add_handler(CallbackQueryHandler(upgrade_grain_mill_callback, pattern="^upgrade_grain_mill$"))
    app.add_handler(CallbackQueryHandler(buy_iron_callback, pattern="^buy_iron:"))
    app.add_handler(CallbackQueryHandler(buy_food_callback, pattern="^buy_food:"))
    app.add_handler(CallbackQueryHandler(sell_res_callback, pattern="^sell_res:"))

    # VIP Profil sozlamalari (rasm, shior, audio, farmon) qabul qiluvchi handler (group=3)
    app.add_handler(
        MessageHandler(
            (filters.PHOTO | filters.AUDIO | filters.VOICE | filters.Document.ALL | (filters.TEXT & ~filters.COMMAND)) & filters.ChatType.PRIVATE,
            vip_input_receiver,
        ),
        group=3,
    )

