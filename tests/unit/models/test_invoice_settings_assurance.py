"""InvoiceSettings model — get_active seeding, print context, to_dict."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestInvoiceSettingsModel:
    def test_seed_from_tenant(self):
        from models.invoice_settings import InvoiceSettings

        settings = InvoiceSettings()
        tenant = MagicMock(
            name='Co',
            name_ar='شركة',
            name_en='Company EN',
            address_ar='ع',
            address_en='En',
            phone_1='050',
            mobile='055',
            email='a@co.com',
            tax_number='T1',
            commercial_register='CR',
            license_number='L1',
        )
        InvoiceSettings._seed_from_tenant(settings, tenant)
        assert settings.company_name_en == 'Company EN'
        assert settings.phone_1 == '050'
        assert settings.tax_number == 'T1'

    def test_seed_from_tenant_none(self):
        from models.invoice_settings import InvoiceSettings

        settings = InvoiceSettings()
        assert InvoiceSettings._seed_from_tenant(settings, None) is settings

    def test_get_active_existing(self, app, mocker):
        from models.invoice_settings import InvoiceSettings

        existing = InvoiceSettings()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = existing
        mocker.patch.object(InvoiceSettings, 'query', mock_q)
        with app.app_context():
            assert InvoiceSettings.get_active(tenant_id=1) is existing

    def test_get_active_creates_for_tenant(self, app, mocker):
        from models.invoice_settings import InvoiceSettings

        tenant = MagicMock(id=2, name='T', name_ar='', name_en='', address_ar=None,
                           address_en=None, phone_1=None, mobile=None, email=None,
                           tax_number=None, commercial_register=None, license_number=None)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch.object(InvoiceSettings, 'query', mock_q)
        mocker.patch('models.invoice_settings.db.session.get', return_value=tenant)
        mock_session = mocker.patch('models.invoice_settings.db.session')
        with app.app_context():
            settings = InvoiceSettings.get_active(tenant_id=2)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        assert settings.tenant_id == 2

    def test_get_active_missing_tenant_falls_back_legacy(self, app, mocker):
        from models.invoice_settings import InvoiceSettings

        legacy = InvoiceSettings()
        first_chain = MagicMock()
        first_chain.first.return_value = None
        legacy_chain = MagicMock()
        legacy_chain.filter.return_value.first.return_value = legacy
        mock_q = MagicMock()
        mock_q.filter_by.side_effect = [first_chain, legacy_chain]
        mocker.patch.object(InvoiceSettings, 'query', mock_q)
        mocker.patch('models.invoice_settings.db.session.get', return_value=None)
        with app.app_context():
            assert InvoiceSettings.get_active(tenant_id=99) is legacy

    def test_get_active_from_current_user(self, app, mocker):
        from models.invoice_settings import InvoiceSettings

        existing = InvoiceSettings()
        user = MagicMock(is_authenticated=True)
        mocker.patch('flask_login.current_user', user)
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=5)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = existing
        mocker.patch.object(InvoiceSettings, 'query', mock_q)
        with app.app_context():
            assert InvoiceSettings.get_active() is existing

    def test_get_active_auth_exception_legacy(self, app, mocker):
        from models.invoice_settings import InvoiceSettings

        legacy = InvoiceSettings()
        mocker.patch('flask_login.current_user', side_effect=RuntimeError('auth'))
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value.first.return_value = legacy
        mocker.patch.object(InvoiceSettings, 'query', mock_q)
        with app.app_context():
            assert InvoiceSettings.get_active() is legacy

    def test_company_print_context(self, app, mocker):
        from models.invoice_settings import InvoiceSettings

        tenant = MagicMock(id=1)
        settings = InvoiceSettings()
        mocker.patch('models.tenant.Tenant.get_current', return_value=tenant)
        mocker.patch('utils.tenant_branding.get_print_header_context', return_value={
            'company_name_ar': 'أ',
            'company_name_en': 'En',
            'address_ar': 'ع',
            'address_en': '',
            'phone': '050',
            'email': 'e@x.com',
            'tax_number': 'T',
            'logo_url': 'logo.png',
        })
        mocker.patch.object(InvoiceSettings, 'get_active', return_value=settings)
        with app.app_context():
            t, s, ctx = InvoiceSettings.company_print_context()
        assert ctx['name_en'] == 'En'
        assert ctx['logo_url'] == 'logo.png'

    def test_company_print_context_explicit_tenant_id(self, app, mocker):
        from models.invoice_settings import InvoiceSettings

        tenant = MagicMock(id=7)
        mocker.patch('models.invoice_settings.db.session.get', return_value=tenant)
        mocker.patch('utils.tenant_branding.get_print_header_context', return_value={
            'company_name_ar': '', 'company_name_en': 'X', 'address_ar': '',
            'address_en': 'Addr', 'phone': '', 'email': '', 'tax_number': '', 'logo_url': '',
        })
        mocker.patch.object(InvoiceSettings, 'get_active', return_value=InvoiceSettings())
        with app.app_context():
            t, _, ctx = InvoiceSettings.company_print_context(tenant_id=7)
        assert t is tenant
        assert ctx['address'] == 'Addr'

    def test_to_dict(self):
        from models.invoice_settings import InvoiceSettings

        s = InvoiceSettings()
        s.id = 1
        s.company_name_ar = 'أ'
        s.company_name_en = 'En'
        s.logo_url = 'l.png'
        s.address_ar = 'ع'
        s.address_en = 'En'
        s.phone_1 = '1'
        s.phone_2 = '2'
        s.email = 'e'
        s.website = 'w'
        s.tax_number = 'T'
        s.header_color = '#000'
        s.accent_color = '#fff'
        s.active_template = 'modern'
        s.default_language = 'ar'
        s.enable_qr_code = True
        s.show_logo = True
        s.show_barcode = False
        d = s.to_dict()
        assert d['company_name_en'] == 'En'
        assert d['enable_qr_code'] is True

    def test_get_active_auth_exception_during_user_resolution(self, app, mocker):
        from models.invoice_settings import InvoiceSettings

        class _BrokenUser:
            @property
            def is_authenticated(self):
                raise RuntimeError('auth')

        legacy = InvoiceSettings()
        mocker.patch('flask_login.current_user', _BrokenUser())
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value.first.return_value = legacy
        mocker.patch.object(InvoiceSettings, 'query', mock_q)
        with app.app_context():
            assert InvoiceSettings.get_active() is legacy

    def test_get_active_auth_context_exception(self, app, mocker):
        from models.invoice_settings import InvoiceSettings

        legacy = InvoiceSettings()
        mocker.patch('flask_login.current_user', side_effect=RuntimeError('auth'))
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value.first.return_value = legacy
        mocker.patch.object(InvoiceSettings, 'query', mock_q)
        with app.app_context():
            assert InvoiceSettings.get_active() is legacy

    def test_repr(self):
        from models.invoice_settings import InvoiceSettings

        s = InvoiceSettings()
        s.company_name_ar = 'شركة'
        assert 'شركة' in repr(s)
