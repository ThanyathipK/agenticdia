"""
Integration tests for :meth:`app.repositories.project.ProjectRepository.search`.

The sidebar project search must match not only the project *name* but also the
content of any persisted conversation message belonging to the project, so a
user can find a chat by what was said inside it.

Uses an in-memory SQLite database (aiosqlite) so the ILIKE/outer-join query is
exercised against a real engine rather than a fake session.

Run from the ``backend`` directory::

    ../venv/bin/python -m pytest tests/test_project_repository_search.py -v
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.repositories import ConversationMessageRepository
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


async def _add_message(session: AsyncSession, project_id: str, role: str, message: str) -> None:
    await ConversationMessageRepository.save_message(project_id, role, message, session=session)


@pytest.mark.asyncio
async def test_name_match_returns_project(db_session):
    pid = await _create_project(db_session, "Payment Gateway Redesign")
    await _add_message(db_session, pid, "user", "hello world")

    results = await ProjectRepository.search(db_session, "gateway")

    assert [p["id"] for p in results] == [pid]


@pytest.mark.asyncio
async def test_message_match_returns_project_with_unrelated_name(db_session):
    pid = await _create_project(db_session, "Onboarding Flow")
    await _add_message(db_session, pid, "assistant", "The settlement engine retries failed transfers three times.")

    # The name does NOT contain the term; only a chat message does.
    results = await ProjectRepository.search(db_session, "settlement")

    assert [p["id"] for p in results] == [pid]


@pytest.mark.asyncio
async def test_matching_project_without_messages_is_found(db_session):
    await _create_project(db_session, "Empty Chat Project")

    results = await ProjectRepository.search(db_session, "empty chat")

    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_is_case_insensitive_for_names_and_messages(db_session):
    named = await _create_project(db_session, "Data Warehouse Migration")
    messaged = await _create_project(db_session, "Mobile App")
    await _add_message(db_session, messaged, "user", "We need KAFKA ingestion here")

    by_name = await ProjectRepository.search(db_session, "data warehouse")
    by_message = await ProjectRepository.search(db_session, "kafka")

    assert [p["id"] for p in by_name] == [named]
    assert [p["id"] for p in by_message] == [messaged]


@pytest.mark.asyncio
async def test_no_match_returns_empty_list(db_session):
    await _create_project(db_session, "Alpha")
    await _create_project(db_session, "Beta")

    results = await ProjectRepository.search(db_session, "nonexistent-term")

    assert results == []


@pytest.mark.asyncio
async def test_query_can_match_multiple_projects_via_name_and_message(db_session):
    by_name = await _create_project(db_session, "Auth Service Revamp")
    by_message = await _create_project(db_session, "Billing Portal")
    await _add_message(db_session, by_message, "user", "How should OAuth tokens be refreshed?")

    results = await ProjectRepository.search(db_session, "auth")

    assert sorted(p["id"] for p in results) == sorted([by_name, by_message])


@pytest.mark.asyncio
async def test_results_keep_pinned_first_ordering(db_session):
    unpinned = await _create_project(db_session, "Search Target A")
    pinned = await _create_project(db_session, "Search Target B")
    await ProjectRepository.toggle_pinned(pinned, True, db_session)

    results = await ProjectRepository.search(db_session, "search target")

    assert [p["id"] for p in results] == [pinned, unpinned]
    assert results[0]["is_pinned"] is True


@pytest.mark.asyncio
async def test_message_match_returns_snippet_centered_on_term(db_session):
    # Message match -> the project name has nothing to highlight, so the
    # snippet must surface the exact message excerpt for the UI to highlight.
    pid = await _create_project(db_session, "Onboarding Flow")
    await _add_message(
        db_session, pid, "assistant",
        "The settlement engine retries failed transfers up to three times.",
    )

    results = await ProjectRepository.search(db_session, "retries")

    assert results[0]["id"] == pid
    snippet = results[0].get("match_snippet", "")
    assert "retries" in snippet.lower()


@pytest.mark.asyncio
async def test_name_match_omits_snippet_when_no_messages(db_session):
    # When a project matches purely via its name, there is no message excerpt,
    # so the caller must not receive a match_snippet field at all.
    pid = await _create_project(db_session, "Empty Chat Project")

    results = await ProjectRepository.search(db_session, "empty chat")

    assert results[0]["id"] == pid
    assert ("match_snippet" not in results[0]) or (results[0]["match_snippet"] is None)