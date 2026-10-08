"""Deployment database policy and tolerant local-model schema tests."""
import pytest

from app.config import SQLITE_FALLBACK_URL, Settings
from app.schemas import AuditRecommendationDetail


def test_missing_database_url_is_allowed_only_for_local_fallback():
    local = Settings(DATABASE_URL="", ALLOW_SQLITE_FALLBACK=True)
    assert local.async_database_url == SQLITE_FALLBACK_URL

    deployed = Settings(DATABASE_URL="", ALLOW_SQLITE_FALLBACK=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is empty"):
        _ = deployed.async_database_url


def test_placeholder_supabase_url_is_rejected_when_fallback_disabled():
    settings = Settings(
        DATABASE_URL=(
            "postgresql://postgres.[YOUR_PROJECT_REF]:[YOUR_PASSWORD]"
            "@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
        ),
        ALLOW_SQLITE_FALLBACK=False,
    )
    with pytest.raises(RuntimeError, match="unfilled placeholder"):
        _ = settings.async_database_url


def test_single_recommended_acceptance_criterion_is_coerced_without_llm_retry():
    recommendation = AuditRecommendationDetail(
        summary="Add idempotency handling.",
        proposed_acceptance_criteria="Given a duplicate key, then do not post twice.",
    )
    assert recommendation.proposed_acceptance_criteria == [
        "Given a duplicate key, then do not post twice."
    ]
