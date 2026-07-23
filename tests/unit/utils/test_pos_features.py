"""POS Phase 4 — SaaS sub-feature flags: plan mapping, overrides, decorator wiring."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from utils.pos_features import POS_SUBFEATURES, plan_meets, pos_feature_enabled


def _tenant(plan="basic", **flags):
    defaults = {
        "enable_pos_promotions": None,
        "enable_pos_multi_tender": None,
        "enable_pos_returns": None,
        "enable_pos_shifts": None,
    }
    defaults.update(flags)
    return SimpleNamespace(subscription_plan=plan, **defaults)


class TestPlanMeets:
    def test_hierarchy(self):
        assert plan_meets("basic", "basic") is True
        assert plan_meets("basic", "pro") is False
        assert plan_meets("pro", "pro") is True
        assert plan_meets("enterprise", "pro") is True
        assert plan_meets("pro", "enterprise") is False

    def test_none_plan_defaults_basic(self):
        assert plan_meets(None, "pro") is False
        assert plan_meets(None, "basic") is True


class TestFeatureResolution:
    @pytest.mark.parametrize("feature", sorted(POS_SUBFEATURES))
    def test_basic_tenant_inherits_off(self, feature):
        assert pos_feature_enabled(_tenant("basic"), feature) is False

    @pytest.mark.parametrize("feature", sorted(POS_SUBFEATURES))
    def test_pro_tenant_inherits_on(self, feature):
        assert pos_feature_enabled(_tenant("pro"), feature) is True

    @pytest.mark.parametrize("feature", sorted(POS_SUBFEATURES))
    def test_enterprise_tenant_inherits_on(self, feature):
        assert pos_feature_enabled(_tenant("enterprise"), feature) is True

    def test_explicit_true_overrides_basic_plan(self):
        tenant = _tenant("basic", enable_pos_promotions=True)
        assert pos_feature_enabled(tenant, "pos_promotions") is True

    def test_explicit_false_overrides_pro_plan(self):
        tenant = _tenant("pro", enable_pos_returns=False)
        assert pos_feature_enabled(tenant, "pos_returns") is False

    def test_unknown_feature_raises(self):
        with pytest.raises(ValueError, match="Unknown POS sub-feature"):
            pos_feature_enabled(_tenant("pro"), "pos_time_travel")


class TestDecoratorWiring:
    def test_feature_columns_include_pos_subfeatures(self):
        from utils.decorators import _FEATURE_COLUMNS

        for feature in POS_SUBFEATURES:
            assert feature in _FEATURE_COLUMNS

    def test_require_subscription_feature_none_inherits_plan(self, app, mocker):
        """NULL column on a basic tenant → 403; on pro → passes."""
        from utils.decorators import require_subscription_feature

        basic = _tenant("basic")
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        session = mocker.patch("utils.decorators.db.session")
        session.get.return_value = basic

        @require_subscription_feature("pos_returns")
        def handler():
            return "ok"

        with app.test_request_context():
            with pytest.raises(Exception) as excinfo:
                handler()
            assert getattr(excinfo.value, "code", None) == 403

        session.get.return_value = _tenant("pro")
        with app.test_request_context():
            assert handler() == "ok"
