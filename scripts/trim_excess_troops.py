"""
Qal'alari > 2 va hech qachon donat qilmagan o'yinchilarning askarlarini -80% (20% qoldirish) skripti.
Default: --dry-run (bazaga tegmaydi). Qo'llash uchun: --apply (avval zaxira nusxa oladi).
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
    bdir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backups", f"trim_troops_{ts}"))
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
        res = await crud.audit_and_trim_non_donor_troops(session, dry_run=not apply_changes)

    mode = "APPLY (-80%)" if apply_changes else "DRY-RUN"
    print(f"=== TRIM NON-DONOR TROOPS ({mode}) ===")
    print(f"Jami ta'sirlanadigan o'yinchilar: {res['affected_count']}")
    for row in res["affected"]:
        print(
            f"  - ID={row['user_id']} TG={row['telegram_id']} Ism={row['name']} "
            f"| Qal'alar={row['castles_count']} | Donat=Yo'q "
            f"| Armiya: {row['army_before']} -> {row['army_after']} "
            f"| Garnizon: {row['garrison_before']} -> {row['garrison_after']}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Bazaga qo'llash")
    args = parser.parse_args()
    asyncio.run(main(apply_changes=args.apply))
