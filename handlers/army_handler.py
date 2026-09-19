from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, crud
from core.economy_engine import calculate_army_upkeep
from core.anti_cheat import validate_recruitment
from keyboards.menus import recruit_keyboard, back_to_main_keyboard
from data.units_data import UNITS_DATA


async def army_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/army yoki /recruit yoki /askar buyrug'i"""
    user_id = update.effective_user.id
    if context.args and len(context.args) >= 1:
        # Buyruq orqali tezkor yollash: /recruit 500 yoki /recruit piyoda 500
        await handle_quick_recruit_command(update, context)
        return
    await show_army(update, user_id, is_message=True)


async def army_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """menu_army callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    context.user_data.pop("awaiting_recruit_input", None)
    await show_army(query, user_id, is_message=False)


async def show_army(target, user_id: int, is_message: bool):
    """Armiya holati va yollash menyusini ixcham chiqarish"""
    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            msg = "❌ Siz hali ro'yxatdan o'tmagansiz. /start ni bosing."
            if is_message:
                await target.message.reply_text(msg)
            else:
                await target.edit_message_text(msg)
            return

        army = user.army
        upkeep = calculate_army_upkeep(army)
        special_name = user.house.special_troop_name if user.house else "Maxsus Qo'shin"
        cats = getattr(army, "catapults", 0) or 0
        twrs = getattr(army, "siege_towers", 0) or 0

        text = (
            f"⚔️ **ARMIYA QARORGOHI**\n"
            f"💰 **Xazina:** {user.gold:,}🪙 | {user.food:,}🌾 | {user.iron:,}⛓️ (Ozuqa: -{int(upkeep)}🌾/s)\n\n"
            f"🛡️ Piyoda: **{army.infantry:,}** | 🏹 Kamonchi: **{army.archers:,}**\n"
            f"🐎 Otliq: **{army.cavalry:,}** | 🗡️ Nayzachi: **{army.spearmen:,}**\n"
            f"🔥 {special_name}: **{army.special_troops:,}**\n"
            f"🏹 Qamal Katapultasi: **{cats:,} / 20 ta** | 🗼 Qamal Minorasi: **{twrs:,} / 10 ta**\n\n"
            f"💡 *Jang afzalligi: 🐎>🏹, 🗡️>🐎, 🏹>🛡️, 🛡️>🗡️*"
        )

        if is_message:
            await target.message.reply_text(text, parse_mode="Markdown", reply_markup=recruit_keyboard())
        else:
            await target.edit_message_text(text, parse_mode="Markdown", reply_markup=recruit_keyboard())


async def recruit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tayyor to'plamda qo'shin yollash"""
    query = update.callback_query
    parts = query.data.split(":")
    unit_type = parts[1]
    amount = int(parts[2])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        is_valid, gold_cost, iron_cost, err_msg = validate_recruitment(user, unit_type, amount)
        if not is_valid:
            await query.answer(err_msg, show_alert=True)
            return

        success, quest_completed = await crud.recruit_troops(
            session=session,
            user_id=user.id,
            unit_type=unit_type,
            amount=amount,
            gold_cost=gold_cost,
            iron_cost=iron_cost,
        )

        if success:
            unit_name = UNITS_DATA[unit_type]["name"]
            msg = f"✅ +{amount:,} ta {unit_name} safga qo'shildi!"
            if quest_completed:
                msg += "\n\n🎉 Kunlik vazifa bajarildi (+100 askar)!\n🎁 Mukofot: +500🪙 Oltin, +1,000🌾 Oziq, +80 XP"
            await query.answer(msg, show_alert=True)
            await show_army(query, user_id, is_message=False)
        else:
            await query.answer("❌ Xatolik yuz berdi.", show_alert=True)


async def rec_custom_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'lda askar yollash uchun askar turini tanlash ekrani"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        sp_name = user.house.special_troop_name if user.house else "Maxsus Qo'shin"
        sp_data = UNITS_DATA.get("special_troops", {"gold_cost": 12, "iron_cost": 6})

        text = (
            f"✍️ **QO'LDA ASKAR YOLLASH**\n"
            f"💰 Xazinangiz: **{user.gold:,}**🪙 Oltin | **{user.iron:,}**⛓️ Temir\n\n"
            f"Yollamoqchi bo'lgan askar turini tanlang:"
        )

        buttons = [
            [
                InlineKeyboardButton(f"🛡️ Piyoda ({UNITS_DATA['infantry']['gold_cost']}🪙/{UNITS_DATA['infantry']['iron_cost']}⛓️)", callback_data="rec_custom_pick:infantry"),
                InlineKeyboardButton(f"🏹 Kamonchi ({UNITS_DATA['archers']['gold_cost']}🪙/{UNITS_DATA['archers']['iron_cost']}⛓️)", callback_data="rec_custom_pick:archers"),
            ],
            [
                InlineKeyboardButton(f"🐎 Otliq ({UNITS_DATA['cavalry']['gold_cost']}🪙/{UNITS_DATA['cavalry']['iron_cost']}⛓️)", callback_data="rec_custom_pick:cavalry"),
                InlineKeyboardButton(f"🗡️ Nayzachi ({UNITS_DATA['spearmen']['gold_cost']}🪙/{UNITS_DATA['spearmen']['iron_cost']}⛓️)", callback_data="rec_custom_pick:spearmen"),
            ],
            [
                InlineKeyboardButton(f"🔥 {sp_name[:18]} ({sp_data['gold_cost']}🪙/{sp_data['iron_cost']}⛓️)", callback_data="rec_custom_pick:special_troops"),
            ],
            [
                InlineKeyboardButton("🔙 Armiyaga Qaytish", callback_data="menu_army"),
            ]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def rec_custom_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan askar turiga miqdor kiritish ekrani"""
    query = update.callback_query
    await query.answer()
    unit_type = query.data.split(":")[1]
    user_id = query.from_user.id

    if unit_type not in UNITS_DATA:
        await query.answer("Noto'g'ri askar turi.", show_alert=True)
        return

    unit_info = UNITS_DATA[unit_type]
    context.user_data["awaiting_recruit_input"] = {"unit_type": unit_type}

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        g_cost = unit_info["gold_cost"]
        i_cost = unit_info["iron_cost"]
        max_by_gold = user.gold // g_cost if g_cost > 0 else 0
        max_by_iron = user.iron // i_cost if i_cost > 0 else 0
        max_count = max(0, min(max_by_gold, max_by_iron))

        text = (
            f"✍️ **{unit_info['name']} Yollash**\n"
            f"• 1 ta askar: **{g_cost}**🪙 oltin, **{i_cost}**⛓️ temir\n"
            f"• Xazinangiz yetadi: **{max_count:,}** tagacha\n\n"
            f"Qancha askar yollamoqchisiz? Sonini chatga yozing:\n"
            f"*(Masalan: `250` yoki `1000`)*"
        )

        buttons = []
        if max_count > 0:
            buttons.append([
                InlineKeyboardButton(f"⚡ Barchasini Yollash ({max_count:,} ta)", callback_data=f"rec_do:{unit_type}:{max_count}")
            ])
            quick_row = []
            for q in [100, 250, 500, 1000]:
                if max_count >= q:
                    quick_row.append(InlineKeyboardButton(f"+{q:,}", callback_data=f"rec_do:{unit_type}:{q}"))
            if quick_row:
                buttons.append(quick_row)

        buttons.append([
            InlineKeyboardButton("🔙 Orqaga", callback_data="rec_custom_menu")
        ])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def rec_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tezkor miqdorda yoki MAX yollash callback"""
    query = update.callback_query
    parts = query.data.split(":")
    unit_type = parts[1]
    amount = int(parts[2])
    user_id = query.from_user.id
    context.user_data.pop("awaiting_recruit_input", None)

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        is_valid, gold_cost, iron_cost, err_msg = validate_recruitment(user, unit_type, amount)
        if not is_valid:
            await query.answer(err_msg, show_alert=True)
            return

        success, quest_completed = await crud.recruit_troops(
            session=session,
            user_id=user.id,
            unit_type=unit_type,
            amount=amount,
            gold_cost=gold_cost,
            iron_cost=iron_cost,
        )

        if success:
            unit_name = UNITS_DATA[unit_type]["name"]
            msg = f"✅ +{amount:,} ta {unit_name} safga qo'shildi!"
            if quest_completed:
                msg += "\n\n🎉 Kunlik vazifa bajarildi (+100 askar)!\n🎁 Mukofot: +500🪙 Oltin, +1,000🌾 Oziq, +80 XP"
            await query.answer(msg, show_alert=True)
            await show_army(query, user_id, is_message=False)
        else:
            await query.answer("❌ Xatolik yuz berdi.", show_alert=True)


async def handle_recruit_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi son yozganda qabul qilish"""
    if not update.message or not update.message.text:
        return

    req_data = context.user_data.get("awaiting_recruit_input")
    if not req_data:
        return

    unit_type = req_data.get("unit_type", "infantry")
    text = update.message.text.strip()
    user_id = update.effective_user.id

    if not text.isdigit():
        await update.message.reply_text(
            "❌ Iltimos, faqat butun son yozing (masalan: `250` yoki `1000`).\nBekor qilish uchun /army bosing.",
            parse_mode="Markdown"
        )
        return

    amount = int(text)
    if amount <= 0 or amount > 50000:
        await update.message.reply_text("❌ Miqdor 1 dan 50,000 gacha bo'lishi kerak!")
        return

    context.user_data.pop("awaiting_recruit_input", None)

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        is_valid, gold_cost, iron_cost, err_msg = validate_recruitment(user, unit_type, amount)
        if not is_valid:
            await update.message.reply_text(err_msg)
            return

        success, quest_completed = await crud.recruit_troops(
            session=session,
            user_id=user.id,
            unit_type=unit_type,
            amount=amount,
            gold_cost=gold_cost,
            iron_cost=iron_cost,
        )

        if success:
            unit_name = UNITS_DATA[unit_type]["name"]
            msg = (
                f"✅ **QO'SHIN SAFGA QO'SHILDI!**\n\n"
                f"⚔️ Olingan: **+{amount:,} ta {unit_name}**\n"
                f"💰 Sarflandi: -{gold_cost:,}🪙 oltin, -{iron_cost:,}⛓️ temir\n"
            )
            if quest_completed:
                msg += "\n🎉 Kunlik vazifa bajarildi! (+500🪙, +1,000🌾, +80 XP)\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
            await show_army(update, user_id, is_message=True)
        else:
            await update.message.reply_text("❌ Xatolik yuz berdi.")


async def handle_quick_recruit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/recruit [tur] [son] yoki /recruit [son] buyrug'i"""
    args = context.args
    user_id = update.effective_user.id

    unit_type = "infantry"
    amount = 0

    alias_map = {
        "piyoda": "infantry",
        "piyodalar": "infantry",
        "infantry": "infantry",
        "kamonchi": "archers",
        "kamonchilar": "archers",
        "archers": "archers",
        "otliq": "cavalry",
        "otliqlar": "cavalry",
        "cavalry": "cavalry",
        "nayzachi": "spearmen",
        "nayzachilar": "spearmen",
        "spearmen": "spearmen",
        "maxsus": "special_troops",
        "special": "special_troops",
    }

    if len(args) == 1 and args[0].isdigit():
        amount = int(args[0])
    elif len(args) >= 2:
        if args[0].lower() in alias_map and args[1].isdigit():
            unit_type = alias_map[args[0].lower()]
            amount = int(args[1])
        elif args[1].lower() in alias_map and args[0].isdigit():
            unit_type = alias_map[args[1].lower()]
            amount = int(args[0])

    if amount <= 0:
        await update.message.reply_text(
            "Foydalanish: `/recruit [son]` yoki `/recruit [tur] [son]`\n"
            "Masalan: `/recruit piyoda 500` yoki `/recruit 200`",
            parse_mode="Markdown"
        )
        return

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        is_valid, gold_cost, iron_cost, err_msg = validate_recruitment(user, unit_type, amount)
        if not is_valid:
            await update.message.reply_text(err_msg)
            return

        success, quest_completed = await crud.recruit_troops(
            session=session,
            user_id=user.id,
            unit_type=unit_type,
            amount=amount,
            gold_cost=gold_cost,
            iron_cost=iron_cost,
        )

        if success:
            unit_name = UNITS_DATA[unit_type]["name"]
            msg = (
                f"✅ **QO'SHIN SAFGA QO'SHILDI!**\n\n"
                f"⚔️ Olingan: **+{amount:,} ta {unit_name}**\n"
                f"💰 Sarflandi: -{gold_cost:,}🪙 oltin, -{iron_cost:,}⛓️ temir\n"
            )
            if quest_completed:
                msg += "\n🎉 Kunlik vazifa bajarildi! (+500🪙, +1,000🌾, +80 XP)\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
            await show_army(update, user_id, is_message=True)
        else:
            await update.message.reply_text("❌ Xatolik yuz berdi.")


async def siege_workshop_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qamal qurollari ustaxonasi menyusi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_with_relations(session, user_id)
        if not user:
            return

        army = user.army
        cats = getattr(army, "catapults", 0) or 0
        twrs = getattr(army, "siege_towers", 0) or 0

        text = (
            f"🏹🗼 **QAMAL QUROLLARI USTAXONASI (SIEGE WORKSHOP)**\n\n"
            f"Dushman qal'alarining mustahkam devorlarini buzib kirish va o'z piyodalaringizni asrash uchun qamal mashinalarini yasang!\n\n"
            f"💰 Hamyoningiz: <b>{user.gold:,}🪙 Oltin | {user.iron:,}⛓️ Temir | {user.food:,}🌾 Oziq</b>\n\n"
            f"──────── <b>MAVJUD QAMAL QUROLLARI</b> ────────\n"
            f"1. 🏹 <b>Qamal Trebusheti (Katapulta): {cats} / 20 ta</b>\n"
            f"   • Narxi: 400🪙 Oltin | 600⛓️ Temir | 100🌾 Oziq\n"
            f"   • Xususiyati: Jang boshlanishida qal'a devorini masofadan yemirib tashlaydi (-35 mudofaa/dona).\n\n"
            f"2. 🗼 <b>Qamal Minorasi (Siege Tower): {twrs} / 10 ta</b>\n"
            f"   • Narxi: 300🪙 Oltin | 500⛓️ Temir | 50🌾 Oziq\n"
            f"   • Xususiyati: Piyodalarni devordagi kamonchilar o'qlaridan himoyalab, istehkomlar ustiga olib chiqadi (-35% talafot).\n\n"
            f"Kerakli qurol va sonni tanlang:"
        )

        buttons = [
            [
                InlineKeyboardButton("🏹 +1 Katapulta (400🪙, 600⛓️)", callback_data="build_siege:catapult:1"),
                InlineKeyboardButton("🏹 +5 Katapulta", callback_data="build_siege:catapult:5"),
            ],
            [
                InlineKeyboardButton("🗼 +1 Qamal Minorasi (300🪙, 500⛓️)", callback_data="build_siege:siege_tower:1"),
                InlineKeyboardButton("🗼 +3 Qamal Minorasi", callback_data="build_siege:siege_tower:3"),
            ],
            [InlineKeyboardButton("🔙 Armiyaga Qaytish", callback_data="menu_army")],
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def build_siege_weapon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qamal qurolini yasash ijrosi"""
    query = update.callback_query
    parts = query.data.split(":")
    w_type = parts[1]
    amount = int(parts[2])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        ok, msg = await crud.build_siege_weapon(session, user_id, w_type, amount)

    await query.answer(msg[:150], show_alert=True)
    await siege_workshop_menu_callback(update, context)


def register_army_handlers(app):
    app.add_handler(CommandHandler(["army", "recruit", "askar"], army_command))
    app.add_handler(CallbackQueryHandler(army_callback, pattern="^menu_army$"))
    app.add_handler(CallbackQueryHandler(recruit_callback, pattern="^rec:"))
    app.add_handler(CallbackQueryHandler(rec_custom_menu_callback, pattern="^rec_custom_menu$"))
    app.add_handler(CallbackQueryHandler(rec_custom_pick_callback, pattern="^rec_custom_pick:"))
    app.add_handler(CallbackQueryHandler(rec_do_callback, pattern="^rec_do:"))
    app.add_handler(CallbackQueryHandler(siege_workshop_menu_callback, pattern="^siege_workshop_menu$"))
    app.add_handler(CallbackQueryHandler(build_siege_weapon_callback, pattern="^build_siege:"))

