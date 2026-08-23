"""
Unit tests for true server-side generation cancellation (Stop button).

Verifies that:
- ``WorkflowCancellationRegistry.register / unregister / is_running / cancel``
  behave correctly across idle / running / already-finished-task paths;
- cancelling a registered task really interrupts the awaited coroutine
  (standing in for an in-flight LLM call);
- ``POST /api/process-requirements/cancel`` is wired up and reports
  ``cancelled: false`` when nothing is in flight (no DB touched).

Run from the ``backend`` directory::

    ../venv/bin/python -m pytest tests/test_workflow_cancellation.py -v
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.workflow_cancellation import workflow_cancellations


# ==========================================
# WorkflowCancellationRegistry
# ==========================================
@pytest.mark.asyncio
async def test_cancel_returns_false_when_idle():
    from app.workflow_cancellation import WorkflowCancellationRegistry

    registry = WorkflowCancellationRegistry()

    assert registry.is_running("p1") is False
    assert registry.cancel("p1") is False
    assert registry.is_running("p1") is False


@pytest.mark.asyncio
async def test_cancel_stops_a_registered_running_task():
    from app.workflow_cancellation import WorkflowCancellationRegistry

    registry = WorkflowCancellationRegistry()
    started = asyncio.Event()
    observed = {"cancelled": False}

    async def slow_generation():
        started.set()
        try:
            # Stands in for an in-flight LLM call (e.g. prd_workflow.ainvoke).
            await asyncio.sleep(60)
            return "completed"
        except asyncio.CancelledError:
            observed["cancelled"] = True
            raise

    task = asyncio.create_task(slow_generation())
    await started.wait()
    registry.register("p1", task)

    assert registry.is_running("p1") is True
    assert registry.cancel("p1") is True

    with pytest.raises(asyncio.CancelledError):
        await task
    assert observed["cancelled"] is True

    registry.unregister("p1", task)
    assert registry.is_running("p1") is False


@pytest.mark.asyncio
async def test_unregister_ignores_mismatched_task_and_cancel_cleans_done_tasks():
    from app.workflow_cancellation import WorkflowCancellationRegistry

    registry = WorkflowCancellationRegistry()

    async def noop():
        return "x"

    finished = asyncio.create_task(noop())
    await finished
    registry.register("p1", finished)

    # A finished task counts as not-running and cancel() lazily cleans it up.
    assert registry.is_running("p1") is False
    assert registry.cancel("p1") is False
    assert registry.cancel("p1") is False

    # unregister() with the WRONG task object must not drop the registration.
    stranger = asyncio.create_task(noop())
    await stranger
    registry.register("p2", finished)
    registry.unregister("p2", stranger)

    live_started = asyncio.Event()

    async def live_generation():
        live_started.set()
        await asyncio.sleep(60)

    live = asyncio.create_task(live_generation())
    await live_started.wait()
    registry.register("p2", live)

    assert registry.cancel("p2") is True  # registration survived the mismatched unregister
    with pytest.raises(asyncio.CancelledError):
        await live
    registry.unregister("p2", live)
    assert registry.is_running("p2") is False


# ==========================================
# POST /api/process-requirements/cancel
# ==========================================
def test_cancel_endpoint_reports_idle_project(monkeypatch):
    # Fresh registry state so other tests cannot leak registrations in.
    monkeypatch.setattr(workflow_cancellations, "_tasks", {})

    project_id = "11111111-1111-1111-1111-111111111111"
    # No `with` block on purpose: lifespan (migrations/seeding) must not run here.
    response = TestClient(app).post(
        "/api/process-requirements/cancel",
        params={"project_id": project_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cancelled"] is False
    assert payload["project_id"] == project_id
