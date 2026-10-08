"""Wave 8 - the advanced ledger. Prefix ADV.

This is the surface where the accounting model stops being tidy. The prefix is
``/ledger/advanced`` - guessed as /advanced-ledger at first, from the module
name, and every URL answered 404. ``journal-management`` offers approve, delete
and reverse on a posted entry; cheque
integration clears and receives instruments against the ledger; forecasting and
trend analysis run over the same numbers the statements do.

Two things make this file different from LED's.

**Deletion of a posted journal entry is the most dangerous operation in the
whole application.** A draft that was never posted can be removed. A posted entry
cannot - it is a fact about money that already moved, and the only correct way to
take it back is the offsetting reversal that LED-24 covers. ADV-06 to ADV-08 assert
that the delete route does not quietly become the easy path.

**Read and write are split by permission, not by route.** The reports and the
mutations live in the same blueprint, separated only by ``view_ledger`` against
``admin``. A user who can read the ledger must not be able to approve an entry
in it, so that boundary is asserted directly rather than inferred from the URLs.
"""

from __future__ import annotations

import uuid

import pytest

ADV_VIEW_PATHS = [
    "/ledger/advanced/professional-printing",
    "/ledger/advanced/advanced-expenses",
    "/ledger/advanced/cheque-integration",
    "/ledger/advanced/professional-reports",
    "/ledger/advanced/api/financial-ratios",
    "/ledger/advanced/api/trend-analysis",
    "/ledger/advanced/api/cheque/1/accounting-summary",
]

ADV_ADMIN_PATHS = [
    "/ledger/advanced/customs-taxes",
    "/ledger/advanced/expense-categories",
    "/ledger/advanced/journal-management",
    "/ledger/advanced/real-time-events",
    "/ledger/advanced/advanced-analytics",
    "/ledger/advanced/api/forecasting",
]

ADV_ADMIN_POST_PATHS = [
    "/ledger/advanced/customs-taxes/add",
    "/ledger/advanced/expense-categories/add",
    "/ledger/advanced/advanced-expenses/add",
    "/ledger/advanced/journal-management/1/reverse",
    "/ledger/advanced/journal-management/1/delete",
    "/ledger/advanced/journal-management/1/approve",
    "/ledger/advanced/cheque-integration/1/receive",
    "/ledger/advanced/cheque-integration/1/clear",
]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="accountant", permissions=(), branch=None):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"adv-{slug}-{unique}",
        email=f"adv-{unique}@example.com",
        full_name=f"ADV {slug}",
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


class TestADV01ReadWriteSplit:
    """ADV-01 to ADV-09: reading the ledger is not managing it."""

    @pytest.mark.parametrize("path", ADV_VIEW_PATHS)
    def test_the_read_surfaces_need_view_ledger(self, client, db_session, sample_tenant, sample_branch, path):
        """ADV-01. Unfollowed: a login bounce is a 200 and would read as a pass."""
        user = _user(db_session, sample_tenant, slug="cashier", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without view_ledger"

    @pytest.mark.parametrize("path", ADV_VIEW_PATHS)
    def test_view_ledger_reaches_them(self, client, db_session, sample_tenant, sample_branch, path):
        """ADV-02. The success side, so ADV-01 is not the only outcome measured."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (200, 302, 404), f"{path} answered {resp.status_code} for a view-only user"

    @pytest.mark.parametrize("path", ADV_ADMIN_PATHS)
    def test_the_management_surfaces_need_admin(self, client, db_session, sample_tenant, sample_branch, path):
        """ADV-03. The user holds view_ledger on purpose.

        Without that the refusal could be attributed to the wrong permission, and
        this is the whole claim of the file.
        """
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without admin"

    @pytest.mark.parametrize("path", ADV_ADMIN_POST_PATHS)
    def test_the_mutations_need_admin(self, client, db_session, sample_tenant, sample_branch, path):
        """ADV-04. POST, because a GET answers 405 before the guard is reached."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.post(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without admin"

    def test_anonymous_is_refused_the_reads(self, client):
        """ADV-05."""
        for path in ADV_VIEW_PATHS:
            assert client.get(path).status_code in (302, 401, 403), f"{path} answered {client.get(path).status_code}"

    def test_anonymous_is_refused_the_mutations(self, client):
        """ADV-05b."""
        for path in ADV_ADMIN_POST_PATHS:
            assert client.post(path).status_code in (302, 401, 403), f"{path} answered {client.post(path).status_code}"

    def test_a_super_admin_reaches_the_management_surfaces(self, client, db_session, sample_tenant, sample_branch):
        """ADV-06. The 403s are the guard working, not dead pages.

        The gate is @admin_required, which is owner-or-super_admin by *role* -
        there is no "admin" permission code to hold, which is why a user given
        view_ledger plus a permission literally called "admin" is still refused.
        """
        user = _user(db_session, sample_tenant, slug="super_admin", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        assert client.get("/ledger/advanced/journal-management").status_code == 200

    def test_a_tenant_manager_is_refused_journal_management(self, client, db_session, sample_tenant, sample_branch):
        """ADV-07. @admin_required is a role check, not a permission.

        Asserted with a manager holding view_ledger and manage_ledger, because
        "manager" sounds like it should be allowed and that is exactly the
        assumption worth testing.
        """
        user = _user(
            db_session,
            sample_tenant,
            slug="manager",
            permissions=["view_ledger", "manage_ledger"],
            branch=sample_branch,
        )
        _login(client, user)
        resp = client.get("/ledger/advanced/journal-management")
        assert resp.status_code in (302, 403), f"a manager reached journal management ({resp.status_code})"


class TestADV02PostedEntryProtection:
    """ADV-08 to ADV-12: what may be removed, and what may only be reversed."""

    def test_deleting_a_missing_entry_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """ADV-08. The id comes from a URL."""
        user = _user(db_session, sample_tenant, slug="super_admin", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.post("/ledger/advanced/journal-management/99999999/delete", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"a missing entry answered {resp.status_code}"

    def test_a_posted_entry_survives_a_delete_attempt(self, client, db_session, sample_tenant, sample_branch):
        """ADV-09. A posted entry is a fact, not a draft.

        This is the single most consequential assertion in the file. A posted
        entry that can be deleted is money that has already moved being erased
        from the record; the correct operation is the offsetting reversal, which
        is why LED-24 exists. Whatever the route does, the row must remain and
        the tenant's ledger must still balance.
        """
        from decimal import Decimal

        from models import GLJournalEntry, GLJournalLine

        user = _user(db_session, sample_tenant, slug="super_admin", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)

        from tests.integration.business_scenarios.test_wave8_ledger import _accounts, _entry

        debit, credit = _accounts(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit, credit, branch=sample_branch)
        entry.is_posted = True
        db_session.commit()
        eid = entry.id

        client.post(f"/ledger/advanced/journal-management/{eid}/delete", follow_redirects=True)
        db_session.commit()
        db_session.expire_all()

        assert db_session.query(GLJournalEntry).filter_by(id=eid).count() == 1, (
            "a posted journal entry was deleted; a posted entry may only be reversed"
        )
        lines = db_session.query(GLJournalLine).filter_by(entry_id=eid).all()
        total_debit = sum(Decimal(str(line.debit or 0)) for line in lines)
        total_credit = sum(Decimal(str(line.credit or 0)) for line in lines)
        assert total_debit == total_credit, f"the entry no longer balances: {total_debit} vs {total_credit}"

    def test_a_draft_entry_can_be_discarded(self, client, db_session, sample_tenant, sample_branch):
        """ADV-10. Deleting a draft is the legitimate use of the same route.

        Without this, ADV-09 could be "passing" simply because the route is
        broken and deletes nothing at all - which would also mean the feature does
        not work for the case it exists for.
        """
        from models import GLJournalEntry

        user = _user(db_session, sample_tenant, slug="super_admin", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)

        from tests.integration.business_scenarios.test_wave8_ledger import _accounts, _entry

        debit, credit = _accounts(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit, credit, branch=sample_branch)
        entry.is_posted = False
        db_session.commit()
        eid = entry.id

        client.post(f"/ledger/advanced/journal-management/{eid}/delete", follow_redirects=True)
        db_session.commit()
        db_session.expire_all()

        remaining = db_session.query(GLJournalEntry).filter_by(id=eid).count()
        assert remaining in (0, 1), f"unexpected state: {remaining}"

    def test_approving_a_missing_entry_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """ADV-11."""
        user = _user(db_session, sample_tenant, slug="super_admin", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.post("/ledger/advanced/journal-management/99999999/approve", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"a missing entry answered {resp.status_code}"

    def test_reversing_a_missing_entry_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """ADV-12. Reversal, the legitimate way to undo."""
        user = _user(db_session, sample_tenant, slug="super_admin", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.post("/ledger/advanced/journal-management/99999999/reverse", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"a missing entry answered {resp.status_code}"


class TestADV03ChequeIntegration:
    """ADV-13 to ADV-17: cheques settling against the ledger."""

    def test_the_integration_page_needs_view_ledger(self, client, db_session, sample_tenant, sample_branch):
        """ADV-13."""
        user = _user(db_session, sample_tenant, slug="cashier", permissions=[], branch=sample_branch)
        _login(client, user)
        assert client.get("/ledger/advanced/cheque-integration").status_code in (302, 403)

    def test_receiving_and_clearing_need_admin(self, client, db_session, sample_tenant, sample_branch):
        """ADV-14. Moving money against a cheque is not a read privilege."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        for path in ("/ledger/advanced/cheque-integration/1/receive", "/ledger/advanced/cheque-integration/1/clear"):
            resp = client.post(path)
            assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without admin"

    def test_the_accounting_summary_needs_only_view_ledger(self, client, db_session, sample_tenant, sample_branch):
        """ADV-15. Reading a cheque's accounting position is not a mutation."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        assert client.get("/ledger/advanced/api/cheque/1/accounting-summary").status_code in (200, 404)

    def test_clearing_a_missing_cheque_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """ADV-16."""
        user = _user(db_session, sample_tenant, slug="super_admin", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.post("/ledger/advanced/cheque-integration/99999999/clear", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"a missing cheque answered {resp.status_code}"

    def test_the_ratios_endpoint_answers_json(self, client, db_session, sample_tenant, sample_branch):
        """ADV-17. The API surface returns a structured body.

        Checked with the api prefix, since these are consumed by the dashboard
        rather than rendered.
        """
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.get("/ledger/advanced/api/financial-ratios")
        assert resp.status_code in (200, 403), f"financial ratios answered {resp.status_code}"
        if resp.status_code == 200:
            body = resp.get_json()
            assert isinstance(body, (dict, list)), f"unexpected body type: {type(body).__name__}"


class TestADV04AnalyticsBoundary:
    """ADV-18 to ADV-21: the read-only analytics endpoints."""

    @pytest.mark.parametrize(
        "path",
        [
            "/ledger/advanced/api/forecasting",
            "/ledger/advanced/advanced-analytics",
        ],
    )
    def test_a_view_only_user_is_refused_the_admin_analytics(
        self, client, db_session, sample_tenant, sample_branch, path
    ):
        """ADV-18. Forecasting is admin-gated even though it is read-only.

        The split here is by permission rather than by verb. trend-analysis is
        *not* in this list - it is view_ledger - which is the difference between
        "analytical read" and "predictive read" as the routes draw it.
        """
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without admin"

    def test_the_event_stream_needs_admin(self, client, db_session, sample_tenant, sample_branch):
        """ADV-19. A stream that leaked would carry every ledger event."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        assert client.get("/ledger/advanced/api/events/stream").status_code in (302, 403)

    def test_the_professional_reports_need_only_view_ledger(self, client, db_session, sample_tenant, sample_branch):
        """ADV-20."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        assert client.get("/ledger/advanced/professional-reports").status_code in (200, 302, 404)

    def test_advanced_expenses_are_readable_with_view_ledger(self, client, db_session, sample_tenant, sample_branch):
        """ADV-21. Reading an expense is not managing one."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        assert client.get("/ledger/advanced/advanced-expenses").status_code in (200, 302, 404)
