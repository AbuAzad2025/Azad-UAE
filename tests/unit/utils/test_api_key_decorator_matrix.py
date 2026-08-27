"""api_key_required decorator — full allow/deny matrix against real rows."""

from __future__ import annotations

import uuid

from flask import g

from extensions import db
from utils.decorators import api_key_required


def _suffix():
    return uuid.uuid4().hex[:10]


def _make_key(sample_tenant, sample_user, *, key=None, secret=None, scope="write", is_active=True, tenant_id=True):
    from models.api_key import APIKey

    key = key or f"K-{_suffix()}"
    secret = secret or f"S-{_suffix()}"
    row = APIKey(
        name=f"probe-{key}",
        key=key,
        secret=secret,
        service="pos-sync",
        scope=scope,
        is_active=is_active,
        tenant_id=sample_tenant.id if tenant_id else None,
        created_by=sample_user.id,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _call(app, mocker, decorated, key, secret, status_ok=True):
    if status_ok:
        mocker.patch("utils.tenanting.get_tenant_status", return_value={"ok": True})
    else:
        mocker.patch(
            "utils.tenanting.get_tenant_status",
            return_value={"ok": False, "reason": "suspended probe"},
        )
    with app.test_request_context(
        "/__api_probe__",
        headers={"X-API-Key": key, "X-API-Secret": secret},
    ):
        return decorated()


class TestApiKeyRequiredMatrix:
    def test_missing_credentials_401(self, app, sample_tenant):
        @api_key_required(scope="read")
        def view():
            return "never"

        with app.test_request_context("/__api_probe__"):
            body, code = view()
        assert code == 401
        assert body.json["error"] == "Missing API credentials"

    def test_unknown_or_inactive_key_403(self, app, mocker, db_session, sample_tenant, sample_user):
        _make_key(sample_tenant, sample_user, is_active=False)

        @api_key_required(scope="read")
        def view():
            return "never"

        body, code = _call(app, mocker, view, "nope", "nope")
        assert code == 403
        assert "Invalid" in body.json["error"]

    def test_platform_level_key_rejected(self, app, mocker, db_session, sample_tenant, sample_user):
        row = _make_key(sample_tenant, sample_user, tenant_id=False)

        @api_key_required()
        def view():
            return "never"

        body, code = _call(app, mocker, view, row.key, row.secret)
        assert code == 403
        assert "not bound to a tenant" in body.json["error"]

    def test_read_only_key_cannot_write(self, app, mocker, db_session, sample_tenant, sample_user):
        row = _make_key(sample_tenant, sample_user, scope="read")

        @api_key_required(scope="write")
        def view():
            return "never"

        body, code = _call(app, mocker, view, row.key, row.secret)
        assert code == 403
        assert "Read-only API key" in body.json["error"]

    def test_unhealthy_tenant_blocked_with_reason(self, app, mocker, db_session, sample_tenant, sample_user):
        row = _make_key(sample_tenant, sample_user)

        @api_key_required(scope="read")
        def view():
            return "never"

        body, code = _call(app, mocker, view, row.key, row.secret, status_ok=False)
        assert code == 403
        assert body.json["error"] == "suspended probe"

    def test_happy_path_sets_tenant_and_tracks_usage(self, app, mocker, db_session, sample_tenant, sample_user):
        from models.api_key import APIKey

        api_row = _make_key(sample_tenant, sample_user, scope="read")
        before = api_row.usage_count or 0

        @api_key_required(scope="read")
        def view():
            assert g.active_tenant_id == sample_tenant.id
            return "ok-view"

        result = _call(app, mocker, view, api_row.key, api_row.secret)
        assert result == "ok-view"
        db.session.flush()
        fresh = db.session.get(APIKey, api_row.id)
        assert (fresh.usage_count or 0) >= before + 1
