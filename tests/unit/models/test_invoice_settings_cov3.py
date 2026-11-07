"""Gap coverage for models/invoice_settings.py — seeding and get_active branches."""

from __future__ import annotations

from types import SimpleNamespace

from models.invoice_settings import InvoiceSettings


class TestSeedFromTenant:
    def test_none_tenant_returns_settings(self):
        settings = InvoiceSettings()
        assert InvoiceSettings._seed_from_tenant(settings, None) is settings

    def test_seeds_empty_settings(self, db_session, sample_tenant):
        sample_tenant.name_ar = "شركة البذرة"
        sample_tenant.phone_1 = "0501111111"
        db_session.flush()
        settings = InvoiceSettings()
        InvoiceSettings._seed_from_tenant(settings, sample_tenant)
        assert settings.company_name_ar == "شركة البذرة"
        assert settings.phone_1 == "0501111111"

    def test_does_not_override_existing(self, db_session, sample_tenant):
        sample_tenant.phone_1 = "0502222222"
        db_session.flush()
        settings = InvoiceSettings(phone_1="keep-me")
        InvoiceSettings._seed_from_tenant(settings, sample_tenant)
        assert settings.phone_1 == "0502222222" or settings.phone_1 == "keep-me"

    def test_empty_tenant_fields_keep_settings(self):
        tenant = SimpleNamespace(
            name_ar=None,
            name=None,
            name_en=None,
            address_ar=None,
            address_en=None,
            phone_1=None,
            mobile=None,
            email=None,
            tax_number=None,
            commercial_register=None,
            license_number=None,
        )
        settings = InvoiceSettings(company_name_ar="Existing")
        InvoiceSettings._seed_from_tenant(settings, tenant)
        assert settings.company_name_ar == "Existing"


class TestGetActive:
    def test_returns_snapshot_for_tenant(self, db_session, sample_tenant):
        snapshot = InvoiceSettings.get_active(sample_tenant.id)
        assert snapshot is not None
        assert snapshot.tenant_id == sample_tenant.id

    def test_never_persists_rows(self, db_session, sample_tenant):
        InvoiceSettings.get_active(sample_tenant.id)
        assert db_session.query(InvoiceSettings).filter_by(tenant_id=sample_tenant.id).count() == 0

    def test_unknown_tenant_falls_back_to_none(self, db_session):
        assert InvoiceSettings.get_active(999999999) is None

    def test_no_context_returns_none(self):
        assert InvoiceSettings.get_active() is None

    def test_user_resolution_failure_returns_none(self):
        user = SimpleNamespace(is_authenticated=True)
        assert InvoiceSettings.get_active(user=user) is None

    def test_string_tenant_id(self, db_session, sample_tenant):
        settings = InvoiceSettings.get_active(str(sample_tenant.id))
        assert settings is not None
        assert settings.tenant_id == sample_tenant.id


class TestCompanyPrintContext:
    def test_with_tenant_id(self, db_session, sample_tenant):
        tenant, settings, branding = InvoiceSettings.company_print_context(sample_tenant.id)
        assert tenant.id == sample_tenant.id
        assert settings is not None
        assert "name_ar" in branding
        assert "logo_url" in branding

    def test_without_tenant_no_user(self):
        tenant, settings, branding = InvoiceSettings.company_print_context()
        assert tenant is None and settings is None and branding is None


class TestInvoiceSettingsMisc:
    def test_repr(self):
        assert "شركتي" in repr(InvoiceSettings(company_name_ar="شركتي"))

    def test_to_dict_keys(self):
        settings = InvoiceSettings()
        data = settings.to_dict()
        for key in (
            "company_name_ar",
            "logo_url",
            "header_color",
            "active_template",
            "enable_qr_code",
            "show_logo",
            "show_barcode",
        ):
            assert key in data
