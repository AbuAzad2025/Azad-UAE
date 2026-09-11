"""Gap coverage for models/tenant.py — currency, subscription, labels."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from models.tenant import Tenant


def _tenant(**kwargs):
    params = {"name": "Cov Tenant", "name_ar": "مستأجر", "slug": "cov-tenant"}
    params.update(kwargs)
    return Tenant(**params)


class TestBaseCurrency:
    def test_normalizes(self):
        assert _tenant(base_currency=" aed ").get_base_currency == "AED"

    def test_falls_back_to_default(self):
        assert _tenant(base_currency=None, default_currency="usd").get_base_currency == "USD"

    def test_falls_back_to_ils(self):
        assert _tenant(base_currency=None, default_currency=None).get_base_currency == "ILS"

    def test_display_symbol(self):
        assert isinstance(_tenant(base_currency="AED").get_currency_for_display(), str)


class TestBusinessTypeLabel:
    def test_unknown_code(self):
        assert _tenant(business_type="nope").business_type_label() == "nope"

    def test_both_langs(self):
        label = _tenant(business_type="general").business_type_label(lang="both")
        assert "/" in label

    def test_none_business_type(self):
        label = _tenant(business_type=None).business_type_label()
        assert str(label)


class TestGetCurrent:
    def test_no_user_returns_none(self):
        assert Tenant.get_current() is None

    def test_anonymous_user_returns_none(self):
        user = SimpleNamespace(is_authenticated=False)
        assert Tenant.get_current(user=user) is None

    def test_broken_user_returns_none(self):
        user = SimpleNamespace(is_authenticated=True)
        assert Tenant.get_current(user=user) is None


class TestSubscription:
    def test_is_lifetime(self):
        assert _tenant(subscription_plan_duration="lifetime").is_lifetime is True
        assert _tenant(subscription_plan_duration="monthly").is_lifetime is False

    def test_active_lifetime(self):
        assert _tenant(subscription_plan_duration="lifetime").is_subscription_active() is True

    def test_active_future_naive(self):
        end = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=3)
        assert _tenant(subscription_end=end).is_subscription_active() is True

    def test_inactive_past(self):
        end = datetime.now(UTC) - timedelta(days=1)
        assert _tenant(subscription_end=end).is_subscription_active() is False

    def test_active_no_end(self):
        assert _tenant(subscription_end=None).is_subscription_active() is True

    def test_remaining_lifetime(self):
        assert _tenant(subscription_plan_duration="lifetime").get_remaining_days() == 9999

    def test_remaining_future_naive(self):
        end = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=5)
        assert _tenant(subscription_end=end).get_remaining_days() >= 4

    def test_remaining_past_clamped(self):
        end = datetime.now(UTC) - timedelta(days=5)
        assert _tenant(subscription_end=end).get_remaining_days() == 0

    def test_remaining_none(self):
        assert _tenant(subscription_end=None).get_remaining_days() == 9999

    def test_duration_display(self):
        assert _tenant(subscription_plan_duration="monthly").get_subscription_duration_display() == "شهري"
        assert _tenant(subscription_plan_duration="annual").get_subscription_duration_display(lang="en") == "Annual"
        assert _tenant(subscription_plan_duration="x").get_subscription_duration_display() == "x"


class TestMutations:
    def test_extend_zero_days(self):
        tenant = _tenant()
        assert tenant.extend_subscription(0) is tenant
        assert tenant.subscription_end is None

    def test_extend_unset_base(self):
        tenant = _tenant(subscription_end=None)
        tenant.extend_subscription(10)
        assert tenant.subscription_end is not None
        assert tenant.updated_at is not None

    def test_extend_past_base_resets_to_now(self):
        tenant = _tenant(subscription_end=datetime.now(UTC) - timedelta(days=30))
        tenant.extend_subscription(5)
        assert tenant.subscription_end > datetime.now(UTC)

    def test_extend_future_base_adds(self):
        base = datetime.now(UTC) + timedelta(days=20)
        tenant = _tenant(subscription_end=base)
        tenant.extend_subscription(5)
        assert tenant.subscription_end.date() == (base + timedelta(days=5)).date()

    def test_extend_naive_base(self):
        tenant = _tenant(subscription_end=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=2))
        tenant.extend_subscription(3)
        assert tenant.subscription_end is not None

    def test_extend_negative(self):
        tenant = _tenant(subscription_end=datetime.now(UTC) + timedelta(days=20))
        tenant.extend_subscription(-5)
        assert tenant.subscription_end is not None

    def test_set_end_none_and_empty(self):
        tenant = _tenant(subscription_end=datetime.now(UTC))
        tenant.set_subscription_end(None)
        assert tenant.subscription_end is None
        tenant.set_subscription_end("")
        assert tenant.subscription_end is None

    def test_set_end_iso_string(self):
        tenant = _tenant()
        tenant.set_subscription_end("2030-05-01T00:00:00")
        assert tenant.subscription_end.year == 2030

    def test_set_end_datetime(self):
        end = datetime.now(UTC) + timedelta(days=9)
        tenant = _tenant()
        tenant.set_subscription_end(end)
        assert tenant.subscription_end == end

    def test_apply_plan_all_none(self):
        tenant = _tenant(subscription_plan="basic")
        tenant.apply_subscription_plan(None, None, None)
        assert tenant.subscription_plan == "basic"
        assert tenant.updated_at is not None

    def test_apply_plan_values(self):
        tenant = _tenant()
        tenant.apply_subscription_plan("pro", "annual", True)
        assert tenant.subscription_plan == "pro"
        assert tenant.subscription_plan_duration == "annual"
        assert tenant.is_trial is True


class TestToDict:
    def test_with_end(self):
        tenant = _tenant(subscription_end=datetime(2030, 1, 1, tzinfo=UTC))
        data = tenant.to_dict()
        assert data["subscription_end"] == "2030-01-01T00:00:00+00:00"
        assert data["slug"] == "cov-tenant"

    def test_without_end(self):
        assert _tenant(subscription_end=None).to_dict()["subscription_end"] is None

    def test_repr(self):
        assert "Cov Tenant" in repr(_tenant())
