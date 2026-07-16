"""Logging setup — request id filter, color formatter, app wiring."""
from __future__ import annotations

import logging
import os
import sys
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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

    def test_format_encoding_stdout_access_error(self, mocker):
        from utils.logging_setup import ColorFormatter
        mocker.patch.dict(os.environ, {'FLASK_ENV': 'production'}, clear=False)
        record = logging.LogRecord('app', logging.INFO, '', 0, 'ok', (), None)
        record.request_id = '-'
        fmt = ColorFormatter()
        mocker.patch.object(fmt, 'formatTime', return_value='ts')
        bad_stdout = MagicMock()
        type(bad_stdout).encoding = property(
            lambda _self: (_ for _ in ()).throw(RuntimeError('no enc'))
        )
        mocker.patch('utils.logging_setup.sys.stdout', bad_stdout)
        assert 'ok' in fmt.format(record)

    def test_setup_logging_win32_wraps_streams(self, app, monkeypatch, mocker):
        import io
        raw_out = SimpleNamespace(buffer=BytesIO())
        raw_err = SimpleNamespace(buffer=BytesIO())
        monkeypatch.setattr('utils.logging_setup.sys.platform', 'win32')
        monkeypatch.setattr('utils.logging_setup.sys.stdout', raw_out)
        monkeypatch.setattr('utils.logging_setup.sys.stderr', raw_err)
        wrapped = io.TextIOWrapper(BytesIO(), encoding='utf-8')
        wrapper = mocker.patch('io.TextIOWrapper', return_value=wrapped)
        mocker.patch.object(app.logger, 'info')
        from utils.logging_setup import setup_logging
        setup_logging(app)
        assert wrapper.call_count >= 2

    def test_setup_logging_configures_handlers(self, app, mocker):
        mocker.patch('utils.logging_setup.sys.platform', 'linux')
        from utils.logging_setup import setup_logging
        setup_logging(app)
        assert app.logger.handlers
        assert logging.getLogger('sqlalchemy.engine').level == logging.WARNING

    def test_colorama_import_fallback(self):
        import builtins
        import importlib
        import sys

        mod_name = 'utils.logging_setup'
        saved = sys.modules.pop(mod_name, None)
        real_import = builtins.__import__

        def blocked_import(name, globals_dict=None, locals_dict=None, fromlist=(), level=0):
            if name == 'colorama':
                raise ImportError('blocked for test')
            return real_import(name, globals_dict, locals_dict, fromlist, level)

        try:
            with patch.object(builtins, '__import__', side_effect=blocked_import):
                mod = importlib.import_module(mod_name)
            assert mod.Fore.BLUE == ''
            assert mod.Style.RESET_ALL == ''
        finally:
            if saved is not None:
                sys.modules[mod_name] = saved
            importlib.import_module(mod_name)

    def test_format_encoding_ascii_fallback(self, mocker):
        from utils.logging_setup import ColorFormatter

        mocker.patch.dict(os.environ, {'FLASK_ENV': 'production'}, clear=False)
        mocker.patch('utils.logging_setup.sys.stdout', SimpleNamespace(encoding='invalid-encoding-xyz'))
        fmt = ColorFormatter()
        mocker.patch.object(fmt, 'formatTime', return_value='ts')
        record = logging.LogRecord('app', logging.INFO, '', 0, 'ok', (), None)
        record.request_id = '-'
        assert 'ok' in fmt.format(record)
