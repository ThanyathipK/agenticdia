"""Immutable audit history, finding lifecycle comparison, and waivers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditRunModel, AuditWaiverModel
from app.repositories.base import as_uuid


def finding_key(finding: dict[str, Any]) -> str:
    return "|".join((
        str(finding.get("rule_id") or "ADHOC").upper(),
        str(finding.get("target_requirement_id") or "PROJECT").upper(),
        str(finding.get("finding_type") or "unknown").lower(),
    ))


async def record_audit_run(project_id: str, audit: dict[str, Any], session: AsyncSession) -> AuditRunModel:
    pid = as_uuid(project_id)
    history = (
        await session.execute(
            select(AuditRunModel)
            .where(AuditRunModel.project_id == pid)
            .order_by(AuditRunModel.run_number.desc())
        )
    ).scalars().all()
    previous = history[0] if history else None
    current_findings = [item for item in (audit.get("findings") or []) if isinstance(item, dict)]
    current_keys = {finding_key(item) for item in current_findings}
    previous_keys = {finding_key(item) for item in (previous.findings or [])} if previous else set()
    historical_keys = {
        finding_key(item)
        for run in history
        for item in (run.findings or [])
        if isinstance(item, dict)
    }
    comparison = {
        "new": sorted(current_keys - historical_keys),
        "reopened": sorted((current_keys & historical_keys) - previous_keys),
        "unchanged": sorted(current_keys & previous_keys),
        "resolved": sorted(previous_keys - current_keys),
    }
    run = AuditRunModel(
        project_id=pid,
        audit_result_id=as_uuid(audit["id"]) if audit.get("id") else None,
        run_number=(history[0].run_number + 1) if history else 1,
        audit_version_reviewed=int(audit.get("audit_version_reviewed") or 1),
        is_valid=bool(audit.get("is_valid")),
        verdict=str(audit.get("verdict") or "needs_clarification"),
        findings=current_findings,
        passed_checks=audit.get("passed_checks") or [],
        failed_checks=audit.get("failed_checks") or [],
        source_references=audit.get("source_references") or [],
        project_context=audit.get("project_context") or {},
        checklist_id=str(audit.get("checklist_id") or "banking-core"),
        checklist_version=str(audit.get("checklist_version") or "1.0.0"),
        comparison=comparison,
    )
    session.add(run)
    await session.flush()
    await session.refresh(run)
    return run


async def list_audit_runs(project_id: str, session: AsyncSession) -> list[dict[str, Any]]:
    pid = as_uuid(project_id)
    runs = (
        await session.execute(
            select(AuditRunModel)
            .where(AuditRunModel.project_id == pid)
            .order_by(AuditRunModel.run_number.desc())
        )
    ).scalars().all()
    waivers = await list_waivers(project_id, session, include_inactive=False)
    waiver_keys = {(w["rule_id"], (w["target_requirement_id"] or "PROJECT").upper()): w for w in waivers}
    output = []
    for run in runs:
        findings = []
        for finding in run.findings or []:
            item = dict(finding)
            key = finding_key(item)
            rule_target = (
                str(item.get("rule_id") or "ADHOC").upper(),
                str(item.get("target_requirement_id") or "PROJECT").upper(),
            )
            item["finding_key"] = key
            item["lifecycle"] = next(
                (name for name in ("new", "reopened", "unchanged") if key in (run.comparison or {}).get(name, [])),
                "unchanged",
            )
            item["waiver"] = waiver_keys.get(rule_target) or waiver_keys.get((rule_target[0], "PROJECT"))
            findings.append(item)
        output.append({
            "id": str(run.id),
            "project_id": str(run.project_id),
            "run_number": run.run_number,
            "audit_version_reviewed": run.audit_version_reviewed,
            "is_valid": run.is_valid,
            "verdict": run.verdict,
            "findings": findings,
            "passed_checks": run.passed_checks or [],
            "failed_checks": run.failed_checks or [],
            "checklist_id": run.checklist_id,
            "checklist_version": run.checklist_version,
            "comparison": run.comparison or {},
            "created_at": run.created_at.isoformat() if run.created_at else None,
        })
    return output


async def create_waiver(
    project_id: str,
    session: AsyncSession,
    *,
    rule_id: str,
    target_requirement_id: Optional[str],
    reason: str,
    compensating_control: Optional[str],
    owner: str,
    expires_at: datetime,
    approver_id: str,
    approver_name: str,
) -> dict[str, Any]:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise ValueError("Waiver expiry must be in the future.")
    waiver = AuditWaiverModel(
        project_id=as_uuid(project_id),
        rule_id=rule_id.upper(),
        target_requirement_id=(target_requirement_id or "").upper() or None,
        reason=reason.strip(),
        compensating_control=(compensating_control or "").strip() or None,
        owner=owner.strip(),
        approved_by=as_uuid(approver_id),
        approved_by_name=approver_name,
        expires_at=expires_at,
        status="active",
    )
    session.add(waiver)
    await session.flush()
    await session.refresh(waiver)
    return _serialize_waiver(waiver)


async def list_waivers(project_id: str, session: AsyncSession, *, include_inactive: bool = True) -> list[dict[str, Any]]:
    stmt = select(AuditWaiverModel).where(AuditWaiverModel.project_id == as_uuid(project_id))
    if not include_inactive:
        stmt = stmt.where(
            AuditWaiverModel.status == "active",
            AuditWaiverModel.expires_at > datetime.now(timezone.utc),
        )
    rows = (await session.execute(stmt.order_by(AuditWaiverModel.created_at.desc()))).scalars().all()
    return [_serialize_waiver(row) for row in rows]


async def revoke_waiver(project_id: str, waiver_id: str, reason: str, session: AsyncSession) -> Optional[dict[str, Any]]:
    waiver = await session.scalar(
        select(AuditWaiverModel).where(
            AuditWaiverModel.id == as_uuid(waiver_id),
            AuditWaiverModel.project_id == as_uuid(project_id),
        )
    )
    if waiver is None:
        return None
    waiver.status = "revoked"
    waiver.revoked_reason = reason.strip()
    waiver.revoked_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(waiver)
    return _serialize_waiver(waiver)


def _serialize_waiver(waiver: AuditWaiverModel) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    expires = waiver.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    effective_status = "expired" if waiver.status == "active" and expires <= now else waiver.status
    return {
        "id": str(waiver.id),
        "project_id": str(waiver.project_id),
        "rule_id": waiver.rule_id,
        "target_requirement_id": waiver.target_requirement_id,
        "reason": waiver.reason,
        "compensating_control": waiver.compensating_control,
        "owner": waiver.owner,
        "approved_by": str(waiver.approved_by) if waiver.approved_by else None,
        "approved_by_name": waiver.approved_by_name,
        "expires_at": waiver.expires_at.isoformat(),
        "status": effective_status,
        "revoked_reason": waiver.revoked_reason,
        "revoked_at": waiver.revoked_at.isoformat() if waiver.revoked_at else None,
        "created_at": waiver.created_at.isoformat() if waiver.created_at else None,
    }
