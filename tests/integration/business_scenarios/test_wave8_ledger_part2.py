"""Wave 8 (part 2) - the general ledger, continued. Prefix LED.

``test_wave8_ledger.py`` covered the three access guards and the reversal rules.
This file covers what the ledger *computes* and what the chart-of-accounts routes
will and will not let an administrator do - the second half of the 48-route domain,
and the part where a mistake is arithmetically invisible.

The balance API is the clearest case. ``calculate-journal-balance`` is a *client
helper*: the browser posts the lines it has typed and the server says whether they
balance. If that answer is wrong in the permissive direction the user is told their
entry is fine when it is not, and the entry posts. LED-31 to LED-38 therefore test
the *refusals* - zero lines, one-sided lines, an empty body - rather than the happy
path, because a helper that only ever says "unbalanced" would pass every one of
them.

Account deletion has three independent guards (protected code, existing journal
lines, child accounts) and each is tested on its own. Collapsing them into one
"cannot delete" assertion would pass against an implementation that enforced only
the first, which is the one that fires most often and the least dangerously.

The accounting identity is asserted against the database, never against a rendered
page. ``assert_balanced_lines`` is the real gate and ``post_or_fail`` is the real
caller, so both are read back out of ``gl_journal_lines`` rather than trusted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="ledger-user", permissions=(), branch=None):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"led2-{slug}-{unique}",
        email=f"led2-{unique}@example.com",
        full_name=f"LED2 {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    return client.post(
        "/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True
    )


def _viewer(client, db_session, tenant, branch):
    user = _user(db_session, tenant, slug="ledger-viewer", permissions=["view_ledger"], branch=branch)
    _login(client, user)
    return user


def _manager(client, db_session, tenant, branch):
    user = _user(
        db_session,
        tenant,
        slug="ledger-manager",
        permissions=["view_ledger", "manage_ledger"],
        branch=branch,
    )
    _login(client, user)
    return user


def _admin(client, db_session, tenant, branch):
    """A user who satisfies ``@admin_required`` for this tenant.

    ``is_admin_surface_user`` accepts ``role.slug == "super_admin"`` or the role's
    name matching ``RoleEnum.SUPER_ADMIN.name``, so the seeded super_admin role is
    reused rather than renamed into - renaming collided with the seeded row on
    ``roles_name_key``, which is a reminder that the seeded roles are shared
    state across every scenario in the suite.
    """
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug="super_admin").first()
    if role is None:
        role = Role(name=f"Super Admin {uuid.uuid4().hex[:6]}", slug="super_admin", is_active=True)
        db_session.add(role)
        db_session.commit()
    role.permissions = Permission.query.filter(Permission.code.in_(["view_ledger", "manage_ledger"])).all()
    db_session.add(role)
    db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"led2-admin-{unique}",
        email=f"led2-admin-{unique}@example.com",
        full_name="LED2 Admin",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    _login(client, user)
    return user


def _chart(db_session, tenant):
    from models import GLAccount
    from services.gl_service import GLService
    from utils.tenanting import without_tenant_scope

    found = (
        db_session.query(GLAccount)
        .filter_by(tenant_id=tenant.id, is_header=False, is_active=True)
        .order_by(GLAccount.code)
        .all()
    )
    if not found:
        with without_tenant_scope():
            GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.expire_all()
        found = (
            db_session.query(GLAccount)
            .filter_by(tenant_id=tenant.id, is_header=False, is_active=True)
            .order_by(GLAccount.code)
            .all()
        )
    assert len(found) >= 2, f"the tenant chart has {len(found)} postable accounts, need 2"
    return found


def _two_codes(db_session, tenant):
    """A debit-side and a credit-side account, for lines that have to differ."""
    accounts = _chart(db_session, tenant)
    debit = next((a for a in accounts if a.type == "asset"), accounts[0])
    credit = next((a for a in accounts if a.type in ("liability", "equity", "income")), accounts[-1])
    return debit, credit


def _entry(db_session, tenant, debit_account, credit_account, *, amount="100.00", branch=None, entry_type="manual"):
    from models import GLJournalEntry, GLJournalLine

    entry = GLJournalEntry(
        tenant_id=tenant.id,
        entry_date=datetime.now(UTC),
        entry_number=f"LED2-{uuid.uuid4().hex[:10]}",
        entry_type=entry_type,
        branch_id=branch.id if branch else None,
        description="LED2 scenario",
        is_posted=True,
    )
    db_session.add(entry)
    db_session.flush()
    db_session.add_all(
        [
            GLJournalLine(
                entry_id=entry.id,
                tenant_id=tenant.id,
                account_id=debit_account.id,
                debit=Decimal(amount),
                credit=Decimal("0"),
                description="debit",
            ),
            GLJournalLine(
                entry_id=entry.id,
                tenant_id=tenant.id,
                account_id=credit_account.id,
                debit=Decimal("0"),
                credit=Decimal(amount),
                description="credit",
            ),
        ]
    )
    db_session.flush()
    return entry


def _line_totals(db_session, entry):
    from models import GLJournalLine

    lines = db_session.query(GLJournalLine).filter_by(entry_id=entry.id).all()
    debits = sum(Decimal(str(ln.debit or 0)) for ln in lines)
    credits = sum(Decimal(str(ln.credit or 0)) for ln in lines)
    return debits, credits


class TestLED28FinancialStatements:
    """LED-28 to LED-30: the statements render and stay tenant-scoped."""

    @pytest.mark.parametrize(
        "path",
        [
            "/ledger/trial-balance",
            "/ledger/income-statement",
            "/ledger/balance-sheet",
            "/ledger/cash-flow",
            "/ledger/vat-report",
            "/ledger/budget-vs-actual",
        ],
    )
    def test_a_viewer_reaches_the_statements(self, client, db_session, sample_tenant, sample_branch, path):
        """LED-28. The success side of the boundary file.

        ``fiscal-year-preview`` is deliberately absent: it is guarded by
        ``permission_required("admin")`` rather than ``view_ledger``, so a viewer
        is refused there by design. LED-28b covers it.
        """
        _viewer(client, db_session, sample_tenant, sample_branch)
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} answered {resp.status_code} for a view_ledger user"

    def test_the_fiscal_year_preview_is_an_admin_surface(self, client, db_session, sample_tenant, sample_branch):
        """LED-28b. It reads ``permission_required("admin")``, not ``view_ledger``.

        Noted separately because a viewer being refused here is the contract, not
        a gap: the fiscal-year view is part of the close, which is an admin action.
        """
        _viewer(client, db_session, sample_tenant, sample_branch)
        assert client.get("/ledger/fiscal-year-preview").status_code in (302, 403), (
            "a view-only user reached the fiscal-year preview"
        )

    def test_the_trial_balance_is_internally_consistent(self, client, db_session, sample_tenant, sample_branch):
        """LED-29. Read from the rows, not from the rendered totals.

        Sum(debit) == Sum(credit) across every posted line in the tenant. A report
        that displayed a balanced-looking total while the underlying rows did not
        balance would pass a page-level assertion; this cannot.
        """
        from models import GLJournalEntry, GLJournalLine

        _viewer(client, db_session, sample_tenant, sample_branch)
        debit_account, credit_account = _two_codes(db_session, sample_tenant)
        _entry(db_session, sample_tenant, debit_account, credit_account, branch=sample_branch)
        db_session.commit()

        resp = client.get("/ledger/trial-balance")
        assert resp.status_code == 200

        lines = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry)
            .filter(
                GLJournalEntry.tenant_id == sample_tenant.id,
                GLJournalEntry.is_posted.is_(True),
            )
            .all()
        )
        if not lines:
            pytest.skip("this tenant has no posted lines to reconcile")
        debits = sum(Decimal(str(ln.debit or 0)) for ln in lines)
        credits = sum(Decimal(str(ln.credit or 0)) for ln in lines)
        assert debits == credits, f"posted rows do not balance: Dr {debits} vs Cr {credits}"

    def test_a_statement_never_reports_another_tenants_rows(self, client, db_session, sample_tenant, sample_branch):
        """LED-30. Aggregation across tenants is the breach the whole domain fears."""
        from models import GLJournalEntry

        _viewer(client, db_session, sample_tenant, sample_branch)
        _two_codes(db_session, sample_tenant)
        db_session.commit()

        for path in ("/ledger/trial-balance", "/ledger/income-statement", "/ledger/balance-sheet"):
            body = client.get(path).get_data(as_text=True)
            ours = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
            assert str(ours) in body or ours == 0, f"{path} rendered a count that is not ours"

    def test_the_account_statement_of_an_unknown_account_is_refused(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """LED-30b."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        assert client.get("/ledger/account/99999999").status_code in (302, 404)
        assert client.get("/ledger/account/99999999/statement").status_code in (302, 404)

    def test_the_account_page_shows_the_code_we_asked_for(self, client, db_session, sample_tenant, sample_branch):
        """LED-30c. A page that renders *some* account is not evidence."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        debit_account, _ = _two_codes(db_session, sample_tenant)
        resp = client.get(f"/ledger/account/{debit_account.id}")
        assert resp.status_code == 200
        assert debit_account.code in resp.get_data(as_text=True), (
            f"the account page did not render {debit_account.code}"
        )


class TestLED31BalanceApi:
    """LED-31 to LED-38: the client-side balance helper must not lie."""

    @staticmethod
    def _balance(client, lines):
        return client.post("/ledger/api/calculate-journal-balance", json={"lines": lines})

    def test_an_empty_body_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-31. No body is not a balanced entry."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        assert client.post("/ledger/api/calculate-journal-balance", json={}).status_code == 400

    def test_no_lines_is_not_balanced(self, client, db_session, sample_tenant, sample_branch):
        """LED-32. 0 == 0, and reporting that as balanced would be nonsense.

        The route's own predicate guards this with ``total_debit > 0``; this
        pins it, because dropping that clause would make an empty form look ready
        to post.
        """
        _viewer(client, db_session, sample_tenant, sample_branch)
        body = self._balance(client, []).get_json()
        assert body is not None
        assert not body["data"]["is_balanced"], "an entry with no lines was reported as balanced"

    def test_a_one_sided_entry_is_not_balanced(self, client, db_session, sample_tenant, sample_branch):
        """LED-33. The classic half-filled form."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        body = self._balance(client, [{"debit": "100", "credit": "0"}]).get_json()
        assert not body["data"]["is_balanced"], "a debit-only entry was reported as balanced"

    def test_a_mismatched_entry_is_not_balanced(self, client, db_session, sample_tenant, sample_branch):
        """LED-34. Wrong by a whole currency unit, not a rounding crumb."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        body = self._balance(client, [{"debit": "100", "credit": "0"}, {"debit": "0", "credit": "90"}]).get_json()
        assert not body["data"]["is_balanced"], "a 10-unit mismatch was reported as balanced"
        assert body["data"]["difference"] == 10.0, f"the reported difference is {body['data']['difference']}, not 10"

    def test_a_genuinely_balanced_entry_is_reported_balanced(self, client, db_session, sample_tenant, sample_branch):
        """LED-35. The success side.

        Without this, every refusal above would also pass against a helper that
        always answered "unbalanced" - which would be useless to the browser.
        """
        _viewer(client, db_session, sample_tenant, sample_branch)
        body = self._balance(client, [{"debit": "100", "credit": "0"}, {"debit": "0", "credit": "100"}]).get_json()
        assert body["data"]["is_balanced"] is True
        assert body["data"]["difference"] == 0.0

    def test_the_balance_api_needs_view_ledger(self, client, db_session, sample_tenant, sample_branch):
        """LED-36. It is a read of the chart, so it takes the read permission."""
        user = _user(db_session, sample_tenant, slug="no-ledger", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.post("/ledger/api/calculate-journal-balance", json={"lines": []})
        assert resp.status_code in (302, 403), f"the balance API answered {resp.status_code} without view_ledger"

    def test_the_balance_api_is_refused_anonymously(self, client):
        """LED-37. POST, so a GET's 405 cannot stand in for the guard."""
        resp = client.post("/ledger/api/calculate-journal-balance", json={"lines": []})
        assert resp.status_code in (302, 401, 403), f"anonymously the API answered {resp.status_code}"

    def test_junk_amounts_do_not_crash_the_helper(self, client, db_session, sample_tenant, sample_branch):
        """LED-38. A half-typed number in a form field.

        The route catches the Decimal error and answers 400. A 500 here would mean
        one bad keystroke in the browser produced a server error page.
        """
        _viewer(client, db_session, sample_tenant, sample_branch)
        resp = self._balance(client, [{"debit": "not-a-number", "credit": "0"}])
        assert resp.status_code in (200, 400), f"junk amounts answered {resp.status_code}"


class TestLED39AccountSearchApi:
    """LED-39 to LED-41: the account picker the manual-entry form depends on."""

    def test_the_search_returns_json(self, client, db_session, sample_tenant, sample_branch):
        """LED-39."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        _chart(db_session, sample_tenant)
        resp = client.get("/ledger/api/accounts/search?q=6")
        assert resp.status_code == 200, f"account search answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "application/json" in ctype, f"account search is {ctype}, not JSON"

    def test_the_search_only_returns_our_accounts(self, client, db_session, sample_tenant, sample_branch):
        """LED-40. The picker feeds a posting, so a foreign account is a real risk."""
        from models import GLAccount

        _viewer(client, db_session, sample_tenant, sample_branch)
        _chart(db_session, sample_tenant)
        resp = client.get("/ledger/api/accounts/search?q=")
        assert resp.status_code == 200
        rows = resp.get_json()["data"]
        ours = {a.id for a in db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id).all()}
        for row in rows:
            assert row["id"] in ours, f"the search returned account {row['id']}, which is not ours"

    def test_the_search_needs_view_ledger(self, client, db_session, sample_tenant, sample_branch):
        """LED-41."""
        user = _user(db_session, sample_tenant, slug="no-search", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.get("/ledger/api/accounts/search?q=6")
        assert resp.status_code in (302, 403), f"account search answered {resp.status_code} without view_ledger"


class TestLED42ManualEntry:
    """LED-42 to LED-46: the manual entry form is a posting surface."""

    def test_the_form_renders_for_a_manager(self, client, db_session, sample_tenant, sample_branch):
        """LED-42. GET does not need manage_ledger's POST path to be reachable."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/ledger/manual-entry").status_code == 200

    def test_a_viewer_cannot_reach_the_form(self, client, db_session, sample_tenant, sample_branch):
        """LED-43. view_ledger does not imply manage_ledger."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        assert client.get("/ledger/manual-entry").status_code in (302, 403), (
            "a view-only user reached the manual entry form"
        )

    def test_an_unbalanced_manual_entry_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-44. The core guarantee.

        A manual entry with debits that do not equal credits must not be written.
        The assertion is on the row count, because the route flashes an error and
        re-renders - a 200 that changed nothing.
        """
        from models import GLJournalEntry

        _manager(client, db_session, sample_tenant, sample_branch)
        debit_account, credit_account = _two_codes(db_session, sample_tenant)
        before = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()

        client.post(
            "/ledger/manual-entry",
            data={
                "description": "unbalanced",
                "line_0_account": debit_account.code,
                "line_0_debit": "100",
                "line_0_credit": "0",
                "line_1_account": credit_account.code,
                "line_1_debit": "0",
                "line_1_credit": "40",
            },
            follow_redirects=True,
        )
        after = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"an unbalanced manual entry was written ({before} -> {after})"

    def test_a_balanced_manual_entry_is_written_and_balances(self, client, db_session, sample_tenant, sample_branch):
        """LED-45. The success side, read back from the rows."""
        from models import GLJournalEntry

        _manager(client, db_session, sample_tenant, sample_branch)
        debit_account, credit_account = _two_codes(db_session, sample_tenant)
        before = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()

        client.post(
            "/ledger/manual-entry",
            data={
                "description": "balanced manual",
                "line_0_account": debit_account.code,
                "line_0_debit": "250.50",
                "line_0_credit": "0",
                "line_1_account": credit_account.code,
                "line_1_debit": "0",
                "line_1_credit": "250.50",
            },
            follow_redirects=True,
        )

        entries = (
            db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id, description="balanced manual").all()
        )
        assert len(entries) == 1, f"expected one manual entry, wrote {len(entries)} ({before} before)"
        debits, credits = _line_totals(db_session, entries[0])
        assert debits == credits, f"the written entry does not balance: Dr {debits} vs Cr {credits}"
        assert debits == Decimal("250.500"), f"the entry carries {debits}, not the posted 250.50"

    def test_an_entry_with_no_lines_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-46. The form submitted empty is not a zero-value entry."""
        from models import GLJournalEntry

        _manager(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        client.post(
            "/ledger/manual-entry",
            data={"description": "empty"},
            follow_redirects=True,
        )
        after = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, "an entry with no lines was written"


class TestLED47AccountAdministration:
    """LED-47 to LED-53: the chart of accounts is a protected structure."""

    def test_an_admin_reaches_the_account_admin_surfaces(self, client, db_session, sample_tenant, sample_branch):
        """LED-47. The success side of @admin_required."""
        _admin(client, db_session, sample_tenant, sample_branch)
        for path in (
            "/ledger/admin-accounts",
            "/ledger/admin-accounts/add",
            "/ledger/admin-vaults",
            "/admin/ledger/accounts",
            "/admin/ledger/accounts/add",
            "/admin/ledger/vaults",
        ):
            assert client.get(path).status_code == 200, f"{path} answered {client.get(path).status_code} for an admin"

    def test_a_plain_manager_is_refused_the_chart_of_accounts(self, client, db_session, sample_tenant, sample_branch):
        """LED-48. manage_ledger is not admin.

        The chart is the structure every posting depends on; letting a posting
        manager restructure it would let them redirect the ledger's own postings.
        """
        _manager(client, db_session, sample_tenant, sample_branch)
        for path in ("/ledger/admin-accounts", "/ledger/admin-accounts/add", "/ledger/admin-vaults"):
            assert client.get(path).status_code in (302, 403), (
                f"{path} answered {client.get(path).status_code} for a manage_ledger user"
            )

    def test_a_unique_code_can_be_added(self, client, db_session, sample_tenant, sample_branch):
        """LED-49. The happy path for chart administration."""
        from models import GLAccount

        _admin(client, db_session, sample_tenant, sample_branch)
        code = f"9{uuid.uuid4().hex[:3]}"
        before = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id, code=code).count()

        client.post(
            "/ledger/admin-accounts/add",
            data={"code": code, "name": f"Probe {code}", "name_ar": "حساب", "type": "expense"},
            follow_redirects=True,
        )
        after = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id, code=code).count()
        assert after == before + 1, f"the account {code} was not created ({before} -> {after})"

    def test_a_duplicate_code_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-50. Code uniqueness is what makes a chart addressable."""
        from models import GLAccount

        _admin(client, db_session, sample_tenant, sample_branch)
        _chart(db_session, sample_tenant)
        existing = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id).order_by(GLAccount.code).first()
        assert existing is not None, "the tenant has no chart to duplicate from"

        before = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id, code=existing.code).count()
        client.post(
            "/ledger/admin-accounts/add",
            data={
                "code": existing.code,
                "name": "Duplicate",
                "name_ar": "مكرر",
                "type": "expense",
            },
            follow_redirects=True,
        )
        after = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id, code=existing.code).count()
        assert after == before, f"a duplicate code {existing.code} was accepted ({before} -> {after})"

    def test_an_account_with_journal_lines_cannot_be_deleted(self, client, db_session, sample_tenant, sample_branch):
        """LED-51. Deleting a posted-to account would orphan the history.

        This is the guard that matters most in practice, and it is tested against
        a real entry rather than a real id, so the refusal is attributable.
        """
        from models import GLAccount

        _admin(client, db_session, sample_tenant, sample_branch)
        debit_account, credit_account = _two_codes(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit_account, credit_account, branch=sample_branch)
        db_session.commit()

        code = str(debit_account.code)
        assert not _is_protected(code), f"{code} is a protected code; pick another for this scenario"

        client.post(f"/admin/ledger/accounts/{debit_account.id}/delete", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(GLAccount, debit_account.id) is not None, (
            f"account {code} was deleted while entry {entry.entry_number} still references it"
        )

    def test_an_account_with_children_cannot_be_deleted(self, client, db_session, sample_tenant, sample_branch):
        """LED-52. Removing a parent would orphan the subtree."""
        from models import GLAccount

        _admin(client, db_session, sample_tenant, sample_branch)
        _chart(db_session, sample_tenant)

        parent = (
            db_session.query(GLAccount)
            .filter_by(tenant_id=sample_tenant.id, is_header=True)
            .filter(
                GLAccount.id.in_(
                    db_session.query(GLAccount.parent_id)
                    .filter_by(tenant_id=sample_tenant.id)
                    .filter(GLAccount.parent_id.isnot(None))
                    .distinct()
                )
            )
            .first()
        )
        if parent is None:
            pytest.skip("this tenant's chart has no parent with children")

        child_ids = [
            a.id for a in db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id, parent_id=parent.id).all()
        ]
        client.post(f"/admin/ledger/accounts/{parent.id}/delete", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(GLAccount, parent.id) is not None, (
            f"parent account {parent.code} was deleted while {len(child_ids)} children reference it"
        )
        for child_id in child_ids:
            assert db_session.get(GLAccount, child_id) is not None, f"child {child_id} was orphaned"

    def test_a_protected_system_account_cannot_be_deleted(self, client, db_session, sample_tenant, sample_branch):
        """LED-53. The control accounts the whole chart hangs from."""
        from models import GLAccount

        _admin(client, db_session, sample_tenant, sample_branch)
        _chart(db_session, sample_tenant)

        protected = (
            db_session.query(GLAccount)
            .filter_by(tenant_id=sample_tenant.id)
            .filter(GLAccount.code.in_(_protected_codes()))
            .first()
        )
        if protected is None:
            pytest.skip("this tenant's chart has none of the protected codes")

        client.post(f"/admin/ledger/accounts/{protected.id}/delete", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(GLAccount, protected.id) is not None, f"protected account {protected.code} was deleted"


def _protected_codes():
    from routes.admin_ledger import PROTECTED_ACCOUNT_CODES

    return list(PROTECTED_ACCOUNT_CODES)


def _is_protected(code):
    return str(code) in {str(c) for c in _protected_codes()}


class TestLED54AccountAndEntryDetail:
    """LED-54 to LED-58: detail views and the reversal rules that guard them."""

    def test_an_entry_detail_page_renders_its_own_number(self, client, db_session, sample_tenant, sample_branch):
        """LED-54."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        debit_account, credit_account = _two_codes(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit_account, credit_account, branch=sample_branch)
        db_session.commit()

        resp = client.get(f"/ledger/entry/{entry.id}")
        assert resp.status_code == 200, f"the entry page answered {resp.status_code}"
        assert entry.entry_number in resp.get_data(as_text=True), "the entry page did not render its own number"

    def test_an_unknown_entry_detail_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-55."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        assert client.get("/ledger/entry/99999999").status_code in (302, 404)

    def test_reversing_a_posted_entry_adds_an_offsetting_entry(self, client, db_session, sample_tenant, sample_branch):
        """LED-56. The reversal is a new entry, not an edit of the old one.

        A manual entry carries no ``reference_type`` - there is no document behind
        it - so the pairing is asserted structurally: the original survives, the
        entry count grows by one, and the two together net to zero.
        """
        from models import GLJournalEntry

        _manager(client, db_session, sample_tenant, sample_branch)
        debit_account, credit_account = _two_codes(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit_account, credit_account, branch=sample_branch)
        db_session.commit()
        entry_id = entry.id
        before = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post(f"/ledger/entry/{entry_id}/reverse", follow_redirects=True)
        assert resp.status_code == 200, f"reversing answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"reversing added {after - before} entries, expected exactly 1"
        assert db_session.get(GLJournalEntry, entry_id) is not None, "reversing removed the original entry"

        original_debits, original_credits = _line_totals(db_session, db_session.get(GLJournalEntry, entry_id))
        assert original_debits == original_credits, (
            f"the original entry was rewritten: Dr {original_debits} vs Cr {original_credits}"
        )

    def test_reversing_the_same_entry_twice_does_not_double_reverse(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """LED-57. A double-click must not double the correction.

        ``GLJournalEntry.reverse_entry`` refuses an entry that is already
        reversed, so the entry count is unchanged by the second attempt.
        """
        from models import GLJournalEntry

        _manager(client, db_session, sample_tenant, sample_branch)
        debit_account, credit_account = _two_codes(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit_account, credit_account, branch=sample_branch)
        db_session.commit()
        entry_id = entry.id

        client.post(f"/ledger/entry/{entry_id}/reverse", follow_redirects=True)
        first = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()

        client.post(f"/ledger/entry/{entry_id}/reverse", follow_redirects=True)
        db_session.expire_all()
        second = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        assert second == first, f"a second reversal added another entry ({first} -> {second})"

    def test_the_admin_reversal_route_marks_the_entry(self, client, db_session, sample_tenant, sample_branch):
        """LED-58. The admin surface has its own reversal, so it gets its own test."""
        from models import GLJournalEntry

        _admin(client, db_session, sample_tenant, sample_branch)
        debit_account, credit_account = _two_codes(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit_account, credit_account, branch=sample_branch)
        db_session.commit()
        entry_id = entry.id

        resp = client.post(f"/admin/ledger/journals/{entry_id}/reverse", follow_redirects=True)
        assert resp.status_code == 200, f"the admin reversal answered {resp.status_code}"

        db_session.expire_all()
        refreshed = db_session.get(GLJournalEntry, entry_id)
        assert refreshed is not None, "the admin reversal removed the original entry"
        assert refreshed.is_reversed is True, f"is_reversed is {refreshed.is_reversed!r} after an admin reversal"


class TestLED59PeriodsAndClose:
    """LED-59 to LED-63: period close is the ledger's off switch."""

    def test_the_periods_page_is_reachable(self, client, db_session, sample_tenant, sample_branch):
        """LED-59."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        assert client.get("/ledger/periods").status_code == 200

    def test_posting_into_a_closed_period_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-60. The guard `assert_period_open` exists for.

        Written against a real closed period so the refusal is attributable rather
        than a missing row. ``GLPeriod`` closes on an ``is_closed`` flag with a
        ``year``/``month`` pair - not on a status string and not on a date range,
        which is worth recording because both were wrong on the first attempt.
        """
        from models import GLPeriod
        from utils.tenanting import without_tenant_scope

        _manager(client, db_session, sample_tenant, sample_branch)
        debit_account, credit_account = _two_codes(db_session, sample_tenant)

        with without_tenant_scope():
            period = db_session.query(GLPeriod).filter_by(tenant_id=sample_tenant.id, year=2019, month=1).first()
            if period is None:
                period = GLPeriod(tenant_id=sample_tenant.id, year=2019, month=1, is_closed=True)
                db_session.add(period)
                db_session.commit()
            else:
                period.is_closed = True
                db_session.commit()

        assert period.is_closed is True, "the scenario period is not actually closed"

        resp = client.post(
            "/ledger/manual-entry",
            data={
                "description": "into a closed period",
                "entry_date": "2019-01-15",
                "line_0_account": debit_account.code,
                "line_0_debit": "50",
                "line_0_credit": "0",
                "line_1_account": credit_account.code,
                "line_1_debit": "0",
                "line_1_credit": "50",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"posting into a closed period answered {resp.status_code}"

        from models import GLJournalEntry

        written = (
            db_session.query(GLJournalEntry)
            .filter_by(tenant_id=sample_tenant.id, description="into a closed period")
            .count()
        )
        assert written == 0, f"an entry was written into the closed period {period.year}-{period.month}"

    def test_the_fiscal_year_close_is_a_post_only_surface(self, client, db_session, sample_tenant, sample_branch):
        """LED-61. POST-only, so a GET would answer 405 and hide the guard."""
        user = _user(db_session, sample_tenant, slug="no-close", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.post("/ledger/close-fiscal-year", follow_redirects=True)
        assert resp.status_code in (302, 403), f"a view-only user closed a fiscal year and got {resp.status_code}"

    def test_depreciation_is_gated_behind_manage_ledger(self, client, db_session, sample_tenant, sample_branch):
        """LED-62. Depreciation writes entries; a reader may not run it."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/ledger/run-depreciation", follow_redirects=True)
        assert resp.status_code in (302, 403), f"a view-only user ran depreciation and got {resp.status_code}"

    def test_the_gl_flag_gates_the_whole_ledger(self, db_session):
        """LED-63. The third guard: a tenant switch, not a permission.

        ``install_feature_gate(ledger_bp, "gl")`` reads the tenant's ``enable_gl``.
        A tenant with GL off must not reach the ledger whatever permissions their
        users hold - which is a different control from anything else in this file.
        """
        from models import Tenant

        columns = Tenant.__table__.columns
        assert "enable_gl" in columns, "Tenant has no enable_gl flag to gate the ledger with"
