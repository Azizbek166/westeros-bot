import asyncio
import sys

sys.path.insert(0, r"C:\Users\user\Desktop\winter is coming")
from config import BOT_TOKEN, OWNER_ID
from telegram import Bot
from telegram.constants import ParseMode

async def send_announcement():
    bot = Bot(token=BOT_TOKEN)
    announcement = (
        "👑🏆 <b>VESTEROSDA YANGI DAVR: 1-MAVSUM YAKUNLANDI!</b> 🏆👑\n\n"
        "🏛️ <b>TEMIR TAXT G'OLIBI:</b> <b>🐉 House Blackfyre</b> xonadoni!\n"
        "👑 <b>1-Mavsum Chempioni (Qirol):</b> <b>Liar (@NiclausMikaelson)</b>\n"
        "⚔️ <b>Mavsumning Oliy Jangchisi:</b> <b>kozmunchoq 🐾 (@shaxnoza_0901)</b> (62,514🎖️ nufuz)\n\n"
        "📜 Barcha g'oliblar nomi abadiy <b>Shon-sharaf Zali (Hall of Fame)</b> solnomalariga muhrlandi!\n"
        "🎁 TOP-3 lordlar uchun yangi mavsum boshlang'ich bonuslari biriktirildi.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌟 <b>2-MAVSUM RASMAN BOSHLANDI: AJDARLAR VA MUZ DAVRI!</b> 🌟\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔥 <b>Yangi Mavsumdagi Katta O'zgarishlar:</b>\n"
        "• 🐉 <b>6 xil afsonaviy ajdarlar</b> (Arrax, Syrax, Meleys, Caraxes, Vhagar, Balerion) va Ajdarlar uyasi!\n"
        "• 🏹 <b>Scorpion Mudofaa Tizimi:</b> Ajdarlarga qarshi 60% gacha zararni qaytarish taktikasi!\n"
        "• 🏗️ <b>Yangi Binolar Hubi:</b> Temir koni, Don tegirmoni va Qal'a istehkomi darajalari!\n"
        "• 💎 <b>Xavfsiz Donat Tizimi:</b> To'lov chekini skrinshot bilan qo'lda tasdiqlash va adolatli o'yin kafolati!\n"
        "• 📱 <b>Mukammal Mini App:</b> To'liq qulay scroll, zamonaviy menyular va tezkor harakatlar!\n\n"
        "⚔️ Barcha qal'alar neytral holatga qaytarildi. Yetti Qirollik taxti yangi qahramonlarni kutmoqda!\n\n"
        "👉 O'yinga kirish: /start yoki Mini Appni oching!"
    )
    try:
        await bot.send_message(
            chat_id=OWNER_ID,
            text=announcement,
            parse_mode=ParseMode.HTML
        )
        print("SUCCESS: Telegram announcement sent to OWNER_ID!")
    except Exception as e:
        print(f"FAILED to send to OWNER: {e}")

if __name__ == "__main__":
    asyncio.run(send_announcement())
