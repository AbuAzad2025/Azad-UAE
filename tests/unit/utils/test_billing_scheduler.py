"""Behavioral tests for utils.billing_scheduler (subscription lifecycle)."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import utils.billing_scheduler as billing_scheduler
from utils.billing_scheduler import (
    REMINDER_WINDOW_DAYS,
    _get_tenant_admin_email,
    _resolve_whatsapp_number,
    _send_expiry_reminder,
    _suspend_tenant,
    run_subscription_check,
)

FIXED_NOW = datetime(2026, 8, 26, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def frozen_now(monkeypatch):
    """Freeze utils.billing_scheduler's datetime.now at FIXED_NOW (or a custom moment)."""

    def _freeze(moment=FIXED_NOW):
        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return moment.replace(tzinfo=None)
                return moment.astimezone(tz)

        monkeypatch.setattr(billing_scheduler, "datetime", FrozenDateTime)
        return moment

    return _freeze


@pytest.fixture
def wa_config(monkeypatch, app):
    """Point DEVELOPER_WHATSAPP at a normalized-on-read number for this test only."""

    def _set(raw):
        monkeypatch.setitem(app.config, "DEVELOPER_WHATSAPP", raw)
        return raw

    return _set


def _make_tenant(db_session, label, *, end=None, duration="monthly", active=True, suspended=False):
    from models import Tenant

    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Sched {label} {suffix}",
        name_ar="جدولة",
        slug=f"sched-{label}-{suffix}",
        email=f"sched-{label}-{suffix}@test.local",
        phone_1="0500000000",
        country="AE",
        subscription_plan="basic",
        subscription_plan_duration=duration,
        default_currency="AED",
        base_currency="AED",
    )
    tenant.is_active = active
    tenant.is_suspended = suspended
    tenant.subscription_end = end
    db_session.add(tenant)
    db_session.commit()
    return tenant


def _baseline():
    """Snapshot scheduler counts before creating fixtures (leak-proof deltas)."""
    return run_subscription_check()


def _fake_db_returning(tenants):
    """A db stand-in whose query().filter()*N.all() yields the given tenants."""
    result = MagicMock(name="query_result")
    result.filter.return_value = result  # idempotent filter chaining
    result.all.return_value = list(tenants)
    return SimpleNamespace(session=SimpleNamespace(query=MagicMock(return_value=result)))


class TestRunSubscriptionCheck:
    def test_full_lifecycle_suspend_remind_and_active(self, db_session, frozen_now, mocker, wa_config):
        moment = frozen_now()
        wa_config("00971 50 123 4567")
        send_mock = mocker.patch(
            "services.whatsapp_service.WhatsAppService.send_custom_message",
            return_value={"success": True},
        )
        before = _baseline()

        expired = _make_tenant(db_session, "expired", end=moment - timedelta(hours=2))
        soon = _make_tenant(db_session, "soon", end=moment + timedelta(days=2))
        _make_tenant(db_session, "healthy", end=moment + timedelta(days=40))

        summary = run_subscription_check()

        assert summary["suspended"] == before["suspended"] + 1
        assert summary["reminded"] == before["reminded"] + 1
        assert summary["active"] == before["active"] + 1
        assert summary["total"] == before["total"] + 3

        db_session.expire(expired)
        assert expired.is_active is False
        assert expired.is_suspended is True
        assert expired.suspension_reason.startswith("Subscription expired on ")
        assert (moment - timedelta(hours=2)).isoformat() in expired.suspension_reason

        send_mock.assert_called_once()
        phone, message = send_mock.call_args[0]
        assert phone == "971501234567"
        assert f"ينتهي خلال {2} يوم" in message

        db_session.expire(soon)
        assert soon.is_active is True
        assert soon.is_suspended is False

    def test_boundaries_exact_now_suspends_exact_cutoff_reminds(self, db_session, frozen_now, mocker, wa_config):
        moment = frozen_now()
        wa_config("971501234567")
        mocker.patch(
            "services.whatsapp_service.WhatsAppService.send_custom_message",
            return_value={"success": True},
        )
        before = _baseline()

        _make_tenant(db_session, "edge-now", end=moment)  # end <= now → suspend
        _make_tenant(db_session, "edge-cutoff", end=moment + timedelta(days=REMINDER_WINDOW_DAYS))

        summary = run_subscription_check()

        assert summary["suspended"] == before["suspended"] + 1
        assert summary["reminded"] == before["reminded"] + 1

    def test_non_billable_tenants_are_skipped(self, db_session, frozen_now, mocker):
        moment = frozen_now()
        past = moment - timedelta(days=1)
        send_mock = mocker.patch(
            "services.whatsapp_service.WhatsAppService.send_custom_message",
            return_value={"success": True},
        )
        before = _baseline()

        lifetime = _make_tenant(db_session, "lifetime", end=past, duration="lifetime")
        inactive = _make_tenant(db_session, "inactive", end=past, active=False)
        already_suspended = _make_tenant(db_session, "susp", end=past, suspended=True)
        no_end = _make_tenant(db_session, "noend", end=None)

        summary = run_subscription_check()

        assert summary["total"] == before["total"]
        assert summary["suspended"] == before["suspended"]
        assert summary["reminded"] == before["reminded"]
        assert summary["active"] == before["active"]
        send_mock.assert_not_called()

        for tenant, expected_active in ((lifetime, True), (inactive, False)):
            db_session.expire(tenant)
            assert tenant.is_active is expected_active
            assert tenant.is_suspended is False
        db_session.expire(already_suspended)
        assert already_suspended.is_suspended is True
        assert no_end.is_suspended is False

    def test_naive_expiry_is_normalized_before_comparison(self, app, frozen_now, monkeypatch):
        """Naive subscription_end values must still be classified, not crash."""
        frozen_now()
        naive_end = FIXED_NOW.replace(tzinfo=None) - timedelta(days=5)
        tenant = SimpleNamespace(
            id=555001,
            subscription_end=naive_end,
            is_active=True,
            is_suspended=False,
            suspension_reason=None,
            subscription_plan_duration="monthly",
        )
        fake_db = _fake_db_returning([tenant])
        monkeypatch.setattr(billing_scheduler, "db", fake_db)

        summary = run_subscription_check()

        assert summary == {"reminded": 0, "suspended": 1, "active": 0, "total": 1}
        assert tenant.is_active is False
        assert tenant.is_suspended is True


class TestSuspendTenant:
    def test_suspend_success_returns_true(self, db_session):
        tenant = _make_tenant(db_session, "victim", end=FIXED_NOW - timedelta(days=1))
        assert _suspend_tenant(tenant) is True
        assert tenant.is_active is False
        assert tenant.is_suspended is True
        assert "Subscription expired on" in tenant.suspension_reason

    def test_suspend_failure_returns_false_and_logs(self, caplog):
        class ExplodingEnd:
            def isoformat(self):
                raise RuntimeError("iso boom")

        tenant = SimpleNamespace(
            id=424242,
            subscription_end=ExplodingEnd(),
            is_active=True,
            is_suspended=False,
            suspension_reason=None,
        )

        with caplog.at_level(logging.ERROR, logger="utils.billing_scheduler"):
            result = _suspend_tenant(tenant)

        assert result is False
        assert any("Failed to suspend tenant 424242" in r.message for r in caplog.records)

    def test_failed_suspension_not_counted_as_suspended(self, app, frozen_now, monkeypatch, caplog):
        """Regression: a failed DB commit must not inflate the 'suspended' metric."""
        frozen_now()

        class ExplodingIsoDatetime(datetime):
            def isoformat(self, *args, **kwargs):
                raise RuntimeError("db down")

        exploding = SimpleNamespace(
            id=777001,
            subscription_end=ExplodingIsoDatetime(2026, 8, 20, tzinfo=UTC),
            is_active=True,
            is_suspended=False,
            suspension_reason=None,
        )
        fake_db = _fake_db_returning([exploding])
        monkeypatch.setattr(billing_scheduler, "db", fake_db)

        with caplog.at_level(logging.ERROR, logger="utils.billing_scheduler"):
            summary = run_subscription_check()

        assert summary["total"] == 1
        assert summary["suspended"] == 0
        assert any("Failed to suspend tenant 777001" in r.message for r in caplog.records)


class TestSendExpiryReminder:
    def test_sends_message_with_days_left(self, app, frozen_now, mocker, wa_config, caplog):
        moment = frozen_now()
        wa_config("+971-50-123-4567")
        send_mock = mocker.patch(
            "services.whatsapp_service.WhatsAppService.send_custom_message",
            return_value={"success": True},
        )
        tenant = SimpleNamespace(id=987654, subscription_end=moment + timedelta(days=2))

        with caplog.at_level(logging.INFO, logger="utils.billing_scheduler"):
            _send_expiry_reminder(tenant)

        send_mock.assert_called_once()
        phone, message = send_mock.call_args[0]
        assert phone == "971501234567"
        assert "ينتهي خلال 2 يوم" in message
        assert any(f"Expiry reminder sent for tenant {tenant.id}" in r.message for r in caplog.records)

    def test_naive_subscription_end_does_not_crash_reminder(self, app, frozen_now, mocker, wa_config):
        """Regression: naive DB datetimes previously raised TypeError inside the try block."""
        frozen_now()
        wa_config("971501234567")
        send_mock = mocker.patch(
            "services.whatsapp_service.WhatsAppService.send_custom_message",
            return_value={"success": True},
        )
        naive_end = FIXED_NOW.replace(tzinfo=None) + timedelta(days=2)
        tenant = SimpleNamespace(id=987655, subscription_end=naive_end)

        _send_expiry_reminder(tenant)

        phone, message = send_mock.call_args[0]
        assert phone == "971501234567"
        assert "ينتهي خلال 2 يوم" in message

    def test_provider_failure_logs_warning(self, app, frozen_now, mocker, wa_config, caplog):
        frozen_now()
        wa_config("971501234567")
        mocker.patch(
            "services.whatsapp_service.WhatsAppService.send_custom_message",
            return_value={"success": False, "error": "gateway down"},
        )
        tenant = SimpleNamespace(id=987656, subscription_end=FIXED_NOW + timedelta(days=1))

        with caplog.at_level(logging.WARNING, logger="utils.billing_scheduler"):
            _send_expiry_reminder(tenant)

        assert any("Reminder failed for tenant" in r.message and "gateway down" in r.message for r in caplog.records)

    def test_unexpected_exception_logs_error(self, app, frozen_now, mocker, wa_config, caplog):
        frozen_now()
        wa_config("971501234567")
        mocker.patch(
            "services.whatsapp_service.WhatsAppService.send_custom_message",
            side_effect=RuntimeError("boom"),
        )
        tenant = SimpleNamespace(id=987657, subscription_end=FIXED_NOW + timedelta(days=1))

        with caplog.at_level(logging.ERROR, logger="utils.billing_scheduler"):
            _send_expiry_reminder(tenant)

        assert any("Failed to send reminder for tenant 987657" in r.message for r in caplog.records)


class TestWhatsAppResolution:
    def test_skips_reminder_when_no_number_anywhere(self, app, monkeypatch, mocker, caplog):
        monkeypatch.setitem(app.config, "DEVELOPER_WHATSAPP", "")
        mocker.patch(
            "models.system_settings.SystemSettings.get_current",
            side_effect=RuntimeError("no settings table"),
        )
        send_mock = mocker.patch("services.whatsapp_service.WhatsAppService.send_custom_message")
        tenant = SimpleNamespace(id=987658, subscription_end=FIXED_NOW + timedelta(days=1))

        with caplog.at_level(logging.WARNING, logger="utils.billing_scheduler"):
            _send_expiry_reminder(tenant)

        send_mock.assert_not_called()
        assert any("WhatsApp not configured" in r.message for r in caplog.records)

    def test_resolve_digits_from_app_config(self, app, monkeypatch):
        monkeypatch.setitem(app.config, "DEVELOPER_WHATSAPP", "+971 (50) 123-4567")
        assert _resolve_whatsapp_number() == "971501234567"

    def test_resolve_strips_leading_double_zero(self, app, monkeypatch):
        monkeypatch.setitem(app.config, "DEVELOPER_WHATSAPP", "00971501234567")
        assert _resolve_whatsapp_number() == "971501234567"

    def test_falls_back_to_system_settings(self, app, monkeypatch, mocker):
        monkeypatch.setitem(app.config, "DEVELOPER_WHATSAPP", "")
        settings_stub = SimpleNamespace(get_custom_setting=lambda key: " 971-52-999-8877 ")
        mocker.patch("models.system_settings.SystemSettings.get_current", return_value=settings_stub)
        assert _resolve_whatsapp_number() == "971529998877"

    def test_settings_failure_yields_empty_number(self, app, monkeypatch, mocker):
        monkeypatch.setitem(app.config, "DEVELOPER_WHATSAPP", "")
        mocker.patch(
            "models.system_settings.SystemSettings.get_current",
            side_effect=RuntimeError("db offline"),
        )
        assert _resolve_whatsapp_number() == ""

    def test_empty_everywhere_yields_empty_number(self, app, monkeypatch, mocker):
        monkeypatch.setitem(app.config, "DEVELOPER_WHATSAPP", "")
        settings_stub = SimpleNamespace(get_custom_setting=lambda key, default=None: None)
        mocker.patch("models.system_settings.SystemSettings.get_current", return_value=settings_stub)
        assert _resolve_whatsapp_number() == ""


class TestGetTenantAdminEmail:
    def test_returns_lowest_id_company_admin_email(self, db_session):
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="super_admin").first()
        if role is None:
            role = Role(name="Super Admin", slug="super_admin", is_active=True)
            db_session.add(role)
            db_session.commit()

        suffix = uuid.uuid4().hex[:8]
        tenant = _make_tenant(db_session, f"admin-t{suffix}")
        first = User(
            username=f"adm1-{suffix}",
            email=f"adm1-{suffix}@example.com",
            full_name="Admin One",
            tenant_id=tenant.id,
            role_id=role.id,
        )
        first.set_password("password123")
        second = User(
            username=f"adm2-{suffix}",
            email=f"adm2-{suffix}@example.com",
            full_name="Admin Two",
            tenant_id=tenant.id,
            role_id=role.id,
        )
        second.set_password("password123")
        db_session.add_all([first, second])
        db_session.commit()

        assert _get_tenant_admin_email(tenant.id) == first.email

    def test_returns_empty_string_without_admin(self, db_session):
        suffix = uuid.uuid4().hex[:8]
        tenant = _make_tenant(db_session, f"noadmin-{suffix}")
        assert _get_tenant_admin_email(tenant.id) == ""
