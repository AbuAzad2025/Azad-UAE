"""Coverage-99 boost for routes/owner/monitoring.py (all 19 endpoints)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def owner_client(app_factory, bypass_owner_auth):
    from routes.owner import owner_bp

    app = app_factory(owner_bp)
    return app.test_client()


def _pagination(items=None):
    p = MagicMock()
    p.items = items or []
    return p


class TestHealthAndActivity:
    def test_system_health_ok(self, owner_client):
        with (
            patch(
                "services.health_service.HealthCheckService.get_health_data",
                return_value={"ok": True},
            ),
            patch("routes.owner.monitoring.render_template", return_value="ok"),
        ):
            assert owner_client.get("/owner/system-health").status_code == 200

    def test_system_health_error(self, owner_client):
        with patch(
            "services.health_service.HealthCheckService.get_health_data",
            side_effect=RuntimeError("down"),
        ):
            assert owner_client.get("/owner/system-health").status_code in (200, 302)

    def test_activity_monitor(self, owner_client):
        ctx = {"recent_audits": [], "active_users": [], "recent_sales": [], "stats": {}}
        with (
            patch("services.logging_core.LoggingCore.get_activity_context", return_value=ctx),
            patch("routes.owner.monitoring.render_template", return_value="ok"),
        ):
            assert owner_client.get("/owner/activity-monitor").status_code == 200

    def test_login_history(self, owner_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.login_history_pagination",
                return_value=_pagination(),
            ),
            patch(
                "services.owner_ops_service.OwnerOpsService.login_history_users",
                return_value=[],
            ),
            patch(
                "services.owner_ops_service.OwnerOpsService.login_history_stats",
                return_value={},
            ),
            patch("routes.owner.monitoring.render_template", return_value="ok"),
        ):
            resp = owner_client.get("/owner/login-history?page=2&user_id=1&success=true")
        assert resp.status_code == 200

    def test_performance_metrics(self, owner_client):
        with (
            patch(
                "services.logging_core.LoggingCore.get_performance_metrics_data",
                return_value={},
            ),
            patch("routes.owner.monitoring.render_template", return_value="ok"),
        ):
            assert owner_client.get("/owner/performance-metrics").status_code == 200


class TestSecurityAlerts:
    def test_list(self, owner_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.security_alerts_pagination",
                return_value=_pagination(),
            ),
            patch(
                "services.owner_ops_service.OwnerOpsService.security_alert_stats",
                return_value={},
            ),
            patch("routes.owner.monitoring.render_template", return_value="ok"),
        ):
            assert owner_client.get("/owner/security-alerts?severity=high").status_code == 200

    def test_resolve_ok(self, owner_client):
        alert = MagicMock()
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_security_alert_or_404",
                return_value=alert,
            ),
            patch("routes.owner.monitoring.db.session"),
        ):
            assert owner_client.post("/owner/security-alerts/1/resolve").status_code in (
                200,
                302,
            )

    def test_resolve_error(self, owner_client):
        alert = MagicMock()
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_security_alert_or_404",
                return_value=alert,
            ),
            patch(
                "routes.owner.monitoring.db.session.commit",
                side_effect=RuntimeError("db gone"),
            ),
        ):
            assert owner_client.post("/owner/security-alerts/1/resolve").status_code in (
                200,
                302,
            )


class TestIpWhitelist:
    def test_get(self, owner_client):
        settings = MagicMock(owner_whitelist_ips=[{"ip": "1.1.1.1"}])
        with (
            patch("routes.owner.monitoring.SystemSettings.get_current", return_value=settings),
            patch("routes.owner.monitoring.render_template", return_value="ok"),
        ):
            assert owner_client.get("/owner/ip-whitelist").status_code == 200

    def test_post_ok(self, owner_client):
        settings = MagicMock(owner_whitelist_ips=[])
        with (
            patch("routes.owner.monitoring.SystemSettings.get_current", return_value=settings),
            patch("routes.owner.monitoring.db.session"),
        ):
            resp = owner_client.post("/owner/ip-whitelist", data={"ip_address": "2.2.2.2", "description": "office"})
        assert resp.status_code in (200, 302)

    def test_post_error(self, owner_client):
        settings = MagicMock(owner_whitelist_ips=[])
        with (
            patch("routes.owner.monitoring.SystemSettings.get_current", return_value=settings),
            patch("routes.owner.monitoring.db.session.commit", side_effect=RuntimeError("x")),
        ):
            resp = owner_client.post("/owner/ip-whitelist", data={"ip_address": "3.3.3.3"})
        assert resp.status_code in (200, 302)

    def test_delete_valid_index(self, owner_client):
        settings = MagicMock(owner_whitelist_ips=[{"ip": "1.1.1.1"}])
        with (
            patch("routes.owner.monitoring.SystemSettings.get_current", return_value=settings),
            patch("routes.owner.monitoring.db.session"),
        ):
            assert owner_client.post("/owner/ip-whitelist/0/delete").status_code in (200, 302)

    def test_delete_out_of_range(self, owner_client):
        settings = MagicMock(owner_whitelist_ips=[])
        with patch("routes.owner.monitoring.SystemSettings.get_current", return_value=settings):
            assert owner_client.post("/owner/ip-whitelist/9/delete").status_code in (200, 302)

    def test_delete_error(self, owner_client):
        settings = MagicMock(owner_whitelist_ips=[{"ip": "1.1.1.1"}])
        with (
            patch("routes.owner.monitoring.SystemSettings.get_current", return_value=settings),
            patch("routes.owner.monitoring.db.session.commit", side_effect=RuntimeError("x")),
        ):
            assert owner_client.post("/owner/ip-whitelist/0/delete").status_code in (200, 302)


class TestApiKeys:
    def test_get(self, owner_client):
        with (
            patch("services.owner_ops_service.OwnerOpsService.list_api_keys", return_value=[]),
            patch("routes.owner.monitoring.render_template", return_value="ok"),
        ):
            assert owner_client.get("/owner/api-keys").status_code == 200

    def test_post_ok(self, owner_client):
        with (
            patch("routes.owner.monitoring.APIKey") as key_cls,
            patch("routes.owner.monitoring.db.session"),
        ):
            key_cls.generate_key.return_value = "k" * 16
            key_cls.return_value = MagicMock(key="k" * 16)
            resp = owner_client.post("/owner/api-keys", data={"name": "n", "service": "s"})
        assert resp.status_code in (200, 302)

    def test_post_error(self, owner_client):
        with (
            patch("routes.owner.monitoring.APIKey") as key_cls,
            patch("routes.owner.monitoring.db.session.commit", side_effect=RuntimeError("x")),
        ):
            key_cls.generate_key.return_value = "k" * 16
            key_cls.return_value = MagicMock(key="k" * 16)
            resp = owner_client.post("/owner/api-keys", data={"name": "n", "service": "s"})
        assert resp.status_code in (200, 302)

    def test_toggle_on_off(self, owner_client):
        key = MagicMock(is_active=True)
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_api_key_or_404",
                return_value=key,
            ),
            patch("routes.owner.monitoring.db.session"),
        ):
            assert owner_client.post("/owner/api-keys/1/toggle").status_code in (200, 302)

    def test_toggle_error(self, owner_client):
        key = MagicMock(is_active=False)
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_api_key_or_404",
                return_value=key,
            ),
            patch("routes.owner.monitoring.db.session.commit", side_effect=RuntimeError("x")),
        ):
            assert owner_client.post("/owner/api-keys/1/toggle").status_code in (200, 302)


class TestDashboards:
    def _check(self, owner_client, url, service, method, ret):
        with (
            patch(f"{service}.{method}", return_value=ret),
            patch("routes.owner.monitoring.get_active_tenant_id", return_value=1),
            patch("routes.owner.monitoring._owner_branch_scope", return_value=None),
            patch("routes.owner.monitoring.render_template", return_value="ok"),
        ):
            assert owner_client.get(url).status_code == 200

    def test_financial_dashboard(self, owner_client):
        self._check(
            owner_client,
            "/owner/financial-dashboard-advanced",
            "services.financial_service.FinancialService",
            "get_financial_dashboard_advanced_context",
            {"months_data": [], "kpis": {}},
        )

    def test_sales_insights(self, owner_client):
        self._check(
            owner_client,
            "/owner/sales-insights",
            "services.analytics_service.AnalyticsService",
            "get_sales_insights",
            {},
        )

    def test_customer_insights(self, owner_client):
        self._check(
            owner_client,
            "/owner/customer-insights",
            "services.analytics_service.AnalyticsService",
            "get_customer_insights",
            [],
        )

    def test_product_performance(self, owner_client):
        self._check(
            owner_client,
            "/owner/product-performance",
            "services.analytics_service.AnalyticsService",
            "get_product_performance",
            [],
        )

    def test_forecasting(self, owner_client):
        self._check(
            owner_client,
            "/owner/forecasting",
            "services.analytics_service.AnalyticsService",
            "get_forecasting_data",
            ([], []),
        )


class TestErrorLogs:
    def _log(self, with_user=True):
        from datetime import datetime

        log = MagicMock()
        log.id = 1
        log.user_id = 7 if with_user else None
        log.category = "c"
        log.level = "error"
        log.source = "s"
        log.fingerprint = None
        log.occurrence_count = None
        log.first_seen_at = datetime(2024, 1, 1)
        log.last_seen_at = None
        log.request_id = None
        log.environment = None
        log.app_version = None
        log.url = None
        log.method = None
        log.ip_address = None
        log.tenant_id = 1
        log.message = "m"
        log.exception_type = None
        log.stack_trace = None
        log.request_data = {"a": 1}
        return log

    def test_list_with_users(self, owner_client):
        user = MagicMock()
        user.id = 7
        user.get_display_name.return_value = None
        user.username = "u7"
        with (
            patch(
                "services.logging_core.LoggingCore.get_error_logs",
                return_value=([self._log(True), self._log(False)], _pagination(), [], [], [], {}),
            ),
            patch(
                "services.owner_ops_service.OwnerOpsService.get_users_by_ids",
                return_value=[user],
            ),
            patch("routes.owner.monitoring.render_template", return_value="ok"),
        ):
            resp = owner_client.get("/owner/error-audit-logs?category=c&search=m")
        assert resp.status_code == 200

    def test_resolve_ok(self, owner_client):
        with patch("services.logging_core.LoggingCore.mark_error_resolved", return_value=True):
            assert owner_client.post("/owner/error-audit-logs/1/resolve").status_code in (
                200,
                302,
            )

    def test_resolve_fail(self, owner_client):
        with patch("services.logging_core.LoggingCore.mark_error_resolved", return_value=False):
            assert owner_client.post("/owner/error-audit-logs/1/resolve").status_code in (
                200,
                302,
            )

    def test_export_ok(self, owner_client):
        with patch(
            "services.logging_core.LoggingCore.export_error_logs",
            return_value=("{}", "application/json", "logs.json"),
        ):
            resp = owner_client.get("/owner/error-audit-logs/export?format=json")
        assert resp.status_code == 200

    def test_export_error(self, owner_client):
        with patch(
            "services.logging_core.LoggingCore.export_error_logs",
            side_effect=RuntimeError("bad fmt"),
        ):
            assert owner_client.get("/owner/error-audit-logs/export").status_code in (
                200,
                302,
            )

    def test_clear_ok(self, owner_client):
        with (
            patch("services.logging_core.LoggingCore.clear_all_error_logs", return_value=3),
            patch("routes.owner.monitoring.db.session"),
        ):
            assert owner_client.post("/owner/error-audit-logs/clear").status_code in (200, 302)

    def test_clear_error(self, owner_client):
        with patch(
            "services.logging_core.LoggingCore.clear_all_error_logs",
            side_effect=RuntimeError("x"),
        ):
            assert owner_client.post("/owner/error-audit-logs/clear").status_code in (200, 302)
