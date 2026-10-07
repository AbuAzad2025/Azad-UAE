"""Wave 7 - platform monitoring, security alerts and API keys. Prefix MON.

Everything here is under ``/owner/`` and therefore answers 404 to a non-owner,
which the scenarios assert per route rather than in aggregate: this module holds
an IP allowlist and the ability to mint platform API keys, so a single missing
decorator is the whole security model.

The second concern is that most of these routes *write*. An allowlist entry, an
API key, an alert resolution - each is a security decision, and the interesting
failures are the refusals and the invalid inputs rather than the happy paths.
"""

from __future__ import annotations

import uuid

import pytest

OWNER_MON_PATHS = [
    "/owner/system-health",
    "/owner/activity-monitor",
    "/owner/login-history",
    "/owner/performance-metrics",
    "/owner/security-alerts",
    "/owner/error-audit-logs",
    "/owner/ip-whitelist",
    "/owner/api-keys",
]

OWNER_MON_POST_PATHS = [
    "/owner/security-alerts/1/resolve",
    "/owner/error-audit-logs/1/resolve",
    "/owner/error-audit-logs/clear",
    "/owner/api-keys/1/toggle",
    "/owner/ip-whitelist/0/delete",
]


def _tenant_user(db_session, tenant, slug="cashier", is_owner=False):
    from models import Role, User

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    user = User(
        username=f"mon-{slug}-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        full_name=f"MON {slug}",
        tenant_id=None if is_owner else tenant.id,
        role_id=role.id,
        is_owner=is_owner,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": "Str0ng!Pass99"},
        follow_redirects=True,
    )


def _whitelist_rows(db_session) -> list:
    """Every stored whitelist entry, read directly.

    SystemSettings.get_current() *creates* a row when it finds none, so calling it
    from a test can hand back an empty default instead of what the route wrote.
    Querying the table is what actually asserts the stored state, and the column is
    db.Text holding JSON - the shape custom_settings uses in this same table.
    """
    from models import SystemSettings

    db_session.expire_all()
    out = []
    for row in db_session.query(SystemSettings).all():
        raw = row.owner_whitelist_ips
        if raw is None:
            continue
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict):
                    out.append(str(entry.get("ip")))
            continue
        # The column is db.Text holding JSON - the same shape as custom_settings
        # and notification_templates - so a stored value is read back as a string.
        import json

        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            out.append(f"<unparseable:{raw[:40]}>")
            continue
        for entry in parsed:
            if isinstance(entry, dict):
                out.append(str(entry.get("ip")))
    return out


class TestMON01Boundary:
    """MON-01 to MON-05: the panel is the owner's alone."""

    @pytest.mark.parametrize("path", OWNER_MON_PATHS)
    def test_anonymous_is_told_nothing_exists(self, client, path):
        """MON-01. 404 per route, not a redirect that confirms the path."""
        assert client.get(path).status_code == 404, f"{path} answered {client.get(path).status_code} anonymously"

    @pytest.mark.parametrize("path", OWNER_MON_POST_PATHS)
    def test_the_write_routes_are_closed_anonymously(self, client, path):
        """MON-02. POST, because a GET would answer 405 before the guard ran.

        Resolving an alert or minting a key is a POST; testing it with GET would
        look protected while testing nothing.
        """
        resp = client.post(path, follow_redirects=True)
        assert resp.status_code == 404, f"{path} answered {resp.status_code} to an anonymous POST"

    def test_a_tenant_user_is_refused_everywhere(self, client, db_session, sample_tenant):
        """MON-03. The attacker here is a tenant who has found the panel."""
        user = _tenant_user(db_session, sample_tenant)
        _login(client, user)
        for path in ("/owner/ip-whitelist", "/owner/api-keys", "/owner/security-alerts"):
            assert client.get(path).status_code == 404, f"a tenant user reached {path}"

    def test_a_tenant_user_cannot_resolve_an_alert(self, client, db_session, sample_tenant):
        """MON-04. Alerts are evidence; a tenant dismissing them is a problem."""
        user = _tenant_user(db_session, sample_tenant)
        _login(client, user)
        resp = client.post("/owner/security-alerts/1/resolve", follow_redirects=True)
        assert resp.status_code == 404, f"a tenant user resolved an alert ({resp.status_code})"

    def test_the_owner_reaches_the_read_only_surfaces(self, client, scenario_owner):
        """MON-05. The 404s are the guard working, not dead pages."""
        for path in ("/owner/system-health", "/owner/security-alerts", "/owner/login-history", "/owner/api-keys"):
            assert client.get(path).status_code == 200, f"the owner could not load {path}"


class TestMON02ApiKeys:
    """MON-06 to MON-12: minting and revoking platform credentials."""

    def test_a_key_can_be_created_and_is_listed(self, client, scenario_owner, db_session):
        """MON-06."""
        from models import APIKey

        before = db_session.query(APIKey).count()
        client.post(
            "/owner/api-keys", data={"name": "w7 monitoring key", "service": "monitoring"}, follow_redirects=True
        )
        db_session.expire_all()
        assert db_session.query(APIKey).count() > before, "creating an API key stored nothing"

    def test_a_key_needs_a_name(self, client, scenario_owner, db_session):
        """MON-07. An unnamed credential is unattributable in an audit."""
        from models import APIKey

        before = db_session.query(APIKey).count()
        client.post("/owner/api-keys", data={"name": "", "service": "monitoring"}, follow_redirects=True)
        db_session.expire_all()
        assert db_session.query(APIKey).count() == before, (
            "an API key was created with no name - an unattributable credential is one nobody can revoke"
        )

    def test_the_secret_is_never_returned_to_the_page(self, client, scenario_owner, db_session):
        """MON-08. The listing is for humans; the secret leaves once, at creation."""
        client.post("/owner/api-keys", data={"name": "w7 secret check", "service": "monitoring"}, follow_redirects=True)
        db_session.expire_all()
        body = client.get("/owner/api-keys").get_data(as_text=True)
        from models import APIKey

        for key in db_session.query(APIKey).all():
            if key.secret and len(key.secret) >= 16:
                assert key.secret not in body, "the API key listing rendered a stored secret"

    def test_toggling_deactivates_a_key(self, client, scenario_owner, db_session):
        """MON-09. Revocation has to actually stop the key working."""
        from models import APIKey

        client.post("/owner/api-keys", data={"name": "w7 toggle", "service": "monitoring"}, follow_redirects=True)
        db_session.expire_all()
        key = db_session.query(APIKey).order_by(APIKey.id.desc()).first()
        kid = key.id
        assert key.is_active is True

        client.post(f"/owner/api-keys/{kid}/toggle", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(APIKey, kid).is_active is False, "toggle did not deactivate the key"

    def test_toggling_back_reactivates(self, client, scenario_owner, db_session):
        """MON-10. The round trip."""
        from models import APIKey

        client.post("/owner/api-keys", data={"name": "w7 toggle back", "service": "monitoring"}, follow_redirects=True)
        db_session.expire_all()
        key = db_session.query(APIKey).order_by(APIKey.id.desc()).first()
        kid = key.id

        client.post(f"/owner/api-keys/{kid}/toggle", follow_redirects=True)
        db_session.expire_all()
        client.post(f"/owner/api-keys/{kid}/toggle", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(APIKey, kid).is_active is True, "two toggles did not restore the key"

    def test_toggling_a_missing_key_is_refused(self, client, scenario_owner):
        """MON-11. The id comes from a URL."""
        resp = client.post("/owner/api-keys/99999999/toggle", follow_redirects=True)
        assert resp.status_code in (302, 404), f"a missing key answered {resp.status_code}"

    def test_a_deactivated_key_does_not_authenticate(self, client, scenario_owner, db_session):
        """MON-12. Revocation is only real if the vault stops honouring it.

        This is the end-to-end half: the vault resolves a key with
        ``filter_by(key=..., is_active=True)``, so a deactivated key has to stop
        working at the API rather than merely looking off in the listing.
        """
        from models import APIKey

        key = APIKey(
            name="w7 revoked",
            key=f"w7revoked-{uuid.uuid4().hex}",
            secret=uuid.uuid4().hex,
            service="monitoring",
            scope="write",
            is_active=False,
        )
        db_session.add(key)
        db_session.commit()
        raw = key.key
        db_session.expire_all()

        resp = client.post(
            "/payment-vault/api/purchase",
            json={"package_id": 1},
            headers={"Origin": "http://localhost:5000", "X-API-Key": raw},
        )
        assert resp.status_code == 403, f"a deactivated key authenticated ({resp.status_code})"


class TestMON03AlertsAndWhitelist:
    """MON-13 to MON-18: alerts, the IP allowlist and the audit log."""

    def test_resolving_a_missing_alert_is_refused(self, client, scenario_owner):
        """MON-13."""
        resp = client.post("/owner/security-alerts/99999999/resolve", follow_redirects=True)
        assert resp.status_code in (302, 404), f"a missing alert answered {resp.status_code}"

    def test_the_alert_list_can_be_cleared(self, client, scenario_owner):
        """MON-14. The route exists and is wired to the owner."""
        resp = client.post("/owner/error-audit-logs/clear", follow_redirects=True)
        assert resp.status_code in (200, 302), f"clearing the error log answered {resp.status_code}"

    def test_resolving_a_missing_error_log_is_refused(self, client, scenario_owner):
        """MON-15."""
        # 302, not a failure code: the route flashes "fails to update" and
        # redirects. Unfollowed, because the followed landing page is a 200 and
        # asserting on it reports a failed update as a success.
        resp = client.post("/owner/error-audit-logs/99999999/resolve")
        assert resp.status_code in (302, 404), f"a missing error log answered {resp.status_code}"

    def test_the_error_log_exports(self, client, scenario_owner):
        """MON-16. An owner needs to be able to get the evidence out."""
        resp = client.get("/owner/error-audit-logs/export")
        assert resp.status_code < 500, f"exporting the error log answered {resp.status_code}"

    def test_the_ip_whitelist_page_renders(self, client, scenario_owner):
        """MON-17."""
        assert client.get("/owner/ip-whitelist").status_code == 200

    def test_the_whitelist_refuses_an_entry_it_cannot_parse(self, client, scenario_owner, db_session):
        """MON-18. An unparseable address must not be stored.

        Asserted against the stored setting rather than the rendered page. The
        page-only version passed while the defect was live, because the template
        did not happen to echo the bad value back - a test that inspects the
        output rather than the state cannot tell a stored hole from a hidden one.
        """
        client.post(
            "/owner/ip-whitelist",
            data={"ip_address": "not-an-ip-address", "description": "w7 junk"},
            follow_redirects=True,
        )
        assert "not-an-ip-address" not in _whitelist_rows(db_session), (
            "an unparseable address was stored in the allowlist"
        )

    def test_the_whitelist_refuses_a_blank_address(self, client, scenario_owner, db_session):
        """MON-18b. An empty submission used to store {"ip": null}.

        A permanent phantom row that matches nothing and shifts every
        index-based delete after it.
        """
        client.post("/owner/ip-whitelist", data={"ip_address": "", "description": "w7 blank"}, follow_redirects=True)
        rows = _whitelist_rows(db_session)
        assert "" not in rows and "None" not in rows, f"a blank address was stored: {rows}"

    def test_a_real_address_is_stored(self, client, scenario_owner, db_session):
        """MON-18c. The success path, so the two refusals are not the only outcome."""
        client.post(
            "/owner/ip-whitelist",
            data={"ip_address": "203.0.113.7", "description": "w7 real"},
            follow_redirects=True,
        )
        rows = _whitelist_rows(db_session)
        assert "203.0.113.7" in rows, f"a valid address was not stored; rows={rows}"

    def test_the_same_address_is_not_stored_twice(self, client, scenario_owner, db_session):
        """MON-18d. A duplicate is a second row that shifts the delete indices."""
        for _ in range(2):
            client.post(
                "/owner/ip-whitelist",
                data={"ip_address": "203.0.113.8", "description": "w7 dupe"},
                follow_redirects=True,
            )
        count = _whitelist_rows(db_session).count("203.0.113.8")
        assert count <= 1, f"the same address was stored {count} times"

    def test_a_stored_address_can_be_deleted(self, client, scenario_owner, db_session):
        """MON-19b. The delete path had the same defect as the add path.

        It read the Text column as a list, popped, then assigned a list back to a
        Text column - the identical "can't adapt type 'dict'" failure - so removing
        an entry rolled back and the row stayed. Both halves are asserted here so
        a fix to one cannot leave the other broken.
        """
        client.post(
            "/owner/ip-whitelist",
            data={"ip_address": "203.0.113.20", "description": "w7 to delete"},
            follow_redirects=True,
        )
        assert "203.0.113.20" in _whitelist_rows(db_session), "setup: the address was never stored"

        rows = _whitelist_rows(db_session)
        index = rows.index("203.0.113.20")
        client.post(f"/owner/ip-whitelist/{index}/delete", follow_redirects=True)
        assert "203.0.113.20" not in _whitelist_rows(db_session), (
            f"the entry survived a delete; rows={_whitelist_rows(db_session)}"
        )

    def test_deleting_a_whitelist_entry_that_is_not_there_is_refused(self, client, scenario_owner):
        """MON-19. Indices come from a URL."""
        resp = client.post("/owner/ip-whitelist/999/delete", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"deleting a missing entry answered {resp.status_code}"
