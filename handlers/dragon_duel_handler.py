from datetime import datetime, timedelta
import json
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    Application,
)
from database import AsyncSessionLocal, crud, models
from core.dragon_battle import simulate_dragon_battle
from keyboards.menus import back_to_main_keyboard
from config import escape_md


async def dragon_duel_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarlar dueli va turnirlari asosiy menyusi"""
    query = update.callback_query
    if query:
        await query.answer()

    text = (
        "🐉 **WESTEROS AFSONAVIY AJDARLAR DUELI VA TURNIRLARI**\n\n"
        "Vesteros osmonida olov va po'lat shiddati! Lordlar o'z ajdarlarini bir-biriga qarshi sinovdan o'tkazishlari mumkin.\n\n"
        "⚔️ **Erkin Ajdarlar Dueli:** Istalgan vaqtda, cheklovlarsiz boshqa lord bilan 1v1 jang qiling.\n"
        "🏆 **Kunlik Ajdarlar Turniri:** Har kuni bir marta avtomatik o'tkaziladigan Vesteros ajdarlari chempionati!\n\n"
        "👇 *Kerakli bo'limni tanlang:*"
    )

    buttons = [
        [
            InlineKeyboardButton("🌐 Ochiq Duel Zali (Lobby)", callback_data="dragon_duel_lobby"),
            InlineKeyboardButton("⚔️ Lordni Duelga Chaqirish", callback_data="dragon_duel_direct_menu"),
        ],
        [
            InlineKeyboardButton("📩 Kelgan Chaqiruvlar", callback_data="dragon_duel_inbox"),
            InlineKeyboardButton("🏆 Kunlik Ajdarlar Turniri", callback_data="dragon_tourney_menu"),
        ],
        [
            InlineKeyboardButton("🏆 Duelchilar Reytingi", callback_data="rank_cat:dragon_duels:all"),
        ],
        [
            InlineKeyboardButton("🔙 Ajdarlar Markazi", callback_data="menu_dragon"),
            InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main"),
        ]
    ]

    kb = InlineKeyboardMarkup(buttons)
    if query and query.message:
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    elif update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def dragon_duel_lobby_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ochiq duel zali — faol chaqiruvlar ro'yxati"""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return

        open_duels = await crud.get_open_dragon_duels(session, limit=10)

    text = (
        "🌐 **OCHIQ AJDARLAR DUEL ZALI**\n\n"
        "Bu yerda boshqa lordlar o'z ajdarlarini jangga qo'ygan. Istalgan ajdarni tanlab, o'z ajdaringiz bilan jangga kiring!\n"
        "Jang natijasi va to'liq jang lavhalari ikkala lordga yuboriladi.\n\n"
    )

    buttons = [
        [InlineKeyboardButton("🔥 Ochiq Chaqiruv Yaratish", callback_data="dragon_duel_create_pick")]
    ]

    if not open_duels:
        text += "📭 *Hozirda ochiq zolda kutilayotgan duel chaqiruvlari yo'q. Birinchi bo'lib chaqiruv yarating!*"
    else:
        text += "👇 **Faol ochiq chaqiruvlar:**\n"
        for idx, duel in enumerate(open_duels, 1):
            c_name = duel.challenger.username or duel.challenger.full_name if duel.challenger else "Lord"
            d_name = duel.challenger_dragon.name if duel.challenger_dragon else "Ajdar"
            d_power = duel.challenger_dragon.power if duel.challenger_dragon else 100

            if duel.challenger_user_id == user_db.id:
                # O'z chaqiruvi bo'lsa bekor qilish imkoni
                buttons.append([
                    InlineKeyboardButton(f"❌ O'z chaqiruvingiz ({d_name}) — Bekor qilish", callback_data=f"dragon_duel_cancel:{duel.id}")
                ])
            else:
                buttons.append([
                    InlineKeyboardButton(f"⚔️ {c_name}: {d_name} (⚡{d_power:,})", callback_data=f"dragon_duel_accept_pick:{duel.id}")
                ])

    buttons.append([InlineKeyboardButton("🔙 Ajdarlar Dueli Menyusi", callback_data="dragon_duel_menu")])

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def dragon_duel_create_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ochiq duel zaliga qo'yish uchun ajdarni tanlash"""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return
        dragons = await crud.get_user_dragons(session, user_db.id)

    usable_dragons = [d for d in dragons if d.stage != "egg"]
    if not usable_dragons:
        await query.answer("Jangga qo'yish uchun balog'atga yetgan ajdaringiz yo'q! (Tuxumlar jang qila olmaydi)", show_alert=True)
        return

    text = (
        "🐉 **OCHIQ CHAQIRUV UCHUN AJDARNI TANLANG**\n\n"
        "Qaysi ajdaringizni Vesteros ochiq duel zaliga chiqarasiz?"
    )

    buttons = []
    for d in usable_dragons:
        buttons.append([
            InlineKeyboardButton(
                f"🔥 {d.name} ({d.stage.capitalize()} | ⚡{d.power:,})",
                callback_data=f"dragon_duel_create_do:{d.id}"
            )
        ])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="dragon_duel_lobby")])

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def dragon_duel_create_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarni ochiq duel zaliga joylashtirish"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 2:
        return

    try:
        dragon_id = int(parts[1])
    except ValueError:
        return

    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return

        dragon = await session.get(models.Dragon, dragon_id)
        if not dragon or dragon.user_id != user_db.id:
            await query.answer("Ajdar topilmadi!", show_alert=True)
            return

        if dragon.stage == "egg":
            await query.answer("Tuxum jangga qatnasha olmaydi!", show_alert=True)
            return

        duel = await crud.create_dragon_duel_entry(
            session=session,
            challenger_user_id=user_db.id,
            challenger_dragon_id=dragon.id,
            is_open_lobby=True
        )

    await query.answer("✅ Ajdaringiz ochiq duel zaliga muvaffaqiyatli qo'yildi!", show_alert=True)
    await dragon_duel_lobby_callback(update, context)


async def dragon_duel_accept_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Raqib ajdarga qarshi o'z ajdaringizni tanlash ekrani"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 2:
        return

    try:
        duel_id = int(parts[1])
    except ValueError:
        return

    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return

        duel = await crud.get_dragon_duel_by_id(session, duel_id)
        if not duel or duel.status not in ["pending", "open_lobby"]:
            await query.answer("Ushbu duel allaqachon yakunlangan yoki bekor qilingan!", show_alert=True)
            return

        dragons = await crud.get_user_dragons(session, user_db.id)

    usable_dragons = [d for d in dragons if d.stage != "egg"]
    if not usable_dragons:
        await query.answer("Jang qilish uchun balog'atga yetgan ajdaringiz yo'q!", show_alert=True)
        return

    c_name = duel.challenger.username or duel.challenger.full_name if duel.challenger else "Lord"
    d_name = duel.challenger_dragon.name if duel.challenger_dragon else "Ajdar"
    d_power = duel.challenger_dragon.power if duel.challenger_dragon else 100

    text = (
        f"⚔️ **DUELNI QABUL QILISH**\n\n"
        f"Raqib: **{c_name}**\n"
        f"Raqib ajdari: **{d_name}** (⚡Quvvat: **{d_power:,}**)\n\n"
        f"Ushbu ajdarga qarshi o'z ajdaringizni tanlang:"
    )

    buttons = []
    for d in usable_dragons:
        buttons.append([
            InlineKeyboardButton(
                f"🔥 {d.name} ({d.stage.capitalize()} | ⚡{d.power:,})",
                callback_data=f"dragon_duel_fight:{duel.id}:{d.id}"
            )
        ])
    buttons.append([InlineKeyboardButton("🔙 Bekor qilish", callback_data="dragon_duel_lobby")])

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def dragon_duel_fight_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarlar jangini simulyatsiya qilish va natijalarni har ikki lordga yuborish"""
    query = update.callback_query
    await query.answer("🔥 Jang hisoblanmoqda...")

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    try:
        duel_id = int(parts[1])
        my_dragon_id = int(parts[2])
    except ValueError:
        return

    user = update.effective_user

    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return

        duel = await crud.get_dragon_duel_by_id(session, duel_id)
        if not duel or duel.status not in ["pending", "open_lobby"]:
            await query.answer("Ushbu duel allaqachon yakunlangan!", show_alert=True)
            return

        d1_obj = duel.challenger_dragon
        d2_obj = await session.get(models.Dragon, my_dragon_id)

        if not d1_obj or not d2_obj or d2_obj.user_id != user_db.id:
            await query.answer("Ajdar ma'lumotlarida xatolik!", show_alert=True)
            return

        c_user = duel.challenger
        challenger_name = c_user.username or c_user.full_name if c_user else "Lord 1"
        challenger_tg_id = c_user.telegram_id if c_user else 0
        defender_name = user_db.username or user_db.full_name or "Lord 2"

        d1_dict = {
            "id": d1_obj.id,
            "name": d1_obj.name,
            "grade": d1_obj.grade,
            "stage": d1_obj.stage,
            "level": d1_obj.level,
            "power": d1_obj.power or 100,
            "user_id": duel.challenger_user_id,
            "user_name": challenger_name,
        }

        d2_dict = {
            "id": d2_obj.id,
            "name": d2_obj.name,
            "grade": d2_obj.grade,
            "stage": d2_obj.stage,
            "level": d2_obj.level,
            "power": d2_obj.power or 100,
            "user_id": user_db.id,
            "user_name": defender_name,
        }

        # Simulyatsiya
        battle_res = simulate_dragon_battle(d1_dict, d2_dict)
        winner_dragon = battle_res["winner"]
        duel_log = battle_res["duel_log"]

        ok, msg, updated_duel = await crud.complete_dragon_duel(
            session=session,
            duel_id=duel.id,
            defender_user_id=user_db.id,
            defender_dragon_id=d2_obj.id,
            winner_dragon_id=winner_dragon["id"],
            winner_user_id=winner_dragon["user_id"],
            duel_log=duel_log
        )

    # Natija klaviaturasi
    res_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Ochiq Duel Zaliga Qaytish", callback_data="dragon_duel_lobby")],
        [InlineKeyboardButton("🔙 Ajdarlar Dueli Menyusi", callback_data="dragon_duel_menu")]
    ])

    # 1. Jangni qabul qilgan (himoyachi) lordga xabar
    try:
        await query.edit_message_text(duel_log, parse_mode="Markdown", reply_markup=res_kb)
    except Exception:
        await query.message.reply_text(duel_log, parse_mode="Markdown", reply_markup=res_kb)

    # 2. Chaqiruvchi (challenger) lordga telegram xabari yuborish
    if challenger_tg_id and challenger_tg_id != user.id:
        try:
            notify_text = (
                f"🔔 **AJDARINGIZ DUELDA JANG QILDI!**\n\n"
                f"Sizning ochiq chaqiruvingizni Lord **{defender_name}** qabul qildi.\n\n"
                f"{duel_log}"
            )
            await context.bot.send_message(
                chat_id=challenger_tg_id,
                text=notify_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Challenger {challenger_tg_id} ga duel natijasini yuborishda xatolik: {e}")


async def dragon_duel_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'z duel chaqiruvini bekor qilish"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 2:
        return

    try:
        duel_id = int(parts[1])
    except ValueError:
        return

    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return

        ok, msg = await crud.cancel_or_reject_dragon_duel(session, duel_id, user_db.id)

    await query.answer(msg, show_alert=True)
    await dragon_duel_lobby_callback(update, context)


async def dragon_duel_direct_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """To'g'ridan-to'g'ri biror lordni duelga chaqirish menyusi"""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return
        dragons = await crud.get_user_dragons(session, user_db.id)

    usable = [d for d in dragons if d.stage != "egg"]
    if not usable:
        await query.answer("Duelga kirish uchun balog'atga yetgan ajdaringiz yo'q!", show_alert=True)
        return

    text = (
        "⚔️ **LORDNI TO'G'RIDAN-TO'G'RI DUELGA CHAQIRISH**\n\n"
        "1. Jang qilmoqchi bo'lgan o'z ajdaringizni tanlang.\n"
        "2. Keyin chaqirmoqchi bo'lgan lordning Telegram ID yoki username'ini kiriting."
    )

    buttons = []
    for d in usable:
        buttons.append([
            InlineKeyboardButton(f"🔥 {d.name} (⚡{d.power:,})", callback_data=f"dragon_duel_direct_pick:{d.id}")
        ])
    buttons.append([InlineKeyboardButton("🔙 Ajdarlar Dueli Menyusi", callback_data="dragon_duel_menu")])

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def dragon_duel_direct_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdar tanlangach, raqib ID yoki username kiritishni so'rash"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 2:
        return

    try:
        dragon_id = int(parts[1])
    except ValueError:
        return

    context.user_data["awaiting_dragon_duel_target"] = dragon_id

    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="dragon_duel_direct_menu")]
    ])

    text = (
        "✍️ **RAQIB LORDNI KO'RSATING**\n\n"
        "Ajdarlar dueli uchun chaqirmoqchi bo'lgan lordning **Telegram ID raqami** yoki **@username**'ini yuboring:\n"
        "(Masalan: `123456789` yoki `@lord_stark`)"
    )

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=cancel_kb)
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=cancel_kb)


async def handle_dragon_duel_target_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Raqib ID yoki username kiritilganda to'g'ridan-to'g'ri duel chaqiruvi yaratish"""
    dragon_id = context.user_data.pop("awaiting_dragon_duel_target", None)
    if not dragon_id or not update.message or not update.message.text:
        return

    target_raw = update.message.text.strip().lstrip("@")
    user = update.effective_user

    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return

        dragon = await session.get(models.Dragon, dragon_id)
        if not dragon or dragon.user_id != user_db.id:
            await update.message.reply_text("Ajdar topilmadi.")
            return

        # Raqibni izlash (ID yoki username)
        target_user = None
        if target_raw.isdigit():
            tg_id_val = int(target_raw)
            target_user = await crud.get_user_with_relations(session, tg_id_val)
            if not target_user:
                # database user_id tekshirish
                target_user = await session.get(models.User, tg_id_val)
        else:
            res = await session.execute(
                models.User.__table__.select().where(models.User.username.ilike(f"%{target_raw}%"))
            )
            row = res.first()
            if row:
                target_user = await session.get(models.User, row.id)

        if not target_user:
            await update.message.reply_text(
                "❌ Bunday foydalanuvchi topilmadi! Iltimos, Telegram ID yoki to'g'ri username kiriting."
            )
            context.user_data["awaiting_dragon_duel_target"] = dragon_id
            return

        if target_user.id == user_db.id:
            await update.message.reply_text("⚠️ O'zingizni duelga chaqira olmaysiz!")
            context.user_data["awaiting_dragon_duel_target"] = dragon_id
            return

        # Duel yaratish
        duel = await crud.create_dragon_duel_entry(
            session=session,
            challenger_user_id=user_db.id,
            challenger_dragon_id=dragon.id,
            defender_user_id=target_user.id,
            is_open_lobby=False
        )

    # Challengerga xabar
    await update.message.reply_text(
        f"✅ **Ajdarlar dueli chaqiruvi yuborildi!**\n\n"
        f"👤 Raqib: **{escape_md(target_user.full_name)}** (@{target_user.username or 'yo\'q'})\n"
        f"🐉 Sizning ajdaringiz: **{dragon.name}**\n\n"
        f"Raqib chaqiruvni qabul qilgach, jang avtomatik o'tkaziladi va natijasi sizga yuboriladi! ⚔️",
        parse_mode="Markdown",
        reply_markup=back_to_main_keyboard()
    )

    # Raqibga bildirishnoma yuborish
    if target_user.telegram_id:
        invite_text = (
            f"🔥 **SIZGA AJDARLAR DUELI CHAQIRUVI KELDI!**\n\n"
            f"👑 Chaqiruvchi: **{escape_md(user.full_name)}** (@{user.username or 'yo\'q'})\n"
            f"🐉 Raqib ajdari: **{dragon.name}** (⚡Quvvat: **{dragon.power:,}**)\n\n"
            f"Jangni qabul qilasizmi?"
        )
        invite_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚔️ Duelni Qabul Qilish", callback_data=f"dragon_duel_accept_pick:{duel.id}"),
                InlineKeyboardButton("❌ Rad Etish", callback_data=f"dragon_duel_cancel:{duel.id}"),
            ]
        ])
        try:
            await context.bot.send_message(
                chat_id=target_user.telegram_id,
                text=invite_text,
                parse_mode="Markdown",
                reply_markup=invite_kb
            )
        except Exception as e:
            print(f"Raqib {target_user.telegram_id} ga duel taklifini yuborishda xatolik: {e}")


async def dragon_duel_inbox_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kelgan to'g'ridan-to'g'ri duel chaqiruvlari ro'yxati"""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return
        pending = await crud.get_user_pending_dragon_duels(session, user_db.id)

    text = "📩 **SIZGA KELGAN AJDARLAR DUELI CHAQIRUVLARI**\n\n"
    buttons = []

    if not pending:
        text += "📭 *Hozirda sizga yuborilgan kutilayotgan duel chaqiruvlari yo'q.*"
    else:
        for d in pending:
            c_name = d.challenger.username or d.challenger.full_name if d.challenger else "Lord"
            dr_name = d.challenger_dragon.name if d.challenger_dragon else "Ajdar"
            dr_power = d.challenger_dragon.power if d.challenger_dragon else 100
            buttons.append([
                InlineKeyboardButton(f"⚔️ {c_name}: {dr_name} (⚡{dr_power:,})", callback_data=f"dragon_duel_accept_pick:{d.id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"dragon_duel_cancel:{d.id}")
            ])

    buttons.append([InlineKeyboardButton("🔙 Ajdarlar Dueli Menyusi", callback_data="dragon_duel_menu")])

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ============================================================
# KUNLIK AVTOMATIK AJDARLAR TURNIRI HANDLERLARI
# ============================================================

async def dragon_tourney_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kunlik avtomatik ajdarlar turniri asosiy menyusi"""
    query = update.callback_query
    if query:
        await query.answer()

    user = update.effective_user
    now_uzb = datetime.utcnow() + timedelta(hours=5)
    today_str = now_uzb.strftime("%Y-%m-%d")

    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return

        tourney = await crud.get_or_create_daily_dragon_tourney(session, today_str)
        part_count = len(tourney.participants or [])

        # Foydalanuvchining bugungi qatnashuvi
        my_part = None
        for p in (tourney.participants or []):
            if p.user_id == user_db.id:
                my_part = p
                break

    status_labels = {
        "registration": "🟢 Ro'yxatga olish ochiq (Har kuni 20:00 gacha)",
        "in_progress": "⚔️ Janglar davom etmoqda",
        "completed": "🏆 Turnir yakunlangan",
    }
    st_text = status_labels.get(tourney.status, tourney.status)

    text = (
        f"🏆 **KUNLIK AVTOMATIK AJDARLAR TURNIRI**\n\n"
        f"📅 Sana: **{today_str}** (Toshkent vaqti)\n"
        f"📌 Holati: **{st_text}**\n"
        f"👥 Ro'yxatdan o'tgan ajdarlar: **{part_count} ta**\n\n"
        f"Turnir har kuni avtomatik ravishda tashkil qilinadi. Ishtirokchilar ajdarlari juftlanib, 1/8, 1/4, Yarim final va Final janglari o'tkaziladi!\n\n"
    )

    buttons = []
    if tourney.status == "registration":
        if my_part:
            text += f"✅ **Siz ro'yxatdan o'tgansiz:** 🐉 **{my_part.dragon_name}** (⚡Quvvat: {my_part.dragon_power:,})\nTurnir vaqti boshlanganda janglar avtomatik o'tkaziladi!"
        else:
            buttons.append([InlineKeyboardButton("📝 Turnirga Ajdarni Ro'yxatdan O'tkazish", callback_data="dragon_tourney_join_pick")])

    if tourney.status == "completed":
        c_dr = tourney.champion_dragon_name or "Ajdar"
        c_usr = tourney.champion_user_name or "Lord"
        text += f"👑 **Bugungi Turnir Chempioni:** **{c_dr}**\n👤 Hukmdori: **{c_usr}**\n\n"
        buttons.append([InlineKeyboardButton("📊 Turnir Natijalari va Setkasi", callback_data="dragon_tourney_bracket")])

    buttons.append([InlineKeyboardButton("🔙 Ajdarlar Dueli Menyusi", callback_data="dragon_duel_menu")])

    kb = InlineKeyboardMarkup(buttons)
    if query and query.message:
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    elif update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def dragon_tourney_join_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Turnirda qatnashish uchun ajdar tanlash"""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return
        dragons = await crud.get_user_dragons(session, user_db.id)

    usable = [d for d in dragons if d.stage != "egg"]
    if not usable:
        await query.answer("Turnirda qatnashish uchun balog'atga yetgan ajdaringiz yo'q!", show_alert=True)
        return

    text = (
        "🐉 **KUNLIK TURNIRDA QATNASHISH**\n\n"
        "Bugungi chempionatda qatnashishi uchun ajdaringizni tanlang:\n"
        "*(Har bir o'yinchi kuniga faqat 1 ta ajdarni ro'yxatdan o'tkaza oladi)*"
    )

    buttons = []
    for d in usable:
        buttons.append([
            InlineKeyboardButton(f"🔥 {d.name} (⚡{d.power:,})", callback_data=f"dragon_tourney_do_join:{d.id}")
        ])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="dragon_tourney_menu")])

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def dragon_tourney_do_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajdarni turnirga ro'yxatdan o'tkazishni yakunlash"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 2:
        return

    try:
        dragon_id = int(parts[1])
    except ValueError:
        return

    user = update.effective_user
    now_uzb = datetime.utcnow() + timedelta(hours=5)
    today_str = now_uzb.strftime("%Y-%m-%d")

    async with AsyncSessionLocal() as session:
        user_db = await crud.get_user_with_relations(session, user.id)
        if not user_db:
            return

        tourney = await crud.get_or_create_daily_dragon_tourney(session, today_str)
        ok, msg = await crud.register_dragon_for_daily_tourney(session, tourney.id, user_db.id, dragon_id)

    await query.answer(msg, show_alert=True)
    await dragon_tourney_menu_callback(update, context)


async def dragon_tourney_bracket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bugungi turnir setkasi va tafsilotlarini ko'rsatish"""
    query = update.callback_query
    await query.answer()

    now_uzb = datetime.utcnow() + timedelta(hours=5)
    today_str = now_uzb.strftime("%Y-%m-%d")

    async with AsyncSessionLocal() as session:
        tourney = await crud.get_or_create_daily_dragon_tourney(session, today_str)
        details = tourney.details or "Turnir hisoboti mavjud emas."

    buttons = [
        [InlineKeyboardButton("🔙 Turnir Menyusiga Qaytish", callback_data="dragon_tourney_menu")]
    ]

    try:
        await query.edit_message_text(details, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        await query.message.reply_text(details, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


def register_dragon_duel_handlers(app: Application):
    """Ajdarlar dueli va turniri handlerlarini ro'yxatdan o'tkazish"""
    app.add_handler(CommandHandler(["dragon_duel", "duel_dragon", "ajdar_duel"], dragon_duel_menu_callback))
    app.add_handler(CallbackQueryHandler(dragon_duel_menu_callback, pattern="^dragon_duel_menu$"))
    app.add_handler(CallbackQueryHandler(dragon_duel_lobby_callback, pattern="^dragon_duel_lobby$"))
    app.add_handler(CallbackQueryHandler(dragon_duel_create_pick_callback, pattern="^dragon_duel_create_pick$"))
    app.add_handler(CallbackQueryHandler(dragon_duel_create_do_callback, pattern="^dragon_duel_create_do:"))
    app.add_handler(CallbackQueryHandler(dragon_duel_accept_pick_callback, pattern="^dragon_duel_accept_pick:"))
    app.add_handler(CallbackQueryHandler(dragon_duel_fight_callback, pattern="^dragon_duel_fight:"))
    app.add_handler(CallbackQueryHandler(dragon_duel_cancel_callback, pattern="^dragon_duel_cancel:"))
    app.add_handler(CallbackQueryHandler(dragon_duel_direct_menu_callback, pattern="^dragon_duel_direct_menu$"))
    app.add_handler(CallbackQueryHandler(dragon_duel_direct_pick_callback, pattern="^dragon_duel_direct_pick:"))
    app.add_handler(CallbackQueryHandler(dragon_duel_inbox_callback, pattern="^dragon_duel_inbox$"))
    app.add_handler(CallbackQueryHandler(dragon_tourney_menu_callback, pattern="^dragon_tourney_menu$"))
    app.add_handler(CallbackQueryHandler(dragon_tourney_join_pick_callback, pattern="^dragon_tourney_join_pick$"))
    app.add_handler(CallbackQueryHandler(dragon_tourney_do_join_callback, pattern="^dragon_tourney_do_join:"))
    app.add_handler(CallbackQueryHandler(dragon_tourney_bracket_callback, pattern="^dragon_tourney_bracket$"))
