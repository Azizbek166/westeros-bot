import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from config import DATABASE_URL

logger = logging.getLogger(__name__)

# Asinxron Engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

# SQLite yuqori yuklamada (200-500 user) qotmasligi uchun WAL rejimi
from sqlalchemy import event

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()
    except Exception:
        pass

# Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db():
    """Asinxron kontekst menejer session uchun"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Barcha jadvallarni yaratish va boshlang'ich ma'lumotlarni tekshirish"""
    from database import models
    from data.houses_data import HOUSES_DATA
    from data.map_data import TERRITORIES_DATA

    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
        # Mavjud bazalar uchun xavfsiz ustun qo'shish (SQLite/PostgreSQL)
        for alter_stmt in [
            "ALTER TABLE battle_marches ADD COLUMN has_dragon BOOLEAN DEFAULT 0",
            "ALTER TABLE battle_marches ADD COLUMN dragon_tactic VARCHAR(50) DEFAULT 'none'",
            "ALTER TABLE users ADD COLUMN daily_donation_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN daily_story_quest_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN daily_rank_quest_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN daily_ww_attack_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN equipped_artifact_id INTEGER",
            "ALTER TABLE dragons ADD COLUMN has_laid_egg BOOLEAN DEFAULT 0",
            "ALTER TABLE users ADD COLUMN iron_mine_level INTEGER DEFAULT 1",
        ]:
            try:
                await conn.execute(text(alter_stmt))
            except Exception:
                pass
        logger.info("✅ Barcha ma'lumotlar bazasi jadvallari yaratildi.")

    # 50 ta Xonadon va Hududlarni boshlang'ich holatda yuklash
    async with AsyncSessionLocal() as session:
        # Xonadonlarni kiritish
        for h_code, h_info in HOUSES_DATA.items():
            result = await session.get(models.House, h_info["id"])
            if not result:
                new_house = models.House(
                    id=h_info["id"],
                    code=h_code,
                    name=h_info["name"],
                    emoji=h_info["emoji"],
                    region=h_info["region"],
                    description=h_info.get("description", ""),
                    gold=h_info.get("starting_gold", 5000),
                    food=h_info.get("starting_food", 10000),
                    iron=h_info.get("starting_iron", 2000),
                    prestige=h_info.get("prestige", 100),
                    defense_bonus=h_info.get("defense_bonus", 1.0),
                    special_troop_name=h_info.get("special_troop", "Special Guard"),
                    is_npc=h_info.get("is_npc", False),
                )
                session.add(new_house)

        # Hududlarni kiritish
        for t_code, t_info in TERRITORIES_DATA.items():
            result = await session.get(models.Territory, t_info["id"])
            if not result:
                new_territory = models.Territory(
                    id=t_info["id"],
                    code=t_code,
                    name=t_info["name"],
                    region=t_info["region"],
                    castle_name=t_info["castle"],
                    owner_house_id=t_info.get("initial_owner_id", 1),
                    population=t_info.get("population", 50000),
                    gold_income=t_info.get("gold_income", 200),
                    food_income=t_info.get("food_income", 500),
                    iron_income=t_info.get("iron_income", 100),
                    defense=t_info.get("defense", 500),
                    garrison_infantry=t_info.get("garrison_infantry", 200),
                    garrison_archers=t_info.get("garrison_archers", 100),
                    garrison_cavalry=t_info.get("garrison_cavalry", 50),
                    garrison_spearmen=t_info.get("garrison_spearmen", 50),
                    is_capital=t_info.get("is_capital", False),
                )
                session.add(new_territory)

        await session.commit()
        logger.info("✅ 50 ta Xonadon va Westeros hududlari bazaga kiritildi.")
