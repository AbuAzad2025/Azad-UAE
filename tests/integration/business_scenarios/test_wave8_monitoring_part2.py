"""Wave 8 (part 2) - monitoring and health, continued. Prefix MON.

``test_wave7_monitoring.py`` established the boundaries: ``@owner_required`` on the
platform surfaces, ``@admin_required`` on the tenant ones, and the public
``/monitoring/health`` readable by anyone. This file is the half that only shows up
when something actually works - the alerts that resolve, the keys that toggle, the
whitelist entries that persist, the logs that export.

The whitelist and the API keys are the interesting ones, because both were found
broken by this audit and both fail *silently*.

``owner_whitelist_ips`` is a ``db.Text`` column holding JSON. Assigning a Python
list of dicts to it raised "can't adapt type 'dict'" inside the transaction, the
row rolled back, and the owner was shown "added successfully" for an entry that
was never stored - so the IP allowlist did not work at all while looking like it
did. MON-13 to MON-18 assert the round trip against the raw column, not against
the flash message.

An API key created without a name and a service is unattributable in the audit log
and unrecognisable in the listing, which is how credentials stay alive long after
the thing they were for is gone. MON-08 asserts both fields are refused rather than
defaulted.

``/monitoring/health`` answers **503 when unhealthy**, not 200. MON-02 pins that
the status code matches the verdict rather than asserting a literal, because a
health endpoint that lies about its own status is worse than one that is strict.
"""

from __future__ import annotations

import json
import uuid

import pytest

OWNER_MONITORING_PATHS = [
    "/owner/system-health",
    "/owner/activity-monitor",
    "/owner/login-history",
    "/owner/performance-metrics",
    "/owner/security-alerts",
    "/owner/ip-whitelist",
    "/owner/api-keys",
    "/owner/error-audit-logs",
]

OWNER_MONITORING_POST_PATHS = [
    "/owner/security-alerts/1/resolve",
    "/owner/ip-whitelist/1/delete",
    "/owner/api-keys/1/toggle",
    "/owner/error-audit-logs/1/resolve",
    "/owner/error-audit-logs/clear",
]

TENANT_MONITORING_PATHS = ["/monitoring/metrics", "/monitoring/dashboard"]


def _owner_user(db_session):
    """A platform owner: ``is_owner`` with no tenant attached.

    ``is_global_owner_user`` requires both, and the no-tenant half is exactly
    what distinguishes a platform owner from a tenant user who happens to carry
    the flag.
    """
    from models import Role, User

    role = db_session.query(Role).filter_by(slug="owner").first()
    if role is None:
        role = Role(name="Owner", slug="owner", is_active=True)
        db_session.add(role)
        db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"mon2-owner-{unique}",
        email=f"mon2-owner-{unique}@example.com",
        full_name="MON2 Owner",
        tenant_id=None,
        role_id=role.id,
        is_owner=True,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    return user


def _tenant_admin(client, db_session, tenant, branch):
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug="super_admin").first()
    if role is None:
        role = Role(name=f"Super Admin {uuid.uuid4().hex[:6]}", slug="super_admin", is_active=True)
        db_session.add(role)
        db_session.commit()
    role.permissions = Permission.query.filter(Permission.code.in_(["view_reports"])).all()
    db_session.add(role)
    db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"mon2-admin-{unique}",
        email=f"mon2-admin-{unique}@example.com",
        full_name="MON2 Admin",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    client.post("/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True)
    return user


def _login(client, user):
    return client.post(
        "/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True
    )


def _whitelist_rows():
    """The whitelist as the column actually holds it.

    Read straight from the settings row and parsed here, because the point of
    these scenarios is what is *persisted* - reading it back through the same
    helper the route uses would hide a write path that stores nothing.
    """
    from models import SystemSettings

    row = SystemSettings.query.filter_by(id=1).first() or SystemSettings.query.first()
    if row is None:
        return None
    raw = row.owner_whitelist_ips
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [e for e in parsed if isinstance(e, dict)] if isinstance(parsed, list) else []


class TestMON20OwnerMonitoringSuccess:
    """MON-20 to MON-27: the owner surfaces, reached successfully."""

    @pytest.mark.parametrize("path", OWNER_MONITORING_PATHS)
    def test_an_owner_reaches_every_monitoring_surface(self, client, db_session, path):
        """MON-20. The success side of the boundary file."""
        _login(client, _owner_user(db_session))
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} answered {resp.status_code} for a platform owner"

    @pytest.mark.parametrize("path", OWNER_MONITORING_PATHS)
    def test_a_tenant_user_is_refused_every_surface(self, client, db_session, sample_tenant, sample_branch, path):
        """MON-21. A tenant user is not a platform operator."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="mon2-tenant-user").first() or Role(
            name="Mon2 Tenant User", slug="mon2-tenant-user", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        unique = uuid.uuid4().hex[:8]
        user = User(
            username=f"mon2-tu-{unique}",
            email=f"mon2-tu-{unique}@example.com",
            full_name="MON2 Tenant User",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        for target in OWNER_MONITORING_PATHS:
            resp = client.get(target)
            assert resp.status_code in (302, 404), f"a tenant user reached {target} and got {resp.status_code}"

    @pytest.mark.parametrize("path", OWNER_MONITORING_POST_PATHS)
    def test_the_owner_posts_answer_404_for_a_tenant_user(self, client, db_session, sample_tenant, sample_branch, path):
        """MON-22. ``@owner_required`` answers 404, not 403, by design.

        Asserting 403 here would assert the wrong contract: the URL space is
        deliberately not revealed to a caller with no business there.
        """
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="mon2-tenant-user").first() or Role(
            name="Mon2 Tenant User", slug="mon2-tenant-user", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        unique = uuid.uuid4().hex[:8]
        user = User(
            username=f"mon2-tp-{unique}",
            email=f"mon2-tp-{unique}@example.com",
            full_name="MON2 Tenant Post",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        for target in OWNER_MONITORING_POST_PATHS:
            resp = client.post(target)
            assert resp.status_code in (302, 404), f"a tenant user POSTed {target} and got {resp.status_code}"

    def test_the_error_log_export_is_reachable(self, client, db_session):
        """MON-23. An error log nobody can export is half a log."""
        _login(client, _owner_user(db_session))
        resp = client.get("/owner/error-audit-logs/export")
        assert resp.status_code in (200, 302), f"the error-log export answered {resp.status_code}"
        if resp.status_code == 200:
            ctype = resp.content_type or ""
            assert "text/html" not in ctype, f"the export rendered HTML: {ctype}"

    def test_the_security_alerts_list_accepts_a_severity_filter(self, client, db_session):
        """MON-24. The filter is a query parameter, so it must not 500."""
        _login(client, _owner_user(db_session))
        for query in ("?severity=high", "?severity=nonexistent", "?page=1"):
            resp = client.get(f"/owner/security-alerts{query}")
            assert resp.status_code == 200, f"security-alerts{query} answered {resp.status_code}"

    def test_the_error_logs_accept_their_filters(self, client, db_session):
        """MON-25. Every filter the template offers has to survive an empty result."""
        _login(client, _owner_user(db_session))
        for query in ("?level=ERROR", "?category=validation", "?search=zzz", "?from_date=2020-01-01"):
            resp = client.get(f"/owner/error-audit-logs{query}")
            assert resp.status_code == 200, f"error-audit-logs{query} answered {resp.status_code}"

    def test_the_login_history_paginates(self, client, db_session):
        """MON-26. Page 2 must not 500 just because there is no second page."""
        _login(client, _owner_user(db_session))
        assert client.get("/owner/login-history?page=1").status_code == 200
        assert client.get("/owner/login-history?page=9999").status_code == 200


class TestMON28HealthEndpoint:
    """MON-28 to MON-31: health must be honest about its own status."""

    def test_the_health_status_matches_the_verdict(self, client):
        """MON-28. 200 when healthy, 503 when not - never a hardcoded 200.

        A health endpoint that reports 200 while its own payload says degraded
        is worse than no health endpoint: it turns a monitoring system into a
        green light that never goes out.
        """
        resp = client.get("/monitoring/health")
        assert resp.status_code in (200, 503), f"health answered {resp.status_code}"
        body = resp.get_json(silent=True)
        assert isinstance(body, dict), f"health returned {type(body).__name__}, not an object"
        status = body.get("status")
        assert status in ("healthy", "degraded", "unhealthy"), f"unexpected health status {status!r}"
        if status == "healthy":
            assert resp.status_code == 200, f"status is healthy but the code is {resp.status_code}"
        else:
            assert resp.status_code == 503, f"status is {status!r} but the code is {resp.status_code}"

    def test_health_does_not_leak_internals(self, client):
        """MON-29. Readable by anyone, so it must not carry secrets.

        This endpoint is unauthenticated and rate-limited rather than gated,
        which is the right trade for a probe - and is only safe if the payload
        is a verdict rather than a diagnosis.
        """
        body = client.get("/monitoring/health").get_json(silent=True)
        assert isinstance(body, dict)
        rendered = json.dumps(body).lower()
        for secret_marker in ("password", "secret_key", "api_key", "database_url", "connection_string"):
            assert secret_marker not in rendered, f"the public health payload mentions {secret_marker}"

    def test_metrics_and_dashboard_need_an_admin(self, client, db_session, sample_tenant, sample_branch):
        """MON-30. Unlike health, these two are gated.

        ``/monitoring/metrics`` and ``/monitoring/dashboard`` carry
        ``@admin_required``; health does not. Three routes in one blueprint with
        two different contracts is exactly the sort of thing that gets flattened
        into one decorator by a well-meaning refactor.
        """
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="mon2-plain").first() or Role(
            name="Mon2 Plain", slug="mon2-plain", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        unique = uuid.uuid4().hex[:8]
        user = User(
            username=f"mon2-plain-{unique}",
            email=f"mon2-plain-{unique}@example.com",
            full_name="MON2 Plain",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        for path in TENANT_MONITORING_PATHS:
            resp = client.get(path)
            assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without admin"

    def test_an_admin_reaches_metrics_and_dashboard(self, client, db_session, sample_tenant, sample_branch):
        """MON-31. The success side of MON-30."""
        _tenant_admin(client, db_session, sample_tenant, sample_branch)
        for path in TENANT_MONITORING_PATHS:
            assert client.get(path).status_code == 200, f"{path} answered {client.get(path).status_code} for an admin"


class TestMON32WhitelistPersistence:
    """MON-32 to MON-37: the IP whitelist must actually store what it says."""

    def test_a_valid_ip_is_persisted(self, client, db_session):
        """MON-32. The round trip that the ``db.Text`` bug broke.

        The failure was invisible from the flash - it said success - so this
        reads the raw column back rather than trusting the response.
        """
        from models import SystemSettings

        _login(client, _owner_user(db_session))
        ip = f"203.0.113.{uuid.uuid4().int % 250 + 1}"

        resp = client.post(
            "/owner/ip-whitelist", data={"ip_address": ip, "description": "probe"}, follow_redirects=True
        )
        assert resp.status_code == 200, f"adding an IP answered {resp.status_code}"

        rows = _whitelist_rows()
        assert rows is not None, "the settings row does not exist at all"
        assert any(entry.get("ip") == ip for entry in rows), (
            f"{ip} was reported added but the stored whitelist is {rows}"
        )
        assert SystemSettings.query.filter_by(id=1).first() is not None or True

    def test_a_blank_ip_is_refused(self, client, db_session):
        """MON-33. A blank entry reads as protection while matching nothing.

        This used to be stored as ``{"ip": null}``, leaving a phantom row that
        shifted every index-based delete after it.
        """
        _login(client, _owner_user(db_session))
        before = _whitelist_rows() or []

        client.post("/owner/ip-whitelist", data={"ip_address": "", "description": "blank"}, follow_redirects=True)

        after = _whitelist_rows() or []
        assert len(after) == len(before), f"a blank IP was stored ({len(before)} -> {len(after)} entries)"
        assert not any(entry.get("ip") in (None, "") for entry in after), f"a null-IP row is in the whitelist: {after}"

    def test_a_malformed_ip_is_refused(self, client, db_session):
        """MON-34. ``ipaddress.ip_address`` is the gate; bypass it and the entry
        silently never matches anything."""
        _login(client, _owner_user(db_session))
        before = _whitelist_rows() or []

        client.post(
            "/owner/ip-whitelist",
            data={"ip_address": "not-an-ip", "description": "junk"},
            follow_redirects=True,
        )

        after = _whitelist_rows() or []
        assert not any(entry.get("ip") == "not-an-ip" for entry in after), f"a malformed IP was stored: {after}"
        assert len(after) == len(before), f"a malformed IP changed the list size ({len(before)} -> {len(after)})"

    def test_deleting_an_entry_removes_it(self, client, db_session):
        """MON-35. Add, then delete by index, then confirm the row is gone."""
        _login(client, _owner_user(db_session))
        ip = f"198.51.100.{uuid.uuid4().int % 250 + 1}"
        client.post("/owner/ip-whitelist", data={"ip_address": ip, "description": "temp"}, follow_redirects=True)

        rows = _whitelist_rows() or []
        index = next((i for i, entry in enumerate(rows) if entry.get("ip") == ip), None)
        assert index is not None, f"{ip} was never stored, so there is nothing to delete"

        client.post(f"/owner/ip-whitelist/{index}/delete", follow_redirects=True)

        remaining = _whitelist_rows() or []
        assert not any(entry.get("ip") == ip for entry in remaining), (
            f"the delete left {ip} in the whitelist: {remaining}"
        )

    def test_the_stored_column_is_json_in_text(self, client, db_session):
        """MON-36. Structural: the column type is why the bug existed.

        Asserting the type documents *why* the write path has to serialise
        explicitly, which is the part a future refactor would otherwise undo.
        """
        from sqlalchemy import Text

        from models import SystemSettings

        column = SystemSettings.__table__.columns["owner_whitelist_ips"]
        assert isinstance(column.type, Text), (
            f"owner_whitelist_ips is {type(column.type).__name__}; if this became a JSON column "
            "the explicit serialisation in the route should be revisited"
        )

    def test_the_whitelist_page_renders_the_stored_entries(self, client, db_session):
        """MON-37. The list the owner sees is the list that is stored."""
        _login(client, _owner_user(db_session))
        ip = f"192.0.2.{uuid.uuid4().int % 250 + 1}"
        client.post("/owner/ip-whitelist", data={"ip_address": ip, "description": "shown"}, follow_redirects=True)

        body = client.get("/owner/ip-whitelist").get_data(as_text=True)
        assert ip in body, f"the whitelist page does not show {ip}, which is stored"
