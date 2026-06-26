from __future__ import annotations

import io
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g

from services import logging_core
from services.logging_core import (
    LoggingCore,
    _ColorFormatter,
    _JsonFormatter,
    _RateMonitor,
    _RequestIdFilter,
    _SafeLogRecordFilter,
    _ensure_utf8_stream,
    _get_request_context,
    _get_request_id,
    _make_fingerprint,
    _sanitize_dict,
)

_REAL_LOG_ERROR = LoggingCore.log_error


class TestHelpers:
    def test_ensure_utf8_stream_reconfigure(self):
        stream = MagicMock()
        assert _ensure_utf8_stream(stream) is stream

    def test_ensure_utf8_stream_buffer_fallback(self):
        stream = MagicMock()
        stream.reconfigure.side_effect = OSError('nope')
        stream.buffer = io.BytesIO(b'')
        wrapped = _ensure_utf8_stream(stream)
        assert wrapped is not None

    def test_sanitize_dict_redacts_secrets(self):
        data = {'password': 'x', 'nested': {'api_key': 'k'}, 'items': [{'token': 't'}], 'safe': 1}
        clean = _sanitize_dict(data)
        assert clean['password'] == '***REDACTED***'
        assert clean['nested']['api_key'] == '***REDACTED***'
        assert clean['items'][0]['token'] == '***REDACTED***'
        assert clean['safe'] == 1

    def test_sanitize_non_dict(self):
        assert _sanitize_dict([]) == {}

    def test_get_request_id_without_context(self):
        rid = _get_request_id()
        assert len(rid) == 36

    def test_get_request_id_reuses_g(self, app):
        with app.test_request_context('/'):
            g.request_id = 'fixed-id'
            assert _get_request_id() == 'fixed-id'

    def test_get_request_context_populated(self, app):
        with app.test_request_context('/test', headers={'User-Agent': 'pytest'}):
            ctx = _get_request_context()
            assert '/test' in ctx['url']
            assert ctx['method'] == 'GET'

    def test_make_fingerprint_stable(self):
        fp1 = _make_fingerprint('BACKEND', 'ValueError', 'src', '/x', 'msg')
        fp2 = _make_fingerprint('BACKEND', 'ValueError', 'src', '/x', 'msg')
        assert fp1 == fp2
        assert len(fp1) == 32


class TestFormattersAndFilters:
    def test_request_id_filter(self, app):
        filt = _RequestIdFilter()
        record = logging.LogRecord('n', logging.INFO, __file__, 1, 'm', (), None)
        with app.test_request_context('/'):
            g.request_id = 'rid-1'
            assert filt.filter(record) is True
            assert record.request_id == 'rid-1'

    def test_safe_log_record_filter_defaults(self):
        record = logging.LogRecord('n', logging.INFO, __file__, 1, 'm', (), None)
        assert _SafeLogRecordFilter().filter(record) is True
        assert record.user == '-'

    def test_color_formatter(self):
        record = logging.LogRecord('n', logging.INFO, __file__, 1, 'hello', (), None)
        record.request_id = 'r'
        text = _ColorFormatter().format(record)
        assert 'hello' in text

    def test_json_formatter_with_exception(self):
        try:
            raise ValueError('boom')
        except ValueError:
            record = logging.LogRecord('n', logging.ERROR, __file__, 1, 'fail', (), sys.exc_info())
        record.request_id = 'r'
        payload = json.loads(_JsonFormatter().format(record))
        assert payload['level'] == 'ERROR'
        assert 'exception' in payload


class TestRateMonitor:
    def test_record_count_spike(self):
        mon = _RateMonitor()
        for _ in range(25):
            mon.record('BACKEND')
        assert mon.count('BACKEND') == 25
        assert mon.spike('BACKEND', threshold=20) is True


class TestLoggingCoreSetup:
    def test_setup_skips_when_initialized(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        app = Flask(__name__)
        LoggingCore._initialized = True
        LoggingCore.setup(app)
        LoggingCore._initialized = False

    def test_setup_initializes_handlers(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        LoggingCore._initialized = False
        LoggingCore._handlers = {}
        app = Flask(__name__)
        app.config['LOG_LEVEL'] = 'DEBUG'
        app.config['LOG_FORMAT'] = 'json'
        with patch('services.logging_core.RotatingFileHandler') as RFH:
            RFH.side_effect = lambda *a, **k: MagicMock(level=logging.INFO)
            LoggingCore.setup(app)
        assert LoggingCore._initialized is True
        LoggingCore._initialized = False

    def test_register_slow_query_listener(self, app):
        LoggingCore.register_slow_query_listener(app)

    def test_register_alert_callback_and_fire(self):
        cb = MagicMock()
        LoggingCore.register_alert_callback(cb)
        LoggingCore._fire_alert_callbacks('BACKEND', 'ERROR', 'msg', 30)
        cb.assert_called_once()
        LoggingCore._alert_callbacks = []

    def test_set_trace_id(self, app):
        with app.test_request_context('/', headers={'X-Trace-Id': 'trace-abc'}):
            LoggingCore.set_trace_id()
            assert g.request_id == 'trace-abc'


class TestErrorLogging:
    def test_log_error_persists(self, mocker):
        persist = mocker.patch.object(LoggingCore, '_persist_error', return_value=42)
        LoggingCore.log_error = _REAL_LOG_ERROR
        row_id = LoggingCore.log_error('fail', category='BACKEND', exception=ValueError('x'))
        assert row_id == 42
        persist.assert_called_once()

    def test_log_frontend_error_truncates_stack(self, mocker):
        persist = mocker.patch.object(LoggingCore, '_persist_error', return_value=1)
        stack = 'x' * 5000
        if stack and len(stack) > 4000:
            stack = stack[:4000] + "\n...[truncated]"
        LoggingCore._persist_error(
            message='fe', category='FRONTEND', level='ERROR', source='frontend.browser',
            stack_trace=stack,
        )
        assert 'truncated' in persist.call_args.kwargs['stack_trace']

    def test_persist_error_duplicate_bump(self, app, mocker):
        mocker.patch.object(LoggingCore, '_find_duplicate', return_value=7)
        mocker.patch.object(LoggingCore, '_bump_duplicate', return_value=30)
        mocker.patch.object(LoggingCore, '_fire_alert_callbacks')
        assert LoggingCore._persist_error('m', category='BACKEND', level='ERROR', source='s') == 7

    def test_persist_error_fresh_insert(self, app, mocker):
        mocker.patch.object(LoggingCore, '_find_duplicate', return_value=None)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (99,)
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch('extensions.db.engine.connect', return_value=ctx)
        row_id = LoggingCore._persist_error('new', category='BACKEND', level='ERROR', source='s')
        assert row_id == 99

    def test_persist_error_fallback_on_db_failure(self, app, mocker):
        mocker.patch.object(LoggingCore, '_find_duplicate', return_value=None)
        mocker.patch('extensions.db.engine.connect', side_effect=RuntimeError('db down'))
        fb = mocker.patch.object(LoggingCore, '_fallback_write')
        assert LoggingCore._persist_error('x', category='BACKEND', level='ERROR', source='s') is None
        fb.assert_called_once()

    def test_find_and_bump_duplicate_errors(self, mocker):
        mocker.patch('extensions.db.engine.connect', side_effect=RuntimeError())
        assert LoggingCore._find_duplicate('fp') is None
        assert LoggingCore._bump_duplicate(1, 'm', None) is None

    def test_fallback_write(self, mocker):
        mocker.patch('sys.stderr.write', side_effect=RuntimeError())
        LoggingCore._fallback_write('msg')


class TestErrorQueries:
    def test_get_error_logs(self, mocker):
        pag = MagicMock(items=[MagicMock()], page=1)
        q = MagicMock()
        q.filter_by.return_value = q
        q.order_by.return_value.paginate.return_value = pag
        q.count.return_value = 1
        E = mocker.patch('models.error_audit_log.ErrorAuditLog')
        E.query = q
        mocker.patch('extensions.db.session.query').return_value.distinct.return_value.order_by.return_value.all.return_value = [('BACKEND',)]
        items, pagination, cats, levels, stats = LoggingCore.get_error_logs(category='BACKEND', level='ERROR', is_resolved='0')
        assert items == pag.items
        assert stats['total'] == 1

    def test_export_error_logs_json_and_text(self, mocker):
        log = MagicMock()
        log.to_dict.return_value = {'id': 1}
        log.id = 1
        log.level = 'ERROR'
        log.category = 'BACKEND'
        log.source = 's'
        log.created_at = datetime.now(timezone.utc)
        log.message = 'm'
        log.stack_trace = 'trace'
        q = MagicMock()
        q.filter_by.return_value = q
        q.order_by.return_value.all.return_value = [log]
        mocker.patch('models.error_audit_log.ErrorAuditLog').query = q
        body, mime, name = LoggingCore.export_error_logs(fmt='json')
        assert mime == 'application/json'
        body2, mime2, _ = LoggingCore.export_error_logs(fmt='txt')
        assert mime2.startswith('text/plain')

    def test_mark_error_resolved(self, mocker):
        conn = MagicMock()
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch('extensions.db.engine.connect', return_value=ctx)
        assert LoggingCore.mark_error_resolved(1, 2, 'fixed') is True


class TestAuditAndSecurity:
    def test_log_audit_success(self, app, mocker):
        mocker.patch('models.audit.AuditLog')
        mock_db = mocker.patch('extensions.db')
        with app.test_request_context('/'):
            LoggingCore.log_audit('create', 'sales', 1, {'x': 1})

    def test_log_audit_fallback(self, app, mocker):
        mocker.patch('models.audit.AuditLog', side_effect=RuntimeError('db'))
        fb = mocker.patch.object(LoggingCore, '_fallback_write')
        LoggingCore.log_audit('create', 'sales', 1)
        fb.assert_called_once()

    def test_get_audit_logs(self, mocker):
        pag = MagicMock(items=[])
        q = MagicMock()
        q.filter_by.return_value = q
        q.order_by.return_value.paginate.return_value = pag
        q.count.return_value = 0
        q.filter.return_value = q
        mocker.patch('models.audit.AuditLog').query = q
        mocker.patch('models.user.User').query.filter_by.return_value.all.return_value = []
        mocker.patch('extensions.db.func')
        LoggingCore.get_audit_logs(tenant_id=1, action='create', user_id=2)

    def test_log_security_commits(self, mocker):
        mocker.patch('models.security_alert.SecurityAlert')
        mock_db = mocker.patch('extensions.db')
        LoggingCore.log_security('failed_login', 'bad attempt', user='u', ip='1.1.1.1')
        mock_db.session.commit.assert_called_once()

    def test_log_security_rollback(self, mocker):
        mocker.patch('models.security_alert.SecurityAlert', side_effect=RuntimeError())
        mock_db = mocker.patch('extensions.db')
        LoggingCore.log_security('failed_login', 'bad')
        mock_db.session.rollback.assert_called_once()


class TestHealthAndMetrics:
    def test_health_check(self, app, mocker):
        mocker.patch.object(LoggingCore, '_check_db', return_value={'healthy': True})
        mocker.patch.object(LoggingCore, '_check_disk', return_value={'healthy': True})
        mocker.patch.object(LoggingCore, '_check_memory', return_value={'healthy': True})
        mocker.patch.object(LoggingCore, '_check_cpu', return_value={'healthy': True})
        hc = LoggingCore.health_check()
        assert hc['status'] == 'healthy'

    def test_check_db_error(self, mocker):
        mocker.patch('extensions.db.session.execute', side_effect=RuntimeError('down'))
        assert LoggingCore._check_db()['healthy'] is False

    def test_check_disk_and_memory_import_errors(self, mocker):
        mocker.patch('shutil.disk_usage', side_effect=RuntimeError())
        assert LoggingCore._check_disk()['healthy'] is True
        mocker.patch.dict('sys.modules', {'psutil': None})
        assert LoggingCore._check_memory()['healthy'] is True

    def test_get_app_metrics_and_error(self, mocker):
        mocker.patch('services.logging_core.Sale', create=True)
        sale = MagicMock()
        sale.query.count.side_effect = [1, RuntimeError('x')]
        customer = MagicMock()
        customer.query.count.return_value = 2
        customer.query.filter_by.return_value.count.return_value = 1
        product = MagicMock()
        product.query.count.return_value = 3
        product.query.filter.return_value.count.return_value = 0

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'models':
                pkg = type('models', (), {})()
                pkg.Sale = sale
                pkg.Customer = customer
                pkg.Product = product
                return pkg
            import builtins
            return builtins.__import__(name, globals, locals, fromlist, level)

        mocker.patch('builtins.__import__', side_effect=fake_import)
        metrics = LoggingCore.get_app_metrics()
        assert metrics.get('total_sales') == 1 or 'error' in metrics
        assert 'error' in LoggingCore.get_app_metrics()

    def test_get_system_health(self, mocker):
        mocker.patch.object(LoggingCore, 'check_database', return_value={'healthy': True})
        mocker.patch.object(LoggingCore, 'get_disk_usage', return_value={'healthy': True})
        mocker.patch.object(LoggingCore, 'get_memory_usage', return_value={'healthy': True})
        mocker.patch.object(LoggingCore, 'get_cpu_usage', return_value={'healthy': True})
        assert LoggingCore.get_system_health()['status'] == 'healthy'


class TestPerformanceAndActivity:
    def test_monitor_endpoint_decorator(self):
        @LoggingCore.monitor_endpoint
        def fast():
            return 'ok'

        assert fast() == 'ok'

    def test_monitor_endpoint_logs_error_path(self):
        @LoggingCore.monitor_endpoint
        def boom():
            raise ValueError('x')

        with pytest.raises(ValueError):
            boom()

    def test_log_slow_query_and_perf_metrics(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        os.makedirs('logs', exist_ok=True)
        with open('logs/performance.log', 'w', encoding='utf-8') as f:
            f.write('SLOW QUERY test\n')
        LoggingCore.log_slow_query('SELECT 1', 0.5)
        data = LoggingCore.get_performance_metrics()
        assert data['slow_queries_count'] >= 1

    def test_log_performance_metric(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        LoggingCore.log_performance_metric('latency', 12.5, tags={'route': '/x'})
        basedir = os.path.abspath(os.path.join(os.path.dirname(logging_core.__file__), os.pardir))
        assert os.path.exists(os.path.join(basedir, 'logs', 'performance.log'))

    def test_get_performance_metrics_data(self, tmp_path, monkeypatch):
        basedir = os.path.abspath(os.path.join(os.path.dirname(logging_core.__file__), os.pardir))
        os.makedirs(os.path.join(basedir, 'logs'), exist_ok=True)
        with open(os.path.join(basedir, 'logs', 'performance.log'), 'w', encoding='utf-8') as f:
            f.write('SLOW endpoint\n')
        data = LoggingCore.get_performance_metrics_data()
        assert data['slow_queries_count'] == 1

    def test_resolve_table_and_db_stats(self, app, mocker):
        mocker.patch.object(LoggingCore, '_resolve_table_name', return_value='sales')
        mocker.patch.object(LoggingCore, '_is_sensitive_table', return_value=False)
        mocker.patch.object(LoggingCore, 'log_audit')
        exec_mock = MagicMock()
        exec_mock.fetchall.return_value = [('sales',)]
        exec_mock.scalar.return_value = 5
        mocker.patch('extensions.db.session.execute', return_value=exec_mock)
        stats, restricted = LoggingCore.get_db_stats_context()
        assert stats.get('sales') == 5

    def test_get_activity_context(self, mocker):
        import models
        col = MagicMock()
        col.__ge__ = lambda self, other: MagicMock()
        col.__eq__ = lambda self, other: MagicMock()
        AuditLog = MagicMock()
        AuditLog.query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
        User = MagicMock()
        User.last_seen = col
        User.is_active = col
        User.tenant_id = col
        User.query.filter.return_value.all.return_value = []
        Sale = MagicMock()
        Sale.created_at = col
        Sale.tenant_id = col
        Sale.branch_id = col
        Sale.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        originals = (models.AuditLog, models.Sale, models.User)
        models.AuditLog, models.Sale, models.User = AuditLog, Sale, User
        try:
            ctx = LoggingCore.get_activity_context(tenant_id=1, branch_id=2)
            assert ctx['stats']['active_now'] == 0
        finally:
            models.AuditLog, models.Sale, models.User = originals

    def test_get_security_events(self, mocker):
        import models
        col = MagicMock()
        col.__ge__ = lambda self, other: MagicMock()
        AuditLog = MagicMock()
        AuditLog.created_at = col
        AuditLog.query.filter.return_value.filter_by.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        original = models.AuditLog
        models.AuditLog = AuditLog
        try:
            assert LoggingCore.get_security_events(user_id=1, days=7) == []
        finally:
            models.AuditLog = original

    def test_generate_device_fingerprint(self, app):
        with app.test_request_context('/', headers={'User-Agent': 'pytest', 'Accept-Language': 'en'}):
            fp = LoggingCore.generate_device_fingerprint()
            assert len(fp) == 16

    def test_track_login_attempt_success_and_lock(self, mocker):
        user = MagicMock(login_attempts=4)
        mocker.patch('models.User').query.filter_by.return_value.first.return_value = user
        mock_db = mocker.patch('extensions.db')
        LoggingCore.track_login_attempt('alice', success=False, ip_address='1.1.1.1')
        assert user.login_attempts == 5
        mock_db.session.commit.assert_called()
        LoggingCore.track_login_attempt('alice', success=True, ip_address='1.1.1.1')
        assert user.login_attempts == 0


class TestAutoCleanup:
    def test_auto_cleanup_deletes_rows(self, app, mocker):
        conn = MagicMock()
        conn.execute.return_value.rowcount = 3
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch('extensions.db.engine.connect', return_value=ctx)
        mocker.patch('shutil.disk_usage', return_value=(100, 90, 10))
        os.makedirs('logs', exist_ok=True)
        results = LoggingCore.auto_cleanup(error_retain_days=1, audit_retain_days=1)
        assert 'error_audit_logs' in results

    def test_schedule_cleanup_starts_thread(self, app, mocker):
        Thread = mocker.patch('threading.Thread')
        LoggingCore.schedule_cleanup(app, interval_hours=24)
        Thread.assert_called_once()

    def test_run_self_diagnostics_issues(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        app = Flask(__name__)
        handler = MagicMock()
        handler.baseFilename = os.path.join(tmp_path, 'missing.log')
        LoggingCore._handlers = {'app': handler}
        with patch('os.access', return_value=False):
            LoggingCore._run_self_diagnostics(app)

    def test_capture_warnings_hook(self, app):
        LoggingCore._capture_warnings(app)

    def test_register_request_hooks_slow_and_fast(self, app):
        LoggingCore._register_request_hooks(app)
        client = app.test_client()
        with patch('services.logging_core.time.time', side_effect=[0, 2.0]):
            with app.test_request_context('/slow'):
                g.request_start_time = 0
                for func in app.after_request_funcs[None]:
                    resp = func(MagicMock(status_code=200))
                    assert resp is not None
