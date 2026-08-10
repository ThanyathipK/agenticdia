"""End-to-end functional test for the new SSE stream endpoint.

Runs against the actual StreamingResponse generator (the same `body_iterator`
the ASGI server would stream to a browser over `text/event-stream`).
"""
import asyncio
import json

from app.routes.events import stream_project_events
from app.event_manager import event_manager

PROJECT_ID = "11111111-1111-1111-1111-111111111111"


async def main():
    print("=== Test 1: invalid project_id → HTTP 400 ===")
    try:
        await stream_project_events("not-a-uuid")
        raise AssertionError("expected HTTPException 400")
    except Exception as e:
        assert e.status_code == 400, e
        print("OK →", e.detail)

    print("\n=== Test 2: handshake + event frames via the real generator ===")
    response = await stream_project_events(PROJECT_ID)
    it = response.body_iterator.__aiter__()

    # Read the initial `connected` handshake frame.
    first = await asyncio.wait_for(it.__anext__(), timeout=5)
    assert first.strip().startswith("data:"), first
    handshake = json.loads(first.split("data: ", 1)[1])
    assert handshake["event"] == "connected", handshake
    assert handshake["data"]["project_id"] == PROJECT_ID
    print("handshake OK →", first.strip())

    # Publish the exact event types the route handlers now emit.
    for i, evt in enumerate(["workflow_update", "requirement_locked", "merge_confirmed"]):
        await event_manager.publish(PROJECT_ID, evt, {"project_id": PROJECT_ID, "index": i})

    received = {}
    for _ in range(3):
        frame = await asyncio.wait_for(it.__anext__(), timeout=5)
        if not frame.strip() or frame.strip() == ": ping":
            continue
        msg = json.loads(frame.split("data: ", 1)[1])
        received[msg["event"]] = msg["data"]

    expected = {
        "workflow_update": 0,
        "requirement_locked": 1,
        "merge_confirmed": 2,
    }
    assert set(received) == set(expected), received
    for evt, idx in expected.items():
        assert received[evt]["index"] == idx, received
        assert received[evt]["project_id"] == PROJECT_ID
    print("streamed events OK →", {k: v["index"] for k, v in received.items()})

    # Close only this stream; a fresh pair is opened for Test 3.
    await it.aclose()
    assert PROJECT_ID not in event_manager._subscribers, f"subscriber leak: {event_manager._subscribers}"
    print("cleanup OK → no subscriber leak")

    print("\n=== Test 3: multiple subscribers + event ordering ===")
    r1 = await stream_project_events(PROJECT_ID)
    r2 = await stream_project_events(PROJECT_ID)
    it1 = r1.body_iterator.__aiter__()
    it2 = r2.body_iterator.__aiter__()
    await asyncio.wait_for(it1.__anext__(), timeout=5)  # skip handshakes
    await asyncio.wait_for(it2.__anext__(), timeout=5)

    # Two subscribers listening; publish once → both must receive the event.
    await event_manager.publish(PROJECT_ID, "state_updated", {"seq": "A"})
    f1 = await asyncio.wait_for(it1.__anext__(), timeout=5)
    f2 = await asyncio.wait_for(it2.__anext__(), timeout=5)
    assert json.loads(f1.split("data: ", 1)[1])["data"]["seq"] == "A"
    assert json.loads(f2.split("data: ", 1)[1])["data"]["seq"] == "A"
    print("multi-subscriber delivery OK")
    await it1.aclose()
    await it2.aclose()
    assert PROJECT_ID not in event_manager._subscribers

    print("\nALL SSE TESTS PASSED ✅")


asyncio.run(main())