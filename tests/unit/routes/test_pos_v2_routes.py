from __future__ import annotations

import json
from contextlib import ExitStack, contextmanager
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query, app_factory, bypass_permission_auth, unauthenticated_client


def _mock_product(pid=1):
    p = MagicMock()
    p.id = pid
    p.name = 'Item'
    p.name_ar = 'صنف'
    p.sku = 'SKU1'
    p.barcode = 'BC1'
    p.regular_price = Decimal('50')
    p.is_active = True
    p.current_stock = Decimal('5')
    p.unit = 'pcs'
    p.has_serial_number = False
    p.get_price_for_customer.return_value = 50.0
    return p


def _walkin_customer():
    c = MagicMock()
    c.id = 9
    c.name = 'Walk-in'
    c.customer_type = 'regular'
    return c


def _mock_session():
    s = MagicMock()
    s.id = 11
    s.session_number = 'POS-SES-1'
    s.opened_at = MagicMock(isoformat=MagicMock(return_value='2026-06-01T10:00:00'))
    s.closed_at = None
    s.duration_minutes = 5
    s.opening_balance_cash = Decimal('100')
    s.closing_balance_cash = None
    s.expected_balance = Decimal('150')
    s.difference = Decimal('0')
    s.total_sales = Decimal('0')
    s.total_cash_sales = Decimal('0')
    s.total_card_sales = Decimal('0')
    s.status = 'open'
    s.tenant_id = 1
    s.branch_id = 2
    s.user_id = 42
    s.notes = ''
    return s


@contextmanager
def _pos_enabled_patches(**kwargs):
    global_setting = kwargs.get('global_setting', MagicMock(enable_pos=True))
    tenant = kwargs.get('tenant', MagicMock(enable_pos=True))
    tenant_obj = tenant
    if not isinstance(tenant, MagicMock) or tenant.enable_pos is True:
        pass
    session_mock = MagicMock()
    session_mock.get.return_value = tenant_obj
    with ExitStack() as stack:
        ss = stack.enter_context(patch('routes.pos.SystemSettings.query'))
        ss.order_by.return_value.first.return_value = global_setting
        stack.enter_context(patch('routes.pos.get_active_tenant_id', return_value=1))
        stack.enter_context(patch('routes.pos.db.session', session_mock))
        stack.enter_context(patch('routes.pos.render_template', return_value='ok'))
        stack.enter_context(patch('routes.pos.LoggingCore.log_audit'))
        stack.enter_context(patch('extensions.limiter.limit', return_value=lambda f: f))
        yield


@contextmanager
def _pos_api_patches(**kwargs):
    with _pos_enabled_patches(**kwargs) as ctx:
        with ExitStack() as stack:
            stack.enter_context(patch('routes.pos.get_accessible_warehouses', return_value=kwargs.get('warehouses', [])))
            stack.enter_context(patch('routes.pos.tenant_get', side_effect=kwargs.get('tenant_get', lambda m, i: _mock_product(i))))
            stack.enter_context(patch('routes.pos.tenant_query', return_value=_chain_query(all=kwargs.get('customers', []))))
            stack.enter_context(patch('routes.pos.search_pos_products', return_value=kwargs.get('search_result', ([], {}, []))))
            stack.enter_context(patch('routes.pos.lookup_pos_product_exact', return_value=kwargs.get('lookup_result', (None, {}))))
            stack.enter_context(patch(
                'routes.pos.serialize_pos_product',
                side_effect=lambda p, sm, **kw: {'id': p.id, 'name': p.name, 'stock': 1, 'is_out_of_stock': False},
            ))
            stack.enter_context(patch('routes.pos.get_pos_walkin_customer', return_value=kwargs.get('walkin', _walkin_customer())))
            stack.enter_context(patch('routes.pos.get_active_session', return_value=kwargs.get('session', _mock_session())))
            stack.enter_context(patch('routes.pos.create_pos_session', return_value=kwargs.get('new_session', _mock_session())))
            stack.enter_context(patch('routes.pos.require_active_session', return_value=kwargs.get('session', _mock_session())))
            stack.enter_context(patch('routes.pos.close_pos_session', return_value=kwargs.get('session', _mock_session())))
            stack.enter_context(patch('routes.pos.merge_checkout_lines', return_value=kwargs.get('merged_lines', [{'product_id': 1, 'quantity': Decimal('1'), 'discount_percent': Decimal('0'), 'unit_price': None}])))
            stack.enter_context(patch('routes.pos.ensure_warehouse_access', return_value=MagicMock(id=3)))
            stack.enter_context(patch('routes.pos.context_aware_default_currency', return_value='AED'))
            stack.enter_context(patch('routes.pos.get_active_branch_id', return_value=kwargs.get('branch_id', 2)))
            stack.enter_context(patch('routes.pos.SaleService.create_sale', return_value=kwargs.get('sale', MagicMock(id=100, sale_number='S-100', tenant_id=1, total_amount=Decimal('50')))))
            stack.enter_context(patch('routes.pos.log_mutation'))
            yield ctx


@pytest.fixture
def pos_client(app_factory, bypass_permission_auth):
    from routes.pos import pos_bp
    app = app_factory(pos_bp)
    return app.test_client()


class TestPosAuth:
    def test_index_requires_login(self, pos_client):
        with _pos_enabled_patches(), unauthenticated_client(pos_client):
            resp = pos_client.get('/pos/')
        assert resp.status_code == 401


class TestPosDisabled:
    def test_system_disabled_json(self, pos_client):
        with _pos_enabled_patches(global_setting=MagicMock(enable_pos=False)):
            resp = pos_client.get('/pos/api/products')
        assert resp.status_code == 403

    def test_tenant_disabled_blocks_api(self, pos_client):
        tenant = MagicMock()
        tenant.enable_pos = False
        with _pos_enabled_patches(tenant=tenant):
            resp = pos_client.get('/pos/api/products')
        assert resp.status_code == 403

    def test_system_disabled_html(self, pos_client):
        with _pos_enabled_patches(global_setting=MagicMock(enable_pos=False)):
            resp = pos_client.get('/pos/')
        assert resp.status_code == 403

    def test_tenant_disabled_html(self, pos_client):
        tenant = MagicMock()
        tenant.enable_pos = False
        with _pos_enabled_patches(tenant=tenant):
            resp = pos_client.get('/pos/grid')
        assert resp.status_code == 403


class TestPosPages:
    def test_index(self, pos_client):
        wh = MagicMock(is_active=True, warehouse_type='store', TYPE_ONLINE='online')
        with _pos_api_patches(warehouses=[wh]), \
             patch('routes.pos.Tenant.get_current', return_value=MagicMock()), \
             patch('utils.currency_utils.resolve_default_currency', return_value='AED'), \
             patch('utils.tax_settings.get_prices_include_vat', return_value=True):
            resp = pos_client.get('/pos/')
        assert resp.status_code == 200

    def test_grid(self, pos_client):
        wh = MagicMock(is_active=True, warehouse_type='store', TYPE_ONLINE='online')
        with _pos_api_patches(warehouses=[wh]), \
             patch('routes.pos.Tenant.get_current', return_value=MagicMock()), \
             patch('utils.currency_utils.resolve_default_currency', return_value='AED'), \
             patch('utils.tax_settings.get_prices_include_vat', return_value=False):
            resp = pos_client.get('/pos/grid')
        assert resp.status_code == 200


class TestPosCatalogApi:
    def test_categories(self, pos_client):
        cat = MagicMock()
        cat.id = 1
        cat.name = 'Food'
        cat.name_ar = 'طعام'
        cq = _chain_query(all=[cat])
        cq.filter_by.return_value.order_by.return_value.all.return_value = [cat]
        with _pos_api_patches(), patch('routes.pos.tenant_query', return_value=cq):
            resp = pos_client.get('/pos/api/categories')
        assert resp.status_code == 200
        assert resp.get_json()[0]['name'] == 'Food'

    def test_products(self, pos_client):
        product = _mock_product()
        with _pos_api_patches(search_result=([product], {1: 5}, [1])):
            resp = pos_client.get('/pos/api/products?q=item')
        assert resp.status_code == 200

    def test_product_lookup_missing_code(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.get('/pos/api/product')
        assert resp.status_code == 400

    def test_product_lookup_not_found(self, pos_client):
        with _pos_api_patches(lookup_result=(None, {})):
            resp = pos_client.get('/pos/api/product?code=MISSING')
        assert resp.status_code == 404

    def test_product_lookup_success(self, pos_client):
        product = _mock_product()
        with _pos_api_patches(lookup_result=(product, {1: 2})):
            resp = pos_client.get('/pos/api/product?barcode=BC1')
        data = resp.get_json()
        assert data['success'] is True

    def test_product_lookup_inactive_warning(self, pos_client):
        product = _mock_product()
        product.is_active = False
        with _pos_api_patches(lookup_result=(product, {1: 0})):
            resp = pos_client.get('/pos/api/product?code=BC1')
        assert 'warning' in resp.get_json()

    def test_product_lookup_out_of_stock_warning(self, pos_client):
        product = _mock_product()
        with _pos_api_patches(lookup_result=(product, {1: 0})), \
             patch('routes.pos.serialize_pos_product', return_value={'is_out_of_stock': True, 'name': 'Item'}):
            resp = pos_client.get('/pos/api/product?code=BC1')
        assert resp.get_json().get('warning') == 'لا يوجد مخزون في المستودع المحدد.'

    def test_customers(self, pos_client):
        customer = MagicMock()
        customer.id = 2
        customer.name = 'Ali'
        customer.name_ar = 'علي'
        customer.phone = '050'
        customer.customer_type = 'regular'
        cq = MagicMock()
        cq.filter_by.return_value = cq
        cq.filter.return_value = cq
        cq.order_by.return_value.limit.return_value.all.return_value = [customer]
        with _pos_api_patches(), patch('routes.pos.tenant_query', return_value=cq):
            resp = pos_client.get('/pos/api/customers?q=ali')
        assert resp.status_code == 200
        assert resp.get_json()[0]['text'].startswith('Ali')


class TestPosWalkin:
    def test_walkin_success(self, pos_client):
        with _pos_api_patches(walkin=_walkin_customer()):
            resp = pos_client.get('/pos/api/walkin-customer')
        assert resp.get_json()['success'] is True

    def test_walkin_failure(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.get_pos_walkin_customer', side_effect=RuntimeError('db')):
            resp = pos_client.get('/pos/api/walkin-customer')
        assert resp.status_code == 400


class TestPosCheckout:
    def _checkout_payload(self, **extra):
        base = {
            'quick_customer': True,
            'lines': [{'product_id': 1, 'quantity': 1}],
            'payment_method': 'cash',
            'paid_amount': 50,
        }
        base.update(extra)
        return base

    def test_checkout_requires_json(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post('/pos/api/checkout', data='not-json')
        assert resp.status_code == 415

    def test_checkout_requires_session(self, pos_client):
        with _pos_api_patches(session=None):
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload())
        assert resp.status_code == 403

    def test_checkout_empty_lines(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post('/pos/api/checkout', json={'lines': []})
        assert resp.status_code == 400

    def test_checkout_invalid_lines(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.merge_checkout_lines', side_effect=ValueError('bad')):
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload())
        assert resp.status_code == 400

    def test_checkout_invalid_product(self, pos_client):
        with _pos_api_patches(tenant_get=lambda m, i: None):
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload(customer_id=None, quick_customer=False))
        assert resp.status_code == 400

    def test_checkout_success(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload())
        data = resp.get_json()
        assert data['success'] is True
        assert data['sale_number'] == 'S-100'

    def test_checkout_serial_validation(self, pos_client):
        product = _mock_product()
        product.has_serial_number = True
        with _pos_api_patches(tenant_get=lambda m, i: product), \
             patch('routes.pos.merge_checkout_lines', return_value=[{'product_id': 1, 'quantity': Decimal('2'), 'discount_percent': Decimal('0'), 'unit_price': None, 'serials': ['A']}]):
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload())
        assert resp.status_code == 400

    def test_checkout_price_override_forbidden(self, pos_client, bypass_permission_auth):
        product = _mock_product()
        bypass_permission_auth.has_permission.return_value = False
        bypass_permission_auth.is_owner = False
        merged = [{'product_id': 1, 'quantity': Decimal('1'), 'discount_percent': Decimal('0'), 'unit_price': Decimal('99')}]
        with _pos_api_patches(tenant_get=lambda m, i: product), \
             patch('routes.pos.merge_checkout_lines', return_value=merged):
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload())
        assert resp.status_code == 403

    def test_checkout_kds_order(self, pos_client):
        product = _mock_product()
        with _pos_api_patches(tenant_get=lambda m, i: product), \
             patch('routes.pos._notify_kds') as notify, \
             patch('models.PosKdsOrder', return_value=MagicMock(id=7, order_number='S-100')):
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload(order_type='dine_in'))
        assert resp.get_json()['success'] is True
        notify.assert_called_once()

    def test_checkout_sale_service_error(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.SaleService.create_sale', side_effect=ValueError('stock')):
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload())
        assert resp.status_code == 400

    def test_checkout_server_error(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.SaleService.create_sale', side_effect=RuntimeError('db')):
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload())
        assert resp.status_code == 500

    def test_checkout_invalid_warehouse(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.ensure_warehouse_access', side_effect=ValueError('bad')):
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload(warehouse_id=99))
        assert resp.status_code == 400

    def test_checkout_missing_payment_method(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload(paid_amount=50, payment_method=''))
        assert resp.status_code == 400

    def test_checkout_inactive_customer(self, pos_client):
        customer = _walkin_customer()
        customer.is_active = False
        with _pos_api_patches(), patch('routes.pos.get_pos_walkin_customer', return_value=customer), \
             patch('routes.pos.tenant_get', return_value=customer):
            resp = pos_client.post('/pos/api/checkout', json={
                'customer_id': 9,
                'lines': [{'product_id': 1, 'quantity': 1}],
            })
        assert resp.status_code == 400

    def test_checkout_walkin_value_error(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.get_pos_walkin_customer', side_effect=ValueError('no tenant')):
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload())
        assert resp.status_code == 400

    def test_checkout_with_customer_and_warehouse(self, pos_client):
        from models import Customer, Product
        customer = _walkin_customer()
        customer.is_active = True
        product = _mock_product()

        def tenant_get_side(model, pk):
            if model is Customer:
                return customer
            if model is Product:
                return product
            return None

        with _pos_api_patches(tenant_get=tenant_get_side):
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload(
                quick_customer=False,
                customer_id=9,
                warehouse_id=3,
            ))
        assert resp.get_json()['success'] is True

    def test_checkout_serial_success(self, pos_client):
        product = _mock_product()
        product.has_serial_number = True
        merged = [{
            'product_id': 1,
            'quantity': Decimal('2'),
            'discount_percent': Decimal('0'),
            'unit_price': None,
            'serials': ['SN1', 'SN2'],
        }]
        with _pos_api_patches(tenant_get=lambda m, i: product), \
             patch('routes.pos.merge_checkout_lines', return_value=merged):
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload())
        assert resp.get_json()['success'] is True

    def test_checkout_price_override_allowed(self, pos_client, bypass_permission_auth):
        product = _mock_product()
        bypass_permission_auth.has_permission.return_value = True
        merged = [{'product_id': 1, 'quantity': Decimal('1'), 'discount_percent': Decimal('0'), 'unit_price': Decimal('99')}]
        with _pos_api_patches(tenant_get=lambda m, i: product), \
             patch('routes.pos.merge_checkout_lines', return_value=merged), \
             patch('routes.pos.LoggingCore.log_audit') as audit:
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload())
        assert resp.get_json()['success'] is True
        audit.assert_called_once()

    def test_checkout_invalid_paid_amount_defaults_zero(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload(paid_amount='not-a-number'))
        assert resp.get_json()['success'] is True

    def test_checkout_qa_marker_notes(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.SaleService.create_sale') as create_sale:
            create_sale.return_value = MagicMock(id=100, sale_number='S-100', tenant_id=1, total_amount=Decimal('50'))
            resp = pos_client.post('/pos/api/checkout', json=self._checkout_payload(qa_marker=True, notes='test'))
        assert resp.get_json()['success'] is True
        assert create_sale.call_args.kwargs['notes'].startswith('[POS-QA]')


class TestPosSessionApi:
    def test_session_current_none(self, pos_client):
        with _pos_api_patches(session=None):
            resp = pos_client.get('/pos/api/session/current')
        assert resp.get_json()['session'] is None

    def test_session_current_open(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.get('/pos/api/session/current')
        assert resp.get_json()['success'] is True

    def test_session_open_conflict(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post('/pos/api/session/open', json={'opening_balance': 50})
        assert resp.status_code == 409

    def test_session_open_success(self, pos_client):
        with _pos_api_patches(session=None, new_session=_mock_session()):
            resp = pos_client.post('/pos/api/session/open', json={'opening_balance': 50})
        assert resp.status_code == 201

    def test_session_open_no_branch(self, pos_client):
        with _pos_api_patches(session=None, branch_id=None):
            resp = pos_client.post('/pos/api/session/open', json={'opening_balance': 0})
        assert resp.status_code == 400

    def test_session_close_success(self, pos_client):
        closed = _mock_session()
        closed.closed_at = MagicMock(isoformat=MagicMock(return_value='2026-06-01T12:00:00'))
        with _pos_api_patches(session=closed):
            resp = pos_client.post('/pos/api/session/close', json={'closing_balance': 120})
        assert resp.get_json()['success'] is True

    def test_session_close_requires_json(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post('/pos/api/session/close', data='not-json')
        assert resp.status_code == 415

    def test_session_close_missing(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.require_active_session', side_effect=ValueError('no session')):
            resp = pos_client.post('/pos/api/session/close', json={'closing_balance': 0})
        assert resp.status_code == 404

    def test_session_open_requires_json(self, pos_client):
        with _pos_api_patches(session=None):
            resp = pos_client.post('/pos/api/session/open', data='not-json')
        assert resp.status_code == 415

    def test_session_open_error(self, pos_client):
        with _pos_api_patches(session=None), patch('routes.pos.create_pos_session', side_effect=RuntimeError('fail')):
            resp = pos_client.post('/pos/api/session/open', json={'opening_balance': 0})
        assert resp.status_code == 400

    def test_session_close_error(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.close_pos_session', side_effect=RuntimeError('fail')):
            resp = pos_client.post('/pos/api/session/close', json={'closing_balance': 0})
        assert resp.status_code == 400

    def test_session_report_missing(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.tenant_get', return_value=None):
            resp = pos_client.get('/pos/api/session/report?session_id=999')
        assert resp.status_code == 404

    def test_session_report_by_id(self, pos_client):
        session = _mock_session()
        with _pos_api_patches(), patch('routes.pos.tenant_get', return_value=session):
            resp = pos_client.get('/pos/api/session/report?session_id=11')
        assert resp.get_json()['success'] is True

    def test_session_report_no_active_session(self, pos_client):
        with _pos_api_patches(session=None):
            resp = pos_client.get('/pos/api/session/report')
        data = resp.get_json()
        assert data['session'] is None
        assert resp.status_code == 200


class TestPosHardware:
    def test_print_receipt_success(self, pos_client):
        response = MagicMock()
        response.read.return_value = json.dumps({'ok': True}).encode()
        response.status = 200
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)
        with _pos_api_patches(), patch('routes.pos.urllib.request.urlopen', return_value=response):
            resp = pos_client.post('/pos/api/hardware/print-receipt', json={'lines': []})
        assert resp.status_code == 200

    def test_print_receipt_agent_down(self, pos_client):
        import urllib.error
        with _pos_api_patches(), patch('routes.pos.urllib.request.urlopen', side_effect=urllib.error.URLError('down')):
            resp = pos_client.post('/pos/api/hardware/print-receipt', json={})
        assert resp.status_code == 503

    def test_open_drawer_success(self, pos_client):
        response = MagicMock()
        response.read.return_value = json.dumps({'opened': True}).encode()
        response.status = 200
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)
        with _pos_api_patches(), patch('routes.pos.urllib.request.urlopen', return_value=response):
            resp = pos_client.post('/pos/api/hardware/open-drawer', json={})
        assert resp.status_code == 200

    def test_open_drawer_generic_error(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.urllib.request.urlopen', side_effect=RuntimeError('boom')):
            resp = pos_client.post('/pos/api/hardware/open-drawer', json={})
        assert resp.status_code == 500

    def test_open_drawer_agent_down(self, pos_client):
        import urllib.error
        with _pos_api_patches(), patch('routes.pos.urllib.request.urlopen', side_effect=urllib.error.URLError('down')):
            resp = pos_client.post('/pos/api/hardware/open-drawer', json={})
        assert resp.status_code == 503

    def test_hardware_status_connected(self, pos_client):
        response = MagicMock()
        response.read.return_value = json.dumps({'status': 'ok'}).encode()
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)
        with _pos_api_patches(), patch('routes.pos.urllib.request.urlopen', return_value=response):
            resp = pos_client.get('/pos/api/hardware/status')
        assert resp.get_json()['status'] == 'ok'

    def test_hardware_status_agent_down(self, pos_client):
        import urllib.error
        with _pos_api_patches(), patch('routes.pos.urllib.request.urlopen', side_effect=urllib.error.URLError('down')):
            resp = pos_client.get('/pos/api/hardware/status')
        data = resp.get_json()
        assert data['status'] == 'disconnected'

    def test_hardware_status_generic_error(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.urllib.request.urlopen', side_effect=RuntimeError('boom')):
            resp = pos_client.get('/pos/api/hardware/status')
        data = resp.get_json()
        assert data['status'] == 'error'


class TestPosKds:
    def test_kds_dashboard(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.get('/pos/kds')
        assert resp.status_code == 200

    def test_kds_orders(self, pos_client):
        order = MagicMock(id=1, order_number='K1', status='pending', created_at=MagicMock(isoformat=lambda: '2026-06-01'), items_json='[]')
        chain = MagicMock()
        chain.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [order]
        with _pos_api_patches(), patch('models.PosKdsOrder.query', chain):
            resp = pos_client.get('/pos/api/kds/orders')
        assert resp.status_code == 200

    def test_kds_update_status(self, pos_client):
        order = MagicMock(id=1)
        with _pos_api_patches(), patch('models.PosKdsOrder.query') as q, patch('routes.pos._notify_kds'):
            q.filter_by.return_value.first.return_value = order
            resp = pos_client.post('/pos/api/kds/orders/1/status', json={'status': 'ready'})
        assert resp.get_json()['success'] is True

    def test_kds_update_status_served_sets_completed_at(self, pos_client):
        order = MagicMock(id=1)
        with _pos_api_patches(), patch('models.PosKdsOrder.query') as q, patch('routes.pos._notify_kds'):
            q.filter_by.return_value.first.return_value = order
            resp = pos_client.post('/pos/api/kds/orders/1/status', json={'status': 'served'})
        assert resp.get_json()['success'] is True
        assert order.completed_at is not None

    def test_notify_kds_delivers_to_subscriber(self):
        import queue
        from routes import pos as pos_module
        q = queue.Queue()
        pos_module._KDS_SUBSCRIBERS.append((1, q))
        try:
            pos_module._notify_kds({'type': 'ping', 'tenant_id': 1}, tenant_id=1)
            msg = q.get_nowait()
            assert 'ping' in msg
        finally:
            pos_module._KDS_SUBSCRIBERS[:] = [
                entry for entry in pos_module._KDS_SUBSCRIBERS if entry[1] is not q
            ]

    def test_notify_kds_skips_other_tenant_subscribers(self):
        import queue
        from routes import pos as pos_module
        tenant_a = queue.Queue()
        tenant_b = queue.Queue()
        pos_module._KDS_SUBSCRIBERS.extend([(1, tenant_a), (2, tenant_b)])
        try:
            pos_module._notify_kds({'type': 'ping', 'tenant_id': 1}, tenant_id=1)
            assert not tenant_b.qsize()
            assert tenant_a.get_nowait()
        finally:
            pos_module._KDS_SUBSCRIBERS.clear()

    def test_notify_kds_removes_failed_subscriber(self):
        from routes import pos as pos_module
        bad_q = MagicMock()
        bad_q.put_nowait.side_effect = Exception('queue full')
        pos_module._KDS_SUBSCRIBERS.append((1, bad_q))
        try:
            pos_module._notify_kds({'type': 'ping', 'tenant_id': 1}, tenant_id=1)
            assert (1, bad_q) not in pos_module._KDS_SUBSCRIBERS
        finally:
            pos_module._KDS_SUBSCRIBERS[:] = [
                entry for entry in pos_module._KDS_SUBSCRIBERS if entry[1] is not bad_q
            ]

    def test_kds_stream_subscribe_and_cleanup(self, pos_client, bypass_permission_auth):
        import queue
        from routes.pos import _KDS_SUBSCRIBERS, kds_stream
        real_q = queue.Queue()
        with _pos_api_patches(), patch('routes.pos._queue.Queue', return_value=real_q):
            with pos_client.application.test_request_context():
                with patch('flask_login.utils._get_user', return_value=bypass_permission_auth):
                    gen, headers = kds_stream()
                real_q.put('event-data')
                assert next(gen) == 'event-data'
                gen.close()
        assert headers['Content-Type'] == 'text/event-stream'
        assert not any(entry[1] is real_q for entry in _KDS_SUBSCRIBERS)

    def test_print_receipt_generic_error(self, pos_client):
        with _pos_api_patches(), patch('routes.pos.urllib.request.urlopen', side_effect=RuntimeError('boom')):
            resp = pos_client.post('/pos/api/hardware/print-receipt', json={})
        assert resp.status_code == 500

    def test_kds_update_not_found(self, pos_client):
        with _pos_api_patches(), patch('models.PosKdsOrder.query') as q:
            q.filter_by.return_value.first.return_value = None
            resp = pos_client.post('/pos/api/kds/orders/9/status', json={'status': 'ready'})
        assert resp.status_code == 404

    def test_kds_update_invalid_status(self, pos_client):
        order = MagicMock(id=1)
        with _pos_api_patches(), patch('models.PosKdsOrder.query') as q:
            q.filter_by.return_value.first.return_value = order
            resp = pos_client.post('/pos/api/kds/orders/1/status', json={'status': 'bogus'})
        assert resp.status_code == 400

    def test_floor_create_missing_name(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post('/pos/api/floors/create', json={'name': ''})
        assert resp.status_code == 400


class TestPosFloors:
    def test_floors_list(self, pos_client):
        floor = MagicMock(id=1, name='Main', name_ar='رئيسي', sort_order=1)
        floor.tables.filter_by.return_value.count.return_value = 4
        chain = MagicMock()
        chain.filter_by.return_value.order_by.return_value.all.return_value = [floor]
        with _pos_api_patches(), patch('models.PosFloor.query', chain):
            resp = pos_client.get('/pos/api/floors')
        assert resp.status_code == 200

    def test_floor_create(self, pos_client):
        floor = MagicMock(id=2)
        with _pos_api_patches(), patch('models.PosFloor', return_value=floor):
            resp = pos_client.post('/pos/api/floors/create', json={'name': 'Upstairs'})
        assert resp.get_json()['success'] is True

    def test_floor_tables(self, pos_client):
        floor = MagicMock(id=1)
        table = MagicMock(id=3, label='T1', capacity=4, pos_x=0, pos_y=0, shape='rectangle', status='free')
        with _pos_api_patches(), patch('models.PosFloor.query') as fq, patch('models.PosTable.query') as tq:
            fq.filter_by.return_value.first.return_value = floor
            tq.filter_by.return_value.order_by.return_value.all.return_value = [table]
            resp = pos_client.get('/pos/api/floors/1/tables')
        assert resp.status_code == 200

    def test_floor_tables_not_found(self, pos_client):
        with _pos_api_patches(), patch('models.PosFloor.query') as fq:
            fq.filter_by.return_value.first.return_value = None
            resp = pos_client.get('/pos/api/floors/99/tables')
        assert resp.status_code == 404

    def test_table_create(self, pos_client):
        floor = MagicMock(id=1)
        table = MagicMock(id=4)
        with _pos_api_patches(), patch('models.PosFloor.query') as fq, patch('models.PosTable', return_value=table):
            fq.filter_by.return_value.first.return_value = floor
            resp = pos_client.post('/pos/api/tables/create', json={'floor_id': 1, 'label': 'T2'})
        assert resp.get_json()['success'] is True

    def test_table_create_missing_fields(self, pos_client):
        with _pos_api_patches():
            resp = pos_client.post('/pos/api/tables/create', json={'floor_id': 1})
        assert resp.status_code == 400

    def test_table_create_floor_not_found(self, pos_client):
        with _pos_api_patches(), patch('models.PosFloor.query') as fq:
            fq.filter_by.return_value.first.return_value = None
            resp = pos_client.post('/pos/api/tables/create', json={'floor_id': 99, 'label': 'T9'})
        assert resp.status_code == 404

    def test_table_status_update(self, pos_client):
        table = MagicMock(id=5)
        with _pos_api_patches(), patch('models.PosTable.query') as tq:
            tq.filter_by.return_value.first.return_value = table
            resp = pos_client.post('/pos/api/tables/5/status', json={'status': 'occupied'})
        assert resp.get_json()['success'] is True

    def test_table_status_not_found(self, pos_client):
        with _pos_api_patches(), patch('models.PosTable.query') as tq:
            tq.filter_by.return_value.first.return_value = None
            resp = pos_client.post('/pos/api/tables/5/status', json={'status': 'free'})
        assert resp.status_code == 404

    def test_table_status_invalid(self, pos_client):
        table = MagicMock(id=5)
        with _pos_api_patches(), patch('models.PosTable.query') as tq:
            tq.filter_by.return_value.first.return_value = table
            resp = pos_client.post('/pos/api/tables/5/status', json={'status': 'bogus'})
        assert resp.status_code == 400

    def test_table_assign(self, pos_client):
        table = MagicMock(id=6)
        with _pos_api_patches(), patch('models.PosTable.query') as tq, patch('models.PosTableOrder', return_value=MagicMock()):
            tq.filter_by.return_value.first.return_value = table
            resp = pos_client.post('/pos/api/tables/6/assign', json={'sale_id': 100})
        assert resp.get_json()['success'] is True

    def test_table_assign_not_found(self, pos_client):
        with _pos_api_patches(), patch('models.PosTable.query') as tq:
            tq.filter_by.return_value.first.return_value = None
            resp = pos_client.post('/pos/api/tables/6/assign', json={'sale_id': 100})
        assert resp.status_code == 404

    def test_table_assign_missing_sale_id(self, pos_client):
        table = MagicMock(id=6)
        with _pos_api_patches(), patch('models.PosTable.query') as tq:
            tq.filter_by.return_value.first.return_value = table
            resp = pos_client.post('/pos/api/tables/6/assign', json={})
        assert resp.status_code == 400


class TestPosCustomerDisplay:
    def _tenant_request(self, tenant_id=1):
        req = MagicMock()
        req.args.get = lambda key, type=int, default=None: tenant_id if key == 'tenant_id' else default
        return patch('routes.pos.request', req)

    def test_customer_display_page(self, pos_client):
        with _pos_enabled_patches():
            resp = pos_client.get('/pos/customer-display')
        assert resp.status_code == 200

    def test_customer_display_stream_missing_tenant(self):
        from routes.pos import customer_display_stream
        req = MagicMock()
        req.args.get = lambda key, type=int, default=None: None
        with patch('routes.pos.request', req):
            gen, headers = customer_display_stream(1)
        assert headers['Content-Type'] == 'text/event-stream'
        assert '"closed"' in next(gen)
        with pytest.raises(StopIteration):
            next(gen)

    def test_customer_display_stream_closed(self):
        from routes.pos import customer_display_stream
        with self._tenant_request(1), patch('routes.pos.db.session') as sess:
            sess.get.return_value = None
            gen, headers = customer_display_stream(999)
        assert headers['Content-Type'] == 'text/event-stream'
        msg = next(gen)
        assert '"closed"' in msg
        with pytest.raises(StopIteration):
            next(gen)

    def test_customer_display_stream_tenant_mismatch(self):
        from routes.pos import customer_display_stream
        session = MagicMock(tenant_id=2)
        with self._tenant_request(1), patch('routes.pos.db.session') as sess:
            sess.get.return_value = session
            gen, headers = customer_display_stream(1)
        assert headers['Content-Type'] == 'text/event-stream'
        assert '"closed"' in next(gen)

    def test_customer_display_stream_waiting(self):
        from routes.pos import customer_display_stream
        session = MagicMock(tenant_id=1)
        calls = {'get': 0}

        def get_session(model, sid):
            calls['get'] += 1
            return session if calls['get'] == 1 else None

        with self._tenant_request(1), patch('routes.pos.db.session') as sess, \
             patch('models.Sale.query') as sale_q, \
             patch('time.sleep') as sleep:
            sess.get.side_effect = get_session
            sale_q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            gen, _ = customer_display_stream(1)
            msg = next(gen)
            assert '"waiting"' in msg
            msg2 = next(gen)
            assert '"closed"' in msg2
            sleep.assert_called()

    def test_customer_display_stream_order_update(self):
        from routes.pos import customer_display_stream
        session = MagicMock(tenant_id=1)
        line = MagicMock()
        line.product.name_ar = 'صنف'
        line.product.name = 'Item'
        line.quantity = Decimal('2')
        line.line_total = Decimal('50')
        sale = MagicMock(id=100, sale_number='S-100', total_amount=Decimal('50'), lines=[line])
        with self._tenant_request(1), patch('routes.pos.db.session') as sess, \
             patch('models.Sale.query') as sale_q, \
             patch('models.PosKdsOrder.query') as kds_q, \
             patch('time.sleep'):
            sess.get.return_value = session
            sale_q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [sale]
            kds_q.filter_by.return_value.first.return_value = None
            gen, _ = customer_display_stream(1)
            msg = next(gen)
        data = json.loads(msg.split('data: ', 1)[1])
        assert data['type'] == 'order_update'
        assert data['status'] == 'confirmed'

    def test_customer_display_stream_same_status_polls(self):
        from routes.pos import customer_display_stream
        session = MagicMock(tenant_id=1)
        line = MagicMock()
        line.product.name_ar = None
        line.product.name = 'Item'
        line.quantity = Decimal('1')
        line.line_total = Decimal('10')
        sale = MagicMock(id=100, sale_number='S-100', total_amount=Decimal('10'), lines=[line])
        kds_order = MagicMock(status='preparing')
        calls = {'get': 0}

        def get_session(model, sid):
            calls['get'] += 1
            return session if calls['get'] <= 2 else None

        with self._tenant_request(1), patch('routes.pos.db.session') as sess, \
             patch('models.Sale.query') as sale_q, \
             patch('models.PosKdsOrder.query') as kds_q, \
             patch('time.sleep') as sleep:
            sess.get.side_effect = get_session
            sale_q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [sale]
            kds_q.filter_by.return_value.first.return_value = kds_order
            gen, _ = customer_display_stream(1)
            first = json.loads(next(gen).split('data: ', 1)[1])
            assert first['status'] == 'preparing'
            second = json.loads(next(gen).split('data: ', 1)[1])
            assert second['type'] == 'closed'
            sleep.assert_called()
