from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import _chain_query, app_factory, bypass_permission_auth, unauthenticated_client


def _sale_query(sale=None, not_found=False):
    q = MagicMock()
    inner = MagicMock()
    if not_found:
        inner.first_or_404.side_effect = NotFound()
    else:
        inner.first_or_404.return_value = sale
    inner.filter.return_value = inner
    q.filter_by.return_value = inner
    q.filter.return_value = inner
    return q


def _customer_query(customer=None, not_found=False):
    return _sale_query(customer, not_found)


@contextmanager
def _whatsapp_patches(sale=None, customer=None, sale_not_found=False, customer_not_found=False):
    with patch('utils.tenanting.get_active_tenant_id', return_value=1), \
         patch('models.Sale') as sale_cls, \
         patch('models.Customer') as customer_cls, \
         patch('routes.whatsapp.WhatsAppService') as wa_svc, \
         patch('routes.whatsapp.flash') as flash, \
         patch('flask.current_app') as app:
        sale_cls.query = _sale_query(sale, sale_not_found)
        customer_cls.query = _customer_query(customer, customer_not_found)
        app.logger = MagicMock()
        yield {'wa_svc': wa_svc, 'flash': flash}


@pytest.fixture
def whatsapp_client(app_factory, bypass_permission_auth):
    from routes.whatsapp import whatsapp_bp
    app = app_factory(whatsapp_bp)
    return app.test_client()


class TestWhatsAppAuth:
    def test_send_invoice_requires_login(self, whatsapp_client):
        with unauthenticated_client(whatsapp_client):
            resp = whatsapp_client.post('/whatsapp/send-invoice/1')
        assert resp.status_code == 401

    def test_send_reminder_requires_admin(self, whatsapp_client, mock_user):
        mock_user.is_admin.return_value = False
        with patch('utils.decorators.is_admin_surface_user', return_value=False):
            resp = whatsapp_client.post('/whatsapp/send-reminder/1')
        assert resp.status_code == 403


class TestSendInvoice:
    def test_success(self, whatsapp_client):
        customer = MagicMock(phone='+971500000001')
        sale = MagicMock(customer=customer, sale_number='INV-100')
        with _whatsapp_patches(sale=sale) as mocks:
            mocks['wa_svc'].send_invoice.return_value = {'success': True}
            resp = whatsapp_client.post('/whatsapp/send-invoice/5', data={'pdf_url': 'https://pdf'})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        mocks['wa_svc'].send_invoice.assert_called_once_with(
            phone='+971500000001',
            invoice_number='INV-100',
            pdf_url='https://pdf',
        )
        mocks['flash'].assert_called_once()

    def test_missing_customer_phone(self, whatsapp_client):
        sale = MagicMock(customer=None)
        with _whatsapp_patches(sale=sale) as mocks:
            resp = whatsapp_client.post('/whatsapp/send-invoice/5')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is False
        assert 'phone' in data['error'].lower()
        mocks['wa_svc'].send_invoice.assert_not_called()

    def test_customer_without_phone(self, whatsapp_client):
        sale = MagicMock(customer=MagicMock(phone=None))
        with _whatsapp_patches(sale=sale) as mocks:
            resp = whatsapp_client.post('/whatsapp/send-invoice/5')
        assert resp.get_json()['success'] is False
        mocks['wa_svc'].send_invoice.assert_not_called()

    def test_service_failure(self, whatsapp_client):
        customer = MagicMock(phone='+971500000001')
        sale = MagicMock(customer=customer, sale_number='INV-101')
        with _whatsapp_patches(sale=sale) as mocks, \
             patch('utils.error_messages.ErrorMessages.whatsapp_failed', return_value='failed'):
            mocks['wa_svc'].send_invoice.return_value = {'success': False, 'error': 'gateway down'}
            resp = whatsapp_client.post('/whatsapp/send-invoice/5')
        assert resp.get_json()['success'] is False
        mocks['flash'].assert_called()

    def test_tenant_isolation_404(self, whatsapp_client):
        with _whatsapp_patches(sale_not_found=True):
            resp = whatsapp_client.post('/whatsapp/send-invoice/999')
        assert resp.status_code == 404


class TestSendReminder:
    def test_success(self, whatsapp_client):
        customer = MagicMock(phone='+971500000002', name='Ali', get_balance_aed=MagicMock(return_value=Decimal('150.50')))
        with _whatsapp_patches(customer=customer) as mocks:
            mocks['wa_svc'].send_payment_reminder.return_value = {'success': True}
            resp = whatsapp_client.post('/whatsapp/send-reminder/3')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        mocks['wa_svc'].send_payment_reminder.assert_called_once()

    def test_missing_phone(self, whatsapp_client):
        customer = MagicMock(phone=None, name='NoPhone')
        with _whatsapp_patches(customer=customer) as mocks:
            resp = whatsapp_client.post('/whatsapp/send-reminder/3')
        assert resp.get_json()['success'] is False
        mocks['wa_svc'].send_payment_reminder.assert_not_called()

    def test_service_failure(self, whatsapp_client):
        customer = MagicMock(phone='+971500000002', name='Ali', get_balance_aed=MagicMock(return_value=Decimal('10')))
        with _whatsapp_patches(customer=customer) as mocks, \
             patch('utils.error_messages.ErrorMessages.whatsapp_failed', return_value='failed'):
            mocks['wa_svc'].send_payment_reminder.return_value = {'success': False, 'error': 'rate limit'}
            resp = whatsapp_client.post('/whatsapp/send-reminder/3')
        assert resp.get_json()['success'] is False

    def test_tenant_isolation_404(self, whatsapp_client):
        with _whatsapp_patches(customer_not_found=True):
            resp = whatsapp_client.post('/whatsapp/send-reminder/999')
        assert resp.status_code == 404


class TestConnection:
    def test_not_configured(self, whatsapp_client):
        with patch('routes.whatsapp.WhatsAppService.is_enabled', return_value=False):
            resp = whatsapp_client.get('/whatsapp/test')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is False
        assert 'WHATSAPP_API_KEY' in data['error']

    def test_configured(self, whatsapp_client):
        with patch('routes.whatsapp.WhatsAppService.is_enabled', return_value=True):
            resp = whatsapp_client.get('/whatsapp/test')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
