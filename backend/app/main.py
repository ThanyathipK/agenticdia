import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.migrations import run_migrations, seed_default_user
from app.event_manager import verify_single_worker_guarantee as verify_sse_single_worker_guarantee
from app.rate_limit import verify_single_worker_guarantee
from app.routes import chat, projects, requirements, lock, events, documents
from app.llm_client import check_lm_studio_health

# Logger initialization
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the application lifecycle.

    Runs versioned Alembic migrations and seeds the default user on startup,
    replacing the deprecated ``@app.on_event("startup")`` handler. Also performs
    a graceful LM Studio reachability probe (Finding #40): the app still boots
    when the local LLM is offline, but a prominent warning is logged so operators
    and the UI (which surfaces the same signal via ``GET /api/health``) can react.
    """
    logger.info("Application startup: running migrations and seeding data...")

    # Finding #39 hardening — fail loud instead of letting 429 protection
    # silently disappear. Refuses to boot when the in-process limiter is paired
    # with multiple uvicorn workers (each worker would keep its own counter),
    # unless the operator explicitly opts into that weaker posture.
    verify_single_worker_guarantee()

    # SSE event-bus hardening — same single-process contract as the rate limiter.
    # The in-process subscriber queues + replay buffer are process-local; with
    # multiple workers events published on one worker would never reach SSE
    # clients connected to another (missing/duplicate streams). This guard is
    # active even when rate limiting is disabled, so the SSE single-process
    # assumption is never silently violated.
    verify_sse_single_worker_guarantee()

    await run_migrations()
    await seed_default_user()

    # Finding #40 — startup check: probe LM Studio without crashing the app.
    # The health probe never raises; this extra guard is belt-and-braces.
    try:
        llm_health = await check_lm_studio_health()
        if llm_health["online"]:
            logger.info(
                f"LM Studio startup check passed: gateway={settings.LM_STUDIO_URL} "
                f"model={llm_health['loaded_models'] or 'none loaded'} "
                f"({llm_health['latency_ms']} ms)"
            )
        else:
            logger.warning(
                "LM Studio is OFFLINE at startup (%s). The UI will show an 'LM "
                "Studio offline' banner and inference calls will return HTTP 503 "
                "until the local server (localhost:1234) is started and the model "
                "'%s' is loaded.",
                llm_health["error"] or "unreachable",
                llm_health["target_model"],
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("LM Studio startup health check failed unexpectedly: %s", exc)

    yield
    # Any graceful-shutdown / cleanup logic belongs here (after ``yield``).
    logger.info("Application shutdown complete.")


# ==========================================
# OPENAPI / DOCS METADATA
# ==========================================
# Tags group endpoints into logical domains within the auto-generated /docs
# and /openapi.json documentation.
openapi_tags = [
    {
        "name": "System",
        "description": "Liveness, health checks and general chat with the local LLM.",
    },
    {
        "name": "Projects",
        "description": "Project CRUD, requirement-state access, conversations, PRD export and PRD version history.",
    },
    {
        "name": "Requirements & Workflow",
        "description": "Requirement CRUD/locking, the multi-agent processing pipeline, and semantic test endpoints (workflow routing, intent detection, requirement matching).",
    },
    {
        "name": "Locking & Pending Actions",
        "description": "Generic artifact locking, lock-status, and human-in-the-loop pending merge actions.",
    },
    {
        "name": "Events & SSE",
        "description": "Artifact event log queries and the Server-Sent Events (SSE) realtime push stream.",
    },
]

# Instantiate FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Asynchronous FastAPI Core for Banking-grade Local LLM (LM Studio) & "
        "Multi-Agent orchestration.\n\n"
        "This service drives the **agenticdia** product: it orchestrates a "
        "LangGraph multi-agent workflow (Gatherer, Auditor, Architect) that "
        "parses raw banking requirements into structured user stories, runs "
        "Krungsri Nimble compliance audits, generates PRD documents and "
        "architecture diagrams, and enforces artifact-level locking with "
        "human-in-the-loop merge confirmation.\n\n"
        "Interactive API documentation is generated below. The raw OpenAPI "
        "specification is available at `/openapi.json`."
    ),
    version="1.2.0",
    openapi_tags=openapi_tags,
    contact={
        "name": "agenticdia",
        "url": "https://github.com/",
    },
    license_info={
        "name": "Proprietary",  # Adjust to the project's actual license.
    },
    lifespan=lifespan,
)


# Enterprise CORS middleware with explicit allowed origins.
# allow_credentials is intentionally omitted (False) because the frontend
# does not send cookies/auth headers, and "*" + credentials is invalid per spec.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# ROUTER REGISTRATION
# ==========================================
# Each router module handles a distinct domain:
#   - chat:        /api/health, /api/chat
#   - projects:    /api/projects, /api/project/{id}, PRD export & versions
#   - requirements:/api/project/{id}/requirements, /api/process-requirements,
#                  /api/workflow-router, /api/intent-detector, /api/requirement-matcher,
#                  /api/audit/respond, /api/clarification/submit
#   - lock:        /api/project/{id}/artifacts/*/lock|unlock|lock-status,
#                  /api/pending-actions, /api/confirm-action, /api/cancel-action
#   - events:      /api/events, /api/project/{id}/events, /api/project/{id}/sse (SSE push stream)
#   - documents:   /api/project/{id}/documents upload/list/get + DRAFT-only process endpoint
app.include_router(chat.router, tags=["System"])
app.include_router(projects.router, tags=["Projects"])
app.include_router(requirements.router, tags=["Requirements & Workflow"])
app.include_router(lock.router, tags=["Locking & Pending Actions"])
app.include_router(events.router, tags=["Events & SSE"])
app.include_router(documents.router, tags=["Documents"])


# ==========================================
# CENTRALIZED ERROR HANDLERS
# ==========================================
# Standardize how client errors (405 Method Not Allowed, 415 Unsupported Media Type,
# 429 Too Many Requests, 404, etc.) and body-validation failures are surfaced. Every
# handler returns a consistent JSON ``{"detail": ...}`` body and, critically, logs the
# failure loudly instead of swallowing it — so transient/outage errors remain visible
# to operators via the application logs rather than being silently masked.
# (Review finding: "silent error swallowing".)

@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Log server errors loudly, then return a structured JSON error body.

    All ``HTTPException``-derived errors (including 404, 405, 415 and the 429 raised
    by the rate limiter) flow through here. ``status_code``/``detail``/``headers`` are
    preserved so, for example, the rate limiter's ``Retry-After`` header and message
    are not lost.
    """
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error(
            "Unhandled HTTP error on %s %s (status=%s)",
            request.method,
            request.url.path,
            exc.status_code,
            exc_info=True,
        )
    elif exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        logger.warning("Rate limited on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a structured 422 for malformed bodies / unsupported content types."""
    logger.warning(
        "Request validation failed on %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on http://0.0.0.0:8000")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)