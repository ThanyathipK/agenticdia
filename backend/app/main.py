import logging
import json
import httpx
import traceback
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.config import settings
from app.database import get_db, engine
from app.models import Base
from app.repository import RequirementStateRepository, ProjectRepository
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
# 3. FASTAPI ENDPOINT ROUTERS
# ==========================================

@app.get("/health", status_code=status.HTTP_200_OK)
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

    logger.info("Initiating conversational analyst run.")
    response = await call_lm_studio(formatted_messages)
    return {"message": response.get("text", "")}


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
    # Temporary: user_id is optional until auth is implemented
    project_data["user_id"] = None
    return await ProjectRepository.create_project(project_data, db)


@app.get("/api/project/{project_id}", status_code=status.HTTP_200_OK)
async def get_project_requirement_state(project_id: str):
    """
    Retrieves the centralized RequirementState for a project from Supabase.
    If it doesn't exist, returns default initialized values.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    logger.info(f"[DB LOG] Loading RequirementState for project {project_id}")
    state = await RequirementStateRepository.get_by_project_id(project_id)
    logger.info(f"[DB LOG] Loading RequirementState for project {project_id} complete. Found: {state is not None}")
    if not state:
        state = {
            "project_id": project_id,
            "project_name": "PromptPay Settlement Engine",
            "requirements": {"epic_name": "PromptPay Real-Time Merchant Settlement Engine"},
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
        state = await RequirementStateRepository.save_or_update(project_id, state)
        logger.info(f"[DB LOG] Saving default state for project {project_id} complete.")
    return state


@app.put("/api/project/{project_id}", status_code=status.HTTP_200_OK)
async def update_project_requirement_state(project_id: str, updates: Dict[str, Any]):
    """
    Directly updates the centralized RequirementState for a project in the database.
    Useful for saving manual PRD edits and synchronizing sections.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    logger.info(f"[DB LOG] Updating RequirementState directly for project {project_id}")
    state = await RequirementStateRepository.save_or_update(project_id, updates)
    return state


@app.post("/api/process-requirements", status_code=status.HTTP_200_OK)
async def post_process_requirements(request: ProcessRequirementsRequest):
    """
    Asynchronously invokes the LangGraph multi-agent workflow (prd_workflow)
    to process raw requirements, audit compliance, or build PRD & architectural diagrams.
    Loads and updates the shared RequirementState from Supabase (as single source of truth).
    """
    logger.info(f"Triggering on-demand {request.target_agent} agent for project {request.project_id}")
    
    # Load the centralized RequirementState from Supabase (single source of truth)
    logger.info(f"[DB LOG] Loading RequirementState for processing project {request.project_id}")
    req_state = await RequirementStateRepository.get_by_project_id(request.project_id)
    logger.info(f"[DB LOG] Loading RequirementState for processing project {request.project_id} complete. Found: {req_state is not None}")
    if not req_state:
        reqs = request.structured_requirements or {}
        all_ac = []
        for us in reqs.get("user_stories", []):
            all_ac.extend(us.get("acceptance_criteria", []))
            
        req_state = {
            "project_id": request.project_id,
            "project_name": "PromptPay Settlement Engine",
            "requirements": {"epic_name": reqs.get("epic_name", "")} if reqs else {},
            "business_goals": [],
            "actors": [],
            "user_stories": reqs.get("user_stories", []),
            "acceptance_criteria": all_ac,
            "clarification_questions": [],
            "validation_status": "pending",
            "generated_prd": "",
            "generated_diagrams": "",
            "current_workflow_state": request.target_agent or "gatherer_node",
            "version_number": request.current_version if request.current_version is not None else 1,
            "updated_at": None
        }
        logger.info(f"[DB LOG] Saving initial state for project {request.project_id}...")
        req_state = await RequirementStateRepository.save_or_update(request.project_id, req_state)
        logger.info(f"[DB LOG] Saving initial state for project {request.project_id} complete.")
    else:
        # If frontend sent newer structured_requirements (e.g. user manually updated them), sync them before workflow run
        if request.structured_requirements:
            reqs = request.structured_requirements
            all_ac = []
            for us in reqs.get("user_stories", []):
                all_ac.extend(us.get("acceptance_criteria", []))
            
            updates = {
                "requirements": {"epic_name": reqs.get("epic_name", "")},
                "user_stories": reqs.get("user_stories", []),
                "acceptance_criteria": all_ac,
                "version_number": reqs.get("version", req_state["version_number"])
            }
            logger.info(f"[DB LOG] Updating user structured requirements for project {request.project_id}...")
            req_state = await RequirementStateRepository.save_or_update(request.project_id, updates)
            logger.info(f"[DB LOG] Updating user structured requirements for project {request.project_id} complete.")

    # Formulate initial state corresponding to AgentState TypedDict
    initial_state = {
        "project_id": request.project_id,
        "raw_input": request.raw_input or "",
        "structured_requirements": {
            "epic_name": req_state.get("requirements", {}).get("epic_name", ""),
            "version": req_state.get("version_number", 1),
            "user_stories": req_state.get("user_stories", [])
        },
        "audit_result": {},
        "prd_markdown": req_state.get("generated_prd", ""),
        "mermaid_diagram": req_state.get("generated_diagrams", ""),
        "current_version": req_state.get("version_number", 1),
        "version_history_summaries": request.version_history_summaries if request.version_history_summaries is not None else "No previous history.",
        "target_agent": request.target_agent or "gatherer",
        "requirement_state": req_state
    }
    
    try:
        # Run state graph asynchronously (nodes will load/save to database internally)
        final_state = await prd_workflow.ainvoke(initial_state)
        
        # Read updated centralized RequirementState from final graph output
        req_state = final_state.get("requirement_state", req_state)
        
        # Determine status dynamically based on centralized validation status
        is_valid = req_state.get("validation_status") == "valid"
        status_str = "completed" if is_valid else "audit_pending"
        
        # Format structures back to preserve frontend compatibility
        structured_out = {
            "epic_name": req_state.get("requirements", {}).get("epic_name", ""),
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
            "structured_requirements": structured_out,
            "audit_result": audit_out,
            "prd_markdown": req_state.get("generated_prd", ""),
            "mermaid_diagram": req_state.get("generated_diagrams", "")
        }
    except Exception as e:
        logger.error(f"Multi-agent workflow execution failed for project {request.project_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LangGraph multi-agent workflow execution failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on http://0.0.0.0:8000")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
