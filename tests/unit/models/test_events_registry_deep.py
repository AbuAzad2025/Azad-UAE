"""models/events listener-group registry deep coverage.

The per-process idempotency set is cleared by the shared models conftest
before/after every test, so calling ``register_all_listeners`` twice inside a
single test deterministically exercises both the first-register and the
duplicate-skip branches of every group.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from models.events import (
    _LISTENER_GROUPS_REGISTERED,
    _log_audit_failure,
    _mark,
    _write_audit_delete_row,
    register_advanced_sale_listener,
    register_all_listeners,
)


class TestListenerGroupRegistry:
    def test_first_call_marks_true(self):
        assert _mark("probe-unique-a") is True

    def test_second_call_skips_and_logs(self, caplog):
        _mark("probe-unique-b")
        with caplog.at_level(logging.INFO):
            assert _mark("probe-unique-b") is False
        assert any("already registered" in r.message for r in caplog.records)


class TestRegisterAllListenersMatrix:
    def test_double_registration_covers_every_group_branch(self):
        register_all_listeners()  # all groups: _mark True path
        # AI listeners stay disabled by default (skip branch already covered);
        # duplicate call drives every `if not _mark(...)` early return.
        register_all_listeners()
        assert "sale" in _LISTENER_GROUPS_REGISTERED

    def test_ai_enabled_warning_path(self, mocker):
        import pytest

        mocker.patch("models.events.ai_orm_listeners_enabled", return_value=True)
        ai = mocker.patch("services.events_ai_service.register_ai_event_listeners")
        neural = mocker.patch("services.events_ai_service.register_neural_event_listeners")
        with pytest.warns(RuntimeWarning):
            register_all_listeners()
        ai.assert_called_once()
        neural.assert_called_once()

    def test_automatic_gl_listeners_skip_logged(self, caplog):
        from models.events import register_automatic_gl_listeners

        with caplog.at_level(logging.INFO):
            register_automatic_gl_listeners()
        assert any("Automatic GL listeners skipped" in r.message for r in caplog.records)

    def test_legacy_advanced_sale_listener_disabled(self, caplog, monkeypatch):
        import models.events as ev

        monkeypatch.setattr(ev, "_ADVANCED_SALE_LISTENER_ALLOWED", False)
        with caplog.at_level(logging.WARNING):
            register_advanced_sale_listener()
        assert any("legacy/disabled" in r.message for r in caplog.records)


class TestAuditDeleteRowWriter:
    def _connection(self, failing=False):
        conn = MagicMock()
        if failing:
            conn.begin_nested.side_effect = RuntimeError("savepoint boom")
        return conn

    def test_writes_audit_row_on_same_transaction(self, caplog):
        target = MagicMock(tenant_id=7, id=42, sale_number="S-1")
        conn = self._connection()
        with caplog.at_level(logging.DEBUG):
            _write_audit_delete_row(conn, target, "sales", "S-1")
        assert conn.execute.called
        ctx = conn.begin_nested.call_args
        assert ctx is not None

    def test_failure_never_breaks_request(self, caplog):
        target = MagicMock(tenant_id=7, id=42)
        conn = self._connection(failing=True)
        with caplog.at_level(logging.ERROR):
            _write_audit_delete_row(conn, target, "purchases", None)
        assert any("audit row insert failed" in r.message for r in caplog.records)


class TestLogAuditFailure:
    def test_delivered_via_current_app_logger(self, caplog, app):
        with app.app_context(), caplog.at_level(logging.ERROR):
            _log_audit_failure("app-context message")
        assert any("app-context message" in r.message for r in caplog.records)

    def test_falls_back_to_module_logger_outside_app_context(self, caplog, mocker):
        mocker.patch("models.events.logger.error")
        # Force the inner `has_app_context` to report False so delivery via
        # current_app is skipped and the module logger fallback fires.
        fake_has_ctx = mocker.patch("flask.has_app_context", return_value=False)
        _log_audit_failure("fallback message")
        fake_has_ctx.assert_called()

    def test_current_app_logger_exception_still_logs(self, mocker):
        module_logger = mocker.patch("models.events.logger.error")
        mocker.patch("flask.has_app_context", return_value=True)
        broken = mocker.patch("flask.current_app")
        type(broken).logger = property(lambda s: (_ for _ in ()).throw(RuntimeError("no logger")))
        _log_audit_failure("boom path")
        module_logger.assert_called_once()
