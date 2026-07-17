from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import Forbidden

from utils import security_helpers as sh


class TestOwnerAllowlist:
    def test_explicit_env_allowlist(self, monkeypatch):
        monkeypatch.setenv("OWNER_ALLOWED_IPS", " 10.0.0.1 , 192.168.1.0/24 ")
        monkeypatch.delenv("AZAD_MASTER_LOGIN_ALLOWLIST", raising=False)
        assert sh._owner_allowlist() == ["10.0.0.1", "192.168.1.0/24"]

    def test_fallback_master_login_allowlist(self, monkeypatch):
        monkeypatch.delenv("OWNER_ALLOWED_IPS", raising=False)
        monkeypatch.setenv("AZAD_MASTER_LOGIN_ALLOWLIST", "203.0.113.5")
        assert sh._owner_allowlist() == ["203.0.113.5"]

    def test_debug_expands_private_ranges(self, monkeypatch):
        monkeypatch.delenv("OWNER_ALLOWED_IPS", raising=False)
        monkeypatch.delenv("AZAD_MASTER_LOGIN_ALLOWLIST", raising=False)
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("DEBUG", "true")
        allowlist = sh._owner_allowlist()
        assert "10.0.0.0/8" in allowlist
        assert "127.0.0.1" in allowlist

    def test_non_production_default_loopback(self, monkeypatch):
        monkeypatch.delenv("OWNER_ALLOWED_IPS", raising=False)
        monkeypatch.delenv("AZAD_MASTER_LOGIN_ALLOWLIST", raising=False)
        monkeypatch.setenv("APP_ENV", "staging")
        monkeypatch.delenv("DEBUG", raising=False)
        allowlist = sh._owner_allowlist()
        assert allowlist == [
            "127.0.0.1",
            "::1",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
        ]

    def test_production_strict_loopback_only(self, monkeypatch):
        monkeypatch.delenv("OWNER_ALLOWED_IPS", raising=False)
        monkeypatch.delenv("AZAD_MASTER_LOGIN_ALLOWLIST", raising=False)
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("DEBUG", raising=False)
        assert sh._owner_allowlist() == ["127.0.0.1", "::1"]


class TestIpAllowed:
    def test_none_or_empty_ip_rejected(self):
        assert sh._ip_allowed(None, ["127.0.0.1"]) is False
        assert sh._ip_allowed("", ["127.0.0.1"]) is False

    def test_invalid_ip_rejected(self):
        assert sh._ip_allowed("not-an-ip", ["127.0.0.1"]) is False

    def test_exact_match_ipv4_and_ipv6(self):
        assert sh._ip_allowed("127.0.0.1", ["127.0.0.1"]) is True
        assert sh._ip_allowed("::1", ["::1"]) is True

    def test_cidr_match(self):
        assert sh._ip_allowed("10.20.30.40", ["10.0.0.0/8"]) is True
        assert sh._ip_allowed("8.8.8.8", ["10.0.0.0/8"]) is False

    def test_malformed_allowlist_entry_skipped(self):
        assert sh._ip_allowed("127.0.0.1", ["bad-entry", "127.0.0.1"]) is True


class TestEnforceOwnerIp:
    def test_skips_unauthenticated_user(self):
        user = MagicMock(is_authenticated=False)
        with patch("flask_login.current_user", user):
            sh.enforce_owner_ip_if_needed()

    def test_skips_non_owner(self):
        user = MagicMock(is_authenticated=True, is_owner=False)
        with patch("flask_login.current_user", user):
            sh.enforce_owner_ip_if_needed()

    def test_skips_debug_app(self, monkeypatch):
        user = MagicMock(is_authenticated=True, is_owner=True)
        app = MagicMock(debug=True)
        monkeypatch.setenv("APP_ENV", "production")
        with patch("flask_login.current_user", user), patch("flask.current_app", app):
            sh.enforce_owner_ip_if_needed()

    def test_skips_non_production_env(self, monkeypatch):
        user = MagicMock(is_authenticated=True, is_owner=True)
        app = MagicMock(debug=False)
        monkeypatch.setenv("APP_ENV", "development")
        with patch("flask_login.current_user", user), patch("flask.current_app", app):
            sh.enforce_owner_ip_if_needed()

    def test_allows_allowlisted_ip(self, monkeypatch):
        user = MagicMock(is_authenticated=True, is_owner=True)
        app = MagicMock(debug=False)
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("OWNER_ALLOWED_IPS", "198.51.100.10")
        with (
            patch("flask_login.current_user", user),
            patch("flask.current_app", app),
            patch.object(sh.request, "remote_addr", "198.51.100.10"),
        ):
            sh.enforce_owner_ip_if_needed()

    def test_blocks_non_allowlisted_ip(self, monkeypatch):
        user = MagicMock(is_authenticated=True, is_owner=True)
        app = MagicMock(debug=False)
        app.logger = MagicMock()
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("OWNER_ALLOWED_IPS", raising=False)
        monkeypatch.delenv("AZAD_MASTER_LOGIN_ALLOWLIST", raising=False)
        with (
            patch("flask_login.current_user", user),
            patch("flask.current_app", app),
            patch.object(sh.request, "remote_addr", "203.0.113.99"),
        ):
            with pytest.raises(Forbidden):
                sh.enforce_owner_ip_if_needed()


class TestOwnerIpDecorator:
    def test_decorator_invokes_view_after_check(self):
        called = []

        @sh.owner_ip_check
        def view():
            called.append(True)
            return "ok"

        with patch.object(sh, "enforce_owner_ip_if_needed"):
            assert view() == "ok"
        assert called


class TestSanitizeSqlLike:
    def test_empty_input(self):
        assert sh.sanitize_sql_like(None) == ""
        assert sh.sanitize_sql_like("") == ""

    def test_escapes_wildcards_and_brackets(self):
        assert sh.sanitize_sql_like("a%b_c[d]") == "a\\%b\\_c\\[d]"

    def test_escapes_backslash(self):
        assert sh.sanitize_sql_like("path\\file") == "path\\\\file"


class TestValidateSqlOrderBy:
    def test_allowed_field_passes(self):
        assert sh.validate_sql_order_by("name", {"name", "id"}) == "name"

    def test_disallowed_field_raises(self):
        with pytest.raises(ValueError, match="حقل الترتيب غير مسموح"):
            sh.validate_sql_order_by("DROP TABLE", {"name", "id"})
