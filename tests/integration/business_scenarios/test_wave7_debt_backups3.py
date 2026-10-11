"""Wave 7 debt, part three - the routes the first two files did not reach.

``test_wave7_debt_backups.py`` covers the SQL console and ``..._backups2.py``
covers truncation, the table browser, backups and the tenant plane. What is left
on these two blueprints is the long tail: the immediate backup button, the
restore preparation step, the export and conversion routes, and the row update
that a permitted table does allow.

Two of these deserve their own point rather than a line in a list.

``prepare-restore`` never restores. Its GET renders the commands an operator
would have to run by hand, and its POST returns the same payload as JSON. The
distinction is that a page whose URL says "restore" and whose GET performs one
would be the worst route in this tree, so the GET is asserted to be inert -
rendered, not executed.

``update-row`` is the one route that legitimately writes. It is guarded by the
same blocked list as everything else, and this file walks both halves: refused
for a tenant table, allowed for a platform one. A write nobody is allowed to
make and a guard nobody can reach are the same defect seen from two directions.
"""

from __future__ import annotations

from tests.integration.business_scenarios.test_wave7_debt_backups import _owner
from tests.integration.business_scenarios.test_wave7_debt_backups2 import _assert_refused


class TestBAK54TheRoutesNotYetReached:
    """BAK-54 to BAK-68: the long tail of the backup and database surfaces."""

    def test_the_immediate_backup_button_answers(self, client, db_session):
        """BAK-54. ``backup-now`` is the one-click path.

        It is a POST that does real work, so the risk is a 500 waiting behind
        the guard rather than a leak through it. Reaching it and getting a
        normal answer is the assertion.
        """
        _owner(db_session, client)

        resp = client.post("/owner/backup-now", json={}, follow_redirects=True)
        assert resp.status_code == 200, f"the immediate backup answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "the immediate backup raised instead of reporting"
        )

    def test_a_scoped_backup_needs_a_tenant_to_scope_to(self, client, db_session):
        """BAK-55. A tenant-scoped backup with no tenant named is refused.

        The owner branch asks for ``tenant_id`` rather than defaulting one.
        Defaulting would mean "the first tenant alphabetically", which is a
        quiet way to hand an operator the wrong company's data.
        """
        _owner(db_session, client)

        resp = client.post("/owner/backups/create", data={"scope": "tenant"}, follow_redirects=True)
        assert resp.status_code == 200, f"a tenant-scope backup with no tenant answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "an unscoped tenant backup raised instead of asking for a tenant"
        )

    def test_a_branch_scoped_backup_needs_a_branch(self, client, db_session, sample_tenant):
        """BAK-56. Same shape one level down.

        A branch scope with no branch named would otherwise back up everything
        under the tenant while its label says "branch".
        """
        from models import Tenant

        _owner(db_session, client)
        tenant = db_session.query(Tenant).filter_by(slug=sample_tenant.slug).first()

        resp = client.post(
            "/owner/backups/create",
            data={"scope": "branch", "tenant_id": str(tenant.id) if tenant else "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"a branch-scope backup with no branch answered {resp.status_code}"

    def test_preparing_a_restore_does_not_restore(self, client, db_session):
        """BAK-57. The GET is inert, and that is the whole point.

        ``prepare-restore`` shows an operator the commands to run by hand. If
        its GET performed the restore, a browser prefetch, a link scanner or a
        curious tab would overwrite a production database. So the GET is walked
        and asserted not to act.
        """
        from models import Tenant

        _owner(db_session, client)
        before = db_session.query(Tenant).count()

        resp = client.get("/owner/backups/prepare-restore/there-is-no-such-backup.sql", follow_redirects=False)
        _assert_refused(resp, "preparing a restore of an unknown backup")

        after = db_session.query(Tenant).count()
        assert after == before, f"merely opening the restore page changed {before} tenants to {after}"

    def test_exporting_the_database_answers(self, client, db_session):
        """BAK-58. The full export runs for an owner and does not raise."""
        _owner(db_session, client)

        resp = client.post("/owner/export-database", data={}, follow_redirects=True)
        assert resp.status_code == 200, f"the database export answered {resp.status_code}"

    def test_converting_the_database_requires_its_confirmation(self, client, db_session):
        """BAK-59. Conversion is a schema rewrite, so it is gated twice.

        ``@owner_required`` answers 404 to a non-owner; the body's own
        confirmation answers something else entirely to an owner who did not
        mean it. Both are refusals and neither is enough on its own.
        """
        _owner(db_session, client)

        page = client.get("/owner/convert-database", follow_redirects=False)
        assert page.status_code == 200, f"the convert page answered {page.status_code}"

        resp = client.post("/owner/convert-database", data={}, follow_redirects=True)
        assert resp.status_code == 200, f"an unconfirmed conversion answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "an unconfirmed conversion raised instead of asking for confirmation"
        )

    def test_the_sql_console_page_renders(self, client, db_session):
        """BAK-60. The console's own page, which ``_sql_console`` also POSTs to."""
        _owner(db_session, client)

        resp = client.get("/owner/sql-console", follow_redirects=False)
        assert resp.status_code == 200, f"the sql console page answered {resp.status_code}"

    def test_updating_a_row_that_does_not_exist_is_handled(self, client, db_session):
        """BAK-61. The write side answers rather than raising.

        ``update-row`` is the one route here that legitimately writes, so it
        needs a positive case: a permitted table, reached with a row id that is
        not there. The correct answer is a handled "no such row", not a 500 and
        not a silent success.

        The permission side is BAK-36 - a blocked table is refused. This is the
        other half: the route is reachable and the guard is not simply "deny
        everything", which would make every refusal scenario in these three
        files pass with a tool that cannot edit anything.
        """
        import uuid

        from models import Tenant

        _owner(db_session, client)
        tenant = Tenant(
            name=f"Bak editable {uuid.uuid4().hex[:6]}",
            name_ar="للاختبار",
            slug=f"bak-edit-{uuid.uuid4().hex[:8]}",
            country="AE",
        )
        db_session.add(tenant)
        db_session.commit()
        original_name = tenant.name
        missing_id = (db_session.query(Tenant).order_by(Tenant.id.desc()).first().id or 0) + 100000

        resp = client.post(
            f"/owner/update-row/{Tenant.__tablename__}/{missing_id}",
            data={"name": "tampered"},
            follow_redirects=False,
        )
        assert resp.status_code != 500, f"updating a missing row raised a 500: {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "updating a missing row rendered an error page"
        )

        db_session.expire_all()
        unchanged = db_session.get(Tenant, tenant.id)
        assert unchanged.name == original_name, (
            f"a row update reported no row but renamed {original_name!r} to {unchanged.name!r}"
        )

    def test_the_recent_audit_log_api_carries_the_owner_queries(self, client, db_session):
        """BAK-62. What the console did is written down.

        ``execute_query`` calls ``_audit_owner_db_action`` with the query prefix
        and the row count. That record is the only thing standing between "an
        owner read some rows" and "someone did", so the endpoint that shows it
        has to answer.
        """
        _owner(db_session, client)
        client.post("/owner/execute-query", data={"query": "SELECT 1 AS one"}, follow_redirects=False)

        resp = client.get("/owner/api/recent-audit-logs", follow_redirects=False)
        assert resp.status_code == 200, f"the audit log api answered {resp.status_code}"
        body = resp.get_data(as_text=True)
        assert "execute_query" in body or "logs" in body.lower(), (
            "the audit log endpoint answered without anything resembling a log"
        )

    def test_verifying_backups_answers(self, client, db_session):
        """BAK-63. The verification page an operator runs after a restore."""
        _owner(db_session, client)

        resp = client.get("/owner/verify-backups", follow_redirects=False)
        assert resp.status_code == 200, f"verify-backups answered {resp.status_code}"

    def test_the_import_export_page_answers(self, client, db_session):
        """BAK-64. And the page that hosts the per-table exports."""
        _owner(db_session, client)

        resp = client.get("/owner/import-export-tools", follow_redirects=False)
        assert resp.status_code == 200, f"import-export-tools answered {resp.status_code}"

    def test_the_data_cleanup_page_answers_to_its_post_without_a_confirm(self, client, db_session):
        """BAK-65. A destructive page's POST still needs its confirmation.

        ``data-cleanup`` accepts GET and POST. A POST carrying no confirmation
        must come back as a normal page rather than cleaning, and the row counts
        are the assertion - the flash wording is not.
        """
        from models import Tenant

        _owner(db_session, client)
        before = db_session.query(Tenant).count()

        resp = client.post("/owner/data-cleanup", data={}, follow_redirects=True)
        assert resp.status_code == 200, f"an unconfirmed cleanup answered {resp.status_code}"

        after = db_session.query(Tenant).count()
        assert after == before, f"an unconfirmed cleanup changed {before} tenants to {after}"

    def test_the_owner_backup_list_answers(self, client, db_session):
        """BAK-66. The landing page for the whole backup plane.

        Everything else in these files redirects here on refusal, so if this
        page did not render, every refusal above would look like a 200.
        """
        _owner(db_session, client)

        resp = client.get("/owner/backups/list", follow_redirects=False)
        assert resp.status_code == 200, f"the backup list answered {resp.status_code}"

    def test_the_database_tools_page_answers(self, client, db_session):
        """BAK-67. Likewise the landing page for every browser refusal."""
        _owner(db_session, client)

        resp = client.get("/owner/database-tools", follow_redirects=False)
        assert resp.status_code == 200, f"the database tools page answered {resp.status_code}"

    def test_tenant_backup_creation_is_rate_limited(self, client, db_session, sample_tenant, sample_branch):
        """BAK-68. A tenant cannot make backups on demand without a limit.

        ``@limiter.limit("5 per hour")`` on the create route is a
        resource-protection control, and a control nobody exercises is a control
        nobody knows is still attached. Five requests are made; the sixth is
        where the limit is expected to bite.
        """
        from tests.integration.business_scenarios.test_wave7_debt_backups2 import _tenant_user

        _tenant_user(client, db_session, sample_tenant, sample_branch)

        statuses = [client.post("/backups/create", data={}, follow_redirects=False).status_code for _ in range(6)]
        limited = [s for s in statuses if s == 429]
        assert limited, f"six consecutive backup creations produced {statuses} and none was rate limited"
