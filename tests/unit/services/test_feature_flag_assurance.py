"""Feature flag service — tenant overrides, config defaults, require_enabled."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestIsEnabled:
    """is_enabled — resolution order tenant → config → False."""

    def test_tenant_override_wins(self, app, mocker):
        tenant = MagicMock(settings={"ENABLE_TREASURY": True})
        mocker.patch("extensions.db.session").get.return_value = tenant

        from services.feature_flag_service import FeatureFlagService

        with app.app_context():
            assert FeatureFlagService.is_enabled("ENABLE_TREASURY", tenant_id=1) is True

    def test_config_default_when_no_tenant_override(self, app, mocker):
        tenant = MagicMock(settings={"OTHER": True})
        mocker.patch("extensions.db.session").get.return_value = tenant
        app.config["ENABLE_MWAC"] = True

        from services.feature_flag_service import FeatureFlagService

        with app.app_context():
            assert FeatureFlagService.is_enabled("ENABLE_MWAC", tenant_id=1) is True

    def test_false_when_unconfigured(self, app):
        from services.feature_flag_service import FeatureFlagService

        with app.app_context():
            app.config["ENABLE_TREASURY"] = False
            assert FeatureFlagService.is_enabled("ENABLE_TREASURY") is False

    def test_unknown_key_uses_raw_config_name(self, app):
        app.config["CUSTOM_FLAG"] = True
        from services.feature_flag_service import FeatureFlagService

        with app.app_context():
            assert FeatureFlagService.is_enabled("CUSTOM_FLAG") is True


class TestRequireEnabled:
    """require_enabled — raises RuntimeError when disabled."""

    def test_raises_when_disabled(self, app, mocker):
        mocker.patch(
            "services.feature_flag_service.FeatureFlagService.is_enabled",
            return_value=False,
        )
        from services.feature_flag_service import FeatureFlagService

        with app.app_context():
            with pytest.raises(RuntimeError, match="ENABLE_TREASURY"):
                FeatureFlagService.require_enabled("ENABLE_TREASURY", tenant_id=3)

    def test_get_all_flags_resolves_known_keys(self, app, mocker):
        mocker.patch(
            "services.feature_flag_service.FeatureFlagService.is_enabled",
            side_effect=lambda k, tenant_id=None: k == "ENABLE_MWAC",
        )
        from services.feature_flag_service import FEATURE_FLAG_KEYS, FeatureFlagService

        with app.app_context():
            flags = FeatureFlagService.get_all_flags(tenant_id=1)
        assert set(flags.keys()) == set(FEATURE_FLAG_KEYS.keys())
        assert flags["ENABLE_MWAC"] is True
