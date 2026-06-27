from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import pytest

from utils.structured_logging import (
    log_data_access,
    log_mutation,
    log_security_event,
    _get_request_context,
    _get_user_context,
)


class TestContextHelpers:
    def test_request_context_without_flask(self, mocker):
        mocker.patch('utils.structured_logging.has_request_context', return_value=False)
        assert _get_request_context() == {}

    def test_request_context_with_flask(self, app):
        with app.test_request_context('/api/test', method='POST', headers={'User-Agent': 'pytest-agent'}):
            ctx = _get_request_context()
            assert ctx['method'] == 'POST'
            assert '/api/test' in ctx['url']
            assert 'pytest-agent' in ctx['user_agent']

    def test_user_context_unauthenticated(self, mocker):
        user = MagicMock(is_authenticated=False)
        mocker.patch('utils.structured_logging.current_user', user)
        assert _get_user_context() == {}

    def test_user_context_authenticated(self, mocker):
        user = MagicMock(
            is_authenticated=True,
            id=7,
            username='tester',
            tenant_id=3,
            is_owner=True,
        )
        mocker.patch('utils.structured_logging.current_user', user)
        ctx = _get_user_context()
        assert ctx['user_id'] == 7
        assert ctx['tenant_id'] == 3
        assert ctx['is_owner'] is True

    def test_user_context_exception_returns_empty(self, mocker):
        class BrokenUser:
            @property
            def is_authenticated(self):
                raise RuntimeError('no user')

        mocker.patch('utils.structured_logging.current_user', BrokenUser())
        assert _get_user_context() == {}


class TestLogMutation:
    def test_log_mutation_info(self, app, mocker):
        mock_logger = mocker.patch('utils.structured_logging.logger')
        user = MagicMock(is_authenticated=True, id=1, username='u', tenant_id=2, is_owner=False)
        mocker.patch('utils.structured_logging.current_user', user)
        with app.test_request_context('/sales/1', method='PUT'):
            log_mutation('update', 'Sale', entity_id=1, details={'field': 'total'})
        mock_logger.info.assert_called_once()
        payload = json.loads(mock_logger.info.call_args[0][0])
        assert payload['action'] == 'update'
        assert payload['entity_type'] == 'Sale'
        assert payload['entity_id'] == 1

    def test_log_mutation_custom_level(self, mocker):
        mock_logger = mocker.patch('utils.structured_logging.logger')
        log_mutation('delete', 'Product', level='warning')
        mock_logger.warning.assert_called_once()

    def test_log_mutation_unknown_level_falls_back_to_info(self, mocker):
        import logging
        mock_logger = mocker.patch('utils.structured_logging.logger', spec=logging.Logger)
        mock_logger.info = MagicMock()
        log_mutation('create', 'User', level='not_a_level')
        mock_logger.info.assert_called_once()


class TestLogSecurityEvent:
    def test_log_security_event_default(self, mocker):
        mock_logger = mocker.patch('utils.structured_logging.logger')
        log_security_event('login_failed', 'bad password')
        mock_logger.info.assert_called_once()
        payload = json.loads(mock_logger.info.call_args[0][0])
        assert payload['security_event'] == 'login_failed'

    def test_log_security_event_alert_uses_warning(self, mocker):
        mock_logger = mocker.patch('utils.structured_logging.logger')
        log_security_event('brute_force', 'many attempts', severity='alert', extra={'ip': '1.2.3.4'})
        mock_logger.warning.assert_called_once()

    def test_log_security_event_error_level(self, mocker):
        mock_logger = mocker.patch('utils.structured_logging.logger')
        log_security_event('permission_denied', 'no access', severity='error')
        mock_logger.error.assert_called_once()


class TestLogDataAccess:
    def test_log_data_access_read(self, app, mocker):
        mock_logger = mocker.patch('utils.structured_logging.logger')
        with app.test_request_context('/reports/customers'):
            log_data_access('Customer', entity_id=5, access_type='read', details={'export': True})
        mock_logger.info.assert_called_once()
        payload = json.loads(mock_logger.info.call_args[0][0])
        assert payload['event_type'] == 'data_access'
        assert payload['access_type'] == 'read'
