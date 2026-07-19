"""Tenant model — get_current, subscription helpers, to_dict."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock


class TestTenantModel:
    def test_get_current_authenticated_active_tenant(self, app, mocker):
        from models.tenant import Tenant

        tenant = MagicMock(id=3, is_active=True)
        mocker.patch("flask_login.utils._get_user")
        user = MagicMock(is_authenticated=True)
        mocker.patch("flask_login.current_user", user)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=3)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = tenant
        mocker.patch.object(Tenant, "query", mock_q)
        with app.test_request_context("/"):
            assert Tenant.get_current() is tenant

    def test_get_current_company_user_via_relationship(self, app, mocker):
        from models.tenant import Tenant

        rel = MagicMock(is_active=True)
        user = MagicMock(is_authenticated=True, tenant=rel)
        mocker.patch("flask_login.current_user", user)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        with app.test_request_context("/"):
            assert Tenant.get_current() is rel

    def test_get_current_inactive_tenant_relationship_returns_none(self, app, mocker):
        from models.tenant import Tenant

        rel = MagicMock(is_active=False)
        user = MagicMock(is_authenticated=True, tenant=rel)
        mocker.patch("flask_login.current_user", user)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        with app.test_request_context("/"):
            assert Tenant.get_current() is None

    def test_get_current_unauthenticated_logs_and_returns_none(self, app, mocker):
        from models.tenant import Tenant

        user = MagicMock(is_authenticated=False)
        mocker.patch("flask_login.current_user", user)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        with app.test_request_context("/", environ_base={"REMOTE_ADDR": "10.0.0.1"}):
            assert Tenant.get_current() is None

    def test_is_subscription_active_no_end_date(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = None
        assert t.is_subscription_active() is True

    def test_is_subscription_active_future_end(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = datetime.now(timezone.utc) + timedelta(days=30)
        assert t.is_subscription_active() is True

    def test_is_subscription_active_expired(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = datetime.now(timezone.utc) - timedelta(days=1)
        assert t.is_subscription_active() is False

    def test_get_remaining_days_open_ended(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = None
        assert t.get_remaining_days() == 9999

    def test_get_remaining_days_countdown(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = datetime.now(timezone.utc) + timedelta(days=10, hours=12)
        assert t.get_remaining_days() >= 10

    def test_get_base_currency_fallback(self):
        from models.tenant import Tenant

        t = Tenant()
        t.base_currency = None
        t.default_currency = "aed"
        assert t.get_base_currency == "AED"

    def test_get_currency_for_display(self, mocker):
        from models.tenant import Tenant

        mocker.patch("utils.currency_utils.get_currency_symbol", return_value="د.إ")
        t = Tenant()
        t.base_currency = "AED"
        assert t.get_currency_for_display() == "د.إ"

    def test_get_current_platform_owner_no_active_tid(self, app, mocker):
        from models.tenant import Tenant

        user = MagicMock(is_authenticated=True)
        mocker.patch("flask_login.current_user", user)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=True)
        with app.test_request_context("/"):
            assert Tenant.get_current() is None

    def test_get_current_swallows_auth_errors(self, app, mocker):
        from models.tenant import Tenant

        class _BrokenUser:
            @property
            def is_authenticated(self):
                raise RuntimeError("auth")

        mocker.patch("flask_login.current_user", _BrokenUser())
        with app.test_request_context("/"):
            assert Tenant.get_current() is None

    def test_to_dict(self):
        from models.tenant import Tenant

        t = Tenant()
        t.id = 1
        t.name = "Co"
        t.name_ar = "شركة"
        t.slug = "co"
        t.business_type = "retail"
        t.country = "AE"
        t.default_currency = "AED"
        t.is_active = True
        t.subscription_plan = "pro"
        assert t.to_dict()["slug"] == "co"

    def test_business_type_label_known_code(self):
        from models.tenant import Tenant

        t = Tenant()
        t.business_type = "batteries"
        assert "بطاريات" in t.business_type_label()

    def test_business_type_label_unknown_code(self):
        from models.tenant import Tenant

        t = Tenant()
        t.business_type = "legacy_garage"
        assert t.business_type_label() == "legacy_garage"

    def test_repr(self):
        from models.tenant import Tenant

        t = Tenant()
        t.name = "Acme"
        assert "Acme" in repr(t)

    def test_extend_subscription_from_none(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = None
        t.extend_subscription(30)
        assert t.subscription_end is not None
        assert t.get_remaining_days() >= 29

    def test_extend_subscription_from_future(self):
        from models.tenant import Tenant

        t = Tenant()
        base = datetime.now(timezone.utc) + timedelta(days=10)
        t.subscription_end = base
        t.extend_subscription(15)
        delta = t.subscription_end - base
        assert delta.days == 15

    def test_extend_subscription_expired_clamps_to_now(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = datetime.now(timezone.utc) - timedelta(days=5)
        t.extend_subscription(7)
        # Clamped to now then +7 days; remaining is 7 days minus sub-second
        # elapsed wall-clock between set and read, so assert a tolerant bound.
        assert t.get_remaining_days() >= 6

    def test_extend_subscription_negative_shortens(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = datetime.now(timezone.utc) + timedelta(days=30)
        t.extend_subscription(-10)
        # Shortened to now+20 days; remaining is 20 days minus sub-second elapsed.
        assert t.get_remaining_days() >= 19

    def test_extend_subscription_zero_is_noop(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = datetime.now(timezone.utc) + timedelta(days=30)
        before = t.subscription_end
        t.extend_subscription(0)
        assert t.subscription_end == before

    def test_set_subscription_end_none_clears(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = datetime.now(timezone.utc) + timedelta(days=5)
        t.set_subscription_end(None)
        assert t.subscription_end is None

    def test_set_subscription_end_iso_string(self):
        from models.tenant import Tenant

        t = Tenant()
        iso = "2030-01-15T00:00:00"
        t.set_subscription_end(iso)
        assert t.subscription_end.year == 2030
        assert t.subscription_end.month == 1

    def test_apply_subscription_plan(self):
        from models.tenant import Tenant

        t = Tenant()
        t.apply_subscription_plan("enterprise", "annual", True)
        assert t.subscription_plan == "enterprise"
        assert t.subscription_plan_duration == "annual"
        assert t.is_trial is True

    def test_immediate_expiration_alert_when_expired(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = datetime.now(timezone.utc) - timedelta(days=1)
        assert t.is_subscription_active() is False
        assert t.get_remaining_days() == 0

    def test_immediate_expiration_alert_when_expiring_soon(self):
        from models.tenant import Tenant

        t = Tenant()
        t.subscription_end = datetime.now(timezone.utc) + timedelta(days=3)
        assert t.is_subscription_active() is True
        assert 0 < t.get_remaining_days() <= 7
