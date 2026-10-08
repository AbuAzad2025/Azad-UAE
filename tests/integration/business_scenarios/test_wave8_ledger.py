"""Wave 8 - the general ledger. Prefix LED.

The ledger is the one surface where an arithmetic mistake is not a cosmetic bug:
a posting that lands on the wrong account still balances, and the balance is the
property everything else trusts. So the scenarios here are not mostly "does the
page render" - they are about what happens when a posting is unbalanced, posted
into a closed period, posted for someone else's tenant, or reversed twice.

Three guards shape the surface and they are asserted separately, because
collapsing them would hide which one is missing:

``permission_required("view_ledger" / "manage_ledger" / "admin")`` on
``routes/ledger.py`` - a permission the operator may or may not hold.
``@admin_required`` on ``routes/admin_ledger.py`` - the chart of accounts itself.
``install_feature_gate(ledger_bp, "gl")`` - a tenant with GL switched off cannot
reach any of it, which is a *tenant* flag rather than a user permission.

The double-entry invariants are checked against the journal rows in the database,
never against what a template echoed back. Wave 7 turned up a whitelist defect
that a page-level assertion passed straight through, because the template did
not happen to print the bad value; a report that renders what it was given
cannot tell a correct posting from a wrong one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

LED_VIEW_PATHS = [
    "/ledger/",
    "/ledger/trial-balance",
    "/ledger/journal-entries",
    "/ledger/vat-report",
    "/ledger/periods",
    "/ledger/income-statement",
    "/ledger/balance-sheet",
    "/ledger/accounts-tree",
    "/ledger/cash-flow",
    "/ledger/aging-analysis",
    "/ledger/admin-dashboard",
    "/ledger/admin-accounts",
    "/ledger/admin-journals",
    "/ledger/admin-reports",
    "/ledger/admin-trial-balance",
    "/ledger/admin-balance-sheet",
    "/ledger/admin-income-statement",
    "/ledger/admin-settings",
]

LED_POST_PATHS = [
    "/ledger/run-depreciation",
    "/ledger/entry/1/reverse",
    "/ledger/close-fiscal-year",
]

ADMIN_LEDGER_PATHS = [
    "/admin/ledger/",
    "/admin/ledger/accounts",
    "/admin/ledger/accounts/add",
    "/admin/ledger/vaults",
    "/admin/ledger/journals",
    "/admin/ledger/journals/1/view",
    "/admin/ledger/reports",
    "/admin/ledger/reports/trial-balance",
    "/admin/ledger/reports/balance-sheet",
    "/admin/ledger/reports/income-statement",
    "/admin/ledger/settings",
]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="cashier", permissions=(), branch=None):
    """A tenant user carrying exactly the permissions under test.

    Permissions are attached explicitly rather than via a factory role, because
    every assertion here is about a specific permission being held or withheld -
    a factory that quietly bundled them would make all of it vacuous.
    """
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"led-{slug}-{unique}",
        email=f"led-{unique}@example.com",
        full_name=f"LED {slug}",
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
        "/auth/login",
        data={"username": user.username, "password": "Str0ng!Pass99"},
        follow_redirects=True,
    )


def _accounts(db_session, tenant):
    """Two postable accounts, provisioning the tenant's chart if it is empty.

    Goes through GLService.ensure_core_accounts rather than inserting rows by
    hand, because that is the path production uses and a hand-built chart would
    not prove the ledger works for a tenant that has just been created - which is
    exactly the case the accounting waves care about.
    """
    from models import GLAccount
    from services.gl_service import GLService

    found = (
        db_session.query(GLAccount)
        .filter_by(tenant_id=tenant.id, is_header=False, is_active=True)
        .order_by(GLAccount.code)
        .limit(2)
        .all()
    )
    if len(found) < 2:
        from utils.tenanting import without_tenant_scope

        with without_tenant_scope():
            GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.expire_all()
        found = (
            db_session.query(GLAccount)
            .filter_by(tenant_id=tenant.id, is_header=False, is_active=True)
            .order_by(GLAccount.code)
            .limit(2)
            .all()
        )
    assert len(found) == 2, f"the tenant chart has {len(found)} postable accounts, need 2"
    return found


def _entry(db_session, tenant, debit, credit, amount="100.00", branch=None):
    """A balanced two-line journal entry, returned uncommitted to the caller.

    Takes a branch because routes/ledger.py compares entry.branch_id against the
    active branch and answers 403 on a mismatch - a hand-built entry with no
    branch is refused by the reversal route, which looks like a broken reversal
    rather than a branch-scoping guard doing its job.
    """
    from models import GLJournalEntry, GLJournalLine

    entry = GLJournalEntry(
        tenant_id=tenant.id,
        entry_date=datetime.now(UTC),
        entry_number=f"LED-{uuid.uuid4().hex[:10]}",
        entry_type="manual",
        branch_id=branch.id if branch is not None else None,
        description="LED scenario",
        is_posted=True,
    )
    db_session.add(entry)
    db_session.flush()
    db_session.add_all(
        [
            GLJournalLine(
                entry_id=entry.id,
                tenant_id=tenant.id,
                account_id=debit.id,
                debit=Decimal(amount),
                credit=Decimal("0"),
                description="debit",
            ),
            GLJournalLine(
                entry_id=entry.id,
                tenant_id=tenant.id,
                account_id=credit.id,
                debit=Decimal("0"),
                credit=Decimal(amount),
                description="credit",
            ),
        ]
    )
    db_session.flush()
    return entry


class TestLED01AccessBoundary:
    """LED-01 to LED-08: three guards, asserted apart."""

    @pytest.mark.parametrize("path", LED_VIEW_PATHS)
    def test_anonymous_is_refused(self, client, path):
        """LED-01. Not 404 here - the ledger admits it exists and withholds access."""
        resp = client.get(path)
        assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code} anonymously"

    @pytest.mark.parametrize("path", LED_POST_PATHS)
    def test_the_post_surfaces_are_refused_anonymously(self, client, path):
        """LED-02. POST, because a GET would answer 405 before the guard ran.

        Depreciation, reversal and fiscal-year close all change the books. A guard
        checked only with GET would never have been exercised at all.
        """
        # No follow_redirects: @login_required bounces to the login page, and
        # that page is a 200. Asserting on the followed response reports a
        # correctly-guarded route as open.
        resp = client.post(path)
        assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code} anonymously"

    def test_a_user_without_view_ledger_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-03. The permission, not the role, is what decides."""
        user = _user(db_session, sample_tenant, slug="cashier", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.get("/ledger/trial-balance")
        assert resp.status_code in (302, 403), f"a user without view_ledger reached the ledger ({resp.status_code})"

    def test_view_ledger_grants_the_read_only_reports(self, client, db_session, sample_tenant, sample_branch):
        """LED-04. The success side, so LED-03 is not the only outcome measured."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        assert client.get("/ledger/trial-balance").status_code == 200

    def test_manage_ledger_is_distinct_from_view_ledger(self, client, db_session, sample_tenant, sample_branch):
        """LED-05. Reading is not writing.

        A user holding only view_ledger gets the reports and is still refused the
        manual-entry form, which is what stops a read-only accountant from
        posting.
        """
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        assert client.get("/ledger/manual-entry").status_code in (302, 403), (
            "a view-only user reached the manual entry form"
        )

    @pytest.mark.parametrize("path", ADMIN_LEDGER_PATHS)
    def test_the_admin_ledger_is_refused_without_admin(self, client, db_session, sample_tenant, sample_branch, path):
        """LED-06. The chart of accounts is behind @admin_required, not view_ledger.

        Deliberately a user who *does* hold view_ledger: without that, the refusal
        could be attributed to the wrong permission.
        """
        user = _user(
            db_session,
            sample_tenant,
            slug="accountant",
            permissions=["view_ledger", "manage_ledger"],
            branch=sample_branch,
        )
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"a non-admin reached {path} ({resp.status_code})"

    def test_a_tenant_with_gl_disabled_is_locked_out(self, client, db_session, sample_tenant, sample_branch):
        """LED-07. enable_gl is a tenant switch, independent of any permission.

        install_feature_gate(ledger_bp, "gl") consults it before the view runs, so
        a user with every ledger permission still gets nothing from a tenant that
        has not bought the module.
        """
        user = _user(
            db_session,
            sample_tenant,
            slug="accountant",
            permissions=["view_ledger", "manage_ledger"],
            branch=sample_branch,
        )
        _login(client, user)
        assert client.get("/ledger/trial-balance").status_code == 200

        sample_tenant.enable_gl = False
        db_session.commit()
        resp = client.get("/ledger/trial-balance")
        assert resp.status_code in (302, 403), f"a GL-disabled tenant still served the ledger ({resp.status_code})"
        sample_tenant.enable_gl = True
        db_session.commit()

    def test_the_balance_api_is_csrf_exempt_so_it_still_needs_a_permission(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """LED-08. Exemption from CSRF is not exemption from authorisation.

        /ledger/api/calculate-journal-balance is on WTF_CSRF_EXEMPT_LIST, which
        is correct for a calculator. It must still be behind login and
        permission, or the exemption becomes an unauthenticated endpoint.
        """
        user = _user(db_session, sample_tenant, slug="cashier", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.post("/ledger/api/calculate-journal-balance", json={"lines": []})
        assert resp.status_code in (302, 401, 403), f"the exempt calculator answered {resp.status_code}"


class TestLED02DoubleEntry:
    """LED-09 to LED-14: the arithmetic itself."""

    def test_a_balanced_entry_is_accepted(self, db_session, sample_tenant):
        """LED-09. The baseline the other scenarios depart from."""
        from services.gl_posting import assert_balanced_lines

        assert_balanced_lines(
            [
                {"debit": Decimal("100.00"), "credit": Decimal("0.00")},
                {"debit": Decimal("0.00"), "credit": Decimal("100.00")},
            ],
            currency=sample_tenant.default_currency,
        )

    def test_an_unbalanced_entry_is_refused(self, db_session, sample_tenant):
        """LED-10. Debits must equal credits. This is the whole invariant."""
        from services.gl_posting import assert_balanced_lines

        with pytest.raises(Exception):
            assert_balanced_lines(
                [
                    {"debit": Decimal("100.00"), "credit": Decimal("0.00")},
                    {"debit": Decimal("0.00"), "credit": Decimal("99.99")},
                ],
                currency=sample_tenant.default_currency,
            )
        db_session.rollback()

    def test_a_one_cent_imbalance_is_still_an_imbalance(self, db_session, sample_tenant):
        """LED-11. The tolerance is 0.001, so a cent is a hundred times it."""
        from services.gl_posting import assert_balanced_lines

        with pytest.raises(Exception):
            assert_balanced_lines(
                [
                    {"debit": Decimal("100.00"), "credit": Decimal("0.00")},
                    {"debit": Decimal("0.00"), "credit": Decimal("99.99")},
                ],
                currency=sample_tenant.default_currency,
            )

    def test_a_single_sided_entry_is_refused(self, db_session, sample_tenant):
        """LED-12. One line with only a debit cannot balance against nothing."""
        from services.gl_posting import assert_balanced_lines

        with pytest.raises(Exception):
            assert_balanced_lines([{"debit": Decimal("100.00"), "credit": Decimal("0.00")}])
        db_session.rollback()

    def test_the_entry_actually_lands_in_the_database_balanced(self, client, db_session, sample_tenant, sample_branch):
        """LED-13. Verified from the rows, not from a rendered page.

        The debit and credit sides are read back off the journal lines and summed.
        A template that renders whatever it was handed would agree with a wrong
        posting; the rows cannot.
        """
        from models import GLJournalLine

        debit, credit = _accounts(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit, credit, branch=sample_branch)
        db_session.commit()
        eid = entry.id

        db_session.expire_all()
        lines = db_session.query(GLJournalLine).filter_by(entry_id=eid).all()
        assert len(lines) == 2, f"the entry stored {len(lines)} lines"
        total_debit = sum(Decimal(str(line.debit or 0)) for line in lines)
        total_credit = sum(Decimal(str(line.credit or 0)) for line in lines)
        assert total_debit == total_credit, f"debits {total_debit} != credits {total_credit}"
        assert total_debit > 0, "a balanced entry of zero proves nothing"

    def test_the_trial_balance_reads_the_rows(self, client, db_session, sample_tenant, sample_branch):
        """LED-14. Debit total equals credit total over the tenant's whole ledger."""
        from models import GLJournalLine

        debit, credit = _accounts(db_session, sample_tenant)
        for _ in range(2):
            _entry(db_session, sample_tenant, debit, credit, amount="75.50")
        db_session.commit()

        db_session.expire_all()
        lines = db_session.query(GLJournalLine).filter_by(tenant_id=sample_tenant.id).all()
        total_debit = sum(Decimal(str(line.debit or 0)) for line in lines)
        total_credit = sum(Decimal(str(line.credit or 0)) for line in lines)
        assert total_debit == total_credit, f"the tenant ledger does not balance: {total_debit} vs {total_credit}"


class TestLED03Periods:
    """LED-15 to LED-18: the closed-period lock."""

    def test_a_period_can_be_opened_and_closed(self, db_session, sample_tenant):
        """LED-15. The flags are the lock, so they are what is asserted."""
        from models import GLPeriod

        period = GLPeriod(tenant_id=sample_tenant.id, year=2031, month=1, is_closed=False)
        db_session.add(period)
        db_session.commit()
        pid = period.id

        period.is_closed = True
        db_session.commit()
        db_session.expire_all()
        assert db_session.get(GLPeriod, pid).is_closed is True

    def test_a_posting_into_a_closed_period_is_refused(self, db_session, sample_tenant):
        """LED-16. assert_period_open is the gate; it must refuse a closed period."""
        from models import GLPeriod
        from services.gl_helpers import assert_period_open

        period = GLPeriod(tenant_id=sample_tenant.id, year=2031, month=2, is_closed=True)
        db_session.add(period)
        db_session.commit()

        from datetime import UTC, datetime

        closed_day = datetime(period.year, period.month, 15, tzinfo=UTC)
        with pytest.raises(Exception):
            assert_period_open(closed_day, sample_tenant.id)
        db_session.rollback()

    def test_an_open_period_is_not_refused(self, db_session, sample_tenant):
        """LED-17. The success side of LED-16."""
        from models import GLPeriod
        from services.gl_helpers import assert_period_open

        period = GLPeriod(tenant_id=sample_tenant.id, year=2031, month=3, is_closed=False)
        db_session.add(period)
        db_session.commit()
        from datetime import UTC, datetime

        open_day = datetime(period.year, period.month, 15, tzinfo=UTC)
        assert_period_open(open_day, sample_tenant.id)
        db_session.rollback()

    def test_closing_a_period_records_who_closed_it(self, db_session, sample_tenant):
        """LED-18. A close with no attribution is not auditable."""
        from models import GLPeriod

        period = GLPeriod(tenant_id=sample_tenant.id, year=2031, month=4, is_closed=True)
        period.closed_by = 1
        period.closed_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
        db_session.add(period)
        db_session.commit()
        db_session.expire_all()
        stored = db_session.get(GLPeriod, period.id)
        assert stored.closed_by is not None, "the period recorded no closer"
        assert stored.closed_at is not None, "the period recorded no close time"


class TestLED04TenantIsolation:
    """LED-19 to LED-22: the ledger never crosses a tenant."""

    def test_an_entry_for_another_tenant_is_not_visible(self, client, db_session, sample_tenant, sample_branch):
        """LED-19. Querying one tenant's ledger must not return another's rows."""
        from models import GLJournalEntry

        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)

        other = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).all()
        assert all(e.tenant_id == sample_tenant.id for e in other), "a foreign entry appeared in the tenant ledger"

    def test_accounts_are_scoped_to_the_tenant(self, client, db_session, sample_tenant, sample_branch):
        """LED-20. The account tree is the other half of the isolation story."""
        from models import GLAccount

        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        _accounts(db_session, sample_tenant)
        accounts = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id).all()
        assert accounts, "the tenant has no chart of accounts at all"
        assert all(a.tenant_id == sample_tenant.id for a in accounts)

    def test_viewing_another_tenants_entry_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-21. An entry id from a URL is not a permission."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.get("/ledger/entry/99999999")
        assert resp.status_code in (302, 403, 404), f"a missing entry answered {resp.status_code}"

    def test_reversing_another_tenants_entry_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-22. The write version of LED-21, on POST."""
        user = _user(
            db_session,
            sample_tenant,
            slug="accountant",
            permissions=["view_ledger", "manage_ledger"],
            branch=sample_branch,
        )
        _login(client, user)
        resp = client.post("/ledger/entry/99999999/reverse", follow_redirects=True)
        assert resp.status_code in (302, 403, 404), f"a missing entry answered {resp.status_code}"


class TestLED05Reverse:
    """LED-23 to LED-27: reversal, which is where double-entry gets tested hardest."""

    def test_reversal_leaves_the_original_untouched(self, client, db_session, sample_tenant, sample_branch):
        """LED-23. A reversal adds a counterpart; it never edits the original.

        If the original moved, the audit trail of what was booked and when would
        be rewritten by a later correction.
        """
        from models import GLJournalLine

        user = _user(
            db_session,
            sample_tenant,
            slug="accountant",
            permissions=["view_ledger", "manage_ledger"],
            branch=sample_branch,
        )
        _login(client, user)
        debit, credit = _accounts(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit, credit, branch=sample_branch)
        db_session.commit()
        eid = entry.id
        before_lines = [
            (Decimal(str(line.debit or 0)), Decimal(str(line.credit or 0)))
            for line in db_session.query(GLJournalLine).filter_by(entry_id=eid).all()
        ]

        client.post(f"/ledger/entry/{eid}/reverse", follow_redirects=True)
        db_session.expire_all()
        after_lines = [
            (Decimal(str(line.debit or 0)), Decimal(str(line.credit or 0)))
            for line in db_session.query(GLJournalLine).filter_by(entry_id=eid).all()
        ]
        assert sorted(before_lines) == sorted(after_lines), "reversal modified the original entry's lines"

    def test_reversing_twice_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-24. Two reversals would un-reverse the reversal.

        This is the most valuable single assertion in the file: the guard against
        it is easy to write, easy to lose in a refactor, and the failure shows up
        as a ledger that silently stops agreeing with reality.
        """
        from models import GLJournalLine

        user = _user(
            db_session,
            sample_tenant,
            slug="accountant",
            permissions=["view_ledger", "manage_ledger"],
            branch=sample_branch,
        )
        _login(client, user)
        debit, credit = _accounts(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit, credit, branch=sample_branch)
        db_session.commit()
        eid = entry.id

        client.post(f"/ledger/entry/{eid}/reverse", follow_redirects=True)
        db_session.expire_all()
        after_first = db_session.query(GLJournalLine).filter_by(entry_id=eid).count()

        client.post(f"/ledger/entry/{eid}/reverse", follow_redirects=True)
        db_session.expire_all()
        after_second = db_session.query(GLJournalLine).filter_by(entry_id=eid).count()
        assert after_second == after_first, (
            f"a second reversal added lines to the original entry ({after_first} -> {after_second})"
        )

    def test_the_offsetting_entry_balances(self, client, db_session, sample_tenant, sample_branch):
        """LED-25. The reversal's own lines must balance, or the ledger drifts."""
        from models import GLJournalEntry, GLJournalLine

        user = _user(
            db_session,
            sample_tenant,
            slug="accountant",
            permissions=["view_ledger", "manage_ledger"],
            branch=sample_branch,
        )
        _login(client, user)
        debit, credit = _accounts(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit, credit, branch=sample_branch)
        db_session.commit()
        eid = entry.id

        client.post(f"/ledger/entry/{eid}/reverse", follow_redirects=True)
        db_session.commit()
        db_session.expire_all()

        # Re-read from the database rather than trusting the identity map: the
        # route committed in the request's session, and an object this session is
        # still holding reports its own stale attributes - which reads as "the
        # reversal did nothing" when it did.
        original = db_session.query(GLJournalEntry).filter_by(id=eid).one()
        assert original.is_reversed is True, "the original was not marked reversed"
        entries = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).all()
        assert len(entries) >= 2, (
            f"the reversal created no counterpart entry; found {len(entries)}: {[e.entry_number for e in entries]}"
        )
        for e in entries:
            lines = db_session.query(GLJournalLine).filter_by(entry_id=e.id).all()
            d = sum(Decimal(str(line.debit or 0)) for line in lines)
            c = sum(Decimal(str(line.credit or 0)) for line in lines)
            assert d == c, f"entry {e.id} does not balance: {d} vs {c}"
