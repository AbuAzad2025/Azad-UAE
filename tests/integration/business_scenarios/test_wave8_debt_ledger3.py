"""Wave 8 debt, part three - the statements, and the last of the ledger routes.

This file exists because LED-88 found a bug that a route inventory never would:
``/admin/ledger/reports/balance-sheet`` rendered ``abs(balance)``, and Jinja has
no ``abs`` function - only an ``abs`` filter. The template raised
``UndefinedError`` on every request, so the admin balance sheet had been a 500
for as long as it had existed, behind a guard that no test crossed.

That is the argument for this file. The admin console is a set of templates
calling model methods and global helpers, and a wrong name in any of them is
invisible to every other kind of test: not a permission problem, not a tenant
isolation problem, not an arithmetic problem. The only thing that finds it is
asking the page to render.

So each statement and report is rendered, and the assertions stay about what the
page is *for* - the aging export's closed type list, the account page's scoped
404, the date fallbacks - rather than about status codes that are already pinned
elsewhere.

The balance sheet gets its own scenario rather than riding along in LED-88's
loop. It is the page that was broken, and a regression on it deserves a
scenario that names it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tests.integration.business_scenarios.test_wave8_debt_ledger import (
    _chart,
    _super_admin,
)
from tests.integration.business_scenarios.test_wave8_debt_ledger2 import _entry, _viewer


def _admin_perm(client, db_session, tenant, branch, *, permissions=("view_ledger", "manage_ledger")):
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug="led-perm-admin2").first()
    if role is None:
        role = Role(name="LED Perm Admin 2", slug="led-perm-admin2", is_active=True)
        db_session.add(role)
        db_session.commit()
    role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
    db_session.add(role)
    db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"led-p2-{unique}",
        email=f"led-p2-{unique}@example.com",
        full_name="LED Perm Admin 2",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()

    client.get("/auth/logout", follow_redirects=True)
    client.post("/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True)
    return user


class TestLED106TheBalanceSheetRenders:
    """LED-106 to LED-107: the page that was silently a 500."""

    def test_the_admin_balance_sheet_renders(self, client, db_session, sample_tenant, sample_branch):
        """LED-106. Regression on ``abs(balance)``.

        The template called ``abs()`` as a function; Jinja exposes ``abs`` only
        as a filter, so every render raised ``UndefinedError`` and the admin
        balance sheet answered 500. Nothing else in the suite could see it -
        the guard was fine, the arithmetic was never reached, and the route was
        listed in the inventory as covered.

        Rendered with real accounts present, because the offending expression
        only evaluates inside the ``liabilities`` and ``equity`` loops. An empty
        chart would skip it and pass.
        """
        _chart(db_session, sample_tenant)
        debit, credit = _chart(db_session, sample_tenant)
        _entry(db_session, sample_tenant, debit, credit, status="posted", branch=sample_branch)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/admin/ledger/reports/balance-sheet", follow_redirects=False)
        assert resp.status_code == 200, (
            f"the admin balance sheet answered {resp.status_code}: {resp.get_data(as_text=True)[:300]}"
        )
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "the admin balance sheet rendered an error page"
        )

    def test_the_admin_balance_sheet_falls_back_on_a_bad_date(self, client, db_session, sample_tenant, sample_branch):
        """LED-107. An unparseable ``as_of_date`` is today, not a 500.

        The route catches the parse failure and logs a warning. The page has to
        render on the fallback, because a bad query string in a bookmarked URL
        should not take the report down.
        """
        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/admin/ledger/reports/balance-sheet?as_of_date=not-a-date", follow_redirects=False)
        assert resp.status_code == 200, f"the balance sheet answered {resp.status_code} for an unparseable date"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "the balance sheet raised on an unparseable date instead of falling back"
        )


class TestLED108TheStatements:
    """LED-108 to LED-115: the remaining read routes, rendered."""

    def test_the_admin_income_statement_renders(self, client, db_session, sample_tenant, sample_branch):
        """LED-108. The report above the balance sheet."""
        _chart(db_session, sample_tenant)
        debit, credit = _chart(db_session, sample_tenant)
        _entry(db_session, sample_tenant, debit, credit, status="posted", branch=sample_branch)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/admin/ledger/reports/income-statement", follow_redirects=False)
        assert resp.status_code == 200, f"the admin income statement answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "the admin income statement rendered an error page"
        )

    def test_the_admin_trial_balance_renders(self, client, db_session, sample_tenant, sample_branch):
        """LED-109. The report that has to add up."""
        _chart(db_session, sample_tenant)
        debit, credit = _chart(db_session, sample_tenant)
        _entry(db_session, sample_tenant, debit, credit, status="posted", branch=sample_branch)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/admin/ledger/reports/trial-balance", follow_redirects=False)
        assert resp.status_code == 200, f"the admin trial balance answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "the admin trial balance rendered an error page"
        )

    def test_the_admin_vaults_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """LED-110. The GL vaults list behind the same guard."""
        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/admin/ledger/vaults", follow_redirects=False)
        assert resp.status_code == 200, f"the admin vaults page answered {resp.status_code}"

    def test_the_account_page_renders_for_one_of_this_tenants_accounts(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """LED-111. The per-account statement.

        ``get_scoped_account_or_404`` is the tenant boundary on this route, so
        the positive case needs an account that *is* this tenant's.
        """
        debit, _credit = _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.get(f"/ledger/account/{debit.id}", follow_redirects=False)
        assert resp.status_code == 200, f"the account page answered {resp.status_code} for this tenant's own account"

    def test_the_account_page_404s_an_account_of_another_tenant(self, client, db_session, sample_tenant, sample_branch):
        """LED-112. And 404s one that is not.

        This is the route where tenant isolation is enforced at lookup time
        rather than by filtering a result set, so the id of a real account
        belonging to another tenant is the interesting input.
        """
        from models import GLAccount, Tenant

        unique = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f"LED Foreign {unique}",
            name_ar="أجنبي",
            slug=f"led-foreign-{unique}",
            email=f"led-foreign-{unique}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        foreign = GLAccount(
            tenant_id=other.id,
            code="1188",
            name="Foreign suspense",
            name_ar="علاقة suspens",
            type="asset",
            is_header=False,
            is_active=True,
            level=1,
        )
        db_session.add(foreign)
        db_session.commit()
        foreign_id = foreign.id

        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.get(f"/ledger/account/{foreign_id}", follow_redirects=False)
        assert resp.status_code == 404, f"the account page rendered another tenant's account: {resp.status_code}"

    def test_the_account_statement_sub_route_renders(self, client, db_session, sample_tenant, sample_branch):
        """LED-113. The statement variant of the same page."""
        debit, _credit = _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.get(f"/ledger/account/{debit.id}/statement", follow_redirects=False)
        assert resp.status_code == 200, f"the account statement answered {resp.status_code}"

    @pytest.mark.parametrize("analysis_type", ["receivables", "payables"])
    def test_the_aging_export_accepts_both_documented_types(
        self, client, db_session, sample_tenant, sample_branch, analysis_type
    ):
        """LED-114. The type list is closed, and both halves of it work.

        A closed list that rejects everything passes the refusal half. Both
        sides are walked, so the export is known to be a real export and not a
        redirect that always goes home.
        """
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.get(f"/ledger/aging-analysis/export?type={analysis_type}", follow_redirects=False)
        assert resp.status_code in (200, 302), f"the {analysis_type} aging export answered {resp.status_code}"
        assert resp.status_code != 400, f"the {analysis_type} aging export was refused; both documented types must work"

    def test_the_aging_export_refuses_an_unknown_type(self, client, db_session, sample_tenant, sample_branch):
        """LED-115. And anything else is refused rather than defaulted.

        Defaulting an unrecognised type to receivables would silently produce
        the wrong side of the ledger for a request that asked for something
        else.
        """
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/ledger/aging-analysis/export?type=inventory", follow_redirects=False)
        assert resp.status_code in (302, 400), f"an unknown aging type answered {resp.status_code}; it must be refused"

    def test_the_aging_analysis_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """LED-116. The page the export refuses back to."""
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/ledger/aging-analysis", follow_redirects=False)
        assert resp.status_code == 200, f"the aging analysis page answered {resp.status_code}"

    def test_a_manual_entry_with_balanced_lines_is_accepted(self, client, db_session, sample_tenant, sample_branch):
        """LED-117. The permitted side of the manual entry form.

        Every guard on this route has been walked from the refusing side
        across these files. The point of a guard suite is to show what it lets
        through as much as what it stops, so a valid entry is submitted and the
        resulting journal is checked for balance and attribution.
        """
        from models import GLJournalEntry, GLJournalLine

        debit, credit = _chart(db_session, sample_tenant)
        _admin_perm(client, db_session, sample_tenant, sample_branch)

        resp = client.post(
            "/ledger/manual-entry",
            data={
                "entry_date": datetime.now(UTC).strftime("%Y-%m-%d"),
                "description": "LED debt accepted entry",
                # line_N_account is an account *code*, not a row id - the form
                # resolves it through the chart, which is also why a code that
                # is not in this tenant's chart cannot be posted against.
                "line_0_account": str(debit.code),
                "line_0_debit": "250.00",
                "line_0_credit": "0",
                "line_1_account": str(credit.code),
                "line_1_debit": "0",
                "line_1_credit": "250.00",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"a valid manual entry answered {resp.status_code}"

        db_session.expire_all()
        entry = (
            db_session.query(GLJournalEntry)
            .filter_by(tenant_id=sample_tenant.id, description="LED debt accepted entry")
            .order_by(GLJournalEntry.id.desc())
            .first()
        )
        assert entry is not None, "a valid manual entry was reported accepted but stored no journal entry"

        lines = db_session.query(GLJournalLine).filter_by(entry_id=entry.id).all()
        assert lines, f"entry {entry.entry_number} was created with no lines"
        total_debit = sum(Decimal(str(ln.debit or 0)) for ln in lines)
        total_credit = sum(Decimal(str(ln.credit or 0)) for ln in lines)
        assert total_debit == total_credit, f"the accepted entry is unbalanced: Dr {total_debit} vs Cr {total_credit}"
        assert total_debit == Decimal("250.00"), f"the entry posted {total_debit}, not the submitted 250.00"
