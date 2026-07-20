from __future__ import annotations

import io
import logging
import os
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g

from services import logging_core as logging_core_module
from services.logging_core import (
    LoggingCore,
    _ColorFormatter,
    _RateMonitor,
    _ensure_utf8_stream,
    _get_request_context,
    _get_request_id,
    _sanitize_dict,
)

_REAL_LOG_ERROR = LoggingCore.log_error
_REAL_LOG_FRONTEND_ERROR = LoggingCore.log_frontend_error


class _Undefined:
    pass


_Undefined.__name__ = "Undefined"


class TestHelpersSecondPass:
    def test_ensure_utf8_stream_buffer_wrap_failure(self):
        stream = MagicMock()
        stream.reconfigure.side_effect = OSError("nope")
        stream.buffer = io.BytesIO(b"")
        with patch("services.logging_core.io.TextIOWrapper", side_effect=OSError("wrap fail")):
            assert _ensure_utf8_stream(stream) is stream

    def test_get_request_id_generates_and_stores(self, app):
        with app.test_request_context("/"):
            g.request_id = ""
            rid = _get_request_id()
            assert len(rid) == 36
            assert g.request_id == rid

    def test_get_request_id_without_request_context(self, mocker):
        mocker.patch("services.logging_core.has_request_context", return_value=False)
        rid = _get_request_id()
        assert len(rid) == 36

    def test_sanitize_dict_type_lookup_failure(self):
        sentinel = object()
        real_type = type

        def broken_type(obj):
            if obj is sentinel:
                raise RuntimeError("type lookup failed")
            return real_type(obj)

        with patch.object(logging_core_module, "type", side_effect=broken_type):
            clean = _sanitize_dict({"key": sentinel})
        assert clean["key"] is sentinel

    def test_sanitize_dict_undefined_values(self):
        clean = _sanitize_dict({"u": _Undefined(), "items": [_Undefined()]})
        assert clean["u"] is None
        assert clean["items"][0] is None

    def test_get_request_context_authenticated_user(self, app, mocker):
        user = MagicMock()
        user.is_authenticated = True
        user.get_id.return_value = "42"
        user.tenant_id = 7
        mocker.patch("flask_login.current_user", user)
        with app.test_request_context("/auth", headers={"User-Agent": "bot"}):
            ctx = _get_request_context()
            assert ctx["user_id"] == 42
            assert ctx["tenant_id"] == 7


class TestFormattersSecondPass:
    def test_color_formatter_with_exc_info(self, mocker):
        mocker.patch.dict(os.environ, {"FLASK_ENV": "development"})
        try:
            raise ValueError("trace me")
        except ValueError:
            record = logging.LogRecord("n", logging.ERROR, __file__, 1, "fail", (), sys.exc_info())
        record.request_id = "r"
        text = _ColorFormatter().format(record)
        assert "trace me" in text

    def test_color_formatter_encoding_fallback(self, mocker):
        mocker.patch.dict(os.environ, {"FLASK_ENV": "production"})
        record = logging.LogRecord("n", logging.INFO, __file__, 1, "plain", (), None)
        mocker.patch(
            "services.logging_core.sys.stdout",
            MagicMock(encoding="invalid-charset-xyz"),
        )
        text = _ColorFormatter().format(record)
        assert "plain" in text


class TestRateMonitorSecondPass:
    def test_prune_removes_stale_entries(self):
        mon = _RateMonitor()
        old_ts = time.time() - 400
        mon._buckets["BACKEND"] = [(old_ts, 5), (time.time(), 1)]
        mon._prune(mon._buckets["BACKEND"], time.time(), window=300)
        assert len(mon._buckets["BACKEND"]) == 1


class TestSetupSecondPass:
    def test_setup_logs_alert_callback_count(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        LoggingCore._initialized = False
        LoggingCore._handlers = {}
        LoggingCore._alert_callbacks = [lambda *a: None]
        app = Flask(__name__)
        with patch("services.logging_core.RotatingFileHandler") as rfh:
            rfh.side_effect = lambda *a, **k: MagicMock(level=logging.INFO)
            LoggingCore.setup(app)
        LoggingCore._initialized = False
        LoggingCore._alert_callbacks = []

    def test_before_request_sets_start_time(self):
        app = Flask(__name__)
        LoggingCore._register_request_hooks(app)
        with app.test_request_context("/start"):
            for func in app.before_request_funcs[None]:
                func()
            assert hasattr(g, "request_start_time")

    def test_after_request_medium_and_info_paths(self, mocker):
        app = Flask(__name__)
        LoggingCore._register_request_hooks(app)
        response = MagicMock(status_code=200)
        with app.test_request_context("/req"):
            g.request_start_time = 100.0
            for func in app.after_request_funcs[None]:
                with patch("services.logging_core.time.time", return_value=100.75):
                    assert func(response) is response
            g.request_start_time = 100.0
            for func in app.after_request_funcs[None]:
                with patch("services.logging_core.time.time", return_value=101.5):
                    assert func(response) is response

    def test_slow_query_listener_executes(self, app, mocker):
        warn = mocker.patch("services.logging_core.logger.warning")
        captured = {}

        def capture_listens_for(target, identifier):
            def decorator(fn):
                captured[identifier] = fn
                return fn

            return decorator

        mocker.patch("sqlalchemy.event.listens_for", side_effect=capture_listens_for)
        LoggingCore.register_slow_query_listener(app)
        conn = MagicMock()
        conn.info = {}
        with patch("services.logging_core.time.time", return_value=1000.0):
            captured["before_cursor_execute"](conn, None, "SELECT 1", None, None, False)
        with patch("services.logging_core.time.time", return_value=1000.25):
            captured["after_cursor_execute"](conn, None, "SELECT 1", None, None, False)
        warn.assert_called_once()

    def test_capture_warnings_route_append_failure(self, app, mocker):
        mocker.patch("services.logging_core.logger.warning")
        LoggingCore._capture_warnings(app)
        import warnings as builtin_warnings

        mock_req = MagicMock()
        type(mock_req).method = property(lambda self: (_ for _ in ()).throw(RuntimeError("route fail")))
        mock_req.path = "/x"
        mocker.patch("services.logging_core.has_request_context", return_value=True)
        mocker.patch("flask.request", mock_req)
        builtin_warnings.showwarning("dep msg", DeprecationWarning, __file__, 1)

    def test_capture_warnings_hook_failure(self, app, mocker):
        import warnings as builtin_warnings

        class WarningsModule:
            @property
            def showwarning(self):
                return builtin_warnings.showwarning

            @showwarning.setter
            def showwarning(self, value):
                raise RuntimeError("cannot hook warnings")

        mocker.patch.dict(sys.modules, {"warnings": WarningsModule()})
        LoggingCore._capture_warnings(app)

    def test_capture_warnings_with_request_context(self, app, mocker):
        mocker.patch("services.logging_core.logger.warning")
        LoggingCore._capture_warnings(app)
        import warnings as builtin_warnings

        with app.test_request_context("/warn"):
            builtin_warnings.showwarning("dep msg", DeprecationWarning, __file__, 1)

    def test_self_diagnostics_writable_paths(self, tmp_path, monkeypatch):
        from logging.handlers import RotatingFileHandler

        monkeypatch.chdir(tmp_path)
        os.makedirs("logs", exist_ok=True)
        app = Flask(__name__)
        handler = MagicMock(spec=RotatingFileHandler)
        handler.baseFilename = os.path.join(tmp_path, "logs", "app.log")
        with open(handler.baseFilename, "w", encoding="utf-8") as f:
            f.write("x")
        LoggingCore._handlers = {"app": handler}
        with patch("os.access", return_value=True):
            LoggingCore._run_self_diagnostics(app)

    def test_self_diagnostics_file_not_writable(self, tmp_path, monkeypatch):
        from logging.handlers import RotatingFileHandler

        monkeypatch.chdir(tmp_path)
        app = Flask(__name__)
        handler = MagicMock(spec=RotatingFileHandler)
        handler.baseFilename = os.path.join(tmp_path, "exists.log")
        with open(handler.baseFilename, "w", encoding="utf-8") as f:
            f.write("x")
        LoggingCore._handlers = {"app": handler}

        def access(path, mode):
            if path == handler.baseFilename:
                return False
            return True

        with patch("os.access", side_effect=access):
            LoggingCore._run_self_diagnostics(app)

    def test_self_diagnostics_missing_parent_not_writable(self, tmp_path, monkeypatch):
        from logging.handlers import RotatingFileHandler

        monkeypatch.chdir(tmp_path)
        app = Flask(__name__)
        handler = MagicMock(spec=RotatingFileHandler)
        handler.baseFilename = os.path.join(tmp_path, "nested", "missing.log")
        LoggingCore._handlers = {"app": handler}
        with patch("os.path.exists", return_value=False):
            with patch("os.access", return_value=False):
                LoggingCore._run_self_diagnostics(app)

    def test_self_diagnostics_check_failed(self, tmp_path, monkeypatch):
        from logging.handlers import RotatingFileHandler

        monkeypatch.chdir(tmp_path)
        app = Flask(__name__)
        handler = MagicMock(spec=RotatingFileHandler)
        type(handler).baseFilename = property(lambda self: (_ for _ in ()).throw(RuntimeError("bad path")))
        LoggingCore._handlers = {"broken": handler}
        LoggingCore._run_self_diagnostics(app)


class TestAlertCallbacksSecondPass:
    def test_fire_alert_callbacks_empty(self):
        LoggingCore._alert_callbacks = []
        LoggingCore._fire_alert_callbacks("BACKEND", "ERROR", "m", 1)

    def test_fire_alert_callbacks_swallows_errors(self):
        LoggingCore._alert_callbacks = [lambda *a: (_ for _ in ()).throw(RuntimeError("cb fail"))]
        LoggingCore._fire_alert_callbacks("BACKEND", "ERROR", "m", 1)
        LoggingCore._alert_callbacks = []


class TestTraceAndErrorSecondPass:
    def test_set_trace_id_without_request_context(self, mocker):
        mocker.patch("services.logging_core.has_request_context", return_value=False)
        LoggingCore.set_trace_id()

    def test_log_error_logger_failure_still_returns(self, mocker):
        LoggingCore.log_error = _REAL_LOG_ERROR
        mocker.patch.object(LoggingCore, "_persist_error", return_value=5)
        mocker.patch("services.logging_core.logger.error", side_effect=RuntimeError("log fail"))
        assert LoggingCore.log_error("boom") == 5

    def test_log_frontend_error_truncates_long_stack(self, mocker):
        LoggingCore.log_frontend_error = _REAL_LOG_FRONTEND_ERROR
        persist = mocker.patch.object(LoggingCore, "_persist_error", return_value=1)
        stack = "line\n" * 3000
        LoggingCore.log_frontend_error("fe error", stack=stack)
        persist.assert_called_once()
        sent = persist.call_args.kwargs["stack_trace"]
        assert "truncated" in sent

    def test_persist_error_config_exception(self, app, mocker):
        mocker.patch.object(LoggingCore, "_find_duplicate", return_value=None)
        mocker.patch(
            "services.logging_core.current_app.config.get",
            side_effect=RuntimeError("no app"),
        )
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (11,)
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        assert LoggingCore._persist_error("m", category="BACKEND", level="ERROR", source="s") == 11

    def test_persist_error_with_extra_dict(self, app, mocker):
        mocker.patch.object(LoggingCore, "_find_duplicate", return_value=None)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (12,)
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        row = LoggingCore._persist_error("m", category="BACKEND", level="ERROR", source="s", extra={"safe": "v"})
        assert row == 12

    def test_persist_error_json_payload(self, app, mocker):
        mocker.patch.object(LoggingCore, "_find_duplicate", return_value=None)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (13,)
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        with app.test_request_context("/api", method="POST", json={"token": "secret"}):
            row = LoggingCore._persist_error("m", category="BACKEND", level="ERROR", source="s")
        assert row == 13

    def test_persist_error_form_payload(self, app, mocker):
        mocker.patch.object(LoggingCore, "_find_duplicate", return_value=None)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (14,)
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        with app.test_request_context("/form", method="POST", data={"name": "x"}):
            row = LoggingCore._persist_error("m", category="BACKEND", level="ERROR", source="s")
        assert row == 14

    def test_persist_error_payload_read_failure(self, mocker):
        mocker.patch.object(LoggingCore, "_find_duplicate", return_value=None)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (15,)
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        mock_req = MagicMock()
        mock_req.is_json = True
        mock_req.get_json.side_effect = RuntimeError("bad json")
        mock_req.form = None
        mocker.patch("services.logging_core.has_request_context", return_value=True)
        mocker.patch("flask.request", mock_req)
        row = LoggingCore._persist_error("m", category="BACKEND", level="ERROR", source="s")
        assert row == 15

    def test_persist_error_frontend_url_endpoint(self, mocker):
        mocker.patch.object(LoggingCore, "_find_duplicate", return_value=None)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (16,)
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        row = LoggingCore._persist_error(
            "fe",
            category="FRONTEND",
            level="ERROR",
            source="browser",
            url="https://example.com/page?q=1",
            extra={"fingerprint_key": "fp-key"},
        )
        assert row == 16

    def test_persist_error_endpoint_path_exception(self, mocker):
        mocker.patch.object(LoggingCore, "_find_duplicate", return_value=None)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (17,)
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        mock_req = MagicMock()
        mock_req.url = "http://localhost/ok"
        mock_req.method = "GET"
        mock_req.headers = {}
        type(mock_req).path = property(lambda self: (_ for _ in ()).throw(RuntimeError("path fail")))
        mocker.patch("services.logging_core.has_request_context", return_value=True)
        mocker.patch("flask.request", mock_req)
        row = LoggingCore._persist_error("m", category="BACKEND", level="ERROR", source="s")
        assert row == 17

    def test_persist_error_rate_spike_fires_alert(self, app, mocker):
        mocker.patch.object(LoggingCore, "_find_duplicate", return_value=None)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (18,)
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        cb = mocker.MagicMock()
        LoggingCore._alert_callbacks = [cb]
        for _ in range(25):
            LoggingCore._rate_monitor.record("SPIKE")
        row = LoggingCore._persist_error("m", category="SPIKE", level="ERROR", source="s")
        assert row == 18
        cb.assert_called()
        LoggingCore._alert_callbacks = []
        LoggingCore._rate_monitor = __import__("services.logging_core", fromlist=["_RateMonitor"])._RateMonitor()

    def test_persist_error_db_retry_exhausted(self, mocker):
        mocker.patch.object(LoggingCore, "_find_duplicate", return_value=None)
        mocker.patch("extensions.db.engine.connect", side_effect=RuntimeError("db"))
        mocker.patch("services.logging_core.time.sleep")
        mocker.patch("services.logging_core._DB_RETRY_MAX_SECONDS", 0.05)
        fb = mocker.patch.object(LoggingCore, "_fallback_write")
        assert LoggingCore._persist_error("x", category="BACKEND", level="ERROR", source="s") is None
        fb.assert_called_once()

    def test_find_duplicate_success(self, mocker):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (99,)
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        assert LoggingCore._find_duplicate("fp-abc") == 99

    def test_bump_duplicate_success(self, mocker):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (26,)
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        assert LoggingCore._bump_duplicate(5, "updated", "trace") == 26


class TestErrorQueriesSecondPass:
    def test_get_error_logs_resolved_filter(self, mocker):
        pag = MagicMock(items=[], page=1)
        q = MagicMock()
        q.filter_by.return_value = q
        q.order_by.return_value.paginate.return_value = pag
        q.count.return_value = 0
        E = mocker.patch("models.error_audit_log.ErrorAuditLog")
        E.query = q
        mocker.patch(
            "extensions.db.session.query"
        ).return_value.distinct.return_value.order_by.return_value.all.return_value = []
        LoggingCore.get_error_logs(category="API", level="WARN", is_resolved="1")

    def test_export_error_logs_filters(self, mocker):
        q = MagicMock()
        q.filter_by.return_value = q
        q.order_by.return_value.all.return_value = []
        mocker.patch("models.error_audit_log.ErrorAuditLog").query = q
        LoggingCore.export_error_logs(category="API", level="WARN", is_resolved="1", fmt="json")
        LoggingCore.export_error_logs(category="API", level="WARN", is_resolved="0", fmt="txt")

    def test_mark_error_resolved_failure(self, mocker):
        mocker.patch("extensions.db.engine.connect", side_effect=RuntimeError("db"))
        assert LoggingCore.mark_error_resolved(1, 2) is False


class TestHealthSecondPass:
    def test_check_db_success(self, mocker):
        mocker.patch("extensions.db.session.execute")
        result = LoggingCore._check_db()
        assert result["healthy"] is True
        assert result["status"] == "connected"

    def test_check_disk_success(self, mocker):
        mocker.patch("shutil.disk_usage", return_value=(1000, 500, 500))
        result = LoggingCore._check_disk()
        assert result["healthy"] is True
        assert result["percent"] == 50.0

    def test_check_memory_with_psutil(self, mocker):
        mem = SimpleNamespace(total=1024**3, used=512 * 1024**2, percent=50.0)
        psutil = MagicMock()
        psutil.virtual_memory.return_value = mem
        mocker.patch.dict("sys.modules", {"psutil": psutil})
        result = LoggingCore._check_memory()
        assert result["healthy"] is True
        assert "total_mb" in result

    def test_check_cpu_with_psutil(self, mocker):
        psutil = MagicMock()
        psutil.cpu_percent.return_value = 10.0
        psutil.cpu_count.return_value = 4
        mocker.patch.dict("sys.modules", {"psutil": psutil})
        result = LoggingCore._check_cpu()
        assert result["healthy"] is True
        assert result["cores"] == 4

    def test_check_database_success_and_error(self, mocker):
        mocker.patch("extensions.db.session.execute")
        assert LoggingCore.check_database()["healthy"] is True
        mocker.patch("extensions.db.session.execute", side_effect=RuntimeError("down"))
        assert LoggingCore.check_database()["healthy"] is False

    def test_get_disk_usage_success_and_error(self, mocker):
        disk = SimpleNamespace(total=1000, used=400, free=600, percent=40.0)
        psutil = MagicMock()
        psutil.disk_usage.return_value = disk
        mocker.patch.dict("sys.modules", {"psutil": psutil})
        assert LoggingCore.get_disk_usage()["healthy"] is True
        mocker.patch.dict(
            "sys.modules",
            {"psutil": MagicMock(disk_usage=MagicMock(side_effect=RuntimeError()))},
        )
        assert LoggingCore.get_disk_usage()["error"] == "unavailable"

    def test_get_memory_usage_success_and_error(self, mocker):
        mem = SimpleNamespace(total=1024**3, used=100 * 1024**2, percent=10.0)
        psutil = MagicMock()
        psutil.virtual_memory.return_value = mem
        mocker.patch.dict("sys.modules", {"psutil": psutil})
        assert LoggingCore.get_memory_usage()["healthy"] is True
        mocker.patch.dict(
            "sys.modules",
            {"psutil": MagicMock(virtual_memory=MagicMock(side_effect=RuntimeError()))},
        )
        assert LoggingCore.get_memory_usage()["error"] == "unavailable"

    def test_get_cpu_usage_success_and_error(self, mocker):
        psutil = MagicMock()
        psutil.cpu_percent.return_value = 5.0
        psutil.cpu_count.return_value = 8
        mocker.patch.dict("sys.modules", {"psutil": psutil})
        assert LoggingCore.get_cpu_usage()["healthy"] is True
        mocker.patch.dict(
            "sys.modules",
            {"psutil": MagicMock(cpu_percent=MagicMock(side_effect=RuntimeError()))},
        )
        assert LoggingCore.get_cpu_usage()["error"] == "unavailable"


class TestPerformanceSecondPass:
    def test_log_perf_warn_and_debug(self, mocker):
        warn = mocker.patch("services.logging_core.logger.warning")
        debug = mocker.patch("services.logging_core.logger.debug")
        LoggingCore._log_perf("slow_ep", 1500.0)
        warn.assert_called_once()
        LoggingCore._log_perf("ok_ep", 50.0)
        debug.assert_called_once()


class TestTableHelpersSecondPass:
    def test_is_sensitive_table(self):
        assert LoggingCore._is_sensitive_table("users") is True
        assert LoggingCore._is_sensitive_table("sales") is False

    def test_resolve_table_name_paths(self, mocker):
        assert LoggingCore._resolve_table_name("") is None
        assert LoggingCore._resolve_table_name("bad-name!") is None
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["Sales", "products"]
        mocker.patch("sqlalchemy.inspect", return_value=inspector)
        from extensions import db

        mocker.patch.object(logging_core_module, "db", db, create=True)
        with patch("services.logging_core.db", db, create=True):
            assert LoggingCore._resolve_table_name("sales") == "Sales"

    def test_get_db_stats_sensitive_and_exception(self, mocker):
        mocker.patch.object(LoggingCore, "_resolve_table_name", side_effect=["users", "sales", None])
        mocker.patch.object(LoggingCore, "log_audit")
        exec_mock = MagicMock()
        exec_mock.fetchall.return_value = [("users",), ("sales",), ("DROP",)]
        exec_mock.scalar.return_value = 3
        mocker.patch("extensions.db.session.execute", return_value=exec_mock)
        stats, restricted = LoggingCore.get_db_stats_context()
        assert restricted == 1
        assert stats.get("sales") == 3

        mocker.patch("extensions.db.session.execute", side_effect=RuntimeError("db"))
        stats2, restricted2 = LoggingCore.get_db_stats_context()
        assert stats2 == {}
        assert restricted2 == 0


class TestMiscSecondPass:
    def test_log_performance_metric_write_failure(self, mocker):
        mocker.patch("os.makedirs")
        mocker.patch("builtins.open", side_effect=OSError("disk full"))
        LoggingCore.log_performance_metric("x", 1.0)

    def test_track_login_attempt_commit_failure(self, mocker):
        user = MagicMock(login_attempts=0)
        mocker.patch("models.User").query.filter_by.return_value.first.return_value = user
        mock_session = mocker.patch("utils.db_safety.db.session")
        mock_session.flush.side_effect = RuntimeError("commit fail")
        with pytest.raises(RuntimeError):
            LoggingCore.track_login_attempt("bob", success=True, ip_address="1.1.1.1")
        mock_session.rollback.assert_called_once()


class TestAutoCleanupSecondPass:
    def test_auto_cleanup_disk_check_failure(self, mocker):
        mocker.patch("shutil.disk_usage", side_effect=RuntimeError("disk err"))
        conn = MagicMock()
        conn.execute.return_value.rowcount = 0
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        results = LoggingCore.auto_cleanup()
        assert "error_audit_logs" in results

    def test_auto_cleanup_disk_warning(self, mocker, tmp_path):
        mocker.patch("shutil.disk_usage", return_value=(100, 90, 10))
        conn = MagicMock()
        conn.execute.return_value.rowcount = 2
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        os.makedirs(tmp_path / "logs", exist_ok=True)
        with patch("services.logging_core._LOGS_DIR", str(tmp_path / "logs")):
            results = LoggingCore.auto_cleanup()
        assert results.get("disk_warning") is True

    def test_auto_cleanup_log_dir_size_failure(self, mocker):
        mocker.patch("shutil.disk_usage", return_value=(100, 50, 50))
        mocker.patch("os.walk", side_effect=RuntimeError("walk fail"))
        conn = MagicMock()
        conn.execute.return_value.rowcount = 0
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        results = LoggingCore.auto_cleanup()
        assert "logs_dir_mb" not in results

    def test_auto_cleanup_table_failure(self, mocker):
        mocker.patch("shutil.disk_usage", return_value=(100, 50, 50))
        mocker.patch("extensions.db.engine.connect", side_effect=RuntimeError("cleanup fail"))
        results = LoggingCore.auto_cleanup()
        assert results["error_audit_logs"] == 0

    def test_schedule_cleanup_worker_one_iteration(self, app, mocker):
        sleep_calls = []

        def fake_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 2:
                raise KeyboardInterrupt("stop worker")

        mocker.patch("services.logging_core.time.sleep", side_effect=fake_sleep)
        cleanup = mocker.patch.object(LoggingCore, "auto_cleanup", return_value={"error_audit_logs": 1})
        thread_cls = mocker.patch("threading.Thread")
        captured = {}

        def start_thread():
            target = thread_cls.call_args.kwargs.get("target") or thread_cls.call_args[1]["target"]
            captured["target"] = target
            target()

        thread_cls.return_value.start.side_effect = start_thread
        try:
            LoggingCore.schedule_cleanup(app, interval_hours=1)
        except KeyboardInterrupt:
            pass
        cleanup.assert_called_once()

    def test_schedule_cleanup_worker_error_path(self, app, mocker):
        sleep_calls = []

        def fake_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) > 1:
                raise KeyboardInterrupt("stop loop")

        mocker.patch("services.logging_core.time.sleep", side_effect=fake_sleep)
        mocker.patch.object(LoggingCore, "auto_cleanup", side_effect=RuntimeError("cleanup fail"))
        thread_cls = mocker.patch("threading.Thread")

        def capture_and_run():
            target = thread_cls.call_args.kwargs.get("target") or thread_cls.call_args[1]["target"]
            try:
                target()
            except KeyboardInterrupt:
                pass

        thread_cls.return_value.start.side_effect = capture_and_run
        LoggingCore.schedule_cleanup(app, interval_hours=1)
