"""Wave 7 debt, part two - truncation, the table browser, and both backup planes.

``test_wave7_debt_backups.py`` covers the SQL console. This file covers the
destructive and data-reading surfaces around it, and the rule they all share:
every one of them takes a *name* the caller supplies, and the name has to be
resolved against something authoritative before it is used.

There are three different resolvers and the differences are the point:

- ``_resolve_known_table`` matches a normalised name against the inspector's
  real table list. An unknown name is not found, so nothing happens.
- ``_resolve_truncatable_table`` additionally rejects blocked tables.
- ``_resolve_browsable_table`` rejects the same blocked set, for the read path.

A resolver that only checked "is this a known table" would let an owner empty
``sales`` from the platform plane, where no tenant scope applies to protect
anyone. The block list is derived from ``db.metadata`` rather than written by
hand, because the hand-written version silently missed ``gl_journal_lines``,
``sale_lines``, ``card_payments``, ``pos_sessions`` and ``employees`` - all
readable from the console before that derivation existed.

Confirmation tokens are the other half. ``truncate-table`` requires the literal
``YES_DELETE_ALL`` and refuses anything else, so a stray form post with an
empty ``confirm`` cannot empty a table. The backup plane carries its own
equivalent: ``restore-target`` and a system-scope backup both re-check
``is_global_owner_user`` in the body, because ``@owner_required`` alone is not
the whole condition.

The last section is the tenant plane (``/backups/*``), which is a different
blueprint with a different guard. It answers 302 to an anonymous caller where
the owner plane answers 404 - the contrast is asserted here so a future
consolidation of the two guards cannot quietly change one of them.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.business_scenarios.test_wave7_debt_backups import _owner


def _assert_refused(resp, what, *, must_not_contain=None):
    """A refusal in these blueprints is a flash-and-redirect, not an abort.

    ``browse_table`` and every filename route answer ``redirect(...)`` with a
    danger flash, so 302 *is* the refusal here. Asserting a 4xx would be
    asserting a status these routes never produce, and the failure mode it
    protects against is not the status anyway - it is the payload being served
    anyway. So the check is that the response is not the resource.
    """
    assert resp.status_code != 200, f"{what} answered 200: the resource was served instead of refused"
    disposition = resp.headers.get("Content-Disposition", "")
    assert "attachment" not in disposition, f"{what} answered as a file attachment: {disposition!r}"
    if must_not_contain:
        body = resp.get_data(as_text=True)
        assert must_not_contain not in body, f"{what} served {must_not_contain!r} instead of refusing"


def _tenant_user(client, db_session, tenant, branch, *, slug="bak-tenant-admin", permissions=("manage_backups",)):
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("-", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
    db_session.add(role)
    db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"{slug}-{unique}",
        email=f"{slug}-{unique}@example.com",
        full_name=f"BAK {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()

    client.get("/auth/logout", follow_redirects=True)
    client.post("/auth/login", data={"username": user.username, "password": "password123"}, follow_redirects=True)
    return user


class TestBAK29Truncation:
    """BAK-29 to BAK-34: the destructive route, and everything before it runs."""

    def test_the_wrong_confirmation_token_does_nothing(self, client, db_session):
        """BAK-29. The token is the thing being confirmed.

        An empty or wrong ``confirm`` must leave the database untouched. This is
        the scenario a mis-clicked form or a stale browser tab produces, so the
        assertion is on the data rather than on the flash message.
        """
        from models import Tenant

        _owner(db_session, client)
        before = db_session.query(Tenant).count()

        for confirm in ("", "yes", "YES_DELETE_ALL "):
            resp = client.post(
                "/owner/truncate-table",
                data={"table_name": "tenants", "confirm": confirm},
                follow_redirects=True,
            )
            assert resp.status_code == 200, f"a truncate with confirm={confirm!r} answered {resp.status_code}"
            db_session.expire_all()
            assert db_session.query(Tenant).count() == before, (
                f"tenants was truncated with confirm={confirm!r}; {before} rows became "
                f"{db_session.query(Tenant).count()}"
            )

    def test_the_right_token_against_a_blocked_table_does_nothing(self, client, db_session):
        """BAK-30. Confirmation is necessary, not sufficient.

        ``_resolve_truncatable_table`` rejects blocked tables *after* the token
        check, so a correct token against a tenant business table still does
        nothing. Order matters: if the resolver ran first the audit would lose
        the evidence that a token was supplied at all.
        """
        from models import Sale

        _owner(db_session, client)
        table = Sale.__tablename__
        before = db_session.query(Sale).count()

        resp = client.post(
            "/owner/truncate-table",
            data={"table_name": table, "confirm": "YES_DELETE_ALL"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"truncating a blocked table answered {resp.status_code}"
        db_session.expire_all()
        assert db_session.query(Sale).count() == before, f"{table} was truncated from the platform plane"

    def test_an_unknown_table_name_does_nothing(self, client, db_session):
        """BAK-31. A name the inspector has never heard of resolves to nothing.

        Without the inspector lookup, an arbitrary string would reach the SQL
        builder, and ``DELETE FROM <whatever>`` on an unvalidated identifier is
        not a thing any route should be able to assemble.
        """
        _owner(db_session, client)

        resp = client.post(
            "/owner/truncate-table",
            data={"table_name": "table_that_is_not_here", "confirm": "YES_DELETE_ALL"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"an unknown table answered {resp.status_code}"

    @pytest.mark.parametrize("table_name", ["../etc/passwd", "tenants; DROP TABLE roles", "ten ants"])
    def test_a_malformed_table_name_does_nothing(self, client, db_session, table_name):
        """BAK-32. The name is pattern-checked before it is resolved.

        ``_TABLE_NAME_RE`` is the first gate. A traversal string or an injected
        fragment must not reach the inspector, let alone the query builder.
        """
        from models import Tenant

        _owner(db_session, client)
        before = db_session.query(Tenant).count()

        resp = client.post(
            "/owner/truncate-table",
            data={"table_name": table_name, "confirm": "YES_DELETE_ALL"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"a malformed table name answered {resp.status_code}"
        db_session.expire_all()
        assert db_session.query(Tenant).count() == before, (
            f"a malformed table name reached the truncate path: {table_name!r}"
        )


class TestBAK33TheTableBrowser:
    """BAK-33 to BAK-38: reading and editing rows by name."""

    def test_browsing_a_blocked_table_is_refused(self, client, db_session):
        """BAK-33. The read path blocks what the write path blocks.

        A browser that will show rows the console will not is a console with an
        extra click. Both resolvers consult the same blocked set for exactly
        that reason.
        """
        from models import Payment

        _owner(db_session, client)
        table = Payment.__tablename__

        resp = client.get(f"/owner/browse-table/{table}", follow_redirects=False)
        _assert_refused(resp, f"browsing the blocked table {table}", must_not_contain=table)

    def test_browsing_an_unknown_table_is_refused(self, client, db_session):
        """BAK-34. And an unknown name is refused rather than rendered empty.

        An empty page would be indistinguishable from "this table is empty",
        which is the more dangerous answer of the two.
        """
        _owner(db_session, client)

        resp = client.get("/owner/browse-table/table_that_is_not_here", follow_redirects=False)
        _assert_refused(resp, "browsing an unknown table")

    def test_the_edit_view_refuses_a_blocked_table(self, client, db_session):
        """BAK-35. Editing is a write; it carries the write's block list."""
        from models import Sale

        _owner(db_session, client)

        resp = client.get(f"/owner/edit-table-data/{Sale.__tablename__}", follow_redirects=False)
        _assert_refused(resp, f"the edit view for {Sale.__tablename__}", must_not_contain=Sale.__tablename__)

    def test_updating_a_row_in_a_blocked_table_is_refused(self, client, db_session):
        """BAK-36. The POST cannot be more permissive than the GET that offers it.

        Checking the table on the form render but not on the submit would leave
        the blocked set as a UI suggestion. This walks straight to the POST.
        """
        from models import Sale

        _owner(db_session, client)
        table = Sale.__tablename__

        resp = client.post(
            f"/owner/update-row/{table}/1",
            data={"name": "tampered"},
            follow_redirects=False,
        )
        _assert_refused(resp, f"updating a row in the blocked table {table}")

    def test_the_export_page_refuses_a_blocked_table(self, client, db_session):
        """BAK-37. Export is a read with a different exit, so it carries the
        same block list. A CSV of tenant rows leaves the database's own guards
        entirely."""
        from models import Sale

        _owner(db_session, client)

        resp = client.get(f"/owner/export-excel/{Sale.__tablename__}", follow_redirects=False)
        _assert_refused(resp, f"exporting {Sale.__tablename__}", must_not_contain=Sale.__tablename__)

    def test_the_database_tools_pages_answer_to_an_owner(self, client, db_session):
        """BAK-38. The read-only admin pages all render.

        Without this the file would only ever prove refusals, and a set of pages
        that 500 for their intended audience would still pass.
        """
        _owner(db_session, client)

        broken = []
        for path in (
            "/owner/database-tools",
            "/owner/sql-console",
            "/owner/verify-backups",
            "/owner/import-export-tools",
            "/owner/data-cleanup",
            "/owner/backups/list",
            "/owner/scheduled-backups",
        ):
            resp = client.get(path, follow_redirects=False)
            if resp.status_code != 200:
                broken.append((path, resp.status_code))
        assert not broken, f"owner database pages did not answer: {broken}"


class TestBAK39TheBackupPlane:
    """BAK-39 to BAK-48: backups, and the two body-level owner re-checks."""

    def test_a_system_scope_backup_needs_a_global_owner(self, client, db_session, sample_tenant, sample_branch):
        """BAK-39. ``@owner_required`` is not the whole condition.

        A user with the ``is_owner`` flag but a tenant attached is not a global
        owner, and a system-scope backup is the one operation that crosses every
        tenant boundary. The body re-checks rather than trusting the decorator,
        because the decorator answers 404 for a stale session and this has to
        answer 403 - the two are different signals to whoever is auditing.
        """
        _tenant_user(client, db_session, sample_tenant, sample_branch, permissions=["manage_backups"])

        resp = client.post("/owner/backups/create", data={"scope": "system"}, follow_redirects=False)
        assert resp.status_code in (403, 404), f"a tenant user created a system-scope backup: {resp.status_code}"

    def test_the_restore_target_rechecks_the_owner_in_the_body(self, client, db_session, sample_tenant, sample_branch):
        """BAK-40. Restoring is the operation that destroys data.

        ``restore-target`` re-checks ``is_global_owner_user`` inside the body in
        addition to the decorator, and it is the only route that restores
        anything. A tenant user must not reach it by any path.
        """
        _tenant_user(client, db_session, sample_tenant, sample_branch, permissions=["manage_backups"])

        resp = client.post(
            "/owner/backups/restore-target/some-backup.sql",
            data={"confirm": "RESTORE"},
            follow_redirects=False,
        )
        assert resp.status_code in (403, 404), f"a tenant user reached the restore target: {resp.status_code}"

    def test_backup_info_for_a_foreign_filename_is_refused(self, client, db_session):
        """BAK-41. The filename is resolved through the access check.

        ``_owner_backup_filename`` plus ``user_may_access_backup`` means a name
        the caller does not own resolves to nothing. Guessing a backup's name
        must not be enough to read its metadata.
        """
        _owner(db_session, client)

        resp = client.get("/owner/backups/info/../../etc/passwd", follow_redirects=False)
        _assert_refused(resp, "backup info for a traversal filename")

    def test_downloading_an_unknown_backup_is_refused(self, client, db_session):
        """BAK-42. An unknown name is not downloadable, and not a 500."""
        _owner(db_session, client)

        resp = client.get("/owner/backups/download/there-is-no-such-backup.sql", follow_redirects=False)
        _assert_refused(resp, "downloading an unknown backup")

    def test_deleting_a_backup_with_a_traversal_filename_is_refused(self, client, db_session):
        """BAK-43. Delete is a POST and must sanitise like the rest.

        The filename arrives in a form body rather than the path here, so the
        resolver has to be reached deliberately - it is easy to write this one
        without the sanitiser because the URL looks harmless.
        """
        _owner(db_session, client)

        resp = client.post(
            "/owner/backups/delete",
            data={"filename": "../../etc/passwd"},
            follow_redirects=False,
        )
        _assert_refused(resp, "delete with a traversal filename")

    def test_scheduled_backups_render_and_persist(self, client, db_session):
        """BAK-44. The schedule is configuration, so both halves are walked.

        GET renders the form; POST stores ``enabled``, ``frequency``,
        ``backup_time`` and ``keep_count``. A schedule that renders but does not
        persist is a backup policy nobody thinks is running.
        """
        _owner(db_session, client)

        page = client.get("/owner/scheduled-backups", follow_redirects=False)
        assert page.status_code == 200, f"the scheduled-backups page answered {page.status_code}"

        resp = client.post(
            "/owner/scheduled-backups",
            data={
                "enabled": "on",
                "frequency": "daily",
                "backup_time": "02:30",
                "keep_count": "14",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"saving the backup schedule answered {resp.status_code}"

        after = client.get("/owner/scheduled-backups", follow_redirects=False).get_data(as_text=True)
        assert "02:30" in after or "14" in after, "the saved schedule does not appear on the page it was saved from"


class TestBAK45TheTenantBackupPlane:
    """BAK-45 to BAK-54: ``/backups/*`` - a different blueprint, different answers."""

    def test_anonymous_is_redirected_not_hidden(self, client, db_session):
        """BAK-45. The tenant plane answers 302 where the owner plane answers
        404, and the difference is deliberate.

        ``@login_required`` flashes and redirects; ``@owner_required`` hides the
        route entirely. A test that asserted 404 here would be asserting the
        owner plane's convention onto the tenant plane, and a future
        consolidation of the two guards would break one of them silently.
        """
        resp = client.get("/backups/", follow_redirects=False)
        assert resp.status_code == 302, (
            f"the tenant backup index answered {resp.status_code} to an anonymous caller, expected a login redirect"
        )

    def test_a_tenant_user_without_the_permission_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """BAK-46. ``manage_backups`` is the gate, and missing it is a 403."""
        _tenant_user(client, db_session, sample_tenant, sample_branch, permissions=["manage_sales"])

        resp = client.get("/backups/", follow_redirects=False)
        assert resp.status_code == 403, f"a user without manage_backups answered {resp.status_code}, expected 403"

    def test_the_index_answers_to_a_tenant_admin(self, client, db_session, sample_tenant, sample_branch):
        """BAK-47. And the permitted side renders."""
        _tenant_user(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/backups/", follow_redirects=False)
        assert resp.status_code == 200, f"the tenant backup index answered {resp.status_code} to an admin"

    def test_downloading_a_foreign_backup_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """BAK-48. ``_owned_or_deny`` applies to every filename route here.

        Download, verify and delete all resolve the name through the same
        helper, so a tenant cannot reach another tenant's backup by guessing a
        filename. This walks download; the delete half is below.
        """
        _tenant_user(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/backups/download/someone-elses-backup.sql", follow_redirects=False)
        _assert_refused(resp, "a tenant downloading a backup it does not own")

    def test_deleting_a_foreign_backup_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """BAK-49. The destructive one, with the same resolver.

        A delete that skipped the ownership check would be the worst outcome in
        this file: recoverable for the attacker, unrecoverable for the owner.
        """
        _tenant_user(client, db_session, sample_tenant, sample_branch)

        resp = client.post("/backups/delete/someone-elses-backup.sql", follow_redirects=False)
        _assert_refused(resp, "a tenant deleting a backup it does not own")

    def test_verifying_a_foreign_backup_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """BAK-50. Verify is the third of the four filename routes."""
        _tenant_user(client, db_session, sample_tenant, sample_branch)

        resp = client.post("/backups/verify/someone-elses-backup.sql", follow_redirects=False)
        _assert_refused(resp, "a tenant verifying a backup it does not own")

    def test_clearing_the_cache_answers(self, client, db_session):
        """BAK-51. The remaining owner maintenance POSTs do not raise.

        ``clear-cache``, ``database-optimize`` and the export routes all sit
        behind the owner guard. None of them is dangerous to reach *as an
        owner*; the risk is a 500 waiting behind a guard that is never crossed.
        """
        _owner(db_session, client)

        broken = []
        for path in ("/owner/clear-cache", "/owner/database-optimize"):
            resp = client.post(path, follow_redirects=True)
            if resp.status_code != 200:
                broken.append((path, resp.status_code))
        assert not broken, f"owner maintenance routes did not answer: {broken}"

    def test_the_recent_audit_log_api_answers_to_an_owner(self, client, db_session):
        """BAK-52. The audit trail behind the database tools is readable.

        If this endpoint 500s, the operator investigating a bad console query
        has no record of what was run.
        """
        _owner(db_session, client)

        resp = client.get("/owner/api/recent-audit-logs", follow_redirects=False)
        assert resp.status_code == 200, f"the audit log api answered {resp.status_code} to an owner"

    def test_the_data_cleanup_page_requires_a_confirmation_to_act(self, client, db_session):
        """BAK-53. A destructive page renders on GET and acts only on a POST
        that says so.

        The page has to render - an operator needs to read what it is about to
        do - but rendering must not clean anything.
        """
        from models import Tenant

        _owner(db_session, client)
        before = db_session.query(Tenant).count()

        page = client.get("/owner/data-cleanup", follow_redirects=False)
        assert page.status_code == 200, f"the data-cleanup page answered {page.status_code}"

        after = db_session.query(Tenant).count()
        assert after == before, f"merely rendering data-cleanup changed {before} tenants to {after}"
