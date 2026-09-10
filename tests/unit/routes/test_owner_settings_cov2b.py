"""Coverage B for routes/owner/settings.py.

Targets: lines 1127, 1166, 1211 + ranges 873-875, 908-910, 968-970,
1028-1030, 1053-1055, 1077-1079, 1104-1106 and arcs 963->974, 965->974,
1146->1148.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from routes.owner import owner_bp


@contextmanager
def _base(**overrides):
    mock_db = overrides.get("mock_db") or MagicMock()
    mock_db.engine = MagicMock()
    atomic = overrides.get("atomic")
    if atomic is None:
        atomic = MagicMock()
        atomic.return_value.__enter__ = MagicMock()
        atomic.return_value.__exit__ = MagicMock(return_value=False)
    patches = [
        patch("routes.owner.settings.render_template", return_value="ok"),
        patch("routes.owner.settings.url_for", return_value="/"),
        patch("routes.owner.settings.db", mock_db),
        patch("routes.owner.settings._invalidate_owner_changes"),
        patch("routes.owner.settings._audit_owner_db_action"),
        patch("services.logging_core.LoggingCore.log_audit"),
        patch("utils.db_safety.atomic_transaction", atomic),
    ]
    for p in patches:
        p.start()
    try:
        yield mock_db
    finally:
        for p in reversed(patches):
            p.stop()


def _raising_atomic():
    atomic = MagicMock()
    atomic.return_value.__enter__ = MagicMock(side_effect=RuntimeError("tx down"))
    atomic.return_value.__exit__ = MagicMock(return_value=False)
    return atomic


class TestSettingsPostExceptions:
    """Ranges 873-875, 908-910, 1028-1030, 1053-1055, 1077-1079, 1104-1106."""

    def test_tax_settings_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        tenant = MagicMock()
        tenant_cls = MagicMock()
        tenant_cls.get_current = MagicMock(return_value=tenant)
        with (
            _base(atomic=_raising_atomic()),
            patch("routes.owner.settings.Tenant", tenant_cls),
        ):
            resp = app.test_client().post("/owner/tax-settings", data={"enable_tax": "on"})
        assert resp.status_code == 302

    def test_currency_settings_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base(atomic=_raising_atomic()):
            resp = app.test_client().post("/owner/currency-settings", data={"default_currency": "AED"})
        assert resp.status_code == 302

    def test_email_settings_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base(atomic=_raising_atomic()):
            resp = app.test_client().post("/owner/email-settings", data={"smtp_server": "x"})
        assert resp.status_code == 302

    def test_sms_settings_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base(atomic=_raising_atomic()):
            resp = app.test_client().post("/owner/sms-settings", data={"sms_provider": "x"})
        assert resp.status_code == 302

    def test_whatsapp_settings_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base(atomic=_raising_atomic()):
            resp = app.test_client().post("/owner/whatsapp-settings", data={"whatsapp_api_key": "x"})
        assert resp.status_code == 302

    def test_notification_templates_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base(atomic=_raising_atomic()):
            resp = app.test_client().post("/owner/notification-templates", data={"invoice_email_template": "x"})
        assert resp.status_code == 302


class TestExchangeRates:
    """Range 968-970 (delete found) + arcs 963->974, 965->974."""

    def test_delete_existing_record(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        rec = MagicMock()
        with (
            _base() as mock_db,
            patch(
                "services.owner_ops_service.OwnerOpsService.find_exchange_rate_record",
                return_value=rec,
            ),
        ):
            resp = app.test_client().post(
                "/owner/exchange-rates",
                data={"action": "delete", "record_id": "5"},
            )
        assert resp.status_code == 302
        mock_db.session.delete.assert_called_once_with(rec)

    def test_unknown_action_goes_to_redirect(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base():
            resp = app.test_client().post("/owner/exchange-rates", data={"action": "unknown-op"})
        assert resp.status_code == 302

    def test_delete_without_id_goes_to_redirect(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base():
            resp = app.test_client().post("/owner/exchange-rates", data={"action": "delete"})
        assert resp.status_code == 302


class TestApiJsonGuards:
    """Lines 1127, 1166, 1211 (empty JSON object is falsy)."""

    def test_update_tenant_settings_empty_json(self, app_factory, bypass_company_admin_auth):
        app = app_factory(owner_bp)
        with _base():
            resp = app.test_client().post("/owner/api/update-tenant-settings", json={})
        assert resp.status_code == 400

    def test_toggle_warehouse_empty_json(self, app_factory, bypass_company_admin_auth):
        app = app_factory(owner_bp)
        with _base():
            resp = app.test_client().post("/owner/api/toggle-warehouse-negative", json={})
        assert resp.status_code == 400

    def test_supervisor_override_empty_json(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base():
            resp = app.test_client().post("/owner/api/supervisor-override", json={})
        assert resp.status_code == 400


class TestApiTenantFieldBranches:
    """Arc 1146->1148 — exercise both else-sub-branches."""

    def _tenant(self):
        t = MagicMock()
        t.id = 1
        return t

    def test_prices_include_vat_branch(self, app_factory, bypass_company_admin_auth):
        app = app_factory(owner_bp)
        tenant = self._tenant()
        with (
            _base() as mock_db,
            patch("routes.owner.settings.get_active_tenant_id", return_value=1),
        ):
            mock_db.session.get.return_value = tenant
            resp = app.test_client().post(
                "/owner/api/update-tenant-settings",
                json={"field": "prices_include_vat", "value": True},
            )
        assert resp.status_code == 200
        assert tenant.prices_include_vat is True

    def test_logo_url_branch(self, app_factory, bypass_company_admin_auth):
        app = app_factory(owner_bp)
        tenant = self._tenant()
        with (
            _base() as mock_db,
            patch("routes.owner.settings.get_active_tenant_id", return_value=1),
        ):
            mock_db.session.get.return_value = tenant
            resp = app.test_client().post(
                "/owner/api/update-tenant-settings",
                json={"field": "logo_url", "value": "  https://x/logo.png  "},
            )
        assert resp.status_code == 200
        assert tenant.logo_url == "https://x/logo.png"
