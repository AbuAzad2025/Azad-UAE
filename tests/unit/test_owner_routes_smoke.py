import pytest
from app import create_app
from config import Config

@pytest.fixture(scope="module")
def smoke_app():
    class SmokeConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        WTF_CSRF_ENABLED = False
    
    app = create_app(SmokeConfig)
    return app

@pytest.fixture(scope="module")
def smoke_client(smoke_app):
    return smoke_app.test_client()

def test_routes_exist(smoke_app):
    with smoke_app.app_context():
        rules = sorted(str(r) for r in smoke_app.url_map.iter_rules())
        targets = [
            "/owner/error-audit-logs",
            "/owner/error-audit-logs/export",
            "/owner/backups/list",
            "/owner/system-health",
            "/owner/activity-monitor",
            "/owner/performance-metrics",
            "/owner/archived",
        ]
        for target in targets:
            assert any(target in r for r in rules), f"Route {target} not found"

def test_routes_no_500(smoke_client):
    targets = [
        "/owner/error-audit-logs",
        "/owner/error-audit-logs/export?format=json",
        "/owner/backups/list",
        "/owner/system-health",
        "/owner/activity-monitor",
        "/owner/performance-metrics",
        "/owner/archived",
    ]
    for target in targets:
        response = smoke_client.get(target)
        # 302 (redirect to login) or 403 (owner required) are acceptable
        assert response.status_code != 500, f"Route {target} returned 500"

def test_services_callable():
    from services.error_audit_service import ErrorAuditService
    from services.backup_service import BackupService
    from services.health_service import HealthCheckService
    from services.monitoring_service import MonitoringService
    from services.archive_service import ArchiveService
    
    checks = [
        (ErrorAuditService, ["get_logs_query", "get_dropdowns", "get_stats", "get_export_payload", "mark_resolved", "log"]),
        (BackupService, ["get_list_backups_context"]),
        (HealthCheckService, ["run_full_health_check", "get_health_data"]),
        (MonitoringService, ["get_system_health", "get_activity_monitor_context", "get_performance_metrics_data", "check_database", "get_disk_usage", "get_memory_usage", "get_cpu_usage", "log_performance_metric"]),
        (ArchiveService, ["get_archived_records_query", "get_archived_records"]),
    ]
    
    for cls, names in checks:
        for name in names:
            attr = getattr(cls, name, None)
            assert attr is not None, f"{cls.__name__}.{name} is missing"
            assert callable(attr), f"{cls.__name__}.{name} is not callable"
