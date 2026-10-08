"""Project health, immutable audit history, and waiver lifecycle tests."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.audit_history_service import create_waiver, list_audit_runs, list_waivers, record_audit_run, revoke_waiver
from app.models import ProjectModel, RequirementModel, UserModel
from app.project_health_service import build_project_health
from tests.test_documents import db_session, seeded_project


def _audit(findings, version=1):
    return {
        "audit_version_reviewed": version,
        "is_valid": not findings,
        "verdict": "pass" if not findings else "pass_with_warnings",
        "findings": findings,
        "passed_checks": [],
        "failed_checks": [],
        "checklist_id": "banking-core",
        "checklist_version": "1.0.0",
    }


def _finding():
    return {
        "rule_id": "BANK-READINESS-001",
        "finding_type": "missing",
        "category": "Readiness",
        "target_requirement_id": "REQ-001",
        "description": "Success metric is missing.",
        "impact": "warning",
    }


@pytest.mark.asyncio
async def test_audit_run_comparison_detects_resolved_and_reopened(db_session, seeded_project):
    first = await record_audit_run(seeded_project, _audit([_finding()], 1), db_session)
    second = await record_audit_run(seeded_project, _audit([], 2), db_session)
    third = await record_audit_run(seeded_project, _audit([_finding()], 3), db_session)

    key = "BANK-READINESS-001|REQ-001|missing"
    assert first.comparison["new"] == [key]
    assert second.comparison["resolved"] == [key]
    assert third.comparison["reopened"] == [key]

    history = await list_audit_runs(seeded_project, db_session)
    assert history[0]["findings"][0]["lifecycle"] == "reopened"


@pytest.mark.asyncio
async def test_waiver_create_expire_filter_and_revoke(db_session, seeded_project):
    project = await db_session.scalar(select(ProjectModel).where(ProjectModel.id == seeded_project))
    user = await db_session.scalar(select(UserModel).where(UserModel.id == project.user_id))
    waiver = await create_waiver(
        seeded_project,
        db_session,
        rule_id="BANK-READINESS-001",
        target_requirement_id="REQ-001",
        reason="Accepted until the next delivery gate.",
        compensating_control="Weekly manual review.",
        owner="Product Owner",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        approver_id=str(user.id),
        approver_name=user.full_name,
    )
    assert len(await list_waivers(seeded_project, db_session, include_inactive=False)) == 1
    revoked = await revoke_waiver(seeded_project, waiver["id"], "No longer required.", db_session)
    assert revoked["status"] == "revoked"
    assert await list_waivers(seeded_project, db_session, include_inactive=False) == []


@pytest.mark.asyncio
async def test_project_health_returns_actionable_traceability_gaps(db_session, seeded_project):
    db_session.add(RequirementModel(
        project_id=seeded_project,
        requirement_code="REQ-001",
        title="Uncovered requirement",
        status="active",
    ))
    await db_session.flush()
    health = await build_project_health(seeded_project, db_session)
    kinds = {issue["kind"] for issue in health["issues"]}
    assert health["coverage_percent"] == 0
    assert "missing_stories" in kinds
    assert "missing_sections" in kinds
    assert "missing_diagrams" in kinds
    assert health["metrics"]["requirements_without_diagram"] == 1
