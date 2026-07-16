import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from app.config import settings

logger = logging.getLogger("app.database")

# Declarative base class for SQLAlchemy database models
Base = declarative_base()

# Async connection engine optimized for Supabase Cloud postgres connectivity
# Includes connection pooling parameters to handle concurrent multi-agent transactions if postgres is used
try:
    db_url = settings.async_database_url
    is_sqlite = db_url.startswith("sqlite")
    
    if is_sqlite:
        engine_kwargs = {
            "echo": settings.DEBUG
        }
    else:
        engine_kwargs = {
            "pool_size": 20,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_recycle": 1800,
            "echo": settings.DEBUG
        }
        
    engine = create_async_engine(
        db_url,
        **engine_kwargs
    )
    logger.info(f"Async SQLAlchemy Database Engine initialized successfully (SQLite={is_sqlite}).")
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
