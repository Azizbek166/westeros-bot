import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database import AsyncSessionLocal, models

async def migrate():
    async with AsyncSessionLocal() as session:
        h = await session.get(models.House, 15)
        if h:
            print(f"Updating House {h.id}: '{h.name}' -> 'House Blackfyre'")
            h.name = "House Blackfyre"
            h.emoji = "🐉"
            h.region = "Crownlands"
            h.description = "Qora Ajdar sulolasi — Valyria qonidan bo'lgan jasur isyonchilar va Oltin To'da (Golden Company) asoschilari."
            h.special_troop_name = "Blackfyre Dragonblades"
            h.starting_gold = 8000
            h.starting_food = 8000
            h.starting_iron = 3000
            h.prestige = max(h.prestige or 0, 260)
            h.defense_bonus = 1.15
            await session.commit()
            print("Migration successful! House 15 is now House Blackfyre.")
        else:
            print("House 15 not found in database.")

if __name__ == "__main__":
    asyncio.run(migrate())
