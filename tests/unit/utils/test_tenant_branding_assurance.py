"""Tenant branding resolution — logos, warnings, print context."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from utils import tenant_branding as tb


class TestNormalizeStaticRel:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (None, ""),
            ("C:\\Users\\logo.png", ""),
            ("https://cdn.example.com/logo.png", "https://cdn.example.com/logo.png"),
            ("/static/assets/x.png", "assets/x.png"),
            ("static/assets/x.png", "assets/x.png"),
            ("assets\\tenants\\a\\logo.png", "assets/tenants/a/logo.png"),
        ],
    )
    def test_normalize(self, raw, expected):
        assert tb.normalize_static_rel(raw) == expected


class TestStaticExists:
    def test_http_url_counts_as_existing(self):
        assert tb._static_exists("https://example.com/logo.png") is True

    def test_missing_file_returns_false(self, mocker):
        mocker.patch("os.path.isfile", return_value=False)
        assert tb._static_exists("assets/missing.png") is False

    def test_existing_file(self, mocker):
        mocker.patch("os.path.isfile", return_value=True)
        assert tb._static_exists("assets/brand/azad/logos/logo.png") is True


class TestResolveBranding:
    @staticmethod
    def _tenant(**kw):
        t = MagicMock()
        t.id = kw.get("id", 1)
        t.slug = kw.get("slug", "acme")
        t.name = kw.get("name", "Acme")
        t.name_ar = "أكمي"
        t.name_en = "Acme EN"
        t.logo_url = kw.get("logo_url", "assets/tenants/acme/logos/logo.png")
        t.logo_dark_url = None
        t.favicon_url = None
        t.address_ar = "دبي"
        t.address_en = "Dubai"
        t.phone_1 = "050"
        t.mobile = None
        t.email = "a@acme.com"
        t.tax_number = "TRN1"
        t.vat_country = "AE"
        t.default_currency = "AED"
        t.timezone = "Asia/Dubai"
        t.city = "Dubai"
        return t

    def test_resolve_with_tenant_id(self, mocker):
        tenant = self._tenant()
        settings = MagicMock(
            logo_path="assets/tenants/acme/logos/logo.png",
            logo_url=None,
            company_name_ar="أ",
            company_name_en="B",
            address_ar="x",
            address_en="y",
            phone_1="1",
            email="e",
            tax_number="T",
        )
        mocker.patch("extensions.db.session.get", return_value=tenant)
        mocker.patch(
            "models.invoice_settings.InvoiceSettings.get_active", return_value=settings
        )
        mocker.patch("utils.tenant_assets.branding_for_tenant_slug", return_value={})
        mocker.patch("os.path.isfile", return_value=True)

        branding = tb.resolve_tenant_branding(tenant_id=1)
        assert branding["tenant_id"] == 1
        assert branding["company_name_en"] == "B"
        assert branding["developer_logo_url"] == tb.AZAD_LOGO

    def test_resolve_without_tenant_uses_defaults(self, mocker):
        mocker.patch("models.tenant.Tenant.get_current", return_value=None)
        mocker.patch(
            "models.invoice_settings.InvoiceSettings.get_active", return_value=None
        )
        branding = tb.resolve_tenant_branding()
        assert branding["company_name_en"] == "Company"
        assert branding["default_currency"] == "AED"

    def test_document_logo_explicit_settings_override(self, mocker):
        settings = MagicMock(logo_path="assets/custom.png", logo_url=None)
        mocker.patch(
            "utils.tenant_branding.resolve_tenant_branding",
            return_value={"logo_url": "fallback"},
        )
        mocker.patch("os.path.isfile", return_value=True)
        assert tb.document_logo_relative_path(settings=settings) == "assets/custom.png"

    def test_document_logo_no_explicit_returns_branding(self, mocker):
        mocker.patch(
            "utils.tenant_branding.resolve_tenant_branding",
            return_value={"logo_url": "brand.png"},
        )
        assert tb.document_logo_relative_path(settings=None) == "brand.png"

    def test_document_logo_explicit_empty_falls_through(self, mocker):
        settings = MagicMock(logo_path=None, logo_url=None)
        mocker.patch("utils.tenant_branding._first_existing", return_value="")
        mocker.patch(
            "utils.tenant_branding.resolve_tenant_branding",
            return_value={"logo_url": "fallback.png"},
        )
        assert tb.document_logo_relative_path(settings=settings) == "fallback.png"

    def test_get_print_header_and_invoice_branding(self, mocker):
        payload = {"logo_url": "x"}
        mocker.patch(
            "utils.tenant_branding.resolve_tenant_branding", return_value=payload
        )
        assert tb.get_print_header_context(1) == payload
        assert tb.get_invoice_branding(1) == payload


class TestBrandingPathWarnings:
    def test_no_branding(self):
        assert tb.branding_path_warnings(None) == ["no branding resolved"]

    def test_windows_absolute_path_warning(self):
        warns = tb.branding_path_warnings(
            {"logo_url": "C:\\logo.png", "tenant_slug": "x"}
        )
        assert any("Windows path" in w for w in warns)

    def test_missing_file_warning(self, mocker):
        mocker.patch("utils.tenant_branding._static_exists", return_value=False)
        warns = tb.branding_path_warnings(
            {"logo_url": "assets/missing.png", "tenant_slug": "x"}
        )
        assert any("file missing" in w for w in warns)

    def test_platform_default_logo_warning(self):
        warns = tb.branding_path_warnings(
            {
                "tenant_slug": "otherco",
                "logo_url": "assets/brand/azad/logos/logo.png",
            }
        )
        assert any("platform default" in w for w in warns)

    def test_first_existing_picks_http(self):
        assert tb._first_existing(None, "https://x/logo.png") == "https://x/logo.png"

    def test_first_existing_skips_empty(self, mocker):
        mocker.patch("utils.tenant_branding._static_exists", return_value=True)
        assert tb._first_existing("", "assets/ok.png") == "assets/ok.png"
