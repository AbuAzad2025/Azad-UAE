"""Tenant profile tax constants — creation/edit lock the statutory rate."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def to_client(app_factory, bypass_owner_auth):
    from routes.owner import owner_bp

    app = app_factory(owner_bp)
    return app.test_client()


def test_create_locks_rate_to_country(to_client):
    with (
        patch(
            "services.owner_ops_service.OwnerOpsService.active_packages_sorted",
            return_value=[],
        ),
        patch(
            "services.owner_ops_service.OwnerOpsService.find_tenant_by_slug",
            return_value=None,
        ),
        patch("routes.owner.tenants.Tenant") as tcls,
        patch("routes.owner.tenants.db.session"),
        patch("models.ensure_default_pos_order_types", return_value=None),
        patch("services.gl_service.GLService.ensure_core_accounts", return_value=None),
        patch("services.gl_service.GLService.ensure_gl_mappings", return_value=None),
    ):
        tcls.return_value = MagicMock(id=11)
        resp = to_client.post(
            "/owner/tenants/create",
            data={
                "name_ar": "شركة",
                "slug": "co-tax",
                "default_currency": "ILS",
                "vat_country": "PS",
                "enable_tax": "on",
                "prices_include_vat": "on",
                "vat_number": "123456789",
                "logo_url": "https://x.example/logo.png",
                "address_en": "Example street",
                "city": "Dubai",
                "country": "AE",
                "website": "https://x.example",
                "commercial_register": "CR-123",
            },
        )
        assert resp.status_code in (200, 302, 303)
        kwargs = tcls.call_args.kwargs
        assert kwargs["vat_country"] == "PS"
        assert kwargs["default_tax_rate"] == Decimal("16.00")
        assert kwargs["enable_tax"] is True
        assert kwargs["prices_include_vat"] is True
        assert kwargs["vat_number"] == "123456789"
        assert kwargs["logo_url"] == "https://x.example/logo.png"
        assert kwargs["address_en"] == "Example street"
        assert kwargs["city"] == "Dubai" and kwargs["country"] == "AE"
        assert kwargs["website"] == "https://x.example"
        assert kwargs["commercial_register"] == "CR-123"


def test_print_overlay_seeds_invoice_constants_from_tenant():
    from models.invoice_settings import InvoiceSettings

    settings = InvoiceSettings()
    t = MagicMock()
    t.name_ar = "شركة أ"
    t.name_en = "Co A"
    t.address_ar = "شارع 1"
    t.address_en = None  # falsy → keeps settings default
    t.phone_1 = None
    t.mobile = None
    t.email = None
    t.website = "https://x.example"
    t.tax_number = "123456789"
    t.commercial_register = "CR-1"
    t.license_number = None
    t.bank_name = "البنك العربي"
    t.bank_account_number = "123"
    t.iban = "AE07 0331 2345 6789 0123 456"
    t.swift_code = "EBILAEAD"
    t.payment_terms_ar = "الدفع عند التسليم"
    t.payment_terms_en = None
    t.footer_invoice_text_ar = "شكرًا لثقتكم"
    t.footer_invoice_text_en = None
    t.default_invoice_note_ar = "ملاحظة"
    t.default_invoice_note_en = None
    t.invoice_header_color = "#111111"
    t.invoice_accent_color = "#222222"
    t.active_invoice_template = "gulf"
    InvoiceSettings._seed_from_tenant(settings, t)
    assert settings.bank_name == "البنك العربي"
    assert settings.iban.startswith("AE07")
    assert settings.payment_terms_ar == "الدفع عند التسليم"
    assert settings.footer_text_ar == "شكرًا لثقتكم"
    assert settings.default_invoice_note_ar == "ملاحظة"
    assert settings.header_color == "#111111"
    assert settings.accent_color == "#222222"
    assert settings.active_template == "gulf"
    assert settings.website == "https://x.example"


def test_create_rejects_invalid_trn(to_client):
    with (
        patch(
            "services.owner_ops_service.OwnerOpsService.active_packages_sorted",
            return_value=[],
        ),
        patch(
            "services.owner_ops_service.OwnerOpsService.find_tenant_by_slug",
            return_value=None,
        ),
        patch("routes.owner.tenants.Tenant") as tcls,
    ):
        resp = to_client.post(
            "/owner/tenants/create",
            data={
                "name_ar": "شركة",
                "slug": "co-badtrn",
                "default_currency": "ILS",
                "vat_country": "PS",
                "vat_number": "12",
            },
        )
        assert resp.status_code in (200, 302, 303)
        # An invalid tax number must never create the tenant.
        tcls.assert_not_called()


def test_edit_relocks_rate_on_country_change(to_client):
    from tests.unit.routes.test_owner_tenants_coverage99 import _tenant

    tenant = _tenant()
    tenant.vat_country = "AE"
    tenant.default_tax_rate = Decimal("5.00")
    tenant.enable_tax = True
    tenant.vat_number = "123456789012345"
    tenant.tax_number = ""
    tenant.logo_url = ""
    tenant.prices_include_vat = False
    with (
        patch("services.owner_ops_service.OwnerOpsService.get_tenant_or_404", return_value=tenant),
        patch("routes.owner.tenants.db.session"),
        patch("routes.owner.tenants._invalidate_owner_changes"),
        patch("routes.owner.tenants._audit_owner_db_action"),
        patch("routes.owner.tenants.render_template", return_value="form"),
        patch("services.invoice_profile_service.InvoiceProfileService.sync_from_tenant"),
    ):
        resp = to_client.post(
            f"/owner/tenants/{tenant.id}/edit",
            data={
                "name_ar": "أكمي",
                "name_en": "Acme",
                "slug": "acme",
                "default_currency": "ILS",
                "vat_country": "PS",
                "enable_tax": "on",
                "vat_number": "123456789",
                "tax_number": "",
                "logo_url": "https://x.example/logo.png",
            },
        )
        assert resp.status_code in (200, 302, 303)
        assert tenant.vat_country == "PS"
        assert tenant.default_tax_rate == Decimal("16.00")
        assert tenant.enable_tax is True
        assert tenant.logo_url == "https://x.example/logo.png"


def test_partial_edit_preserves_unsubmitted_tax_and_invoice_fields(to_client):
    from tests.unit.routes.test_owner_tenants_coverage99 import _tenant
    from utils.invoice_profile import sync_invoice_profile

    tenant = _tenant()
    tenant.vat_country = "AE"
    tenant.default_tax_rate = Decimal("7.00")
    tenant.enable_tax = True
    tenant.prices_include_vat = True
    tenant.vat_number = "123456789012345"
    tenant.tax_number = "tax-number"
    tenant.bank_name = "Existing Bank"
    tenant.iban = "existing-iban"
    tenant.enable_store = True
    overlay = MagicMock(bank_name="Existing Bank", iban="existing-iban", company_name_ar="Old")
    with (
        patch("services.owner_ops_service.OwnerOpsService.get_tenant_or_404", return_value=tenant),
        patch("routes.owner.tenants.db.session"),
        patch(
            "services.invoice_profile_service.InvoiceProfileService.sync_from_tenant",
            side_effect=lambda t, fields: sync_invoice_profile(t, overlay, fields),
        ) as sync,
        patch("routes.owner.tenants._invalidate_owner_changes"),
        patch("routes.owner.tenants._audit_owner_db_action"),
    ):
        response = to_client.post(f"/owner/tenants/{tenant.id}/edit", data={"name_ar": "New Name"})

    assert response.status_code == 302
    assert tenant.name_ar == overlay.company_name_ar == "New Name"
    assert tenant.default_tax_rate == Decimal("7.00")
    assert tenant.enable_tax and tenant.prices_include_vat and tenant.enable_store
    assert tenant.vat_number == "123456789012345"
    assert tenant.tax_number == "tax-number"
    assert tenant.bank_name == overlay.bank_name == "Existing Bank"
    assert tenant.iban == overlay.iban == "existing-iban"
    sync.assert_called_once_with(tenant, {"name_ar"})


def test_edit_syncs_real_footer_column_and_allows_explicit_clear(to_client):
    from tests.unit.routes.test_owner_tenants_coverage99 import _tenant
    from utils.invoice_profile import sync_invoice_profile

    tenant = _tenant()
    tenant.vat_country = "AE"
    tenant.default_tax_rate = Decimal("5")
    tenant.iban = "old-iban"
    tenant.footer_invoice_text_ar = "old footer"
    overlay = MagicMock(iban="old-iban", footer_text_ar="old footer")
    with (
        patch("services.owner_ops_service.OwnerOpsService.get_tenant_or_404", return_value=tenant),
        patch("routes.owner.tenants.db.session"),
        patch(
            "services.invoice_profile_service.InvoiceProfileService.sync_from_tenant",
            side_effect=lambda t, fields: sync_invoice_profile(t, overlay, fields),
        ),
        patch("routes.owner.tenants._invalidate_owner_changes"),
        patch("routes.owner.tenants._audit_owner_db_action"),
    ):
        response = to_client.post(
            f"/owner/tenants/{tenant.id}/edit", data={"footer_invoice_text_ar": "New footer", "iban": ""}
        )

    assert response.status_code == 302
    assert tenant.footer_invoice_text_ar == overlay.footer_text_ar == "New footer"
    assert tenant.iban is None and overlay.iban is None


def test_full_profile_form_can_disable_tax(to_client):
    from tests.unit.routes.test_owner_tenants_coverage99 import _tenant

    tenant = _tenant()
    tenant.vat_country = "AE"
    tenant.enable_tax = True
    tenant.prices_include_vat = True
    with (
        patch("services.owner_ops_service.OwnerOpsService.get_tenant_or_404", return_value=tenant),
        patch("routes.owner.tenants.db.session"),
        patch("routes.owner.tenants._invalidate_owner_changes"),
        patch("routes.owner.tenants._audit_owner_db_action"),
    ):
        response = to_client.post(f"/owner/tenants/{tenant.id}/edit", data={"profile_tax_fields": "1"})

    assert response.status_code == 302
    assert tenant.enable_tax is False
    assert tenant.prices_include_vat is False


def test_edit_company_identity_updates_profile_and_print_settings(to_client):
    from tests.unit.routes.test_owner_tenants_coverage99 import _tenant
    from utils.invoice_profile import sync_invoice_profile

    tenant = _tenant()
    tenant.vat_country = "AE"
    overlay = MagicMock()
    with (
        patch("services.owner_ops_service.OwnerOpsService.get_tenant_or_404", return_value=tenant),
        patch("routes.owner.tenants.db.session"),
        patch(
            "services.invoice_profile_service.InvoiceProfileService.sync_from_tenant",
            side_effect=lambda t, fields: sync_invoice_profile(t, overlay, fields),
        ),
        patch("routes.owner.tenants._invalidate_owner_changes"),
        patch("routes.owner.tenants._audit_owner_db_action"),
    ):
        response = to_client.post(
            f"/owner/tenants/{tenant.id}/edit",
            data={
                "address_en": "New street",
                "city": "Dubai",
                "country": "AE",
                "website": "https://x.example",
                "commercial_register": "CR-123",
            },
        )

    assert response.status_code == 302
    assert tenant.address_en == overlay.address_en == "New street"
    assert tenant.website == overlay.website == "https://x.example"
    assert tenant.commercial_register == overlay.commercial_register == "CR-123"
    assert tenant.city == "Dubai" and tenant.country == "AE"
