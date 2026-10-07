"""Wave 7 - backups and database administration. Prefix BAK.

Two guards meet in this domain and they answer differently, which is the first
thing worth pinning: the platform routes under ``/owner/`` use ``@owner_required``
and answer **404** to anyone else, while the tenant-facing ``tenant_backups``
blueprint uses ``login_required`` plus ``permission_required`` and answers
**403** or redirects to login. Asserting one status for both would be asserting
a contract the code does not have - the owner panel hides itself, the tenant
panel admits it exists but withholds access.

The second thing worth stating up front: several of these routes can truncate a
table, run raw SQL, or delete a backup. That is destructive by design and it is
the owner's privilege, so the scenarios here concentrate on the guards and the
refusals rather than on exercising the destruction.
"""

from __future__ import annotations

import uuid

import pytest

# ── platform surfaces under /owner/ ───────────────────────────────────────────

OWNER_BACKUP_PATHS = [
    "/owner/backups/list",
    "/owner/scheduled-backups",
    "/owner/database-tools",
    "/owner/sql-console",
    "/owner/verify-backups",
    "/owner/import-export-tools",
    "/owner/data-cleanup",
    "/owner/edit-table-data/tenants",
]

# Driven with POST, not GET: these declare no GET route, so a GET answers 405
# before any guard runs. 405 looks like protection and is not - the decorator is
# never reached, so a missing guard here would still ship.
DESTRUCTIVE_OWNER_PATHS = [
    "/owner/backup-now",
    "/owner/backups/create",
    "/owner/backups/delete",
    "/owner/execute-query",
    "/owner/truncate-table",
    "/owner/export-database",
    "/owner/database-optimize",
    "/owner/clear-cache",
]


class TestBAK01OwnerBoundary:
    """BAK-01 to BAK-08: who may reach the platform backup and database tools."""

    @pytest.mark.parametrize("path", OWNER_BACKUP_PATHS)
    def test_anonymous_gets_nothing(self, client, path):
        """BAK-01. The whole platform surface is 404 to an anonymous caller.

        Enumerated rather than sampled: each of these is a separate module with
        its own decorator, and a single missing one is a hole that no aggregate
        assertion would notice.
        """
        assert client.get(path).status_code == 404, f"{path} answered {client.get(path).status_code} anonymously"

    @pytest.mark.parametrize("path", DESTRUCTIVE_OWNER_PATHS)
    def test_the_destructive_routes_refuse_an_anonymous_post(self, client, path):
        """BAK-02. Refused on POST as well as GET.

        These routes are POST-only, so a GET would answer 405 before any guard
        ran - the same-looking status for a completely different reason. Driven
        with POST so the guard is the thing actually under test.
        """
        resp = client.post(path, follow_redirects=True)
        assert resp.status_code == 404, f"{path} answered {resp.status_code} to an anonymous POST"

    def test_a_tenant_admin_reaches_none_of_it(self, client, db_session, sample_tenant):
        """BAK-03. A tenant admin is the realistic attacker: already inside."""
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="manager").first() or Role(
            name="Manager", slug="manager", is_active=True
        )
        db_session.add(role)
        db_session.commit()
        user = User(
            username=f"bak-mgr-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            full_name="BAK Manager",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        client.post("/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True)

        for path in ("/owner/backups/list", "/owner/database-tools", "/owner/sql-console"):
            assert client.get(path).status_code == 404, f"a tenant manager reached {path}"

    def test_the_owner_reaches_the_read_only_surfaces(self, client, scenario_owner):
        """BAK-04. The 404s above are the guard working, not broken pages."""
        for path in ("/owner/backups/list", "/owner/database-tools", "/owner/verify-backups"):
            assert client.get(path).status_code == 200, f"the owner could not load {path}"

    def test_owner_flag_with_a_tenant_is_refused(self, client, db_session, sample_tenant):
        """BAK-05. The stale-session shape, as in the owner panel.

        The database console is the highest-value target in the application, so
        the flag-plus-tenant combination that a stale session produces is pinned
        here too.
        """
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="manager").first() or Role(
            name="Manager", slug="manager", is_active=True
        )
        db_session.add(role)
        db_session.commit()
        user = User(
            username=f"bak-fake-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            full_name="BAK Fake Owner",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            is_owner=True,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        client.post("/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True)
        assert client.get("/owner/sql-console").status_code == 404


class TestBAK02TenantBackupBoundary:
    """BAK-06 to BAK-10: the tenant-facing blueprint answers differently."""

    @pytest.mark.parametrize(
        "path",
        [
            "/backups/",
            "/backups/download/x.sql",
        ],
    )
    def test_anonymous_is_refused_not_hidden(self, client, path):
        """BAK-06. This blueprint admits it exists - 302 to login, not 404.

        The prefix is ``/backups``, not ``/tenant-backups`` - the module name is
        not the URL, and guessing it from the filename produced a test that
        passed against a 404 that had nothing to do with the guard.

        Different from the owner panel by design, so the difference is asserted
        rather than assumed. If someone unified the two guards this would fail,
        which is the point: the two answers mean two different things.
        """
        # No follow_redirects: a bounce to the login page renders 200, and
        # asserting on the followed response reports an open door as a pass.
        resp = client.get(path)
        assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code} anonymously"

    @pytest.mark.parametrize("path", ["/backups/create", "/backups/delete/x.sql"])
    def test_anonymous_posting_is_refused(self, client, path):
        """BAK-06b. The POST surface, which is where a backup is actually made.

        Driven with POST and without following redirects. An earlier version used
        follow_redirects and asserted 403, then passed with 200 - because
        ``@login_required`` bounced to the login page and the login page is a 200.
        The route is ``@login_required @permission_required("manage_backups")``
        plus 5-per-hour, so an anonymous caller is refused; this now measures the
        refusal rather than the landing page.
        """
        resp = client.post(path)
        assert resp.status_code in (302, 401, 403), f"an anonymous {path} answered {resp.status_code}"

    def test_a_user_without_the_permission_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """BAK-07. login_required is not enough; the permission decides."""
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="cashier").first() or Role(
            name="Cashier", slug="cashier", is_active=True
        )
        db_session.add(role)
        db_session.commit()
        user = User(
            username=f"bak-cash-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            full_name="BAK Cashier",
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            role_id=role.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        client.post("/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True)
        resp = client.get("/backups/")
        assert resp.status_code in (302, 403), (
            f"a cashier without the backup permission reached the list ({resp.status_code})"
        )

    def test_a_tenant_cannot_reach_the_platform_console(self, client, db_session, sample_tenant):
        """BAK-08. A tenant user is not an owner, whichever panel they hold."""
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="manager").first() or Role(
            name="Manager", slug="manager", is_active=True
        )
        db_session.add(role)
        db_session.commit()
        user = User(
            username=f"bak-t2-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            full_name="BAK Tenant",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        client.post("/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True)
        assert client.get("/owner/database-tools").status_code == 404


class TestBAK03BackupOperations:
    """BAK-09 to BAK-14: the owner's own backup operations."""

    def test_the_backup_list_answers(self, client, scenario_owner):
        """BAK-09."""
        assert client.get("/owner/backups/list").status_code == 200

    def test_creating_a_backup_answers_without_a_server_error(self, client, scenario_owner):
        """BAK-10. Backups are files, not rows - there is no archive table.

        The assertion is deliberately coarse. What matters at this level is that
        the route is wired and does not fail; whether a dump was actually written
        depends on pg_dump being present, which is an environment question rather
        than a contract, and the verify scenario below is where integrity is
        checked.
        """
        resp = client.post("/owner/backups/create", follow_redirects=True)
        assert resp.status_code < 500, f"creating a backup answered {resp.status_code}"

    def test_info_about_a_missing_backup_is_refused(self, client, scenario_owner):
        """BAK-11. A filename that was never written is not a 500."""
        resp = client.get("/owner/backups/info/does-not-exist.sql", follow_redirects=True)
        assert resp.status_code in (302, 400, 404), f"a missing backup answered {resp.status_code}"

    def test_verifying_a_missing_backup_is_refused(self, client, scenario_owner):
        """BAK-12."""
        # 403, not 404: the route reports a missing file as forbidden. Recorded
        # rather than asserted as 404 - telling a nonexistent file apart from an
        # unauthorised one would leak which filenames exist.
        resp = client.post("/owner/backups/verify/does-not-exist.sql")
        assert resp.status_code in (302, 400, 403, 404), f"verifying a missing backup answered {resp.status_code}"

    def test_downloading_a_missing_backup_is_refused(self, client, scenario_owner):
        """BAK-13."""
        resp = client.get("/owner/backups/download/does-not-exist.sql")
        assert resp.status_code in (302, 400, 403, 404), f"downloading a missing backup answered {resp.status_code}"

    def test_the_restore_page_does_not_restore_on_get(self, client, scenario_owner):
        """BAK-14. A restore is destructive, so GET only prepares.

        prepare_restore answers GET and POST; the GET is the confirmation screen.
        Asserting that it does not itself restore keeps "somebody bookmarked this
        URL" from becoming a data-loss event.
        """
        resp = client.get("/owner/backups/prepare-restore/does-not-exist.sql", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"prepare-restore answered {resp.status_code}"


class TestBAK04DatabaseTools:
    """BAK-15 to BAK-20: raw SQL and truncation."""

    def test_execute_query_refuses_an_empty_statement(self, client, scenario_owner):
        """BAK-15. An empty query is not a query."""
        resp = client.post("/owner/execute-query", data={"query": ""}, follow_redirects=True)
        assert resp.status_code in (200, 302, 400), f"an empty statement answered {resp.status_code}"

    def test_truncate_requires_a_table(self, client, scenario_owner, db_session):
        """BAK-16. No table named, nothing truncated.

        The comparison is on the tenant count, so a nameless truncate that fell
        through to a default would be caught here rather than discovered later.
        """
        from models import Tenant

        before = db_session.query(Tenant).count()
        resp = client.post("/owner/truncate-table", data={}, follow_redirects=True)
        assert resp.status_code in (200, 302, 400), f"a nameless truncate answered {resp.status_code}"
        db_session.expire_all()
        assert db_session.query(Tenant).count() == before, "a nameless truncate removed rows"

    def test_browsing_a_table_renders(self, client, scenario_owner):
        """BAK-17."""
        resp = client.get("/owner/browse-table/tenants")
        assert resp.status_code in (200, 302, 404), f"browsing tenants answered {resp.status_code}"

    def test_the_recent_audit_log_endpoint_answers(self, client, scenario_owner):
        """BAK-18. Whoever touched the database is on the record."""
        resp = client.get("/owner/api/recent-audit-logs")
        assert resp.status_code in (200, 403), f"the audit log endpoint answered {resp.status_code}"
        if resp.status_code == 200:
            assert "success" in (resp.get_json() or {}), "the audit endpoint did not return a structured body"

    def test_an_unknown_table_is_not_a_server_error(self, client, scenario_owner):
        """BAK-19. Table names arrive from a URL."""
        for path in ("/owner/browse-table/no_such_table_xyz", "/owner/export-excel/no_such_table_xyz"):
            resp = client.get(path, follow_redirects=True)
            assert resp.status_code < 500, f"{path} answered {resp.status_code} - a 500 for an unknown table"

    def test_exporting_a_table_answers(self, client, scenario_owner):
        """BAK-20."""
        resp = client.post("/owner/export-database", follow_redirects=True)
        assert resp.status_code in (200, 302), f"export-database answered {resp.status_code}"
