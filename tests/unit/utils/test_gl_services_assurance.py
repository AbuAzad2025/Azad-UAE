"""GL service wrappers — lazy imports and default currency resolution."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


class TestGlServiceWrappers:
    def test_gl_ensure_core_accounts(self, mocker):
        gl = mocker.patch('services.gl_service.GLService')
        from utils.gl_services import gl_ensure_core_accounts
        gl_ensure_core_accounts(tenant_id=1)
        gl.ensure_core_accounts.assert_called_once_with(tenant_id=1)

    def test_gl_get_customer_credit_account(self, mocker):
        gl = mocker.patch('services.gl_service.GLService')
        customer = MagicMock()
        from utils.gl_services import gl_get_customer_credit_account
        gl_get_customer_credit_account(customer, branch_id=2, tenant_id=3)
        gl.get_customer_credit_account.assert_called_once_with(customer, branch_id=2, tenant_id=3)

    def test_gl_get_customer_credit_concept(self, mocker):
        gl = mocker.patch('services.gl_service.GLService')
        customer = MagicMock()
        from utils.gl_services import gl_get_customer_credit_concept
        gl_get_customer_credit_concept(customer)
        gl.get_customer_credit_concept.assert_called_once_with(customer)

    def test_gl_get_default_liquidity_account(self, mocker):
        gl = mocker.patch('services.gl_service.GLService')
        from utils.gl_services import gl_get_default_liquidity_account
        gl_get_default_liquidity_account('cash', tenant_id=1, branch_id=2)
        gl.get_default_liquidity_account.assert_called_once_with('cash', branch_id=2, tenant_id=1)

    def test_gl_create_manual_entry(self, mocker):
        gl = mocker.patch('services.gl_service.GLService')
        from utils.gl_services import gl_create_manual_entry
        gl_create_manual_entry('a', description='x')
        gl.create_manual_entry.assert_called_once_with('a', description='x')

    def test_gl_post_or_fail_default_currency(self, mocker):
        post = mocker.patch('services.gl_posting.post_or_fail')
        mocker.patch('utils.currency_utils.get_system_default_currency', return_value='AED')
        from utils.gl_services import gl_post_or_fail
        gl_post_or_fail([], 'desc', 'sale', 1, branch_id=2, tenant_id=3)
        post.assert_called_once()
        assert post.call_args.kwargs['currency'] == 'AED'

    def test_gl_post_or_fail_explicit_currency(self, mocker):
        post = mocker.patch('services.gl_posting.post_or_fail')
        from utils.gl_services import gl_post_or_fail
        gl_post_or_fail([], 'desc', 'sale', 1, currency='USD', exchange_rate=Decimal('3.67'))
        assert post.call_args.kwargs['currency'] == 'USD'

    def test_gl_resolve_exchange_rate(self, mocker):
        svc = mocker.patch('services.exchange_rate_service.ExchangeRateService')
        mocker.patch('utils.currency_utils.get_system_default_currency', return_value='AED')
        from utils.gl_services import gl_resolve_exchange_rate
        from datetime import date
        gl_resolve_exchange_rate(date.today(), 'USD', tenant_id=1)
        svc.resolve_exchange_rate_for_transaction.assert_called_once()

    def test_gl_next_entry_number(self, mocker):
        helper = mocker.patch('services.gl_helpers.next_entry_number', return_value='JE-1')
        from utils.gl_services import gl_next_entry_number
        assert gl_next_entry_number(4) == 'JE-1'
        helper.assert_called_once_with(4)

    def test_gl_post_entry(self, mocker):
        gl = mocker.patch('services.gl_service.GLService')
        from utils.gl_services import gl_post_entry
        gl_post_entry('lines')
        gl.post_entry.assert_called_once_with('lines')
