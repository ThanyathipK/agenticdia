"""
Tests for the part-level PRD system: prd_sections + prd_section_versions.

Covers:
  - split_markdown_sections: the official template.md yields exactly the nine
    canonical parts with the same keys the frontend preview produces
  - ensure_sections_seeded: seeds the nine lockable parts, 'contents' born locked
  - update_content: appends an immutable version row on every change
  - lock enforcement: a locked part refuses edits (ArtifactLockError)
  - sync_sections_from_prd: locked / human-owned parts are PRESERVED across
    regeneration; unlocked AI parts are refreshed; the stitched markdown keeps
    both
  - prd_is_sectioned_markdown: the architect early-exit guard helper

Run from the ``backend`` directory::

    ../venv/bin/python -m pytest tests/test_prd_sections.py -v
"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.lock_service import ArtifactLockError, LockService
from app.models import PRDSectionModel, ProjectModel, UserModel
from app.prd_section_service import (
    CANONICAL_KEYS,
    CANONICAL_PRD_SECTIONS,
    assemble_document_markdown,
    ensure_sections_seeded,
    prd_is_sectioned_markdown,
    split_markdown_sections,
    stitch_markdown,
    sync_sections_from_prd,
)
from app.repositories.prd_section import (
    PRDSectionRepository,
    PRDSectionVersionRepository,
)


# =====================================================================
# Database plumbing: real async SQLite in-memory schema
# =====================================================================
@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        # Seed one user + one project to satisfy the FK chain.
        user = UserModel(
            email="ba@example.com",
            full_name="Product Owner",
            role="product_owner",
        )
        session.add(user)
        await session.flush()
        project = ProjectModel(
            user_id=user.id,
            name="PromptPay Refund Portal",
            industry_standard="Krungsri Nimble Baseline",
        )
        session.add(project)
        await session.flush()
        yield session, str(project.id)

    await engine.dispose()


def _markdown_prd() -> str:
    """A minimal but structurally complete PRD markdown — the same nine-part
    structure the pandoc-normalized LaTeX template produces (cover block has
    NO '## ' heading; only '### ' section boundaries)."""
    return "\n".join([
        "PRODUCT REQUIREMENT",
        "",
        "Nimble by Krungsri",
        "",
        "PMO No: PMO-1234",
        "",
        "### Stakeholders",
        "",
        "|Role|Name|",
        "|---|---|",
        "|Product Owner||",
        "",
        "### Version History",
        "",
        "|Version|Date|Author|Description|",
        "|---|---|---|---|",
        "|V1.0||||",
        "",
        "### Reviews",
        "",
        "|Role|Name|Signature|Date|",
        "|---|---|---|---|",
        "|Product Owner||||",
        "",
        "### **Contents**",
        "",
        "1. Business & Strategic Overview",
        "",
        "### 1. Business & Strategic Overview",
        "",
        "|Problem Statement|1. Slow refunds|",
        "",
        "### 2. Product Scope & Functional Requirements",
        "",
        "|User Story||||",
        "",
        "### 3. Technical & Operational Considerations",
        "",
        "|Non-Functional Requirements|1. Performance|",
        "",
        "### 4. Appendix",
        "",
        "|Open Questions & Risks|1.||",
    ])


# =====================================================================
# Splitter
# =====================================================================
class TestSplitMarkdownSections:
    def test_template_yields_the_nine_canonical_parts(self):
        # The SAME source the preview renders: the official LaTeX template
        # normalized to markdown (pandoc), then split with the production rules.
        from app.latex_service import prd_to_markdown
        from app.prompt_loader import load_prd_latex_template
        parts = split_markdown_sections(prd_to_markdown(load_prd_latex_template()))
        keys = [p["section_key"] for p in parts]
        assert keys == [c["section_key"] for c in CANONICAL_PRD_SECTIONS]
        assert len(keys) == 9

    def test_parts_include_their_heading_line(self):
        parts = split_markdown_sections(_markdown_prd())
        stakeholders = next(p for p in parts if p["section_key"] == "stakeholders")
        assert stakeholders["content"].startswith("### Stakeholders")

    def test_content_before_first_heading_is_the_title_part(self):
        parts = split_markdown_sections(_markdown_prd())
        assert parts[0]["section_key"] == "title"
        assert "PRODUCT REQUIREMENT" in parts[0]["content"]

    def test_stitch_roundtrip_is_lossless(self):
        source = _markdown_prd()
        stitched = stitch_markdown(split_markdown_sections(source))
        assert stitched.strip() == source.strip()

    def test_empty_and_latex_input(self):
        assert split_markdown_sections("") == []
        # LaTeX has no markdown headings: one undifferentiated block, not a crash.
        latex_parts = split_markdown_sections("\\section*{Stakeholders}\nbody")
        assert len(latex_parts) == 1
        assert latex_parts[0]["section_key"] == "title"


# =====================================================================
# Seeding + repository behavior (real SQLite)
# =====================================================================
class TestSeedingAndRepository:
    @pytest.mark.asyncio
    async def test_seed_creates_nine_parts_with_version_one(self, db_session):
        session, project_id = db_session
        sections = await ensure_sections_seeded(project_id, session)
        assert len(sections) == 9
        assert {s["section_key"] for s in sections} == CANONICAL_KEYS
        for s in sections:
            assert s["version_number"] == 1
        contents = next(s for s in sections if s["section_key"] == "contents")
        assert contents["is_locked"] is True  # derived structure — born locked
        reviews = next(s for s in sections if s["section_key"] == "reviews")
        assert reviews["ai_generatable"] is False  # human-only part

    @pytest.mark.asyncio
    async def test_seed_is_idempotent(self, db_session):
        session, project_id = db_session
        first = await ensure_sections_seeded(project_id, session)
        second = await ensure_sections_seeded(project_id, session)
        assert len(second) == len(first) == 9

    @pytest.mark.asyncio
    async def test_update_content_appends_versions_never_overwrites(self, db_session):
        session, project_id = db_session
        await ensure_sections_seeded(project_id, session)
        section = await PRDSectionRepository.get_by_key("stakeholders", project_id, session)

        first = await PRDSectionRepository.update_content(
            section["id"], project_id, "### Stakeholders\n\nv2 content", session,
            changed_by="user", change_summary="manual edit",
        )
        second = await PRDSectionRepository.update_content(
            section["id"], project_id, "### Stakeholders\n\nv3 content", session,
            changed_by="user", change_summary="another edit",
        )
        assert first["version_number"] == 2
        assert second["version_number"] == 3

        history = await PRDSectionVersionRepository.get_by_section(section["id"], session)
        numbers = [v["version_number"] for v in history]
        assert numbers == [3, 2, 1]  # newest first, all preserved
        assert history[2]["content"] == section["content"]  # original kept

    @pytest.mark.asyncio
    async def test_locked_section_refuses_edits(self, db_session):
        session, project_id = db_session
        await ensure_sections_seeded(project_id, session)
        section = await PRDSectionRepository.get_by_key("stakeholders", project_id, session)
        await LockService.lock_artifact(
            "prd_section", section["id"], session, locked_by="user", project_id=project_id
        )
        with pytest.raises(ArtifactLockError):
            await PRDSectionRepository.update_content(
                section["id"], project_id, "### Stakeholders\n\nhacked", session
            )
        # The stored content is untouched.
        after = await PRDSectionRepository.get_by_key("stakeholders", project_id, session)
        assert after["content"] == section["content"]

    @pytest.mark.asyncio
    async def test_locked_section_via_generic_lock_status(self, db_session):
        """prd_section participates in the generic LockService contract."""
        session, project_id = db_session
        await ensure_sections_seeded(project_id, session)
        section = await PRDSectionRepository.get_by_key("reviews", project_id, session)
        info = await LockService.lock_artifact(
            "prd_section", section["id"], session,
            locked_by="user", lock_reason="sign-off received", project_id=project_id,
        )
        assert info["is_locked"] is True
        assert info["lock_reason"] == "sign-off received"
        status = await LockService.get_lock_status(
            "prd_section", section["id"], session, project_id=project_id
        )
        assert status["is_locked"] is True

    @pytest.mark.asyncio
    async def test_unlock_artifact(self, db_session):
        session, project_id = db_session
        await ensure_sections_seeded(project_id, session)
        section = await PRDSectionRepository.get_by_key("reviews", project_id, session)
        await LockService.lock_artifact(
            "prd_section", section["id"], session,
            locked_by="user", lock_reason="sign-off received", project_id=project_id,
        )
        info = await LockService.unlock_artifact(
            "prd_section", section["id"], session,
            unlocked_by="user", project_id=project_id,
        )
        assert info["is_locked"] is False
        status = await LockService.get_lock_status(
            "prd_section", section["id"], session, project_id=project_id
        )
        assert status["is_locked"] is False

    @pytest.mark.asyncio
    async def test_born_locked_section_with_no_lock_owner_is_unlockable(self, db_session):
        """Regression: 'contents' is seeded is_locked=True with locked_by=NULL
        (system-derived structure). The unlock ownership check used to treat
        that NULL as a DIFFERENT owner and answered 403 Forbidden forever.
        A lock with no recorded owner is not held by any user, so any
        requester may clear it."""
        session, project_id = db_session
        await ensure_sections_seeded(project_id, session)
        contents = await PRDSectionRepository.get_by_key("contents", project_id, session)
        assert contents["is_locked"] is True
        assert contents["locked_by"] is None

        info = await LockService.unlock_artifact(
            "prd_section", contents["id"], session,
            unlocked_by="user", project_id=project_id,
        )
        assert info["is_locked"] is False
        after = await PRDSectionRepository.get_by_key("contents", project_id, session)
        assert after["is_locked"] is False

    @pytest.mark.asyncio
    async def test_unlock_denied_while_another_user_holds_the_lock(self, db_session):
        """The guard must keep protecting locks actually held by someone else."""
        session, project_id = db_session
        await ensure_sections_seeded(project_id, session)
        stakeholders = await PRDSectionRepository.get_by_key("stakeholders", project_id, session)
        await LockService.lock_artifact(
            "prd_section", stakeholders["id"], session,
            locked_by="alice", project_id=project_id,
        )
        with pytest.raises(PermissionError):
            await LockService.unlock_artifact(
                "prd_section", stakeholders["id"], session,
                unlocked_by="bob", project_id=project_id,
            )
        # ...and the lock survives the denied attempt.
        after = await PRDSectionRepository.get_by_key("stakeholders", project_id, session)
        assert after["is_locked"] is True
        assert after["locked_by"] == "alice"



# =====================================================================
# AI regeneration ownership contract (sync_sections_from_prd)
# =====================================================================
class TestSyncSectionsFromPrd:
    @pytest.mark.asyncio
    async def test_locked_and_human_parts_survive_regeneration(self, db_session):
        session, project_id = db_session
        await ensure_sections_seeded(project_id, session, source_markdown=_markdown_prd())

        # User fills in the human-only Reviews part and LOCKS the stakeholders part.
        reviews = await PRDSectionRepository.get_by_key("reviews", project_id, session)
        await PRDSectionRepository.update_content(
            reviews["id"], project_id,
            "### Reviews\n\n|Role|Name|Signature|Date|\n|---|---|---|---|\n|Product Owner|Ann|signed|2026-09-04|",
            session, changed_by="user",
        )
        stakeholders = await PRDSectionRepository.get_by_key("stakeholders", project_id, session)
        await PRDSectionRepository.update_content(
            stakeholders["id"], project_id,
            "### Stakeholders\n\n|Role|Name|\n|---|---|\n|Product Owner|Ann Person|",
            session, changed_by="user",
        )
        await LockService.lock_artifact(
            "prd_section", stakeholders["id"], session,
            locked_by="user", project_id=project_id,
        )

        # AI "regenerates" the document with different stakeholder / review content.
        regenerated = _markdown_prd().replace(
            "|Product Owner||", "|Product Owner|AI INVENTED|"
        )
        merged = await sync_sections_from_prd(project_id, regenerated, session)

        assert merged is not None
        assert "AI INVENTED" not in merged  # locked part untouched
        assert "signed" in merged  # human-only part untouched
        after = await PRDSectionRepository.get_by_key("stakeholders", project_id, session)
        assert "Ann Person" in after["content"]

    @pytest.mark.asyncio
    async def test_unlocked_ai_parts_are_refreshed_and_versioned(self, db_session):
        session, project_id = db_session
        await ensure_sections_seeded(project_id, session, source_markdown=_markdown_prd())
        appendix = await PRDSectionRepository.get_by_key("appendix", project_id, session)
        assert appendix["version_number"] == 1

        regenerated = _markdown_prd().replace(
            "|Open Questions & Risks|1.||",
            "|Open Questions & Risks|1. Latency SLO undefined||",
        )
        merged = await sync_sections_from_prd(project_id, regenerated, session)
        assert merged is not None
        assert "Latency SLO undefined" in merged

        after = await PRDSectionRepository.get_by_key("appendix", project_id, session)
        assert after["version_number"] == 2  # content changed => new version row
        history = await PRDSectionVersionRepository.get_by_section(after["id"], session)
        assert history[0]["changed_by"] == "automated_agent"
        # v1 (the seed content) is still there — nothing overwritten.
        assert history[-1]["content"] == appendix["content"]

    @pytest.mark.asyncio
    async def test_unchanged_parts_get_no_version_row(self, db_session):
        session, project_id = db_session
        source = _markdown_prd()
        await ensure_sections_seeded(project_id, session, source_markdown=source)
        before = {s["section_key"]: s["version_number"]
                  for s in await PRDSectionRepository.get_by_project(project_id, session)}
        merged = await sync_sections_from_prd(project_id, source, session)
        assert merged is not None
        after = {s["section_key"]: s["version_number"]
                 for s in await PRDSectionRepository.get_by_project(project_id, session)}
        assert before == after  # identical content => no new versions

    @pytest.mark.asyncio
    async def test_sync_preserves_stitched_document(self, db_session):
        session, project_id = db_session
        source = _markdown_prd()
        await ensure_sections_seeded(project_id, session, source_markdown=source)
        merged = await sync_sections_from_prd(project_id, source, session)
        assert merged is not None
        # The stitched document round-trips through the splitter unchanged.
        assert merged.strip() == source.strip()

    @pytest.mark.asyncio
    async def test_sync_on_empty_project_creates_parts(self, db_session):
        session, project_id = db_session
        merged = await sync_sections_from_prd(project_id, _markdown_prd(), session)
        assert merged is not None
        sections = await PRDSectionRepository.get_by_project(project_id, session)
        assert {s["section_key"] for s in sections} == CANONICAL_KEYS


# =====================================================================
# Architect early-exit guard helper
# =====================================================================
class TestPrdIsSectionedMarkdown:
    def test_stitched_document_is_recognized(self):
        assert prd_is_sectioned_markdown(_markdown_prd()) is True

    def test_latex_document_is_not(self):
        assert prd_is_sectioned_markdown(
            "\\documentclass{article}\n\\section*{Stakeholders}\nbody"
        ) is False

    def test_empty_is_not(self):
        assert prd_is_sectioned_markdown("") is False
        assert prd_is_sectioned_markdown(None) is False  # type: ignore[arg-type]