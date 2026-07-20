from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.unit.routes.conftest import (
    unauthenticated_client,
)


@pytest.fixture
def monitoring_client(app_factory, bypass_admin_auth):
    from routes.monitoring import monitoring_bp

    app = app_factory(monitoring_bp)
    return app.test_client()


class TestMonitoringHealth:
    def test_health_healthy(self, monitoring_client):
        with patch(
            "routes.monitoring.LoggingCore.get_system_health",
            return_value={"status": "healthy"},
        ):
            resp = monitoring_client.get("/monitoring/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "healthy"

    def test_health_unhealthy(self, monitoring_client):
        with patch(
            "routes.monitoring.LoggingCore.get_system_health",
            return_value={"status": "degraded"},
        ):
            resp = monitoring_client.get("/monitoring/health")
        assert resp.status_code == 503

    def test_health_no_auth_required(self, monitoring_client):
        with (
            unauthenticated_client(monitoring_client),
            patch(
                "routes.monitoring.LoggingCore.get_system_health",
                return_value={"status": "healthy"},
            ),
        ):
            resp = monitoring_client.get("/monitoring/health")
        assert resp.status_code == 200


class TestMonitoringMetrics:
    def test_metrics_json(self, monitoring_client):
        with patch(
            "routes.monitoring.LoggingCore.get_app_metrics",
            return_value={"requests": 10},
        ):
            resp = monitoring_client.get("/monitoring/metrics")
        assert resp.status_code == 200
        assert resp.get_json()["requests"] == 10

    def test_metrics_requires_login(self, monitoring_client):
        with unauthenticated_client(monitoring_client):
            resp = monitoring_client.get("/monitoring/metrics")
        assert resp.status_code == 401

    def test_metrics_requires_admin(self, monitoring_client, mock_user):
        with patch("utils.decorators.is_admin_surface_user", return_value=False):
            resp = monitoring_client.get("/monitoring/metrics")
        assert resp.status_code == 403


class TestMonitoringDashboard:
    def test_dashboard_renders(self, monitoring_client):
        with (
            patch(
                "routes.monitoring.LoggingCore.get_system_health",
                return_value={"status": "healthy"},
            ),
            patch("routes.monitoring.LoggingCore.get_app_metrics", return_value={"cpu": 1}),
            patch("routes.monitoring.render_template", return_value="ok") as render,
        ):
            resp = monitoring_client.get("/monitoring/dashboard")
        assert resp.status_code == 200
        render.assert_called_once()
        assert render.call_args[0][0] == "monitoring/dashboard.html"

    def test_dashboard_unauthenticated(self, monitoring_client):
        with unauthenticated_client(monitoring_client):
            resp = monitoring_client.get("/monitoring/dashboard")
        assert resp.status_code == 401
