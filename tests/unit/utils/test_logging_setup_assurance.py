"""Logging setup — request id filter, color formatter, app wiring."""
from __future__ import annotations

import logging
import os
import sys
from io import BytesIO
from unittest.mock import MagicMock

import pytest


class TestRequestIdFilter:
    def test_filter_with_request_context(self, app, mocker):
        from utils.logging_setup import RequestIdFilter
        mocker.patch('utils.logging_setup.has_request_context', return_value=True)
        with app.test_request_context():
            from flask import g
            g.request_id = 'abc-123'
            record = logging.LogRecord('n', logging.INFO, '', 0, 'msg', (), None)
            assert RequestIdFilter().filter(record) is True
            assert record.request_id == 'abc-123'

    def test_filter_without_request_context(self, mocker):
        from utils.logging_setup import RequestIdFilter
        mocker.patch('utils.logging_setup.has_request_context', return_value=False)
        record = logging.LogRecord('n', logging.INFO, '', 0, 'msg', (), None)
        RequestIdFilter().filter(record)
        assert record.request_id == '-'


class TestColorFormatter:
    def test_format_dev_colors(self, mocker):
        from utils.logging_setup import ColorFormatter
        mocker.patch.dict(os.environ, {'FLASK_ENV': 'development'}, clear=False)
        record = logging.LogRecord('app', logging.ERROR, '', 0, 'boom', (), None)
        record.request_id = 'rid'
        text = ColorFormatter().format(record)
        assert 'ERROR' in text
        assert 'boom' in text

    def test_format_prod_no_colors(self, mocker):
        from utils.logging_setup import ColorFormatter
        mocker.patch.dict(os.environ, {'FLASK_ENV': 'production'}, clear=False)
        record = logging.LogRecord('app', logging.INFO, '', 0, 'ok', (), None)
        record.request_id = '-'
        assert ColorFormatter().format(record).startswith('[')

    def test_format_with_exception(self, mocker):
        from utils.logging_setup import ColorFormatter
        mocker.patch.dict(os.environ, {'FLASK_ENV': 'production'}, clear=False)
        try:
            raise ValueError('x')
        except ValueError:
            import sys as _sys
            exc = _sys.exc_info()
        record = logging.LogRecord('app', logging.ERROR, '', 0, 'fail', (), exc)
        record.request_id = '-'
        assert 'ValueError' in ColorFormatter().format(record)


class TestSetupLogging:
    def test_format_encoding_fallback(self, mocker):
        from utils.logging_setup import ColorFormatter
        mocker.patch.dict(os.environ, {'FLASK_ENV': 'production'}, clear=False)
        record = logging.LogRecord('app', logging.INFO, '', 0, 'ok', (), None)
        record.request_id = '-'
        fmt = ColorFormatter()
        mocker.patch.object(fmt, 'formatTime', return_value='ts')
        mocker.patch('utils.logging_setup.sys.stdout', None)
        text = fmt.format(record)
        assert 'ok' in text

    def test_setup_logging_configures_handlers(self, app):
        from utils.logging_setup import setup_logging
        setup_logging(app)
        assert app.logger.handlers
        assert logging.getLogger('sqlalchemy.engine').level == logging.WARNING

    def test_setup_logging_wraps_stdout_on_windows(self, app, mocker):
        mocker.patch('utils.logging_setup.sys.platform', 'win32')
        buffer = BytesIO(b'hello')
        fake_stdout = MagicMock()
        fake_stdout.buffer = buffer
        del fake_stdout._azad_utf8_wrapped
        mocker.patch('utils.logging_setup.sys.stdout', fake_stdout)
        mocker.patch('utils.logging_setup.sys.stderr', fake_stdout)
        mocker.patch('utils.logging_setup.io.TextIOWrapper', return_value=fake_stdout)
        from utils.logging_setup import setup_logging
        setup_logging(app)
