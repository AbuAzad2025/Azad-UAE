from __future__ import annotations

import io
import logging
import sys
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g

from utils.logging_setup import ColorFormatter, RequestIdFilter, setup_logging


class TestRequestIdFilter:
    def test_uses_request_id_from_g(self, flask_app):
        record = logging.LogRecord('app', logging.INFO, __file__, 10, 'hello', (), None)
        with flask_app.test_request_context('/'):
            g.request_id = 'req-42'
            assert RequestIdFilter().filter(record) is True
        assert record.request_id == 'req-42'

    def test_defaults_without_request_context(self):
        record = logging.LogRecord('app', logging.INFO, __file__, 10, 'hello', (), None)
        with patch('utils.logging_setup.has_request_context', return_value=False):
            assert RequestIdFilter().filter(record) is True
        assert record.request_id == '-'


@pytest.fixture
def flask_app():
    return Flask(__name__)


class TestColorFormatter:
    def test_formats_with_colors_in_development(self, monkeypatch):
        monkeypatch.setenv('FLASK_ENV', 'development')
        formatter = ColorFormatter()
        record = logging.LogRecord('svc', logging.INFO, __file__, 3, 'ready', (), None)
        record.request_id = 'rid'
        message = formatter.format(record)
        assert 'INFO' in message
        assert 'ready' in message
        assert 'rid' in message

    def test_formats_without_colors_outside_development(self, monkeypatch):
        monkeypatch.setenv('FLASK_ENV', 'production')
        formatter = ColorFormatter()
        record = logging.LogRecord('svc', logging.ERROR, __file__, 4, 'boom', (), None)
        record.request_id = '-'
        try:
            raise RuntimeError('x')
        except RuntimeError:
            record.exc_info = sys.exc_info()
        message = formatter.format(record)
        assert 'ERROR' in message
        assert 'RuntimeError' in message

    def test_stdout_encoding_lookup_failure(self, monkeypatch):
        monkeypatch.setenv('FLASK_ENV', 'production')
        stdout = MagicMock()

        def _encoding(_self):
            raise RuntimeError('encoding unavailable')

        type(stdout).encoding = property(_encoding)
        formatter = ColorFormatter()
        record = logging.LogRecord('svc', logging.WARNING, __file__, 5, 'warn', (), None)
        with patch('utils.logging_setup.sys.stdout', stdout):
            message = formatter.format(record)
        assert 'warn' in message


class TestSetupLogging:
    def test_configures_root_and_app_loggers(self, flask_app):
        flask_app.config['LOG_LEVEL'] = 'DEBUG'
        setup_logging(flask_app)
        assert flask_app.logger.handlers
        assert logging.getLogger('sqlalchemy.engine').level == logging.WARNING
        assert logging.getLogger('werkzeug').propagate is True
