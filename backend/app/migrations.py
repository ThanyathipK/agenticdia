"""Alembic migration runner for AgenticDIA.

Replaces the previous ad-hoc startup migrations (routes/migrations.py) with
proper versioned Alembic migrations. Migrations are stored in
backend/alembic/versions/ and tracked in the alembic_version table.

The Alembic env.py module handles the async engine connection lifecycle,
so this module simply delegates to Alembic's command API.
"""
import asyncio
import logging
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import UserModel

logger = logging.getLogger("app.migrations")

# Path to the alembic.ini file relative to this module.
# backend/app/migrations.py -> backend/alembic.ini
BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


async def run_migrations() -> None:
    """Run all pending Alembic migrations.

    Delegates to Alembic's command API. The env.py module reads the
    application's DATABASE_URL from app.config and manages its own async
    engine lifecycle (including ``asyncio.run(run_async_migrations())``).

    ``asyncio.run()`` cannot be called from inside a running event loop, so
    when this startup coroutine is executed on uvicorn's loop we must not
    invoke Alembic directly. Instead the blocking Alembic upgrade is
    offloaded to a worker thread, where a fresh event loop can be created
    safely and the migration connection is fully isolated from the app engine.
    """
    logger.info("Running Alembic migrations...")

    def _upgrade() -> None:
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(cfg, "head")

    await asyncio.to_thread(_upgrade)

    logger.info("Alembic migrations completed successfully.")


async def seed_default_user() -> None:
    """Seed the default system user used by automated agents."""
    logger.info("Running migration step: seed_default_user.")
    try:
        async with AsyncSessionLocal() as session:
            system_user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
            stmt = select(UserModel).where(UserModel.id == system_user_id)
            res = await session.execute(stmt)
            exists = res.scalar_one_or_none()
            if not exists:
                system_user = UserModel(
                    id=system_user_id,
                    email="system@banking.com",
                    full_name="System User",
                    role="Developer"
                )
                session.add(system_user)
                await session.commit()
                logger.info("Seeded default system user successfully.")
            else:
                logger.info("Default system user already exists.")
    except Exception as e:
        logger.critical("CRITICAL: Failed to seed default system user!", exc_info=True)
        raise RuntimeError("Default user seeding failed") from e
