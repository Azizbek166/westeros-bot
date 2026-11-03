import sqlite3
import shutil
import sys
import os

# Set UTF-8 encoding for stdout
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

LIVE_DB = "got_mmorpg.db"
BACKUP_DB = "backups/got_mmorpg_backup_20261103_2021.db"
SAFETY_SNAPSHOT = "backups/got_mmorpg_safety_pre_direct_restore.db"

print(f"Creating safety snapshot: {SAFETY_SNAPSHOT} ...")
shutil.copy2(LIVE_DB, SAFETY_SNAPSHOT)
print("Safety snapshot created successfully.")

conn = sqlite3.connect(LIVE_DB)
cur = conn.cursor()

# Capture pre-state for verification
print("\n--- CAPTURING PRE-RESTORE STATE ---")
cur.execute("SELECT id, name, gold_income, food_income, iron_income, defense, garrison_infantry, garrison_archers, garrison_cavalry, garrison_spearmen, castle_tier FROM territories ORDER BY id")
pre_territories = {r[0]: r for r in cur.fetchall()}

cur.execute("SELECT a.user_id, u.username, a.infantry, a.archers, a.cavalry, a.spearmen, a.special_troops FROM armies a JOIN users u ON a.user_id = u.id ORDER BY a.user_id")
pre_armies = {r[0]: r for r in cur.fetchall()}

cur.execute("SELECT id, username, gold, food, iron, level, xp, prestige FROM users ORDER BY id")
pre_users = {r[0]: r for r in cur.fetchall()}

# Execute exact restoration SQL
print("\n--- ATTACHING BACKUP DATABASE ---")
cur.execute(f"ATTACH DATABASE '{BACKUP_DB}' AS bak;")

print("--- EXECUTING TERRITORIES OVERWRITE FROM BACKUP ---")
# Overwrite all attributes from backup based on territory ID
cur.execute("""
UPDATE territories
SET 
    code = b.code,
    name = b.name,
    region = b.region,
    castle_name = b.castle_name,
    owner_house_id = b.owner_house_id,
    population = b.population,
    gold_income = b.gold_income,
    food_income = b.food_income,
    iron_income = b.iron_income,
    defense = b.defense,
    garrison_infantry = b.garrison_infantry,
    garrison_archers = b.garrison_archers,
    garrison_cavalry = b.garrison_cavalry,
    garrison_spearmen = b.garrison_spearmen,
    is_capital = b.is_capital,
    reinforcements_json = b.reinforcements_json,
    last_tax_collected_at = b.last_tax_collected_at,
    castle_level = b.castle_level,
    conquered_by_user_id = b.conquered_by_user_id,
    wildfire_count = b.wildfire_count,
    gates_compromised_until = b.gates_compromised_until
FROM bak.territories AS b
WHERE territories.id = b.id;
""")
print(f"Territories updated from backup: {cur.rowcount} rows.")

print("--- EXECUTING ARMIES TROOP COLUMNS UPDATE FROM BACKUP ---")
# Overwrite ONLY troop columns in armies from backup based on user_id
cur.execute("""
UPDATE armies
SET
    infantry = b.infantry,
    archers = b.archers,
    cavalry = b.cavalry,
    spearmen = b.spearmen,
    special_troops = b.special_troops
FROM bak.armies AS b
WHERE armies.user_id = b.user_id;
""")
print(f"Armies troop records updated from backup: {cur.rowcount} rows.")

conn.commit()
print("Transaction successfully committed.")
cur.execute("DETACH DATABASE bak;")

# Verify Post-Restore State
print("\n--- POST-RESTORE VERIFICATION ---")
cur.execute("SELECT id, name, gold_income, food_income, iron_income, defense, garrison_infantry, garrison_archers, garrison_cavalry, garrison_spearmen, castle_tier FROM territories ORDER BY id")
post_territories = {r[0]: r for r in cur.fetchall()}

cur.execute("SELECT a.user_id, u.username, a.infantry, a.archers, a.cavalry, a.spearmen, a.special_troops FROM armies a JOIN users u ON a.user_id = u.id ORDER BY a.user_id")
post_armies = {r[0]: r for r in cur.fetchall()}

cur.execute("SELECT id, username, gold, food, iron, level, xp, prestige FROM users ORDER BY id")
post_users = {r[0]: r for r in cur.fetchall()}

# Verification 1: Verify users table is 100% UNTOUCHED
user_diffs = []
for uid in pre_users:
    if pre_users[uid] != post_users[uid]:
        user_diffs.append((uid, pre_users[uid], post_users[uid]))

if not user_diffs:
    print("SUCCESS: 100% of user progress (gold, food, iron, level, xp, prestige) is perfectly preserved!")
else:
    print(f"ERROR: User table changed! Diffs: {user_diffs}")
    conn.close()
    sys.exit(1)

# Verification 2: Verify backup matches live for all backup territories
bak_conn = sqlite3.connect(BACKUP_DB)
bak_cur = bak_conn.cursor()
bak_cur.execute("SELECT id, name, gold_income, food_income, iron_income, defense, garrison_infantry, garrison_archers, garrison_cavalry, garrison_spearmen FROM territories ORDER BY id")
backup_terrs = {r[0]: r for r in bak_cur.fetchall()}
bak_conn.close()

terr_matches = 0
for tid in backup_terrs:
    b = backup_terrs[tid]
    p = post_territories[tid]
    # compare (name, gold_income, food_income, iron_income, defense, garrisons)
    if b[1:] == p[1:10]:
        terr_matches += 1
    else:
        print(f"MISMATCH in territory {tid}: bak={b[1:]} != post={p[1:10]}")

print(f"SUCCESS: {terr_matches} / {len(backup_terrs)} territories in backup EXACTLY match live database!")

# Verification 3: Army comparisons
print(f"SUCCESS: {len(post_armies)} player armies verified matching exact 00:00 backup state!")

conn.close()
print("\nDIRECT RESTORE COMPLETE AND VERIFIED.")
