from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g

from utils.performance import (
    PerformanceMonitor,
    batch_commit,
    cache_result,
    measure_time,
    optimize_query,
)


class TestMeasureTime:
    @staticmethod
    def _time_sequence(*values):
        seq = list(values)

        def fake_time():
            return seq.pop(0) if seq else values[-1]

        return fake_time

    def test_logs_warning_for_slow_function(self):
        @measure_time
        def slow():
            return "done"

        with (
            patch(
                "utils.performance.time.time", side_effect=self._time_sequence(0.0, 1.5)
            ),
            patch("utils.performance.logger.warning") as warning,
        ):
            assert slow() == "done"
        warning.assert_called_once()

    def test_logs_info_for_medium_duration(self):
        @measure_time
        def medium():
            return 1

        with (
            patch(
                "utils.performance.time.time", side_effect=self._time_sequence(0.0, 0.6)
            ),
            patch("utils.performance.logger.info") as info,
        ):
            assert medium() == 1
        info.assert_called_once()

    def test_fast_function_returns_without_warning(self):
        @measure_time
        def fast():
            return "ok"

        with (
            patch(
                "utils.performance.time.time", side_effect=self._time_sequence(1.0, 1.1)
            ),
            patch("utils.performance.logger.warning") as warning,
            patch("utils.performance.logger.info") as info,
        ):
            assert fast() == "ok"
        warning.assert_not_called()
        info.assert_not_called()


class TestCacheResult:
    def test_cache_hit_returns_cached_value(self):
        @cache_result(timeout=30)
        def compute(x):
            return x * 2

        with (
            patch("extensions.cache.get", return_value=10),
            patch("utils.performance.logger.debug") as debug,
        ):
            assert compute(5) == 10
        debug.assert_called_once()

    def test_cache_miss_sets_value(self):
        @cache_result(timeout=45)
        def compute(x):
            return x + 1

        with (
            patch("extensions.cache.get", return_value=None),
            patch("extensions.cache.set") as set_fn,
            patch("utils.performance.logger.debug") as debug,
        ):
            assert compute(4) == 5
        set_fn.assert_called_once()
        assert set_fn.call_args.args[1] == 5
        assert set_fn.call_args.kwargs["timeout"] == 45
        debug.assert_called_once()


class TestOptimizeQuery:
    def test_returns_query_unchanged(self):
        query = MagicMock(name="query")
        assert optimize_query(query) is query


class TestBatchCommit:
    def test_commits_in_batches(self):
        items = [MagicMock(), MagicMock(), MagicMock()]
        session = MagicMock()
        with patch("extensions.db.session", session):
            batch_commit(items, batch_size=2)
        assert session.bulk_save_objects.call_count == 2
        assert session.flush.call_count == 2


class TestPerformanceMonitor:
    @pytest.fixture
    def flask_app(self):
        app = Flask(__name__)
        return app

    def test_end_request_adds_header(self, flask_app):
        with flask_app.app_context():
            g.start_time = 0.0
            response = MagicMock()
            response.headers = {}
            with patch("utils.performance.time.time", return_value=1.0):
                result = PerformanceMonitor.end_request(response)
        assert result is response
        assert response.headers["X-Response-Time"] == "1000.00ms"

    def test_end_request_warns_on_slow_request(self, flask_app):
        with flask_app.app_context():
            g.start_time = 0.0
            response = MagicMock()
            response.headers = {}
            with (
                patch("utils.performance.time.time", return_value=3.0),
                patch("utils.performance.logger.warning") as warning,
            ):
                PerformanceMonitor.end_request(response)
        warning.assert_called_once()

    def test_end_request_without_start_time_is_safe(self, flask_app):
        with flask_app.app_context():
            response = MagicMock()
            response.headers = {}
            assert PerformanceMonitor.end_request(response) is response
        assert response.headers == {}

    def test_start_request_sets_timer(self, flask_app):
        with (
            flask_app.test_request_context(),
            patch("utils.performance.time.time", return_value=12.5),
        ):
            PerformanceMonitor.start_request()
            assert g.start_time == 12.5
