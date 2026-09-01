import asyncio
import logging
import re
import uuid
from typing import Dict, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.latex_service import (
    compile_latex_to_pdf,
    convert_latex_to_docx,
    convert_markdown_to_docx,
    convert_markdown_to_pdf,
    docx_to_pdf,
    has_markdown_structure,
    is_markdown_prd,
    prd_to_markdown,
    soffice_available,
)
from app.repositories import (
    ProjectRepository,
    RequirementStateRepository,
    ConversationMessageRepository,
    PRDVersionRepository,
)
from app.schemas import (
    ProjectCreate,
    ProjectSummary,
    ProjectCreated,
    ProjectDeleteResponse,
    ProjectPinRequest,
    RequirementStateResponse,
    ConversationMessageResponse,
    PRDVersionResponse,
    PRDExportResponse,
)
from app.prompt_loader import load_prd_template, load_prd_latex_template
from app.event_manager import event_manager

logger = logging.getLogger("app.routes.projects")

router = APIRouter()


@router.get("/api/projects", response_model=List[ProjectSummary], status_code=status.HTTP_200_OK)
async def get_projects(db: AsyncSession = Depends(get_db)) -> List[ProjectSummary]:
    """
    List all projects.

    Args:
        db: Active asynchronous database session.

    Returns:
        List[ProjectSummary]: All project summary records.
    """
    return await ProjectRepository.list_all(db)


@router.get("/api/projects/search", response_model=List[ProjectSummary], status_code=status.HTTP_200_OK)
async def search_projects(
    q: str = Query(..., min_length=1, description="Text matched case-insensitively against project names and conversation message content."),
    db: AsyncSession = Depends(get_db),
) -> List[ProjectSummary]:
    """
    Search projects by name or by their conversation message content.

    Args:
        q: Search text; matched case-insensitively against project names and
           any persisted conversation message belonging to the project.
        db: Active asynchronous database session.

    Returns:
        List[ProjectSummary]: Matching project summary records (pinned first).

    Raises:
        HTTPException: 400 if the query is empty after trimming.
    """
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query must not be empty")
    return await ProjectRepository.search(db, query)


@router.post("/api/projects", response_model=ProjectCreated, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)) -> ProjectCreated:
    """
    Create a new project and initialize its requirement state.

    Args:
        payload: Project creation payload.
        db: Active asynchronous database session.

    Returns:
        ProjectCreated: The new project's UUID string and name.
    """
    project_data = payload.model_dump()
    project_data["id"] = str(uuid.uuid4())
    # Use system user UUID as default until proper auth is implemented
    project_data["user_id"] = "00000000-0000-0000-0000-000000000000"
    created_project = await ProjectRepository.create_project(project_data, db)
    await event_manager.publish(str(project_data["id"]), "project_created", {"project_id": project_data["id"]})
    return created_project


@router.put("/api/projects/{project_id}", response_model=ProjectSummary, status_code=status.HTTP_200_OK)
async def update_project(project_id: str, payload: ProjectCreate, db: AsyncSession = Depends(get_db)) -> ProjectSummary:
    """
    Update an existing project (rename).

    Args:
        project_id: Project UUID string.
        payload: Updated project fields.
        db: Active asynchronous database session.

    Returns:
        ProjectSummary: The updated project record.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID; 404 if not found.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    updates = payload.model_dump()
    updated = await ProjectRepository.update(project_id, updates, db)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    await event_manager.publish(project_id, "project_updated", {
        "project_id": project_id,
        "name": updates.get("name")
    })
    return updated


@router.delete("/api/projects/{project_id}", response_model=ProjectDeleteResponse, status_code=status.HTTP_200_OK)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)) -> ProjectDeleteResponse:
    """
    Delete an existing project.

    Args:
        project_id: Project UUID string.
        db: Active asynchronous database session.

    Returns:
        ProjectDeleteResponse: Confirmation containing the deleted project ID.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID; 404 if not found.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    deleted = await ProjectRepository.delete(project_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    await event_manager.publish(project_id, "project_deleted", {"project_id": project_id})
    return {"status": "deleted", "project_id": project_id}


@router.put("/api/projects/{project_id}/pin", response_model=ProjectSummary, status_code=status.HTTP_200_OK)
async def pin_project(project_id: str, payload: ProjectPinRequest, db: AsyncSession = Depends(get_db)) -> ProjectSummary:
    """Pin or unpin a project (chat) so it floats to the top of the sidebar.

    Args:
        project_id: Project UUID string.
        payload: Desired pinned state.
        db: Active asynchronous database session.

    Returns:
        ProjectSummary: The updated project record.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID; 404 if not found.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    updated = await ProjectRepository.toggle_pinned(project_id, payload.is_pinned, db)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    await event_manager.publish(project_id, "project_updated", {
        "project_id": project_id,
        "is_pinned": payload.is_pinned,
    })
    return updated


@router.get("/api/project/{project_id}", response_model=RequirementStateResponse, status_code=status.HTTP_200_OK)
async def get_project_requirement_state(project_id: str, session: AsyncSession = Depends(get_db)) -> RequirementStateResponse:
    """
    Retrieves the centralized RequirementState for a project from Supabase.

    If it doesn't exist, returns default initialized values. Includes the
    persisted conversation history for the project.

    Args:
        project_id: Project UUID string.
        session: Active asynchronous database session.

    Returns:
        RequirementStateResponse: The flattened requirement state.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID.
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
        await event_manager.publish(project_id, "state_initialized", {"project_id": project_id})

    conv_history = await ConversationMessageRepository.get_conversation_history(project_id)
    if isinstance(state, dict):
        state = dict(state)
        state["conversation_history"] = conv_history
    return state


@router.get("/api/project/{project_id}/conversations", response_model=List[ConversationMessageResponse], status_code=status.HTTP_200_OK)
async def get_project_conversations(project_id: str) -> List[ConversationMessageResponse]:
    """
    Retrieve the persisted conversation history for a project.

    Args:
        project_id: Project UUID string.

    Returns:
        List[ConversationMessageResponse]: All conversation messages, oldest first.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")
    return await ConversationMessageRepository.get_conversation_history(project_id)


@router.put("/api/project/{project_id}", response_model=RequirementStateResponse, status_code=status.HTTP_200_OK)
async def update_project_requirement_state(project_id: str, updates: Dict[str, Any], session: AsyncSession = Depends(get_db)) -> RequirementStateResponse:
    """
    Directly updates the centralized RequirementState for a project in the database.

    Useful for saving manual PRD edits and synchronizing sections. Refuses to
    mutate a locked project.

    Args:
        project_id: Project UUID string.
        updates: Partial requirement-state payload to apply.
        session: Active asynchronous database session.

    Returns:
        RequirementStateResponse: The updated, flattened requirement state.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID; 409 if the
            project is locked; 404 if the project cannot be resolved.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    # LOCK ENFORCEMENT: Cannot update requirement state of a locked project
    from app.lock_service import LockService, ArtifactLockError
    try:
        lock_info = await LockService.get_lock_status("project", project_id, session, project_id=project_id)
        LockService.raise_if_locked("project", project_id, lock_info)
    except ArtifactLockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    logger.info(f"[DB LOG] Updating RequirementState directly for project {project_id}")
    state = await RequirementStateRepository.save_or_update(project_id, updates, session)
    await event_manager.publish(project_id, "state_updated", {"project_id": project_id})
    return state


@router.get("/api/prd/template", status_code=status.HTTP_200_OK)
def get_prd_template() -> Dict[str, str]:
    """
    Serves the authoritative Krungsri Nimble PRD templates.

    - "template_latex": prompts/template-krungsrinimble.tex - the PDF-exact
      LaTeX template injected as the <prd_template> block into every PRD
      generation prompt. The running header/footer/page numbers are applied by
      fancyhdr at compile time rather than stored as lines.
    - "template_markdown": prompts/template.md - the markdown skeleton kept for
      the ongoing on-screen preview, so no frontend rendering breaks.

    Both expose the SAME document structure that the Architect fills in.
    """
    return {
        "template_latex": load_prd_latex_template(),
        "template_markdown": load_prd_template(),
    }


@router.post("/api/prd/export/{project_id}", response_model=PRDExportResponse, status_code=status.HTTP_200_OK)
async def post_prd_export_generation(project_id: UUID, db: AsyncSession = Depends(get_db)) -> PRDExportResponse:
    """
    Gathers linked user stories and acceptance criteria from the database,
    dispatches them to the local LLM, and returns a clean, finalized
    Production PRD document structured in markdown.

    A new immutable PRD version record is persisted on success.

    Args:
        project_id: Project UUID.
        db: Active asynchronous database session.

    Returns:
        PRDExportResponse: The generated PRD markdown, diagram, version and
            version record ID.

    Raises:
        HTTPException: 404 if the project or its requirement state is missing.
    """
    logger.info(f"Triggering automated compliance PRD synthesis for project {project_id}.")

    # Validate project existence
    project = await ProjectRepository.get_by_id(str(project_id), db)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Fetch the real requirement state: requirements, user stories, and acceptance criteria
    req_state = await RequirementStateRepository.get_by_project_id(str(project_id), db)
    if not req_state:
        raise HTTPException(
            status_code=404,
            detail=f"No requirement state found for project {project_id}. Gather requirements before exporting a PRD."
        )

    requirements = req_state.get("requirements", []) or []
    user_stories = req_state.get("user_stories", []) or []
    acceptance_criteria = req_state.get("acceptance_criteria", []) or []
    business_goals = req_state.get("business_goals", []) or []
    actors = req_state.get("actors", []) or []
    version_number = req_state.get("version_number", 1)

    if not user_stories and not requirements:
        raise HTTPException(
            status_code=404,
            detail=f"No user stories or requirements found for project {project_id}. Gather requirements before exporting a PRD."
        )

    # DETERMINISTIC TEMPLATE FILL: build the PRD by filling the official
    # Krungsri Nimble template from the persisted project artifacts. The
    # skeleton - every table, merged-cell structure and \newpage marker - is
    # always the untouched official template, so the export is PDF-exact and
    # compiles every time.
    from app.prd_filler import fill_template_body

    nested = any(
        isinstance(r, dict) and r.get("user_stories") for r in (requirements or [])
    )
    all_stories = (
        [us for r in requirements for us in (r.get("user_stories") or [])]
        if nested else user_stories
    )
    data = {
        "epic_name": (
            requirements[0].get("title", "") if requirements
            else str(project.get("name", ""))
        ),
        "business_goals": business_goals,
        "actors": actors,
        "requirements": requirements if nested else [],
        "user_stories": [] if nested else user_stories,
        "acceptance_criteria": [] if nested else acceptance_criteria,
        "scope_in": [
            s.get("story_title", "") for s in all_stories
            if isinstance(s, dict) and s.get("story_title")
        ],
    }

    markdown_content = fill_template_body(
        project_id=str(project_id),
        project_name=str(project.get("name", "")),
        version=version_number,
        data=data,
        version_summary="Initial approved version",
    )
    # Persist the newly generated PRD as an immutable version record
    version_record = None
    try:
        version_record = await PRDVersionRepository.create(str(project_id), {
            "generated_prd": markdown_content,
            "generated_diagram": "",
            "generated_by": "prd_export_endpoint"
        }, db)
        logger.info(f"[PRD EXPORT] Created PRD version {version_record['version_number']} for project {project_id}.")
    except Exception as version_err:
        # FAIL LOUDLY: a failed PRD version persistence must not be masked as a
        # successful export (the caller would otherwise receive a version_number that
        # was never actually persisted to the DB).
        logger.error(f"[PRD EXPORT] Failed to create PRD version: {str(version_err)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PRD generated but failed to persist version record: {str(version_err)}",
        ) from version_err

    await event_manager.publish(str(project_id), "prd_exported", {
        "project_id": str(project_id),
        "version": version_record["version_number"] if version_record else version_number,
    })

    return {
        "project_id": project_id,
        "version": version_record["version_number"] if version_record else version_number,
        "version_id": version_record["version_id"] if version_record else None,
        "prd_markdown": markdown_content,
        "mermaid_diagram": ""
    }


# ==========================================
# PRD FILE EXPORT API (LaTeX -> PDF / DOCX)
# ==========================================
# The generated PRD is a LaTeX document that follows the authoritative
# template-krungsrinimble.tex template, so both file exports are built from
# THAT LaTeX server-side:
#   DOCX -> native python-docx renderer (Pandoc fallback)
#   PDF  -> the SAME Word document, rendered by headless LibreOffice
#           (Tectonic/LaTeX fallback) so the two downloads always match -
#           the TeX engine silently drops Thai glyphs, the Word renderer
#           does not.
# The browser never parses the LaTeX as markdown again.


class LatexExportPayload(BaseModel):
    """Body for the compiled-file export endpoints.

    ``latex_source`` is the current PRD document as held by the frontend store
    (a standalone LaTeX document). ``version``/``project_name`` only shape the
    suggested download filename.
    """

    latex_source: str = Field(..., description="Full LaTeX PRD document source.")
    version: Optional[int] = Field(None, ge=1, description="PRD version for the filename.")
    project_name: Optional[str] = Field(None, description="Project name for the filename.")


def _safe_filename_stem(project_id: UUID, payload: LatexExportPayload) -> str:
    name = (payload.project_name or "").strip()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", name)[:48].strip("-") if name else str(project_id)[:8]
    version_part = f"-V{payload.version}" if payload.version else ""
    return f"PRD-{stem}{version_part or ''}"


async def _export_prd_bytes(
    project_id: str,
    payload: LatexExportPayload,
    db: AsyncSession,
    fmt: str,
) -> Response:
    """Shared body of both file exports: validate, compile off-loop, respond.

    Blocking subprocess work runs in a worker thread so the event loop (and the
    SSE stream other tabs hold open) is never stalled by a slow TeX compile.
    """
    project = await ProjectRepository.get_by_id(str(project_id), db)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    source = (payload.latex_source or "").strip()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No PRD content was supplied to export.",
        )

    # Exporting BEFORE the first PRD has been generated: the frontend store
    # still holds the blank Markdown skeleton served by GET /api/prd/template
    # (preloaded into prdMarkdown on mount). Substitute the OFFICIAL Krungsri
    # Nimble LaTeX template so the downloaded file is the real branded blank
    # PRD instead of a plain-GFM rendering of the skeleton (or, before the
    # classification fix, a 502 compile failure).
    if source == load_prd_template().strip():
        source = load_prd_latex_template()

    # The PRD store holds LaTeX (Krungsri .tex template) for documents generated
    # after the LaTeX switch, and plain GFM Markdown for older ones. Both are
    # exportable: LaTeX goes through the native DOCX renderer (PDF: rendered
    # from that DOCX by LibreOffice) and Markdown through Pandoc's GFM readers.
    is_markdown = is_markdown_prd(source)

    # PDF exports render the SAME Word document the DOCX export produces, so
    # both downloads always match. This matters because the TeX pipeline drops
    # every Thai glyph (its fonts have no Thai coverage) and fails hard on LLM
    # LaTeX mistakes, while the Word renderer handles full Unicode and
    # degrades gracefully. Hosts without LibreOffice keep the historical TeX
    # PDF pipelines unchanged.
    soffice_ok: Optional[bool] = None

    def _soffice_reachable() -> bool:
        nonlocal soffice_ok
        if soffice_ok is None:
            soffice_ok = soffice_available()
        return soffice_ok

    def _pdf_via_docx(src: str, markdown_reader: bool) -> bytes:
        """PDF via the Word pipeline, with the TeX pipelines as fallback."""
        if _soffice_reachable():
            build = convert_markdown_to_docx if markdown_reader else convert_latex_to_docx
            try:
                return docx_to_pdf(build(src))
            except RuntimeError as soffice_err:
                logger.warning(
                    "DOCX->PDF conversion failed for project %s (%s); "
                    "retrying via the TeX PDF pipeline.",
                    project_id, soffice_err,
                )
        return convert_markdown_to_pdf(src) if markdown_reader else compile_latex_to_pdf(src)

    try:
        if fmt == "pdf":
            data = await asyncio.to_thread(_pdf_via_docx, source, is_markdown)
        elif is_markdown:
            data = await asyncio.to_thread(convert_markdown_to_docx, source)
        else:
            data = await asyncio.to_thread(convert_latex_to_docx, source)
    except RuntimeError as compile_err:
        # Defense in depth: a source classified as LaTeX (it carried strong
        # \begin{...}/\documentclass markers) can still be MOSTLY Markdown —
        # e.g. a legacy PRD containing a fenced ```latex block. One retry
        # through the Markdown pipeline beats an opaque 502 for the user.
        if not is_markdown and has_markdown_structure(source):
            logger.warning(
                "LaTeX export failed for project %s (%s) (%s); "
                "retrying via the Markdown pipeline.",
                project_id, fmt, compile_err,
            )
            if fmt == "pdf":
                retry_fn = lambda: _pdf_via_docx(source, True)  # noqa: E731
            else:
                retry_fn = convert_markdown_to_docx
            try:
                data = await asyncio.to_thread(retry_fn, source)
            except FileNotFoundError as err:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(err),
                ) from err
            except ValueError as err:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err),
                ) from err
            except RuntimeError as err:
                logger.error("Markdown retry export failed for project %s (%s): %s", project_id, fmt, err)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail=str(err),
                ) from err
        else:
            logger.error("LaTeX export failed for project %s (%s): %s", project_id, fmt, compile_err)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(compile_err),
            ) from compile_err
    except FileNotFoundError as err:
        # Toolchain not installed/reachable on this host.
        logger.error("LaTeX export toolchain missing: %s", err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(err),
        ) from err
    except ValueError as err:
        # Empty / unusable source.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err

    media_type = "application/pdf" if fmt == "pdf" else (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    stem = _safe_filename_stem(UUID(project_id), payload)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{stem}.{fmt}"'},
    )


@router.post("/api/project/{project_id}/export/pdf", status_code=status.HTTP_200_OK)
async def export_prd_pdf(
    project_id: str,
    payload: LatexExportPayload,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Compiles the supplied LaTeX PRD into a downloadable PDF via Tectonic.

    The PRD source follows prompts/template-krungsrinimble.tex - this endpoint
    renders THAT LaTeX, it does not re-parse Markdown.

    Returns:
        Response: application/pdf attachment.

    Raises:
        HTTPException: 404 unknown project; 422 empty/legacy-Markdown source;
            502 TeX compile failure; 503 toolchain unavailable.
    """
    return await _export_prd_bytes(project_id, payload, db, "pdf")


@router.post("/api/project/{project_id}/export/docx", status_code=status.HTTP_200_OK)
async def export_prd_docx(
    project_id: str,
    payload: LatexExportPayload,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Converts the supplied LaTeX PRD into a downloadable Word document via Pandoc.

    Returns:
        Response: .docx attachment converted from the Krungsri Nimble LaTeX.

    Raises:
        HTTPException: same contract as the PDF endpoint.
    """
    return await _export_prd_bytes(project_id, payload, db, "docx")


@router.post("/api/prd/convert", status_code=status.HTTP_200_OK)
async def convert_prd_to_markdown(payload: LatexExportPayload) -> Dict[str, str]:
    """
    Normalize a stored PRD into GFM Markdown for the on-screen preview.

    Accepts either the Krungsri LaTeX body produced by the Architect agent or a
    legacy Markdown PRD and returns clean GFM Markdown (pipe tables, ``### ``
    section headings) that the frontend markdown renderer can display directly,
    so raw LaTeX never leaks into the PRD panel.

    Returns:
        Dict[str, str]: ``{"markdown": <converted document>, "source_kind":
        "latex" | "markdown"}``.

    Raises:
        HTTPException: 422 when no usable content was supplied.
    """
    source = (payload.latex_source or "").strip()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No PRD content was supplied to convert.",
        )
    source_kind = "markdown" if is_markdown_prd(source) else "latex"
    try:
        markdown = await asyncio.to_thread(prd_to_markdown, source)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err
    except RuntimeError as err:
        logger.error("PRD preview conversion failed: %s", err)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(err),
        ) from err
    return {"markdown": markdown, "source_kind": source_kind}


# ==========================================
# PRD VERSION HISTORY API
# ==========================================

@router.get("/api/project/{project_id}/prd-versions", response_model=List[PRDVersionResponse], status_code=status.HTTP_200_OK)
async def get_prd_versions(project_id: str, session: AsyncSession = Depends(get_db)) -> List[PRDVersionResponse]:
    """
    Retrieves all PRD versions for a project.

    Args:
        project_id: Project UUID string.
        session: Active asynchronous database session.

    Returns:
        List[PRDVersionResponse]: Immutable PRD version records, newest first.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    versions = await PRDVersionRepository.get_by_project(project_id, session)
    return versions


@router.get("/api/project/{project_id}/prd-versions/latest", response_model=PRDVersionResponse, status_code=status.HTTP_200_OK)
async def get_latest_prd_version(project_id: str, session: AsyncSession = Depends(get_db)) -> PRDVersionResponse:
    """
    Retrieves the latest PRD version for a project.

    Args:
        project_id: Project UUID string.
        session: Active asynchronous database session.

    Returns:
        PRDVersionResponse: The most recent immutable PRD version record.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID; 404 if no
            PRD versions exist for the project.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    version = await PRDVersionRepository.get_latest(project_id, session)
    if not version:
        raise HTTPException(status_code=404, detail="No PRD versions found for this project")
    return version


@router.get("/api/project/{project_id}/prd-versions/{version_number}", response_model=PRDVersionResponse, status_code=status.HTTP_200_OK)
async def get_prd_version_by_number(project_id: str, version_number: int, session: AsyncSession = Depends(get_db)) -> PRDVersionResponse:
    """
    Retrieves a specific PRD version by version number.

    Args:
        project_id: Project UUID string.
        version_number: Monotonic PRD version number.
        session: Active asynchronous database session.

    Returns:
        PRDVersionResponse: The requested immutable PRD version record.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID; 404 if the
            requested version does not exist for the project.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    version = await PRDVersionRepository.get_by_version_number(project_id, version_number, session)
    if not version:
        raise HTTPException(status_code=404, detail=f"PRD version {version_number} not found for this project")
    return version