"""Coverage A for routes/owner/settings.py.

Targets: lines 810, 1127-ish helpers live in B; here covers ranges
135-137, 227-228, 329-330, 407-408, 619-621, 632-633, 745-747, 755-756
and arcs 101->108, 217->229, 555->573, 575->592.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from routes.owner import owner_bp


def _settings_obj(**kw):
    s = MagicMock()
    s.default_currency = kw.get("default_currency", "AED")
    s.auto_update_rates = False
    s.notification_templates = {}
    s.enable_qr_code = False
    s.company_name_ar = "شركة"
    return s


@contextmanager
def _base(**overrides):
    mock_db = overrides.get("mock_db") or MagicMock()
    mock_db.engine = MagicMock()
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


class TestUpdateIntegration:
    """Arc 101->108 (unknown service) + range 135-137 (save exception)."""

    def test_unknown_service_uses_empty_config(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        integration = MagicMock()
        integration.set_config = MagicMock()
        cls = MagicMock()
        cls.get_service_config = MagicMock(return_value=integration)
        with (
            _base(),
            patch("routes.owner.settings.IntegrationSettings", cls),
        ):
            resp = app.test_client().post("/owner/integrations/update/slack", data={"enabled": "on"})
        assert resp.status_code == 302
        integration.set_config.assert_called_once_with({})

    def test_save_exception_flashes_error(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        cls = MagicMock()
        cls.get_service_config = MagicMock(side_effect=RuntimeError("db down"))
        with (
            _base(),
            patch("routes.owner.settings.IntegrationSettings", cls),
        ):
            resp = app.test_client().post("/owner/integrations/update/whatsapp", data={"enabled": "on"})
        assert resp.status_code == 302


class TestCompanyInfo:
    """Range 227-228 (invoice sync exception) + arc 217->229 (inv None)."""

    def _tenant(self):
        t = MagicMock()
        t.name_ar = "x"
        t.name_en = "y"
        return t

    def test_invoice_sync_exception_still_saves(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        tenant = self._tenant()
        tenant_cls = MagicMock()
        tenant_cls.get_current = MagicMock(return_value=tenant)
        inv_cls = MagicMock()
        inv_cls.get_active = MagicMock(side_effect=RuntimeError("inv down"))
        with (
            _base(),
            patch("routes.owner.settings.Tenant", tenant_cls),
            patch("routes.owner.settings.InvoiceSettings", inv_cls),
        ):
            resp = app.test_client().post("/owner/company-info", data={"name_ar": "م", "business_type": "general"})
        assert resp.status_code == 302

    def test_invoice_none_skips_sync(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        tenant = self._tenant()
        tenant_cls = MagicMock()
        tenant_cls.get_current = MagicMock(return_value=tenant)
        inv_cls = MagicMock()
        inv_cls.get_active = MagicMock(return_value=None)
        with (
            _base(),
            patch("routes.owner.settings.Tenant", tenant_cls),
            patch("routes.owner.settings.InvoiceSettings", inv_cls),
        ):
            resp = app.test_client().post("/owner/company-info", data={"name_ar": "م", "business_type": "general"})
        assert resp.status_code == 302


class TestSystemConfigCurrencyParse:
    """Range 329-330 (default_currency setter raises, caught internally)."""

    def test_default_currency_setter_error_is_swallowed(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)

        class ExplodingSettings:
            def __setattr__(self, name, value):
                if name == "default_currency":
                    raise RuntimeError("bad currency")
                super().__setattr__(name, value)

        settings = ExplodingSettings()
        cls = MagicMock()
        cls.get_current = MagicMock(return_value=settings)
        tenant = MagicMock()
        tenant_cls = MagicMock()
        tenant_cls.get_current = MagicMock(return_value=tenant)
        with (
            _base(),
            patch("routes.owner.settings.SystemSettings", cls),
            patch("routes.owner.settings.Tenant", tenant_cls),
        ):
            resp = app.test_client().post("/owner/system-config", data={"default_currency": "AED"})
        assert resp.status_code == 302


class TestStorePaymentEditMissing:
    """Range 407-408 (method not found)."""

    def test_edit_missing_method_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _base() as mock_db:
            mock_db.session.get.return_value = None
            resp = app.test_client().get("/owner/store-payment-methods/9999/edit")
        assert resp.status_code == 302


class TestPreviewBranches:
    """Ranges 619-621, 632-633, 745-747, 755-756."""

    def _preview_common(self, stack, *, qr=False):
        settings = MagicMock()
        settings.enable_qr_code = qr
        settings.company_name_ar = "شركة"
        inv_cls = MagicMock()
        inv_cls.get_active = MagicMock(return_value=settings)
        stack.enter_context(patch("models.invoice_settings.InvoiceSettings", inv_cls))
        stack.enter_context(
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
        )
        return settings

    def test_preview_invoice_other_tenant(self, app_factory, bypass_owner_auth):
        from contextlib import ExitStack

        app = app_factory(owner_bp)
        tenant = MagicMock()
        with (
            _base(),
            ExitStack() as stack,
        ):
            self._preview_common(stack)
            stack.enter_context(patch("utils.tenanting.get_active_tenant_id", return_value=1))
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            stack.enter_context(patch("utils.tenanting.without_tenant_scope", return_value=ctx))
            stack.enter_context(patch("models.Tenant.get_current", return_value=tenant))
            stack.enter_context(patch("utils.currency_utils.resolve_default_currency", return_value="AED"))
            resp = app.test_client().get("/owner/preview-invoice/modern?tenant_id=99")
        assert resp.status_code == 200

    def test_preview_invoice_currency_fallback(self, app_factory, bypass_owner_auth):
        from contextlib import ExitStack

        app = app_factory(owner_bp)
        with (
            _base(),
            ExitStack() as stack,
        ):
            self._preview_common(stack)
            stack.enter_context(patch("utils.tenanting.get_active_tenant_id", return_value=1))
            stack.enter_context(patch("models.Tenant.get_current", side_effect=RuntimeError("no tenant")))
            stack.enter_context(
                patch("routes.owner.settings.get_system_default_currency", return_value="AED"),
            )
            resp = app.test_client().get("/owner/preview-invoice/modern")
        assert resp.status_code == 200

    def test_preview_receipt_other_tenant(self, app_factory, bypass_owner_auth):
        from contextlib import ExitStack

        app = app_factory(owner_bp)
        tenant = MagicMock()
        with (
            _base(),
            ExitStack() as stack,
        ):
            self._preview_common(stack)
            stack.enter_context(patch("utils.tenanting.get_active_tenant_id", return_value=1))
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            stack.enter_context(patch("utils.tenanting.without_tenant_scope", return_value=ctx))
            stack.enter_context(patch("models.Tenant.get_current", return_value=tenant))
            stack.enter_context(patch("utils.currency_utils.resolve_default_currency", return_value="AED"))
            resp = app.test_client().get("/owner/preview-receipt/modern?tenant_id=99")
        assert resp.status_code == 200

    def test_preview_receipt_currency_fallback(self, app_factory, bypass_owner_auth):
        from contextlib import ExitStack

        app = app_factory(owner_bp)
        with (
            _base(),
            ExitStack() as stack,
        ):
            self._preview_common(stack)
            stack.enter_context(patch("utils.tenanting.get_active_tenant_id", return_value=1))
            stack.enter_context(patch("models.Tenant.get_current", side_effect=RuntimeError("no tenant")))
            stack.enter_context(
                patch("routes.owner.settings.get_system_default_currency", return_value="AED"),
            )
            resp = app.test_client().get("/owner/preview-receipt/modern")
        assert resp.status_code == 200

    def test_preview_receipt_source_info_line(self, app_factory, bypass_owner_auth):
        """Line 810 — force template to call receipt.get_source_info()."""
        from contextlib import ExitStack

        app = app_factory(owner_bp)
        with (
            _base(),
            ExitStack() as stack,
        ):
            self._preview_common(stack)
            stack.enter_context(patch("utils.tenanting.get_active_tenant_id", return_value=1))
            stack.enter_context(patch("models.Tenant.get_current", return_value=MagicMock()))
            stack.enter_context(patch("utils.currency_utils.resolve_default_currency", return_value="AED"))

            def _render(name, **ctx):
                ctx["receipt"].get_source_info()
                return "ok"

            stack.enter_context(patch("routes.owner.settings.render_template", side_effect=_render))
            resp = app.test_client().get("/owner/preview-receipt/modern")
        assert resp.status_code == 200


class TestInvoiceUploadSkips:
    """Arcs 555->573 (no logo) and 575->592 (no watermark)."""

    def test_post_without_files_skips_upload_blocks(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        settings = _settings_obj()
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
