import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from config import DATABASE_URL

logger = logging.getLogger(__name__)

# Asinxron Engine va SQLite sozlamalari
from sqlalchemy import event, select, text, update, delete

def create_custom_engine(db_url: str):
    is_sqlite = "sqlite" in db_url
    engine_kwargs = {
        "echo": False,
        "pool_pre_ping": True,
    }
    if not is_sqlite:
        engine_kwargs.update({
            "pool_size": 20,
            "max_overflow": 30,
            "pool_timeout": 30,
            "pool_recycle": 1800,
        })
    eng = create_async_engine(
        db_url,
        **engine_kwargs
    )
    if is_sqlite:
        @event.listens_for(eng.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.execute("PRAGMA cache_size=-64000")
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.close()
            except Exception:
                pass
    return eng

engine = create_custom_engine(DATABASE_URL)

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
    """Barcha jadvallarni yaratish va boshlang'ich ma'lumotlarni tekshirish (PostgreSQL xatosi bo'lsa SQLite ga avto-o'tadi)"""
    global engine, AsyncSessionLocal
    from database import models
    from data.houses_data import HOUSES_DATA
    from data.map_data import TERRITORIES_DATA

    try:
        async with engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
    except Exception as e:
        if "sqlite" not in engine.url.drivername:
            logger.error(f"⚠️ PostgreSQL serveriga ulanib bo'lmadi ({e}). Server muddati tugagan yoki o'chirilgan bo'lishi mumkin.")
            logger.warning("🔄 Bot avtomatik tarzda mustaqil SQLite bazasiga o'tkazilmoqda!")
            from config import DEFAULT_DB_PATH
            fallback_url = f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}"
            engine = create_custom_engine(fallback_url)
            AsyncSessionLocal.configure(bind=engine)
            async with engine.begin() as conn:
                await conn.run_sync(models.Base.metadata.create_all)
        else:
            raise

    async with engine.begin() as conn:
        # Mavjud SQLite bazalar uchun xavfsiz ustun qo'shish (PostgreSQL yangi bazada create_all barcha ustunlarni yaratadi)
        if "sqlite" in engine.url.drivername:
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
                "ALTER TABLE users ADD COLUMN daily_bandit_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN daily_plague_count INTEGER DEFAULT 0",
                "ALTER TABLE territories ADD COLUMN last_tax_collected_at DATETIME",
                "ALTER TABLE dragons ADD COLUMN artifact_code VARCHAR(50)",
                "ALTER TABLE houses ADD COLUMN lord_elected_at DATETIME",
                "ALTER TABLE users ADD COLUMN daily_duel_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN daily_recruit_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN grain_mill_level INTEGER DEFAULT 1",
                "ALTER TABLE territories ADD COLUMN castle_level INTEGER DEFAULT 1",
                "ALTER TABLE territories ADD COLUMN conquered_by_user_id INTEGER",
                "ALTER TABLE battle_marches ADD COLUMN dragon_id INTEGER",
                "ALTER TABLE users ADD COLUMN title VARCHAR(100)",
                "ALTER TABLE users ADD COLUMN streak_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN last_streak_date VARCHAR(10) DEFAULT ''",
                "ALTER TABLE houses ADD COLUMN group_chat_id BIGINT",
                "ALTER TABLE houses ADD COLUMN group_title VARCHAR(200)",
                "ALTER TABLE armies ADD COLUMN catapults INTEGER DEFAULT 0",
                "ALTER TABLE armies ADD COLUMN siege_towers INTEGER DEFAULT 0",
                "ALTER TABLE territories ADD COLUMN wildfire_count INTEGER DEFAULT 0",
                "ALTER TABLE battle_marches ADD COLUMN catapults INTEGER DEFAULT 0",
                "ALTER TABLE battle_marches ADD COLUMN siege_towers INTEGER DEFAULT 0",
                "ALTER TABLE armies ADD COLUMN champion VARCHAR(50)",
                "ALTER TABLE battle_marches ADD COLUMN champion VARCHAR(50)",
                "ALTER TABLE territories ADD COLUMN gates_compromised_until DATETIME",
                "ALTER TABLE users ADD COLUMN daily_caravan_send_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN daily_caravan_raid_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN daily_spy_scout_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN daily_spy_sabotage_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN daily_spy_gates_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN castle_taxes_json TEXT DEFAULT '{}'",
                "ALTER TABLE users ADD COLUMN daily_chest_date VARCHAR(10) DEFAULT ''",
                "ALTER TABLE users ADD COLUMN daily_quests_claimed_json TEXT DEFAULT '{}'",
                "ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT 0",
                "ALTER TABLE tournaments ADD COLUMN bracket_json TEXT DEFAULT '{}'",
                "ALTER TABLE tournament_participants ADD COLUMN tactic VARCHAR(30) DEFAULT 'rock'",
                "ALTER TABLE tournament_participants ADD COLUMN tactics_seq VARCHAR(100) DEFAULT 'rock,scissors,paper'",
                "ALTER TABLE users ADD COLUMN vip_tier VARCHAR(50)",
                "ALTER TABLE users ADD COLUMN vip_until DATETIME",
                "ALTER TABLE users ADD COLUMN custom_photo_file_id VARCHAR(255)",
                "ALTER TABLE users ADD COLUMN custom_status VARCHAR(255)",
                "ALTER TABLE users ADD COLUMN custom_audio_file_id VARCHAR(255)",
                "ALTER TABLE users ADD COLUMN custom_audio_title VARCHAR(255)",
                "ALTER TABLE users ADD COLUMN royal_decree_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN daily_gold_earned BIGINT DEFAULT 0",
                "ALTER TABLE users ADD COLUMN daily_prestige_earned INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN weekly_gold_earned BIGINT DEFAULT 0",
                "ALTER TABLE users ADD COLUMN weekly_prestige_earned INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN weekly_limit_date VARCHAR(10) DEFAULT ''",
                "ALTER TABLE users ADD COLUMN custom_video_file_id VARCHAR(255)",
                "ALTER TABLE territories ADD COLUMN castle_tier INTEGER DEFAULT 2",
            ]:
                try:
                    await conn.execute(text(alter_stmt))
                except Exception:
                    pass
        else:
            # PostgreSQL (Render)
            for pg_alter in [
                "ALTER TABLE donation_requests DROP CONSTRAINT IF EXISTS donation_requests_user_id_fkey",
                "ALTER TABLE donation_requests ALTER COLUMN user_id DROP NOT NULL",
                "ALTER TABLE hall_of_fame DROP CONSTRAINT IF EXISTS hall_of_fame_king_user_id_fkey",
                "ALTER TABLE territories DROP CONSTRAINT IF EXISTS territories_conquered_by_user_id_fkey",
                "ALTER TABLE tournaments DROP CONSTRAINT IF EXISTS tournaments_winner_user_id_fkey",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_duel_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_recruit_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_caravan_send_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_caravan_raid_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_spy_scout_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_spy_sabotage_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_spy_gates_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS castle_taxes_json TEXT DEFAULT '{}'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_chest_date VARCHAR(10) DEFAULT ''",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_quests_claimed_json TEXT DEFAULT '{}'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE",
                "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS bracket_json TEXT DEFAULT '{}'",
                "ALTER TABLE tournament_participants ADD COLUMN IF NOT EXISTS tactic VARCHAR(30) DEFAULT 'rock'",
                "ALTER TABLE tournament_participants ADD COLUMN IF NOT EXISTS tactics_seq VARCHAR(100) DEFAULT 'rock,scissors,paper'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS iron_mine_level INTEGER DEFAULT 1",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS grain_mill_level INTEGER DEFAULT 1",
                "ALTER TABLE territories ADD COLUMN IF NOT EXISTS castle_level INTEGER DEFAULT 1",
                "ALTER TABLE territories ADD COLUMN IF NOT EXISTS conquered_by_user_id INTEGER",
                "ALTER TABLE battle_marches ADD COLUMN IF NOT EXISTS dragon_id INTEGER",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS title VARCHAR(100)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_streak_date VARCHAR(10) DEFAULT ''",
                "ALTER TABLE houses ADD COLUMN IF NOT EXISTS group_chat_id BIGINT",
                "ALTER TABLE houses ADD COLUMN IF NOT EXISTS group_title VARCHAR(200)",
                "ALTER TABLE armies ADD COLUMN IF NOT EXISTS catapults INTEGER DEFAULT 0",
                "ALTER TABLE armies ADD COLUMN IF NOT EXISTS siege_towers INTEGER DEFAULT 0",
                "ALTER TABLE territories ADD COLUMN IF NOT EXISTS wildfire_count INTEGER DEFAULT 0",
                "ALTER TABLE territories ADD COLUMN IF NOT EXISTS gates_compromised_until TIMESTAMP",
                "ALTER TABLE battle_marches ADD COLUMN IF NOT EXISTS catapults INTEGER DEFAULT 0",
                "ALTER TABLE battle_marches ADD COLUMN IF NOT EXISTS siege_towers INTEGER DEFAULT 0",
                "ALTER TABLE armies ADD COLUMN IF NOT EXISTS champion VARCHAR(50)",
                "ALTER TABLE battle_marches ADD COLUMN IF NOT EXISTS champion VARCHAR(50)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_tier VARCHAR(50)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_until TIMESTAMP",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_photo_file_id VARCHAR(255)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_video_file_id VARCHAR(255)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_status VARCHAR(255)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_audio_file_id VARCHAR(255)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_audio_title VARCHAR(255)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS royal_decree_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_gold_earned BIGINT DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_prestige_earned INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_gold_earned BIGINT DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_prestige_earned INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_limit_date VARCHAR(10) DEFAULT ''",
                "ALTER TABLE territories ADD COLUMN IF NOT EXISTS castle_tier INTEGER DEFAULT 2",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS equipped_artifact_id INTEGER",
            ]:
                try:
                    await conn.execute(text(pg_alter))
                except Exception:
                    pass

        # spy_missions jadvali mavjudligini kafolatlash
        try:
            if "sqlite" in engine.url.drivername:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS spy_missions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        target_territory_id INTEGER NOT NULL,
                        mission_type VARCHAR(50) NOT NULL,
                        cost_gold INTEGER DEFAULT 1000,
                        status VARCHAR(30) DEFAULT 'success',
                        report_text TEXT DEFAULT '',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS spy_missions (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        target_territory_id INTEGER NOT NULL,
                        mission_type VARCHAR(50) NOT NULL,
                        cost_gold INTEGER DEFAULT 1000,
                        status VARCHAR(30) DEFAULT 'success',
                        report_text TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
        except Exception as e:
            logger.warning(f"spy_missions table check: {e}")

        # Check if dragons table in SQLite has obsolete UNIQUE constraint on user_id
        if "sqlite" in engine.url.drivername:
            try:
                res = await conn.execute(text("SELECT sql FROM sqlite_master WHERE name='dragons' AND type='table'"))
                table_sql = res.scalar()
                if table_sql and "user_id INTEGER UNIQUE" in table_sql:
                    logger.info("Migrating dragons table to remove UNIQUE on user_id...")
                    await conn.execute(text("PRAGMA foreign_keys=OFF"))
                    await conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS dragons_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            name TEXT NOT NULL,
                            grade TEXT DEFAULT 'C',
                            stage TEXT DEFAULT 'egg',
                            level INTEGER DEFAULT 1,
                            hunger INTEGER DEFAULT 50,
                            power INTEGER DEFAULT 100,
                            artifact_code VARCHAR(50),
                            has_laid_egg BOOLEAN DEFAULT 0,
                            last_fed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY(user_id) REFERENCES users(id)
                        )
                    """))
                    await conn.execute(text("""
                        INSERT INTO dragons_new (id, user_id, name, grade, stage, level, hunger, power, artifact_code, has_laid_egg, last_fed, created_at)
                        SELECT id, user_id, name, grade, stage, level, hunger, power, artifact_code, has_laid_egg, last_fed, created_at FROM dragons
                    """))
                    await conn.execute(text("DROP TABLE dragons"))
                    await conn.execute(text("ALTER TABLE dragons_new RENAME TO dragons"))
                    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_dragons_user_id ON dragons(user_id)"))
                    await conn.execute(text("PRAGMA foreign_keys=ON"))
                    logger.info("Dragons table migrated successfully.")
            except Exception as e:
                logger.warning(f"Dragons table migration check: {e}")

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
            elif result.id == 15 and "Blackfyre" in h_info["name"] and result.name != h_info["name"]:
                result.name = h_info["name"]
                result.emoji = h_info["emoji"]
                result.code = h_code
                result.description = h_info.get("description", "")
                result.special_troop_name = h_info.get("special_troop", "Blackfyre Dragonblades")

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
                    owner_house_id=t_info.get("initial_owner_id"),
                    population=t_info.get("population", 50000),
                    gold_income=t_info.get("gold_income", 20),
                    food_income=t_info.get("food_income", 50),
                    iron_income=t_info.get("iron_income", 15),
                    defense=t_info.get("defense", 500),
                    garrison_infantry=t_info.get("garrison_infantry", 200),
                    garrison_archers=t_info.get("garrison_archers", 100),
                    garrison_cavalry=t_info.get("garrison_cavalry", 50),
                    garrison_spearmen=t_info.get("garrison_spearmen", 50),
                    is_capital=t_info.get("is_capital", False),
                    castle_tier=t_info.get("castle_tier", 2),
                    castle_level=1,
                )
                session.add(new_territory)
            else:
                # Barcha qal'alar solig'i va toifasini map_data bilan muvofiqlashtirish (egasiz qal'alarga tegilmaydi)
                result.gold_income = t_info.get("gold_income", 40)
                result.food_income = t_info.get("food_income", 100)
                result.iron_income = t_info.get("iron_income", 30)
                result.castle_tier = t_info.get("castle_tier", 2)

        # Barcha yangi ochilgan yoki custom qal'alar daromadini ham 2x me'yorlarga to'g'rilash
        all_terrs_res = await session.execute(select(models.Territory))
        tier_standards = {
            1: {"gold": 1000, "food": 2000, "iron": 900},
            2: {"gold": 600, "food": 1600, "iron": 520},
            3: {"gold": 380, "food": 1100, "iron": 340},
        }
        for terr in all_terrs_res.scalars().all():
            if terr.id > 60 or terr.code not in TERRITORIES_DATA:
                c_tier = terr.castle_tier or 2
                std = tier_standards.get(c_tier, tier_standards[2])
                if (terr.gold_income or 0) < std["gold"]:
                    terr.gold_income = std["gold"]
                    terr.food_income = std["food"]
                    terr.iron_income = std["iron"]
                    terr.castle_tier = c_tier


        # Tun Qiroli (White Walkers) global eventini 500,000 HP ga yangilash
        import json
        ev_res = await session.execute(select(models.EventState).where(models.EventState.event_name == "white_walkers"))
        ww_ev = ev_res.scalar_one_or_none()
        if ww_ev:
            try:
                ev_data = json.loads(ww_ev.data_json or "{}")
                if ev_data.get("max_hp", 0) < 500000:
                    ev_data["max_hp"] = 500000
                    if ev_data.get("hp", 0) <= 250000:
                        ev_data["hp"] = 500000
                    ww_ev.data_json = json.dumps(ev_data)
            except Exception:
                pass
        else:
            new_ww = models.EventState(
                event_name="white_walkers",
                data_json=json.dumps({"hp": 500000, "max_hp": 500000, "status": "active"}),
                is_active=True,
            )
            session.add(new_ww)

        # Mavsumlar (30-kunlik Seasons) tizimi boshlang'ich 1-mavsumini ishga tushirish
        from datetime import timedelta
        s_res = await session.execute(select(models.SeasonState).where(models.SeasonState.is_active == True))
        active_season = s_res.scalar_one_or_none()
        if not active_season:
            now = datetime.utcnow()
            season1 = models.SeasonState(
                season_number=1,
                start_date=now,
                end_date=now + timedelta(days=30),
                is_active=True,
            )
            session.add(season1)
            logger.info("✅ 1-Mavsum (Season 1) muvaffaqiyatli ishga tushirildi (30 kunlik sikl).")

        # Dinamik Ob-havo (Dinamik Fasllar) boshlang'ich holati
        weather_res = await session.execute(select(models.EventState).where(models.EventState.event_name == "world_weather"))
        weather_ev = weather_res.scalar_one_or_none()
        if not weather_ev:
            init_weather = models.EventState(
                event_name="world_weather",
                data_json=json.dumps({
                    "weather_type": "severe_winter",
                    "name": "Qattiq Qish (Severe Winter)",
                    "description": "Shimolda mudofaa +15%, askarlar oziq-ovqat sarfi +25%. Ayozli izg'irinlar esmoqda.",
                    "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat(),
                }),
                is_active=True,
            )
            session.add(init_weather)
            logger.info("✅ Westeros ob-havosi (Qattiq Qish) o'rnatildi.")

        # Haftalik Ritsarlar Turnirini tekshirish/boshlash
        tourney_res = await session.execute(select(models.Tournament).where(models.Tournament.status == "active"))
        active_tourney = tourney_res.scalar_one_or_none()
        if not active_tourney:
            new_tourney = models.Tournament(
                name="Qirol Qo'li Turniri #1",
                status="active",
                prize_pool=7500,
                details="Qirollikning eng qudratli ritsarlari jangi! G'olibga 70% xazina va 'Qirollik Chempioni' sharafli unvoni beriladi.",
                created_at=datetime.utcnow()
            )
            session.add(new_tourney)
            logger.info("✅ Haftalik Ritsarlar Turniri #1 yaratildi.")

        # Barcha xonadonlardan is_npc holatini tozalash (NPC xonadonlar butunlay bekor qilindi)
        await session.execute(update(models.House).values(is_npc=False))

        # Crakehall xonadoni (id=9) arbitraj oqibatida 300M dan oshib ketgan xazinasini asl holatiga qaytarish
        crakehall = await session.get(models.House, 9)
        if crakehall and (crakehall.gold or 0) > 50000000:
            logger.info(f"🧹 Crakehall xazinasi arbitrajdan tozalandi: {crakehall.gold:,} -> 5,500 oltin")
            crakehall.gold = 5500
            crakehall.food = 7500
            crakehall.iron = 3200

        # Arbitrajdan foydalanib 50M dan ko'p oltin to'plagan o'yinchilarni tozalash
        await session.execute(
            update(models.User)
            .where(models.User.gold > 50000000)
            .values(gold=10000)
        )

        # Barrowton (id=43) va boshqa kanonik neytral qal'alarni egasiz holatda saqlash
        for t_code, t_info in TERRITORIES_DATA.items():
            if t_info.get("initial_owner_id") is None:
                terr_obj = await session.get(models.Territory, t_info["id"])
                if terr_obj and not terr_obj.conquered_by_user_id and terr_obj.owner_house_id is not None:
                    logger.info(f"🏛️ #{terr_obj.id} {terr_obj.name} qal'asi egasiz (neytral) holatga qaytarildi (avvalgi egasi: {terr_obj.owner_house_id}).")
                    terr_obj.owner_house_id = None
                    terr_obj.conquered_by_user_id = None

        # House Blackfyre (id=15) da 5 ta qal'a limitini qat'iy tekshirish (ortiqcha qal'alarni egasiz qilish)
        bf_left_res = await session.execute(
            select(models.Territory)
            .where(models.Territory.owner_house_id == 15)
            .order_by(models.Territory.id.desc())
        )
        bf_left = bf_left_res.scalars().all()
        if len(bf_left) > 5:
            excess = bf_left[:len(bf_left) - 5]
            for t in excess:
                t.owner_house_id = None
                t.conquered_by_user_id = None
                t.defense = 500
                t.castle_level = 1
                t.wildfire_count = 0
                t.reinforcements_json = "{}"
                t.garrison_infantry = 200
                t.garrison_archers = 100
                t.garrison_cavalry = 50
                t.garrison_spearmen = 50
                logger.info(f"🏰 Blackfyre xonadonidagi 5 tadan ortiqcha bo'lgan #{t.id} {t.name} qal'asi egasiz (neytral) holatga keltirildi.")

        # Barcha qolgan xonadonlarda ham 5 ta qal'a limitini qat'iy tekshirish
        all_houses_res = await session.execute(select(models.House))
        for h in all_houses_res.scalars().all():
            h_t_res = await session.execute(
                select(models.Territory)
                .where(models.Territory.owner_house_id == h.id)
                .order_by(models.Territory.is_capital.desc(), models.Territory.id)
            )
            h_terrs = h_t_res.scalars().all()
            if len(h_terrs) > 5:
                for t in h_terrs[5:]:
                    t.owner_house_id = None
                    t.conquered_by_user_id = None
                    t.defense = 500
                    t.castle_level = 1
                    t.wildfire_count = 0
                    t.reinforcements_json = "{}"
                    t.garrison_infantry = 200
                    t.garrison_archers = 100
                    t.garrison_cavalry = 50
                    t.garrison_spearmen = 50
                    logger.info(f"🏰 Xonadon #{h.id} ({h.name}) ning ortiqcha #{t.id} {t.name} qal'asi egasiz holatga keltirildi.")

        # Tun Qiroli (White Walkers) reytingi, hissalari va hujum sonini 0 ga tushirish (HP: 1,000,000)
        await session.execute(delete(models.NightKingContribution))
        await session.execute(update(models.User).values(daily_ww_attack_count=0))
        ww_res = await session.execute(select(models.EventState).where(models.EventState.event_name == "white_walkers"))
        ww_state = ww_res.scalar_one_or_none()
        if ww_state:
            ww_state.data_json = json.dumps({"hp": 1000000, "max_hp": 1000000, "status": "active"})
            ww_state.is_active = True
        else:
            session.add(models.EventState(
                event_name="white_walkers",
                data_json=json.dumps({"hp": 1000000, "max_hp": 1000000, "status": "active"}),
                is_active=True,
            ))
        logger.info("❄️ Tun Qiroli (White Walkers) reytingi 0 ga tushirildi va HP 1,000,000 ga kuchaytirildi.")

        # Kunlik va haftalik reytingdagi eski chalkash ma'lumotlarni tozalash (faqat aktual sana ko'rsatiladi)
        today_clean_str = (datetime.utcnow() + timedelta(hours=5)).strftime("%Y-%m-%d")
        week_clean_str = (datetime.utcnow() + timedelta(hours=5)).strftime("%Y-W%W")

        # 1. Yangi kun kelgan o'yinchilarning barcha kunlik limitlarini to'liq va to'g'ri nolga tushirish
        await session.execute(
            update(models.User)
            .where(models.User.daily_limit_date != today_clean_str)
            .values(
                daily_quiz_count=0,
                daily_council_count=0,
                daily_secret_quest_count=0,
                daily_donation_count=0,
                daily_story_quest_count=0,
                daily_rank_quest_count=0,
                daily_ww_attack_count=0,
                daily_bandit_count=0,
                daily_plague_count=0,
                daily_duel_count=0,
                daily_recruit_count=0,
                daily_caravan_send_count=0,
                daily_caravan_raid_count=0,
                daily_spy_scout_count=0,
                daily_spy_sabotage_count=0,
                daily_spy_gates_count=0,
                daily_quests_claimed_json="{}",
                daily_gold_earned=0,
                daily_prestige_earned=0,
                daily_limit_date=today_clean_str,
            )
        )
        await session.execute(
            update(models.User)
            .where(models.User.weekly_limit_date != week_clean_str)
            .values(weekly_gold_earned=0, weekly_prestige_earned=0, weekly_limit_date=week_clean_str)
        )

        # 2. Avvalgi xatolik tufayli qotib qolgan o'yinchilar limitlarini bir martalik to'liq yechish
        mig_flag_res = await session.execute(
            select(models.EventState).where(models.EventState.event_name == "daily_limits_unstick_v1")
        )
        if not mig_flag_res.scalars().first():
            logger.info("🔧 O'yinchilarning qotib qolgan barcha limitlari va topshiriqlari 0 ga tushirilmoqda (bir martalik tozalash)...")
            await session.execute(
                update(models.User)
                .values(
                    daily_quiz_count=0,
                    daily_council_count=0,
                    daily_secret_quest_count=0,
                    daily_donation_count=0,
                    daily_story_quest_count=0,
                    daily_rank_quest_count=0,
                    daily_ww_attack_count=0,
                    daily_bandit_count=0,
                    daily_plague_count=0,
                    daily_duel_count=0,
                    daily_recruit_count=0,
                    daily_caravan_send_count=0,
                    daily_caravan_raid_count=0,
                    daily_spy_scout_count=0,
                    daily_spy_sabotage_count=0,
                    daily_spy_gates_count=0,
                    daily_quests_claimed_json="{}",
                    daily_gold_earned=0,
                    daily_prestige_earned=0,
                    daily_limit_date=today_clean_str,
                )
            )
            session.add(models.EventState(
                event_name="daily_limits_unstick_v1",
                data_json=json.dumps({"applied_at": today_clean_str}),
                is_active=True,
            ))

        # Fronterra va barcha maxsus xonadonlar maydonlarini tekshirib to'g'irlash (House panel crash bo'lmasligi uchun)
        all_houses_check = await session.execute(select(models.House))
        for h in all_houses_check.scalars().all():
            if h.defense_bonus is None:
                h.defense_bonus = 1.0
            if h.gold is None:
                h.gold = 5000
            if h.food is None:
                h.food = 10000
            if h.iron is None:
                h.iron = 2000
            if h.prestige is None:
                h.prestige = 100
            if not h.description:
                h.description = f"{h.name} shonli xonadoni."
            if not h.special_troop_name:
                h.special_troop_name = f"{h.name} Gvardiyasi"

        # House Blackfyre (id=15) a'zolariga yo'qolgan 200,000 askarini shaxsiy armiyasiga qaytarish
        bf_users_res = await session.execute(select(models.User).where(models.User.house_id == 15))
        for u in bf_users_res.scalars().all():
            army_res = await session.execute(select(models.Army).where(models.Army.user_id == u.id))
            army = army_res.scalar_one_or_none()
            if not army:
                army = models.Army(user_id=u.id, infantry=0, archers=0, cavalry=0, spearmen=0)
                session.add(army)
                await session.flush()
            curr_tot = (army.infantry or 0) + (army.archers or 0) + (army.cavalry or 0) + (army.spearmen or 0)
            if curr_tot < 200000:
                needed = 200000 - curr_tot
                add_inf = int(needed * 0.35)
                add_arc = int(needed * 0.25)
                add_cav = int(needed * 0.20)
                add_sp = needed - (add_inf + add_arc + add_cav)
                army.infantry = (army.infantry or 0) + add_inf
                army.archers = (army.archers or 0) + add_arc
                army.cavalry = (army.cavalry or 0) + add_cav
                army.spearmen = (army.spearmen or 0) + add_sp
                logger.info(f"🛡️ House Blackfyre o'yinchisi #{u.id} armiyasiga {needed:,} ta yo'qolgan askar tiklab berildi (Jami: 200,000).")

        # Ajdarlar quvvatini to'g'irlash: Darajasini pasaytirmagan holda har bir ajdarning
        # quvvatini o'z darajasidagi ruxsat etilgan maksimal me'yorga keltirish (normalizatsiya)
        from database import crud
        dragons_res = await session.execute(select(models.Dragon))
        for drg in dragons_res.scalars().all():
            max_p = crud.get_max_dragon_power(drg.level, drg.stage, drg.artifact_code)
            if (drg.power or 0) > max_p:
                logger.info(f"🐉 Ajdar #{drg.id} ({drg.name}, Daraja {drg.level}) quvvati normallashtirildi: {drg.power:,} -> {max_p:,}")
                drg.power = max_p

        await session.commit()
        logger.info("✅ 50 ta Xonadon va Westeros hududlari bazaga kiritildi.")

