"""Error audit — severity classification, dedup, sanitization, escalation."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


class TestSanitization:
    """_sanitize_dict — scrub passwords and API keys."""

    def test_redacts_secret_keys(self):
        from services.error_audit_service import ErrorAuditService

        data = {
            'username': 'admin',
            'password': 'secret123',
            'api_key': 'sk-live-xyz',
            'nested': {'refresh_token': 'tok'},
        }
        clean = ErrorAuditService._sanitize_dict(data)
        assert clean['username'] == 'admin'
        assert clean['password'] == '***REDACTED***'
        assert clean['api_key'] == '***REDACTED***'
        assert clean['nested']['refresh_token'] == '***REDACTED***'

    def test_non_dict_returns_empty(self):
        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService._sanitize_dict('not-a-dict') == {}


class TestFingerprintAndDedup:
    """_make_fingerprint / dedup window — collapse similar crashes."""

    def test_fingerprint_stable_for_same_inputs(self):
        from services.error_audit_service import ErrorAuditService

        fp1 = ErrorAuditService._make_fingerprint('BACKEND', 'ValueError', 'svc', '/api/x', 'boom')
        fp2 = ErrorAuditService._make_fingerprint('BACKEND', 'ValueError', 'svc', '/api/x', 'boom')
        assert fp1 == fp2
        assert len(fp1) == 32

    def test_find_duplicate_returns_id(self, mocker):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (42,)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch('services.error_audit_service.db.engine.connect', return_value=ctx)

        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService._find_duplicate('abc') == 42

    def test_bump_duplicate_increments_occurrence(self, mocker):
        conn = MagicMock()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch('services.error_audit_service.db.engine.connect', return_value=ctx)

        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService._bump_duplicate(7, 'again', 'trace') is True
        conn.commit.assert_called_once()


class TestQueryAndStats:
    """get_logs_query / get_stats / export — classification filters."""

    def test_logs_query_resolved_filter(self, mocker):
        from models.error_audit_log import ErrorAuditLog

        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mocker.patch.object(
            ErrorAuditLog, 'query', new_callable=mocker.PropertyMock, return_value=mock_q,
        )

        from services.error_audit_service import ErrorAuditService

        ErrorAuditService.get_logs_query('BACKEND', 'ERROR', '1')
        mock_q.filter_by.assert_any_call(is_resolved=True)

    def test_stats_counts(self, mocker):
        from models.error_audit_log import ErrorAuditLog

        base_q = MagicMock()
        base_q.count.return_value = 100
        unresolved_q = MagicMock()
        unresolved_q.count.return_value = 12
        critical_q = MagicMock()
        critical_q.count.return_value = 3

        mock_prop = mocker.PropertyMock(return_value=base_q)
        mocker.patch.object(ErrorAuditLog, 'query', mock_prop)
        base_q.filter_by.side_effect = [unresolved_q, critical_q]

        from services.error_audit_service import ErrorAuditService

        stats = ErrorAuditService.get_stats()
        assert stats['total'] == 100
        assert stats['unresolved'] == 12
        assert stats['critical'] == 3

    def test_export_json_payload(self, mocker):
        log = MagicMock()
        log.to_dict.return_value = {'id': 1, 'level': 'CRITICAL'}
        mocker.patch(
            'services.error_audit_service.ErrorAuditService.get_logs_query',
            return_value=MagicMock(all=MagicMock(return_value=[log])),
        )

        from services.error_audit_service import ErrorAuditService

        body, mime, name = ErrorAuditService.get_export_payload('', '', '', 'json')
        assert mime == 'application/json'
        assert name == 'error_audit_logs.json'
        assert '"CRITICAL"' in body


class TestLogApi:
    """log / log_exception / mark_resolved — persistence delegation."""

    def test_log_exception_delegates_to_persist(self, mocker):
        mocker.patch(
            'services.error_audit_service.ErrorAuditService._persist',
            return_value=99,
        )

        from services.error_audit_service import ErrorAuditService

        row_id = ErrorAuditService.log_exception(ValueError('bad'), source='payroll')
        assert row_id == 99

    def test_log_critical_level_passthrough(self, mocker):
        persist = mocker.patch(
            'services.error_audit_service.ErrorAuditService._persist',
            return_value=1,
        )

        from services.error_audit_service import ErrorAuditService

        ErrorAuditService.log('disk full', level='CRITICAL', category='INFRA', source='backup')
        assert persist.call_args.kwargs['level'] == 'CRITICAL'

    def test_dedup_short_circuits_insert(self, mocker):
        mocker.patch(
            'services.error_audit_service.ErrorAuditService._find_duplicate',
            return_value=55,
        )
        mocker.patch(
            'services.error_audit_service.ErrorAuditService._bump_duplicate',
            return_value=True,
        )
        insert = mocker.patch('services.error_audit_service.db.engine.connect')

        from services.error_audit_service import ErrorAuditService

        row_id = ErrorAuditService._persist('dup error', category='BACKEND', level='ERROR', source='x')
        assert row_id == 55
        insert.assert_not_called()

    def test_mark_resolved_returns_false_on_db_error(self, mocker):
        mocker.patch(
            'services.error_audit_service.db.engine.connect',
            side_effect=RuntimeError('db'),
        )

        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService.mark_resolved(1, user_id=2) is False

    def test_get_or_create_request_id_without_context(self):
        from services.error_audit_service import ErrorAuditService

        rid = ErrorAuditService.get_or_create_request_id()
        assert len(rid) == 36


class TestQueryFilters:
    def test_logs_query_unresolved_filter(self, mocker):
        from models.error_audit_log import ErrorAuditLog

        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mocker.patch.object(
            ErrorAuditLog, 'query', new_callable=mocker.PropertyMock, return_value=mock_q,
        )
        from services.error_audit_service import ErrorAuditService

        ErrorAuditService.get_logs_query('API', 'WARNING', '0')
        mock_q.filter_by.assert_any_call(category='API')
        mock_q.filter_by.assert_any_call(level='WARNING')
        mock_q.filter_by.assert_any_call(is_resolved=False)

    def test_get_dropdowns(self, mocker):
        session = mocker.patch('services.error_audit_service.db.session')
        cat_q = MagicMock()
        cat_q.distinct.return_value.order_by.return_value.all.return_value = [('BACKEND',), ('FRONTEND',)]
        lvl_q = MagicMock()
        lvl_q.distinct.return_value.order_by.return_value.all.return_value = [('ERROR',), ('CRITICAL',)]
        session.query.side_effect = [cat_q, lvl_q]
        from services.error_audit_service import ErrorAuditService

        categories, levels = ErrorAuditService.get_dropdowns()
        assert categories == ['BACKEND', 'FRONTEND']
        assert levels == ['ERROR', 'CRITICAL']


class TestExportText:
    def test_export_txt_payload(self, mocker):
        from datetime import datetime, timezone

        log = MagicMock()
        log.id = 1
        log.level = 'ERROR'
        log.category = 'BACKEND'
        log.source = 'svc'
        log.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        log.url = 'http://x'
        log.user_id = 2
        log.tenant_id = 3
        log.is_resolved = False
        log.message = 'boom'
        log.stack_trace = 'trace' * 200
        log.request_data = '{"k":1}'
        mocker.patch(
            'services.error_audit_service.ErrorAuditService.get_logs_query',
            return_value=MagicMock(all=MagicMock(return_value=[log])),
        )
        from services.error_audit_service import ErrorAuditService

        body, mime, name = ErrorAuditService.get_export_payload('', '', '', 'txt')
        assert mime.startswith('text/plain')
        assert name == 'error_audit_logs.txt'
        assert b'boom' in body
        assert b'Stack Trace' in body
        assert b'Request Data' in body


class TestPersistPaths:
    def test_log_frontend_truncates_stack(self, mocker):
        persist = mocker.patch(
            'services.error_audit_service.ErrorAuditService._persist',
            return_value=1,
        )
        from services.error_audit_service import ErrorAuditService

        long_stack = 'x' * 5000
        ErrorAuditService.log_frontend('js error', stack=long_stack)
        trace = persist.call_args.kwargs['stack_trace']
        assert 'truncated' in trace

    def test_log_exception_empty_message(self, mocker):
        mocker.patch(
            'services.error_audit_service.ErrorAuditService._persist',
            return_value=2,
        )
        from services.error_audit_service import ErrorAuditService

        class Silent(Exception):
            def __str__(self):
                return ''

        row_id = ErrorAuditService.log_exception(Silent())
        assert row_id == 2

    def test_log_logger_failure_still_returns_id(self, mocker):
        mocker.patch(
            'services.error_audit_service.ErrorAuditService._persist',
            return_value=8,
        )
        mocker.patch('services.error_audit_service.logger.error', side_effect=RuntimeError('log'))
        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService.log('msg') == 8

    def test_mark_resolved_success(self, mocker):
        conn = MagicMock()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch('services.error_audit_service.db.engine.connect', return_value=ctx)
        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService.mark_resolved(5, user_id=1, note='fixed') is True
        conn.commit.assert_called_once()

    def test_find_duplicate_exception_returns_none(self, mocker):
        mocker.patch(
            'services.error_audit_service.db.engine.connect',
            side_effect=RuntimeError('db'),
        )
        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService._find_duplicate('fp') is None

    def test_bump_duplicate_failure(self, mocker):
        mocker.patch(
            'services.error_audit_service.db.engine.connect',
            side_effect=RuntimeError('db'),
        )
        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService._bump_duplicate(1, 'm', 't') is False

    def test_persist_insert_success(self, app, mocker):
        mocker.patch(
            'services.error_audit_service.ErrorAuditService._find_duplicate',
            return_value=None,
        )
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (77,)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch('services.error_audit_service.db.engine.connect', return_value=ctx)
        from services.error_audit_service import ErrorAuditService

        with app.test_request_context('/api/test', method='POST', json={'password': 'secret'}):
            row_id = ErrorAuditService._persist(
                'backend fail',
                category='BACKEND',
                level='ERROR',
                source='api',
                exception=ValueError('bad'),
            )
        assert row_id == 77

    def test_persist_insert_engine_failure(self, mocker):
        mocker.patch(
            'services.error_audit_service.ErrorAuditService._find_duplicate',
            return_value=None,
        )
        mocker.patch(
            'services.error_audit_service.db.engine.connect',
            side_effect=RuntimeError('engine'),
        )
        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService._persist('x', category='BACKEND', level='ERROR', source='s') is None

    def test_persist_frontend_fingerprint_key(self, mocker):
        mocker.patch(
            'services.error_audit_service.ErrorAuditService._find_duplicate',
            return_value=None,
        )
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (3,)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch('services.error_audit_service.db.engine.connect', return_value=ctx)
        from services.error_audit_service import ErrorAuditService

        ErrorAuditService._persist(
            'msg',
            category='FRONTEND',
            level='ERROR',
            source='browser',
            url='https://app.example.com/page',
            extra={'fingerprint_key': 'fp-key'},
        )
        conn.execute.assert_called_once()

    def test_persist_dup_bump_fails_falls_through(self, mocker):
        mocker.patch(
            'services.error_audit_service.ErrorAuditService._find_duplicate',
            return_value=10,
        )
        mocker.patch(
            'services.error_audit_service.ErrorAuditService._bump_duplicate',
            return_value=False,
        )
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (11,)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch('services.error_audit_service.db.engine.connect', return_value=ctx)
        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService._persist('x', category='BACKEND', level='ERROR', source='s') == 11

    def test_get_or_create_request_id_reuses_g(self, app):
        from flask import g
        from services.error_audit_service import ErrorAuditService

        with app.test_request_context():
            g.request_id = 'existing-id'
            assert ErrorAuditService.get_or_create_request_id() == 'existing-id'


class TestSanitizeAdvanced:
    def test_sanitize_list_and_undefined(self):
        from services.error_audit_service import ErrorAuditService

        class Undefined:
            pass

        data = {
            'items': [{'token': 'x'}, Undefined()],
            'plain': 'ok',
        }
        clean = ErrorAuditService._sanitize_dict(data)
        assert clean['items'][0]['token'] == '***REDACTED***'
        assert clean['items'][1] is None
        assert clean['plain'] == 'ok'

    def test_sanitize_non_dict_key_type_edge(self):
        from services.error_audit_service import ErrorAuditService

        class WeirdKey:
            def lower(self):
                raise RuntimeError('lower fail')

        data = {WeirdKey(): 'value'}
        clean = ErrorAuditService._sanitize_dict(data)
        assert len(clean) == 1

    def test_sanitize_undefined_scalar(self):
        from services.error_audit_service import ErrorAuditService

        class Undefined:
            pass

        clean = ErrorAuditService._sanitize_dict({'scalar': Undefined()})
        assert clean['scalar'] is None


class TestRequestId:
    def test_generates_and_stores_request_id(self, app):
        from flask import g
        from services.error_audit_service import ErrorAuditService

        with app.test_request_context('/new'):
            if hasattr(g, 'request_id'):
                delattr(g, 'request_id')
            rid = ErrorAuditService.get_or_create_request_id()
            assert len(rid) == 36
            assert g.request_id == rid

    def test_persist_without_extra_uses_form_payload(self, app, mocker):
        mocker.patch('services.error_audit_service.ErrorAuditService._find_duplicate', return_value=None)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (5,)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch('services.error_audit_service.db.engine.connect', return_value=ctx)
        from services.error_audit_service import ErrorAuditService

        with app.test_request_context('/form', method='POST', data={'username': 'a'}):
            row_id = ErrorAuditService._persist('form err', category='BACKEND', level='ERROR', source='web')
        assert row_id == 5

    def test_persist_user_lookup_failure(self, app, mocker):
        mocker.patch('services.error_audit_service.ErrorAuditService._find_duplicate', return_value=None)
        mocker.patch('services.error_audit_service.current_user', MagicMock(get_id=MagicMock(side_effect=RuntimeError('user'))))
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (6,)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch('services.error_audit_service.db.engine.connect', return_value=ctx)
        from services.error_audit_service import ErrorAuditService

        with app.test_request_context('/x'):
            assert ErrorAuditService._persist('x', category='BACKEND', level='ERROR', source='s') == 6

    def test_persist_app_config_failure(self, app, mocker):
        mocker.patch('services.error_audit_service.ErrorAuditService._find_duplicate', return_value=None)
        mocker.patch('services.error_audit_service.current_app', MagicMock(config=MagicMock(get=MagicMock(side_effect=RuntimeError('cfg')))))
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (7,)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch('services.error_audit_service.db.engine.connect', return_value=ctx)
        from services.error_audit_service import ErrorAuditService

        with app.test_request_context('/x'):
            assert ErrorAuditService._persist('x', category='BACKEND', level='ERROR', source='s') == 7

    def test_persist_form_parse_failure(self, app, mocker):
        mocker.patch('services.error_audit_service.ErrorAuditService._find_duplicate', return_value=None)
        bad_request = MagicMock()
        bad_request.url = 'http://localhost/x'
        bad_request.method = 'POST'
        bad_request.headers = {}
        bad_request.is_json = False
        bad_request.form = MagicMock(to_dict=MagicMock(side_effect=RuntimeError('form')))
        mocker.patch('services.error_audit_service.request', bad_request)
        mocker.patch('services.error_audit_service.has_request_context', return_value=True)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (8,)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch('services.error_audit_service.db.engine.connect', return_value=ctx)
        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService._persist('x', category='BACKEND', level='ERROR', source='s') == 8

    def test_persist_endpoint_parse_failure(self, app, mocker):
        mocker.patch('services.error_audit_service.ErrorAuditService._find_duplicate', return_value=None)
        mocker.patch('services.error_audit_service.urlparse', side_effect=RuntimeError('parse'))
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (9,)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch('services.error_audit_service.db.engine.connect', return_value=ctx)
        from services.error_audit_service import ErrorAuditService

        ErrorAuditService._persist(
            'msg', category='FRONTEND', level='ERROR', source='browser', url='https://app/x',
        )
        conn.execute.assert_called_once()

    def test_persist_engine_stderr_failure(self, mocker):
        mocker.patch('services.error_audit_service.ErrorAuditService._find_duplicate', return_value=None)
        mocker.patch('services.error_audit_service.db.engine.connect', side_effect=RuntimeError('engine'))
        mocker.patch('sys.stderr.write', side_effect=RuntimeError('stderr'))
        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService._persist('x', category='BACKEND', level='ERROR', source='s') is None

    def test_get_or_create_request_id_sets_g(self, app):
        from flask import g
        from services.error_audit_service import ErrorAuditService

        with app.test_request_context('/'):
            rid = ErrorAuditService.get_or_create_request_id()
            assert g.request_id == rid

    def test_get_or_create_request_id_returns_existing(self, app):
        from flask import g
        from services.error_audit_service import ErrorAuditService

        with app.test_request_context('/'):
            g.request_id = 'already-set'
            assert ErrorAuditService.get_or_create_request_id() == 'already-set'

    def test_persist_authenticated_user_tenant(self, app, mocker):
        mocker.patch('services.error_audit_service.ErrorAuditService._find_duplicate', return_value=None)
        user = MagicMock(is_authenticated=True)
        user.get_id.return_value = '42'
        user.tenant_id = 99
        mocker.patch('services.error_audit_service.current_user', user)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (12,)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch('services.error_audit_service.db.engine.connect', return_value=ctx)
        from services.error_audit_service import ErrorAuditService

        with app.test_request_context('/secure'):
            assert ErrorAuditService._persist('auth', category='BACKEND', level='ERROR', source='s') == 12
