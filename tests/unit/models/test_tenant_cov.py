"""Coverage tests for models/tenant.py uncovered lines/arcs.

Targets:
  lines 217 (lifetime subscription active), 227 (lifetime remaining days),
  239 (subscription duration display), 276 (set end with datetime),
  arcs 192->194 (active tid miss falls through), 194->205 (platform owner
  short-circuit), 198-203 (exception path in _get_current_uncached).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock


class TestLifetimeBranches:
    def test_line_217_lifetime_is_active(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_plan_duration = "lifetime"
        t.subscription_end = datetime.now(UTC) - timedelta(days=365)
        assert t.is_lifetime is True
        assert t.is_subscription_active() is True

    def test_line_227_lifetime_remaining_days(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_plan_duration = "lifetime"
        t.subscription_end = None
        assert t.get_remaining_days() == 9999


class TestDurationDisplay:
    def test_line_239_arabic_labels(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_plan_duration = "monthly"
        assert t.get_subscription_duration_display() == "شهري"
        t.subscription_plan_duration = "annual"
        assert t.get_subscription_duration_display() == "سنوي"

    def test_line_239_english_labels(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_plan_duration = "monthly"
        assert t.get_subscription_duration_display(lang="en") == "Monthly"
        t.subscription_plan_duration = "lifetime"
        assert t.get_subscription_duration_display(lang="en") == "Lifetime"

    def test_line_239_unknown_duration_echoes(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_plan_duration = "biennial"
        assert t.get_subscription_duration_display() == "biennial"


class TestSetSubscriptionEnd:
    def test_line_276_datetime_value(self):
        from models.tenant import Tenant

        t = Tenant()
        end = datetime.now(UTC) + timedelta(days=45)
        t.set_subscription_end(end)
        assert t.subscription_end == end
        assert t.updated_at is not None

    def test_set_subscription_end_empty_string_clears(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = datetime.now(UTC) + timedelta(days=5)
        t.set_subscription_end("")
        assert t.subscription_end is None


class TestGetCurrentArcs:
    def test_arc_192_194_active_tid_miss_falls_through_to_rel(self, app, mocker):
        from models.tenant import Tenant

        rel = MagicMock(is_active=True)
        user = MagicMock(is_authenticated=True, tenant=rel)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=7)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch.object(Tenant, "query", mock_q)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        with app.test_request_context("/"):
            assert Tenant.get_current(user=user) is rel

    def test_arc_194_205_platform_owner_no_tenant_returns_none(self, app, mocker):
        from models.tenant import Tenant

        user = MagicMock(is_authenticated=True)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=True)
        with app.test_request_context("/"):
            assert Tenant.get_current(user=user) is None

    def test_arc_198_203_resolver_exception_returns_none(self, app, mocker):
        from models.tenant import Tenant

        user = MagicMock(is_authenticated=True)
        mocker.patch(
            "utils.tenanting.get_active_tenant_id",
            side_effect=RuntimeError("resolver boom"),
        )
        with app.test_request_context("/"):
            assert Tenant.get_current(user=user) is None
