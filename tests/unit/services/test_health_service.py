from __future__ import annotations

from datetime import datetime

from unittest.mock import MagicMock

from services.health_service import HealthCheckService


class TestCheckDatabase:
    def test_healthy_connection(self, mocker):
        mocker.patch("services.health_service.db.session.execute")
        result = HealthCheckService.check_database()
        assert result["status"] == "healthy"

    def test_unhealthy_connection(self, mocker):
        mocker.patch(
            "services.health_service.db.session.execute",
            side_effect=RuntimeError("connection refused"),
        )
        result = HealthCheckService.check_database()
        assert result["status"] == "unhealthy"
        assert "connection refused" in result["message"]


class TestCheckNowpayments:
    def test_no_vault_warning(self, mocker):
        mocker.patch(
            "services.health_service.PaymentVault.get_platform_vault", return_value=None
        )
        result = HealthCheckService.check_nowpayments()
        assert result["status"] == "warning"

    def test_fully_configured(self, mocker):
        vault = MagicMock(nowpayments_api_key="key", bitcoin_address="addr")
        mocker.patch(
            "services.health_service.PaymentVault.get_platform_vault",
            return_value=vault,
        )
        result = HealthCheckService.check_nowpayments()
        assert result["status"] == "healthy"

    def test_partial_configuration_warning(self, mocker):
        vault = MagicMock(nowpayments_api_key="key", bitcoin_address=None)
        mocker.patch(
            "services.health_service.PaymentVault.get_platform_vault",
            return_value=vault,
        )
        result = HealthCheckService.check_nowpayments()
        assert result["status"] == "warning"

    def test_exception_unhealthy(self, mocker):
        mocker.patch(
            "services.health_service.PaymentVault.get_platform_vault",
            side_effect=RuntimeError("vault error"),
        )
        result = HealthCheckService.check_nowpayments()
        assert result["status"] == "unhealthy"


class TestCheckEncryption:
    def test_encryption_healthy(self, mocker):
        mocker.patch("werkzeug.security.generate_password_hash", return_value="hash")
        result = HealthCheckService.check_encryption()
        assert result["status"] == "healthy"

    def test_encryption_failure(self, mocker):
        mocker.patch("werkzeug.security.generate_password_hash", return_value=None)
        result = HealthCheckService.check_encryption()
        assert result["status"] == "unhealthy"

    def test_encryption_exception(self, mocker):
        mocker.patch(
            "werkzeug.security.generate_password_hash",
            side_effect=RuntimeError("crypto down"),
        )
        result = HealthCheckService.check_encryption()
        assert result["status"] == "unhealthy"


class TestCheckSystemResources:
    def test_healthy_resources(self, mocker):
        mocker.patch("services.health_service.psutil.cpu_percent", return_value=10.0)
        mocker.patch(
            "services.health_service.psutil.virtual_memory",
            return_value=MagicMock(percent=20.0),
        )
        mocker.patch(
            "services.health_service.psutil.disk_usage",
            return_value=MagicMock(percent=30.0),
        )
        result = HealthCheckService.check_system_resources()
        assert result["status"] == "healthy"
        assert result["warnings"] is None

    def test_high_cpu_warning(self, mocker):
        mocker.patch("services.health_service.psutil.cpu_percent", return_value=95.0)
        mocker.patch(
            "services.health_service.psutil.virtual_memory",
            return_value=MagicMock(percent=20.0),
        )
        mocker.patch(
            "services.health_service.psutil.disk_usage",
            return_value=MagicMock(percent=30.0),
        )
        result = HealthCheckService.check_system_resources()
        assert result["status"] == "warning"
        assert any("CPU" in w for w in result["warnings"])

    def test_high_memory_warning(self, mocker):
        mocker.patch("services.health_service.psutil.cpu_percent", return_value=10.0)
        mocker.patch(
            "services.health_service.psutil.virtual_memory",
            return_value=MagicMock(percent=95.0),
        )
        mocker.patch(
            "services.health_service.psutil.disk_usage",
            return_value=MagicMock(percent=30.0),
        )
        result = HealthCheckService.check_system_resources()
        assert result["status"] == "warning"

    def test_low_disk_warning(self, mocker):
        mocker.patch("services.health_service.psutil.cpu_percent", return_value=10.0)
        mocker.patch(
            "services.health_service.psutil.virtual_memory",
            return_value=MagicMock(percent=20.0),
        )
        mocker.patch(
            "services.health_service.psutil.disk_usage",
            return_value=MagicMock(percent=95.0),
        )
        result = HealthCheckService.check_system_resources()
        assert result["status"] == "warning"

    def test_psutil_exception(self, mocker):
        mocker.patch(
            "services.health_service.psutil.cpu_percent", side_effect=OSError("psutil")
        )
        result = HealthCheckService.check_system_resources()
        assert result["status"] == "unknown"


class TestGetSystemMetrics:
    def test_returns_metrics(self, mocker):
        proc = MagicMock()
        proc.memory_info.return_value = MagicMock(rss=1048576)
        proc.cpu_percent.return_value = 1.0
        proc.num_threads.return_value = 4
        proc.create_time.return_value = datetime.now().timestamp()
        mocker.patch("services.health_service.psutil.Process", return_value=proc)
        result = HealthCheckService.get_system_metrics()
        assert "database" in result
        assert "process" in result
        assert "timestamp" in result

    def test_metrics_error(self, mocker):
        mocker.patch(
            "services.health_service.psutil.Process", side_effect=RuntimeError("proc")
        )
        result = HealthCheckService.get_system_metrics()
        assert "error" in result


class TestRunFullHealthCheck:
    def test_overall_healthy(self, mocker):
        mocker.patch.object(
            HealthCheckService, "check_database", return_value={"status": "healthy"}
        )
        mocker.patch.object(
            HealthCheckService, "check_nowpayments", return_value={"status": "healthy"}
        )
        mocker.patch.object(
            HealthCheckService, "check_encryption", return_value={"status": "healthy"}
        )
        mocker.patch.object(
            HealthCheckService,
            "check_system_resources",
            return_value={"status": "healthy"},
        )
        result = HealthCheckService.run_full_health_check()
        assert result["overall_status"] == "healthy"

    def test_overall_warning(self, mocker):
        mocker.patch.object(
            HealthCheckService, "check_database", return_value={"status": "healthy"}
        )
        mocker.patch.object(
            HealthCheckService, "check_nowpayments", return_value={"status": "warning"}
        )
        mocker.patch.object(
            HealthCheckService, "check_encryption", return_value={"status": "healthy"}
        )
        mocker.patch.object(
            HealthCheckService,
            "check_system_resources",
            return_value={"status": "healthy"},
        )
        result = HealthCheckService.run_full_health_check()
        assert result["overall_status"] == "warning"

    def test_overall_unhealthy(self, mocker):
        mocker.patch.object(
            HealthCheckService, "check_database", return_value={"status": "unhealthy"}
        )
        mocker.patch.object(
            HealthCheckService, "check_nowpayments", return_value={"status": "warning"}
        )
        mocker.patch.object(
            HealthCheckService, "check_encryption", return_value={"status": "healthy"}
        )
        mocker.patch.object(
            HealthCheckService,
            "check_system_resources",
            return_value={"status": "healthy"},
        )
        result = HealthCheckService.run_full_health_check()
        assert result["overall_status"] == "unhealthy"


class TestGetHealthData:
    def test_health_data_structure(self, mocker, app):
        mocker.patch.object(
            HealthCheckService,
            "check_system_resources",
            return_value={"cpu_percent": 10, "memory_percent": 20, "disk_percent": 30},
        )
        size_result = MagicMock()
        size_result.scalar.return_value = 1048576
        mocker.patch(
            "services.health_service.db.session.execute", return_value=size_result
        )
        mocker.patch(
            "services.health_service.psutil.virtual_memory",
            return_value=MagicMock(total=8e9, used=4e9),
        )
        mocker.patch(
            "services.health_service.psutil.disk_usage",
            return_value=MagicMock(total=100e9, used=50e9, free=50e9),
        )
        user_query = MagicMock()
        user_query.filter.return_value.scalar.return_value = 3
        mocker.patch(
            "services.health_service.db.session.query", return_value=user_query
        )

        with app.app_context():
            data = HealthCheckService.get_health_data()

        assert data["cpu"]["percent"] == 10
        assert data["active_users"] == 3
        assert "system" in data

    def test_health_data_db_size_fallback(self, mocker, app):
        mocker.patch.object(
            HealthCheckService,
            "check_system_resources",
            return_value={"cpu_percent": 10, "memory_percent": 20, "disk_percent": 30},
        )
        mocker.patch(
            "services.health_service.db.session.execute",
            side_effect=RuntimeError("not postgres"),
        )
        mocker.patch(
            "services.health_service.psutil.virtual_memory",
            return_value=MagicMock(total=8e9, used=4e9),
        )
        mocker.patch(
            "services.health_service.psutil.disk_usage",
            return_value=MagicMock(total=100e9, used=50e9, free=50e9),
        )
        user_query = MagicMock()
        user_query.filter.return_value.scalar.side_effect = RuntimeError("users")
        mocker.patch(
            "services.health_service.db.session.query", return_value=user_query
        )

        with app.app_context():
            data = HealthCheckService.get_health_data()

        assert data["database"]["size_mb"] == 0
        assert data["active_users"] == 0
