"""
Mavjud o'yinchilar va qal'alar taqsimotini muvozanatlash migratsiya skripti.
Default holatda --dry-run rejimida ishlaydi (bazani o'zgartirmaydi).
Haqiqiy qo'llash uchun: python scripts/fix_castle_distribution.py --apply
"""
import argparse
import asyncio
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.db import AsyncSessionLocal, init_db
from database import crud


def create_sqlite_backup() -> str:
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "got_mmorpg.db"))
    if not os.path.exists(db_path):
        return ""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    bdir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backups", f"castle_fix_{ts}"))
    os.makedirs(bdir, exist_ok=True)
    dst = os.path.join(bdir, "got_mmorpg.db")
    shutil.copy2(db_path, dst)
    return dst


async def main(apply_changes: bool):
    await init_db()
    if apply_changes:
        bkp = create_sqlite_backup()
        if bkp:
            print(f"[BACKUP] Yaratildi: {bkp}")

    async with AsyncSessionLocal() as session:
        res = await crud.audit_and_fix_castle_distribution(session, dry_run=not apply_changes)

    mode = "APPLY" if apply_changes else "DRY-RUN"
    print(f"=== CASTLE DISTRIBUTION ({mode}) ===")
    print(f"START_CASTLES_PER_PLAYER: {res['start_castles_per_player']}")
    print(f"Split/dublikat egalik: {res['split_fixed']}")
    print(f"Bo'shatilgan ortiqcha qal'alar: {res['released_count']}")
    print(f"To'ldirilgan yetishmayotgan qal'alar: {res['assigned_count']}")
    if res["changes"]:
        print("O'zgarishlar:")
        for line in res["changes"][:50]:
            print("  -", line)
    else:
        print("Hech qanday nomutanosiblik topilmadi.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Haqiqiy bazaga o'zgarishlarni qo'llash")
    args = parser.parse_args()
    asyncio.run(main(apply_changes=args.apply))
