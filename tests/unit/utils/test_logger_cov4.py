"""Cov4: logger (telemetry) — context, formatter, init, emitters, bridge."""

from __future__ import annotations

import logging
from unittest.mock import patch

import utils.logger as lg


def test_bind_clear_resolve():
    lg.bind_context(tenant_id=5, bogus_field=1)  # 119-124 (bogus ignored)
    assert lg._resolve({"tenant_id": 9}, "tenant_id") == 9  # 112-116 explicit
    assert lg._resolve({}, "tenant_id") == 5  # ctx fallback
    lg.clear_context()  # 127-130
    assert lg._resolve({}, "tenant_id") is None


def test_formatter_duration_paths():
    fmt = lg._TelemetryEventFormatter()
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", (), None)
    rec.telemetry_event = {"explicit": {}, "extras": {}}
    out = fmt.format(rec)  # no duration, no start
    assert "hello" in out  # 73-109
    lg.bind_context(duration_ms=12.5)
    rec2 = logging.LogRecord("t", logging.INFO, __file__, 1, "hi", (), None)
    rec2.telemetry_event = {"explicit": {}, "extras": {"k": "v"}}
    assert "hi" in fmt.format(rec2)  # 78-80
    lg.clear_context()
    lg.bind_context(request_start=__import__("time").monotonic() - 1)
    rec3 = logging.LogRecord("t", logging.INFO, __file__, 1, "hey", (), None)
    rec3.telemetry_event = {"explicit": {}, "extras": {}}
    assert "hey" in fmt.format(rec3)  # 81-86
    lg.clear_context()


def test_formatter_exc_and_extra_collision():
    fmt = lg._TelemetryEventFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        exc = sys.exc_info()
    rec = logging.LogRecord("t", logging.ERROR, __file__, 1, "fail", (), exc)
    rec.telemetry_event = {"explicit": {}, "extras": {"message": "no-override"}}
    assert "exception" in fmt.format(rec)  # 104-108


def test_init_testing_and_prod(app, tmp_path, monkeypatch):
    app.testing = True
    log = lg.init_telemetry(app)  # 260-263
    assert log is not None
    app.testing = False
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(lg, "_INSTANCE_DIR", str(tmp_path))
    log2 = lg.init_telemetry(app)  # file sink 265-273
    assert log2 is not None
    monkeypatch.setenv("FLASK_ENV", "development")
    log3 = lg.init_telemetry(app)  # 275-278 stdout
    assert log3 is not None


def test_emitters_never_raise():
    lg.log_event("X", "m1", _bridge=False, tenant_id=1, custom="v")  # 284-327
    lg.log_exception("m2", ValueError("x"), _bridge=False)  # 330-357
    lg.log_exception("m3", None, _bridge=False)
    lg.log_financial("m4", tenant_id=2)  # PYTEST env -> bridge off unless opt-in
    lg.log_security("m5")
    lg.log_hardware("m6")
    with lg.enable_error_log_bridge():  # 173-184
        assert lg._bridge_allowed() is True  # 187-190 (opt-in)


def test_bridge_recursion_and_failure():
    lg._in_bridge.set(True)
    lg._bridge_to_error_log("C", "m", event_level="INFO", bridge_level=None, exception=None, explicit={}, extras={})
    lg._in_bridge.set(False)  # 203-204 early return
    with patch("services.logging_core.LoggingCore.log_error", side_effect=RuntimeError("db")):
        lg._bridge_to_error_log(
            "C", "m", event_level="INFO", bridge_level=None, exception=None, explicit={}, extras={}
        )  # 242-244
