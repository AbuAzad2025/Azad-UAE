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
