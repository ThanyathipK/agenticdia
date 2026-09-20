"""architect_node must ALWAYS fill the official Krungsri template from the
project dataset - it must never merge with, or return, a previous PRD doc."""
import sys

import pytest

sys.path.insert(0, "/Users/thanyathip/Desktop/agenticdia/backend")

import app.agents as agents
from app.prompt_loader import load_prd_latex_template_body

REQ_STATE = {
    "project_id": "p1",
    "project_name": "PromptPay Refund Portal",
    "requirements": [
        {
            "requirement_code": "REQ-001",
            "title": "Refund Request Submission",
            "user_stories": [
                {
                    "ticket_code": "US-001",
                    "story_title": "Submit refund request online",
                    "as_a": "Retail Customer",
                    "i_want_to": "submit a refund request",
                    "so_that": "I get my money back",
                    "is_locked": False,
                    "acceptance_criteria": [
                        "Given a valid transaction ID, when submitted, then status is PENDING"
                    ],
                }
            ],
        }
    ],
    "business_goals": [{"description": "Cut refund handling time by 60%"}],
    "actors": [{"name": "Retail Customer"}, {"name": "Bank Refund Officer"}],
    "user_stories": [],
    "acceptance_criteria": [],
    "generated_prd": "",
    "generated_diagrams": "",
    "current_workflow_state": "gatherer_node",
    "version_number": 2,
    "updated_at": None,
}


def _patch(monkeypatch, req_state):
    async def fake_state(project_id, session=None, current_version=1):
        return dict(req_state)

    async def fake_save(**kwargs):
        return None

    async def fake_diagram(project_id, req_state, project_data):
        # Stands in for the LLM round-trip in agents._generate_flow_diagram so
        # these template-fill tests stay offline and deterministic.
        return "flowchart TD\n  A([Start]) --> B[Generated from PRD dataset]"

    monkeypatch.setattr(agents, "get_or_init_requirement_state", fake_state)
    monkeypatch.setattr(agents.ConversationMessageRepository, "save_message", fake_save)
    monkeypatch.setattr(agents, "_generate_flow_diagram", fake_diagram)


@pytest.mark.asyncio
async def test_architect_fills_template_from_full_project_dataset(monkeypatch):
    """The generated PRD is the OFFICIAL template body with the project's own
    data filled in - cover, stakeholders, FR/AC rows and scope lists."""
    _patch(monkeypatch, REQ_STATE)

    result = await agents.architect_node({
        "project_id": "p1",
        "current_version": 2,
        "structured_requirements": {},
        "version_history_summaries": "No previous revision logs available.",
    })

    prd = result["prd_markdown"]
    # the untouched official skeleton
    assert "\\section*{Stakeholders}" in prd
    assert "\\multirow" in prd and "\\multicolumn" in prd
    # filled from the project data
    assert "PromptPay Refund Portal" in prd        # cover PMO_NAME
    assert "V2.0" in prd                            # version history
    assert "Cut refund handling time by 60" in prd  # business objectives
    assert "US-001: Submit refund request online" in prd  # FR row
    assert "Given a valid transaction ID" in prd          # acceptance criteria
    assert "Submit refund request online" in prd          # scope in
    # persisted into the requirement state
    assert result["requirement_state"]["generated_prd"] == prd
    # the flow diagram is refreshed together with the document
    assert result["mermaid_diagram"].startswith("flowchart TD")
    assert result["requirement_state"]["generated_diagrams"] == result["mermaid_diagram"]


@pytest.mark.asyncio
async def test_architect_regenerates_instead_of_merging_legacy_prd(monkeypatch):
    """A stored PRD that does NOT follow the Krungsri template must be thrown
    away and regenerated as a fresh filled template - never merged."""
    legacy = dict(REQ_STATE)
    legacy["generated_prd"] = "# Core Banking PRD\n\nOld markdown sections..."
    legacy["generated_diagrams"] = ""
    _patch(monkeypatch, legacy)

    result = await agents.architect_node({
        "project_id": "p1",
        "current_version": 2,
        "structured_requirements": {},
    })

    assert "# Core Banking PRD" not in result["prd_markdown"]
    assert "\\section*{Stakeholders}" in result["prd_markdown"]


@pytest.mark.asyncio
async def test_architect_reuses_krungsri_prd_when_nothing_changed(monkeypatch):
    """When every story is unchanged and the stored PRD already follows the
    template, the node returns the stored document as-is."""
    krungsri = dict(REQ_STATE)
    krungsri["generated_prd"] = load_prd_latex_template_body()
    krungsri["generated_diagrams"] = "graph TD"
    stories = []
    for req in krungsri["requirements"]:
        for story in req["user_stories"]:
            story["change_type"] = "unchanged"
            stories.append(story)
    krungsri["user_stories"] = stories
    _patch(monkeypatch, krungsri)

    result = await agents.architect_node({
        "project_id": "p1",
        "current_version": 2,
        "structured_requirements": {},
    })

    assert result["prd_markdown"] == load_prd_latex_template_body()


@pytest.mark.asyncio
async def test_architect_raises_on_empty_dataset(monkeypatch):
    """No stories anywhere -> fail loudly instead of producing a blank PRD."""
    empty = dict(REQ_STATE)
    empty["requirements"] = []
    _patch(monkeypatch, empty)

    with pytest.raises(ValueError, match="no unlocked user stories"):
        await agents.architect_node({
            "project_id": "p1",
            "current_version": 2,
            "structured_requirements": {},
        })
