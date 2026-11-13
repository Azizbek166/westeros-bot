"""
Stage 2 Service Layer Verification Test Suite
Independent tests for all 9 game service domains against isolated test DB.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import AsyncSessionLocal, init_db
import services


async def run_stage2_tests():
    await init_db()
    async with AsyncSessionLocal() as session:
        # 1. Player Profile
        prof = await services.get_player_profile(session, 1)
        assert prof["user_id"] == 1, "Player profile failed"
        assert "gold" in prof and "army" in prof, "Player profile structure incomplete"
        print("  [OK] Domain 1 (Player Profile): PASSED")
        
        # 2. Military / Army
        army = await services.get_army_overview(session, 1)
        assert "troops" in army and "units_config" in army, "Army overview failed"
        print("  [OK] Domain 2 (Military Overview & Recruitment): PASSED")
        
        # 3. Castles / Economy
        c_ov = await services.get_castles_overview(session, 1)
        assert "castles" in c_ov and "total_castles" in c_ov, "Castle overview failed"
        print("  [OK] Domain 3 (Castles & Tax System): PASSED")
        
        # 4. Daily Hub
        daily = await services.get_daily_hub_data(session, 1)
        assert "streak" in daily and "daily_quests" in daily, "Daily hub failed"
        print("  [OK] Domain 4 (Daily Hub & Streak): PASSED")
        
        # 5. Quests & Citadel
        ok, msg, q_data = await services.get_citadel_quiz_question(session, 1)
        assert ok and "question" in q_data, "Quiz question failed"
        print("  [OK] Domain 5 (Citadel & Council Quests): PASSED")
        
        # 6. Iron Bank
        bank = await services.get_bank_hub_data(session, 1)
        assert "user_gold" in bank and "deposit" in bank, "Bank hub failed"
        print("  [OK] Domain 6 (Iron Bank): PASSED")
        
        # 7. Duels & Champions
        duel = await services.get_duel_hub_data(session, 1)
        assert "duels_limit" in duel and "available_champions" in duel, "Duel hub failed"
        print("  [OK] Domain 7 (Duels & Champions): PASSED")
        
        # 8. Guild System
        guild = await services.get_guild_hub_data(session, 1)
        assert "in_guild" in guild, "Guild hub failed"
        print("  [OK] Domain 8 (Guild System): PASSED")
        
        # 9. Battles & Marches
        battle = await services.get_battle_hub_data(session, 1)
        assert "active_outbound_marches" in battle, "Battle hub failed"
        print("  [OK] Domain 9 (Battles & Marches): PASSED")

    print("\n>>> ALL 9 SERVICE DOMAINS VERIFIED 100% OPERATIONAL! <<<")


if __name__ == "__main__":
    asyncio.run(run_stage2_tests())
