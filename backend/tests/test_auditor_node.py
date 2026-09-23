"""
Offline unit tests for :func:`app.agents.auditor_node`'s requirement-board
contract.

Auditing stories must NEVER rebuild, renumber or flatten the requirement groups:
the node used to replace the reloaded board with a single hardcoded ``REQ-001``
group holding every story, which collapsed real groups (and on a fresh project
claimed the first requirement number, pushing the first gathered requirement to
``REQ-002``).

The stories below are all ``change_type: "unchanged"``, so the node short-circuits
before any LLM call and these tests stay offline and deterministic.

Run from the ``backend`` directory::

    ../venv/bin/python -m pytest tests/test_auditor_node.py -v
"""
import copy

import pytest

import app.agents as agents
from app.requirement_codes import FIRST_REQUIREMENT_CODE


def _story(code: str, title: str) -> dict:
    return {
        "ticket_code": code,
        "story_title": title,
        "as_a": "Retail Customer",
        "i_want_to": f"use {title.lower()}",
        "so_that": "I get value",
        "acceptance_criteria": [f"Given X, when {code}, then Y"],
        "change_type": "unchanged",
    }


US_001 = _story("US-001", "Submit refund request")
US_002 = _story("US-002", "SMS refund alerts")


def _board(requirements, stories):
    return {
        "project_id": "p1",
        "project_name": "Refund Portal",
        "requirements": requirements,
        "business_goals": [],
        "actors": [],
        "user_stories": stories,
        "acceptance_criteria": [],
        "clarification_questions": [],
        "validation_status": "pending",
        "generated_prd": "",
        "generated_diagrams": "",
        "current_workflow_state": "gatherer_node",
        "version_number": 3,
        "updated_at": None,
    }


MULTI_GROUP_BOARD = _board(
    [
        {"requirement_code": "REQ-001", "title": "Refund Request", "description": "", "user_stories": [US_001]},
        {"requirement_code": "REQ-002", "title": "Refund Notifications", "description": "", "user_stories": [US_002]},
    ],
    [US_001, US_002],
)


def _patch(monkeypatch, req_state):
    async def fake_state(project_id, session=None, current_version=1):
        return copy.deepcopy(req_state)

    monkeypatch.setattr(agents, "get_or_init_requirement_state", fake_state)


def _legacy_payload(stories):
    """The epic-only payload shape the route builds (no ``requirements`` key)."""
    return {"epic_name": "Refund Portal", "version": 3, "user_stories": copy.deepcopy(stories)}


def _groups(req_state):
    return {
        r["requirement_code"]: sorted(s["ticket_code"] for s in r["user_stories"])
        for r in req_state["requirements"]
    }


@pytest.mark.asyncio
async def test_auditor_keeps_requirement_groups_intact(monkeypatch):
    """An audit run must not collapse a multi-requirement board onto REQ-001."""
    _patch(monkeypatch, MULTI_GROUP_BOARD)

    result = await agents.auditor_node({
        "project_id": "p1",
        "current_version": 3,
        "structured_requirements": _legacy_payload(MULTI_GROUP_BOARD["user_stories"]),
    })

    assert _groups(result["requirement_state"]) == {
        "REQ-001": ["US-001"],
        "REQ-002": ["US-002"],
    }


@pytest.mark.asyncio
async def test_auditor_synthesizes_the_first_code_for_a_flat_legacy_board(monkeypatch):
    """A legacy FLAT board (stories with no requirement rows) still gets ONE
    group to live under — numbered from the shared sequence, never hardcoded."""
    _patch(monkeypatch, _board([], [US_001, US_002]))

    result = await agents.auditor_node({
        "project_id": "p1",
        "current_version": 3,
        "structured_requirements": _legacy_payload([US_001, US_002]),
    })

    groups = _groups(result["requirement_state"])
    assert list(groups) == [FIRST_REQUIREMENT_CODE] == ["REQ-001"]
    assert groups["REQ-001"] == ["US-001", "US-002"]


@pytest.mark.asyncio
async def test_auditor_never_fabricates_a_requirement_without_stories(monkeypatch):
    """Nothing to attach -> no requirement is invented (the phantom group used to
    occupy the first requirement number)."""
    _patch(monkeypatch, _board([], []))

    result = await agents.auditor_node({
        "project_id": "p1",
        "current_version": 3,
        "structured_requirements": _legacy_payload([]),
    })

    assert result["requirement_state"]["requirements"] == []
    assert result["requirement_state"]["user_stories"] == []
