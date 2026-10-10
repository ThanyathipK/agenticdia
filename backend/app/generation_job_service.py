"""Persistent, cancellable background execution for long-running AI work."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import AuthenticatedUser
from app.database import AsyncSessionLocal
from app.models import GenerationJobModel, UserModel
from app.schemas import ProcessRequirementsRequest

logger = logging.getLogger("app.generation_jobs")

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
ACTIVE_STATUSES = {"queued", "running", "cancelling"}
_tasks: dict[str, asyncio.Task] = {}


def serialize_job(job: GenerationJobModel) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "project_id": str(job.project_id),
        "job_type": job.job_type,
        "status": job.status,
        "progress_stage": job.progress_stage,
        "result": job.result_payload,
        "error_message": job.error_message,
        "cancel_requested": bool(job.cancel_requested),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


async def create_job(project_id: str, user_id: str, job_type: str, payload: dict[str, Any], session) -> dict[str, Any]:
    existing = await session.scalar(
        select(GenerationJobModel).where(
            GenerationJobModel.project_id == uuid.UUID(str(project_id)),
            GenerationJobModel.status.in_(ACTIVE_STATUSES),
        ).limit(1)
    )
    if existing is not None:
        raise ValueError(f"Project already has an active {existing.job_type} job ({existing.id}).")
    job = GenerationJobModel(
        project_id=uuid.UUID(str(project_id)),
        requested_by_user_id=uuid.UUID(str(user_id)),
        job_type=job_type,
        request_payload=jsonable_encoder(payload),
    )
    session.add(job)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise ValueError("Project already has an active generation job.") from None
    await session.refresh(job)
    return serialize_job(job)


async def get_job(job_id: str, project_id: str, session) -> GenerationJobModel | None:
    try:
        jid = uuid.UUID(str(job_id))
        pid = uuid.UUID(str(project_id))
    except ValueError:
        return None
    return await session.scalar(select(GenerationJobModel).where(
        GenerationJobModel.id == jid,
        GenerationJobModel.project_id == pid,
    ))


async def _execute(job: GenerationJobModel, session) -> dict[str, Any]:
    user = await session.get(UserModel, job.requested_by_user_id)
    if user is None:
        raise RuntimeError("The user who requested this job no longer exists.")
    if job.job_type in {"architect", "auditor"}:
        from app.routes.requirements import _process_requirements_pipeline

        request = ProcessRequirementsRequest.model_validate(job.request_payload)
        request.target_agent = job.job_type
        current_user = AuthenticatedUser(
            id=str(user.id), email=user.email, full_name=user.full_name, role=user.role,
        )
        return jsonable_encoder(await _process_requirements_pipeline(request, session, current_user))
    if job.job_type == "regeneration":
        from app.dependency_graph_service import execute_regeneration
        from app.lock_service import LockService

        lock_info = await LockService.get_lock_status(
            "project", str(job.project_id), session, project_id=str(job.project_id),
        )
        LockService.raise_if_locked("project", str(job.project_id), lock_info)

        result = await execute_regeneration(
            str(job.project_id),
            list(job.request_payload.get("changed_artifacts") or []),
            user.full_name,
            session,
        )
        if result.get("status") == "failed":
            raise RuntimeError(result.get("error_message") or "Partial regeneration failed.")
        return jsonable_encoder(result)
    raise RuntimeError(f"Unsupported generation job type: {job.job_type}")


async def _run_job(job_id: str) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(GenerationJobModel, uuid.UUID(job_id))
        if job is None or job.status in TERMINAL_STATUSES:
            return
        if job.cancel_requested:
            job.status = "cancelled"
            job.progress_stage = "cancelled"
            job.completed_at = datetime.now(timezone.utc)
            await session.commit()
            return
        job.status = "running"
        job.progress_stage = "model_processing"
        job.started_at = job.started_at or datetime.now(timezone.utc)
        await session.commit()
        try:
            result = await _execute(job, session)
            job.status = "completed"
            job.progress_stage = "completed"
            job.result_payload = result
            job.completed_at = datetime.now(timezone.utc)
            await session.commit()
        except asyncio.CancelledError:
            await session.rollback()
            job = await session.get(GenerationJobModel, uuid.UUID(job_id))
            if job is not None:
                # The cancellation request is committed by a different API
                # session. Refresh the identity-map object before deciding
                # whether this was a user stop or process shutdown.
                await session.refresh(job)
                # Explicit API cancellation sets cancel_requested before it
                # cancels the task. A process shutdown does not: leave that
                # work queued so startup recovery can safely resume it.
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.progress_stage = "cancelled"
                    job.completed_at = datetime.now(timezone.utc)
                else:
                    job.status = "queued"
                    job.progress_stage = "interrupted_by_shutdown"
                    job.completed_at = None
                await session.commit()
            logger.info("Generation job %s interrupted (user_cancelled=%s)", job_id, bool(job and job.cancel_requested))
        except Exception as exc:
            await session.rollback()
            job = await session.get(GenerationJobModel, uuid.UUID(job_id))
            if job is not None:
                job.status = "failed"
                job.progress_stage = "failed"
                job.error_message = str(exc)[:4000]
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()
            logger.exception("Generation job %s failed", job_id)


def launch_job(job_id: str) -> None:
    current = _tasks.get(job_id)
    if current is not None and not current.done():
        return
    task = asyncio.create_task(_run_job(job_id), name=f"generation-job-{job_id}")
    _tasks[job_id] = task
    task.add_done_callback(lambda finished: _tasks.pop(job_id, None) if _tasks.get(job_id) is finished else None)


async def cancel_job(job: GenerationJobModel, session) -> bool:
    if job.status in TERMINAL_STATUSES:
        return False
    job.cancel_requested = True
    job.status = "cancelling"
    job.progress_stage = "cancelling"
    await session.commit()
    task = _tasks.get(str(job.id))
    if task is not None and not task.done():
        task.cancel()
        return True
    # A queued job not yet attached to this process can be cancelled directly.
    job.status = "cancelled"
    job.progress_stage = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    await session.commit()
    return True


async def recover_generation_jobs() -> int:
    """Requeue work interrupted by a restart, then launch every queued job."""
    async with AsyncSessionLocal() as session:
        jobs = list((await session.scalars(select(GenerationJobModel).where(
            GenerationJobModel.status.in_(ACTIVE_STATUSES)
        ))).all())
        for job in jobs:
            if job.cancel_requested:
                job.status = "cancelled"
                job.progress_stage = "cancelled"
                job.completed_at = datetime.now(timezone.utc)
            else:
                job.status = "queued"
                job.progress_stage = "recovered_after_restart"
        await session.commit()
        queued = [str(job.id) for job in jobs if job.status == "queued"]
    for job_id in queued:
        launch_job(job_id)
    return len(queued)


async def shutdown_generation_jobs() -> None:
    tasks = [task for task in _tasks.values() if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
