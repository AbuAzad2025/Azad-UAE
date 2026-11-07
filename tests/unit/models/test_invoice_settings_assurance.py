"""InvoiceSettings compatibility API — seeding and snapshot resolution."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestInvoiceSettingsModel:
    def test_seed_from_tenant(self):
        from models.invoice_settings import InvoiceSettings

        settings = InvoiceSettings()
        tenant = MagicMock(
            name="Co",
            name_ar="شركة",
            name_en="Company EN",
            address_ar="ع",
            address_en="En",
            phone_1="050",
            mobile="055",
            email="a@co.com",
            tax_number="T1",
            commercial_register="CR",
            license_number="L1",
        )
        InvoiceSettings._seed_from_tenant(settings, tenant)
        assert settings.company_name_en == "Company EN"
        assert settings.phone_1 == "050"
        assert settings.tax_number == "T1"

    def test_seed_from_tenant_none(self):
        from models.invoice_settings import InvoiceSettings

        settings = InvoiceSettings()
        assert InvoiceSettings._seed_from_tenant(settings, None) is settings

    def test_get_active_returns_snapshot_from_explicit_tenant(self, db_session, sample_tenant):
        from models.invoice_settings import InvoiceSettings

        sample_tenant.name_ar = "شركة المعروض"
        db_session.flush()
        snapshot = InvoiceSettings.get_active(tenant_id=sample_tenant.id)
        assert snapshot.tenant_id == sample_tenant.id
        assert snapshot.company_name_ar == "شركة المعروض"
        assert snapshot.is_active is True

    def test_get_active_never_persists_rows(self, db_session, sample_tenant):
        from models.invoice_settings import InvoiceSettings

        InvoiceSettings.get_active(tenant_id=sample_tenant.id)
        rows = db_session.query(InvoiceSettings).filter_by(tenant_id=sample_tenant.id).count()
        assert rows == 0

    def test_get_active_unknown_tenant_returns_none(self, db_session):
        from models.invoice_settings import InvoiceSettings

        assert InvoiceSettings.get_active(999999999) is None

    def test_get_active_no_context_returns_none(self):
        from models.invoice_settings import InvoiceSettings

        assert InvoiceSettings.get_active() is None

    def test_get_active_from_current_user(self, db_session, sample_tenant, mocker):
        from models.invoice_settings import InvoiceSettings

        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=sample_tenant.id)
        snapshot = InvoiceSettings.get_active(user="irrelevant")
        assert snapshot.tenant_id == sample_tenant.id

    def test_get_active_user_resolution_failure_returns_none(self, mocker):
        from models.invoice_settings import InvoiceSettings

        mocker.patch("utils.tenanting.get_active_tenant_id", side_effect=RuntimeError("auth"))
        assert InvoiceSettings.get_active(user="irrelevant") is None

    def test_company_print_context(self, db_session, sample_tenant):
        from models.invoice_settings import InvoiceSettings

        sample_tenant.name_ar = "أ"
        sample_tenant.name_en = "En"
        sample_tenant.logo_url = "logo.png"
        db_session.flush()
        tenant, settings, company = InvoiceSettings.company_print_context(sample_tenant.id)
        assert tenant.id == sample_tenant.id
        assert company["name_en"] == "En"
        assert company["logo_url"] == "logo.png"

    def test_company_print_context_explicit_tenant_id(self, db_session, sample_tenant):
        from models.invoice_settings import InvoiceSettings

        sample_tenant.address_ar = ""
        sample_tenant.address_en = "Addr"
        db_session.flush()
        tenant, _, company = InvoiceSettings.company_print_context(sample_tenant.id)
        assert tenant.id == sample_tenant.id
        assert company["address"] == "Addr"

    def test_to_dict(self):
        from models.invoice_settings import InvoiceSettings

        s = InvoiceSettings()
        s.id = 1
        s.company_name_ar = "أ"
        s.company_name_en = "En"
        s.logo_url = "l.png"
        s.address_ar = "ع"
        s.address_en = "En"
        s.phone_1 = "1"
        s.phone_2 = "2"
        s.email = "e"
        s.website = "w"
        s.tax_number = "T"
        s.header_color = "#000"
        s.accent_color = "#fff"
        s.active_template = "modern"
        s.default_language = "ar"
        s.enable_qr_code = True
        s.show_logo = True
        s.show_barcode = False
        d = s.to_dict()
        assert d["company_name_en"] == "En"
        assert d["enable_qr_code"] is True

    def test_get_active_auth_exception_during_user_resolution(self, mocker):
        from models.invoice_settings import InvoiceSettings

        class _BrokenUser:
            @property
            def is_authenticated(self):
                raise RuntimeError("auth")

        mocker.patch("utils.tenanting.get_active_tenant_id", side_effect=RuntimeError("auth"))
        assert InvoiceSettings.get_active(user=_BrokenUser()) is None

    def test_get_active_auth_context_exception(self, mocker):
        from models.invoice_settings import InvoiceSettings

        mocker.patch("utils.tenanting.get_active_tenant_id", side_effect=RuntimeError("auth"))
        assert InvoiceSettings.get_active(user="irrelevant") is None

    def test_repr(self):
        from models.invoice_settings import InvoiceSettings

        s = InvoiceSettings()
        s.company_name_ar = "شركة"
        assert "شركة" in repr(s)
