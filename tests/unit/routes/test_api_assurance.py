"""API routes — telemetry origin policy and core endpoints."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def api_client(app_factory, mocker):
    user = MagicMock(is_authenticated=True, tenant_id=1, id=1)
    user.has_permission.return_value = True
    mocker.patch('flask_login.utils._get_user', return_value=user)
    mocker.patch('extensions.limiter.limit', return_value=lambda f: f)
    mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
    from routes.api import api_bp
    app = app_factory(api_bp, config_overrides={
        'APP_ENV': 'development',
        'DEBUG': True,
        'CLIENT_ERROR_TRUSTED_ORIGINS': ['http://localhost:5000'],
    })
    return app.test_client()


class TestApiHelpers:
    def test_is_production_env(self, app, monkeypatch):
        from routes.api import _is_production_env
        monkeypatch.setenv('APP_ENV', 'production')
        monkeypatch.setenv('DEBUG', 'false')
        app.config.update(APP_ENV='production', DEBUG=False)
        with app.app_context():
            assert _is_production_env() is True

    def test_origin_from_referer(self):
        from routes.api import _origin_from_referer
        assert _origin_from_referer('https://app.test/page') == 'https://app.test'
        assert _origin_from_referer('bad') is None

    def test_split_origins(self):
        from routes.api import _split_origins
        assert _split_origins('http://a.com/, http://b.com') == {'http://a.com', 'http://b.com'}
        assert _split_origins(['http://x.com/']) == {'http://x.com'}

    def test_trusted_telemetry_origins_dev_default(self, app):
        from routes.api import _trusted_telemetry_origins
        app.config.update(APP_ENV='development', DEBUG=True)
        with app.app_context():
            origins = _trusted_telemetry_origins()
            assert 'http://localhost:5000' in origins


class TestApiEndpoints:
    def test_health(self, api_client):
        resp = api_client.get('/api/health')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'ok'

    def test_version(self, api_client):
        resp = api_client.get('/api/version')
        assert resp.status_code == 200
        assert 'version' in resp.get_json()

    def test_echo(self, api_client):
        resp = api_client.put('/api/echo', json={'hello': 'world'})
        assert resp.status_code == 200
        assert resp.get_json()['data']['hello'] == 'world'

    def test_log_client_error_rejects_unknown_origin(self, api_client):
        resp = api_client.post(
            '/api/log-client-error',
            json={'message': 'x'},
            headers={'Origin': 'http://evil.test'},
        )
        assert resp.status_code in (403, 503)

    def test_log_client_error_rejects_unknown_origin(self, api_client):
        mocker.patch('services.currency_service.CurrencyService.get_supported_currencies', return_value=['AED'])
        mocker.patch('services.currency_service.CurrencyService.get_currency_label', return_value='AED')
        mocker.patch('services.currency_service.CurrencyService.COMMON_CURRENCIES', ['AED'])
        resp = api_client.get('/api/currencies')
        assert resp.status_code == 200

    def test_currencies(self, api_client, mocker):