from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import _chain_query, app_factory, bypass_permission_auth, unauthenticated_client


def _mock_supplier(**kwargs):
    s = MagicMock()
    s.id = kwargs.get('id', 1)
    s.name = kwargs.get('name', 'Vendor Co')
    s.phone = kwargs.get('phone', '0501234567')
    s.email = kwargs.get('email', 'v@example.com')
    s.supplier_type = kwargs.get('supplier_type', 'parts')
    s.is_active = kwargs.get('is_active', True)
    s.is_verified = kwargs.get('is_verified', False)
    s.tenant_id = kwargs.get('tenant_id', 1)
    s.preferred_currency = kwargs.get('preferred_currency', 'AED')
    s.purchases = MagicMock()
    return s


def _scoped_query(all_items=None):
    q = _chain_query(all=all_items or [])
    q.filter.return_value = q
    q.filter_by.return_value = q
    return q


@contextmanager
def _supplier_patches(**kwargs):
    suppliers = kwargs.get('suppliers', [_mock_supplier()])
    scoped = _scoped_query(suppliers)
    with ExitStack() as stack:
        stack.enter_context(patch('routes.suppliers.render_template', return_value='ok'))
        stack.enter_context(patch('routes.suppliers.tenant_query', return_value=scoped))
        stack.enter_context(patch('routes.suppliers.tenant_get_or_404', return_value=kwargs.get('supplier', _mock_supplier())))
        stack.enter_context(patch('routes.suppliers.get_active_tenant_id', return_value=1))
        stack.enter_context(patch('routes.suppliers.branch_scope_id', return_value=kwargs.get('branch_scope')))
        stack.enter_context(patch('routes.suppliers.should_show_all_branch_columns', return_value=kwargs.get('show_branches', False)))
        stack.enter_context(patch('routes.suppliers._supplier_in_scope', return_value=kwargs.get('in_scope', True)))
        stack.enter_context(patch('routes.suppliers._supplier_scoped_totals', return_value=([], Decimal('0'), Decimal('0'))))
        stack.enter_context(patch('routes.suppliers.LoggingCore.log_audit'))
        stack.enter_context(patch('routes.suppliers.log_mutation'))
        stack.enter_context(patch('routes.suppliers.atomic_transaction'))
        stack.enter_context(patch('routes.suppliers.resolve_default_currency', return_value='AED'))
        stack.enter_context(patch('extensions.limiter.limit', return_value=lambda f: f))
        stack.enter_context(patch('extensions.db.session'))
        yield {'scoped': scoped, 'suppliers': suppliers}


@pytest.fixture
def suppliers_client(app_factory, bypass_permission_auth):
    from routes.suppliers import suppliers_bp
    app = app_factory(suppliers_bp)
    return app.test_client()


class TestSuppliersHelpers:
    def test_supplier_in_scope_no_branch(self):
        from routes.suppliers import _supplier_in_scope
        with patch('routes.suppliers.branch_scope_id', return_value=None):
            assert _supplier_in_scope(1) is True

    def test_attach_branch_labels_empty(self):
        from routes.suppliers import _attach_supplier_branch_labels
        _attach_supplier_branch_labels([])

    def test_attach_branch_labels(self):
        from routes.suppliers import _attach_supplier_branch_labels
        supplier = _mock_supplier(id=3)
        purchase_row = MagicMock()
        purchase_row.all.return_value = [(3, 1)]
        payment_row = MagicMock()
        payment_row.all.return_value = [(3, 2)]
        branch = MagicMock(id=1, name='Main', code='M1')
        with patch('routes.suppliers.db.session') as sess, \
             patch('models.Branch.query') as bq:
            sess.query.side_effect = [purchase_row, payment_row]
            bq.filter.return_value.all.return_value = [branch]
            _attach_supplier_branch_labels([supplier])
        assert hasattr(supplier, 'branch_labels')


class TestSuppliersAuth:
    def test_index_requires_login(self, suppliers_client):
        with _supplier_patches(), unauthenticated_client(suppliers_client):
            resp = suppliers_client.get('/suppliers/')
        assert resp.status_code == 401


class TestSuppliersIndex:
    def test_index_renders(self, suppliers_client):
        with _supplier_patches():
            resp = suppliers_client.get('/suppliers/')
        assert resp.status_code == 200

    def test_index_search_and_type(self, suppliers_client):
        with _supplier_patches():
            resp = suppliers_client.get('/suppliers/?search=vendor&type=parts')
        assert resp.status_code == 200

    def test_index_branch_columns(self, suppliers_client):
        with _supplier_patches(show_branches=True), \
             patch('routes.suppliers._attach_supplier_branch_labels') as attach:
            resp = suppliers_client.get('/suppliers/')
        assert resp.status_code == 200
        attach.assert_called_once()


class TestSuppliersCreate:
    def test_create_get(self, suppliers_client):
        with _supplier_patches():
            resp = suppliers_client.get('/suppliers/create')
        assert resp.status_code == 200

    def test_create_missing_type(self, suppliers_client):
        with _supplier_patches():
            resp = suppliers_client.post('/suppliers/create', data={'name': 'New Vendor'})
        assert resp.status_code == 200

    def test_create_invalid_rating(self, suppliers_client):
        with _supplier_patches():
            resp = suppliers_client.post('/suppliers/create', data={
                'name': 'New Vendor',
                'supplier_type': 'parts',
                'rating': 'bad',
            })
        assert resp.status_code == 200

    def test_create_success(self, suppliers_client):
        supplier = _mock_supplier(id=9)
        with _supplier_patches(), \
             patch('routes.suppliers.Supplier', return_value=supplier), \
             patch('utils.field_validators.normalize_phone_optional', return_value='050'), \
             patch('utils.field_validators.validate_currency_code', return_value='AED'), \
             patch('utils.tenant_limits.check_suppliers_limit'):
            resp = suppliers_client.post('/suppliers/create', data={
                'name': 'New Vendor',
                'supplier_type': 'equipment',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_with_opening_balance(self, suppliers_client):
        supplier = _mock_supplier(id=10)
        with _supplier_patches(), \
             patch('routes.suppliers.Supplier', return_value=supplier), \
             patch('utils.field_validators.normalize_phone_optional', return_value=None), \
             patch('utils.field_validators.validate_currency_code', return_value='AED'), \
             patch('utils.tenant_limits.check_suppliers_limit'), \
             patch('services.gl_posting.post_or_fail'), \
             patch('services.gl_service.GLService.ensure_core_accounts'):
            resp = suppliers_client.post('/suppliers/create', data={
                'name': 'Balanced Vendor',
                'supplier_type': 'parts',
                'initial_balance': '500',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_tenant_limit_error(self, suppliers_client):
        from utils.tenant_limits import TenantLimitError
        with _supplier_patches(), \
             patch('utils.tenant_limits.check_suppliers_limit', side_effect=TenantLimitError('suppliers', 10, 10)):
            resp = suppliers_client.post('/suppliers/create', data={
                'name': 'Too Many',
                'supplier_type': 'parts',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_exception(self, suppliers_client):
        with _supplier_patches(), \
             patch('routes.suppliers.Supplier', side_effect=RuntimeError('db')):
            resp = suppliers_client.post('/suppliers/create', data={
                'name': 'Fail Vendor',
                'supplier_type': 'parts',
            })
        assert resp.status_code == 200


class TestSuppliersView:
    def test_view_success(self, suppliers_client):
        supplier = _mock_supplier()
        purchases_q = MagicMock()
        purchases_q.filter.return_value = purchases_q
        purchases_q.order_by.return_value.limit.return_value.all.return_value = []
        purchases_q.count.return_value = 0
        supplier.purchases.filter_by.return_value = purchases_q
        with _supplier_patches(supplier=supplier), \
             patch('routes.suppliers._supplier_scoped_totals', return_value=([], Decimal('100'), Decimal('40'))):
            resp = suppliers_client.get('/suppliers/1')
        assert resp.status_code == 200

    def test_view_out_of_scope(self, suppliers_client):
        with _supplier_patches(in_scope=False):
            resp = suppliers_client.get('/suppliers/1')
        assert resp.status_code == 403


class TestSuppliersEdit:
    def test_edit_get(self, suppliers_client):
        with _supplier_patches():
            resp = suppliers_client.get('/suppliers/1/edit')
        assert resp.status_code == 200

    def test_edit_post_success(self, suppliers_client):
        supplier = _mock_supplier()
        with _supplier_patches(supplier=supplier), \
             patch('utils.field_validators.normalize_phone_optional', return_value='050'), \
             patch('utils.field_validators.validate_currency_code', return_value='AED'):
            resp = suppliers_client.post('/suppliers/1/edit', data={
                'name': 'Updated Vendor',
                'supplier_type': 'parts',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_post_error(self, suppliers_client):
        supplier = _mock_supplier()
        with _supplier_patches(supplier=supplier), \
             patch('utils.field_validators.normalize_phone_optional', side_effect=RuntimeError('fail')):
            resp = suppliers_client.post('/suppliers/1/edit', data={'name': 'X'})
        assert resp.status_code == 200


class TestSuppliersDelete:
    def test_delete_soft(self, suppliers_client):
        supplier = _mock_supplier()
        with _supplier_patches(supplier=supplier), \
             patch('routes.suppliers.Purchase.query') as pq, \
             patch('routes.suppliers.Payment.query') as payq:
            pq.filter_by.return_value.count.return_value = 2
            payq.filter_by.return_value.count.return_value = 0
            resp = suppliers_client.post('/suppliers/1/delete', follow_redirects=False)
        assert resp.status_code == 302
        assert supplier.is_active is False

    def test_delete_hard(self, suppliers_client):
        supplier = _mock_supplier()
        with _supplier_patches(supplier=supplier), \
             patch('routes.suppliers.Purchase.query') as pq, \
             patch('routes.suppliers.Payment.query') as payq:
            pq.filter_by.return_value.count.return_value = 0
            payq.filter_by.return_value.count.return_value = 0
            resp = suppliers_client.post('/suppliers/1/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_fallback_soft(self, suppliers_client):
        supplier = _mock_supplier()
        session = MagicMock()
        session.commit.side_effect = [RuntimeError('fk'), None]
        with _supplier_patches(supplier=supplier), \
             patch('routes.suppliers.db.session', session), \
             patch('routes.suppliers.Purchase.query') as pq, \
             patch('routes.suppliers.Payment.query') as payq:
            pq.filter_by.return_value.count.return_value = 0
            payq.filter_by.return_value.count.return_value = 0
            resp = suppliers_client.post('/suppliers/1/delete', follow_redirects=False)
        assert resp.status_code == 302


class TestSuppliersStatement:
    def test_statement_renders(self, suppliers_client):
        supplier = _mock_supplier()
        purchase = MagicMock(
            purchase_date=datetime(2026, 1, 10),
            purchase_number='P-1',
            base_amount=Decimal('100'),
            total_amount=Decimal('100'),
            currency='AED',
            exchange_rate=Decimal('1'),
        )
        payment = MagicMock(
            payment_date=datetime(2026, 1, 15),
            payment_number='PAY-1',
            reference_number='',
            amount_aed=Decimal('40'),
            amount=Decimal('40'),
            currency='AED',
            exchange_rate=Decimal('1'),
            direction='outgoing',
            payment_method='cash',
            payment_confirmed=True,
            rejection_reason=None,
            notes='',
            cheque_number=None,
            bank_name=None,
            cheque_date=None,
        )
        purchases_q = MagicMock()
        purchases_q.filter.return_value = purchases_q
        purchases_q.order_by.return_value.all.return_value = [purchase]
        supplier.purchases.filter_by.return_value = purchases_q
        with _supplier_patches(supplier=supplier), \
             patch('routes.suppliers.Payment.query') as payq, \
             patch('utils.decorators.is_admin_surface_user', return_value=True):
            payq.filter_by.return_value = payq
            payq.filter.return_value = payq
            payq.order_by.return_value.all.return_value = [payment]
            resp = suppliers_client.get('/suppliers/1/statement?date_from=2026-01-01')
        assert resp.status_code == 200


class TestSuppliersApiSearch:
    def test_api_search_with_query(self, suppliers_client):
        with _supplier_patches(), \
             patch('routes.suppliers._supplier_scoped_totals', return_value=([], Decimal('10'), Decimal('3'))):
            resp = suppliers_client.get('/suppliers/api/search?q=vendor')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_api_search_empty_query(self, suppliers_client):
        with _supplier_patches(), \
             patch('routes.suppliers._supplier_scoped_totals', return_value=([], Decimal('0'), Decimal('0'))):
            resp = suppliers_client.get('/suppliers/api/search')
        assert resp.status_code == 200

    def test_api_search_error(self, suppliers_client):
        with _supplier_patches(), \
             patch('routes.suppliers._scoped_supplier_query', side_effect=RuntimeError('db')):
            resp = suppliers_client.get('/suppliers/api/search?q=x')
        assert resp.get_json() == []
