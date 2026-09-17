import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database.db import AsyncSessionLocal
from database import crud

async def main():
    print('⚠️ DIQQAT: WESTEROS O\'YININI 0 GA TUSHIRISH (RESET)...')
    async with AsyncSessionLocal() as session:
        await crud.reset_entire_game(session)
    print('✅ MUVAFFAQIYATLI YAKUNLANDI!')
    print('Barcha o\'yinchilar, armiyalar va ajdarlar tozalandi.')
    print('Xonadonlar va qal\'alar boshlang\'ich holatiga qaytarildi.')
    print('Barcha foydalanuvchilar endi /start bosib 0 dan o\'yinni boshlaydi!')

if __name__ == '__main__':
    asyncio.run(main())
