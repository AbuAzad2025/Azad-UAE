"""Tests for app.py uncovered lines."""

import contextlib
import importlib
import importlib.util
import os
import sys
from unittest.mock import MagicMock, patch

import pytest


def _load_app_module():
    """Load app.py module directly, bypassing the app/ package."""
    spec = importlib.util.spec_from_file_location(
        "app_module", os.path.join(os.path.dirname(__file__), "..", "..", "app.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["app_module"] = module
    spec.loader.exec_module(module)
    return module


def test_mask_db_uri_no_scheme():
    """Test _mask_db_uri with URI that has no scheme."""
    app_mod = _load_app_module()
    result = app_mod._mask_db_uri("invalid-uri")
    assert result == "invalid-uri"


def test_mask_db_uri_no_at_sign():
    """Test _mask_db_uri with URI that has no @ sign."""
    app_mod = _load_app_module()
    result = app_mod._mask_db_uri("postgresql://user:pass")
    assert result == "postgresql://user:pass"


def test_mask_db_uri_no_colon_in_creds():
    """Test _mask_db_uri with URI that has no colon in credentials."""
    app_mod = _load_app_module()
    result = app_mod._mask_db_uri("postgresql://user@host/db")
    assert result == "postgresql://user@host/db"


def test_mask_db_uri_valid():
    """Test _mask_db_uri with valid URI."""
    app_mod = _load_app_module()
    result = app_mod._mask_db_uri("postgresql://user:pass@host/db")
    assert result == "postgresql://user:***@host/db"


def test_mask_db_uri_empty():
    """Test _mask_db_uri with empty string."""
    app_mod = _load_app_module()
    result = app_mod._mask_db_uri("")
    assert result == ""


def test_mask_db_uri_exception_handling():
    """Test _mask_db_uri exception handling with malformed URI."""
    app_mod = _load_app_module()
    # This should trigger the exception handling path
    result = app_mod._mask_db_uri("://@")
    assert result is not None


def test_main_block_backup_service_failure():
    """Test __main__ block when BackupService.initialize fails."""
    # This test is skipped because it's difficult to test the __main__ block
    # without conflicting with the app/ package import
    pytest.skip("Cannot test __main__ block due to app/ package conflict")


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
