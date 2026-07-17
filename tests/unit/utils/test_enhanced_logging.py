from __future__ import annotations

import io
import logging
import sys
from unittest.mock import MagicMock, patch

from flask import Flask

from utils.enhanced_logging import (
    PerformanceLogger,
    SafeLogRecordFilter,
    SecurityLogger,
    _ensure_utf8_stream,
    setup_enhanced_logging,
)


class TestEnsureUtf8Stream:
    def test_reconfigure_path(self):
        stream = MagicMock()
        stream.reconfigure.return_value = None
        assert _ensure_utf8_stream(stream) is stream
        stream.reconfigure.assert_called_once()

    def test_reconfigure_failure_uses_buffer_wrapper(self):
        stream = MagicMock()
        stream.reconfigure.side_effect = OSError("nope")
        stream.buffer = io.BytesIO(b"")
        wrapped = _ensure_utf8_stream(stream)
        assert hasattr(wrapped, "read") or hasattr(wrapped, "write")

    def test_buffer_wrapper_failure_returns_original(self):
        stream = MagicMock()
        stream.reconfigure.side_effect = OSError("nope")
        stream.buffer = io.BytesIO(b"")
        with patch(
            "utils.enhanced_logging.io.TextIOWrapper", side_effect=OSError("wrap fail")
        ):
            assert _ensure_utf8_stream(stream) is stream

    def test_returns_original_when_no_buffer(self):
        stream = MagicMock(spec=["write"])
        assert _ensure_utf8_stream(stream) is stream


class TestSafeLogRecordFilter:
    def test_injects_missing_context_fields(self):
        record = logging.LogRecord("x", logging.WARNING, __file__, 1, "msg", (), None)
        assert SafeLogRecordFilter().filter(record) is True
        assert record.user == "-"
        assert record.ip == "-"
        assert record.tenant == "-"
        assert record.request_id == "-"


class TestSetupEnhancedLogging:
    def test_configures_handlers_and_teardown(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        app = Flask(__name__)
        app.logger = logging.getLogger("enhanced-test")
        app.logger.handlers.clear()
        app.debug = False

        def make_handler():
            handler = MagicMock()
            handler.level = logging.INFO
            return handler

        with patch(
            "utils.enhanced_logging.RotatingFileHandler",
            side_effect=lambda *a, **k: make_handler(),
        ):
            handlers = setup_enhanced_logging(app)

        assert set(handlers) == {"app", "error", "security", "performance"}
        assert app.logger.handlers

        teardown = next(
            (
                item[0] if isinstance(item, tuple) else item
                for item in app.teardown_appcontext_funcs
                if getattr(item[0] if isinstance(item, tuple) else item, "__name__", "")
                == "_close_log_handlers"
            ),
            None,
        )
        assert teardown is not None
        teardown(None)

    def test_removes_existing_stream_handlers_and_closes_on_error(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        app = Flask(__name__)
        app.logger = logging.getLogger("enhanced-test-2")
        app.logger.handlers.clear()
        app.debug = True
        stale = logging.StreamHandler()
        stale.stream = sys.stdout
        app.logger.addHandler(stale)

        def make_handler():
            log_handler = MagicMock()
            log_handler.level = logging.INFO
            log_handler.close.side_effect = RuntimeError("close fail")
            return log_handler

        with (
            patch(
                "utils.enhanced_logging.RotatingFileHandler",
                side_effect=lambda *a, **k: make_handler(),
            ),
            patch("utils.enhanced_logging.logging.getLogger") as get_logger,
        ):
            werkzeug = MagicMock()
            werkzeug.handlers = [logging.StreamHandler()]
            get_logger.return_value = werkzeug
            handlers = setup_enhanced_logging(app)

        assert werkzeug.removeHandler.called
        teardown = next(
            (
                item[0] if isinstance(item, tuple) else item
                for item in app.teardown_appcontext_funcs
                if getattr(item[0] if isinstance(item, tuple) else item, "__name__", "")
                == "_close_log_handlers"
            ),
            None,
        )
        assert teardown is not None
        teardown(None)
        for handler in handlers.values():
            handler.close.assert_called()


class TestSecurityLogger:
    def test_security_events_emit_logs(self):
        with (
            patch("utils.enhanced_logging.logging.warning") as warning,
            patch("utils.enhanced_logging.logging.info") as info,
        ):
            SecurityLogger.log_failed_login("alice", "1.2.3.4", "pytest")
            SecurityLogger.log_successful_login("bob", "5.6.7.8")
            SecurityLogger.log_permission_denied("carol", "delete", "9.9.9.9")
            SecurityLogger.log_rate_limit_exceeded("dave", "/api", "8.8.8.8")
        assert warning.call_count == 3
        info.assert_called_once()


class TestPerformanceLogger:
    def test_slow_query_cache_logs(self):
        with (
            patch("utils.enhanced_logging.logging.warning") as warning,
            patch("utils.enhanced_logging.logging.debug") as debug,
        ):
            PerformanceLogger.log_slow_query("SELECT *", 0.5)
            PerformanceLogger.log_slow_query("SELECT big", 2.0)
            PerformanceLogger.log_cache_hit("products")
            PerformanceLogger.log_cache_miss("customers")
        warning.assert_called_once()
        assert debug.call_count == 2
