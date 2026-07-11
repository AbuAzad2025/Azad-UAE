from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


@pytest.fixture
def flask_app():
    return Flask(__name__)


class TestGenerateDeviceFingerprint:
    def test_hashes_request_headers(self, flask_app):
        with flask_app.test_request_context(
            '/',
            headers={
                'User-Agent': 'TestAgent/1.0',
                'Accept-Language': 'en-US',
                'Accept-Encoding': 'gzip',
                'Sec-Ch-Ua-Platform': 'Windows',
            },
        ):
            from utils.advanced_audit import generate_device_fingerprint

            fp1 = generate_device_fingerprint()
            fp2 = generate_device_fingerprint()

        assert len(fp1) == 16
        assert fp1 == fp2

    def test_handles_missing_headers(self, flask_app):
        with flask_app.test_request_context('/'):
            from utils.advanced_audit import generate_device_fingerprint

            fp = generate_device_fingerprint()

        assert len(fp) == 16
        assert all(c in '0123456789abcdef' for c in fp)


class TestLogSensitiveAction:
    def test_persists_audit_for_authenticated_user(self, flask_app):
        audit_entry = MagicMock()
        session = MagicMock()
        user = MagicMock()
        user.is_authenticated = True
        user.id = 9

        with patch('models.AuditLog') as audit_ctor, patch(
            'utils.advanced_audit.db.session', session
        ), patch('utils.advanced_audit.notify_admin_of_sensitive_action') as notify, patch(
            'utils.advanced_audit.current_user', user
        ):
            audit_ctor.return_value = audit_entry
            with flask_app.test_request_context(
                '/',
                headers={'User-Agent': 'pytest'},
                environ_base={'REMOTE_ADDR': '10.0.0.1'},
            ):
                from utils.advanced_audit import log_sensitive_action

                log_sensitive_action(
                    'update',
                    table_name='users',
                    record_id=3,
                    changes={'role': 'admin'},
                    severity='medium',
                )

        audit_ctor.assert_called_once_with(
            user_id=9,
            action='update',
            table_name='users',
            record_id=3,
            changes={'role': 'admin'},
            ip_address='10.0.0.1',
            user_agent='pytest',
        )
        session.add.assert_called_once_with(audit_entry)
        session.flush.assert_called_once()
        notify.assert_not_called()

    def test_high_severity_notifies_admin(self, flask_app):
        audit_entry = MagicMock()
        user = MagicMock()
        user.is_authenticated = False

        with patch('models.AuditLog') as audit_ctor, patch(
            'utils.advanced_audit.db.session'
        ), patch('utils.advanced_audit.notify_admin_of_sensitive_action') as notify, patch(
            'utils.advanced_audit.current_user', user
        ):
            audit_ctor.return_value = audit_entry
            with flask_app.test_request_context('/'):
                from utils.advanced_audit import log_sensitive_action

                log_sensitive_action('delete', severity='high')

        notify.assert_called_once_with('delete', audit_entry)

    def test_failure_rolls_back_and_logs(self, flask_app):
        session = MagicMock()
        user = MagicMock()
        user.is_authenticated = False

        with patch('models.AuditLog', side_effect=RuntimeError('db down')), patch(
            'utils.advanced_audit.db.session', session
        ), patch('logging.getLogger') as get_logger, patch(
            'utils.advanced_audit.current_user', user
        ):
            with flask_app.test_request_context('/'):
                from utils.advanced_audit import log_sensitive_action

                log_sensitive_action('login')

        session.rollback.assert_called_once()
        get_logger.return_value.exception.assert_called_once()


class TestTrackLoginAttempt:
    def test_success_resets_attempts_and_sets_last_login(self):
        user = MagicMock()
        user.login_attempts = 4
        user.last_login = None
        user.locked_until = None
        query = MagicMock()
        query.filter_by.return_value.first.return_value = user
        session = MagicMock()

        with patch('models.User') as user_model, patch('utils.advanced_audit.db.session', session):
            user_model.query = query
            from utils.advanced_audit import track_login_attempt

            track_login_attempt('alice', success=True, ip_address='1.2.3.4')

        assert user.login_attempts == 0
        assert user.last_login is not None
        session.flush.assert_called_once()

    def test_failed_attempt_increments_without_lock_below_threshold(self):
        user = MagicMock()
        user.login_attempts = 2
        user.locked_until = None
        query = MagicMock()
        query.filter_by.return_value.first.return_value = user
        session = MagicMock()

        with patch('models.User') as user_model, patch('utils.advanced_audit.db.session', session):
            user_model.query = query
            from utils.advanced_audit import track_login_attempt

            track_login_attempt('bob', success=False, ip_address='1.2.3.4')

        assert user.login_attempts == 3
        assert user.locked_until is None
        session.flush.assert_called_once()

    def test_failed_attempt_locks_account_at_threshold(self):
        user = MagicMock()
        user.login_attempts = 4
        user.locked_until = None
        query = MagicMock()
        query.filter_by.return_value.first.return_value = user

        with patch('models.User') as user_model, patch('utils.advanced_audit.db.session'):
            user_model.query = query
            from utils.advanced_audit import track_login_attempt

            before = datetime.now(timezone.utc)
            track_login_attempt('carol', success=False, ip_address='5.6.7.8')
            after = datetime.now(timezone.utc)

        assert user.login_attempts == 5
        assert user.locked_until is not None
        assert before + timedelta(minutes=14) < user.locked_until < after + timedelta(minutes=16)

    def test_unknown_user_is_noop(self):
        query = MagicMock()
        query.filter_by.return_value.first.return_value = None
        session = MagicMock()

        with patch('models.User') as user_model, patch('utils.advanced_audit.db.session', session):
            user_model.query = query
            from utils.advanced_audit import track_login_attempt

            track_login_attempt('missing', success=False, ip_address='9.9.9.9')

        session.flush.assert_not_called()


class TestGetSecurityEvents:
    def _build_query(self, rows):
        query = MagicMock()
        query.filter.return_value = query
        query.filter_by.return_value = query
        query.order_by.return_value.limit.return_value.all.return_value = rows
        return query

    def test_returns_recent_security_actions(self):
        rows = [MagicMock(action='login'), MagicMock(action='delete')]
        query = self._build_query(rows)
        created_at = MagicMock()
        created_at.__ge__ = MagicMock(return_value='since_filter')

        with patch('models.AuditLog') as audit_log:
            audit_log.query = query
            audit_log.created_at = created_at
            audit_log.action = MagicMock()
            from utils.advanced_audit import get_security_events

            result = get_security_events(days=7)

        assert result == rows
        assert query.filter.call_count == 2
        query.filter.assert_any_call('since_filter')
        query.order_by.assert_called_once()
        query.order_by.return_value.limit.assert_called_once_with(100)

    def test_filters_by_user_when_provided(self):
        query = self._build_query([])
        created_at = MagicMock()
        created_at.__ge__ = MagicMock(return_value='since_filter')

        with patch('models.AuditLog') as audit_log:
            audit_log.query = query
            audit_log.created_at = created_at
            audit_log.action = MagicMock()
            from utils.advanced_audit import get_security_events

            get_security_events(user_id=15, days=30)

        query.filter_by.assert_called_once_with(user_id=15)


class TestNotifyAdminStub:
    def test_notify_admin_is_noop(self):
        from utils.advanced_audit import notify_admin_of_sensitive_action

        notify_admin_of_sensitive_action('delete', MagicMock())
