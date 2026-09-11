"""Cov4: feature_flag_service — key mapping, defaults, require_enabled arcs."""

from __future__ import annotations

import pytest

from services.feature_flag_service import FEATURE_FLAG_KEYS, FeatureFlagService


def test_is_enabled_known_key_true(app):
    app.config["ENABLE_TREASURY"] = True
    assert FeatureFlagService.is_enabled("ENABLE_TREASURY") is True


def test_is_enabled_known_key_defaults_false(app):
    app.config.pop("ENABLE_MWAC", None)
    assert FeatureFlagService.is_enabled("ENABLE_MWAC") is False


def test_is_enabled_unknown_key_passthrough(app):
    app.config["SOME_CUSTOM_FLAG"] = True
    assert FeatureFlagService.is_enabled("SOME_CUSTOM_FLAG") is True
    assert FeatureFlagService.is_enabled("SOME_CUSTOM_FLAG", tenant_id=123) is True
    assert FeatureFlagService.is_enabled("MISSING_FLAG_XYZ") is False


def test_get_all_flags_returns_all_keys(app):
    app.config["ENABLE_TREASURY"] = True
    flags = FeatureFlagService.get_all_flags()
    assert set(flags) == set(FEATURE_FLAG_KEYS)
    assert flags["ENABLE_TREASURY"] is True


def test_require_enabled_passes(app):
    app.config["ENABLE_TREASURY"] = True
    assert FeatureFlagService.require_enabled("ENABLE_TREASURY", tenant_id=1) is None


def test_require_enabled_raises(app):
    app.config["ENABLE_TREASURY"] = False
    with pytest.raises(RuntimeError, match="ENABLE_TREASURY"):
        FeatureFlagService.require_enabled("ENABLE_TREASURY", tenant_id=9)
