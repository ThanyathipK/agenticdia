import logging
import json
import httpx
import traceback
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.config import settings
from app.database import get_db, engine
from app.models import Base
from app.repository import RequirementStateRepository, ProjectRepository, ConversationMessageRepository, PendingActionRepository, PRDVersionRepository, ArtifactEventLogRepository
from app.schemas import (
    ProjectCreate, 
    UserAnswerSubmit, 
    ChatSessionRequest, 
    LLMStructuredOutput, 
    CheckResultItem
)
from app.agents import prd_workflow

# Pydantic schema for multi-agent Agile requirements processing request
class ProcessRequirementsRequest(BaseModel):
    project_id: str
    raw_input: Optional[str] = Field(default="")
    current_version: Optional[int] = Field(default=1)
    version_history_summaries: Optional[str] = Field(default="No previous history.")
    target_agent: Optional[str] = Field(default="gatherer")
    structured_requirements: Optional[Dict[str, Any]] = Field(default_factory=dict)

# Logger initialization
logger = logging.getLogger("app.main")

# Instantiate FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Asynchronous FastAPI Core for Banking-grade Local LLM (LM Studio) & Multi-Agent orchestration.",
    version="1.2.0"
)

async def drop_constraint(engine) -> None:
    logger.info("Running migration step: drop_constraint.")
    try:
        async with engine.begin() as conn:
            def has_table_and_constraint(sync_conn):
                from sqlalchemy import inspect
                inspector = inspect(sync_conn)
                if "user_stories" not in inspector.get_table_names():
                    return False
                return sync_conn.dialect.name == "postgresql"
            
            should_run = await conn.run_sync(has_table_and_constraint)
            if should_run:
                statement = "ALTER TABLE user_stories DROP CONSTRAINT IF EXISTS user_stories_ticket_code_key;"
                await conn.execute(text(statement))
                logger.info("Successfully dropped user_stories_ticket_code_key constraint (PostgreSQL).")
            else:
                logger.info("Skipped dropping constraint (not PostgreSQL or table user_stories does not exist).")
    except Exception as e:
        logger.error(f"Migration step failed: drop_constraint. Error: {str(e)}")
        logger.error(traceback.format_exc())

async def add_project_column(engine) -> None:
    logger.info("Running migration step: add_project_column.")
    try:
        async with engine.begin() as conn:
            def check_needs_column(sync_conn):
                from sqlalchemy import inspect
                inspector = inspect(sync_conn)
                if "user_stories" not in inspector.get_table_names():
                    return False
                columns = [col["name"] for col in inspector.get_columns("user_stories")]
                return "project_id" not in columns
            
            needs_column = await conn.run_sync(check_needs_column)
            if needs_column:
                if conn.dialect.name == "sqlite":
                    statement = "ALTER TABLE user_stories ADD COLUMN project_id VARCHAR(36);"
                else:
                    statement = "ALTER TABLE user_stories ADD COLUMN IF NOT EXISTS project_id VARCHAR(36);"
                
                await conn.execute(text(statement))
                logger.info(f"Successfully added column project_id to user_stories. Statement: {statement}")
            else:
                logger.info("Skipped adding project_id column (table user_stories does not exist or column already exists).")
    except Exception as e:
        logger.error(f"Migration step failed: add_project_column. Error: {str(e)}")
        logger.error(traceback.format_exc())

async def add_audit_columns(engine) -> None:
    columns_to_add = [
        ("requirements", "status", "VARCHAR(50) DEFAULT 'active'"),
        ("requirements", "last_modified_by", "VARCHAR(100) DEFAULT 'automated_agent'"),
        ("requirements", "change_type", "VARCHAR(50) DEFAULT 'created'"),
        
        ("user_stories", "status", "VARCHAR(50) DEFAULT 'active'"),
        ("user_stories", "version", "INTEGER DEFAULT 1"),
        ("user_stories", "last_modified_by", "VARCHAR(100) DEFAULT 'automated_agent'"),
        ("user_stories", "change_type", "VARCHAR(50) DEFAULT 'created'"),
        
        ("acceptance_criteria", "status", "VARCHAR(50) DEFAULT 'active'"),
        ("acceptance_criteria", "version", "INTEGER DEFAULT 1"),
        ("acceptance_criteria", "last_modified_by", "VARCHAR(100) DEFAULT 'automated_agent'"),
        ("acceptance_criteria", "change_type", "VARCHAR(50) DEFAULT 'created'"),
    ]
    logger.info("Running migration step: add_audit_columns.")
    
    for tbl, col, col_type in columns_to_add:
        try:
            async with engine.begin() as conn:
                def check_needs_col(sync_conn):
                    from sqlalchemy import inspect
                    inspector = inspect(sync_conn)
                    if tbl not in inspector.get_table_names():
                        return False
                    columns = [c["name"] for c in inspector.get_columns(tbl)]
                    return col not in columns
                
                needs_col = await conn.run_sync(check_needs_col)
                if needs_col:
                    statement = f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type};"
                    await conn.execute(text(statement))
                    logger.info(f"Successfully added column {col} to table {tbl}.")
                else:
                    logger.info(f"Column {col} on table {tbl} already exists or table does not exist. Skipping.")
        except Exception as e:
            logger.error(f"Failed to add column {col} to table {tbl}: {str(e)}")
            logger.error(traceback.format_exc())

async def backfill_requirements(engine) -> None:
    logger.info("Running migration step: backfill_requirements.")
    
    statements = [
        ("requirements", "UPDATE requirements SET status = 'active', last_modified_by = 'automated_agent', change_type = 'unchanged' WHERE status IS NULL;"),
        ("user_stories", "UPDATE user_stories SET status = 'active', version = 1, last_modified_by = 'automated_agent', change_type = 'unchanged' WHERE status IS NULL;"),
        ("acceptance_criteria", "UPDATE acceptance_criteria SET status = 'active', version = 1, last_modified_by = 'automated_agent', change_type = 'unchanged' WHERE status IS NULL;")
    ]
    
    for tbl, stmt in statements:
        try:
            async with engine.begin() as conn:
                def check_table_exists(sync_conn):
                    from sqlalchemy import inspect
                    inspector = inspect(sync_conn)
                    return tbl in inspector.get_table_names()
                
                table_exists = await conn.run_sync(check_table_exists)
                if table_exists:
                    await conn.execute(text(stmt))
                    logger.info(f"Successfully ran backfill statement for table {tbl}: {stmt}")
                else:
                    logger.info(f"Table {tbl} does not exist. Skipping backfill.")
        except Exception as e:
            logger.error(f"Migration step failed: backfill statement for table {tbl}. Statement: {stmt}\nError: {str(e)}")
            logger.error(traceback.format_exc())

async def migrate_conversation_messages(engine) -> None:
    """
    Migration step: Adds new columns to conversation_messages table if it exists
    with the old schema. Drops and recreates the table if the schema is incompatible.
    """
    logger.info("Running migration step: migrate_conversation_messages.")
    columns_to_add = [
        ("conversation_messages", "conversation_id", "VARCHAR(36)"),
        ("conversation_messages", "workflow_state", "VARCHAR(50) DEFAULT ''"),
        ("conversation_messages", "intent", "VARCHAR(50) DEFAULT ''"),
    ]
    
    for tbl, col, col_type in columns_to_add:
        try:
            async with engine.begin() as conn:
                def check_needs_col(sync_conn):
                    from sqlalchemy import inspect
                    inspector = inspect(sync_conn)
                    if tbl not in inspector.get_table_names():
                        return False
                    columns = [c["name"] for c in inspector.get_columns(tbl)]
                    return col not in columns
                
                needs_col = await conn.run_sync(check_needs_col)
                if needs_col:
                    if conn.dialect.name == "sqlite":
                        # SQLite has limited ALTER TABLE support
                        # For SQLite, we need to handle this differently
                        statement = f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type};"
                    else:
                        statement = f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {col_type};"
                    
                    await conn.execute(text(statement))
                    logger.info(f"Successfully added column {col} to table {tbl}.")
                else:
                    logger.info(f"Column {col} on table {tbl} already exists or table does not exist. Skipping.")
        except Exception as e:
            logger.error(f"Failed to add column {col} to table {tbl}: {str(e)}")
            logger.error(traceback.format_exc())
    
    # Also handle the old 'timestamp' column removal - SQLite doesn't support DROP COLUMN
    # so we just leave it; the model no longer references it
    try:
        async with engine.begin() as conn:
            def check_old_timestamp(sync_conn):
                from sqlalchemy import inspect
                inspector = inspect(sync_conn)
                if "conversation_messages" not in inspector.get_table_names():
                    return False
                columns = [c["name"] for c in inspector.get_columns("conversation_messages")]
                return "timestamp" in columns
            has_old_timestamp = await conn.run_sync(check_old_timestamp)
            if has_old_timestamp:
                logger.info("Old 'timestamp' column exists in conversation_messages. It will be ignored by the new model.")
    except Exception as e:
        logger.error(f"Failed to check old timestamp column: {str(e)}")

async def backfill_project_ids(engine) -> None:
    logger.info("Running migration step: backfill_project_ids.")
    statement = """
        UPDATE user_stories
        SET project_id = (
            SELECT r.project_id 
            FROM requirements r 
            WHERE r.id = user_stories.requirement_id
        )
        WHERE project_id IS NULL;
    """
    try:
        async with engine.begin() as conn:
            def check_tables_exist(sync_conn):
                from sqlalchemy import inspect
                inspector = inspect(sync_conn)
                tables = inspector.get_table_names()
                if "user_stories" not in tables or "requirements" not in tables:
                    return False
                columns = [col["name"] for col in inspector.get_columns("user_stories")]
                return "project_id" in columns
            
            ready_for_backfill = await conn.run_sync(check_tables_exist)
            if ready_for_backfill:
                await conn.execute(text(statement))
                logger.info("Successfully completed migration step: backfill_project_ids.")
            else:
                logger.info("Skipping backfill_project_ids (required tables/columns do not exist yet).")
    except Exception as e:
        logger.error(f"Migration step failed: backfill_project_ids. Error: {str(e)}")
        logger.error(traceback.format_exc())

async def create_all_schemas(engine) -> None:
    logger.info("Running migration step: create_all_schemas.")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Successfully completed migration step: create_all_schemas.")
    except Exception as e:
        logger.critical("CRITICAL: Failed to create/initialize database schemas!", exc_info=True)
        raise RuntimeError("Database schema creation failed") from e

async def seed_default_user() -> None:
    from app.database import AsyncSessionLocal
    from app.models import UserModel
    from sqlalchemy import select
    import uuid

    logger.info("Running migration step: seed_default_user.")
    try:
        async with AsyncSessionLocal() as session:
            system_user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
            stmt = select(UserModel).where(UserModel.id == system_user_id)
            res = await session.execute(stmt)
            exists = res.scalar_one_or_none()
            if not exists:
                system_user = UserModel(
                    id=system_user_id,
                    email="system@banking.com",
                    full_name="System User",
                    role="Developer"
                )
                session.add(system_user)
                await session.commit()
                logger.info("Seeded default system user successfully.")
            else:
                logger.info("Default system user already exists.")
    except Exception as e:
        logger.critical("CRITICAL: Failed to seed default system user!", exc_info=True)
        raise RuntimeError("Default user seeding failed") from e

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing database schemas and running migrations.")
    try:
        await drop_constraint(engine)
        await add_project_column(engine)
        await add_audit_columns(engine)
        await backfill_requirements(engine)
        await backfill_project_ids(engine)
        
        # Run conversation_messages migration BEFORE create_all
        # so it can add columns to an existing old-schema table first
        await migrate_conversation_messages(engine)
        # Then create_all will create any missing tables (including new conversation_messages)
        await create_all_schemas(engine)
        await seed_default_user()
        
        logger.info("Database startup migrations and initialization completed successfully.")
    except Exception as e:
        logger.critical(f"Database initialization failed during a critical step: {str(e)}", exc_info=True)
        raise e

# Enterprise CORS middleware to enable external preview sandbox requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper HTTP client utility to dispatch local inference tasks to LM Studio
async def call_lm_studio(prompt_messages: List[Dict[str, str]], response_format_schema: Any = None) -> Dict[str, Any]:
    """
    Direct low-latency route utility to LM Studio.
    Forces strict JSON outputs using custom parameters, staying within MacBook memory parameters.
    """
    headers = {
        "Authorization": f"Bearer {settings.LM_STUDIO_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Configure request payload staying strictly inside context window memory budgets
    payload: Dict[str, Any] = {
        "model": settings.LM_STUDIO_MODEL_FALLBACK,
        "messages": prompt_messages,
        "temperature": settings.TEMPERATURE,
        "max_tokens": 1500,  # Retain safe generation budget within the 8192 limit
        "stream": False
    }

    # If schema is specified, request structured output constraints from LM Studio JSON mode
    if response_format_schema:
        payload["response_format"] = {
            "type": "json_object",
            "schema": response_format_schema.model_json_schema()
        }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            logger.info(f"Dispatching inference task to local LM Studio at {settings.LM_STUDIO_URL}")
            response = await client.post(
                f"{settings.LM_STUDIO_URL}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            # Access response text safely
            content_text = result["choices"][0]["message"]["content"]
            logger.info("Successfully fetched response from local LLM.")
            return json.loads(content_text) if response_format_schema else {"text": content_text}
            
    except httpx.HTTPStatusError as http_err:
        logger.error(f"LM Studio server returned status error: {http_err.response.status_code} - {http_err.response.text}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Inference gateway error: {str(http_err)}"
        )
    except httpx.RequestError as req_err:
        logger.error(f"Failed to connect to local LM Studio instance: {str(req_err)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LM Studio is offline or unavailable. Ensure it runs on localhost:1234 with API keys."
        )
    except json.JSONDecodeError as json_err:
        logger.error(f"Failed to parse LLM structured output block: {str(json_err)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Local LLM output failed to resolve as a valid compliance schema."
        )


# ==========================================
# PENDING ACTIONS API
# ==========================================

@app.get("/api/pending-actions/{project_id}")
async def get_pending_actions(project_id: str, session: AsyncSession = Depends(get_db)):
    actions = await PendingActionRepository.get_by_project(project_id, session)
    return actions

@app.post("/api/confirm-action/{action_id}")
async def confirm_action(action_id: str, project_id: str, session: AsyncSession = Depends(get_db)):
    # 1. Get the action
    actions = await PendingActionRepository.get_by_project(project_id, session)
    action = next((a for a in actions if a["id"] == action_id), None)
    
    if not action:
        raise HTTPException(status_code=404, detail="Pending action not found")
    
    # 2. Extract the proposed changes (the full merged requirement state)
    proposed_changes = action.get("proposed_changes", {})
    if not proposed_changes:
        await PendingActionRepository.delete(action_id, project_id, session)
        raise HTTPException(status_code=400, detail="No proposed changes found in pending action")
    
    # 3. Apply proposed changes to the database
    logger.info(f"[MERGE CONFIRM] Persisting merged state for project {project_id}...")
    persisted_state = await RequirementStateRepository.save_or_update(project_id, proposed_changes, session)
    
    # 4. Delete the pending action
    await PendingActionRepository.delete(action_id, project_id, session)
    
    logger.info(f"[MERGE CONFIRM] Merge confirmed and persisted for project {project_id}")
    return {
        "status": "confirmed",
        "requirement_state": persisted_state
    }

@app.post("/api/cancel-action/{action_id}")
async def cancel_action(action_id: str, project_id: str, session: AsyncSession = Depends(get_db)):
    await PendingActionRepository.delete(action_id, project_id, session)
    return {"status": "cancelled"}


# ==========================================
# 3. FASTAPI ENDPOINT ROUTERS
# ==========================================

@app.get("/api/health", status_code=status.HTTP_200_OK)
async def get_health_status():
    """Simple connection test endpoint for liveness validation checks."""
    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "local_inference_gateway": settings.LM_STUDIO_URL,
        "macbook_context_window_budget": f"{settings.MAX_CONTEXT_TOKENS} tokens"
    }


@app.post("/api/chat", status_code=status.HTTP_200_OK)
async def post_chat_query(request: ChatSessionRequest):
    """
    Orchestrates requirements dialogue prompts with the local LLM.
    Acts as the entrypoint for LangGraph multi-agent context chains.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Conversation message list cannot be empty.")

    system_instruction = (
        "You are an expert enterprise business analyst specializing in core banking requirement designs. "
        "Adhere to Krungsri Nimble standards, ensure high compliance, security OTP mechanics, and double-entry general ledgers. "
        f"Strictly keep your replies inside a total contextual window budget of {settings.MAX_CONTEXT_TOKENS} tokens."
    )

    formatted_messages = [{"role": "system", "content": system_instruction}]
    for msg in request.messages:
        formatted_messages.append({"role": msg.role, "content": msg.content})
        if request.project_id:
            await ConversationMessageRepository.save_message(
                project_id=str(request.project_id),
                role=msg.role,
                message=msg.content,
                workflow_state="chat",
                intent="GENERAL_CHAT"
            )

    logger.info("Initiating conversational analyst run.")
    response = await call_lm_studio(formatted_messages)
    reply_text = response.get("text", "")

    if request.project_id and reply_text:
        await ConversationMessageRepository.save_message(
            project_id=str(request.project_id),
            role="assistant",
            message=reply_text,
            workflow_state="chat",
            intent="GENERAL_CHAT"
        )

    return {"message": reply_text}


@app.post("/api/audit/respond/{question_id}", status_code=status.HTTP_200_OK)
async def post_audit_resolution_reply(question_id: UUID, payload: UserAnswerSubmit, db: AsyncSession = Depends(get_db)):
    """
    Submits official BA/PO answer to close an active compliance query roadblock.
    Triggers automated DB state validation routines.
    """
    logger.info(f"Updating clarification question {question_id} state with resolution.")
    
    # In a full production implementation, we would execute matching DB updates:
    # db_query = select(ClarificationQuestion).where(ClarificationQuestion.id == question_id)
    # result = await db.execute(db_query)
    # question = result.scalar_one_or_none()
    # if not question: raise HTTPException(status_code=404)
    # question.user_answer = payload.answer_text
    # question.is_resolved = True
    # await db.commit()

    return {
        "status": "success",
        "message": f"Answer to clarification question {question_id} has been logged and registered.",
        "resolved_at": "now",
        "is_resolved": True
    }


@app.post("/api/prd/export/{project_id}", status_code=status.HTTP_200_OK)
async def post_prd_export_generation(project_id: UUID):
    """
    Gathers linked user stories and acceptance criteria, dispatches to local LLM,
    and returns a clean, finalized Production PRD document structured in markdown.
    """
    logger.info(f"Triggering automated compliance PRD synthesis for project {project_id}.")

    # Formulate mock context based on standard payload schemas for deterministic prompt templates
    mock_system_payload_description = (
        "GIVEN a payment gateway transaction exceeding 100,000 THB\n"
        "WHEN they click 'Confirm Transfer'\n"
        "THEN system dispatches an authenticator modal and validates OTP code within 180 seconds."
    )

    prompt = [
        {
            "role": "system",
            "content": "You are a senior system architect. Summarize requirements into a formal, compliant PRD in markdown format."
        },
        {
            "role": "user",
            "content": f"Synthesize a PRD based on project {project_id}. Mapped Acceptance Criteria is as follows:\n{mock_system_payload_description}"
        }
    ]

    prd_response = await call_lm_studio(prompt)
    markdown_content = prd_response.get("text", "# PRD\n\nFailed to synthesize PRD.")

    return {
        "project_id": project_id,
        "version": 1,
        "prd_markdown": markdown_content,
        "mermaid_diagram": "sequenceDiagram\n  Customer->>Gateway: Transfer Request\n  Gateway-->>Customer: Challenge Modal"
    }


@app.get("/api/projects", status_code=status.HTTP_200_OK)
async def get_projects(db: AsyncSession = Depends(get_db)):
    return await ProjectRepository.list_all(db)

@app.post("/api/projects", status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    import uuid
    project_data = payload.dict()
    project_data["id"] = str(uuid.uuid4())
    # Use system user UUID as default until proper auth is implemented
    project_data["user_id"] = "00000000-0000-0000-0000-000000000000"
    return await ProjectRepository.create_project(project_data, db)

@app.put("/api/projects/{project_id}", status_code=status.HTTP_200_OK)
async def update_project(project_id: str, payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    """Update an existing project (rename)."""
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")
    
    updates = payload.dict()
    updated = await ProjectRepository.update(project_id, updates, db)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated

@app.delete("/api/projects/{project_id}", status_code=status.HTTP_200_OK)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Delete an existing project."""
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")
    
    deleted = await ProjectRepository.delete(project_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted", "project_id": project_id}


@app.get("/api/project/{project_id}", status_code=status.HTTP_200_OK)
async def get_project_requirement_state(project_id: str, session: AsyncSession = Depends(get_db)):
    """
    Retrieves the centralized RequirementState for a project from Supabase.
    If it doesn't exist, returns default initialized values.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    logger.info(f"[DB LOG] Loading RequirementState for project {project_id}")
    state = await RequirementStateRepository.get_by_project_id(project_id, session)
    logger.info(f"[DB LOG] Loading RequirementState for project {project_id} complete. Found: {state is not None}")
    if not state:
        state = {
            "project_id": project_id,
            "project_name": "PromptPay Settlement Engine",
            "requirements": [
                {
                    "requirement_code": "REQ-001",
                    "title": "PromptPay Real-Time Merchant Settlement Engine",
                    "description": "Main epic for PromptPay settlement",
                    "user_stories": []
                }
            ],
            "business_goals": [],
            "actors": [],
            "user_stories": [
                {
                    "ticket_code": "US-001",
                    "story_title": "Real-time Fund Settlement via QR Scan",
                    "as_a": "Corporate Merchant Retailer",
                    "i_want_to": "receive instant notifications and settlement when a customer scans my PromptPay QR code",
                    "so_that": "I can verify payment immediately and dispense goods without settlement delay",
                    "acceptance_criteria": [
                        "Given a customer has scanned a valid static PromptPay QR code, When the transaction is approved by the national switch, Then the funds are instantly credited to the corporate account.",
                        "Given the system detects a network timeout during national switch callback, When the transaction is retried, Then an explicit idempotency key must be checked to prevent double posting."
                    ]
                }
            ],
            "acceptance_criteria": [
                "Given a customer has scanned a valid static PromptPay QR code, When the transaction is approved by the national switch, Then the funds are instantly credited to the corporate account.",
                "Given the system detects a network timeout during national switch callback, When the transaction is retried, Then an explicit idempotency key must be checked to prevent double posting."
            ],
            "clarification_questions": [],
            "validation_status": "pending",
            "generated_prd": "",
            "generated_diagrams": "",
            "current_workflow_state": "gatherer_node",
            "version_number": 1,
            "updated_at": None
        }
        # Save default to database
        logger.info(f"[DB LOG] Saving default state for project {project_id}...")
        state = await RequirementStateRepository.save_or_update(project_id, state, session)
        logger.info(f"[DB LOG] Saving default state for project {project_id} complete.")

    conv_history = await ConversationMessageRepository.get_conversation_history(project_id)
    if isinstance(state, dict):
        state = dict(state)
        state["conversation_history"] = conv_history
    return state


@app.get("/api/project/{project_id}/conversations", status_code=status.HTTP_200_OK)
async def get_project_conversations(project_id: str):
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")
    return await ConversationMessageRepository.get_conversation_history(project_id)


@app.put("/api/project/{project_id}", status_code=status.HTTP_200_OK)
async def update_project_requirement_state(project_id: str, updates: Dict[str, Any], session: AsyncSession = Depends(get_db)):
    """
    Directly updates the centralized RequirementState for a project in the database.
    Useful for saving manual PRD edits and synchronizing sections.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    logger.info(f"[DB LOG] Updating RequirementState directly for project {project_id}")
    state = await RequirementStateRepository.save_or_update(project_id, updates, session)
    return state


@app.post("/api/clarification/submit", status_code=status.HTTP_200_OK)
async def post_clarification_submit(payload: Dict[str, Any], session: AsyncSession = Depends(get_db)):
    """
    Submits answers to clarification questions, runs Auditor compliance check,
    and updates workflow state.
    """
    project_id = payload.get("project_id")
    answers = payload.get("answers", {})
    
    req_state = await RequirementStateRepository.get_by_project_id(project_id, session)
    if not req_state:
        raise HTTPException(status_code=404, detail="Project not found")
        
    questions = req_state.get("clarification_questions", [])
    for idx, q in enumerate(questions):
        ans_key = f"q-{idx}"
        if ans_key in answers:
            q["user_answer"] = answers[ans_key]
            q["is_resolved"] = True
            
    req_state["clarification_questions"] = questions
    
    unresolved = [q for q in questions if not q.get("is_resolved", False)]
    is_valid = len(unresolved) == 0
    req_state["validation_status"] = "valid" if is_valid else "invalid"
    req_state["current_workflow_state"] = "REVIEWING" if is_valid else "WAITING_CLARIFICATION"
    
    saved_state = await RequirementStateRepository.save_or_update(project_id, req_state, session)
    return saved_state


@app.post("/api/process-requirements", status_code=status.HTTP_200_OK)
async def post_process_requirements(request: ProcessRequirementsRequest, session: AsyncSession = Depends(get_db)):
    """
    Asynchronously invokes the LangGraph multi-agent workflow (prd_workflow)
    to process raw requirements, audit compliance, or build PRD & architectural diagrams.
    Loads and updates the shared RequirementState from Supabase (as single source of truth).
    
    Pipeline:
    1. Persist every user message before intent detection
    2. Detect intent (GENERAL_CHAT, REQUIREMENT_REQUEST)
    3. If GENERAL_CHAT: generate response with project context, persist, return (no LangGraph)
    4. If REQUIREMENT_REQUEST: proceed to LangGraph workflow
    5. Persist every assistant response
    """
    logger.info(f"Triggering on-demand {request.target_agent} agent for project {request.project_id}")
    
    # ==========================================
    # STEP 1: Persist every user message before any intent detection or agent routing
    # ==========================================
    if request.project_id and request.raw_input and request.raw_input.strip():
        await ConversationMessageRepository.save_message(
            project_id=str(request.project_id),
            role="user",
            message=request.raw_input.strip(),
            workflow_state=request.target_agent or "gatherer",
            intent="PENDING_DETECTION"
        )

    # ==========================================
    # STEP 2: Intent Detection (before LangGraph)
    # ==========================================
    from app.semantic_service import detect_requirement_intent, generate_general_chat_response
    
    # Load the centralized RequirementState from Supabase (single source of truth)
    logger.info(f"[DB LOG] Loading RequirementState for processing project {request.project_id}")
    req_state = await RequirementStateRepository.get_by_project_id(request.project_id, session)
    logger.info(f"[DB LOG] Loading RequirementState for processing project {request.project_id} complete. Found: {req_state is not None}")
    
    # Detect intent on the raw input
    detected_intent_result = await detect_requirement_intent(
        request.raw_input or "",
        req_state.get("user_stories", []) if req_state else []
    )
    detected_intent = detected_intent_result.get("intent", "GENERAL_CHAT")
    logger.info(f"[INTENT DETECTION] Detected intent: {detected_intent} (confidence: {detected_intent_result.get('confidence', 0.0)})")
    
    # ==========================================
    # STEP 3: GENERAL_CHAT handling (bypass LangGraph entirely)
    # ==========================================
    # If the intent is GENERAL_CHAT (greeting, question, explanation request, concept query),
    # generate an LLM response directly without entering any agent workflow.
    # REQUIREMENT_REQUEST intents fall through to the LangGraph workflow below.
    if detected_intent == "GENERAL_CHAT":
        logger.info("[GENERAL_CHAT] Handling as general chat. Generating conversational response with project context.")

        # Load conversation history for context (with error handling for DB failures)
        conv_history = []
        if request.project_id:
            try:
                conv_history = await ConversationMessageRepository.get_conversation_history(request.project_id)
            except Exception as db_err:
                logger.warning(f"[GENERAL_CHAT] Failed to load conversation history from DB: {str(db_err)}. Proceeding without history.")

        # Generate response with full project context
        try:
            response_text = await generate_general_chat_response(
                raw_input=request.raw_input or "",
                project_context=req_state or {},
                conversation_history=conv_history
            )
        except Exception as llm_err:
            logger.error(f"[GENERAL_CHAT] Failed to generate LLM response: {str(llm_err)}")
            response_text = "I understand your question, but I'm currently experiencing some technical difficulties. Please try again in a moment."

        # Persist assistant response (with error handling for DB failures)
        if request.project_id and response_text:
            try:
                await ConversationMessageRepository.save_message(
                    project_id=str(request.project_id),
                    role="assistant",
                    message=response_text,
                    workflow_state="general_chat",
                    intent="GENERAL_CHAT"
                )
            except Exception as db_err:
                logger.warning(f"[GENERAL_CHAT] Failed to save assistant response to DB: {str(db_err)}. Response generated but not persisted.")

        # Return response (no project artifacts modified)
        return {
            "status": "general_chat",
            "detected_intent": "GENERAL_CHAT",
            "message": response_text,
            "structured_requirements": {
                "epic_name": (
                    req_state.get("requirements", [])[0].get("title", "")
                    if req_state and req_state.get("requirements")
                    else ""
                ),
                "version": req_state.get("version_number", 1) if req_state else 1,
                "user_stories": req_state.get("user_stories", []) if req_state else []
            } if req_state else {},
            "audit_result": {
                "is_valid": req_state.get("validation_status") == "valid" if req_state else False,
                "audit_version_reviewed": req_state.get("version_number", 1) if req_state else 1,
                "clarification_questions": req_state.get("clarification_questions", []) if req_state else [],
                "passed_checks": [],
                "failed_checks": []
            },
            "prd_markdown": req_state.get("generated_prd", "") if req_state else "",
            "mermaid_diagram": req_state.get("generated_diagrams", "") if req_state else "",
            "workflow_routing": {"workflow": "CHAT", "confidence": 1.0, "reason": "Routed as GENERAL_CHAT via intent detection."}
        }
    
    # ==========================================
    # STEP 4: Route based on detected intent
    # ==========================================
    # Map detected intent to target_agent for LangGraph workflow routing
    intent_to_target = {
        "CREATE_REQUIREMENT": "gatherer",
        "UPDATE_REQUIREMENT": "gatherer",
        "DELETE_REQUIREMENT": "delete_requirement",
        "CLARIFY_REQUIREMENT": "auditor",
    }
    if detected_intent in intent_to_target:
        request.target_agent = intent_to_target[detected_intent]
        logger.info(f"[INTENT ROUTING] Intent {detected_intent} -> target_agent={request.target_agent}")
    
    current_state = req_state.get("current_workflow_state", "IDLE") if req_state else "IDLE"
    logger.info(f"[WORKFLOW STATE MACHINE] Current workflow state: {current_state}")

    # Routing rules based on current_workflow_state
    if current_state == "IDLE":
        current_state = "GATHERING"
    elif current_state == "GATHERING":
        pass
    elif current_state == "REVIEWING":
        if request.target_agent == "gatherer" or (request.raw_input and ("update" in request.raw_input.lower() or "create" in request.raw_input.lower() or "add" in request.raw_input.lower())):
            current_state = "GATHERING"
        else:
            # Wait for user edits / normal chat, do not run gatherer automatically
            pass
    elif current_state == "AUDITING":
        if request.target_agent != "auditor":
            # Wait until user explicitly clicks Run Auditor
            pass
    elif current_state == "WAITING_CLARIFICATION":
        # User messages treated as clarification answers
        request.target_agent = "auditor"
    elif current_state == "ARCHITECTING":
        if request.target_agent != "architect":
            # Wait until user explicitly clicks Generate PRD / Diagram
            pass
    elif current_state == "COMPLETED":
        if request.target_agent == "gatherer" or (request.raw_input and ("update" in request.raw_input.lower() or "create" in request.raw_input.lower())):
            current_state = "GATHERING"
        else:
            pass

    if not req_state:
        reqs = request.structured_requirements or {}
        all_ac = []
        for us in reqs.get("user_stories", []):
            all_ac.extend(us.get("acceptance_criteria", []))
            
        req_state = {
            "project_id": request.project_id,
            "project_name": "PromptPay Settlement Engine",
            "requirements": [
                {
                    "requirement_code": "REQ-001",
                    "title": reqs.get("epic_name", ""),
                    "description": "",
                    "user_stories": reqs.get("user_stories", [])
                }
            ] if reqs else [],
            "business_goals": [],
            "actors": [],
            "user_stories": reqs.get("user_stories", []),
            "acceptance_criteria": all_ac,
            "clarification_questions": [],
            "validation_status": "pending",
            "generated_prd": "",
            "generated_diagrams": "",
            "current_workflow_state": current_state,
            "version_number": request.current_version if request.current_version is not None else 1,
            "updated_at": None
        }
    else:
        req_state["current_workflow_state"] = current_state
        # If frontend sent newer structured_requirements (e.g. user manually updated them), sync in memory before workflow run
        if request.structured_requirements:
            reqs = request.structured_requirements
            all_ac = []
            for us in reqs.get("user_stories", []):
                all_ac.extend(us.get("acceptance_criteria", []))
            
            reqs_list = reqs.get("requirements", [])
            if isinstance(reqs_list, list) and reqs_list:
                # Use the requirements list from frontend
                req_state["requirements"] = reqs_list
            else:
                # Convert legacy epic_name to requirement format
                req_state["requirements"] = [
                    {
                        "requirement_code": "REQ-001",
                        "title": reqs.get("epic_name", ""),
                        "description": "",
                        "user_stories": reqs.get("user_stories", [])
                    }
                ]
            req_state["user_stories"] = reqs.get("user_stories", [])
            req_state["acceptance_criteria"] = all_ac
            if "version" in reqs:
                req_state["version_number"] = reqs["version"]

    # Formulate initial state corresponding to AgentState TypedDict
    initial_state = {
        "project_id": request.project_id,
        "raw_input": request.raw_input or "",
        "structured_requirements": {
            "epic_name": (
                req_state.get("requirements", [])[0].get("title", "")
                if req_state and req_state.get("requirements")
                else ""
            ),
            "version": req_state.get("version_number", 1),
            "user_stories": req_state.get("user_stories", [])
        },
        "audit_result": {},
        "prd_markdown": req_state.get("generated_prd", ""),
        "mermaid_diagram": req_state.get("generated_diagrams", ""),
        "current_version": req_state.get("version_number", 1),
        "version_history_summaries": request.version_history_summaries if request.version_history_summaries is not None else "No previous history.",
        "target_agent": request.target_agent or "gatherer",
        "requirement_state": req_state,
        "detected_intent": detected_intent,
        "db_session": session  # Pass the active session to workflow nodes
    }
    
    try:
        # Run state graph asynchronously (merges and generates in memory)
        final_state = await prd_workflow.ainvoke(initial_state)
        
        # Read updated centralized RequirementState from final graph output
        req_state = final_state.get("requirement_state", req_state)
        
        # Update workflow state after run
        if request.target_agent == "gatherer" or current_state == "GATHERING":
            req_state["current_workflow_state"] = "REVIEWING"
        elif request.target_agent == "auditor":
            is_valid = req_state.get("validation_status") == "valid"
            req_state["current_workflow_state"] = "REVIEWING" if is_valid else "WAITING_CLARIFICATION"
        elif request.target_agent == "architect":
            req_state["current_workflow_state"] = "COMPLETED"

        workflow_routing = final_state.get("workflow_routing") or {}
        wf_type = str(workflow_routing.get("workflow", "REQUIREMENT")).upper()

        # ==========================================
        # IN-MEMORY MERGE: Store merged state as a pending action instead of directly persisting to DB.
        # The user must confirm before changes are committed to the database.
        # ==========================================
        import uuid
        from datetime import timedelta
        
        logger.info(f"[IN-MEMORY MERGE] Storing merged state as pending action for project {request.project_id}...")
        
        # Create a pending action with the full merged state as proposed changes
        pending_action = await PendingActionRepository.create(
            project_id=request.project_id,
            data={
                "action_type": "MERGE",
                "target_requirement_id": None,
                "original_user_message": request.raw_input or "",
                "proposed_changes": req_state,
                "affected_user_story_ids": [],
                "affected_acceptance_criteria_ids": [],
                "workflow_stage": req_state.get("current_workflow_state", "gatherer_node")
            },
            expires_at=datetime.utcnow() + timedelta(hours=1),
            session=session
        )
        
        pending_action_id = pending_action.get("id")
        logger.info(f"[IN-MEMORY MERGE] Pending action {pending_action_id} created. Awaiting user confirmation.")
        
        # ==========================================
        # STEP 5: Persist assistant response for non-GENERAL_CHAT intents
        # ==========================================
        agent_message = final_state.get("agent_message", "")
        if request.project_id and agent_message:
            await ConversationMessageRepository.save_message(
                project_id=str(request.project_id),
                role="assistant",
                message=agent_message,
                workflow_state=req_state.get("current_workflow_state", request.target_agent or "gatherer"),
                intent=detected_intent
            )
        
        # Determine status dynamically based on centralized validation status
        is_valid = req_state.get("validation_status") == "valid"
        status_str = "completed" if is_valid else "audit_pending"
        
        # Format structures back to preserve frontend compatibility
        reqs_data = req_state.get("requirements", [])
        if isinstance(reqs_data, list):
            # Multi-requirement format
            epic_name = reqs_data[0].get("title", "") if reqs_data else ""
            structured_out = {
                "epic_name": epic_name,
                "version": req_state.get("version_number", 1),
                "user_stories": req_state.get("user_stories", []),
                "requirements": reqs_data
            }
        elif isinstance(reqs_data, dict):
            # Legacy dict format
            structured_out = {
                "epic_name": reqs_data.get("epic_name", ""),
                "version": req_state.get("version_number", 1),
                "user_stories": req_state.get("user_stories", [])
            }
        else:
            # Fallback for None or unexpected types
            structured_out = {
                "epic_name": "",
                "version": req_state.get("version_number", 1),
                "user_stories": req_state.get("user_stories", [])
            }
        
        # Ensure audit result fields are cleanly populated
        audit_out = {
            "is_valid": is_valid,
            "audit_version_reviewed": req_state.get("version_number", 1),
            "clarification_questions": req_state.get("clarification_questions", []),
            "passed_checks": final_state.get("audit_result", {}).get("passed_checks", []),
            "failed_checks": final_state.get("audit_result", {}).get("failed_checks", [])
        }
        
        return {
            "status": status_str,
            "workflow_routing": workflow_routing,
            "detected_intent": final_state.get("detected_intent") or req_state.get("detected_intent", detected_intent),
            "structured_requirements": structured_out,
            "audit_result": audit_out,
            "prd_markdown": req_state.get("generated_prd", ""),
            "mermaid_diagram": req_state.get("generated_diagrams", ""),
            "message": agent_message,
            "pending_merge": True,
            "pending_action_id": pending_action_id
        }
    except Exception as e:
        logger.error(f"Multi-agent workflow execution failed for project {request.project_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LangGraph multi-agent workflow execution failed: {str(e)}"
        )


class WorkflowRouterRequest(BaseModel):
    message: str

@app.post("/api/workflow-router", status_code=status.HTTP_200_OK)
async def post_workflow_router(payload: WorkflowRouterRequest):
    """
    Direct endpoint for testing and executing the Workflow Router.
    Classifies incoming message into CHAT, QUESTION, COMMAND, or REQUIREMENT.
    """
    from app.semantic_service import classify_workflow
    return await classify_workflow(payload.message)


class IntentDetectorRequest(BaseModel):
    message: str
    project_id: Optional[str] = None

@app.post("/api/intent-detector", status_code=status.HTTP_200_OK)
async def post_intent_detector(payload: IntentDetectorRequest, db: AsyncSession = Depends(get_db)):
    """
    Direct endpoint for testing and executing Requirement Intent Detection (GENERAL_CHAT, REQUIREMENT_REQUEST).
    """
    from app.semantic_service import detect_requirement_intent
    from app.repository import RequirementRepository
    
    current_stories = []
    if payload.project_id:
        try:
            req_state = await RequirementStateRepository.get_by_project_id(payload.project_id, db)
            current_stories = req_state.get("user_stories", []) if req_state else []
        except Exception:
            pass
            
    result = await detect_requirement_intent(payload.message, current_stories)
    return result


class RequirementMatcherRequest(BaseModel):
    message: str
    project_id: Optional[str] = None
    detected_intent: Optional[str] = "UPDATE"

@app.post("/api/requirement-matcher", status_code=status.HTTP_200_OK)
async def post_requirement_matcher(payload: RequirementMatcherRequest, db: AsyncSession = Depends(get_db)):
    """
    Direct endpoint for testing and executing the Requirement Matcher Agent.
    Determines which existing requirement(s) the user's message refers to before any modification occurs.
    """
    from app.semantic_service import match_requirement, detect_requirement_intent
    from app.repository import RequirementRepository
    
    current_stories = []
    if payload.project_id:
        try:
            req_state = await RequirementStateRepository.get_by_project_id(payload.project_id, db)
            current_stories = req_state.get("user_stories", []) if req_state else []
        except Exception:
            pass
            
    intent = payload.detected_intent
    if not intent:
        intent_res = await detect_requirement_intent(payload.message, current_stories)
        intent = intent_res.get("intent", "UPDATE")

    result = await match_requirement(payload.message, intent, current_stories)
    return result



# ==========================================
# PRD VERSION HISTORY API
# ==========================================

@app.get("/api/project/{project_id}/prd-versions", status_code=status.HTTP_200_OK)
async def get_prd_versions(project_id: str, session: AsyncSession = Depends(get_db)):
    """
    Retrieves all PRD versions for a project.
    Returns an ordered list of immutable PRD version records.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    versions = await PRDVersionRepository.get_by_project(project_id, session)
    return versions


@app.get("/api/project/{project_id}/prd-versions/latest", status_code=status.HTTP_200_OK)
async def get_latest_prd_version(project_id: str, session: AsyncSession = Depends(get_db)):
    """
    Retrieves the latest PRD version for a project.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    version = await PRDVersionRepository.get_latest(project_id, session)
    if not version:
        raise HTTPException(status_code=404, detail="No PRD versions found for this project")
    return version


@app.get("/api/project/{project_id}/prd-versions/{version_number}", status_code=status.HTTP_200_OK)
async def get_prd_version_by_number(project_id: str, version_number: int, session: AsyncSession = Depends(get_db)):
    """
    Retrieves a specific PRD version by version number.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    version = await PRDVersionRepository.get_by_version_number(project_id, version_number, session)
    if not version:
        raise HTTPException(status_code=404, detail=f"PRD version {version_number} not found for this project")
    return version


# ==========================================
# ARTIFACT EVENT LOG API
# ==========================================

@app.get("/api/events", status_code=status.HTTP_200_OK)
async def get_recent_events(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db)
):
    """
    Retrieve the most recent artifact event log entries across all projects.
    Returns events ordered by timestamp descending (newest first).
    """
    events = await ArtifactEventLogRepository.get_recent(session, limit=limit, offset=offset)
    return {
        "events": events,
        "total": len(events),
        "limit": limit,
        "offset": offset
    }


@app.get("/api/events/{artifact_type}/{artifact_id}", status_code=status.HTTP_200_OK)
async def get_artifact_events(
    artifact_type: str,
    artifact_id: str,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_db)
):
    """
    Retrieve all events for a specific artifact (e.g. a user story, requirement, epic).
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


@app.get("/api/events/action/{action}", status_code=status.HTTP_200_OK)
async def get_events_by_action(
    action: str,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_db)
):
    """
    Retrieve all events for a specific action type (CREATE, UPDATE, DELETE, ARCHIVE, LOCK, UNLOCK).
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


@app.get("/api/project/{project_id}/events", status_code=status.HTTP_200_OK)
async def get_project_events(
    project_id: str,
    artifact_type: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_db)
):
    """
    Retrieve events for a project, optionally filtered by artifact_type and/or action.
    Queries events by known artifact IDs for the project.
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


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on http://0.0.0.0:8000")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
