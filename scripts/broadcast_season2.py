import asyncio
import sys
import sqlite3

sys.path.insert(0, r"C:\Users\user\Desktop\winter is coming")
from config import BOT_TOKEN
from telegram import Bot
from telegram.constants import ParseMode

async def broadcast():
    backup_db = r"C:\Users\user\Desktop\winter is coming\backups\season1_full_backup_2026-11-14_23-02-35\2026-11-14_23-02-35_got_mmorpg.db"
    conn = sqlite3.connect(backup_db)
    c = conn.cursor()
    c.execute("SELECT DISTINCT telegram_id FROM users WHERE telegram_id >= 100000000 AND telegram_id != 9594457048")
    real_tg_ids = [row[0] for row in c.fetchall()]
    print(f"Broadcasting Season 2 launch to {len(real_tg_ids)} real players...")

    bot = Bot(token=BOT_TOKEN)
    announcement = (
        "👑🏆 <b>VESTEROSDA YANGI DAVR: 1-MAVSUM YAKUNLANDI!</b> 🏆👑\n\n"
        "🏛️ <b>TEMIR TAXT G'OLIBI:</b> <b>🐉 House Blackfyre</b> xonadoni!\n"
        "👑 <b>1-Mavsum Chempioni (Qirol):</b> <b>Liar (@NiclausMikaelson)</b>\n"
        "⚔️ <b>Mavsumning Oliy Jangchisi:</b> <b>kozmunchoq 🐾 (@shaxnoza_0901)</b> (62,514🎖️ nufuz)\n\n"
        "📜 Barcha g'oliblar nomi abadiy <b>Shon-sharaf Zali (Hall of Fame)</b> solnomalariga muhrlandi!\n"
        "🎁 TOP-3 lordlar uchun 2-mavsumda avtomatik ochiladigan g'oliblik bonuslari biriktirildi.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌟 <b>2-MAVSUM RASMAN BOSHLANDI: AJDARLAR VA MUZ DAVRI!</b> 🌟\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔥 <b>2-Mavsumdagi Katta Yangiliklar:</b>\n"
        "• 🐉 <b>6 xil afsonaviy ajdarlar:</b> Arrax, Syrax, Meleys, Caraxes, Vhagar va Balerion!\n"
        "• 🏹 <b>Scorpion Mudofaasi:</b> Ajdarlar hujumiga qarshi 60% gacha zararni yutish taktikasi!\n"
        "• 🏗️ <b>Yangi Binolar:</b> Temir koni, Don tegirmoni va Qal'a istehkomi!\n"
        "• 💎 <b>Xavfsiz Donat:</b> Chek skrinshoti orqali tasdiqlash va 100% adolatli balans!\n"
        "• 📱 <b>Yangi Mini App:</b> Tezkor, chiroyli va qulay boshqaruv!\n\n"
        "⚔️ Barcha o'yinchilar teng sharoitda 0 dan boshlaydi! Yangi xonadon tuzing yoki mavjudiga qo'shiling:\n\n"
        "👉 <b>Boshlash uchun:</b> /start bosing yoki Mini Appni oching!"
    )

    success_cnt = 0
    fail_cnt = 0
    for tg_id in real_tg_ids:
        try:
            await bot.send_message(
                chat_id=tg_id,
                text=announcement,
                parse_mode=ParseMode.HTML
            )
            success_cnt += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            fail_cnt += 1

    print(f"Broadcast complete! Successfully sent: {success_cnt}, blocked/failed: {fail_cnt}")

if __name__ == "__main__":
    asyncio.run(broadcast())
