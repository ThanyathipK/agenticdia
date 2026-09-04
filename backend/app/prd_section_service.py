"""
PRD section service — the PRD as a collection of editable, lockable, versioned
PARTS.

The official Krungsri Nimble PRD always renders as the SAME nine parts in the
preview (cover, stakeholders, version history, reviews, contents, 1. business
& strategic overview, 2. product scope, 3. technical & operational, 4.
appendix). This module:

  - defines those canonical parts (:data:`CANONICAL_PRD_SECTIONS`),
  - splits a full PRD markdown document into those parts
    (:func:`split_markdown_sections`) using the EXACT same rules as the
    frontend ``parsePRDToSections`` (``src/utils/markdown.ts``), so a
    ``section_key`` always identifies the same part the user sees,
  - seeds the ``prd_sections`` table for a project on first access
    (:func:`ensure_sections_seeded`),
  - syncs a freshly generated (LaTeX or markdown) PRD into the table while
    PRESERVING human-owned / locked sections (:func:`sync_sections_from_prd`),
  - stitches the stored parts back into the full document
    (:func:`assemble_document_markdown`).

Section content is always stored as MARKDOWN (the preview/human-editing
format). LaTeX sources are normalized via ``latex_service.prd_to_markdown``
before splitting; markdown sources pass through untouched.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.prd_section import PRDSectionRepository

logger = logging.getLogger(__name__)

# The nine canonical PRD parts, in document order. ``section_key`` values match
# the ids produced by the frontend ``parsePRDToSections`` one-to-one:
#   - the cover/front-matter block before the first heading gets id "title"
#   - 'contents' is born locked: it is derived structure nobody edits
#   - 'reviews' is human-only (signatures/dates) — the AI never generates it
CANONICAL_PRD_SECTIONS: List[Dict[str, Any]] = [
    {"section_key": "title", "title": "Cover & Document Information", "section_order": 1,
     "content_source": "template", "ai_generatable": True, "is_locked": False},
    {"section_key": "stakeholders", "title": "Stakeholders", "section_order": 2,
     "content_source": "ai", "ai_generatable": True, "is_locked": False},
    {"section_key": "version_history", "title": "Version History", "section_order": 3,
     "content_source": "template", "ai_generatable": True, "is_locked": False},
    {"section_key": "reviews", "title": "Reviews", "section_order": 4,
     "content_source": "human", "ai_generatable": False, "is_locked": False},
    {"section_key": "contents", "title": "Contents", "section_order": 5,
     "content_source": "template", "ai_generatable": False, "is_locked": True},
    {"section_key": "business_overview", "title": "1. Business & Strategic Overview", "section_order": 6,
     "content_source": "ai", "ai_generatable": True, "is_locked": False},
    {"section_key": "product_scope", "title": "2. Product Scope & Functional Requirements", "section_order": 7,
     "content_source": "ai", "ai_generatable": True, "is_locked": False},
    {"section_key": "tech_ops", "title": "3. Technical & Operational Considerations", "section_order": 8,
     "content_source": "ai", "ai_generatable": True, "is_locked": False},
    {"section_key": "appendix", "title": "4. Appendix", "section_order": 9,
     "content_source": "ai", "ai_generatable": True, "is_locked": False},
]

CANONICAL_KEYS = {c["section_key"] for c in CANONICAL_PRD_SECTIONS}

VALID_REVIEW_STATUSES = {"draft", "satisfied", "approved"}


def _derive_section_key(title: str) -> str:
    """Derive a stable section key from a heading — a 1:1 port of the keyword
    mapping in ``src/utils/markdown.ts::parsePRDToSections``."""
    t = title.lower()
    if "executive summary" in t:
        return "exec_summary"
    if "technical architecture" in t or "technical infrastructure" in t or "technical constraints" in t:
        return "tech_arch"
    if "scope of requirements" in t or "user stories" in t:
        return "user_stories"
    if "stakeholder" in t:
        return "stakeholders"
    if "version history" in t:
        return "version_history"
    if "review" in t:
        return "reviews"
    if "contents" in t:
        return "contents"
    if "business & strategic" in t:
        return "business_overview"
    if "product scope" in t or "functional requirement" in t:
        return "product_scope"
    if "technical & operational" in t:
        return "tech_ops"
    if "appendix" in t:
        return "appendix"
    key = re.sub(r"\*", "", t)
    key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    return key or "section"


def split_markdown_sections(markdown: str) -> List[Dict[str, str]]:
    """Split a full PRD markdown document into its parts.

    Mirrors the frontend splitter: boundaries are '## ' and '### ' headings,
    the block before the first heading is the 'title' (cover) part, and each
    part's content INCLUDES its heading line so stitching is lossless.
    """
    if not markdown or not markdown.strip():
        return []

    parts: List[Dict[str, str]] = []
    current_key = "title"
    current_title = "Product Requirement Document"
    current_lines: List[str] = []

    for line in markdown.split("\n"):
        trimmed = line.strip()
        if trimmed.startswith("## ") or trimmed.startswith("### "):
            parts.append({
                "section_key": current_key,
                "title": current_title,
                "content": "\n".join(current_lines).strip(),
            })
            title = re.sub(r"^#{2,3}\s+", "", trimmed).strip()
            current_title = title
            current_key = _derive_section_key(title)
            current_lines = [line]
        else:
            current_lines.append(line)

    parts.append({
        "section_key": current_key,
        "title": current_title,
        "content": "\n".join(current_lines).strip(),
    })

    return [p for p in parts if p["content"] != "" or p["section_key"] == "title"]


def stitch_markdown(sections: List[Dict[str, Any]]) -> str:
    """Assemble the full PRD markdown from ordered section rows (same join
    rule as the frontend ``stitchSectionsToPRD``)."""
    ordered = sorted(
        sections,
        key=lambda s: (s.get("section_order", 0) or 0, s.get("created_at") or ""),
    )
    return "\n\n".join((s.get("content") or "").strip() for s in ordered if s.get("content"))


def prd_is_sectioned_markdown(document: str) -> bool:
    """True when a stored PRD is the stitched markdown of the canonical parts.

    Used by the architect's early-exit guard: a document assembled from
    ``prd_sections`` is a valid current document even though it is no longer
    the raw LaTeX template body.
    """
    if not document:
        return False
    keys = {p["section_key"] for p in split_markdown_sections(document)}
    return len(keys & CANONICAL_KEYS) >= 7


async def assemble_document_markdown(project_id: str, session: AsyncSession) -> str:
    """Stitch the project's stored PRD sections into the full document."""
    sections = await PRDSectionRepository.get_by_project(project_id, session)
    return stitch_markdown(sections)


async def ensure_sections_seeded(
    project_id: str,
    session: AsyncSession,
    source_markdown: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Guarantee the project has its nine lockable PRD parts.

    Seeds ``prd_sections`` from ``source_markdown`` when provided (typically
    the project's current markdown PRD), otherwise from the official Krungsri
    ``prompts/template.md`` skeleton. No-op when sections already exist.
    """
    existing = await PRDSectionRepository.get_by_project(project_id, session)
    if existing:
        return existing

    source = (source_markdown or "").strip()
    if source:
        try:
            from app.latex_service import is_markdown_prd, prd_to_markdown
            if not is_markdown_prd(source):
                source = prd_to_markdown(source)
        except Exception as conv_err:  # pandoc missing etc. — fall back to the template
            logger.warning(
                "[PRD SECTIONS] Could not normalize seed source for project %s (%s); "
                "seeding from the official template instead.", project_id, conv_err,
            )
            source = ""

    if not source:
        # Seed from the SAME source the preview renders: the official LaTeX
        # template normalized to markdown (yields exactly the nine parts). If
        # the pandoc toolchain is unavailable, degrade to the markdown
        # skeleton (template.md).
        try:
            from app.latex_service import prd_to_markdown
            from app.prompt_loader import load_prd_latex_template
            source = prd_to_markdown(load_prd_latex_template())
        except Exception as tpl_err:
            logger.warning(
                "[PRD SECTIONS] LaTeX template normalization failed (%s); "
                "seeding from the markdown skeleton instead.", tpl_err,
            )
            from app.prompt_loader import load_prd_template
            source = load_prd_template()

    created: Dict[str, Dict[str, Any]] = {}
    for order, part in enumerate(split_markdown_sections(source), start=1):
        defaults = next(
            (c for c in CANONICAL_PRD_SECTIONS if c["section_key"] == part["section_key"]), None
        )
        row = await PRDSectionRepository.create(project_id, {
            "section_key": part["section_key"],
            "title": part["title"],
            "content": part["content"],
            "section_order": defaults["section_order"] if defaults else order,
            "content_source": defaults["content_source"] if defaults else "ai",
            "ai_generatable": defaults["ai_generatable"] if defaults else True,
            "is_locked": defaults["is_locked"] if defaults else False,
            "initial_changed_by": "system",
            "initial_change_summary": "Seeded from the official Krungsri template.",
        }, session)
        created[row["section_key"]] = row

    # Also materialize canonical parts the source document lacks, so the
    # caller always gets the full nine-part skeleton to edit and lock.
    for defaults in CANONICAL_PRD_SECTIONS:
        if defaults["section_key"] in created:
            continue
        row = await PRDSectionRepository.create(project_id, {
            **defaults,
            "content": "",
            "initial_changed_by": "system",
            "initial_change_summary": "Placeholder for a missing template part.",
        }, session)
        created[row["section_key"]] = row

    logger.info("[PRD SECTIONS] Seeded %d sections for project %s", len(created), project_id)
    return await PRDSectionRepository.get_by_project(project_id, session)


async def sync_sections_from_prd(
    project_id: str,
    prd_markdown: str,
    session: AsyncSession,
    *,
    changed_by: str = "automated_agent",
) -> Optional[str]:
    """
    Merge a freshly generated PRD into the project's stored sections.

    Rules (the human/AI ownership contract):
      - a section that does not exist yet is created from the generated part;
      - an existing section is updated ONLY when it is NOT locked and
        ``ai_generatable`` is True — human-owned content and user-satisfied
        (locked) sections are NEVER touched by regeneration;
      - every actual content change appends a ``prd_section_versions`` row
        (append-only, nothing overwritten).

    Returns the stitched full markdown of ALL stored sections (so the caller
    can persist it as the current ``generated_prd``), or ``None`` when the
    source could not be normalized (e.g. pandoc unavailable) — in which case
    the caller must keep the previous document untouched.
    """
    source = (prd_markdown or "").strip()
    if not source:
        return None

    try:
        from app.latex_service import prd_to_markdown
        markdown = prd_to_markdown(source)
    except Exception as conv_err:
        logger.warning(
            "[PRD SECTIONS] Could not normalize generated PRD for project %s (%s); "
            "sections left untouched.", project_id, conv_err,
        )
        return None

    parts = split_markdown_sections(markdown)
    if not parts:
        return None

    existing = {
        s["section_key"]: s
        for s in await PRDSectionRepository.get_by_project(project_id, session)
    }

    for order, part in enumerate(parts, start=1):
        row = existing.get(part["section_key"])
        if row is None:
            defaults = next(
                (c for c in CANONICAL_PRD_SECTIONS if c["section_key"] == part["section_key"]), None
            )
            created = await PRDSectionRepository.create(project_id, {
                "section_key": part["section_key"],
                "title": part["title"],
                "content": part["content"],
                "section_order": defaults["section_order"] if defaults else order,
                "content_source": defaults["content_source"] if defaults else "ai",
                "ai_generatable": defaults["ai_generatable"] if defaults else True,
                "is_locked": defaults["is_locked"] if defaults else False,
                "initial_changed_by": changed_by,
                "initial_change_summary": "Generated by the Architect agent.",
            }, session)
            existing[created["section_key"]] = created
        elif (
            not row.get("is_locked")
            and row.get("ai_generatable", True)
            and (row.get("content") or "") != part["content"]
        ):
            updated = await PRDSectionRepository.update_content(
                row["id"], project_id, part["content"], session,
                changed_by=changed_by,
                change_summary="Regenerated by the Architect agent.",
            )
            if updated:
                existing[updated["section_key"]] = updated

    stitched = stitch_markdown(list(existing.values()))
    logger.info(
        "[PRD SECTIONS] Synced %d generated parts into %d stored sections for project %s",
        len(parts), len(existing), project_id,
    )
    return stitched