from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from flask import make_response


def _chain_query(**terminals):
    q = MagicMock(name='query_chain')
    q.return_value = q
    for method in ('filter', 'filter_by', 'order_by', 'join', 'outerjoin', 'group_by', 'limit', 'offset'):
        getattr(q, method).return_value = q
    inner = q.filter.return_value
    inner.first.return_value = terminals.get('first')
    inner.scalar.return_value = terminals.get('scalar', 0)
    inner.all.return_value = terminals.get('all', [])
    inner.count.return_value = terminals.get('count', 0)
    inner.exists.return_value.scalar.return_value = terminals.get('exists', True)
    q.scalar.return_value = terminals.get('scalar', 0)
    q.all.return_value = terminals.get('all', [])
    pag = MagicMock(name='pagination')
    pag.items = terminals.get('all', [])
    pag.page = 1
    pag.per_page = 20
    pag.total = len(pag.items)
    pag.pages = 1
    q.order_by.return_value.paginate.return_value = pag
    q.paginate.return_value = pag
    return q




class TestCustomersIndex:
    def test_index_returns_200(self, customers_client):
        resp = customers_client.get('/customers/')
        assert resp.status_code == 200

    def test_index_with_search(self, customers_client):
        resp = customers_client.get('/customers/?search=Test&type=regular')
        assert resp.status_code == 200


class TestCustomersExport:
    def test_export_csv(self, customers_client, bypass_customers_auth):
        _, customer = bypass_customers_auth
        with patch('routes.customers.send_file', return_value=make_response(b'data', 200)):
            resp = customers_client.get('/customers/export?format=csv')
        assert resp.status_code == 200


class TestCustomersCrud:
    def test_create_get(self, customers_client):
        resp = customers_client.get('/customers/create')
        assert resp.status_code == 200

    def test_create_post_success(self, customers_client, bypass_customers_auth):
        with patch('routes.customers.db') as mock_db, \
             patch('utils.tenant_limits.check_customers_limit'), \
             patch('routes.customers.Customer') as Cust:
            inst = MagicMock(id=5)
            Cust.return_value = inst
            resp = customers_client.post('/customers/create', data={
                'name': 'New Customer',
                'phone': '0501111111',
                'customer_type': 'regular',
            }, follow_redirects=False)
        assert resp.status_code in (200, 302)

    def test_view_customer(self, customers_client):
        resp = customers_client.get('/customers/1')
        assert resp.status_code == 200

    def test_edit_get(self, customers_client):
        resp = customers_client.get('/customers/1/edit')
        assert resp.status_code == 200

    def test_edit_post(self, customers_client, bypass_customers_auth):
        with patch('routes.customers.db') as mock_db:
            resp = customers_client.post('/customers/1/edit', data={
                'name': 'Updated',
                'phone': '0502222222',
                'customer_type': 'regular',
            }, follow_redirects=False)
        assert resp.status_code in (200, 302)

    def test_delete_post(self, customers_client):
        with patch('routes.customers.db') as mock_db, \
             patch('routes.customers._customer_in_scope', return_value=True):
            resp = customers_client.post('/customers/1/delete', follow_redirects=False)
        assert resp.status_code in (200, 302)


class TestCustomersApi:
    def test_api_search(self, customers_client):
        resp = customers_client.get('/customers/api/search?q=Test')
        assert resp.status_code == 200

    def test_customer_balance(self, customers_client):
        resp = customers_client.get('/customers/1/balance')
        assert resp.status_code == 200

    def test_customer_sales(self, customers_client):
        with patch('routes.customers._get_unpaid_sales', return_value=[]):
            resp = customers_client.get('/customers/1/sales')
        assert resp.status_code == 200


class TestCustomersScopedHelpers:
    def test_customer_in_scope_false(self):
        from routes.customers import _customer_in_scope

        with patch('routes.customers.branch_scope_id', return_value=2), \
             patch('routes.customers._scoped_customer_query', return_value=_chain_query(exists=False)), \
             patch('routes.customers.db') as mock_db:
            mock_db.session.query.return_value.scalar.return_value = False
            assert _customer_in_scope(99) is False

    def test_attach_customer_branch_labels(self):
        from routes.customers import _attach_customer_branch_labels

        c = MagicMock(id=1)
        branch = MagicMock(id=2, name='Main', code='M1')
        with patch('routes.customers.db') as mock_db, \
             patch('models.Branch') as Branch:
            mock_db.session.query.return_value.filter.return_value.all.side_effect = [
                [(1, 2)],
                [],
                [],
            ]
            Branch.query.filter.return_value.all.return_value = [branch]
            _attach_customer_branch_labels([c])
        assert hasattr(c, 'branch_labels')

    def test_attach_empty_customers(self):
        from routes.customers import _attach_customer_branch_labels

        _attach_customer_branch_labels([])


class TestCustomersStatement:
    def test_statement_returns_200(self, customers_client, bypass_customers_auth):
        _, customer = bypass_customers_auth
        line = MagicMock()
        line.quantity = 1
        line.unit_price = 100
        line.discount_percent = 0
        line.line_total = 100
        line.notes = ''
        line.product = MagicMock(sku='SKU1', unit='pc')
        line.product.get_display_name.return_value = 'Item'
        sale = MagicMock(
            id=1, sale_number='S-1', sale_date=MagicMock(), payment_status='paid',
            subtotal=100, discount_amount=0, shipping_cost=0, tax_rate=5, tax_amount=0,
            total_amount=100, amount_aed=100, paid_amount_aed=100, balance_due=0,
            currency='AED', exchange_rate=1, notes='', lines=[line],
        )
        sale.seller = MagicMock()
        sale.seller.get_display_name.return_value = 'Seller'
        sale.payments.order_by.return_value.all.return_value = []
        payment = MagicMock(
            id=2, payment_number='P-1', payment_date=MagicMock(), amount_aed=50, amount=50,
            currency='AED', exchange_rate=1, reference_number='REF', payment_method='cash',
            payment_confirmed=True, direction='incoming', notes='', cheque_number=None, bank_name=None,
        )
        payment.get_method_display.return_value = 'نقد'
        payment.user = None
        receipt = MagicMock(
            id=3, receipt_number='RCV-1', receipt_date=MagicMock(), amount_aed=25, amount=25,
            currency='AED', exchange_rate=1, payment_method='cash', payment_confirmed=True, notes='',
        )
        receipt.get_method_display.return_value = 'نقد'
        receipt.user = None
        with patch('routes.customers.Sale') as SaleMod, \
             patch('models.Payment') as PayMod, \
             patch('models.Receipt') as RcvMod, \
             patch('routes.customers.branch_scope_id', return_value=1):
            SaleMod.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [sale]
            PayMod.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [payment]
            RcvMod.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [receipt]
            resp = customers_client.get('/customers/1/statement?date_from=2025-01-01&date_to=2025-12-31')
        assert resp.status_code == 200

    def test_statement_out_of_scope(self, customers_client, bypass_customers_auth):
        with patch('routes.customers._customer_in_scope', return_value=False):
            resp = customers_client.get('/customers/1/statement')
        assert resp.status_code == 403

    def test_export_excel(self, customers_client, bypass_customers_auth):
        with patch('routes.customers.send_file', return_value=make_response(b'data', 200)):
            resp = customers_client.get('/customers/export?format=xlsx')
        assert resp.status_code == 200

    def test_create_post_validation_error(self, customers_client, bypass_customers_auth):
        with patch('routes.customers.db') as mock_db, \
             patch('utils.tenant_limits.check_customers_limit', side_effect=Exception('limit')):
            resp = customers_client.post('/customers/create', data={'name': '', 'phone': ''})
        assert resp.status_code in (200, 302)

    def test_delete_blocked_with_sales(self, customers_client, bypass_customers_auth):
        with patch('routes.customers.db') as mock_db, \
             patch('routes.customers._customer_in_scope', return_value=True), \
             patch('routes.customers.Sale') as SaleMod:
            SaleMod.query.filter_by.return_value.count.return_value = 2
            resp = customers_client.post('/customers/1/delete', follow_redirects=False)
        assert resp.status_code in (200, 302)

    def test_scoped_customer_query_with_branch(self):
        from routes.customers import _scoped_customer_query

        base_q = MagicMock()
        filtered = MagicMock()
        base_q.filter.return_value = filtered
        subq = MagicMock()
        subq.where.return_value = subq
        subq.union.return_value = subq
        with patch('routes.customers.branch_scope_id', return_value=3), \
             patch('routes.customers.tenant_query', return_value=base_q), \
             patch('routes.customers.select', return_value=subq):
            result = _scoped_customer_query()
        assert result is filtered
        base_q.filter.assert_called_once()

    def test_get_customer_balance_scoped_branch(self):
        from routes.customers import _get_customer_balance

        with patch('routes.customers.branch_scope_id', return_value=2), \
             patch('routes.customers.PaymentService.get_customer_balance_scoped', return_value=Decimal('75')) as scoped:
            bal = _get_customer_balance(5)
        assert bal == Decimal('75')
        scoped.assert_called_once_with(5, branch_id=2)

    def test_get_unpaid_sales_branch_filter(self):
        from routes.customers import _get_unpaid_sales

        class _Col:
            def __eq__(self, other):
                return MagicMock()
            def __gt__(self, other):
                return MagicMock()
            def asc(self):
                return MagicMock()

        sale = MagicMock(id=1)
        chain = MagicMock()
        filtered = MagicMock()
        chain.filter.return_value = filtered
        filtered.order_by.return_value.all.return_value = [sale]
        with patch('routes.customers.Sale') as SaleMod, \
             patch('routes.customers.branch_scope_id', return_value=4):
            SaleMod.customer_id = _Col()
            SaleMod.status = _Col()
            SaleMod.balance_due = _Col()
            SaleMod.sale_date = _Col()
            SaleMod.branch_id = _Col()
            SaleMod.query.filter.return_value = chain
            result = _get_unpaid_sales(9)
        assert len(result) == 1
        chain.filter.assert_called_once()

    def test_delete_exception_soft_delete_fallback(self, customers_client, bypass_customers_auth):
        _, customer = bypass_customers_auth
        refetched = MagicMock(name='Refetched', is_active=True)
        with patch('routes.customers.db') as mock_db, \
             patch('routes.customers._customer_in_scope', return_value=True), \
             patch('routes.customers.get_active_tenant_id', return_value=1), \
             patch('routes.customers.Sale') as SaleMod, \
             patch('models.Payment') as PayMod, \
             patch('models.Receipt') as RcvMod, \
             patch('routes.customers.Customer') as CustMod, \
             patch('routes.customers.current_app') as capp:
            SaleMod.query.filter_by.return_value.count.return_value = 0
            PayMod.query.filter_by.return_value.count.return_value = 0
            RcvMod.query.filter_by.return_value.count.return_value = 0
            mock_db.session.commit.side_effect = [RuntimeError('fk block'), None]
            CustMod.query.filter_by.return_value.first.return_value = refetched
            capp.logger = MagicMock()
            resp = customers_client.post('/customers/1/delete', follow_redirects=False)
        assert resp.status_code in (200, 302)
        assert refetched.is_active is False

    def test_delete_fallback_inner_failure(self, customers_client, bypass_customers_auth):
        with patch('routes.customers.db') as mock_db, \
             patch('routes.customers._customer_in_scope', return_value=True), \
             patch('routes.customers.get_active_tenant_id', return_value=1), \
             patch('routes.customers.Sale') as SaleMod, \
             patch('models.Payment') as PayMod, \
             patch('models.Receipt') as RcvMod, \
             patch('routes.customers.Customer') as CustMod, \
             patch('routes.customers.current_app') as capp:
            SaleMod.query.filter_by.return_value.count.return_value = 0
            PayMod.query.filter_by.return_value.count.return_value = 0
            RcvMod.query.filter_by.return_value.count.return_value = 0
            mock_db.session.commit.side_effect = RuntimeError('fk block')
            CustMod.query.filter_by.return_value.first.side_effect = RuntimeError('refetch fail')
            capp.logger = MagicMock()
            resp = customers_client.post('/customers/1/delete', follow_redirects=False)
        assert resp.status_code in (200, 302)


class TestCustomersIndexAndExport:
    def test_index_with_branch_columns(self, customers_client, bypass_customers_auth):
        with patch('routes.customers.should_show_all_branch_columns', return_value=True), \
             patch('routes.customers._attach_customer_branch_labels') as attach:
            resp = customers_client.get('/customers/?search=Test&type=regular')
        assert resp.status_code == 200
        attach.assert_called_once()

    def test_export_scoped_branch_balances(self, customers_client, bypass_customers_auth):
        _, customer = bypass_customers_auth
        with patch('routes.customers.branch_scope_id', return_value=2), \
             patch('routes.customers._scoped_customer_query', return_value=_chain_query(all=[customer])), \
             patch('routes.customers.db') as mock_db, \
             patch('routes.customers.send_file', return_value=make_response(b'data', 200)):
            mock_db.session.query.return_value.filter.return_value.group_by.return_value.all.side_effect = [
                [(1, 100)],
                [(1, 50)],
                [(1, 10)],
            ]
            resp = customers_client.get('/customers/export?format=csv&search=Test&type=regular')
        assert resp.status_code == 200

    def test_api_search_empty_query_lists_all(self, customers_client, bypass_customers_auth):
        with patch('routes.customers._scoped_customer_query', return_value=_chain_query(all=[bypass_customers_auth[1]])):
            resp = customers_client.get('/customers/api/search')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_customer_balance_forbidden(self, customers_client):
        with patch('routes.customers._customer_in_scope', return_value=False):
            resp = customers_client.get('/customers/1/balance')
        assert resp.status_code == 403

    def test_customer_balance_currency_fallback(self, customers_client):
        with patch('routes.customers.resolve_default_currency', side_effect=Exception('no tenant')):
            resp = customers_client.get('/customers/1/balance')
        assert resp.status_code == 200

    def test_customer_sales_scoped_with_balance(self, customers_client):
        sale = MagicMock(
            id=1, sale_number='S-1', sale_date=MagicMock(strftime=lambda fmt: '2025-01-01'),
            amount_aed=Decimal('100'), paid_amount_aed=Decimal('40'), currency='AED',
        )
        chain = MagicMock()
        filtered = MagicMock()
        chain.filter.return_value = filtered
        filtered.order_by.return_value.all.return_value = [sale]
        with patch('routes.customers.Sale') as SaleMod, \
             patch('routes.customers.branch_scope_id', return_value=3):
            SaleMod.query.filter_by.return_value = chain
            resp = customers_client.get('/customers/1/sales')
        assert resp.status_code == 200

    def test_customer_sales_out_of_scope(self, customers_client):
        with patch('routes.customers._customer_in_scope', return_value=False):
            resp = customers_client.get('/customers/1/sales')
        assert resp.status_code == 403

    def test_customer_in_scope_true_with_branch(self):
        from routes.customers import _customer_in_scope

        with patch('routes.customers.branch_scope_id', return_value=2), \
             patch('routes.customers._scoped_customer_query', return_value=_chain_query(exists=True)), \
             patch('routes.customers.db') as mock_db:
            mock_db.session.query.return_value.scalar.return_value = True
            assert _customer_in_scope(1) is True

    def test_delete_hard_success(self, customers_client, bypass_customers_auth):
        with patch('routes.customers.db') as mock_db, \
             patch('routes.customers._customer_in_scope', return_value=True), \
             patch('routes.customers.get_active_tenant_id', return_value=1), \
             patch('routes.customers.Sale') as SaleMod, \
             patch('models.Payment') as PayMod, \
             patch('models.Receipt') as RcvMod:
            SaleMod.query.filter_by.return_value.count.return_value = 0
            PayMod.query.filter_by.return_value.count.return_value = 0
            RcvMod.query.filter_by.return_value.count.return_value = 0
            resp = customers_client.post('/customers/1/delete', follow_redirects=False)
        assert resp.status_code in (200, 302)

    def test_delete_soft_with_branch_scope(self, customers_client, bypass_customers_auth):
        with patch('routes.customers.db') as mock_db, \
             patch('routes.customers._customer_in_scope', return_value=True), \
             patch('routes.customers.get_active_tenant_id', return_value=1), \
             patch('routes.customers.branch_scope_id', return_value=2), \
             patch('routes.customers.Sale') as SaleMod, \
             patch('models.Payment') as PayMod, \
             patch('models.Receipt') as RcvMod:
            SaleMod.query.filter_by.return_value.filter.return_value.count.return_value = 1
            PayMod.query.filter_by.return_value.filter.return_value.count.return_value = 0
            RcvMod.query.filter_by.return_value.filter.return_value.count.return_value = 0
            resp = customers_client.post('/customers/1/delete', follow_redirects=False)
        assert resp.status_code in (200, 302)
