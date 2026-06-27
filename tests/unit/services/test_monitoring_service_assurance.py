from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.monitoring_service import MonitoringService


class TestSensitiveTableHelpers:
    @pytest.mark.parametrize('name,sensitive', [
        ('users', True),
        ('products', False),
        ('', False),
    ])
    def test_is_sensitive_stats_table(self, name, sensitive):
        assert MonitoringService._is_sensitive_stats_table(name) is sensitive

    def test_resolve_known_table_valid(self, mocker):
        inspector = MagicMock()
        inspector.get_table_names.return_value = ['Products', 'sales']
        mocker.patch('sqlalchemy.inspect', return_value=inspector)
        assert MonitoringService._resolve_known_table('sales') == 'sales'

    def test_resolve_known_table_invalid_name(self):
        assert MonitoringService._resolve_known_table('bad-name!') is None

    def test_resolve_known_table_empty(self):
        assert MonitoringService._resolve_known_table('') is None


class TestLogSystemStatsAction:
    def test_commits_audit_log(self, mocker):
        session = mocker.patch('services.monitoring_service.db.session')
        MonitoringService.log_system_stats_action(5, 2)
        session.add.assert_called_once()
        session.commit.assert_called_once()

    def test_rollback_on_commit_failure(self, mocker):
        session = mocker.patch('services.monitoring_service.db.session')
        session.commit.side_effect = RuntimeError('fail')
        with pytest.raises(RuntimeError):
            MonitoringService.log_system_stats_action(1, 0)
        session.rollback.assert_called_once()


class TestGetSystemStatsContext:
    def test_collects_visible_tables(self, mocker):
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [('sales',), ('users',), ('bad-name!',)]
        count_mock = MagicMock()
        count_mock.scalar.return_value = 42
        session = mocker.patch('services.monitoring_service.db.session')
        session.execute.side_effect = [result_mock, count_mock]
        mocker.patch.object(MonitoringService, 'log_system_stats_action')

        def resolve(t):
            if t == 'bad-name!':
                return None
            return t

        stats, restricted = MonitoringService.get_system_stats_context(
            resolve,
            MonitoringService._is_sensitive_stats_table,
        )
        assert 'sales' in stats
        assert 'bad-name!' not in stats
        assert restricted >= 1

    def test_swallows_db_errors(self, mocker):
        session = mocker.patch('services.monitoring_service.db.session')
        session.execute.side_effect = RuntimeError('db down')
        mocker.patch.object(MonitoringService, 'log_system_stats_action')
        stats, restricted = MonitoringService.get_system_stats_context(
            lambda t: t, lambda t: False,
        )
        assert stats == {}
        assert restricted == 0


class TestActivityMonitor:
    def test_get_activity_monitor_context(self, mocker):
        class _Col:
            def __eq__(self, other):
                return self

            def __ge__(self, other):
                return self

            def desc(self):
                return self

        audit = MagicMock()
        user = MagicMock()
        sale = MagicMock()
        audit_q = MagicMock()
        audit_q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [audit]
        user_q = MagicMock()
        user_q.filter.return_value.all.return_value = [user]
        sale_q = MagicMock()
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value.limit.return_value.all.return_value = [sale]
        audit_mod = mocker.patch('services.monitoring_service.AuditLog')
        audit_mod.query = audit_q
        audit_mod.created_at = _Col()
        user_mod = mocker.patch('services.monitoring_service.User')
        user_mod.query = user_q
        user_mod.last_seen = _Col()
        user_mod.is_active = _Col()
        user_mod.tenant_id = _Col()
        sale_mod = mocker.patch('services.monitoring_service.Sale')
        sale_mod.query = sale_q
        sale_mod.created_at = _Col()
        sale_mod.tenant_id = _Col()
        sale_mod.branch_id = _Col()
        ctx = MonitoringService.get_activity_monitor_context(1, scoped_branch_id=5)
        assert ctx['stats']['active_now'] == 1
        assert ctx['stats']['today_sales'] == 1
        assert ctx['recent_audits'] == [audit]

    def test_get_activity_monitor_no_branch_filter(self, mocker):
        class _Col:
            def __eq__(self, other):
                return self

            def __ge__(self, other):
                return self

            def desc(self):
                return self

        audit_q = MagicMock()
        audit_q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
        user_q = MagicMock()
        user_q.filter.return_value.all.return_value = []
        sale_q = MagicMock()
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value.limit.return_value.all.return_value = []
        audit_mod = mocker.patch('services.monitoring_service.AuditLog')
        audit_mod.query = audit_q
        audit_mod.created_at = _Col()
        user_mod = mocker.patch('services.monitoring_service.User')
        user_mod.query = user_q
        user_mod.last_seen = _Col()
        user_mod.is_active = _Col()
        user_mod.tenant_id = _Col()
        sale_mod = mocker.patch('services.monitoring_service.Sale')
        sale_mod.query = sale_q
        sale_mod.created_at = _Col()
        sale_mod.tenant_id = _Col()
        sale_mod.branch_id = _Col()
        ctx = MonitoringService.get_activity_monitor_context(2, scoped_branch_id=None)
        assert ctx['stats']['today_sales'] == 0


class TestPerformanceMetricsFile:
    def test_reads_slow_queries(self, mocker):
        mocker.patch('services.monitoring_service.os.path.exists', return_value=True)
        mocker.patch('builtins.open', mocker.mock_open(read_data='ok line\nSLOW query took 2s\n'))
        data = MonitoringService.get_performance_metrics_data()
        assert data['slow_queries_count'] == 1

    def test_missing_performance_file(self, mocker):
        mocker.patch('services.monitoring_service.os.path.exists', return_value=False)
        data = MonitoringService.get_performance_metrics_data()
        assert data['slow_queries_count'] == 0


class TestHealthMetrics:
    def test_check_database_healthy(self, mocker):
        session = mocker.patch('services.monitoring_service.db.session')
        result = MonitoringService.check_database()
        assert result['healthy'] is True

    def test_check_database_unhealthy(self, mocker):
        session = mocker.patch('services.monitoring_service.db.session')
        session.execute.side_effect = RuntimeError('down')
        result = MonitoringService.check_database()
        assert result['healthy'] is False

    def test_get_disk_usage(self, mocker):
        usage = MagicMock(total=1000, used=400, free=600, percent=40)
        mocker.patch('services.monitoring_service.psutil.disk_usage', return_value=usage)
        result = MonitoringService.get_disk_usage()
        assert result['healthy'] is True
        assert result['percent'] == 40

    def test_get_disk_usage_unavailable(self, mocker):
        mocker.patch('services.monitoring_service.psutil.disk_usage', side_effect=OSError())
        assert MonitoringService.get_disk_usage()['error'] == 'unavailable'

    def test_get_memory_usage(self, mocker):
        mem = MagicMock(total=8 * 1024**2, used=4 * 1024**2, percent=50)
        mocker.patch('services.monitoring_service.psutil.virtual_memory', return_value=mem)
        result = MonitoringService.get_memory_usage()
        assert result['healthy'] is True

    def test_get_memory_usage_unavailable(self, mocker):
        mocker.patch('services.monitoring_service.psutil.virtual_memory', side_effect=OSError())
        assert MonitoringService.get_memory_usage()['error'] == 'unavailable'

    def test_get_cpu_usage_unavailable(self, mocker):
        mocker.patch('services.monitoring_service.psutil.cpu_percent', side_effect=OSError())
        assert MonitoringService.get_cpu_usage()['error'] == 'unavailable'

    def test_get_cpu_usage(self, mocker):
        mocker.patch('services.monitoring_service.psutil.cpu_percent', return_value=55)
        mocker.patch('services.monitoring_service.psutil.cpu_count', return_value=4)
        result = MonitoringService.get_cpu_usage()
        assert result['cores'] == 4

    def test_get_system_health(self, mocker):
        mocker.patch.object(MonitoringService, 'check_database', return_value={'healthy': True})
        mocker.patch.object(MonitoringService, 'get_disk_usage', return_value={'healthy': True})
        mocker.patch.object(MonitoringService, 'get_memory_usage', return_value={'healthy': True})
        mocker.patch.object(MonitoringService, 'get_cpu_usage', return_value={'healthy': True})
        health = MonitoringService.get_system_health()
        assert health['status'] == 'healthy'
        assert 'timestamp' in health


class TestApplicationMetrics:
    def test_get_application_metrics_success(self, mocker):
        class _Col:
            def __eq__(self, other):
                return self

            def __le__(self, other):
                return self

        sale_q = MagicMock()
        sale_q.count.return_value = 10
        customer_q = MagicMock()
        customer_q.count.return_value = 5
        customer_q.filter_by.return_value.count.return_value = 4
        product_q = MagicMock()
        product_q.count.return_value = 20
        product_q.filter.return_value.count.return_value = 2
        sale_mod = mocker.patch('models.Sale')
        sale_mod.query = sale_q
        customer_mod = mocker.patch('models.Customer')
        customer_mod.query = customer_q
        product_mod = mocker.patch('models.Product')
        product_mod.query = product_q
        product_mod.current_stock = _Col()
        product_mod.min_stock_alert = _Col()
        metrics = MonitoringService.get_application_metrics()
        assert metrics['total_sales'] == 10
        assert metrics['low_stock_products'] == 2

    def test_get_application_metrics_error(self, mocker):
        mocker.patch('models.Sale').query.count.side_effect = RuntimeError('orm')
        metrics = MonitoringService.get_application_metrics()
        assert 'error' in metrics


class TestLogPerformanceMetric:
    def test_writes_metric_line(self, tmp_path, mocker):
        basedir = str(tmp_path)
        mocker.patch('services.monitoring_service.os.path.abspath', return_value=basedir)
        mocker.patch('services.monitoring_service.os.path.join', side_effect=os.path.join)
        mocker.patch('services.monitoring_service.os.path.dirname', return_value=basedir)
        MonitoringService.log_performance_metric('latency', 1.23, {'route': 'sales'})
        log_file = tmp_path / 'logs' / 'performance.log'
        assert log_file.exists()
        assert 'latency=1.23' in log_file.read_text(encoding='utf-8')

    def test_log_performance_metric_swallows_errors(self, mocker):
        mocker.patch('services.monitoring_service.os.makedirs', side_effect=OSError())
        MonitoringService.log_performance_metric('x', 1.0)
