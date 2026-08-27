"""utils/advanced_audit.py — device fingerprinting, audit logging, login tracking."""

from __future__ import annotations

import hashlib

from extensions import db


def _headers(ua="ProbeUA/1.0", lang="en-US", enc="gzip"):
    return {"User-Agent": ua, "Accept-Language": lang, "Accept-Encoding": enc}


class TestGenerateDeviceFingerprint:
    def test_stable_within_same_request(self, app):
        from utils.advanced_audit import generate_device_fingerprint

        with app.test_request_context("/", headers=_headers()):
            first = generate_device_fingerprint()
            second = generate_device_fingerprint()
            expected = hashlib.sha256(b"ProbeUA/1.0|en-US|gzip|").hexdigest()[:16]
            assert first == second == expected

    def test_differs_across_user_agents(self, app):
        from utils.advanced_audit import generate_device_fingerprint

        with app.test_request_context("/", headers=_headers(ua="A")):
            a = generate_device_fingerprint()
        with app.test_request_context("/", headers=_headers(ua="B")):
            b = generate_device_fingerprint()
        assert a != b


class TestLogSensitiveAction:
    def test_persists_audit_row_with_defaults(self, app, db_session, sample_tenant):
        from models import AuditLog
        from utils.advanced_audit import log_sensitive_action

        log_sensitive_action("delete_customer", table_name="customers", record_id=42)
        row = AuditLog.query.filter_by(action="delete_customer").order_by(AuditLog.id.desc()).first()
        assert row is not None
        assert row.table_name == "customers"
        assert row.record_id == 42
        # medium severity: no admin notification path

    def test_high_severity_calls_notify(self, app, mocker, db_session):
        from models import AuditLog
        from utils.advanced_audit import log_sensitive_action

        notify = mocker.patch("utils.advanced_audit.notify_admin_of_sensitive_action")
        log_sensitive_action("vault_reset", severity="high")
        assert notify.called
        row = AuditLog.query.filter_by(action="vault_reset").order_by(AuditLog.id.desc()).first()
        assert row is not None

    def test_failure_is_swallowed_and_logged(self, app, mocker, caplog):
        # Force the ORM insert to explode; the helper must swallow the error.
        mocker.patch(
            "extensions.db.session.add",
            side_effect=RuntimeError("session closed"),
        )
        from utils.advanced_audit import log_sensitive_action

        with caplog.at_level("ERROR"):
            log_sensitive_action("boom_action")  # must not raise


class TestTrackLoginAttempt:
    def test_success_resets_lockout_state(self, app, db_session, sample_user):
        from utils.advanced_audit import track_login_attempt

        sample_user.login_attempts = 3
        db.session.flush()
        track_login_attempt(sample_user.username, True, "127.0.0.1")
        assert sample_user.login_attempts == 0
        assert sample_user.last_login is not None

    def test_failures_escalate_to_lockout(self, app, db_session, sample_user):
        from datetime import UTC, datetime

        from utils.advanced_audit import track_login_attempt

        sample_user.login_attempts = 4
        db.session.flush()
        before = datetime.now(UTC).replace(tzinfo=None)
        track_login_attempt(sample_user.username, False, "127.0.0.1")
        assert sample_user.login_attempts == 5
        locked_until = sample_user.locked_until.replace(tzinfo=None)
        delta = (locked_until - before).total_seconds()
        assert delta > 14 * 60  # ~15 minute lock window

    def test_unknown_username_noop(self, app, db_session):
        from utils.advanced_audit import track_login_attempt

        track_login_attempt("ghost-user-nope", False, "127.0.0.1")  # no crash


class TestGetSecurityEvents:
    def test_filters_by_user_and_actions(self, app, db_session, sample_tenant, sample_user):
        from models import AuditLog
        from utils.advanced_audit import get_security_events

        for action in ("login", "logout", "delete", "update", "random_other"):
            db.session.add(AuditLog(user_id=sample_user.id, tenant_id=sample_tenant.id, action=action))
        db.session.flush()

        rows = get_security_events(user_id=sample_user.id)
        actions = {r.action for r in rows}
        assert actions <= {"login", "logout", "delete", "update"}
        assert "login" in actions

    def test_limit_applied(self, app, db_session, sample_tenant, sample_user):
        from models import AuditLog
        from utils.advanced_audit import get_security_events

        for _ in range(7):
            db.session.add(AuditLog(user_id=sample_user.id, tenant_id=sample_tenant.id, action="login"))
        db.session.flush()
        rows = get_security_events(user_id=sample_user.id, days=1)
        assert len(rows) <= 100
