from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import _chain_query, app_factory, bypass_owner_auth, bypass_permission_auth, unauthenticated_client


def _mock_sale(**kwargs):
    sale = MagicMock()
    sale.id = kwargs.get('id', 1)
    sale.tenant_id = kwargs.get('tenant_id', 1)
    sale.branch_id = kwargs.get('branch_id', 2)
    sale.seller_id = kwargs.get('seller_id', 42)
    sale.sale_number = kwargs.get('sale_number', 'S-2026-0001')
    sale.status = kwargs.get('status', 'draft')
    sale.payment_status = kwargs.get('payment_status', 'unpaid')
    sale.total_amount = kwargs.get('total_amount', Decimal('100'))
    sale.currency = kwargs.get('currency', 'AED')
    sale.sale_date = kwargs.get('sale_date', datetime(2026, 6, 26))
    sale.discount_amount = kwargs.get('discount_amount', Decimal('0'))
    sale.notes = kwargs.get('notes', '')
    sale.calculate_totals = MagicMock()
    sale.seller = kwargs.get('seller', MagicMock(full_name='Seller', username='seller', get_display_name=lambda l: 'Seller'))
    sale.customer = kwargs.get('customer', MagicMock(name='Customer'))
    return sale


def _mock_product(**kwargs):
    product = MagicMock()
    product.id = kwargs.get('id', 10)
    product.tenant_id = kwargs.get('tenant_id', 1)
    product.cost_price = Decimal('50')
    product.unit = 'pcs'
    product.get_price_for_customer.return_value = Decimal('99')
    return product


def _mock_customer(**kwargs):
    customer = MagicMock()
    customer.id = kwargs.get('id', 5)
    customer.tenant_id = kwargs.get('tenant_id', 1)
    customer.customer_type = 'retail'
    return customer


def _mock_warehouse():
    wh = MagicMock()
    wh.id = 1
    wh.is_online = False
    return wh


@contextmanager
def _sales_patches(**kwargs):
    sale = kwargs.get('sale', _mock_sale())
    archived = kwargs.get('archived', [])

    def _tenant_get_or_404(model, pk, user=None):
        name = getattr(model, '__name__', str(model))
        if name == 'Sale':
            return sale if int(pk) == int(sale.id) else (_ for _ in ()).throw(NotFound())
        if name == 'Customer':
            return _mock_customer(id=pk)
        if name == 'Product':
            return _mock_product(id=pk)
        return MagicMock()

    def _tenant_get(model, pk, **kw):
        return _tenant_get_or_404(model, pk)

    def _tenant_query(model):
        return _chain_query(all=kwargs.get('sales_list', [sale]), count=kwargs.get('count', 1))

    def _session_get(model, pk):
        name = getattr(model, '__name__', str(model))
        if name == 'Tenant':
            t = MagicMock()
            t.default_currency = 'AED'
            t.name_ar = 'شركة'
            return t
        if name == 'Branch':
            b = MagicMock()
            b.name = 'Main'
            return b
        return None

    archived_q = MagicMock()
    archived_q.filter_by.return_value = archived_q
    archived_q.filter.return_value = archived_q
    archived_q.order_by.return_value = archived_q
    archived_q.limit.return_value = archived_q
    archived_q.all.return_value = archived
    archived_q.first_or_404.return_value = kwargs.get('archived_record', MagicMock())

    with ExitStack() as stack:
        stack.enter_context(patch('routes.sales.render_template', return_value='ok'))
        stack.enter_context(patch('routes.sales.get_active_tenant_id', return_value=kwargs.get('tid', 1)))
        stack.enter_context(patch('routes.sales.tenant_query', side_effect=_tenant_query))
        stack.enter_context(patch('routes.sales.tenant_get_or_404', side_effect=_tenant_get_or_404))
        stack.enter_context(patch('routes.sales.tenant_get', side_effect=_tenant_get))
        stack.enter_context(patch('routes.sales.db.session.get', side_effect=_session_get))
        stack.enter_context(patch('routes.sales.db.session.query', side_effect=lambda *a, **k: archived_q))
        stack.enter_context(patch('routes.sales.db.session.commit'))
        stack.enter_context(patch('routes.sales.db.session.rollback'))
        stack.enter_context(patch('routes.sales.db.session.delete'))
        stack.enter_context(patch('routes.sales.should_show_all_branch_columns', return_value=False))
        stack.enter_context(patch('routes.sales.StoreService.get_physical_warehouses', return_value=[_mock_warehouse()]))
        stack.enter_context(patch('routes.sales.get_accessible_warehouses', return_value=[_mock_warehouse()]))
        stack.enter_context(patch('routes.sales.ensure_warehouse_access'))
        stack.enter_context(patch('routes.sales.atomic_transaction', return_value=MagicMock(__enter__=lambda s: None, __exit__=lambda s, *a: None)))
        stack.enter_context(patch('routes.sales.SaleService.create_sale', return_value=sale))
        stack.enter_context(patch('routes.sales.SaleService.cancel_sale'))
        stack.enter_context(patch('routes.sales.SaleService.has_inventory_posted', return_value=kwargs.get('has_gl', False)))
        stack.enter_context(patch('routes.sales.StockService.get_product_stock', return_value=Decimal('25')))
        stack.enter_context(patch('utils.currency_utils.resolve_default_currency', return_value='AED'))
        stack.enter_context(patch('utils.currency_utils.get_system_default_currency', return_value='AED'))
        stack.enter_context(patch('routes.sales.LoggingCore.log_audit'))
        stack.enter_context(patch('routes.sales.LoggingCore.log_error'))
        stack.enter_context(patch('routes.sales.InvoiceSettings.get_active', return_value=MagicMock(
            enable_qr_code=False, active_template='modern', company_name_ar='Co',
        )))
        stack.enter_context(patch('routes.sales.number_to_arabic_words', return_value='مائة'))
        stack.enter_context(patch('routes.sales.generate_qr_data_url', return_value='data:image/png;base64,x'))
        stack.enter_context(patch('utils.tenant_branding.get_print_header_context', return_value={}))
        stack.enter_context(patch('models.User.query', _chain_query(all=kwargs.get('users', []))))
        stack.enter_context(patch('models.Payment.query', _chain_query(count=kwargs.get('payment_count', 0))))
        stack.enter_context(patch('models.Cheque.query', _chain_query(count=kwargs.get('cheque_count', 0))))
        stack.enter_context(patch('models.ArchivedRecord.query', archived_q))
        stack.enter_context(patch('services.archive_service.ArchiveService'))
        stack.enter_context(patch('services.gl_service.GLService.reverse_entry'))
        stack.enter_context(patch('utils.decorators.branch_scope_id', return_value=kwargs.get('branch_scope')))
        stack.enter_context(patch('extensions.limiter.limit', return_value=lambda f: f))
        yield {'sale': sale}


@pytest.fixture
def sales_client(app_factory, bypass_permission_auth):
    from routes.sales import sales_bp
    app = app_factory(sales_bp)
    return app.test_client()


@pytest.fixture
def sales_owner_client(app_factory, bypass_owner_auth):
    from routes.sales import sales_bp
    app = app_factory(sales_bp)
    return app.test_client()


class TestSalesAuth:
    def test_index_requires_login(self, sales_client):
        with _sales_patches(), unauthenticated_client(sales_client):
            resp = sales_client.get('/sales/')
        assert resp.status_code == 401

    def test_index_forbidden_without_permission(self, sales_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        bypass_permission_auth.is_super_admin.return_value = False
        with _sales_patches(), patch('utils.decorators.is_global_owner_user', return_value=False):
            resp = sales_client.get('/sales/')
        assert resp.status_code == 403


class TestSalesIndex:
    def test_index_renders(self, sales_client):
        with _sales_patches():
            resp = sales_client.get('/sales/')
        assert resp.status_code == 200

    def test_index_with_filters(self, sales_client, bypass_permission_auth):
        bypass_permission_auth.is_seller.return_value = True
        with _sales_patches(), patch('utils.decorators.branch_scope_id', return_value=2):
            resp = sales_client.get('/sales/?search=acme&status=draft&payment_status=unpaid&page=2')
        assert resp.status_code == 200


class TestSalesCreate:
    def test_create_get(self, sales_client):
        with _sales_patches():
            resp = sales_client.get('/sales/create?customer_id=5')
        assert resp.status_code == 200

    def test_create_get_no_tenant(self, sales_client):
        with _sales_patches(tid=None):
            resp = sales_client.get('/sales/create')
        assert resp.status_code == 200

    def test_create_post_success(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/create', data={
                'customer_id': '5',
                'line_count': '1',
                'lines[0][product_id]': '10',
                'lines[0][quantity]': '2',
                'lines[0][unit_price]': '50',
                'warehouse_id': '1',
                'payment_amount': '100',
                'payment_method': 'cash',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_post_no_lines(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/create', data={'customer_id': '5', 'line_count': '0'})
        assert resp.status_code == 302

    def test_create_post_negative_quantity_skipped(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/create', data={
                'customer_id': '5',
                'line_count': '1',
                'lines[0][product_id]': '10',
                'lines[0][quantity]': '-1',
            })
        assert resp.status_code == 302

    def test_create_post_zero_price_line(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/create', data={
                'customer_id': '5',
                'line_count': '1',
                'lines[0][product_id]': '10',
                'lines[0][quantity]': '1',
                'lines[0][unit_price]': '0',
                'warehouse_id': '1',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_post_invalid_line_skipped(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/create', data={
                'customer_id': '5',
                'line_count': '1',
                'lines[0][product_id]': 'bad',
                'lines[0][quantity]': '1',
            })
        assert resp.status_code == 302

    def test_create_post_currency_fallback(self, sales_client):
        with _sales_patches(), patch('utils.currency_utils.resolve_default_currency', side_effect=RuntimeError('fail')):
            resp = sales_client.post('/sales/create', data={
                'customer_id': '5',
                'line_count': '1',
                'lines[0][product_id]': '10',
                'lines[0][quantity]': '1',
                'warehouse_id': '1',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_post_exchange_audit_note(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/create', data={
                'customer_id': '5',
                'line_count': '1',
                'lines[0][product_id]': '10',
                'lines[0][quantity]': '1',
                'warehouse_id': '1',
                'exchange_rate_manual': 'true',
                'exchange_rate_server': '3.67',
                'exchange_rate': '3.5',
                'coupon_code': 'SAVE10',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_post_value_error(self, sales_client):
        with _sales_patches(), patch('routes.sales.SaleService.create_sale', side_effect=ValueError('stock')):
            resp = sales_client.post('/sales/create', data={
                'customer_id': '5',
                'line_count': '1',
                'lines[0][product_id]': '10',
                'lines[0][quantity]': '1',
                'warehouse_id': '1',
            })
        assert resp.status_code == 200

    def test_create_post_generic_error(self, sales_client):
        with _sales_patches(), patch('routes.sales.SaleService.create_sale', side_effect=RuntimeError('db')):
            resp = sales_client.post('/sales/create', data={
                'customer_id': '5',
                'line_count': '1',
                'lines[0][product_id]': '10',
                'lines[0][quantity]': '1',
                'warehouse_id': '1',
            })
        assert resp.status_code == 200


class TestSalesView:
    def test_view_success(self, sales_client):
        with _sales_patches():
            resp = sales_client.get('/sales/1')
        assert resp.status_code == 200

    def test_view_branch_forbidden(self, sales_client):
        with _sales_patches(branch_scope=9):
            resp = sales_client.get('/sales/1')
        assert resp.status_code == 403

    def test_view_seller_other_sale(self, sales_client, bypass_permission_auth):
        bypass_permission_auth.is_seller.return_value = True
        bypass_permission_auth.id = 99
        with _sales_patches(sale=_mock_sale(seller_id=1)):
            resp = sales_client.get('/sales/1', follow_redirects=False)
        assert resp.status_code == 302


class TestSalesPrint:
    def test_print_success(self, sales_client):
        with _sales_patches():
            resp = sales_client.get('/sales/1/print')
        assert resp.status_code == 200

    def test_print_template_fallback(self, sales_client):
        with _sales_patches(), patch('routes.sales.render_template', side_effect=[Exception('missing'), 'ok']):
            resp = sales_client.get('/sales/1/print')
        assert resp.status_code == 200

    def test_print_with_qr(self, sales_client):
        settings = MagicMock(enable_qr_code=True, active_template='modern', company_name_ar='Co')
        with _sales_patches(), patch('routes.sales.InvoiceSettings.get_active', return_value=settings):
            resp = sales_client.get('/sales/1/print')
        assert resp.status_code == 200


class TestSalesEdit:
    def test_edit_get(self, sales_client):
        with _sales_patches():
            resp = sales_client.get('/sales/1/edit')
        assert resp.status_code == 200

    def test_edit_paid_blocked(self, sales_client):
        with _sales_patches(sale=_mock_sale(payment_status='paid')):
            resp = sales_client.get('/sales/1/edit', follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_cancelled_blocked(self, sales_client):
        with _sales_patches(sale=_mock_sale(status='cancelled')):
            resp = sales_client.get('/sales/1/edit', follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_notes_only_when_gl(self, sales_client):
        with _sales_patches(has_gl=True):
            resp = sales_client.post('/sales/1/edit', data={'notes': 'updated'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_discount_update(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/1/edit', data={'notes': 'n', 'discount_amount': '10'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_negative_discount_clamped(self, sales_client):
        sale = _mock_sale()
        with _sales_patches(sale=sale):
            sales_client.post('/sales/1/edit', data={'discount_amount': '-5'})
        assert sale.discount_amount == 0

    def test_edit_error_rollback(self, sales_client):
        sale = _mock_sale()
        sale.calculate_totals.side_effect = RuntimeError('calc')
        with _sales_patches(sale=sale):
            resp = sales_client.post('/sales/1/edit', data={'discount_amount': '5'})
        assert resp.status_code == 200


class TestSalesCancel:
    def test_cancel_seller_denied(self, sales_client, bypass_permission_auth):
        bypass_permission_auth.is_seller.return_value = True
        with _sales_patches():
            resp = sales_client.post('/sales/1/cancel', follow_redirects=False)
        assert resp.status_code == 302

    def test_cancel_success(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/1/cancel')
        assert resp.status_code == 302

    def test_cancel_error(self, sales_client):
        with _sales_patches(), patch('routes.sales.SaleService.cancel_sale', side_effect=RuntimeError('x')):
            resp = sales_client.post('/sales/1/cancel')
        assert resp.status_code == 302


class TestSalesApiPrice:
    def test_api_get_price_missing(self, sales_client):
        with _sales_patches():
            resp = sales_client.get('/sales/api/get-price')
        assert resp.status_code == 400

    def test_api_get_price_success(self, sales_client):
        with _sales_patches():
            resp = sales_client.get('/sales/api/get-price?product_id=10&customer_id=5&warehouse_id=1')
        assert resp.status_code == 200
        assert resp.get_json()['price'] == 99.0

    def test_api_get_price_hides_cost(self, sales_client, bypass_permission_auth):
        bypass_permission_auth.can_see_costs.return_value = False
        with _sales_patches():
            resp = sales_client.get('/sales/api/get-price?product_id=10&customer_id=5')
        assert resp.get_json()['cost_price'] is None


class TestSalesArchived:
    def test_archived_list(self, sales_client):
        archived_rec = MagicMock()
        archived_rec.record_id = 1
        archived_rec.tenant_id = 1
        archived_rec.archived_at = datetime(2026, 6, 1)
        archived_rec.data = {
            'sale_number': 'S-1',
            'sale_date': '2026-06-01T00:00:00',
            'total_amount': '50',
            'currency': 'AED',
            'payment_status': 'paid',
        }
        with _sales_patches(archived=[archived_rec]):
            resp = sales_client.get('/sales/archived')
        assert resp.status_code == 200

    def test_archived_skips_missing_sale(self, sales_client):
        archived_rec = MagicMock()
        archived_rec.record_id = 99
        archived_rec.archived_at = datetime(2026, 6, 1)
        archived_rec.data = {'sale_number': 'S-99', 'sale_date': '2026-06-01', 'total_amount': 0}
        with _sales_patches(archived=[archived_rec]), patch('routes.sales.tenant_get', return_value=None):
            resp = sales_client.get('/sales/archived')
        assert resp.status_code == 200


class TestSalesDeleteArchive:
    def test_delete_non_owner(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/1/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_confirmed_blocked(self, sales_owner_client):
        with _sales_patches(sale=_mock_sale(status='confirmed')):
            resp = sales_owner_client.post('/sales/1/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_success(self, sales_owner_client):
        with _sales_patches(sale=_mock_sale(status='draft'), payment_count=1, cheque_count=1):
            resp = sales_owner_client.post('/sales/1/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_gl_warning_continues(self, sales_owner_client):
        with _sales_patches(sale=_mock_sale(status='draft')), patch('services.gl_service.GLService.reverse_entry', side_effect=RuntimeError('gl')):
            resp = sales_owner_client.post('/sales/1/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_error(self, sales_owner_client):
        mock_archive = MagicMock()
        mock_archive.archive_record.side_effect = RuntimeError('fail')
        with _sales_patches(), patch('services.archive_service.ArchiveService', return_value=mock_archive):
            resp = sales_owner_client.post('/sales/1/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_archive_confirmed_cancels_first(self, sales_client):
        with _sales_patches(sale=_mock_sale(status='confirmed')):
            resp = sales_client.post('/sales/1/archive')
        assert resp.status_code == 302

    def test_archive_error(self, sales_client):
        mock_archive = MagicMock()
        mock_archive.archive_record.side_effect = RuntimeError('fail')
        with _sales_patches(), patch('services.archive_service.ArchiveService', return_value=mock_archive):
            resp = sales_client.post('/sales/1/archive')
        assert resp.status_code == 302

    def test_archive_branch_forbidden(self, sales_client):
        with _sales_patches(branch_scope=9):
            resp = sales_client.post('/sales/1/archive')
        assert resp.status_code == 403

    def test_restore(self, sales_client):
        archived_rec = MagicMock()
        with _sales_patches(archived_record=archived_rec):
            resp = sales_client.post('/sales/1/restore', follow_redirects=False)
        assert resp.status_code == 302

    def test_restore_rollback(self, sales_client):
        archived_rec = MagicMock()
        with _sales_patches(archived_record=archived_rec), \
             patch('routes.sales.db.session.commit', side_effect=RuntimeError('db')):
            resp = sales_client.post('/sales/1/restore')
        assert resp.status_code == 302


class TestSalesCalculateTotals:
    def test_calculate_totals_ex_vat(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/api/calculate-totals', json={
                'lines': [{'quantity': 2, 'unit_price': 50, 'discount_percent': 10}],
                'discount_amount': 5,
                'shipping_cost': 10,
                'tax_rate': 5,
            })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['total'] > 0

    def test_calculate_totals_vat_inclusive(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/api/calculate-totals', json={
                'lines': [{'quantity': 1, 'unit_price': 105, 'discount_percent': 0}],
                'tax_rate': 5,
                'prices_include_vat': True,
            })
        assert resp.get_json()['success'] is True

    def test_calculate_zero_price_line(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/api/calculate-totals', json={
                'lines': [{'quantity': 3, 'unit_price': 0, 'discount_percent': 0}],
            })
        assert resp.get_json()['subtotal'] == 0

    def test_calculate_negative_qty_ignored(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/api/calculate-totals', json={
                'lines': [{'quantity': -2, 'unit_price': 10}],
            })
        assert resp.get_json()['line_count'] == 0

    def test_calculate_invalid_line_skipped(self, sales_client):
        with _sales_patches():
            resp = sales_client.post('/sales/api/calculate-totals', json={
                'lines': [{'quantity': 'bad', 'unit_price': 10}],
            })
        assert resp.get_json()['success'] is True

    def test_calculate_no_data(self, sales_client):
        with _sales_patches():
            resp = sales_client.post(
                '/sales/api/calculate-totals',
                data='',
                content_type='application/json',
            )
        assert resp.status_code in (400, 500)

    def test_calculate_server_error(self, sales_client):
        with _sales_patches(), patch('utils.tax_settings.normalize_tax_rate', side_effect=RuntimeError('boom')):
            resp = sales_client.post('/sales/api/calculate-totals', json={'lines': []})
        assert resp.status_code == 500
