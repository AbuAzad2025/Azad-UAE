"""Cov4: pos_features — tier fallback, plan_meets, overrides."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import utils.pos_features as pf


def test_db_tier_exception_returns_none():
    with patch("models.package.Package.query", side_effect=RuntimeError("no db")):
        assert pf._db_tier_level("pro") is None  # lines 50-53


def test_db_tier_bool_not_int():
    pkg = SimpleNamespace(tier_level=True)
    with patch("models.package.Package.query", MagicMock(filter_by=lambda **k: MagicMock(first=lambda: pkg))):
        assert pf._db_tier_level("pro") is None  # isinstance bool guard line 48


def test_tier_level_unknown_slug():
    assert pf._tier_level("no-such-plan") == 0  # line 58 fallback
    assert pf._tier_level(None) >= 0


def test_plan_meets_matrix():
    assert pf.plan_meets("pro", "pro") is True  # line 63
    assert pf.plan_meets("basic", "pro") is False
    assert pf.plan_meets("enterprise", "pro") is True


def test_pos_feature_unknown_raises():
    with pytest.raises(ValueError):  # line 68-69
        pf.pos_feature_enabled(SimpleNamespace(), "nope")


def test_pos_feature_override():
    t = SimpleNamespace(enable_pos_promotions=True, subscription_plan="basic")
    assert pf.pos_feature_enabled(t, "pos_promotions") is True  # 71-72
    t2 = SimpleNamespace(enable_pos_promotions=False, subscription_plan="enterprise")
    assert pf.pos_feature_enabled(t2, "pos_promotions") is False


def test_pos_feature_plan_default():
    t = SimpleNamespace(enable_pos_returns=None, subscription_plan="basic")
    assert pf.pos_feature_enabled(t, "pos_returns") is False  # 73-76 basic < pro
    t2 = SimpleNamespace(subscription_plan="enterprise")
    assert pf.pos_feature_enabled(t2, "pos_returns") is True
