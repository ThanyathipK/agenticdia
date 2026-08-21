"""Unit tests for the in-memory SSE event bus (app/event_manager.py).

Covers the two properties the event stream now guarantees:

* **Bounded replay** — every published event is buffered per project with a
  monotonic id, and a reconnecting client (``subscribe(..., last_event_id=...)``)
  is seeded with every buffered event written while it was away.
* **Single-worker guard** — the bus is process-local, so it must refuse to boot
  (or, with an explicit opt-in, warn loudly) when multiple uvicorn workers are
  detected, mirroring the rate limiter's ``verify_single_worker_guarantee``.

Run from the ``backend`` directory::

    python3 -m pytest tests/test_event_manager.py -v
"""
import asyncio
import json

import pytest

from app import event_manager as em
from app import rate_limit

P1 = "11111111-1111-1111-1111-111111111111"
P2 = "22222222-2222-2222-2222-222222222222"


# ======================================================================
# Publish ordering + buffering
# ======================================================================
def test_publish_assigns_monotonic_seq_per_project():
    mgr = em.EventManager(history_size=100)
    assert mgr.publish is not None
    # seq must be replicated per project, not global.
    ev = asyncio.run(_publish_two_projects(mgr))
    assert ev == {P1: [1, 2], P2: [1]}


async def _publish_two_projects(mgr):
    await mgr.publish(P1, "a", {"i": 1})
    await mgr.publish(P2, "b", {"i": 2})
    await mgr.publish(P1, "c", {"i": 3})
    return {p: [s for s, _ in mgr._history[p]] for p in (P1, P2)}


@pytest.mark.asyncio
async def test_subscriber_receives_seq_and_payload():
    mgr = em.EventManager(history_size=100)
    queue = mgr.subscribe(P1)
    await mgr.publish(P1, "state_updated", {"seq": "A"})

    seq, payload = await asyncio.wait_for(queue.get(), timeout=1)
    assert seq == 1
    parsed = json.loads(payload)
    assert parsed["event"] == "state_updated"
    assert parsed["data"]["seq"] == "A"


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_still_buffers():
    mgr = em.EventManager(history_size=100)
    await mgr.publish(P1, "workflow_update", {"step": 1})
    assert list(mgr._history[P1])[0][0] == 1


# ======================================================================
# Replay on reconnect
# ======================================================================
@pytest.mark.asyncio
async def test_reconnect_replays_missed_events_after_last_event_id():
    mgr = em.EventManager(history_size=100)

    q1 = mgr.subscribe(P1)
    await mgr.publish(P1, "a", {"i": 1})  # seq 1 — delivered & seen
    await asyncio.wait_for(q1.get(), timeout=1)

    # Client disconnects; two more events land while it is away.
    await mgr.publish(P1, "b", {"i": 2})  # seq 2 — missed
    await mgr.publish(P1, "c", {"i": 3})  # seq 3 — missed
    mgr.unsubscribe(P1, q1)

    # Reconnect with the last id the client actually received.
    q2 = mgr.subscribe(P1, last_event_id=1)
    replayed = []
    while not q2.empty():
        seq, payload = q2.get_nowait()
        replayed.append((seq, json.loads(payload)["data"]["i"]))
    assert replayed == [(2, 2), (3, 3)]


@pytest.mark.asyncio
async def test_reconnect_without_last_event_id_starts_fresh():
    mgr = em.EventManager(history_size=100)
    await mgr.publish(P1, "x", {})
    queue = mgr.subscribe(P1)  # no last_event_id → no replay
    assert queue.empty()


@pytest.mark.asyncio
async def test_replay_buffer_is_bounded_to_history_size():
    mgr = em.EventManager(history_size=2)
    for i in range(5):
        await mgr.publish(P1, "e", {"i": i})
    buffered = [s for s, _ in mgr._history[P1]]
    assert buffered == [4, 5]  # only the most recent `history_size` are kept

    # Replaying after the oldest evicted id yields only what is still buffered.
    q = mgr.subscribe(P1, last_event_id=1)
    seqs = []
    while not q.empty():
        seq, _ = q.get_nowait()
        seqs.append(seq)
    assert seqs == [4, 5]


# ======================================================================
# Single-worker deployment guard (mirrors the rate limiter)
# ======================================================================
def test_sse_guard_accepts_single_worker(monkeypatch):
    monkeypatch.setattr(rate_limit.sys, "argv", ["uvicorn", "app.main:app"])
    em.verify_single_worker_guarantee()  # must not raise


def test_sse_guard_refuses_multiple_workers(monkeypatch):
    monkeypatch.setattr(em.settings, "SSE_ALLOW_MULTI_PROCESS_IN_PROCESS", False)
    # cover both argv spellings uvicorn accepts
    for argv in (
        ["uvicorn", "app.main:app", "--workers", "2"],
        ["uvicorn", "app.main:app", "--workers=3"],
        ["uvicorn", "app.main:app", "-w", "4"],
    ):
        monkeypatch.setattr(rate_limit.sys, "argv", argv)
        with pytest.raises(RuntimeError, match="SSE"):
            em.verify_single_worker_guarantee()


def test_sse_guard_opt_in_warns_but_boots(monkeypatch, caplog):
    monkeypatch.setattr(em.settings, "SSE_ALLOW_MULTI_PROCESS_IN_PROCESS", True)
    monkeypatch.setattr(rate_limit.sys, "argv", ["uvicorn", "app.main:app", "-w", "2"])
    em.verify_single_worker_guarantee()  # must NOT raise
    assert any("multi" in r.message or "worker" in r.message.lower() for r in caplog.records)