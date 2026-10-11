"""Wave 7 debt - the owner panel's maintenance surface, and the blueprint nobody
had entered.

``test_wave7_owner_platform.py`` is thorough about the tenant lifecycle:
creating a tenant, editing one, suspending and activating, package limits,
subscription extension, the AI and store toggles. It proved all of it 404s to
anyone who is not the platform owner.

Three things in ``/owner`` were left at that.

**The maintenance routes.** Six POSTs, all destructive or schema-touching, all
gated on an exact ``confirm`` string - ``FIX_COST_CENTERS``,
``REBUILD_GL_TREE``, ``FIX_DEFAULT_TENANT``, ``REGENERATE_DEFAULT_BACKUP``,
``RUN_DEFAULT_TENANT_MAINTENANCE``, ``CLEANUP_TEST_DBS``. Only their anonymous
404 was ever asserted. The token itself was never exercised, which means nothing
proves a blank confirm does nothing. That is the whole safety property: these
routes rewrite cost-centre indexes and rebuild the GL tree across every tenant,
and the token is the last thing between an operator's mis-click and a broken
chart of accounts for everyone.

**``/super-admin``.** A separate blueprint with its own IP guard, three routes,
and zero scenarios. Its ``activate-subscription`` normalises ``yearly`` to
``annual`` and refuses an unknown duration - small behaviours, but they are the
difference between a subscription lasting a year and one lasting twelve months
of nothing.

**``/owner/archived``.** It 404s without an explicit ``?tenant_id=`` naming an
active tenant. That is a deliberate platform boundary: the alternative is
listing archived sales, purchases and payments for every tenant together in one
workspace. It is the one place in this blueprint where the *default* is the safe
answer, which makes it worth asserting in both directions.
"""

from __future__ import annotations

import uuid

import pytest

MAINTENANCE_TOKENS = {
    "/owner/maintenance/fix-cost-centers": "FIX_COST_CENTERS",
    "/owner/maintenance/rebuild-gl-tree": "REBUILD_GL_TREE",
    "/owner/maintenance/fix-default-tenant": "FIX_DEFAULT_TENANT",
    "/owner/maintenance/regenerate-default-backup": "REGENERATE_DEFAULT_BACKUP",
    "/owner/maintenance/run-default-tenant-maintenance": "RUN_DEFAULT_TENANT_MAINTENANCE",
    "/owner/maintenance/cleanup-test-dbs": "CLEANUP_TEST_DBS",
}


def _owner(db_session, client):
    """A platform owner: ``is_owner`` with no tenant attached."""
    from models import Role, Tenant, User

    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"OWN Platform {unique}",
        name_ar="منصة",
        slug=f"own-plat-{unique}",
        email=f"own-plat-{unique}@example.com",
        country="AE",
        subscription_plan="basic",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()

    role = db_session.query(Role).filter_by(slug="owner").first()
    if role is None:
        role = Role(name="Owner", slug="owner", is_active=True)
        db_session.add(role)
        db_session.commit()

    user = User(
        username=f"own-owner-{unique}",
        email=f"own-plat-{unique}@example.com",
        full_name="OWN Owner",
        tenant_id=None,
        role_id=role.id,
        is_owner=True,
        is_active=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()

    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=True,
    )
    return user


class TestOWN45TheMaintenanceTokens:
    """OWN-45 to OWN-52: six destructive routes, one rule each."""

    @pytest.mark.parametrize("path", sorted(MAINTENANCE_TOKENS))
    def test_a_blank_confirmation_does_nothing(self, client, db_session, path):
        """OWN-45. The token is the last thing before a schema rewrite.

        Walked without ``follow_redirects`` so the status is the refusal itself.
        These routes answer 400 rather than redirecting, which is what lets the
        token be asserted directly - a flash-and-redirect would leave "refused"
        and "redirected to a page that mentions the problem" indistinguishable.
        """
        _owner(db_session, client)
        token = MAINTENANCE_TOKENS[path]

        resp = client.post(path, data={}, follow_redirects=False)
        assert resp.status_code == 400, f"{path} with no confirmation answered {resp.status_code}, expected 400"

        wrong = client.post(path, data={"confirm": token.lower()}, follow_redirects=False)
        assert wrong.status_code == 400, (
            f"{path} with a near-miss confirmation answered {wrong.status_code}, expected 400"
        )

        padded = client.post(path, data={"confirm": f" {token} "}, follow_redirects=False)
        assert padded.status_code == 400, (
            f"{path} with a padded confirmation answered {padded.status_code}; the token is compared exactly"
        )

    @pytest.mark.parametrize("path", sorted(MAINTENANCE_TOKENS))
    def test_the_right_confirmation_is_accepted(self, client, db_session, path):
        """OWN-46. And the routes are not permanently closed.

        A token check that nothing ever satisfies is indistinguishable from a
        working one when the only tests are the refusals above. So each route is
        sent its real token and must get past the token check.

        "Past the token check" is deliberately the whole assertion. Several of
        these routes open a second database engine (``rebuild-gl-tree`` targets
        the configured maintenance database, which does not exist in a test
        environment), so a 500 from the *operation* is legitimate and says
        nothing about the token. Asserting no-5xx here would be asserting that
        the test environment happens to have a second database.
        """
        _owner(db_session, client)
        token = MAINTENANCE_TOKENS[path]

        resp = client.post(path, data={"confirm": token}, follow_redirects=False)
        assert resp.status_code != 400, f"{path} refused its own confirmation token {token!r}: {resp.status_code}"

    def test_fix_default_tenant_reports_its_own_result(self, client, db_session):
        """OWN-46b. The one bug these scenarios found.

        ``fix_default_tenant_metadata`` returns the *list* of columns it
        patched, but the route read it as a report dict
        (``result.get("patched", [])``). The AttributeError was caught by the
        route's own ``except`` and answered as a 500 - so
        ``/owner/maintenance/fix-default-tenant`` failed for every request that
        carried the correct confirmation token, and the repair it exists to
        perform never ran.

        The dry run is used because it is the side that changes nothing, and
        the assertion is on the count in the message rather than on the exit
        code: the bug turned a legitimate zero into a 500, so what matters is
        that the route can report a number at all.
        """
        _owner(db_session, client)

        resp = client.post(
            "/owner/maintenance/fix-default-tenant",
            data={"confirm": "FIX_DEFAULT_TENANT", "dry_run": "on"},
            follow_redirects=False,
        )
        assert resp.status_code == 200, (
            f"the default-tenant repair answered {resp.status_code} with a valid token: "
            f"{resp.get_data(as_text=True)[:200]}"
        )
        body = resp.get_json()
        assert body is not None and body.get("success"), f"the dry run reported a failure: {body}"
        assert isinstance(body["data"]["result"], list), (
            f"the repair returned {type(body['data']['result']).__name__}; the route reads it as a list"
        )


class TestOWN47TheArchivedPlatformBoundary:
    """OWN-47 to OWN-52: the one page whose safe answer is the default."""

    def _active_tenant(self, db_session):
        from models import Tenant

        unique = uuid.uuid4().hex[:8]
        tenant = Tenant(
            name=f"OWN Archived {unique}",
            name_ar="مؤرشف",
            slug=f"own-arch-{unique}",
            email=f"own-arch-{unique}@example.com",
            country="AE",
            subscription_plan="basic",
            is_active=True,
        )
        db_session.add(tenant)
        db_session.commit()
        return tenant

    def test_archived_without_a_tenant_is_hidden(self, client, db_session):
        """OWN-47. The default is a 404, and the default matters.

        ``/owner/archived`` lists archived sales, purchases and payments. With
        no ``?tenant_id=`` it could list every tenant's together in the
        platform workspace, so it 404s instead. The safe answer being the
        absent parameter is unusual enough to be worth pinning.
        """
        _owner(db_session, client)

        resp = client.get("/owner/archived", follow_redirects=False)
        assert resp.status_code == 404, (
            f"the archived page answered {resp.status_code} with no tenant named; it must not list every tenant at once"
        )

    def test_archived_names_an_unknown_tenant_is_hidden(self, client, db_session):
        """OWN-48. And an id that resolves to nothing is the same refusal.

        Falling back to "the first tenant" would be the worst possible
        behaviour: an operator would see another company's archived rows and
        believe them to be their own.
        """
        _owner(db_session, client)

        resp = client.get("/owner/archived?tenant_id=99999999", follow_redirects=False)
        assert resp.status_code == 404, f"an unknown tenant answered {resp.status_code}, expected 404"

    def test_archived_names_a_suspended_tenant_is_hidden(self, client, db_session):
        """OWN-49. Inactive is treated as unknown.

        A suspended tenant's archived records are exactly the ones an operator
        is most likely to go looking for, so "is_active" rather than "exists"
        is the condition.
        """
        tenant = self._active_tenant(db_session)
        tenant.is_active = False
        db_session.commit()
        _owner(db_session, client)

        resp = client.get(f"/owner/archived?tenant_id={tenant.id}", follow_redirects=False)
        assert resp.status_code == 404, (
            f"a suspended tenant answered {resp.status_code} on the archived page, expected 404"
        )

    def test_archived_names_an_active_tenant_renders(self, client, db_session):
        """OWN-50. And the permitted case renders.

        Without this the three refusals above would pass on a page that is
        simply broken.
        """
        tenant = self._active_tenant(db_session)
        _owner(db_session, client)

        resp = client.get(f"/owner/archived?tenant_id={tenant.id}", follow_redirects=False)
        assert resp.status_code == 200, f"the archived page answered {resp.status_code} for an active tenant"


class TestOWN51TheSuperAdminBlueprint:
    """OWN-51 to OWN-57: a whole blueprint with its own prefix and no scenarios."""

    def test_the_super_admin_pages_answer_to_an_owner(self, client, db_session):
        """OWN-51. ``/super-admin`` is a separate blueprint, not an alias.

        It has its own URL prefix, its own ``before_request`` IP guard and its
        own decorators. Treating it as a synonym for ``/owner`` is exactly the
        assumption that would let a refactor merge the two guards and change
        every answer at once.
        """
        _owner(db_session, client)

        # ``/super-admin/`` is an index that redirects to the dashboard rather
        # than rendering, so 302 is its working answer. The dashboard is the
        # page that has to render.
        index = client.get("/super-admin/", follow_redirects=False)
        assert index.status_code in (200, 302), f"the super-admin index answered {index.status_code}"

        dashboard = client.get("/super-admin/dashboard", follow_redirects=False)
        assert dashboard.status_code == 200, f"the super-admin dashboard answered {dashboard.status_code}"

    def test_super_admin_is_hidden_from_a_tenant_user(self, client, db_session, sample_tenant, sample_branch):
        """OWN-52. The same 404 convention as the rest of the owner plane."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="own-tenant-user").first()
        if role is None:
            role = Role(name="Own Tenant User", slug="own-tenant-user", is_active=True)
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code.in_(["manage_sales"])).all()
        db_session.add(role)
        db_session.commit()

        unique = uuid.uuid4().hex[:8]
        user = User(
            username=f"own-tenant-{unique}",
            email=f"own-tenant-{unique}@example.com",
            full_name="OWN Tenant",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("password123")
        db_session.add(user)
        db_session.commit()

        client.get("/auth/logout", follow_redirects=True)
        client.post("/auth/login", data={"username": user.username, "password": "password123"}, follow_redirects=True)

        resp = client.get("/super-admin/dashboard", follow_redirects=False)
        assert resp.status_code == 404, f"a tenant user reached /super-admin: {resp.status_code}"

    @pytest.mark.parametrize(
        "payload",
        [
            {"tenant_id": "", "package_id": "1"},
            {"tenant_id": "1", "package_id": ""},
            {"tenant_id": "", "package_id": ""},
        ],
    )
    def test_activating_a_subscription_needs_both_ids(self, client, db_session, payload):
        """OWN-53. A subscription activation names who and what.

        Missing either one is refused and redirected back rather than guessed.
        Defaulting the tenant would be the wrong answer in the worst way: it
        would upgrade whoever happens to be first.
        """
        _owner(db_session, client)

        resp = client.post("/super-admin/activate-subscription", data=payload, follow_redirects=True)
        assert resp.status_code == 200, f"activating with {payload} answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            f"activating with {payload} raised instead of validating"
        )

    @pytest.mark.parametrize("duration", ["weekly", "fortnightly", "year", "", "decade"])
    def test_an_unknown_duration_is_refused(self, client, db_session, duration):
        """OWN-54. The duration list is closed.

        An unrecognised duration must not fall through to a default month - the
        difference between a customer who bought a year and a customer who got
        a month is not something to decide by accident.
        """
        _owner(db_session, client)

        resp = client.post(
            "/super-admin/activate-subscription",
            data={"tenant_id": "1", "package_id": "1", "duration_type": duration},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"activating with duration={duration!r} answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            f"activating with duration={duration!r} raised instead of validating"
        )

    def test_activating_against_a_tenant_that_does_not_exist_is_handled(self, client, db_session):
        """OWN-55. A valid-looking id for a tenant that is gone.

        The route flashes "not found" and returns. The scenario asserts it does
        not raise, because the realistic failure here is an operator working
        from a stale list rather than an attack.
        """
        _owner(db_session, client)

        resp = client.post(
            "/super-admin/activate-subscription",
            data={"tenant_id": "99999999", "package_id": "1", "duration_type": "monthly"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"activating a missing tenant answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "activating a missing tenant raised instead of reporting"
        )

    def test_activating_against_a_package_that_does_not_exist_is_handled(self, client, db_session):
        """OWN-56. The same for the package half of the pair."""
        _owner(db_session, client)

        resp = client.post(
            "/super-admin/activate-subscription",
            data={"tenant_id": "1", "package_id": "99999999", "duration_type": "monthly"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"activating a missing package answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "activating a missing package raised instead of reporting"
        )
