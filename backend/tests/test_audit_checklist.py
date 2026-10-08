"""Offline contract tests for the versioned banking audit checklist."""
import copy

import pytest
from pydantic import ValidationError

from app.audit_checklist import AuditChecklist, load_active_audit_checklist
from app.schemas import AuditorOutput


def test_active_checklist_has_unique_stable_rules():
    checklist = load_active_audit_checklist()

    assert checklist.checklist_id == "banking-core"
    assert checklist.version == "1.0.0"
    assert len(checklist.rules) == 12
    assert len(checklist.rule_ids) == len(checklist.rules)
    assert "BANK-IDEMPOTENCY-001" in checklist.rule_ids
    assert all(rule.remediation_guidance for rule in checklist.rules)


def test_duplicate_rule_ids_are_rejected():
    raw = load_active_audit_checklist().model_dump()
    duplicate = copy.deepcopy(raw["rules"][0])
    raw["rules"].append(duplicate)

    with pytest.raises(ValidationError, match="must be unique"):
        AuditChecklist.model_validate(raw)


def test_legacy_finding_remains_readable_as_adhoc():
    result = AuditorOutput.model_validate({
        "is_valid": True,
        "findings": [{
            "finding_type": "ambiguous",
            "category": "Terminology",
            "description": "The term account is ambiguous.",
        }],
        "clarification_questions": [],
    })

    assert result.findings[0].rule_id == "ADHOC"


def test_recommendation_is_structured_and_optional():
    result = AuditorOutput.model_validate({
        "is_valid": True,
        "findings": [{
            "rule_id": "BANK-READINESS-001",
            "finding_type": "missing",
            "category": "Product and delivery readiness",
            "description": "The outcome is not measurable.",
            "recommendation": {
                "summary": "Define a measurable outcome.",
                "proposed_requirement_text": "The service shall achieve the agreed completion rate.",
                "proposed_acceptance_criteria": ["Given a reporting period, when results are measured, then the completion rate is available."],
                "expected_benefit": "Makes success testable."
            },
        }],
        "clarification_questions": [],
    })

    assert result.findings[0].recommendation is not None
    assert result.findings[0].recommendation.proposed_acceptance_criteria
