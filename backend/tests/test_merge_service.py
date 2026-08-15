"""
Unit tests for :mod:`app.merge_service`.

Exercises the pure reconciliation logic that powers the multi-agent Gatherer:
- ``normalize_ticket_code`` / ``normalize_title`` / ``generate_next_ticket_code``
- ``merge_user_stories`` (create / update / unchanged / archive semantics)
- the shared post-merge helpers ``filter_active_stories`` and
  ``collect_acceptance_criteria``

Run from the ``backend`` directory::

    ../venv/bin/python -m pytest tests/test_merge_service.py -v
"""
import pytest

from app.merge_service import (
    collect_acceptance_criteria,
    filter_active_stories,
    generate_next_ticket_code,
    merge_user_stories,
    normalize_ticket_code,
    normalize_title,
)


# ==========================================
# Fixtures
# ==========================================
@pytest.fixture
def existing_stories():
    return [
        {
            "id": "s1",
            "ticket_code": "US-001",
            "story_title": "User Login",
            "as_a": "customer",
            "i_want_to": "log in to my account",
            "so_that": "I can manage my funds",
            "acceptance_criteria": ["Login validates credentials", "Failed login shows error"],
            "status": "active",
        },
        {
            "id": "s2",
            "ticket_code": "US-002",
            "story_title": "Transfer Funds",
            "as_a": "customer",
            "i_want_to": "transfer money",
            "so_that": "I can move funds between accounts",
            "acceptance_criteria": ["Transfer requires two-factor auth"],
            "status": "active",
        },
        {
            "id": "s3",
            "ticket_code": "US-003",
            "story_title": "Retired Story",
            "as_a": "customer",
            "i_want_to": "do an old thing",
            "so_that": "legacy purposes",
            "acceptance_criteria": [],
            "status": "archived",
        },
    ]


def make_incoming(**overrides):
    story = {
        "id": "s1",
        "ticket_code": "US-001",
        "story_title": "User Login",
        "as_a": "customer",
        "i_want_to": "log in to my account",
        "so_that": "I can manage my funds",
        "acceptance_criteria": ["Login validates credentials", "Failed login shows error"],
    }
    story.update(overrides)
    return story


# ==========================================
# normalize_ticket_code
# ==========================================
class TestNormalizeTicketCode:
    def test_none_and_empty_return_empty(self):
        assert normalize_ticket_code(None) == ""
        assert normalize_ticket_code("") == ""

    def test_lowercase_is_normalized_to_upper(self):
        assert normalize_ticket_code("us-1") == "US-001"

    def test_pads_to_three_digits(self):
        assert normalize_ticket_code("US-9") == "US-009"
        assert normalize_ticket_code("US-42") == "US-042"
        assert normalize_ticket_code("US-999") == "US-999"

    def test_zero_padding_is_stripped_for_larger_numbers(self):
        assert normalize_ticket_code("US-0100") == "US-100"

    def test_us_000_preserved(self):
        assert normalize_ticket_code("US-000") == "US-000"

    def test_non_us_code_returns_uppercased_input(self):
        assert normalize_ticket_code("xyz") == "XYZ"

    def test_non_string_input_is_stringified(self):
        assert normalize_ticket_code(7) == "7"


# ==========================================
# normalize_title
# ==========================================
class TestNormalizeTitle:
    def test_none_and_empty_return_empty(self):
        assert normalize_title(None) == ""
        assert normalize_title("") == ""

    def test_lowercases_and_collapses_whitespace(self):
        assert normalize_title("  User    LOGIN  ") == "user login"

    def test_mixed_case_is_lowercased(self):
        assert normalize_title("Transfer Funds") == "transfer funds"


# ==========================================
# generate_next_ticket_code
# ==========================================
class TestGenerateNextTicketCode:
    def test_empty_list_starts_at_us_001(self):
        assert generate_next_ticket_code([]) == "US-001"

    def test_increments_beyond_highest_number(self):
        stories = [
            {"ticket_code": "US-005"},
            {"ticket_code": "us-3"},
            {"ticket_code": "REQ-1"},
            {},
        ]
        assert generate_next_ticket_code(stories) == "US-006"

    def test_ignores_non_numeric_suffixes(self):
        assert generate_next_ticket_code([{"ticket_code": "US-ABC"}]) == "US-001"
# ==========================================
# merge_user_stories
# ==========================================
class TestMergeUserStories:
    def test_empty_inputs_returns_empty_list(self):
        assert merge_user_stories([], []) == []

    def test_all_incoming_are_created_with_sequential_codes(self):
        merged = merge_user_stories([], [
            {"story_title": "One", "as_a": "a", "i_want_to": "b", "so_that": "c", "acceptance_criteria": ["AC1"]},
            {"story_title": "Two", "as_a": "a", "i_want_to": "b", "so_that": "c", "acceptance_criteria": []},
        ])
        assert [s["ticket_code"] for s in merged] == ["US-001", "US-002"]
        assert all(s["change_type"] == "created" for s in merged)
        assert all(s["status"] == "active" for s in merged)

    def test_created_story_keeps_incoming_id(self):
        merged = merge_user_stories([], [{"id": "abc-123", "story_title": "One"}])
        assert merged[0]["id"] == "abc-123"

    def test_match_by_id_updates_fields(self, existing_stories):
        incoming = [make_incoming(
            story_title="User Login v2",
            i_want_to="log in with biometrics",
            acceptance_criteria=["Login validates credentials", "Failed login shows error", "Supports biometrics"],
        )]
        merged = merge_user_stories(existing_stories, incoming)
        # s1 updated + s2 unchanged; s3 is archived and is never re-emitted
        assert len(merged) == 2
        updated = next(s for s in merged if s["id"] == "s1")
        assert updated["change_type"] == "updated"
        assert updated["status"] == "active"
        assert updated["story_title"] == "User Login v2"
        assert updated["i_want_to"] == "log in with biometrics"

    def test_identical_incoming_keeps_change_type_unchanged(self, existing_stories):
        incoming = [make_incoming()]
        merged = merge_user_stories(existing_stories, incoming)
        updated = next(s for s in merged if s["id"] == "s1")
        assert updated["change_type"] == "unchanged"
        assert updated["status"] == "active"

    def test_match_by_lowercase_code(self, existing_stories):
        incoming = [make_incoming(id=None, ticket_code="us-1")]
        merged = merge_user_stories(existing_stories, incoming)
        updated = next(s for s in merged if s["ticket_code"] == "US-001")
        assert updated["change_type"] == "unchanged"

    def test_match_by_normalized_title(self, existing_stories):
        incoming = [make_incoming(id=None, ticket_code="US-999", story_title="USER  LOGIN")]
        merged = merge_user_stories(existing_stories, incoming)
        # Matches existing US-001 by normalized title (id/code do not match),
        # so only the active stories (s1 updated + s2 unchanged) come back
        assert len(merged) == 2
        updated = next(s for s in merged if s["ticket_code"] == "US-999")
        assert updated["story_title"] == "USER  LOGIN".strip()
        assert updated["as_a"] == "customer"

    def test_update_recommendation_marks_modified_even_without_field_changes(self, existing_stories):
        incoming = [make_incoming()]
        recs = [{"target_requirement_id": "US-001", "recommended_action": "UPDATE"}]
        merged = merge_user_stories(existing_stories, incoming, recs)
        updated = next(s for s in merged if s["id"] == "s1")
        assert updated["change_type"] == "updated"

    def test_no_change_recommendation_keeps_unchanged_even_with_field_changes(self, existing_stories):
        incoming = [make_incoming(story_title="User Login v2")]
        recs = [{"target_requirement_id": "US-001", "recommended_action": "NO_CHANGE"}]
        merged = merge_user_stories(existing_stories, incoming, recs)
        updated = next(s for s in merged if s["id"] == "s1")
        assert updated["change_type"] == "unchanged"
        # but incoming field values still win
        assert updated["story_title"] == "User Login v2"
    def test_archive_recommendation_archives_matched_story(self, existing_stories):
        incoming = [make_incoming()]
        recs = [{"target_requirement_id": "US-001", "recommended_action": "ARCHIVE"}]
        merged = merge_user_stories(existing_stories, incoming, recs)
        archived = next(s for s in merged if s["id"] == "s1")
        assert archived["status"] == "archived"
        assert archived["change_type"] == "archived"

    def test_incoming_status_archived_archives_matched_story(self, existing_stories):
        incoming = [make_incoming(status="archived")]
        merged = merge_user_stories(existing_stories, incoming)
        archived = next(s for s in merged if s["id"] == "s1")
        assert archived["status"] == "archived"
        assert archived["change_type"] == "archived"

    def test_incoming_change_type_archived_archives_matched_story(self, existing_stories):
        incoming = [make_incoming(change_type="archived")]
        merged = merge_user_stories(existing_stories, incoming)
        archived = next(s for s in merged if s["id"] == "s1")
        assert archived["status"] == "archived"

    def test_unmatched_incoming_with_archive_rec_is_skipped(self, existing_stories):
        incoming = [{"ticket_code": "US-010", "story_title": "Brand New Story", "as_a": "a", "i_want_to": "b", "so_that": "c"}]
        recs = [{"target_requirement_id": "US-010", "recommended_action": "ARCHIVE"}]
        merged = merge_user_stories(existing_stories, incoming, recs)
        # s1 + s2 unchanged, new story skipped thanks to the ARCHIVE recommendation
        assert len(merged) == 2
        assert all(s["change_type"] == "unchanged" for s in merged)

    def test_unmatched_incoming_with_archived_status_is_skipped(self, existing_stories):
        incoming = [{"story_title": "Brand New Story", "status": "archived"}]
        merged = merge_user_stories(existing_stories, incoming)
        assert len(merged) == 2

    def test_existing_unmatched_stories_are_kept_unchanged(self, existing_stories):
        merged = merge_user_stories(existing_stories, [])
        active = [s for s in merged if s["status"] == "active"]
        assert {s["id"] for s in active} == {"s1", "s2"}
        assert all(s["change_type"] == "unchanged" for s in active)

    def test_existing_unmatched_story_archived_via_recommendation(self, existing_stories):
        recs = [{"target_requirement_id": "US-002", "recommended_action": "ARCHIVE"}]
        merged = merge_user_stories(existing_stories, [], recs)
        archived = next(s for s in merged if s["id"] == "s2")
        assert archived["status"] == "archived"
        assert archived["change_type"] == "archived"

    def test_archived_existing_stories_are_not_reprocessed(self, existing_stories):
        # s3 is already archived and should not be touched by the merge
        merged = merge_user_stories(existing_stories, [])
        retired = next((s for s in merged if s["id"] == "s3"), None)
        assert retired is None  # only active existing stories are re-emitted

    def test_new_story_with_us_000_gets_next_code(self, existing_stories):
        incoming = [{"ticket_code": "US-000", "story_title": "New Feature", "as_a": "a", "i_want_to": "b", "so_that": "c"}]
        merged = merge_user_stories(existing_stories, incoming)
        new_story = next(s for s in merged if s["story_title"] == "New Feature")
        assert new_story["ticket_code"] == "US-003"
        assert new_story["change_type"] == "created"

    def test_new_stories_claiming_us_000_get_sequential_next_codes(self, existing_stories):
        incoming = [
            {"ticket_code": "US-000", "story_title": "Feature A", "as_a": "a", "i_want_to": "b", "so_that": "c"},
            {"ticket_code": "US-000", "story_title": "Feature B", "as_a": "a", "i_want_to": "b", "so_that": "c"},
        ]
        merged = merge_user_stories(existing_stories, incoming)
        created = {s["story_title"]: s["ticket_code"] for s in merged if s["change_type"] == "created"}
        # US-001/US-002 are taken by existing active stories, so the two new
        # stories claim US-003 and US-004 in sequence
        assert created["Feature A"] == "US-003"
        assert created["Feature B"] == "US-004"

    def test_update_keeps_matched_code_when_incoming_code_is_us_000(self, existing_stories):
        incoming = [make_incoming(ticket_code="US-000", story_title="User Login v2")]
        merged = merge_user_stories(existing_stories, incoming)
        updated = next(s for s in merged if s["id"] == "s1")
        assert updated["ticket_code"] == "US-001"

    def test_created_story_defaults_fields(self):
        merged = merge_user_stories([], [{"story_title": "One"}])
        assert merged[0]["story_title"] == "One"
        assert merged[0]["acceptance_criteria"] == []

    def test_semantic_recs_do_not_crash_on_missing_keys(self, existing_stories):
        merged = merge_user_stories(existing_stories, [], [{"confidence": 0.9}])
        assert len(merged) == 2
# ==========================================
# filter_active_stories / collect_acceptance_criteria
# ==========================================
class TestFilterActiveStories:
    def test_returns_only_active_stories(self):
        stories = [
            {"id": "a", "status": "active"},
            {"id": "b", "status": "archived"},
            {"id": "c", "status": "active"},
        ]
        result = filter_active_stories(stories)
        assert [s["id"] for s in result] == ["a", "c"]

    def test_missing_status_is_treated_as_active(self):
        stories = [{"id": "a"}, {"id": "b", "status": "archived"}]
        assert [s["id"] for s in filter_active_stories(stories)] == ["a"]

    def test_empty_input_returns_empty_list(self):
        assert filter_active_stories([]) == []


class TestCollectAcceptanceCriteria:
    def test_flattens_criteria_from_multiple_stories(self):
        stories = [
            {"acceptance_criteria": ["AC1", "AC2"]},
            {"acceptance_criteria": ["AC3"]},
            {"acceptance_criteria": []},
        ]
        assert collect_acceptance_criteria(stories) == ["AC1", "AC2", "AC3"]

    def test_missing_criteria_key_is_skipped(self):
        stories = [{"acceptance_criteria": ["AC1"]}, {}]
        assert collect_acceptance_criteria(stories) == ["AC1"]

    def test_empty_input_returns_empty_list(self):
        assert collect_acceptance_criteria([]) == []