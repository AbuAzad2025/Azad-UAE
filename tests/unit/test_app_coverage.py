"""Real behavioral tests for the root ``app.py`` entrypoint helpers.

These tests execute the genuine module source (previously they tested a
copy-pasted duplicate of ``_mask_db_uri``, which proved nothing about the
production code).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP_PY = ROOT / "app.py"

_LOADED = {}


def _load_entry_module():
    """Execute the real app.py once per process and cache the module."""
    mod = _LOADED.get("entry")
    if mod is not None:
        return mod
    spec_name = "azad_app_entry_real"
    saved = sys.modules.pop(spec_name, None)
    spec = importlib.util.spec_from_file_location(spec_name, APP_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec_name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        if saved is not None:
            sys.modules[spec_name] = saved
    _LOADED["entry"] = mod
    return mod


@pytest.fixture(scope="module")
def entry():
    return _load_entry_module()


class _UriThatExplodes(str):
    def split(self, *args, **kwargs):
        raise ValueError("split exploded")


class TestMaskDbUri:
    def test_empty_uri_passthrough(self, entry):
        assert entry._mask_db_uri("") == ""

    def test_falsy_none_passthrough(self, entry):
        assert entry._mask_db_uri(None) is None

    def test_no_scheme_unchanged(self, entry):
        assert entry._mask_db_uri("plain-host/db") == "plain-host/db"

    def test_scheme_without_credentials_unchanged(self, entry):
        uri = "postgresql://localhost/azad"
        assert entry._mask_db_uri(uri) == uri

    def test_single_token_credential_unchanged(self, entry):
        uri = "postgresql://user@host/db"
        assert entry._mask_db_uri(uri) == uri

    def test_password_is_masked(self, entry):
        assert (
            entry._mask_db_uri("postgresql://admin:s3cret@db.local:5432/azad_uae")
            == "postgresql://admin:***@db.local:5432/azad_uae"
        )

    def test_only_first_segment_of_user_is_kept(self, entry):
        masked = entry._mask_db_uri("mysql://u:p1:p2@host/db")
        assert masked == "mysql://u:***@host/db"

    def test_split_failure_reports_via_logging_core(self, entry):
        with patch("services.logging_core.LoggingCore.log_error") as log_error:
            result = entry._mask_db_uri(_UriThatExplodes("postgresql://u:p@host/db"))
        assert result == "postgresql://u:p@host/db"
        log_error.assert_called_once()
        kwargs = log_error.call_args.kwargs
        assert kwargs["category"] == "SYSTEM_INIT"
        assert kwargs["source"] == "app._mask_db_uri"
        assert "split exploded" in kwargs["message"]

    def test_split_failure_with_broken_logging_core_still_returns_uri(self, entry):
        with (
            patch(
                "services.logging_core.LoggingCore.log_error",
                side_effect=RuntimeError("logger down"),
            ),
            patch("logging.getLogger") as get_logger,
        ):
            result = entry._mask_db_uri(_UriThatExplodes("postgresql://u:p@host/db"))
        assert result == "postgresql://u:p@host/db"
        get_logger.return_value.exception.assert_called_once()


class TestEntryModuleContract:
    def test_module_exposes_flask_app_with_test_client(self, entry):
        assert entry.app is not None
        assert hasattr(entry.app, "test_client")

    def test_startup_masking_uses_canonical_function(self, entry):
        """Regression: the __main__ block must not carry its own duplicate masker."""
        source = APP_PY.read_text(encoding="utf-8")
        assert source.count("def _mask_db_uri") == 1
