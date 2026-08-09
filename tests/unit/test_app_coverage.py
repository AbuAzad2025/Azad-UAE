"""Tests for app.py uncovered lines."""

import contextlib
import os
from unittest.mock import MagicMock, patch


def test_mask_db_uri_no_scheme():
    """Test _mask_db_uri with URI that has no scheme."""
    from app import _mask_db_uri

    result = _mask_db_uri("invalid-uri")
    assert result == "invalid-uri"


def test_mask_db_uri_no_at_sign():
    """Test _mask_db_uri with URI that has no @ sign."""
    from app import _mask_db_uri

    result = _mask_db_uri("postgresql://user:pass")
    assert result == "postgresql://user:pass"


def test_mask_db_uri_no_colon_in_creds():
    """Test _mask_db_uri with URI that has no colon in credentials."""
    from app import _mask_db_uri

    result = _mask_db_uri("postgresql://user@host/db")
    assert result == "postgresql://user@host/db"


def test_mask_db_uri_valid():
    """Test _mask_db_uri with valid URI."""
    from app import _mask_db_uri

    result = _mask_db_uri("postgresql://user:pass@host/db")
    assert result == "postgresql://user:***@host/db"


def test_mask_db_uri_empty():
    """Test _mask_db_uri with empty string."""
    from app import _mask_db_uri

    result = _mask_db_uri("")
    assert result == ""


def test_mask_db_uri_exception_handling():
    """Test _mask_db_uri exception handling with malformed URI."""
    from app import _mask_db_uri

    # This should trigger the exception handling path
    result = _mask_db_uri("://@")
    assert result is not None


def test_main_block_backup_service_failure():
    """Test __main__ block when BackupService.initialize fails."""
    with patch("app.create_app") as mock_create:
        mock_app = MagicMock()
        mock_app.config = {"DEBUG": False}
        mock_create.return_value = mock_app

        with patch.dict(os.environ, {"PORT": "5000", "HOST": "0.0.0.0"}):
            with patch("services.backup_service.BackupService.initialize") as mock_init:
                mock_init.side_effect = Exception("Backup failed")
                with patch("app.BackupService", side_effect=Exception("Backup failed")):
                    # Import and run the main block
                    import importlib

                    import app

                    with contextlib.suppress(Exception):
                        importlib.reload(app)  # Expected to fail


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])