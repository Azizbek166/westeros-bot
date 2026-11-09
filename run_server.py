"""
Unified Server Runner for The Iron Throne: Xonadonlar Urushi
Runs the FastAPI Telegram Mini App backend and Telegram Bot concurrently.

Usage:
    python run_server.py              # Runs both FastAPI Mini App and Telegram Bot
    python run_server.py --api-only   # Runs only FastAPI (Mini App API & Static files)
    python run_server.py --bot-only   # Runs only Telegram Bot
"""
import os
import sys
import argparse
import logging
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import API_HOST, API_PORT, BOT_TOKEN, MINIAPP_PRIMARY_INTERFACE

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("run_server")


def run_api(host: str = API_HOST, port: int = API_PORT):
    """Run FastAPI application with Uvicorn."""
    import uvicorn
    logger.info(f"Starting FastAPI Telegram Mini App on {host}:{port}...")
    uvicorn.run("api.main:app", host=host, port=port, reload=False)


def run_bot():
    """Run Telegram Bot polling."""
    import bot
    logger.info("Starting Telegram Bot Polling...")
    bot.main()


def run_unified():
    """Run both FastAPI and Telegram Bot concurrently."""
    import threading
    import bot
    
    port = int(os.getenv("PORT", API_PORT))
    logger.info(f"🚀 Initializing unified deployment on port {port} (Primary Interface: {'Mini App' if MINIAPP_PRIMARY_INTERFACE else 'Bot Fallback'})...")
    
    # bot.py already calls start_health_server() which starts Uvicorn in background thread if PORT is set.
    # To guarantee FastAPI starts in unified mode even if PORT was not explicitly exported, set it:
    os.environ["PORT"] = str(port)
    bot.main()


def main():
    parser = argparse.ArgumentParser(description="The Iron Throne RPG Unified Runner")
    parser.add_argument("--api-only", action="store_true", help="Run only the FastAPI Mini App")
    parser.add_argument("--bot-only", action="store_true", help="Run only the Telegram Bot")
    parser.add_argument("--port", type=int, default=None, help="Port to bind FastAPI")
    args = parser.parse_args()

    port = args.port or int(os.getenv("PORT", API_PORT))

    if args.api_only:
        run_api(port=port)
    elif args.bot_only:
        run_bot()
    else:
        run_unified()


if __name__ == "__main__":
    main()
