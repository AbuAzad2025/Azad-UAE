"""AI access — tenant levels, platform owner bypass, capability gating."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestTenantAiLevel:
    def test_none_tenant_returns_default(self):
        from utils.ai_access import get_tenant_ai_level

        assert get_tenant_ai_level(None) == "execute"

    def test_reads_custom_setting(self, mocker):
        settings = MagicMock()
        settings.get_custom_setting.return_value = {"1": "advanced"}
        mocker.patch(
            "utils.ai_access.SystemSettings.get_current", return_value=settings
        )
        from utils.ai_access import get_tenant_ai_level

        assert get_tenant_ai_level(1) == "advanced"

    def test_invalid_level_falls_back(self, mocker):
        settings = MagicMock()
        settings.get_custom_setting.return_value = {"2": "godmode"}
        mocker.patch(
            "utils.ai_access.SystemSettings.get_current", return_value=settings
        )
        from utils.ai_access import get_tenant_ai_level

        assert get_tenant_ai_level(2, default="basic") == "basic"

    def test_exception_returns_default(self, mocker):
        mocker.patch(
            "utils.ai_access.SystemSettings.get_current", side_effect=RuntimeError("db")
        )
        from utils.ai_access import get_tenant_ai_level

        assert get_tenant_ai_level(3) == "execute"

    def test_set_tenant_ai_level_normalizes(self, mocker):
        settings = MagicMock()
        settings.get_custom_setting.return_value = {}
        mocker.patch(
            "utils.ai_access.SystemSettings.get_current", return_value=settings
        )
        from utils.ai_access import set_tenant_ai_level

        level = set_tenant_ai_level(5, " ADVANCED ")
        assert level == "advanced"
        settings.set_custom_setting.assert_called_once()

    def test_set_invalid_level_defaults_execute(self, mocker):
        settings = MagicMock()
        settings.get_custom_setting.return_value = {}
        mocker.patch(
            "utils.ai_access.SystemSettings.get_current", return_value=settings
        )
        from utils.ai_access import set_tenant_ai_level

        assert set_tenant_ai_level(1, "invalid") == "execute"


class TestAiAccessState:
    def test_unauthenticated(self):
        from utils.ai_access import get_ai_access_state

        state = get_ai_access_state(user=None)
        assert state["allowed"] is False
        assert state["reason"] == "unauthenticated"

    def test_platform_owner_allowed(self, mocker):
        user = MagicMock(is_authenticated=True)
        mocker.patch("utils.ai_access.is_global_owner_user", return_value=True)
        from utils.ai_access import get_ai_access_state

        state = get_ai_access_state(user=user)
        assert state["allowed"] is True
        assert state["is_platform_user"] is True

    def test_missing_tenant(self, mocker):
        user = MagicMock(is_authenticated=True)
        mocker.patch("utils.ai_access.is_global_owner_user", return_value=False)
        mocker.patch("utils.ai_access.get_active_tenant_id", return_value=None)
        from utils.ai_access import get_ai_access_state

        state = get_ai_access_state(user=user)
        assert state["reason"] == "missing_tenant"

    def test_inactive_tenant(self, mocker):
        user = MagicMock(is_authenticated=True)
        mocker.patch("utils.ai_access.is_global_owner_user", return_value=False)
        mocker.patch("utils.ai_access.get_active_tenant_id", return_value=1)
        mocker.patch(
            "utils.ai_access.db.session.get", return_value=MagicMock(is_active=False)
        )
        from utils.ai_access import get_ai_access_state

        state = get_ai_access_state(user=user)
        assert state["reason"] == "tenant_inactive"

    def test_global_disabled(self, mocker):
        user = MagicMock(is_authenticated=True)
        mocker.patch("utils.ai_access.is_global_owner_user", return_value=False)
        mocker.patch("utils.ai_access.get_active_tenant_id", return_value=1)
        tenant = MagicMock(is_active=True, enable_ai=True)
        mocker.patch("utils.ai_access.db.session.get", return_value=tenant)
        settings = MagicMock(enable_ai_assistant=False)
        mocker.patch(
            "utils.ai_access.SystemSettings.get_current", return_value=settings
        )
        mocker.patch("utils.ai_access.get_tenant_ai_level", return_value="execute")
        from utils.ai_access import get_ai_access_state

        state = get_ai_access_state(user=user)
        assert state["reason"] == "global_disabled"

    def test_tenant_disabled(self, mocker):
        user = MagicMock(is_authenticated=True)
        mocker.patch("utils.ai_access.is_global_owner_user", return_value=False)
        mocker.patch("utils.ai_access.get_active_tenant_id", return_value=1)
        tenant = MagicMock(is_active=True, enable_ai=False)
        mocker.patch("utils.ai_access.db.session.get", return_value=tenant)
        settings = MagicMock(enable_ai_assistant=True)
        mocker.patch(
            "utils.ai_access.SystemSettings.get_current", return_value=settings
        )
        mocker.patch("utils.ai_access.get_tenant_ai_level", return_value="basic")
        from utils.ai_access import get_ai_access_state

        state = get_ai_access_state(user=user)
        assert state["reason"] == "tenant_disabled"

    def test_allowed_tenant(self, mocker):
        user = MagicMock(is_authenticated=True)
        mocker.patch("utils.ai_access.is_global_owner_user", return_value=False)
        mocker.patch("utils.ai_access.get_active_tenant_id", return_value=2)
        tenant = MagicMock(is_active=True, enable_ai=True)
        mocker.patch("utils.ai_access.db.session.get", return_value=tenant)
        settings = MagicMock(enable_ai_assistant=True)
        mocker.patch(
            "utils.ai_access.SystemSettings.get_current", return_value=settings
        )
        mocker.patch("utils.ai_access.get_tenant_ai_level", return_value="advanced")
        from utils.ai_access import get_ai_access_state

        state = get_ai_access_state(user=user)
        assert state["allowed"] is True
        assert state["ai_level"] == "advanced"

    def test_settings_exception_defaults_global_enabled(self, mocker):
        user = MagicMock(is_authenticated=True)
        mocker.patch("utils.ai_access.is_global_owner_user", return_value=True)
        mocker.patch(
            "utils.ai_access.SystemSettings.get_current", side_effect=RuntimeError("x")
        )
        from utils.ai_access import get_ai_access_state

        assert get_ai_access_state(user=user)["allowed"] is True


class TestAiLevelAllows:
    @pytest.mark.parametrize(
        "level,cap,expected",
        [
            ("basic", "basic", True),
            ("basic", "advanced", False),
            ("advanced", "basic", True),
            ("execute", "execute", True),
            ("unknown", "advanced", False),
        ],
    )
    def test_capability_order(self, level, cap, expected):
        from utils.ai_access import ai_level_allows

        assert ai_level_allows(level, cap) is expected
