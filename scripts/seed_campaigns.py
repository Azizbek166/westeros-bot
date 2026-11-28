"""
Idempotent Campaign Seeder CLI.
Ishga tushirish: python scripts/seed_campaigns.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import AsyncSessionLocal, init_db
from services.campaign_service import list_campaigns, seed_all_campaigns


async def main():
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_all_campaigns(session)
        camps = await list_campaigns(session, include_drafts=False)
        print(f"Published campaigns total: {len(camps)}")
        for c in camps:
            print(
                f"  - [{c.order_index}] #{c.id} {c.title} "
                f"(slug={c.slug}, min_level={c.min_level}, stages={len(c.missions or [])})"
            )


if __name__ == "__main__":
    asyncio.run(main())
