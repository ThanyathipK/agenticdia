"""
Integration tests for :meth:`app.repositories.project.ProjectRepository.toggle_flagged`.

Flagging (the dashboard ★ star marker) must be fully independent from pinning
(the sidebar's pinned-first ordering): toggling one never affects the other,
and a flagged project never floats to the top of the sidebar.

Uses an in-memory SQLite database (aiosqlite) so the writes are exercised
against a real engine rather than a fake session.

Run from the ``backend`` directory::

    ../venv/bin/python -m pytest tests/test_project_flag.py -v
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.repositories.project import ProjectRepository


@pytest_asyncio.fixture()
async def db_session():
    """Fresh in-memory SQLite schema per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _create_project(session: AsyncSession, name: str) -> str:
    created = await ProjectRepository.create_project({"id": str(uuid.uuid4()), "name": name}, session)
    return created["id"]


@pytest.mark.asyncio
async def test_flag_defaults_to_false(db_session):
    pid = await _create_project(db_session, "Flag Default")

    project = await ProjectRepository.get_by_id(pid, db_session)

    assert project["is_flagged"] is False
    assert project["is_pinned"] is False


@pytest.mark.asyncio
async def test_toggle_flagged_updates_only_the_flag(db_session):
    pid = await _create_project(db_session, "Pin Untouched")
    await ProjectRepository.toggle_pinned(pid, True, db_session)

    updated = await ProjectRepository.toggle_flagged(pid, True, db_session)

    # Flagging must not touch the sidebar pin (and vice versa).
    assert updated["is_flagged"] is True
    assert updated["is_pinned"] is True
    fetched = await ProjectRepository.get_by_id(pid, db_session)
    assert fetched["is_flagged"] is True
    assert fetched["is_pinned"] is True


@pytest.mark.asyncio
async def test_toggle_flagged_can_unflag(db_session):
    pid = await _create_project(db_session, "Unflag")
    await ProjectRepository.toggle_flagged(pid, True, db_session)

    updated = await ProjectRepository.toggle_flagged(pid, False, db_session)

    assert updated["is_flagged"] is False
    # Unflagging must not accidentally pin either.
    assert updated["is_pinned"] is False


@pytest.mark.asyncio
async def test_toggle_flagged_missing_project_returns_none(db_session):
    missing = await ProjectRepository.toggle_flagged(str(uuid.uuid4()), True, db_session)

    assert missing is None


@pytest.mark.asyncio
async def test_flag_does_not_float_to_sidebar_top(db_session):
    pinned = await _create_project(db_session, "Pinned Project")
    flagged = await _create_project(db_session, "Flagged Only")
    await ProjectRepository.toggle_pinned(pinned, True, db_session)
    await ProjectRepository.toggle_flagged(flagged, True, db_session)

    results = await ProjectRepository.list_all(db_session)
    order = [p["id"] for p in results]

    # The pinned project still comes first even though the flagged project was
    # created later: flagging NEVER affects the sidebar ordering.
    assert order == [pinned, flagged]
    assert results[0]["is_pinned"] is True
    assert results[0]["is_flagged"] is False
    assert results[1]["is_pinned"] is False
    assert results[1]["is_flagged"] is True