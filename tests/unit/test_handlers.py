from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, make_response
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from app.handlers import _wants_json_error_response, register_error_handlers


@pytest.fixture
def app_with_handlers():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test'
    app.config['TESTING'] = True
    app.config['DEBUG'] = False
    register_error_handlers(app)

    @app.route('/page')
    def page():
        return 'ok'

    @app.route('/api/data')
    def api_data():
        return {'ok': True}

    @app.route('/boom')
    def boom():
        raise RuntimeError('unexpected')

    @app.route('/db-fail')
    def db_fail():
        raise SQLAlchemyError('db down')

    @app.route('/not-found')
    def not_found_route():
        raise NotFound()

    return app


def _handler(app, exc):
    spec = app.error_handler_spec.get(None, {})
    code = getattr(exc, 'code', None)
    if code is not None and code in spec:
        for exc_cls, fn in spec[code].items():
            if isinstance(exc, exc_cls):
                return fn
    if None in spec:
        for exc_cls, fn in spec[None].items():
            if isinstance(exc, exc_cls):
                return fn
    for bucket in spec.values():
        if isinstance(bucket, dict):
            for exc_cls, fn in bucket.items():
                if isinstance(exc_cls, type) and isinstance(exc, exc_cls):
                    return fn
    return None


def _invoke(app, exc):
    handler = _handler(app, exc)
    assert handler is not None
    result = handler(exc)
    if isinstance(result, tuple):
        body, status = result
        if hasattr(body, 'status_code'):
            body.status_code = status
            return body
        return make_response(body, status)
    return result


class TestWantsJsonErrorResponse:
    def test_json_content_type(self, app_with_handlers):
        with app_with_handlers.test_request_context('/api/data', content_type='application/json'):
            assert _wants_json_error_response() is True

    def test_api_path(self, app_with_handlers):
        with app_with_handlers.test_request_context('/api/data'):
            assert _wants_json_error_response() is True

    def test_xhr_header(self, app_with_handlers):
        with app_with_handlers.test_request_context('/page', headers={'X-Requested-With': 'XMLHttpRequest'}):
            assert _wants_json_error_response() is True


class TestCsrfHandler:
    def test_csrf_json(self, app_with_handlers):
        with patch('app.handlers.LoggingCore.log_error'):
            with app_with_handlers.test_request_context('/api/data', method='POST', headers={'Accept': 'application/json'}):
                resp = _invoke(app_with_handlers, CSRFError('bad token'))
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_csrf_unauthenticated_redirect(self, app_with_handlers):
        anon = MagicMock()
        anon.is_authenticated = False
        with patch('app.handlers.LoggingCore.log_error'), \
             patch('app.handlers.current_user', anon), \
             patch('app.handlers.url_for', return_value='/login'):
            with app_with_handlers.test_request_context('/page'):
                resp = _invoke(app_with_handlers, CSRFError('bad token'))
        assert resp.status_code in (302, 400)

    def test_csrf_authenticated_html(self, app_with_handlers):
        user = MagicMock()
        user.is_authenticated = True
        with patch('app.handlers.LoggingCore.log_error'), \
             patch('app.handlers.current_user', user), \
             patch('app.handlers.render_template', return_value='forbidden'):
            with app_with_handlers.test_request_context('/page'):
                resp = _invoke(app_with_handlers, CSRFError('bad token'))
        assert resp.status_code == 400


class TestHttpErrorHandlers:
    def test_handle_500_production(self, app_with_handlers):
        with patch('app.handlers.LoggingCore.log_error'), \
             patch('app.handlers.render_template', return_value='error'):
            with app_with_handlers.test_request_context('/page'):
                resp = _invoke(app_with_handlers, Exception('fail'))
        assert resp.status_code == 500

    def test_handle_500_debug_reraises(self):
        app = Flask(__name__)
        app.config['DEBUG'] = True
        register_error_handlers(app)
        with patch('app.handlers.LoggingCore.log_error'):
            with app.test_request_context('/'):
                handler = _handler(app, Exception('fail'))
                with pytest.raises(Exception, match='fail'):
                    handler(Exception('fail'))

    def test_handle_404_skips_vite_paths(self, app_with_handlers):
        with patch('app.handlers.LoggingCore.log_error') as log_err, \
             patch('app.handlers.render_template', return_value='missing'):
            with app_with_handlers.test_request_context('/@vite/client'):
                resp = _invoke(app_with_handlers, NotFound())
        assert resp.status_code == 404
        log_err.assert_not_called()

    def test_handle_404_logs_normal_paths(self, app_with_handlers):
        with patch('app.handlers.LoggingCore.log_error') as log_err, \
             patch('app.handlers.render_template', return_value='missing'):
            with app_with_handlers.test_request_context('/missing-page'):
                resp = _invoke(app_with_handlers, NotFound())
        assert resp.status_code == 404
        log_err.assert_called_once()

    def test_handle_403(self, app_with_handlers):
        with patch('app.handlers.LoggingCore.log_error'), \
             patch('app.handlers.render_template', return_value='forbidden'):
            with app_with_handlers.test_request_context('/secret'):
                resp = _invoke(app_with_handlers, Forbidden())
        assert resp.status_code == 403

    def test_handle_http_exception_json(self, app_with_handlers):
        with patch('app.handlers.LoggingCore.log_error'):
            with app_with_handlers.test_request_context('/api/data', headers={'Accept': 'application/json'}):
                resp = _invoke(app_with_handlers, BadRequest('bad input'))
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_handle_generic_exception(self, app_with_handlers):
        with patch('app.handlers.LoggingCore.log_error'), \
             patch('app.handlers.render_template', return_value='error'):
            resp = app_with_handlers.test_client().get('/boom')
        assert resp.status_code == 500

    def test_handle_database_exception(self, app_with_handlers):
        with patch('app.handlers.LoggingCore.log_error'), \
             patch('app.handlers.render_template', return_value='error'):
            resp = app_with_handlers.test_client().get('/db-fail')
        assert resp.status_code == 500

    def test_handle_http_exception_html_returns_exc(self, app_with_handlers):
        with patch('app.handlers.LoggingCore.log_error'):
            with app_with_handlers.test_request_context('/page'):
                result = _handler(app_with_handlers, BadRequest('bad input'))(BadRequest('bad input'))
        assert result.code == 400

    def test_handle_404_via_client(self, app_with_handlers):
        with patch('app.handlers.LoggingCore.log_error'), \
             patch('app.handlers.render_template', return_value='missing'):
            resp = app_with_handlers.test_client().get('/not-found')
        assert resp.status_code == 404
