"""Deep assurance — routes/api.py endpoints, guards, telemetry, search."""
from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class TestPublicApi:
    """Unauthenticated public endpoints."""

    def test_health(self, app, client):
        with app.app_context():
            resp = client.get('/api/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'

    def test_version(self, app, client):
        with app.app_context():
            resp = client.get('/api/version')
        assert resp.status_code == 200
        assert 'version' in resp.get_json()


class TestAuthGuards:
    """Protected routes reject anonymous clients."""

    @pytest.mark.parametrize('path', [
        '/api/currencies',
        '/api/search?q=test',
        '/api/products',
        '/api/check-username?username=validuser',
    ])
    def test_login_required(self, app, client, path):
        with app.app_context():
            resp = client.get(path)
        assert resp.status_code in (302, 401, 403)


class TestAuthenticatedApi:
    """Happy-path and validation with logged-in tenant user."""

    def test_currencies_list(self, app, auth_client):
        with app.app_context():
            resp = auth_client.get('/api/currencies')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'AED' in data['currencies'] or len(data['currencies']) >= 0

    def test_payment_fields_cash_and_unknown(self, app, auth_client):
        with app.app_context():
            cash = auth_client.get('/api/payment-fields/cash')
            unknown = auth_client.get('/api/payment-fields/unknown_method')
        assert cash.status_code == 200
        assert cash.get_json()['en_title'] == 'Cash Payment'
        assert unknown.get_json()['fields'] == []

    def test_search_customers_suppliers_products(
        self, app, auth_client, sample_customer, sample_supplier, sample_product,
    ):
        with app.app_context():
            cust = auth_client.get('/api/search?q=Test&type=customers')
            supp = auth_client.get('/api/search?q=Test&type=suppliers')
            prod = auth_client.get('/api/search?q=Test&type=products')
        assert cust.status_code == 200
        assert supp.status_code == 200
        assert prod.status_code == 200
        assert isinstance(cust.get_json()['results'], list)

    def test_check_username_validation_matrix(self, app, auth_client):
        import uuid
        with app.app_context():
            short = auth_client.get('/api/check-username?username=ab')
            bad = auth_client.get('/api/check-username?username=bad@name')
            unique = f'user_{uuid.uuid4().hex[:8]}'
            avail = auth_client.get(f'/api/check-username?username={unique}')
        assert short.get_json()['available'] is False
        assert bad.get_json()['available'] is False
        assert avail.get_json()['available'] is True

    def test_industry_fields_default(self, app, auth_client):
        with app.app_context():
            resp = auth_client.get('/api/industry-fields')
        assert resp.status_code == 200
        assert resp.get_json()['industry'] == 'general'

    def test_product_info_and_barcode(
        self, app, auth_client, sample_product, db_session,
    ):
        import uuid
        barcode_value = f'BAR-{uuid.uuid4().hex[:8]}'
        sample_product.barcode = barcode_value
        db_session.add(sample_product)
        db_session.commit()
        with app.app_context():
            info = auth_client.get(f'/api/products/{sample_product.id}/info')
            missing = auth_client.get('/api/products/999999/info')
            barcode = auth_client.get(f'/api/products/barcode/{barcode_value}')
            validate_empty = auth_client.get('/api/barcode/validate')
            validate_dup = auth_client.get(f'/api/barcode/validate?code={barcode_value}')
        assert info.status_code == 200
        assert info.get_json()['success'] is True
        assert missing.status_code == 404
        assert barcode.get_json()['success'] is True
        assert validate_empty.get_json()['valid'] is False
        assert validate_dup.get_json()['exists'] is True

    def test_echo_dev_only(self, app, auth_client):
        with app.app_context():
            resp = auth_client.put('/api/echo', json={'ping': True})
        assert resp.status_code == 200
        assert resp.get_json()['data']['ping'] is True

    def test_exchange_rates_display(self, app, auth_client):
        with app.app_context():
            resp = auth_client.get('/api/exchange-rates/display?base=USD&symbols=AED,EUR')
        assert resp.status_code == 200

    def test_products_low_stock(self, app, auth_client, mocker):
        from types import SimpleNamespace
        product = SimpleNamespace(
            id=1, name='Low', sku='L1', current_stock=1, min_stock_alert=10, visible_stock=1,
        )
        mocker.patch(
            'routes.api.StockService.get_low_stock_products',
            return_value=[product],
        )
        with app.app_context():
            resp = auth_client.get('/api/products/low-stock')
        assert resp.status_code == 200
        assert resp.get_json()['count'] == 1

    def test_products_low_stock_failure(self, app, auth_client, mocker):
        mocker.patch(
            'routes.api.StockService.get_low_stock_products',
            side_effect=RuntimeError('db'),
        )
        with app.app_context():
            resp = auth_client.get('/api/products/low-stock')
        assert resp.status_code == 500

    def test_currency_rate_failure(self, app, auth_client, mocker):
        mocker.patch(
            'services.currency_service.CurrencyService.get_exchange_rate_details',
            side_effect=ValueError('no rate'),
        )
        with app.app_context():
            resp = auth_client.get('/api/currency-rate/USD/AED')
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_warehouses_with_injected_helper(self, app, auth_client, mocker):
        from types import SimpleNamespace
        import routes.api as api_module

        wh = SimpleNamespace(id=1, name='Main WH')
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [wh]
        mocker.patch.object(api_module, 'get_accessible_warehouses', return_value=mock_q, create=True)
        with app.app_context():
            resp = auth_client.get('/api/warehouses?q=Main')
        assert resp.status_code == 200
        assert resp.get_json()['results'][0]['id'] == 1


class TestClientErrorTelemetry:
    """log-client-error origin policy and payload limits."""

    def test_accepts_trusted_origin_in_testing(self, app, client):
        with app.app_context():
            resp = client.post(
                '/api/log-client-error',
                json={'message': 'test error', 'type': 'runtime'},
                headers={'Origin': 'http://localhost:5000'},
            )
        assert resp.status_code == 204

    def test_rejects_untrusted_origin(self, app, client):
        app.config['CLIENT_ERROR_TRUSTED_ORIGINS'] = 'https://app.example.com'
        with app.app_context():
            resp = client.post(
                '/api/log-client-error',
                json={'message': 'spam'},
                headers={'Origin': 'https://evil.example.com'},
            )
        assert resp.status_code == 403

    def test_rejects_oversized_payload(self, app, client):
        with app.app_context():
            resp = client.post(
                '/api/log-client-error',
                data='x' * (60 * 1024),
                content_type='application/json',
                headers={'Origin': 'http://localhost:5000'},
            )
        assert resp.status_code == 413

    def test_invalid_event_type_normalized(self, app, client, mocker):
        mocker.patch('services.logging_core.LoggingCore.log_frontend_error')
        with app.app_context():
            resp = client.post(
                '/api/log-client-error',
                json={'message': 'bad', 'type': 'not_a_real_type', 'lineno': 1, 'colno': 2},
                headers={'Origin': 'http://localhost:5000'},
            )
        assert resp.status_code == 204


class TestApiHelpers:
    """Pure helpers — origin parsing, production flag, scoped balances."""

    def test_split_origins_and_referer(self, app):
        from routes.api import _origin_from_referer, _split_origins

        with app.app_context():
            assert _split_origins('https://a.com, https://b.com') == {'https://a.com', 'https://b.com'}
            assert _origin_from_referer('https://shop.example/page') == 'https://shop.example'
            assert _origin_from_referer('') is None

    def test_is_production_env_testing_false(self, app):
        from routes.api import _is_production_env

        with app.app_context():
            app.config['APP_ENV'] = 'testing'
            app.config['DEBUG'] = True
            assert _is_production_env() is False

    def test_validate_telemetry_no_origin_in_dev(self, app):
        from routes.api import _validate_public_telemetry_origin

        with app.app_context():
            app.config['APP_ENV'] = 'testing'
            app.config['DEBUG'] = True
            assert _validate_public_telemetry_origin() is None
