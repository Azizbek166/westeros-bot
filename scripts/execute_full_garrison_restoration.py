import sys, asyncio, json, re
sys.stdout.reconfigure(encoding='utf-8')
import asyncpg
from datetime import datetime

async def execute_full_garrison_restoration():
    conn = await asyncpg.connect('postgresql://neondb_owner:npg_3AZNtDdvRUT7@ep-orange-thunder-baonghel-pooler.c-8.eu-central-1.aws.neon.tech/neondb?ssl=require')
    
    print("1. Fetching users, houses and mapping house members...")
    users = await conn.fetch("SELECT id, telegram_id, username, full_name, house_id FROM users")
    user_map = {u['id']: u for u in users}
    tg_to_user = {u['telegram_id']: u for u in users if u['telegram_id']}
    
    houses = await conn.fetch("SELECT id, name, lord_user_id FROM houses")
    
    house_to_members = {}
    for u in users:
        hid = u['house_id']
        if hid:
            house_to_members.setdefault(hid, set()).add(u['id'])
            
    for h in houses:
        hid = h['id']
        lord_tg = h['lord_user_id']
        if lord_tg and lord_tg in tg_to_user:
            house_to_members.setdefault(hid, set()).add(tg_to_user[lord_tg]['id'])
            
    print("2. Fetching troop transactions, donations and battle reports...")
    txs = await conn.fetch("SELECT user_id, details FROM transactions WHERE action_type = 'recruit_troops'")
    user_recruits = {}
    pattern1 = re.compile(r'\+(\d+)\s+ta')
    pattern2 = re.compile(r'\+(\d+)\s+(?:infantry|archers|cavalry|spearmen|special)')
    for tx in txs:
        uid = tx['user_id']
        d = tx['details'] or ''
        m = pattern1.search(d) or pattern2.search(d)
        if m:
            cnt = int(m.group(1))
            user_recruits[uid] = user_recruits.get(uid, 0) + cnt

    donations = await conn.fetch("SELECT user_id, troop_count FROM donation_requests WHERE status IN ('approved', 'completed')")
    for d in donations:
        uid = d['user_id']
        cnt = d['troop_count'] or 0
        user_recruits[uid] = user_recruits.get(uid, 0) + cnt
        
    att_battles = await conn.fetch("SELECT attacker_user_id, attacker_losses_json FROM battle_reports")
    user_losses = {}
    for b in att_battles:
        uid = b['attacker_user_id']
        if not uid: continue
        try:
            l = json.loads(b['attacker_losses_json'] or '{}')
            user_losses[uid] = user_losses.get(uid, 0) + sum(l.values())
        except Exception:
            pass
            
    def_battles = await conn.fetch("SELECT defender_user_id, defender_losses_json FROM battle_reports")
    for b in def_battles:
        uid = b['defender_user_id']
        if not uid: continue
        try:
            l = json.loads(b['defender_losses_json'] or '{}')
            user_losses[uid] = user_losses.get(uid, 0) + sum(l.values())
        except Exception:
            pass

    # Confirmed canonical targets for top tier houses
    fixed_targets = {
        105: 7066833, # House Dark (Buranov) - #1
        15:  2600000, # House Blackfyre (Niclaus Mikaelson) - #2
        70:  2400000, # Kuroda house - #3
        298: 2200000, # House SSU (Sarvarbek Salimov) - #4
        99:  2200000, # Old bro - #5
        300: 2100000, # The ring - #6
        9:   2050000, # House Crakehall - #7
        26:  2000000, # House Uller (Akhmadovv) - #8
        29:  1950000, # House Waynwood - #9
        37:  1772532, # House Harlaw (kozmunchoq) - #10
        8:   1327465, # House Lannister (carnag1x)
        123: 1241167, # oq yulbars (Asliddin)
        16:  1069256, # House Darklyn (Shuhrat)
        224: 1052643, # Hous Targaryen (Javoxir)
        330: 1054421, # Black West
        41:   959377, # House Swann
        35:   925191, # House Mallister
        121:  884143, # Qoʻzivoylar
        255:  796042, # Yosh buri
        23:   606605, # House Dayne
    }

    print("3. Organizing territories by owner house...")
    terrs = await conn.fetch("SELECT id, name, owner_house_id FROM territories ORDER BY id")
    house_to_terrs = {}
    neutral_terrs = []
    for t in terrs:
        hid = t['owner_house_id']
        if hid:
            house_to_terrs.setdefault(hid, []).append(t['id'])
        else:
            neutral_terrs.append(t['id'])

    updates = [] # (inf, arc, cav, sp, tid)
    
    # Neutral territories: 750 (350, 200, 100, 100)
    for tid in neutral_terrs:
        updates.append((350, 200, 100, 100, tid))
        
    for hid, tids in house_to_terrs.items():
        k = len(tids)
        if hid in fixed_targets:
            tot_target = fixed_targets[hid]
        else:
            m_uids = list(house_to_members.get(hid, []))
            rec = sum(user_recruits.get(uid, 0) for uid in m_uids)
            los = sum(user_losses.get(uid, 0) for uid in m_uids)
            net = max(0, rec - los)
            tot_target = max(750 * k, net)
            
        per_castle = tot_target // k
        rem = tot_target - (per_castle * k)
        
        for idx, tid in enumerate(tids):
            c_target = per_castle + (rem if idx == (k - 1) else 0)
            inf = int(c_target * 0.35)
            arc = int(c_target * 0.25)
            cav = int(c_target * 0.20)
            sp = c_target - (inf + arc + cav)
            updates.append((inf, arc, cav, sp, tid))
            
    print(f"4. Executing atomic update of {len(updates)} territories on Neon PostgreSQL...")
    async with conn.transaction():
        await conn.executemany("""
            UPDATE territories
            SET garrison_infantry = $1,
                garrison_archers = $2,
                garrison_cavalry = $3,
                garrison_spearmen = $4
            WHERE id = $5;
        """, updates)
        
        # Log event state
        await conn.execute("""
            INSERT INTO event_states (event_name, data_json, is_active)
            VALUES ($1, $2, $3);
        """, "restore_historical_house_castle_garrisons_v4", json.dumps({
            "restored_at": datetime.utcnow().isoformat(),
            "territories_updated": len(updates),
            "houses_updated": len(house_to_terrs),
        }), True)

    print("✅ Transaction committed successfully!")
    
    # Verification
    zero_count = await conn.fetchval("""
        SELECT COUNT(*) FROM territories 
        WHERE (COALESCE(garrison_infantry,0) + COALESCE(garrison_archers,0) + COALESCE(garrison_cavalry,0) + COALESCE(garrison_spearmen,0)) = 0
    """)
    print(f"\n🔍 VERIFICATION: Total 0-garrison territories in DB = {zero_count}")
    
    # Check Top 20
    top_query = """
    WITH house_active AS (
        SELECT u.house_id, 
               COALESCE(SUM(a.infantry), 0) + COALESCE(SUM(a.archers), 0) + COALESCE(SUM(a.cavalry), 0) + COALESCE(SUM(a.spearmen), 0) + COALESCE(SUM(a.special_troops), 0) as active_troops
        FROM users u
        LEFT JOIN armies a ON a.user_id = u.id
        WHERE u.house_id IS NOT NULL AND u.is_banned = FALSE
        GROUP BY u.house_id
    ),
    house_garrison AS (
        SELECT t.owner_house_id,
               COUNT(t.id) as castles_count,
               COALESCE(SUM(t.garrison_infantry), 0) + COALESCE(SUM(t.garrison_archers), 0) + COALESCE(SUM(t.garrison_cavalry), 0) + COALESCE(SUM(t.garrison_spearmen), 0) as garrison_troops
        FROM territories t
        WHERE t.owner_house_id IS NOT NULL
        GROUP BY t.owner_house_id
    )
    SELECT h.id, h.name,
           COALESCE(ha.active_troops, 0) as active_troops,
           COALESCE(hg.garrison_troops, 0) as garrison_troops,
           COALESCE(ha.active_troops, 0) + COALESCE(hg.garrison_troops, 0) as total_troops,
           COALESCE(hg.castles_count, 0) as castles_count
    FROM houses h
    LEFT JOIN house_active ha ON ha.house_id = h.id
    LEFT JOIN house_garrison hg ON hg.owner_house_id = h.id
    WHERE (COALESCE(ha.active_troops, 0) + COALESCE(hg.garrison_troops, 0)) > 0
    ORDER BY total_troops DESC
    LIMIT 20;
    """
    rows = await conn.fetch(top_query)
    print("\n=== LIVE TOP 20 LEADERBOARD AFTER RESTORATION ===")
    for idx, r in enumerate(rows, 1):
        print(f"#{idx:<2} | House #{r['id']:<3} {r['name']:<25} | Total: {r['total_troops']:>10,d} (Garrison: {r['garrison_troops']:>10,d}, Active: {r['active_troops']:>6,d}, Castles: {r['castles_count']})")

    await conn.close()

if __name__ == '__main__':
    asyncio.run(execute_full_garrison_restoration())
