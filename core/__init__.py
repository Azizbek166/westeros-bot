"""
Core game engines and logic modules for Westeros MMORPG.
Lazy-loaded exports to avoid circular import issues during package initialization.
"""

__all__ = [
    "calculate_battle",
    "calculate_caravan_raid",
    "resolve_tourney_duel",
    "calculate_hourly_income",
    "calculate_army_upkeep",
    "process_hourly_tick",
    "process_due_marches",
    "process_due_trade_caravans",
    "run_white_walkers_step",
    "can_attack_target",
    "validate_recruitment",
]


def __getattr__(name: str):
    if name in ("calculate_battle", "calculate_caravan_raid", "resolve_tourney_duel"):
        from core import battle_engine
        return getattr(battle_engine, name)
    elif name in ("calculate_hourly_income", "calculate_army_upkeep", "process_hourly_tick"):
        from core import economy_engine
        return getattr(economy_engine, name)
    elif name in ("process_due_marches", "run_white_walkers_step", "process_due_trade_caravans"):
        from core import tick_engine
        return getattr(tick_engine, name)
    elif name in ("can_attack_target", "validate_recruitment"):
        from core import anti_cheat
        return getattr(anti_cheat, name)
    raise AttributeError(f"module 'core' has no attribute '{name}'")
