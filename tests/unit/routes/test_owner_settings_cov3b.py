"""Coverage cov3b for routes/owner/settings.py.

Targets: lines 1127, 1166, 1211 + ranges 745-747, 755-756, 873-875,
908-910, 968-970, 1028-1030, 1053-1055, 1077-1079, 1104-1106
and arcs 555->573, 575->592, 963->974, 965->974, 1146->1148.
Real test-client paths; mocks only at service/DB boundaries.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

from routes.owner import owner_bp


def _atomic():
    atomic = MagicMock()
    atomic.return_value.__enter__ = MagicMock()
    atomic.return_value.__exit__ = MagicMock(return_value=False)
    return atomic


def _raising_atomic():
    atomic = MagicMock()
    atomic.return_value.__enter__ = MagicMock(side_effect=RuntimeError("tx down"))
    atomic.return_value.__exit__ = MagicMock(return_value=False)
    return atomic


@contextmanager
def _base(**overrides):
    mock_db = overrides.get("mock_db") or MagicMock()
    mock_db.engine = MagicMock()
    atomic = overrides.get("atomic") or _atomic()
    specs = [
        patch("routes.owner.settings.render_template", return_value="ok"),
        patch("routes.owner.settings.url_for", return_value="/"),
        patch("routes.owner.settings.db", mock_db),
        patch("routes.owner.settings._invalidate_owner_changes"),
        patch("routes.owner.settings._audit_owner_db_action"),
        patch("routes.owner.settings.atomic_transaction", atomic),
        patch("utils.db_safety.atomic_transaction", atomic),
        patch("services.logging_core.LoggingCore.log_audit"),
    ]
    with ExitStack() as stack:
        for spec in specs:
            stack.enter_context(spec)
        yield mock_db


class TestSettingsPostExceptionsCov3b:
    """Ranges 873-875, 908-910, 1028-1030, 1053-1055, 1077-1079, 1104-1106."""

    def test_cov3_tax_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        tenant_cls = MagicMock()
        tenant_cls.get_current = MagicMock(return_value=MagicMock())
        with (
            _base(atomic=_raising_atomic()),
            patch("routes.owner.settings.Tenant", tenant_cls),
        ):
            resp = app.test_client().post("/owner/tax-settings", data={"enable_tax": "on"})
        assert resp.status_code == 302

    def test_cov3_currency_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base(atomic=_raising_atomic()):
            resp = app.test_client().post("/owner/currency-settings", data={"default_currency": "AED"})
        assert resp.status_code == 302

    def test_cov3_email_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base(atomic=_raising_atomic()):
            resp = app.test_client().post("/owner/email-settings", data={"smtp_server": "x"})
        assert resp.status_code == 302

    def test_cov3_sms_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base(atomic=_raising_atomic()):
            resp = app.test_client().post("/owner/sms-settings", data={"sms_provider": "x"})
        assert resp.status_code == 302

    def test_cov3_whatsapp_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base(atomic=_raising_atomic()):
            resp = app.test_client().post("/owner/whatsapp-settings", data={"whatsapp_api_key": "x"})
        assert resp.status_code == 302

    def test_cov3_notification_templates_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base(atomic=_raising_atomic()):
            resp = app.test_client().post("/owner/notification-templates", data={"invoice_email_template": "x"})
        assert resp.status_code == 302


class TestExchangeRatesCov3b:
    """Range 968-970 (delete found) + arcs 963->974, 965->974."""

    def test_cov3_delete_existing_record(self, app_factory, bypass_owner_auth):
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

    def test_cov3_unknown_action_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base():
            resp = app.test_client().post("/owner/exchange-rates", data={"action": "unknown-op"})
        assert resp.status_code == 302

    def test_cov3_delete_without_id_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base():
            resp = app.test_client().post("/owner/exchange-rates", data={"action": "delete"})
        assert resp.status_code == 302


class TestApiJsonGuardsCov3b:
    """Lines 1127, 1166, 1211 (empty JSON object is falsy)."""

    def test_cov3_update_tenant_empty_json(self, app_factory, bypass_company_admin_auth):
        app = app_factory(owner_bp)
        with _base():
            resp = app.test_client().post("/owner/api/update-tenant-settings", json={})
        assert resp.status_code == 400

    def test_cov3_toggle_warehouse_empty_json(self, app_factory, bypass_company_admin_auth):
        app = app_factory(owner_bp)
        with _base():
            resp = app.test_client().post("/owner/api/toggle-warehouse-negative", json={})
        assert resp.status_code == 400

    def test_cov3_supervisor_override_empty_json(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base():
            resp = app.test_client().post("/owner/api/supervisor-override", json={})
        assert resp.status_code == 400


class TestApiTenantFieldsCov3b:
    """Arc 1146->1148 — both else-sub-branches."""

    def _tenant(self):
        t = MagicMock()
        t.id = 1
        return t

    def test_cov3_prices_include_vat(self, app_factory, bypass_company_admin_auth):
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

    def test_cov3_logo_url(self, app_factory, bypass_company_admin_auth):
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


class TestPreviewReceiptCov3b:
    """Ranges 745-747 (other tenant) and 755-756 (currency fallback)."""

    def _common(self, stack):
        settings = MagicMock()
        settings.enable_qr_code = False
        settings.company_name_ar = "شركة"
        inv_cls = MagicMock()
        inv_cls.get_active = MagicMock(return_value=settings)
        stack.enter_context(patch("models.invoice_settings.InvoiceSettings", inv_cls))
        stack.enter_context(patch("utils.tenant_branding.get_print_header_context", return_value={}))

    def test_cov3_other_tenant(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _base(),
            ExitStack() as stack,
        ):
            self._common(stack)
            stack.enter_context(patch("utils.tenanting.get_active_tenant_id", return_value=1))
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            stack.enter_context(patch("utils.tenanting.without_tenant_scope", return_value=ctx))
            stack.enter_context(patch("models.Tenant.get_current", return_value=MagicMock()))
            resp = app.test_client().get("/owner/preview-receipt/modern?tenant_id=99")
        assert resp.status_code == 200

    def test_cov3_currency_fallback(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _base(),
            ExitStack() as stack,
        ):
            self._common(stack)
            stack.enter_context(patch("utils.tenanting.get_active_tenant_id", return_value=1))
            stack.enter_context(patch("models.Tenant.get_current", side_effect=RuntimeError("no tenant")))
            stack.enter_context(
                patch("routes.owner.settings.get_system_default_currency", return_value="AED"),
            )
            resp = app.test_client().get("/owner/preview-receipt/modern")
        assert resp.status_code == 200


class TestInvoiceUploadSkipCov3b:
    """Arcs 555->573 (no logo) and 575->592 (no watermark)."""

    def test_cov3_post_without_files(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        settings = MagicMock()
        settings.default_currency = "AED"
        settings.auto_update_rates = False
        settings.notification_templates = {}
        settings.enable_qr_code = False
        settings.company_name_ar = "شركة"
        inv_cls = MagicMock()
        inv_cls.get_active = MagicMock(return_value=settings)
        with (
            _base(),
            patch("routes.owner.settings.InvoiceSettings", inv_cls),
        ):
            resp = app.test_client().post(
                "/owner/invoice-settings",
                data={"company_name_ar": "شركة", "company_name_en": "Co"},
            )
        assert resp.status_code == 302
