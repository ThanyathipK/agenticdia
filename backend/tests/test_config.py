"""Regression tests for environment-backed application settings."""

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize("value", ["release", "production", "prod"])
def test_debug_release_mode_names_disable_debug(value):
    assert Settings(_env_file=None, DEBUG=value).DEBUG is False


@pytest.mark.parametrize("value", ["debug", "development", "dev"])
def test_debug_development_mode_names_enable_debug(value):
    assert Settings(_env_file=None, DEBUG=value).DEBUG is True


def test_debug_still_rejects_unknown_values():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DEBUG="unexpected")
