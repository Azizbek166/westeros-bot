"""
API Routers module
"""
from api.routers.player import router as player_router
from api.routers.actions import router as actions_router

__all__ = ["player_router", "actions_router"]
