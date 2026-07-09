from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from utils.rate_limiter_enhanced import adaptive_rate_limit, smart_rate_limit


@pytest.fixture
def flask_app():
    app = Flask(__name__)

    @app.route('/api/test')
    @smart_rate_limit(max_requests=2, window_seconds=60)
    def smart_endpoint():
        return {'ok': True}

    @app.route('/api/adaptive')
    @adaptive_rate_limit(base_limit=10)
    def adaptive_endpoint():
        return {'ok': True}

    return app


def _owner_user():
    user = MagicMock()
    user.is_authenticated = True
    user.is_owner = True
    return user


def _regular_user():
    user = MagicMock()
    user.is_authenticated = True
    user.is_owner = False
    user.is_super_admin.return_value = False
    user.is_manager.return_value = False
    user.id = 42
    return user


class TestSmartRateLimit:
    def test_owner_bypasses_limit(self, flask_app):
        with flask_app.test_request_context('/api/test'):
            with patch('utils.rate_limiter_enhanced.current_user', _owner_user()):
                response = flask_app.view_functions['smart_endpoint']()
        assert response == {'ok': True}

    def test_allows_requests_under_limit(self, flask_app):
        now = datetime(2026, 6, 1, 12, 0, 0)
        with flask_app.test_request_context('/api/test', environ_base={'REMOTE_ADDR': '10.0.0.1'}):
            with patch('utils.rate_limiter_enhanced.current_user', MagicMock(is_authenticated=False)), patch(
                'utils.rate_limiter_enhanced.cache.get', return_value=[]
            ), patch('utils.rate_limiter_enhanced.cache.set') as set_fn, patch(
                'utils.rate_limiter_enhanced.datetime'
            ) as dt:
                dt.now.return_value = now
                response = flask_app.view_functions['smart_endpoint']()
        assert response == {'ok': True}
        set_fn.assert_called_once()

    def test_blocks_when_window_limit_exceeded(self, flask_app):
        now = datetime(2026, 6, 1, 12, 0, 0)
        recent = [now - timedelta(seconds=5), now - timedelta(seconds=10)]
        with flask_app.test_request_context('/api/test', environ_base={'REMOTE_ADDR': '10.0.0.2'}):
            with patch('utils.rate_limiter_enhanced.current_user', MagicMock(is_authenticated=False)), patch(
                'utils.rate_limiter_enhanced.cache.get', return_value=recent
            ), patch('utils.rate_limiter_enhanced.datetime') as dt:
                dt.now.return_value = now
                body, status = flask_app.view_functions['smart_endpoint']()
        assert status == 429
        assert body.get_json()['error'] == 'Rate limit exceeded'

    def test_prunes_expired_requests_from_window(self, flask_app):
        now = datetime(2026, 6, 1, 12, 0, 0)
        stale = [now - timedelta(seconds=120)]
        with flask_app.test_request_context('/api/test', environ_base={'REMOTE_ADDR': '10.0.0.3'}):
            with patch('utils.rate_limiter_enhanced.current_user', MagicMock(is_authenticated=False)), patch(
                'utils.rate_limiter_enhanced.cache.get', return_value=stale
            ), patch('utils.rate_limiter_enhanced.cache.set') as set_fn, patch(
                'utils.rate_limiter_enhanced.datetime'
            ) as dt:
                dt.now.return_value = now
                response = flask_app.view_functions['smart_endpoint']()
        assert response == {'ok': True}
        stored = set_fn.call_args.args[1]
        assert len(stored) == 1


class TestAdaptiveRateLimit:
    def test_owner_gets_highest_limit(self, flask_app):
        with flask_app.test_request_context('/api/adaptive', environ_base={'REMOTE_ADDR': '1.1.1.1'}):
            with patch('utils.rate_limiter_enhanced.current_user', _owner_user()), patch(
                'utils.rate_limiter_enhanced.cache.get', return_value=999
            ), patch('utils.rate_limiter_enhanced.cache.set') as set_fn:
                response = flask_app.view_functions['adaptive_endpoint']()
        assert response == {'ok': True}
        set_fn.assert_called_once()

    def test_super_admin_and_manager_limits(self, flask_app):
        super_admin = _regular_user()
        super_admin.is_super_admin.return_value = True
        manager = _regular_user()
        manager.is_manager.return_value = True

        with flask_app.test_request_context('/api/adaptive'):
            with patch('utils.rate_limiter_enhanced.current_user', super_admin), patch(
                'utils.rate_limiter_enhanced.cache.get', return_value=50
            ), patch('utils.rate_limiter_enhanced.cache.set'):
                assert flask_app.view_functions['adaptive_endpoint']() == {'ok': True}

        with flask_app.test_request_context('/api/adaptive'):
            with patch('utils.rate_limiter_enhanced.current_user', manager), patch(
                'utils.rate_limiter_enhanced.cache.get', return_value=40
            ), patch('utils.rate_limiter_enhanced.cache.set'):
                assert flask_app.view_functions['adaptive_endpoint']() == {'ok': True}

    def test_anonymous_user_gets_reduced_limit_and_blocks(self, flask_app):
        with flask_app.test_request_context('/api/adaptive', environ_base={'REMOTE_ADDR': '8.8.8.8'}):
            with patch('utils.rate_limiter_enhanced.current_user', MagicMock(is_authenticated=False)), patch(
                'utils.rate_limiter_enhanced.cache.get', return_value=5
            ):
                body, status = flask_app.view_functions['adaptive_endpoint']()
        assert status == 429
        assert body.get_json()['your_limit'] == 5

    def test_authenticated_user_blocks_at_base_limit(self, flask_app):
        with flask_app.test_request_context('/api/adaptive'):
            with patch('utils.rate_limiter_enhanced.current_user', _regular_user()), patch(
                'utils.rate_limiter_enhanced.cache.get', return_value=10
            ):
                body, status = flask_app.view_functions['adaptive_endpoint']()
        assert status == 429
        assert body.get_json()['your_limit'] == 10
