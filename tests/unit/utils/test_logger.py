"""Unit tests for utils/logger.py — structured JSON telemetry logger."""

from __future__ import annotations

import json
import logging
import time

import pytest
from flask import Flask

from utils import logger as telemetry
from utils.logger import (
    CATEGORY_CRITICAL_FINANCIAL,
    CATEGORY_HARDWARE_WARN,
    CATEGORY_SECURITY_ALERT,
    CATEGORY_SOFTWARE_EXCEPTION,
    TELEMETRY_LOGGER_NAME,
    bind_context,
    clear_context,
    enable_error_log_bridge,
    init_telemetry,
    log_event,
    log_exception,
    log_financial,
    log_hardware,
    log_security,
)
from services.logging_core import LoggingCore


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.entries: list[dict] = []
        self.setFormatter(telemetry._TelemetryEventFormatter())

    def emit(self, record):
        self.entries.append(json.loads(self.format(record)))


@pytest.fixture()
def capture():
    handler = _CaptureHandler()
    log = logging.getLogger(TELEMETRY_LOGGER_NAME)
    log.handlers.clear()
    log.addHandler(handler)
    yield handler
    log.handlers.clear()
    log.addHandler(logging.NullHandler())
    clear_context()


@pytest.fixture(autouse=True)
def _reset_state():
    yield
    clear_context()
    log = logging.getLogger(TELEMETRY_LOGGER_NAME)
    log.handlers.clear()
    log.addHandler(logging.NullHandler())
    log.propagate = False


class TestSchema:
    def test_full_schema_with_bound_context(self, capture):
        bind_context(
            tenant_id=7,
            user_id=9,
            request_id="rid-1",
            ip="1.2.3.4",
            endpoint="pos.api",
            method="POST",
        )
        log_event("TEST_EVENT", "hello", extra_flag=True)
        entry = capture.entries[-1]
        for key in (
            "timestamp",
            "level",
            "category",
            "message",
            "tenant_id",
            "user_id",
            "request_id",
            "ip",
            "endpoint",
            "method",
            "duration_ms",
        ):
            assert key in entry
        assert entry["category"] == "TEST_EVENT"
        assert entry["message"] == "hello"
        assert entry["tenant_id"] == 7
        assert entry["user_id"] == 9
        assert entry["request_id"] == "rid-1"
        assert entry["extra_flag"] is True

    def test_explicit_tenant_id_overrides_context(self, capture):
        bind_context(tenant_id=7)
        log_event("TEST_EVENT", "m", tenant_id=99)
        assert capture.entries[-1]["tenant_id"] == 99

    def test_contextvars_work_outside_request_context(self, capture):
        # No app/request context bound at all — extras + explicit ids still emit.
        log_event("BG_EVENT", "background", tenant_id=3, job="cleanup")
        entry = capture.entries[-1]
        assert entry["tenant_id"] == 3
        assert entry["job"] == "cleanup"
        assert entry["request_id"] is None

    def test_duration_ms_computed_from_request_start(self, capture):
        bind_context(request_start=time.monotonic() - 0.05)
        log_event("TIMED", "m", tenant_id=1)
        assert capture.entries[-1]["duration_ms"] >= 40

    def test_extras_never_clobber_core_keys(self, capture):
        log_event("CORE", "m", tenant_id=1, level="hijack")
        entry = capture.entries[-1]
        assert entry["level"] == "INFO"
        assert entry["category"] == "CORE"


class TestCategories:
    def test_helper_categories_and_levels(self, capture):
        log_financial("fin", tenant_id=1)
        log_security("sec", tenant_id=1)
        log_hardware("hw", tenant_id=1)
        cats = [e["category"] for e in capture.entries[-3:]]
        assert cats == [CATEGORY_CRITICAL_FINANCIAL, CATEGORY_SECURITY_ALERT, CATEGORY_HARDWARE_WARN]
        levels = [e["level"] for e in capture.entries[-3:]]
        assert levels == ["CRITICAL", "WARNING", "WARNING"]

    def test_log_exception_includes_stack(self, capture):
        try:
            raise ValueError("boom")
        except ValueError as exc:
            log_exception("failed hard", exception=exc, level="CRITICAL", tenant_id=5)
        entry = capture.entries[-1]
        assert entry["category"] == CATEGORY_SOFTWARE_EXCEPTION
        assert entry["level"] == "CRITICAL"
        assert entry["tenant_id"] == 5
        assert entry["exception"]["type"] == "ValueError"
        assert "boom" in entry["exception"]["traceback"]


class TestSinks:
    def test_testing_mode_attaches_nullhandler_only(self, app, capsys):
        init_telemetry(app)
        log = logging.getLogger(TELEMETRY_LOGGER_NAME)
        assert len(log.handlers) == 1
        assert isinstance(log.handlers[0], logging.NullHandler)
        log_event("QUIET", "no output expected", tenant_id=1)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "QUIET" not in captured.err

    def test_no_propagation_to_root(self, capture):
        log = logging.getLogger(TELEMETRY_LOGGER_NAME)
        assert log.propagate is False

    def test_file_sink_writes_jsonl(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("FLASK_ENV", "production")
        sink = tmp_path / "telemetry.jsonl"
        monkeypatch.setattr(telemetry, "_telemetry_sink_path", lambda: str(sink))
        app2 = Flask(__name__)
        init_telemetry(app2)
        bind_context(request_id="file-rid")
        log_event("FILE_EVENT", "written", tenant_id=42, amount="10.500")
        for h in logging.getLogger(TELEMETRY_LOGGER_NAME).handlers:
            h.flush()
        lines = sink.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["category"] == "FILE_EVENT"
        assert entry["tenant_id"] == 42
        assert entry["request_id"] == "file-rid"
        assert entry["amount"] == "10.500"

    def test_development_mode_mirrors_stdout(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("FLASK_ENV", "development")
        monkeypatch.setattr(telemetry, "_telemetry_sink_path", lambda: str(tmp_path / "t.jsonl"))
        app2 = Flask(__name__)
        init_telemetry(app2)
        log_event("DEV_EVENT", "dev line", tenant_id=1)
        out = capsys.readouterr().out
        assert "DEV_EVENT" in out


class TestRobustness:
    def test_emit_never_raises_with_broken_handler(self):
        class _BrokenHandler(logging.Handler):
            def emit(self, record):
                raise RuntimeError("sink down")

        log = logging.getLogger(TELEMETRY_LOGGER_NAME)
        log.handlers.clear()
        log.addHandler(_BrokenHandler())
        # Must not propagate the sink failure into business flow.
        log_event("BROKEN", "m", tenant_id=1)
        log.handlers.clear()
        log.addHandler(logging.NullHandler())

    def test_clear_context_resets_all(self, capture):
        bind_context(tenant_id=7, request_id="x")
        clear_context()
        log_event("AFTER_CLEAR", "m")
        entry = capture.entries[-1]
        assert entry["tenant_id"] is None
        assert entry["request_id"] is None

    def test_bind_context_ignores_unknown_fields(self, capture):
        bind_context(tenant_id=1, not_a_real_field="ignored")
        log_event("BOUND", "m")
        entry = capture.entries[-1]
        assert entry["tenant_id"] == 1
        assert "not_a_real_field" not in entry


class TestErrorLogBridge:
    """The telemetry → LoggingCore DB bridge: mapping, guards, opt-in."""

    @pytest.fixture()
    def bridge_mock(self, mocker):
        """Intercept LoggingCore.log_error with the bridge explicitly enabled."""
        mock = mocker.patch.object(LoggingCore, "log_error")
        with enable_error_log_bridge():
            yield mock

    def test_bridge_off_by_default_under_pytest(self, mocker):
        mock = mocker.patch.object(LoggingCore, "log_error")
        log_financial("no opt-in", tenant_id=1)
        log_security("no opt-in", tenant_id=1)
        log_exception("no opt-in", tenant_id=1)
        mock.assert_not_called()

    def test_anomaly_category_level_source_mapping(self, bridge_mock):
        log_financial("fin probe", tenant_id=7, event="gl_unbalanced_entry")
        log_security("sec probe", tenant_id=7, event="cross_tenant_attempt")
        log_hardware("hw probe", tenant_id=7, event="hardware_agent_unreachable")

        calls = bridge_mock.call_args_list
        assert [c.kwargs["category"] for c in calls] == [
            CATEGORY_CRITICAL_FINANCIAL,
            CATEGORY_SECURITY_ALERT,
            CATEGORY_HARDWARE_WARN,
        ]
        # Category defaults: financial CRITICAL, security ERROR, hardware WARNING.
        assert [c.kwargs["level"] for c in calls] == ["CRITICAL", "ERROR", "WARNING"]
        assert all(c.kwargs["source"] == "backend" for c in calls)
        assert all(c.kwargs["tenant_id"] == 7 for c in calls)
        assert calls[0].kwargs["extra"]["event"] == "gl_unbalanced_entry"
        assert calls[0].kwargs["extra"]["telemetry_category"] == CATEGORY_CRITICAL_FINANCIAL

    def test_explicit_level_wins_over_category_default(self, bridge_mock):
        log_security("severe probe", level="CRITICAL", tenant_id=1)
        assert bridge_mock.call_args.kwargs["level"] == "CRITICAL"

    def test_frontend_software_exception_mapping(self, bridge_mock):
        log_event(
            CATEGORY_SOFTWARE_EXCEPTION,
            "js crash probe",
            level="ERROR",
            tenant_id=3,
            user_id=8,
            source="frontend",
            url="http://localhost:5000/sales",
            stack="TypeError: x\n    at render (app.js:10)",
            client_ts="2026-07-26T00:00:00.000Z",
        )
        kwargs = bridge_mock.call_args.kwargs
        assert kwargs["category"] == CATEGORY_SOFTWARE_EXCEPTION
        assert kwargs["level"] == "ERROR"  # event level, not a category default
        assert kwargs["source"] == "frontend"
        assert kwargs["stack_trace"] == "TypeError: x\n    at render (app.js:10)"
        assert kwargs["url"] == "http://localhost:5000/sales"
        assert kwargs["tenant_id"] == 3
        assert kwargs["user_id"] == 8
        assert kwargs["extra"]["client_ts"] == "2026-07-26T00:00:00.000Z"
        # source/stack/url are consumed into first-class kwargs, not duplicated raw.
        assert "stack" not in kwargs["extra"]
        assert "url" not in kwargs["extra"]
        assert "source" not in kwargs["extra"]

    def test_explicit_context_wins_over_bound_context(self, bridge_mock):
        bind_context(tenant_id=1, user_id=2, request_id="rid-ctx", ip="9.9.9.9", method="PATCH")
        log_financial("ctx probe", tenant_id=99)
        kwargs = bridge_mock.call_args.kwargs
        assert kwargs["tenant_id"] == 99  # explicit beats bound
        assert kwargs["user_id"] == 2  # bound context fills the rest
        assert kwargs["request_id"] == "rid-ctx"
        assert kwargs["ip_address"] == "9.9.9.9"
        assert kwargs["method"] == "PATCH"

    def test_log_exception_carries_exception_and_event_level(self, bridge_mock):
        try:
            raise ValueError("bridged boom")
        except ValueError as exc:
            log_exception("hard failure probe", exception=exc, level="CRITICAL", tenant_id=5)
        kwargs = bridge_mock.call_args.kwargs
        assert kwargs["category"] == CATEGORY_SOFTWARE_EXCEPTION
        assert kwargs["level"] == "CRITICAL"
        assert isinstance(kwargs["exception"], ValueError)
        assert str(kwargs["exception"]) == "bridged boom"

    def test_bridge_failure_swallowed_and_jsonl_intact(self, bridge_mock, capture):
        bridge_mock.side_effect = RuntimeError("db down")
        log_security("resilient probe", tenant_id=1)  # must not raise
        entry = capture.entries[-1]
        assert entry["category"] == CATEGORY_SECURITY_ALERT
        assert entry["message"] == "resilient probe"

    def test_reentrancy_guard_blocks_recursive_bridge(self, bridge_mock):
        def _recursive(*args, **kwargs):
            log_security("recursive inner", tenant_id=1)

        bridge_mock.side_effect = _recursive
        log_security("outer probe", tenant_id=1)
        assert bridge_mock.call_count == 1

    def test_bridge_false_opt_out_skips_db(self, bridge_mock):
        log_exception("skip me", exception=None, tenant_id=1, _bridge=False)
        log_event(CATEGORY_SOFTWARE_EXCEPTION, "skip me too", tenant_id=1, _bridge=False)
        bridge_mock.assert_not_called()
