"""
User Story Merge Service.

Pure, dependency-free helpers (no langchain / DB / LLM imports) that power
the multi-agent Gatherer's user story reconciliation logic.

The core entrypoint is :func:`merge_user_stories`, which reconciles newly
generated user stories against previously persisted ones:

- Keep unchanged stories        -> ``change_type="unchanged"``, ``status="active"``
- Update modified stories       -> ``change_type="updated"``,  ``status="active"``
- Insert brand-new stories      -> ``change_type="created"``,  ``status="active"``
- Archive deleted stories       -> ``change_type="archived"``, ``status="archived"``

Exposing this logic in a dedicated module (instead of inside ``agents.py``)
keeps it unit-testable without bootstrapping an LLM client or the LangGraph
workflow.
"""
from typing import Dict, Any, List, Optional


# ==========================================
# NORMALIZATION / TICKET HELPERS
# ==========================================
def normalize_ticket_code(code: Optional[str]) -> str:
    if not code:
        return ""
    code = str(code).strip().upper()
    if code.startswith("US-"):
        num_part = code[3:]
        if num_part.isdigit():
            return f"US-{int(num_part):03d}"
    return code


def normalize_title(title: Optional[str]) -> str:
    if not title:
        return ""
    return " ".join(str(title).lower().strip().split())


def generate_next_ticket_code(stories: List[Dict[str, Any]]) -> str:
    max_num = 0
    for s in stories:
        tc = s.get("ticket_code", "")
        if tc and str(tc).strip().upper().startswith("US-"):
            num_part = str(tc).strip().upper()[3:]
            if num_part.isdigit():
                max_num = max(max_num, int(num_part))
    return f"US-{max_num + 1:03d}"

# ==========================================
# CORE MERGE LOGIC
# ==========================================
def merge_user_stories(
    existing_stories: List[Dict[str, Any]],
    new_incoming_stories: List[Dict[str, Any]],
    semantic_recs: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Merges newly generated user stories with existing user stories.
    Requirements:
    - Load all existing User Stories.
    - Merge newly generated User Stories.
    - Keep unchanged stories (change_type="unchanged", status="active").
    - Update modified stories (change_type="updated", status="active").
    - Insert new stories (change_type="created", status="active").
    - Archive deleted stories (change_type="archived", status="archived").

    ``semantic_recs`` is an optional list of semantic-change recommendations of
    the form ``{"target_requirement_id": ..., "recommended_action": ...}``
    where ``recommended_action`` is one of ``INSERT``, ``UPDATE``,
    ``ARCHIVE`` or ``NO_CHANGE``.
    """
    semantic_recs = semantic_recs or []

    rec_by_code = {}
    rec_by_title = {}
    for rec in semantic_recs:
        target_id = rec.get("target_requirement_id")
        action = rec.get("recommended_action")
        if target_id and action:
            norm_target = normalize_ticket_code(target_id)
            if norm_target:
                rec_by_code[norm_target] = action
            else:
                rec_by_title[normalize_title(target_id)] = action

    existing_by_id = {}
    existing_by_code = {}
    existing_by_title = {}

    active_existing = [s for s in existing_stories if s.get("status", "active") == "active"]

    for s in active_existing:
        if s.get("id"):
            existing_by_id[str(s["id"])] = s
        code = normalize_ticket_code(s.get("ticket_code"))
        if code and code != "US-000":
            existing_by_code[code] = s
        title = normalize_title(s.get("story_title"))
        if title:
            existing_by_title[title] = s

    matched_existing_ptrs = set()
    merged_stories: List[Dict[str, Any]] = []

    # 1. Process incoming stories
    for inc in new_incoming_stories:
        inc_id = str(inc["id"]) if inc.get("id") else None
        inc_code = normalize_ticket_code(inc.get("ticket_code"))
        inc_title = normalize_title(inc.get("story_title"))

        matched = None
        if inc_id and inc_id in existing_by_id:
            matched = existing_by_id[inc_id]
        elif inc_code and inc_code in existing_by_code:
            matched = existing_by_code[inc_code]
        elif inc_title and inc_title in existing_by_title:
            matched = existing_by_title[inc_title]

        if matched:
            matched_existing_ptrs.add(id(matched))

            rec_act = rec_by_code.get(inc_code) or rec_by_code.get(normalize_ticket_code(matched.get("ticket_code"))) or rec_by_title.get(inc_title)

            if rec_act == "ARCHIVE" or inc.get("status") == "archived" or inc.get("change_type") == "archived":
                archived_story = dict(matched)
                archived_story["status"] = "archived"
                archived_story["change_type"] = "archived"
                merged_stories.append(archived_story)
                continue

            # Compare fields to check if modified
            m_title = (matched.get("story_title") or "").strip()
            m_as_a = (matched.get("as_a") or "").strip()
            m_i_want = (matched.get("i_want_to") or "").strip()
            m_so_that = (matched.get("so_that") or "").strip()
            m_ac = matched.get("acceptance_criteria", [])

            i_title = (inc.get("story_title") or m_title).strip()
            i_as_a = (inc.get("as_a") or m_as_a).strip()
            i_i_want = (inc.get("i_want_to") or m_i_want).strip()
            i_so_that = (inc.get("so_that") or m_so_that).strip()
            i_ac = inc.get("acceptance_criteria") if "acceptance_criteria" in inc else m_ac

            title_diff = (m_title != i_title)
            as_a_diff = (m_as_a != i_as_a)
            i_want_diff = (m_i_want != i_i_want)
            so_that_diff = (m_so_that != i_so_that)
            ac_diff = (m_ac != i_ac)

            field_changed = title_diff or as_a_diff or i_want_diff or so_that_diff or ac_diff

            if rec_act == "UPDATE":
                is_modified = True
            elif rec_act == "NO_CHANGE":
                is_modified = False
            else:
                is_modified = field_changed

            updated_story = dict(matched)
            updated_story["story_title"] = i_title
            updated_story["as_a"] = i_as_a
            updated_story["i_want_to"] = i_i_want
            updated_story["so_that"] = i_so_that
            updated_story["acceptance_criteria"] = i_ac
            updated_story["status"] = "active"
            updated_story["change_type"] = "updated" if is_modified else "unchanged"

            if inc_code and inc_code != "US-000":
                updated_story["ticket_code"] = inc_code
            elif not updated_story.get("ticket_code"):
                updated_story["ticket_code"] = matched.get("ticket_code") or "US-001"

            merged_stories.append(updated_story)

        else:
            # Unmatched incoming -> New story insertion
            rec_act = rec_by_code.get(inc_code) or rec_by_title.get(inc_title)
            if rec_act == "ARCHIVE" or inc.get("status") == "archived":
                continue

            ticket_code = inc_code
            if not ticket_code or ticket_code == "US-000" or ticket_code in existing_by_code:
                ticket_code = generate_next_ticket_code(active_existing + merged_stories)

            new_story = {
                "ticket_code": ticket_code,
                "story_title": inc.get("story_title", "Untitled Story"),
                "as_a": inc.get("as_a", ""),
                "i_want_to": inc.get("i_want_to", ""),
                "so_that": inc.get("so_that", ""),
                "acceptance_criteria": inc.get("acceptance_criteria", []),
                "status": "active",
                "change_type": "created"
            }
            if inc.get("id"):
                new_story["id"] = inc["id"]

            merged_stories.append(new_story)

    # 2. Process existing active stories that were NOT matched by incoming
    for ex in active_existing:
        if id(ex) in matched_existing_ptrs:
            continue

        ex_code = normalize_ticket_code(ex.get("ticket_code"))
        ex_title = normalize_title(ex.get("story_title"))
        rec_act = rec_by_code.get(ex_code) or rec_by_title.get(ex_title)

        if rec_act == "ARCHIVE":
            archived_story = dict(ex)
            archived_story["status"] = "archived"
            archived_story["change_type"] = "archived"
            merged_stories.append(archived_story)
        else:
            # KEEP UNCHANGED!
            unchanged_story = dict(ex)
            unchanged_story["status"] = "active"
            unchanged_story["change_type"] = "unchanged"
            merged_stories.append(unchanged_story)

    return merged_stories


# ==========================================
# POST-MERGE HELPERS (shared by gatherer_node)
# ==========================================
def filter_active_stories(stories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Returns only the stories whose status is ``"active"`` (default if unset)."""
    return [s for s in stories if s.get("status", "active") == "active"]


def collect_acceptance_criteria(stories: List[Dict[str, Any]]) -> List[Any]:
    """Flattens the ``acceptance_criteria`` of every story into a single list."""
    all_ac: List[Any] = []
    for story in stories:
        all_ac.extend(story.get("acceptance_criteria", []))
    return all_ac