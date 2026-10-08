"""Load and validate the canonical, versioned Auditor checklist.

The checklist is code-owned seed data for now. Keeping its contract outside the
prompt makes rule identities stable and lets every persisted audit record the
exact policy version used to produce it.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AuditChecklistRule(BaseModel):
    rule_id: str = Field(pattern=r"^[A-Z][A-Z0-9-]+$")
    category: str
    title: str
    description: str
    classification: Literal["required_when_applicable", "recommended"]
    default_severity: Literal["low", "medium", "high", "critical"]
    applicability_hints: list[str] = Field(default_factory=list)
    expected_evidence: list[str] = Field(default_factory=list)
    remediation_guidance: str


class AuditChecklist(BaseModel):
    checklist_id: str
    name: str
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    jurisdiction: str
    rules: list[AuditChecklistRule] = Field(min_length=1)

    @model_validator(mode="after")
    def rule_ids_are_unique(self) -> "AuditChecklist":
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Checklist rule_id values must be unique")
        return self

    def prompt_payload(self) -> dict:
        """Return the compact, model-facing representation."""
        return {
            "checklist_id": self.checklist_id,
            "version": self.version,
            "rules": [rule.model_dump() for rule in self.rules],
        }

    @property
    def rule_ids(self) -> set[str]:
        return {rule.rule_id for rule in self.rules}


@lru_cache(maxsize=1)
def load_active_audit_checklist() -> AuditChecklist:
    path = Path(__file__).with_name("checklists") / "banking_v1.json"
    with path.open(encoding="utf-8") as source:
        return AuditChecklist.model_validate(json.load(source))

