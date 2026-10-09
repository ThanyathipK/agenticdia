"""Persistent background-job completion and cancellation semantics."""
import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import GenerationJobModel, ProjectModel, UserModel
import app.generation_job_service as jobs


@pytest_asyncio.fixture
async def job_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/jobs.db")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(jobs, "AsyncSessionLocal", factory)
    async with factory() as session:
        user = UserModel(email="jobs@example.com", full_name="Job Owner", role="product_owner")
        session.add(user)
        await session.flush()
        project = ProjectModel(user_id=user.id, name="Background Work", industry_standard="Banking")
        session.add(project)
        await session.commit()
        yield factory, str(user.id), str(project.id)
    await jobs.shutdown_generation_jobs()
    await engine.dispose()


async def _new_job(factory, user_id, project_id):
    async with factory() as session:
        payload = await jobs.create_job(project_id, user_id, "architect", {"project_id": project_id}, session)
        await session.commit()
        return payload["id"]


@pytest.mark.asyncio
async def test_background_job_persists_completed_result(job_db, monkeypatch):
    factory, user_id, project_id = job_db
    job_id = await _new_job(factory, user_id, project_id)

    async def execute(_job, _session):
        return {"prd_markdown": "# Complete"}

    monkeypatch.setattr(jobs, "_execute", execute)
    jobs.launch_job(job_id)
    await asyncio.wait_for(jobs._tasks[job_id], timeout=1)

    async with factory() as session:
        job = await session.get(GenerationJobModel, job_id)
        assert job.status == "completed"
        assert job.result_payload == {"prd_markdown": "# Complete"}


@pytest.mark.asyncio
async def test_user_cancel_is_terminal_but_shutdown_is_recoverable(job_db, monkeypatch):
    factory, user_id, project_id = job_db
    started = asyncio.Event()

    async def execute(_job, _session):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(jobs, "_execute", execute)
    cancelled_id = await _new_job(factory, user_id, project_id)
    jobs.launch_job(cancelled_id)
    await asyncio.wait_for(started.wait(), timeout=1)
    task = jobs._tasks[cancelled_id]
    async with factory() as session:
        job = await session.get(GenerationJobModel, cancelled_id)
        assert await jobs.cancel_job(job, session)
    await asyncio.gather(task, return_exceptions=True)
    async with factory() as session:
        cancelled = await session.get(GenerationJobModel, cancelled_id)
        assert cancelled.status == "cancelled"
        assert cancelled.cancel_requested is True

        # A terminal job no longer blocks a new project job.
        second = await jobs.create_job(project_id, user_id, "architect", {"project_id": project_id}, session)
        await session.commit()
    started.clear()
    jobs.launch_job(second["id"])
    await asyncio.wait_for(started.wait(), timeout=1)
    await jobs.shutdown_generation_jobs()
    async with factory() as session:
        interrupted = await session.get(GenerationJobModel, second["id"])
        assert interrupted.status == "queued"
        assert interrupted.progress_stage == "interrupted_by_shutdown"
        assert interrupted.cancel_requested is False
