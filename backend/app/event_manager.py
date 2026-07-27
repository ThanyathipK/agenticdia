"""
In-memory event manager for Server-Sent Events (SSE) notifications.
Provides a simple pub/sub mechanism where state changes trigger events
to connected SSE clients.
"""
import asyncio
import json
import logging
from typing import Dict, Set, Any

logger = logging.getLogger("app.event_manager")


class EventManager:
    """
    Manages SSE subscriptions per project_id.
    Each project has a set of asyncio.Queue instances (one per connected client).
    """

    def __init__(self):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}

    def subscribe(self, project_id: str) -> asyncio.Queue:
        """Create a new subscription queue for a project."""
        if project_id not in self._subscribers:
            self._subscribers[project_id] = set()
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[project_id].add(queue)
        logger.debug(f"SSE client subscribed to project {project_id}. Total subscribers: {len(self._subscribers[project_id])}")
        return queue

    def unsubscribe(self, project_id: str, queue: asyncio.Queue) -> None:
        """Remove a subscription queue."""
        if project_id in self._subscribers:
            self._subscribers[project_id].discard(queue)
            if not self._subscribers[project_id]:
                del self._subscribers[project_id]
            logger.debug(f"SSE client unsubscribed from project {project_id}.")

    async def publish(self, project_id: str, event_type: str, data: Any) -> None:
        """Publish an event to all subscribers of a project."""
        if project_id not in self._subscribers:
            return
        message = {
            "event": event_type,
            "data": data
        }
        payload = json.dumps(message)
        dead_queues = set()
        for queue in self._subscribers[project_id]:
            try:
                await queue.put(payload)
            except Exception:
                dead_queues.add(queue)
        # Clean up dead queues
        for q in dead_queues:
            self._subscribers[project_id].discard(q)
        if dead_queues:
            logger.debug(f"Removed {len(dead_queues)} dead SSE subscriber(s) for project {project_id}.")


# Singleton instance
event_manager = EventManager()