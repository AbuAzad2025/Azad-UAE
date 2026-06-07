import logging
from unittest.mock import MagicMock
from utils.logging_setup import setup_logging, RequestIdFilter, ColorFormatter

class TestRequestIdFilter:
    def test_sets_request_id_outside_context(self):
        f = RequestIdFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        f.filter(record)
        assert record.request_id == "-"

class TestColorFormatter:
    def test_format_produces_string(self):
        fmt = ColorFormatter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
        out = fmt.format(record)
        assert isinstance(out, str)
        assert "hello" in out
    def test_format_includes_level_name(self):
        fmt = ColorFormatter()
        record = logging.LogRecord("test", logging.WARNING, "", 0, "warn", (), None)
        out = fmt.format(record)
        assert "WARNING" in out

class TestSetupLogging:
    def test_configures_app_logger(self):
        app = MagicMock()
        app.config = {"LOG_LEVEL": "DEBUG"}
        app.logger = logging.getLogger("test_app_logger")
        app.logger.handlers.clear()
        setup_logging(app)
        assert app.logger.level == logging.DEBUG
        assert len(app.logger.handlers) == 2
    def test_sets_sqlalchemy_warning(self):
        app = MagicMock()
        app.config = {"LOG_LEVEL": "INFO"}
        app.logger = logging.getLogger("test_app_logger_2")
        app.logger.handlers.clear()
        setup_logging(app)
        assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
    def test_clears_werkzeug_handlers(self):
        app = MagicMock()
        app.config = {"LOG_LEVEL": "INFO"}
        app.logger = logging.getLogger("test_app_logger_3")
        app.logger.handlers.clear()
        setup_logging(app)
        assert len(logging.getLogger("werkzeug").handlers) == 0
