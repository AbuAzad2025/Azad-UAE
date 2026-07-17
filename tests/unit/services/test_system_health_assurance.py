"""Health + monitoring services — DB/Redis checks, stats, thresholds."""

from __future__ import annotations

from unittest.mock import MagicMock, mock_open


class TestHealthCheckService:
    """HealthCheckService — component checks and overall aggregation."""

    def test_check_database_healthy(self, mocker):
        mocker.patch("services.health_service.db.session").execute.return_value = None
        from services.health_service import HealthCheckService

        assert HealthCheckService.check_database()["status"] == "healthy"

    def test_check_database_unhealthy_on_error(self, mocker):
        mocker.patch("services.health_service.db.session").execute.side_effect = (
            RuntimeError("down")
        )
        from services.health_service import HealthCheckService

        assert HealthCheckService.check_database()["status"] == "unhealthy"

    def test_check_nowpayments_warning_without_vault(self, mocker):
        mocker.patch("models.PaymentVault.get_platform_vault", return_value=None)
        from services.health_service import HealthCheckService

        assert HealthCheckService.check_nowpayments()["status"] == "warning"

    def test_check_nowpayments_healthy_when_configured(self, mocker):
        vault = MagicMock(nowpayments_api_key="k", bitcoin_address="addr")
        mocker.patch("models.PaymentVault.get_platform_vault", return_value=vault)
        from services.health_service import HealthCheckService

        assert HealthCheckService.check_nowpayments()["status"] == "healthy"

    def test_check_system_resources_warning_threshold(self, mocker):
        mocker.patch("services.health_service.psutil.cpu_percent", return_value=95)
        mocker.patch(
            "services.health_service.psutil.virtual_memory"
        ).return_value.percent = 50
        mocker.patch(
            "services.health_service.psutil.disk_usage"
        ).return_value.percent = 50
        from services.health_service import HealthCheckService

        result = HealthCheckService.check_system_resources()
        assert result["status"] == "warning"
        assert result["warnings"]

    def test_run_full_health_check_overall_unhealthy(self, mocker):
        mocker.patch(
            "services.health_service.HealthCheckService.check_database",
            return_value={"status": "unhealthy"},
        )
        mocker.patch(
            "services.health_service.HealthCheckService.check_nowpayments",
            return_value={"status": "healthy"},
        )
        mocker.patch(
            "services.health_service.HealthCheckService.check_encryption",
            return_value={"status": "healthy"},
        )
        mocker.patch(
            "services.health_service.HealthCheckService.check_system_resources",
            return_value={"status": "healthy"},
        )
        from services.health_service import HealthCheckService

        assert (
            HealthCheckService.run_full_health_check()["overall_status"] == "unhealthy"
        )

    def test_get_system_metrics_counts(self, mocker):
        mocker.patch("models.Donation.query").count.return_value = 1
        mocker.patch("models.PackagePurchase.query").count.return_value = 2
        mocker.patch("models.CardPayment.query").count.return_value = 3
        proc = MagicMock()
        proc.memory_info.return_value.rss = 1024 * 1024 * 50
        proc.cpu_percent.return_value = 1.0
        proc.num_threads.return_value = 4
        proc.create_time.return_value = 1_700_000_000
        mocker.patch("services.health_service.psutil.Process", return_value=proc)
        from services.health_service import HealthCheckService

        metrics = HealthCheckService.get_system_metrics()
        assert metrics["database"]["total_donations"] == 1


class TestMonitoringService:
    """MonitoringService — stats context, activity, performance log."""

    def test_sensitive_table_blocked(self):
        from services.monitoring_service import MonitoringService

        assert MonitoringService._is_sensitive_stats_table("users") is True
        assert MonitoringService._is_sensitive_stats_table("products") is False

    def test_resolve_known_table_rejects_invalid(self, mocker):
        mocker.patch("sqlalchemy.inspect").return_value.get_table_names.return_value = [
            "sales"
        ]
        from services.monitoring_service import MonitoringService

        assert MonitoringService._resolve_known_table("sales") == "sales"
        assert MonitoringService._resolve_known_table("../bad") is None

    def test_get_system_stats_context_skips_sensitive(self, mocker):
        row_sales = MagicMock()
        row_sales.__getitem__ = lambda _self, i: "sales"
        row_users = MagicMock()
        row_users.__getitem__ = lambda _self, i: "users"
        mocker.patch(
            "services.monitoring_service.db.session"
        ).execute.return_value.fetchall.return_value = [
            row_sales,
            row_users,
        ]
        mocker.patch(
            "services.monitoring_service.MonitoringService.log_system_stats_action",
        )
        from services.monitoring_service import MonitoringService

        stats, restricted = MonitoringService.get_system_stats_context(
            MonitoringService._resolve_known_table,
            MonitoringService._is_sensitive_stats_table,
        )
        assert restricted == 1
        assert "sales" in stats

    def test_get_activity_monitor_context_branch_filter(self, mocker):
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = []
        mocker.patch("services.monitoring_service.AuditLog.query", mock_q)
        mocker.patch(
            "services.monitoring_service.User.query"
        ).filter.return_value.all.return_value = []
        mocker.patch("services.monitoring_service.Sale.query").filter.return_value = (
            mock_q
        )

        from services.monitoring_service import MonitoringService

        ctx = MonitoringService.get_activity_monitor_context(tid=1, scoped_branch_id=5)
        assert ctx["stats"]["active_now"] == 0

    def test_get_performance_metrics_reads_slow_lines(self, mocker):
        mocker.patch("services.monitoring_service.os.path.exists", return_value=True)
        mocker.patch(
            "builtins.open",
            mock_open(read_data="ok\nSLOW query took 2s\n"),
        )
        from services.monitoring_service import MonitoringService

        data = MonitoringService.get_performance_metrics_data()
        assert data["slow_queries_count"] == 1

    def test_get_system_health_aggregates(self, mocker):
        mocker.patch(
            "services.monitoring_service.MonitoringService.check_database",
            return_value={"healthy": True},
        )
        mocker.patch(
            "services.monitoring_service.MonitoringService.get_disk_usage",
            return_value={"healthy": True},
        )
        mocker.patch(
            "services.monitoring_service.MonitoringService.get_memory_usage",
            return_value={"healthy": True},
        )
        mocker.patch(
            "services.monitoring_service.MonitoringService.get_cpu_usage",
            return_value={"healthy": True},
        )
        from services.monitoring_service import MonitoringService

        assert MonitoringService.get_system_health()["status"] == "healthy"
