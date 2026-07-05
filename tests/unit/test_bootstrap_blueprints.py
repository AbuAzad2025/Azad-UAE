from __future__ import annotations

import builtins
import os
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask_login import LoginManager

from bootstrap import blueprints as bp_module


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test'
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(_):
        return MagicMock(is_authenticated=True)

    app.add_url_rule('/dashboard', 'main.dashboard', lambda: 'ok')
    return app


class TestImportBp:
    def test_import_bp_success(self, flask_app):
        bp = bp_module._import_bp(flask_app, 'routes.monitoring', 'monitoring_bp')
        assert bp.name == 'monitoring'

    def test_import_bp_failure_logs_and_raises(self, flask_app):
        real_import = builtins.__import__

        def selective_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'routes.nonexistent_xyz':
                raise ImportError('missing module')
            return real_import(name, globals, locals, fromlist, level)

        with patch('builtins.__import__', side_effect=selective_import), \
             patch('services.logging_core.LoggingCore.log_error', side_effect=RuntimeError('log fail')):
            with flask_app.app_context():
                with pytest.raises(ImportError):
                    bp_module._import_bp(flask_app, 'routes.nonexistent_xyz', 'fake_bp')

    def test_ai_fallback_catch_all_log_error_fails(self, flask_app, monkeypatch):
        ai_bp = bp_module._make_ai_fallback('import failed')
        flask_app.register_blueprint(ai_bp)

        class _BrokenSession:
            def get(self, key, default=None):
                raise RuntimeError('session fail')

        monkeypatch.setattr('flask.session', _BrokenSession())
        with patch('services.logging_core.LoggingCore.log_error', side_effect=RuntimeError('log fail')):
            resp = flask_app.test_client().get('/ai/another-route', follow_redirects=False)
        assert resp.status_code == 302

    def test_import_bp_log_db_failure(self, flask_app):
        real_import = builtins.__import__

        def selective_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'routes.broken_bp_xyz':
                raise ImportError('missing module')
            return real_import(name, globals, locals, fromlist, level)

        with patch('builtins.__import__', side_effect=selective_import), \
             patch('services.logging_core.LoggingCore.log_error', side_effect=RuntimeError('log fail')):
            with flask_app.app_context():
                with pytest.raises(ImportError):
                    bp_module._import_bp(flask_app, 'routes.broken_bp_xyz', 'fake_bp')


class TestAiFallback:
    def test_ai_fallback_assistant_redirect(self, flask_app):
        ai_bp = bp_module._make_ai_fallback('import failed')
        flask_app.register_blueprint(ai_bp)
        with flask_app.test_client() as client:
            with patch('flask_login.utils._get_user', return_value=MagicMock(is_authenticated=True)):
                resp = client.get('/ai/assistant', follow_redirects=False)
        assert resp.status_code == 302

    def test_ai_fallback_config_redirect(self, flask_app):
        ai_bp = bp_module._make_ai_fallback('import failed')
        flask_app.register_blueprint(ai_bp)
        with flask_app.test_client() as client:
            with patch('flask_login.utils._get_user', return_value=MagicMock(is_authenticated=True)):
                resp = client.get('/ai/config', follow_redirects=False)
        assert resp.status_code == 302

    def test_ai_fallback_chat_unavailable(self, flask_app):
        ai_bp = bp_module._make_ai_fallback('import failed')
        flask_app.register_blueprint(ai_bp)
        resp = flask_app.test_client().post('/ai/chat')
        assert resp.status_code == 503

    def test_ai_fallback_post_endpoints(self, flask_app):
        ai_bp = bp_module._make_ai_fallback('import failed')
        flask_app.register_blueprint(ai_bp)
        client = flask_app.test_client()
        for path in (
            '/ai/recommend-price',
            '/ai/check-stock',
            '/ai/upload-excel',
        ):
            resp = client.post(path)
            assert resp.status_code == 503

    def test_ai_fallback_get_endpoints(self, flask_app):
        ai_bp = bp_module._make_ai_fallback('import failed')
        flask_app.register_blueprint(ai_bp)
        client = flask_app.test_client()
        for path in (
            '/ai/analyze-customer/1',
            '/ai/exchange-rate/USD',
            '/ai/search-market-price/2',
            '/ai/find-compatible/3',
        ):
            resp = client.get(path)
            assert resp.status_code == 503

    def test_ai_fallback_catch_all_sets_session(self, flask_app):
        ai_bp = bp_module._make_ai_fallback('import failed')
        flask_app.register_blueprint(ai_bp)
        with flask_app.test_client() as client:
            with patch('flask_login.utils._get_user', return_value=MagicMock(is_authenticated=True)):
                resp = client.get('/ai/unknown-route', follow_redirects=False)
        assert resp.status_code == 302

    def test_ai_fallback_catch_all_session_error(self, flask_app, monkeypatch):
        ai_bp = bp_module._make_ai_fallback('import failed')
        flask_app.register_blueprint(ai_bp)

        class _BrokenSession:
            def get(self, key, default=None):
                raise RuntimeError('session fail')

        monkeypatch.setattr('flask.session', _BrokenSession())
        with patch('services.logging_core.LoggingCore.log_error') as log_err:
            resp = flask_app.test_client().get('/ai/another-route', follow_redirects=False)
        assert resp.status_code == 302
        log_err.assert_called_once()


class TestRegisterBlueprints:
    def test_register_blueprints_with_disable_ai(self, flask_app, monkeypatch):
        monkeypatch.setenv('DISABLE_AI', '1')
        with patch.object(bp_module, '_import_bp', side_effect=lambda app, mod, name: MagicMock(name=name)):
            result = bp_module.register_blueprints(flask_app)
        assert result is flask_app

    def test_register_blueprints_ai_import_failure(self, flask_app, monkeypatch):
        monkeypatch.delenv('DISABLE_AI', raising=False)
        real_import = builtins.__import__

        def selective_import(name, *args, **kwargs):
            if name == 'routes.ai_routes':
                raise ImportError('ai broken')
            return real_import(name, *args, **kwargs)

        with patch.object(bp_module, '_import_bp', side_effect=lambda app, mod, name: MagicMock(name=name)), \
             patch('builtins.__import__', side_effect=selective_import):
            result = bp_module.register_blueprints(flask_app)
        assert result is flask_app

    def test_register_blueprints_success(self, flask_app, monkeypatch):
        monkeypatch.delenv('DISABLE_AI', raising=False)
        fake_bp = MagicMock()
        with patch.object(bp_module, '_import_bp', return_value=fake_bp), \
             patch('routes.ai_routes.ai_bp', fake_bp):
            result = bp_module.register_blueprints(flask_app)
        assert result is flask_app
