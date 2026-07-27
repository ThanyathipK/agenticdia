import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from app.config import settings

logger = logging.getLogger("app.database")

# Declarative base class for SQLAlchemy database models
Base = declarative_base()

# Async connection engine optimized for Supabase Cloud postgres connectivity
# Transaction pooler (port 6543) handles connection pooling at infrastructure level
# so we use minimal SQLAlchemy pooling to avoid double-pooling conflicts
try:
    db_url = settings.async_database_url
    is_sqlite = db_url.startswith("sqlite")
    
    if is_sqlite:
        engine_kwargs = {
            "echo": settings.DEBUG
        }
    else:
        # For transaction pooler (Supabase pooler on port 6543), use NullPool or minimal pool
        # The pooler itself manages connections, so SQLAlchemy should not maintain a large pool
        engine_kwargs = {
            "pool_size": 5,  # Reduced for transaction pooler
            "max_overflow": 5,  # Reduced for transaction pooler
            "pool_timeout": 10,  # Faster timeout for pooler connections
            "pool_recycle": 300,  # 5 minutes - shorter recycle for pooler
            "pool_pre_ping": True,  # Verify connections before use
            "echo": settings.DEBUG,
            "connect_args": {
                "server_settings": {
                    "application_name": "agenticdia-backend"
                },
                "statement_cache_size": 0  # Required for PgBouncer compatibility
            }
        }
        
    engine = create_async_engine(
        db_url,
        **engine_kwargs
    )
    logger.info(f"Async SQLAlchemy Database Engine initialized successfully (SQLite={is_sqlite}, Pooler mode).")
except Exception as e:
    logger.error(f"Critical error initializing Database Engine: {str(e)}")
    raise e

# Session maker wrapping the async connection engine
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency yield mechanism.
    Provides isolated asynchronous transaction sessions for single requests or multi-agent transactions.
    Gracefully disposes and commits/rolls back connection states.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database transaction error encountered. Session rolled back: {str(e)}")
            raise e
        finally:
            await session.close()
