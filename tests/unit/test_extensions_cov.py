"""Residual-line/arc coverage for extensions.py.

Target (branch coverage):
- arc 71->77: ``TenantAwareCache._tenant_key`` called with no active
  request context — ``has_request_context()`` is False, so the key is
  returned unprefixed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from extensions import TenantAwareCache


class TestTenantKeyWithoutRequestContext:
    def test_plain_key_outside_any_context(self):
        cache = TenantAwareCache(MagicMock())
        assert cache._tenant_key("plain-key") == "plain-key"

    def test_explicit_no_request_context_returns_key(self):
        cache = TenantAwareCache(MagicMock())
        with patch("flask.has_request_context", return_value=False):
            assert cache._tenant_key("another-key") == "another-key"

    def test_delegating_methods_use_plain_key_without_context(self):
        raw = MagicMock()
        raw.get.return_value = "v"
        cache = TenantAwareCache(raw)
        with patch("flask.has_request_context", return_value=False):
            assert cache.get("k") == "v"
        raw.get.assert_called_once_with("k")
