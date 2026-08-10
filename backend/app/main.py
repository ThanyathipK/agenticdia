import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.migrations import run_migrations, seed_default_user
from app.routes import chat, projects, requirements, lock, events

# Logger initialization
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the application lifecycle.

    Runs versioned Alembic migrations and seeds the default user on startup,
    replacing the deprecated ``@app.on_event("startup")`` handler.
    """
    logger.info("Application startup: running migrations and seeding data...")
    await run_migrations()
    await seed_default_user()
    yield
    # Any graceful-shutdown / cleanup logic belongs here (after ``yield``).
    logger.info("Application shutdown complete.")


# Instantiate FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Asynchronous FastAPI Core for Banking-grade Local LLM (LM Studio) & Multi-Agent orchestration.",
    version="1.2.0",
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
app.include_router(chat.router)
app.include_router(projects.router)
app.include_router(requirements.router)
app.include_router(lock.router)
app.include_router(events.router)


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on http://0.0.0.0:8000")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)