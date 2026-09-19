from handlers.start_handler import register_start_handlers
from handlers.profile_handler import register_profile_handlers
from handlers.house_handler import register_house_handlers
from handlers.army_handler import register_army_handlers
from handlers.map_handler import register_map_handlers
from handlers.battle_handler import register_battle_handlers
from handlers.quest_handler import register_quest_handlers
from handlers.diplomacy_handler import register_diplomacy_handlers
from handlers.events_handler import register_events_handlers
from handlers.ranking_handler import register_ranking_handlers
from handlers.admin_handler import register_admin_handlers
from handlers.dragon_handler import register_dragon_handlers
from handlers.duel_handler import register_duel_handlers
from handlers.raven_handler import register_raven_handlers
from handlers.trade_handler import register_trade_handlers
from handlers.bank_handler import register_bank_handlers
from handlers.champion_handler import register_champion_handlers
from handlers.season_handler import register_season_handlers

def register_all_handlers(app):
    """Barcha bot handlerlarini Application ga ro'yxatdan o'tkazish"""
    register_start_handlers(app)
    register_profile_handlers(app)
    register_house_handlers(app)
    register_army_handlers(app)
    register_map_handlers(app)
    register_battle_handlers(app)
    register_quest_handlers(app)
    register_diplomacy_handlers(app)
    register_events_handlers(app)
    register_ranking_handlers(app)
    register_admin_handlers(app)
    register_dragon_handlers(app)
    register_duel_handlers(app)
    register_raven_handlers(app)
    register_trade_handlers(app)
    register_bank_handlers(app)
    register_champion_handlers(app)
    register_season_handlers(app)

