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
                "bank_name": "Pinned Bank",
                "bank_account_number": "123456",
                "iban": "AE00 0000 0000 0000 0000",
                "swift_code": "PINNEDS1",
                "footer_text_ar": "تذييل محدد",
                "active_invoice_template": "gulf",
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
        assert kwargs["bank_name"] == "Pinned Bank"
        assert kwargs["bank_account_number"] == "123456"
        assert kwargs["iban"] == "AE00 0000 0000 0000 0000"
        assert kwargs["swift_code"] == "PINNEDS1"
        assert kwargs["footer_text_ar"] == "تذييل محدد"
        assert kwargs["active_invoice_template"] == "gulf"


def test_print_overlay_reads_from_tenant_profile():
    from types import SimpleNamespace

    from utils.invoice_profile import build_invoice_settings_snapshot

    tenant = SimpleNamespace(
        id=42,
        name="Co A",
        name_ar="شركة أ",
        name_en="Co A",
        address_ar="شارع 1",
        address_en=None,
        city=None,
        country="AE",
        phone_1=None,
        phone_2=None,
        mobile=None,
        email=None,
        website="https://x.example",
        tax_number="123456789",
        vat_number=None,
        commercial_register="CR-1",
        license_number=None,
        logo_url="logo.png",
        logo_dark_url=None,
        favicon_url=None,
        logo_path="",
        stamp_url="",
        signature_url="",
        bank_name="البنك العربي",
        bank_account_number="123",
        iban="AE07 0331 2345 6789 0123 456",
        swift_code="EBILAEAD",
        payment_terms_ar="الدفع عند التسليم",
        payment_terms_en=None,
        footer_text_ar="شكرًا لثقتكم",
        footer_text_en=None,
        default_invoice_note_ar="ملاحظة",
        default_invoice_note_en=None,
        active_invoice_template="gulf",
        paper_size="A4",
        orientation="portrait",
        show_logo=True,
        logo_position="left",
        logo_size="medium",
        enable_qr_code=True,
        qr_position="bottom-right",
        enable_watermark=False,
        watermark_text="",
        watermark_image_path="",
        watermark_opacity=None,
        default_language="ar",
        show_barcode=True,
        show_page_numbers=True,
        show_due_date=True,
        show_terms=True,
        facebook_url=None,
        instagram_url=None,
        whatsapp_number=None,
    )
    profile = build_invoice_settings_snapshot(tenant)
    assert profile.bank_name == "البنك العربي"
    assert profile.iban.startswith("AE07")
    assert profile.payment_terms_ar == "الدفع عند التسليم"
    assert profile.footer_text_ar == "شكرًا لثقتكم"
    assert profile.default_invoice_note_ar == "ملاحظة"
    assert profile.active_template == "gulf"
    assert profile.website == "https://x.example"


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
    with (
        patch("services.owner_ops_service.OwnerOpsService.get_tenant_or_404", return_value=tenant),
        patch("routes.owner.tenants.db.session"),
        patch("routes.owner.tenants._invalidate_owner_changes"),
        patch("routes.owner.tenants._audit_owner_db_action"),
    ):
        response = to_client.post(f"/owner/tenants/{tenant.id}/edit", data={"name_ar": "New Name"})

    assert response.status_code == 302
    assert tenant.name_ar == "New Name"
    assert tenant.default_tax_rate == Decimal("7.00")
    assert tenant.enable_tax and tenant.prices_include_vat and tenant.enable_store
    assert tenant.vat_number == "123456789012345"
    assert tenant.tax_number == "tax-number"
    assert tenant.bank_name == "Existing Bank"
    assert tenant.iban == "existing-iban"


def test_edit_syncs_real_footer_column_and_allows_explicit_clear(to_client):
    from tests.unit.routes.test_owner_tenants_coverage99 import _tenant

    tenant = _tenant()
    tenant.vat_country = "AE"
    tenant.default_tax_rate = Decimal("5")
    tenant.iban = "old-iban"
    tenant.footer_text_ar = "old footer"
    with (
        patch("services.owner_ops_service.OwnerOpsService.get_tenant_or_404", return_value=tenant),
        patch("routes.owner.tenants.db.session"),
        patch("routes.owner.tenants._invalidate_owner_changes"),
        patch("routes.owner.tenants._audit_owner_db_action"),
    ):
        response = to_client.post(f"/owner/tenants/{tenant.id}/edit", data={"footer_text_ar": "New footer", "iban": ""})

    assert response.status_code == 302
    assert tenant.footer_text_ar == "New footer"
    assert tenant.iban is None


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


def test_edit_company_identity_updates_profile_only(to_client):
    from tests.unit.routes.test_owner_tenants_coverage99 import _tenant

    tenant = _tenant()
    tenant.vat_country = "AE"
    before = {field: getattr(tenant, field, None) for field in ("bank_name", "iban", "active_invoice_template")}
    with (
        patch("services.owner_ops_service.OwnerOpsService.get_tenant_or_404", return_value=tenant),
        patch("routes.owner.tenants.db.session"),
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
    assert tenant.address_en == "New street"
    assert tenant.website == "https://x.example"
    assert tenant.commercial_register == "CR-123"
    assert tenant.city == "Dubai" and tenant.country == "AE"
    # Print/invoice constants that were not submitted keep their stored values.
    for field, value in before.items():
        assert getattr(tenant, field) == value
