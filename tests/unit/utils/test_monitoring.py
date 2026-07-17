from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g

from utils.monitoring import (
    DatabaseMonitor,
    ErrorLogger,
    HealthCheck,
    MetricsCollector,
    PerformanceMonitor,
    setup_advanced_logging,
)


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    app.config["APP_VERSION"] = "1.0.0"
    app.config["APP_ENV"] = "testing"
    app.logger = MagicMock()
    return app


class TestPerformanceMonitor:
    def test_log_request_sets_context(self, flask_app):
        with flask_app.test_request_context("/", headers={"X-Request-Id": "req-1"}):
            with patch("utils.monitoring.time.time", return_value=10.0):
                PerformanceMonitor.log_request()
            assert g.start_time == 10.0
            assert g.request_id == "req-1"

    def test_log_response_warns_on_slow_request(self, flask_app):
        response = MagicMock(status_code=200)
        with flask_app.test_request_context("/", headers={"User-Agent": "pytest"}):
            g.start_time = 0.0
            with patch("utils.monitoring.time.time", return_value=1.5):
                result = PerformanceMonitor.log_response(response)
        assert result is response
        flask_app.logger.warning.assert_called_once()
        payload = json.loads(
            flask_app.logger.warning.call_args.args[0].split(": ", 1)[1]
        )
        assert payload["method"] == "GET"
        assert payload["status"] == 200

    def test_log_response_info_for_medium_request(self, flask_app):
        response = MagicMock(status_code=201)
        with flask_app.test_request_context("/api"):
            g.start_time = 0.0
            with patch("utils.monitoring.time.time", return_value=0.6):
                PerformanceMonitor.log_response(response)
        flask_app.logger.info.assert_called_once()

    def test_log_response_without_start_time(self, flask_app):
        response = MagicMock(status_code=204)
        with flask_app.test_request_context("/"):
            assert PerformanceMonitor.log_response(response) is response
        flask_app.logger.warning.assert_not_called()
        flask_app.logger.info.assert_not_called()

    def test_monitor_endpoint_success_and_error(self, flask_app):
        @PerformanceMonitor.monitor_endpoint
        def ok():
            return "done"

        with (
            flask_app.app_context(),
            patch("utils.monitoring.time.time", side_effect=[0.0, 0.1]),
        ):
            assert ok() == "done"
        flask_app.logger.info.assert_called()

        @PerformanceMonitor.monitor_endpoint
        def boom():
            raise ValueError("fail")

        with (
            flask_app.app_context(),
            patch("utils.monitoring.time.time", side_effect=[0.0, 0.2]),
        ):
            with pytest.raises(ValueError, match="fail"):
                boom()
        flask_app.logger.error.assert_called()


class TestDatabaseMonitor:
    def test_logs_only_slow_queries(self, flask_app):
        with flask_app.app_context():
            DatabaseMonitor.log_query("SELECT 1", 0.05)
            DatabaseMonitor.log_query("SELECT slow", 0.2)
        flask_app.logger.warning.assert_called_once()


class TestErrorLogger:
    def test_log_error_with_context_and_audit_failure(self, flask_app):
        session = MagicMock()
        with flask_app.test_request_context("/broken", method="POST"):
            g.request_id = "rid-9"
            g.user = "alice"
            with (
                patch("utils.monitoring.db.session", session),
                patch("models.audit.AuditLog", side_effect=RuntimeError("audit down")),
            ):
                ErrorLogger.log_error(ValueError("bad input"), context={"step": "save"})
        flask_app.logger.error.assert_called_once()
        session.add.assert_not_called()

    def test_log_error_persists_audit_entry(self, flask_app):
        session = MagicMock()
        audit_entry = MagicMock()
        with flask_app.test_request_context("/save", method="PUT"):
            with (
                patch("utils.monitoring.db.session", session),
                patch("models.audit.AuditLog", return_value=audit_entry),
            ):
                ErrorLogger.log_error(RuntimeError("boom"))
        session.add.assert_called_once_with(audit_entry)
        session.flush.assert_called_once()


class TestMetricsCollector:
    def test_record_metric_and_wrappers(self, flask_app):
        with flask_app.app_context():
            MetricsCollector.record_metric("custom", 42, {"region": "ae"})
            MetricsCollector.record_sale(100.0, "AED")
            MetricsCollector.record_payment(50.0, "card")
            MetricsCollector.record_stock_change(7, 3, "in")
        assert flask_app.logger.info.call_count == 4
        last_payload = json.loads(
            flask_app.logger.info.call_args.args[0].replace("METRIC: ", "")
        )
        assert last_payload["metric"] == "stock_movement"
        assert last_payload["tags"]["product_id"] == 7


class TestHealthCheck:
    def test_check_database_healthy_and_unhealthy(self):
        session = MagicMock()
        with patch("utils.monitoring.db.session", session):
            assert HealthCheck.check_database()["status"] == "healthy"
        session.execute.side_effect = RuntimeError("db down")
        with patch("utils.monitoring.db.session", session):
            result = HealthCheck.check_database()
        assert result["status"] == "unhealthy"

    def test_check_redis_paths(self):
        mock_cache = MagicMock()
        mock_cache.get.return_value = "ok"
        with patch("extensions.cache", mock_cache):
            assert HealthCheck.check_redis()["status"] == "healthy"
        mock_cache.get.return_value = "stale"
        with patch("extensions.cache", mock_cache):
            assert HealthCheck.check_redis()["status"] == "unhealthy"
        mock_cache.set.side_effect = RuntimeError("redis down")
        with patch("extensions.cache", mock_cache):
            assert HealthCheck.check_redis()["status"] == "unhealthy"

    def test_check_disk_space_paths(self):
        with patch("shutil.disk_usage", return_value=(100, 50, 50)):
            assert HealthCheck.check_disk_space()["status"] == "healthy"
        with patch("shutil.disk_usage", return_value=(100, 95, 5)):
            assert HealthCheck.check_disk_space()["status"] == "unhealthy"
        with patch("shutil.disk_usage", side_effect=OSError("disk")):
            assert HealthCheck.check_disk_space()["status"] == "unknown"

    def test_get_health_status_overall(self):
        with (
            patch.object(
                HealthCheck, "check_database", return_value={"status": "healthy"}
            ),
            patch.object(
                HealthCheck, "check_redis", return_value={"status": "healthy"}
            ),
            patch.object(
                HealthCheck, "check_disk_space", return_value={"status": "healthy"}
            ),
        ):
            assert HealthCheck.get_health_status()["status"] == "healthy"
        with (
            patch.object(
                HealthCheck, "check_database", return_value={"status": "unhealthy"}
            ),
            patch.object(
                HealthCheck, "check_redis", return_value={"status": "healthy"}
            ),
            patch.object(
                HealthCheck, "check_disk_space", return_value={"status": "healthy"}
            ),
        ):
            assert HealthCheck.get_health_status()["status"] == "unhealthy"


class TestSetupAdvancedLogging:
    def test_registers_handlers_and_routes(self, flask_app, tmp_path):
        flask_app.root_path = str(tmp_path)
        with patch("utils.monitoring.logging.FileHandler") as file_handler:
            file_handler.return_value = MagicMock()
            setup_advanced_logging(flask_app)

        with patch.object(
            HealthCheck, "get_health_status", return_value={"status": "healthy"}
        ):
            health = flask_app.test_client().get("/health")
        assert health.status_code == 200
        assert health.get_json()["status"] == "healthy"

        with patch.object(
            HealthCheck, "get_health_status", return_value={"status": "unhealthy"}
        ):
            unhealthy = flask_app.test_client().get("/health")
        assert unhealthy.status_code == 503

    def test_metrics_route_requires_owner(self, flask_app, tmp_path):
        flask_app.root_path = str(tmp_path)
        with patch("utils.monitoring.logging.FileHandler") as file_handler:
            file_handler.return_value = MagicMock()
            setup_advanced_logging(flask_app)

        owner = MagicMock()
        owner.is_authenticated = True
        owner.is_owner = True
        with (
            patch.object(
                HealthCheck,
                "get_health_status",
                return_value={"status": "unhealthy", "checks": {}},
            ),
            patch("flask_login.utils._get_user", return_value=owner),
        ):
            ok = flask_app.test_client().get("/metrics")
        assert ok.status_code == 200
        assert ok.get_json()["health"]["status"] == "unhealthy"

        guest = MagicMock()
        guest.is_authenticated = False
        with patch("flask_login.utils._get_user", return_value=guest):
            denied = flask_app.test_client().get("/metrics")
        assert denied.status_code == 403
