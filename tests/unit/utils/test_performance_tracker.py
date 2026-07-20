from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g

from utils.performance_tracker import (
    PerformanceContext,
    log_slow_queries,
    track_performance,
)


class TestTrackPerformance:
    def test_slow_operation_logs_warning(self):
        @track_performance(threshold_ms=100)
        def work():
            return "x"

        with (
            patch("utils.performance_tracker.time.time", side_effect=[0.0, 0.25, 0.25]),
            patch("utils.performance_tracker.logger.warning") as warning,
        ):
            assert work() == "x"
        warning.assert_called_once()

    def test_fast_operation_logs_debug(self):
        @track_performance(threshold_ms=500)
        def work():
            return 1

        with (
            patch("utils.performance_tracker.time.time", side_effect=[1.0, 1.01, 1.01]),
            patch("utils.performance_tracker.logger.debug") as debug,
        ):
            assert work() == 1
        debug.assert_called_once()

    def test_records_metrics_on_g(self, flask_app):
        @track_performance()
        def timed_op():
            return "ok"

        with flask_app.test_request_context():
            with patch("utils.performance_tracker.time.time", side_effect=[0.0, 0.01, 0.01]):
                assert timed_op() == "ok"
            assert g.performance_metrics["timed_op"] == pytest.approx(10.0, rel=1e-3)

    def test_appends_to_existing_metrics(self, flask_app):
        @track_performance()
        def second():
            return 2

        with flask_app.test_request_context():
            g.performance_metrics = {"first": 1.0}
            with patch("utils.performance_tracker.time.time", side_effect=[0.0, 0.02, 0.02]):
                assert second() == 2
            assert g.performance_metrics["first"] == 1.0
            assert "second" in g.performance_metrics


@pytest.fixture
def flask_app():
    return Flask(__name__)


class TestPerformanceContext:
    def test_context_manager_logs_elapsed(self):
        with (
            patch("utils.performance_tracker.time.time", side_effect=[0.0, 0.05, 0.05]),
            patch("utils.performance_tracker.logger.info") as info,
        ):
            with PerformanceContext("db-scan"):
                pass
        info.assert_called_once()


class TestLogSlowQueries:
    def test_registers_and_warns_on_slow_query(self):
        registered = {}

        def fake_listens_for(_target, identifier):
            def decorator(fn):
                registered[identifier] = fn
                return fn

            return decorator

        with patch("sqlalchemy.event.listens_for", fake_listens_for):
            log_slow_queries(MagicMock())

        before = registered["before_cursor_execute"]
        after = registered["after_cursor_execute"]
        conn = MagicMock()
        conn.info = {}

        with (
            patch("utils.performance_tracker.time.time", side_effect=[0.0, 0.2, 0.2]),
            patch("utils.performance_tracker.logger.warning") as warning,
        ):
            before(conn, None, "SELECT * FROM sales", {}, None, False)
            after(conn, None, "SELECT * FROM sales", {}, None, False)
        warning.assert_called_once()

    def test_fast_query_does_not_warn(self):
        registered = {}

        def fake_listens_for(_target, identifier):
            def decorator(fn):
                registered[identifier] = fn
                return fn

            return decorator

        with patch("sqlalchemy.event.listens_for", fake_listens_for):
            log_slow_queries(MagicMock())

        conn = MagicMock()
        conn.info = {}
        with (
            patch("utils.performance_tracker.time.time", side_effect=[1.0, 1.01, 1.01]),
            patch("utils.performance_tracker.logger.warning") as warning,
        ):
            registered["before_cursor_execute"](conn, None, "SELECT 1", {}, None, False)
            registered["after_cursor_execute"](conn, None, "SELECT 1", {}, None, False)
        warning.assert_not_called()
