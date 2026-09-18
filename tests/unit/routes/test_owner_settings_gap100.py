"""Gap100 for routes/owner/settings.py — covers 135-137, 555->573, 575->592, 1146->1148."""

from __future__ import annotations

import io
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from routes.owner import owner_bp


def _atomic():
    a = MagicMock()
    a.return_value.__enter__ = MagicMock()
    a.return_value.__exit__ = MagicMock(return_value=False)
    return a


def _invoice_settings_obj():
    s = MagicMock()
    s.default_currency = "AED"
    s.auto_update_rates = False
    s.notification_templates = {}
    s.enable_qr_code = False
    s.company_name_ar = "شركة"
    s.logo_path = None
    s.watermark_image_path = None
    return s


def _invoice_settings_class(settings):
    cls = MagicMock(name="InvoiceSettings")
    cls.get_active = MagicMock(return_value=settings)
    return cls


class TestIntegrationExceptionGap100:
    """Lines 135-137 — IntegrationService.test_email raises."""

    def test_email_test_exception_returns_500(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with ExitStack() as stack:
            stack.enter_context(patch("routes.owner.settings.render_template", return_value="ok"))
            stack.enter_context(patch("routes.owner.settings.url_for", return_value="/"))
            mock_db = MagicMock()
            mock_db.engine = MagicMock()
            stack.enter_context(patch("routes.owner.settings.db", mock_db))
            stack.enter_context(patch("routes.owner.settings._invalidate_owner_changes"))
            stack.enter_context(patch("routes.owner.settings._audit_owner_db_action"))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_audit"))
            atomic = _atomic()
            stack.enter_context(patch("routes.owner.settings.atomic_transaction", atomic))
            stack.enter_context(patch("utils.db_safety.atomic_transaction", atomic))
            stack.enter_context(
                patch(
                    "services.integration_service.IntegrationService.test_email",
                    side_effect=RuntimeError("smtp down"),
                )
            )
            # Ensure test_currency_api not called
            stack.enter_context(patch("services.integration_service.IntegrationService.test_currency_api"))
            resp = app.test_client().post("/owner/integrations/test/email")
        assert resp.status_code == 500
        data = resp.get_json()
        assert "smtp down" in data["message"]

    def test_currency_test_exception_returns_500(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with ExitStack() as stack:
            stack.enter_context(patch("routes.owner.settings.render_template", return_value="ok"))
            stack.enter_context(patch("routes.owner.settings.url_for", return_value="/"))
            mock_db = MagicMock()
            mock_db.engine = MagicMock()
            stack.enter_context(patch("routes.owner.settings.db", mock_db))
            stack.enter_context(patch("routes.owner.settings._invalidate_owner_changes"))
            stack.enter_context(patch("routes.owner.settings._audit_owner_db_action"))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_audit"))
            atomic = _atomic()
            stack.enter_context(patch("routes.owner.settings.atomic_transaction", atomic))
            stack.enter_context(patch("utils.db_safety.atomic_transaction", atomic))
            stack.enter_context(
                patch(
                    "services.integration_service.IntegrationService.test_currency_api",
                    side_effect=RuntimeError("api down"),
                )
            )
            resp = app.test_client().post("/owner/integrations/test/currency_api")
        assert resp.status_code == 500
        assert "api down" in resp.get_json()["message"]


class TestInvoiceLogoWatermarkGap100:
    """Arcs 555->573 (logo) and 575->592 (watermark)."""

    def test_logo_upload_sets_logo_path(self, app_factory, bypass_owner_auth, tmp_path):
        app = app_factory(owner_bp)
        settings = _invoice_settings_obj()
        inv_cls = _invoice_settings_class(settings)
        atomic = _atomic()
        with ExitStack() as stack:
            stack.enter_context(patch("routes.owner.settings.render_template", return_value="ok"))
            stack.enter_context(patch("routes.owner.settings.url_for", return_value="/"))
            mock_db = MagicMock()
            mock_db.engine = MagicMock()
            stack.enter_context(patch("routes.owner.settings.db", mock_db))
            stack.enter_context(patch("routes.owner.settings._invalidate_owner_changes"))
            stack.enter_context(patch("routes.owner.settings._audit_owner_db_action"))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_audit"))
            stack.enter_context(patch("routes.owner.settings.atomic_transaction", atomic))
            stack.enter_context(patch("utils.db_safety.atomic_transaction", atomic))
            stack.enter_context(patch("routes.owner.settings.InvoiceSettings", inv_cls))
            stack.enter_context(patch("models.invoice_settings.InvoiceSettings", inv_cls))
            # let makedirs create real dirs; mock save to avoid filesystem side-effects
            stack.enter_context(patch("werkzeug.datastructures.FileStorage.save"))
            resp = app.test_client().post(
                "/owner/invoice-settings",
                data={
                    "company_name_ar": "شركة",
                    "company_logo": (io.BytesIO(b"fake-logo"), "logo.png"),
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        assert settings.logo_path is not None
        assert "uploads/logos/" in settings.logo_path

    def test_watermark_upload_sets_watermark_path(self, app_factory, bypass_owner_auth, tmp_path):
        app = app_factory(owner_bp)
        settings = _invoice_settings_obj()
        inv_cls = _invoice_settings_class(settings)
        atomic = _atomic()
        with ExitStack() as stack:
            stack.enter_context(patch("routes.owner.settings.render_template", return_value="ok"))
            stack.enter_context(patch("routes.owner.settings.url_for", return_value="/"))
            mock_db = MagicMock()
            mock_db.engine = MagicMock()
            stack.enter_context(patch("routes.owner.settings.db", mock_db))
            stack.enter_context(patch("routes.owner.settings._invalidate_owner_changes"))
            stack.enter_context(patch("routes.owner.settings._audit_owner_db_action"))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_audit"))
            stack.enter_context(patch("routes.owner.settings.atomic_transaction", atomic))
            stack.enter_context(patch("utils.db_safety.atomic_transaction", atomic))
            stack.enter_context(patch("routes.owner.settings.InvoiceSettings", inv_cls))
            stack.enter_context(patch("models.invoice_settings.InvoiceSettings", inv_cls))
            stack.enter_context(patch("werkzeug.datastructures.FileStorage.save"))
            resp = app.test_client().post(
                "/owner/invoice-settings",
                data={
                    "company_name_ar": "شركة",
                    "watermark_image": (io.BytesIO(b"fake-wm"), "wm.png"),
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        assert settings.watermark_image_path is not None
        assert "uploads/watermarks/" in settings.watermark_image_path

    def test_both_uploads_together(self, app_factory, bypass_owner_auth, tmp_path):
        app = app_factory(owner_bp)
        settings = _invoice_settings_obj()
        inv_cls = _invoice_settings_class(settings)
        atomic = _atomic()
        with ExitStack() as stack:
            stack.enter_context(patch("routes.owner.settings.render_template", return_value="ok"))
            stack.enter_context(patch("routes.owner.settings.url_for", return_value="/"))
            mock_db = MagicMock()
            mock_db.engine = MagicMock()
            stack.enter_context(patch("routes.owner.settings.db", mock_db))
            stack.enter_context(patch("routes.owner.settings._invalidate_owner_changes"))
            stack.enter_context(patch("routes.owner.settings._audit_owner_db_action"))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_audit"))
            stack.enter_context(patch("routes.owner.settings.atomic_transaction", atomic))
            stack.enter_context(patch("utils.db_safety.atomic_transaction", atomic))
            stack.enter_context(patch("routes.owner.settings.InvoiceSettings", inv_cls))
            stack.enter_context(patch("models.invoice_settings.InvoiceSettings", inv_cls))
            stack.enter_context(patch("werkzeug.datastructures.FileStorage.save"))
            resp = app.test_client().post(
                "/owner/invoice-settings",
                data={
                    "company_name_ar": "شركة",
                    "company_logo": (io.BytesIO(b"logo"), "logo.png"),
                    "watermark_image": (io.BytesIO(b"wm"), "wm.png"),
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        assert "uploads/logos/" in settings.logo_path
        assert "uploads/watermarks/" in settings.watermark_image_path

    def test_empty_filename_skips_save(self, app_factory, bypass_owner_auth, tmp_path):
        app = app_factory(owner_bp)
        settings = _invoice_settings_obj()
        inv_cls = _invoice_settings_class(settings)
        atomic = _atomic()
        with ExitStack() as stack:
            stack.enter_context(patch("routes.owner.settings.render_template", return_value="ok"))
            stack.enter_context(patch("routes.owner.settings.url_for", return_value="/"))
            mock_db = MagicMock()
            mock_db.engine = MagicMock()
            stack.enter_context(patch("routes.owner.settings.db", mock_db))
            stack.enter_context(patch("routes.owner.settings._invalidate_owner_changes"))
            stack.enter_context(patch("routes.owner.settings._audit_owner_db_action"))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_audit"))
            stack.enter_context(patch("routes.owner.settings.atomic_transaction", atomic))
            stack.enter_context(patch("utils.db_safety.atomic_transaction", atomic))
            stack.enter_context(patch("routes.owner.settings.InvoiceSettings", inv_cls))
            stack.enter_context(patch("models.invoice_settings.InvoiceSettings", inv_cls))
            stack.enter_context(patch("werkzeug.datastructures.FileStorage.save"))
            # Provide files with empty filename — should skip inner if
            resp = app.test_client().post(
                "/owner/invoice-settings",
                data={
                    "company_name_ar": "شركة",
                    "company_logo": (io.BytesIO(b""), ""),
                    "watermark_image": (io.BytesIO(b""), ""),
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        # Should not set paths when filename empty
        assert settings.logo_path is None
        assert settings.watermark_image_path is None


class TestApiUpdateTenantLogoUrlGap100:
    """Arc 1146->1148 — tenant.logo_url + updated_at."""

    def test_logo_url_updates_and_sets_updated_at(self, app_factory, bypass_company_admin_auth):
        app = app_factory(owner_bp)
        tenant = MagicMock()
        tenant.id = 1
        tenant.logo_url = None
        tenant.updated_at = None
        atomic = _atomic()
        with ExitStack() as stack:
            stack.enter_context(patch("routes.owner.settings.render_template", return_value="ok"))
            stack.enter_context(patch("routes.owner.settings.url_for", return_value="/"))
            mock_db = MagicMock()
            mock_db.engine = MagicMock()
            mock_db.session.get.return_value = tenant
            stack.enter_context(patch("routes.owner.settings.db", mock_db))
            stack.enter_context(patch("routes.owner.settings._invalidate_owner_changes"))
            stack.enter_context(patch("routes.owner.settings._audit_owner_db_action"))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_audit"))
            stack.enter_context(patch("routes.owner.settings.atomic_transaction", atomic))
            stack.enter_context(patch("utils.db_safety.atomic_transaction", atomic))
            stack.enter_context(patch("routes.owner.settings.get_active_tenant_id", return_value=1))
            resp = app.test_client().post(
                "/owner/api/update-tenant-settings",
                json={"field": "logo_url", "value": "  https://cdn.example.com/logo.png  "},
            )
        assert resp.status_code == 200
        assert tenant.logo_url == "https://cdn.example.com/logo.png"
        assert tenant.updated_at is not None

    def test_prices_include_vat_also_sets_updated_at(self, app_factory, bypass_company_admin_auth):
        app = app_factory(owner_bp)
        tenant = MagicMock()
        tenant.id = 1
        tenant.updated_at = None
        atomic = _atomic()
        with ExitStack() as stack:
            stack.enter_context(patch("routes.owner.settings.render_template", return_value="ok"))
            stack.enter_context(patch("routes.owner.settings.url_for", return_value="/"))
            mock_db = MagicMock()
            mock_db.engine = MagicMock()
            mock_db.session.get.return_value = tenant
            stack.enter_context(patch("routes.owner.settings.db", mock_db))
            stack.enter_context(patch("routes.owner.settings._invalidate_owner_changes"))
            stack.enter_context(patch("routes.owner.settings._audit_owner_db_action"))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_audit"))
            stack.enter_context(patch("routes.owner.settings.atomic_transaction", atomic))
            stack.enter_context(patch("utils.db_safety.atomic_transaction", atomic))
            stack.enter_context(patch("routes.owner.settings.get_active_tenant_id", return_value=1))
            resp = app.test_client().post(
                "/owner/api/update-tenant-settings",
                json={"field": "prices_include_vat", "value": True},
            )
        assert resp.status_code == 200
        assert tenant.prices_include_vat is True
        assert tenant.updated_at is not None
