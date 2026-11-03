#!/usr/bin/env python3
"""
THE IRON THRONE — Qal'alar Garnizonini Tiklash Skripti
Ushbu skript jonli ma'lumotlar bazasidagi (got_mmorpg.db) o'yinchilarning
shaxsiy ma'lumotlariga (pul, daraja, inventar, profil) mutlaqo tegmagan holda,
FAQAT VA FAQAT qal'alar (territories) jadvalidagi garnizon askarlari sonini
zaxira bazadan yoki kanonik standartdan olib xavfsiz UPDATE qiladi.
"""

import sys
import os
import sqlite3
import argparse

# Windows konsolida UTF-8 chiqishini ta'minlash
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# data/map_data.py ni yuklash uchun yo'lni qo'shish
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from data.map_data import TERRITORIES_DATA
except ImportError:
    TERRITORIES_DATA = {}

# Custom (yangidan ochilgan) qal'alar uchun darajaga mos garnizon standarti
CUSTOM_TIER_GARRISON = {
    1: {"infantry": 350, "archers": 200, "cavalry": 100, "spearmen": 100},  # Boshlang'ich
    2: {"infantry": 450, "archers": 250, "cavalry": 150, "spearmen": 150},
    3: {"infantry": 600, "archers": 350, "cavalry": 200, "spearmen": 200},
    4: {"infantry": 800, "archers": 450, "cavalry": 250, "spearmen": 250},
    5: {"infantry": 1000, "archers": 600, "cavalry": 350, "spearmen": 350}, # Afsonaviy
}


def update_garrisons(live_db_path: str, backup_db_path: str = None):
    if not os.path.exists(live_db_path):
        print(f"[XATO] Jonli baza fayli topilmadi: {live_db_path}")
        return False

    print(f"[*] Jonli bazaga ulanmoqda: {live_db_path}")
    live_conn = sqlite3.connect(live_db_path)
    live_conn.row_factory = sqlite3.Row
    live_cur = live_conn.cursor()

    backup_garrisons = {}
    if backup_db_path and os.path.exists(backup_db_path):
        print(f"[*] Zaxira bazadan garnizonlar o'qilmoqda: {backup_db_path}")
        try:
            bak_conn = sqlite3.connect(backup_db_path)
            bak_conn.row_factory = sqlite3.Row
            bak_cur = bak_conn.cursor()
            rows = bak_cur.execute(
                "SELECT id, garrison_infantry, garrison_archers, garrison_cavalry, garrison_spearmen FROM territories"
            ).fetchall()
            for r in rows:
                backup_garrisons[r['id']] = {
                    'infantry': r['garrison_infantry'] or 0,
                    'archers': r['garrison_archers'] or 0,
                    'cavalry': r['garrison_cavalry'] or 0,
                    'spearmen': r['garrison_spearmen'] or 0,
                }
            bak_conn.close()
            print(f"[OK] Zaxira bazadan {len(backup_garrisons)} ta qal'a garnizoni olindi.")
        except Exception as e:
            print(f"[OGOHLANTIRISH] Zaxira bazadan o'qishda xatolik: {e}")

    # Jonli bazadagi qal'alarni olish
    live_terrs = live_cur.execute(
        "SELECT id, code, name, garrison_infantry, garrison_archers, garrison_cavalry, garrison_spearmen, castle_level, castle_tier FROM territories ORDER BY id"
    ).fetchall()

    print(f"[*] Qal'alar garnizonini yangilash jarayoni (Jami: {len(live_terrs)} ta qal'a)...")
    updated_count = 0

    for t in live_terrs:
        t_id = t['id']
        t_code = t['code']
        t_name = t['name']
        c_lvl = t['castle_level'] or 1

        b_inf = t['garrison_infantry'] or 0
        b_arc = t['garrison_archers'] or 0
        b_cav = t['garrison_cavalry'] or 0
        b_sp = t['garrison_spearmen'] or 0
        old_total = b_inf + b_arc + b_cav + b_sp

        # 1-usul: Zaxira bazada saqlangan qonuniy garnizon
        target = backup_garrisons.get(t_id)

        # 2-usul: Agar zaxirada bo'lmasa yoki zaxiradagi son normadan tashqari bo'lsa -> Kanonik map_data
        if not target or (target['infantry'] + target['archers'] + target['cavalry'] + target['spearmen'] > 50000):
            c_data = TERRITORIES_DATA.get(t_code)
            if not c_data:
                for k, v in TERRITORIES_DATA.items():
                    if v.get('id') == t_id:
                        c_data = v
                        break
            if c_data:
                target = {
                    'infantry': c_data.get('garrison_infantry', 200),
                    'archers': c_data.get('garrison_archers', 100),
                    'cavalry': c_data.get('garrison_cavalry', 50),
                    'spearmen': c_data.get('garrison_spearmen', 50),
                }
            else:
                # Custom (o'yinchilar ochgan) qal'a standarti
                target = CUSTOM_TIER_GARRISON.get(c_lvl, CUSTOM_TIER_GARRISON[1])

        new_total = target['infantry'] + target['archers'] + target['cavalry'] + target['spearmen']

        # Faqat o'zgargan qal'alarni UPDATE qilish
        if (b_inf != target['infantry'] or b_arc != target['archers'] or
            b_cav != target['cavalry'] or b_sp != target['spearmen']):
            live_cur.execute("""
                UPDATE territories
                SET garrison_infantry = ?,
                    garrison_archers = ?,
                    garrison_cavalry = ?,
                    garrison_spearmen = ?
                WHERE id = ?
            """, (target['infantry'], target['archers'], target['cavalry'], target['spearmen'], t_id))
            print(f"[YANGILANDI] Qal'a #{t_id} ({t_name}): {old_total:,} -> {new_total:,} askar (Piyoda: {target['infantry']}, Kamonchi: {target['archers']}, Otliq: {target['cavalry']}, Nayzachi: {target['spearmen']})")
            updated_count += 1

    live_conn.commit()
    live_conn.close()

    print(f"\n[OK] Yakunlandi! {updated_count} ta qal'a garnizoni muvaffaqiyatli UPDATE qilindi.")
    print("[HIMOYA] O'yinchilar profillari, puli, XP, darajasi va inventariga mutlaqo tegilmadi!")
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Qal'alar garnizonini faqat territories jadvalida yangilash")
    parser.add_argument('--live', default='got_mmorpg.db', help='Jonli database fayli yo\'li')
    parser.add_argument('--backup', default='backups/got_mmorpg_backup_20261103_2021.db', help='Zaxira (backup) database fayli yo\'li')
    args = parser.parse_args()

    update_garrisons(args.live, args.backup)
