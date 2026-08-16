import asyncio
import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.event_manager import event_manager
from app.repositories import ArtifactEventLogRepository
from app.schemas import (
    EventListResponse,
    ArtifactEventListResponse,
    ActionEventListResponse,
    ProjectEventListResponse,
)

logger = logging.getLogger("app.routes.events")

router = APIRouter()


@router.get("/api/project/{project_id}/sse", status_code=status.HTTP_200_OK)
async def stream_project_events(project_id: str):
    """
    Server-Sent Events (SSE) stream for a project.

    Subscribes to the in-memory EventManager pub/sub bus and pushes any state
    change event published for this project to connected clients as a
    `text/event-stream`. This replaces the frontend's 3s polling of
    `/api/project/{id}`: clients now refresh only when a change actually occurs.

    Each frame is an unnamed `data:` event carrying JSON of the form:
        {"event": "<event_type>", "data": {...}}
    Heartbeat comments (`: ping`) keep the connection alive through proxies.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    async def event_generator():
        queue = event_manager.subscribe(project_id)
        try:
            # Initial handshake so the client knows the stream is open.
            yield f"data: {json.dumps({'event': 'connected', 'data': {'project_id': project_id}})}\n\n"

            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    message = json.loads(payload)
                    event_type = message.get("event", "message")
                    event_data = message.get("data", {})
                    framed = json.dumps({"event": event_type, "data": event_data})
                    yield f"data: {framed}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat comment keeps the connection alive through proxies/load balancers.
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            # Client disconnected; stop the generator.
            logger.debug(f"SSE stream closed for project {project_id}.")
        except Exception as e:
            logger.error(f"SSE stream error for project {project_id}: {str(e)}")
        finally:
            event_manager.unsubscribe(project_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/events", response_model=EventListResponse, status_code=status.HTTP_200_OK)
async def get_recent_events(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db)
) -> EventListResponse:
    """
    Retrieve the most recent artifact event log entries across all projects.

    Args:
        limit: Maximum number of events to return.
        offset: Pagination offset.
        session: Active asynchronous database session.

    Returns:
        EventListResponse: Newest-first events with pagination metadata.
    """
    events = await ArtifactEventLogRepository.get_recent(session, limit=limit, offset=offset)
    return {
        "events": events,
        "total": len(events),
        "limit": limit,
        "offset": offset
    }


@router.get("/api/events/{artifact_type}/{artifact_id}", response_model=ArtifactEventListResponse, status_code=status.HTTP_200_OK)
async def get_artifact_events(
    artifact_type: str,
    artifact_id: str,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_db)
) -> ArtifactEventListResponse:
    """
    Retrieve all events for a specific artifact (e.g. a user story, requirement, epic).

    Args:
        artifact_type: Type of artifact queried.
        artifact_id: UUID string of the artifact.
        limit: Maximum number of events to return.
        offset: Pagination offset.
        session: Active asynchronous database session.

    Returns:
        ArtifactEventListResponse: Newest-first events for the artifact.
    """
    events = await ArtifactEventLogRepository.get_by_artifact(
        artifact_type, artifact_id, session, limit=limit, offset=offset
    )
    return {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "events": events,
        "total": len(events),
        "limit": limit,
        "offset": offset
    }


@router.get("/api/events/action/{action}", response_model=ActionEventListResponse, status_code=status.HTTP_200_OK)
async def get_events_by_action(
    action: str,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_db)
) -> ActionEventListResponse:
    """
    Retrieve all events for a specific action type (CREATE, UPDATE, DELETE, ARCHIVE, LOCK, UNLOCK).

    Args:
        action: The action type to filter by.
        limit: Maximum number of events to return.
        offset: Pagination offset.
        session: Active asynchronous database session.

    Returns:
        ActionEventListResponse: Newest-first events for the action.

    Raises:
        HTTPException: 400 if ``action`` is not a valid event action.
    """
    action_upper = action.upper()
    if action_upper not in ArtifactEventLogRepository.VALID_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action '{action}'. Must be one of: {', '.join(sorted(ArtifactEventLogRepository.VALID_ACTIONS))}"
        )
    events = await ArtifactEventLogRepository.get_by_action(action_upper, session, limit=limit, offset=offset)
    return {
        "action": action_upper,
        "events": events,
        "total": len(events),
        "limit": limit,
        "offset": offset
    }


@router.get("/api/project/{project_id}/events", response_model=ProjectEventListResponse, status_code=status.HTTP_200_OK)
async def get_project_events(
    project_id: str,
    artifact_type: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_db)
) -> ProjectEventListResponse:
    """
    Retrieve events for a project, optionally filtered by artifact_type and/or action.

    Queries events by known artifact IDs for the project.

    Args:
        project_id: Project UUID string.
        artifact_type: Optional artifact-type filter.
        action: Optional action-type filter.
        limit: Maximum number of events to return.
        offset: Pagination offset.
        session: Active asynchronous database session.

    Returns:
        ProjectEventListResponse: Newest-first events for the project.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID or ``action``
            is invalid.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    if action:
        action_upper = action.upper()
        if action_upper not in ArtifactEventLogRepository.VALID_ACTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action '{action}'. Must be one of: {', '.join(sorted(ArtifactEventLogRepository.VALID_ACTIONS))}"
            )
        action = action_upper

    events = await ArtifactEventLogRepository.get_by_project(
        project_id, session, artifact_type=artifact_type, action=action, limit=limit, offset=offset
    )
    return {
        "project_id": project_id,
        "artifact_type": artifact_type,
        "action": action,
        "events": events,
        "total": len(events),
        "limit": limit,
        "offset": offset
    }