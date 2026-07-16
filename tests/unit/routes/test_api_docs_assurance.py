"""API docs routes — OpenAPI spec exposure and production protection."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def api_docs_client(app_factory, mocker):
    mocker.patch('flask_login.utils._get_user', return_value=MagicMock(is_authenticated=False))
    from routes.api_docs import api_docs_bp
    app = app_factory(api_docs_bp)
    return app.test_client()


class TestApiDocsPublic:
    def test_openapi_json(self, api_docs_client):
        resp = api_docs_client.get('/api-docs/openapi.json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['openapi'] == '3.0.3'
        assert '/health' in data['paths']

    def test_contact_overrides(self, app_factory, mocker):
        mocker.patch('flask_login.utils._get_user', return_value=MagicMock(is_authenticated=False))
        from routes.api_docs import api_docs_bp
        app = app_factory(api_docs_bp, config_overrides={
            'DEVELOPER_NAME': 'Dev',
            'DEVELOPER_EMAIL': 'dev@test.com',
            'DEVELOPER_WEBSITE': 'https://dev.test',
        })
        client = app.test_client()
        contact = client.get('/api-docs/openapi.json').get_json()['info']['contact']
        assert contact['name'] == 'Dev'
        assert contact['email'] == 'dev@test.com'

    def test_swagger_and_redoc(self, api_docs_client):
        assert b'swagger-ui' in api_docs_client.get('/api-docs/').data.lower()
        assert b'redoc' in api_docs_client.get('/api-docs/redoc').data.lower()


class TestApiDocsProtection:
    def test_protected_anonymous_404(self, api_docs_client):
        with patch('routes.api_docs._api_docs_public', return_value=False):
            with patch('routes.api_docs.current_user', MagicMock(is_authenticated=False)):
                resp = api_docs_client.get('/api-docs/openapi.json')
        assert resp.status_code == 404

    def test_protected_authenticated_ok(self, api_docs_client):
        with patch('routes.api_docs._api_docs_public', return_value=False):
            with patch('routes.api_docs.current_user', MagicMock(is_authenticated=True)):
                resp = api_docs_client.get('/api-docs/openapi.json')
        assert resp.status_code == 200
        assert 'servers' not in resp.get_json()

    def test_api_docs_public_env(self, monkeypatch):
        monkeypatch.setenv('APP_ENV', 'development')
        monkeypatch.setenv('DEBUG', 'true')
        from routes.api_docs import _api_docs_public
        assert _api_docs_public() is True

    def test_api_docs_production_requires_swagger_flag(self, monkeypatch):
        monkeypatch.setenv('APP_ENV', 'staging')
        monkeypatch.setenv('DEBUG', 'false')
        monkeypatch.setenv('ENABLE_SWAGGER_UI', 'true')
        from routes.api_docs import _api_docs_public
        assert _api_docs_public() is True
