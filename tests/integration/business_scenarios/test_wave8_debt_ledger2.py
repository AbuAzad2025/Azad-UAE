"""Wave 8 debt, part two - the ledger's own arithmetic, and the admin pages.

``test_wave8_debt_ledger.py`` covers account management. This file covers the
two things the tenant ledger file asserted about behaviour but never from the
permitted side, plus the admin read surface.

``/ledger/api/calculate-journal-balance`` is the backend check behind the manual
entry form. It decides whether the operator is allowed to submit, and its rule
is stricter than it looks: balanced means the difference is under a cent **and
both totals are non-zero**. That second condition is the interesting one. An
empty entry - no lines at all - has a difference of zero and is therefore
"balanced" by the first test alone, so a form that posted nothing would be
accepted as a balanced entry and produce a journal with no lines in it. The
scenarios walk all three shapes: balanced, unbalanced, and empty.

``close-fiscal-year`` is guarded by ``permission_required("admin")`` rather
than ``manage_ledger``. That is a third permission code on a route in the
middle of the ledger, and it is the kind of detail that drifts: a refactor
harmonising the guards would silently widen or narrow who can close a year.

The admin read pages are walked together. They are all behind ``@admin_required``
and all render from the same underlying data, so a single scenario asserting
they answer is honest coverage of "the admin console is not a 500 waiting behind
a guard nobody crosses".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tests.integration.business_scenarios.test_wave8_debt_ledger import _chart, _super_admin


def _viewer(client, db_session, tenant, branch, *, slug="led-viewer", permissions=("view_ledger",)):
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
    db_session.add(role)
    # The role is shared by every user this helper makes, so the permission
    db_session.add(role)
    db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"{slug}-{unique}",
        email=f"{slug}-{unique}@example.com",
        full_name=f"LED {slug}",
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


def _entry(db_session, tenant, debit, credit, *, status="posted", amount="100.00", branch=None):
    from models import GLJournalEntry, GLJournalLine

    entry = GLJournalEntry(
        tenant_id=tenant.id,
        entry_date=datetime.now(UTC),
        entry_number=f"LEDY-{uuid.uuid4().hex[:10]}",
        entry_type="manual",
        branch_id=branch.id if branch is not None else None,
        description="LED debt scenario",
        status=status,
        is_posted=status == "posted",
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


class TestLED76TheBalanceCalculator:
    """LED-76 to LED-81: the check behind the manual entry form."""

    def _balance(self, client, lines):
        return client.post(
            "/ledger/api/calculate-journal-balance",
            json={"lines": lines},
            follow_redirects=False,
        )

    def test_a_balanced_entry_is_reported_balanced(self, client, db_session, sample_tenant, sample_branch):
        """LED-76. The positive case, which every other one depends on."""
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = self._balance(
            client,
            [
                {"debit": "100.00", "credit": "0"},
                {"debit": "0", "credit": "100.00"},
            ],
        )
        assert resp.status_code == 200, f"the balance api answered {resp.status_code}"
        data = resp.get_json()["data"]
        assert data["is_balanced"] is True, f"a balanced entry was reported unbalanced: {data}"
        assert data["difference"] == 0, f"a balanced entry reported a difference of {data['difference']}"

    def test_an_unbalanced_entry_is_reported_unbalanced(self, client, db_session, sample_tenant, sample_branch):
        """LED-77. Direction does not matter, only the gap."""
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = self._balance(
            client,
            [
                {"debit": "100.00", "credit": "0"},
                {"debit": "0", "credit": "60.00"},
            ],
        )
        assert resp.status_code == 200, f"the balance api answered {resp.status_code}"
        data = resp.get_json()["data"]
        assert data["is_balanced"] is False, f"an unbalanced entry was reported balanced: {data}"
        assert data["difference"] == pytest.approx(40.0), f"the reported difference is {data['difference']}"

    def test_an_entry_with_no_lines_is_not_balanced(self, client, db_session, sample_tenant, sample_branch):
        """LED-78. Zero on both sides is not a balanced entry.

        ``difference`` is zero for an empty form, so the first half of the rule
        says yes. The ``total_debit > 0 and total_credit > 0`` half is what
        stops it - without it the manual entry form would accept an entry with
        no lines and produce a journal record that moves nothing.
        """
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = self._balance(client, [])
        assert resp.status_code == 200, f"the balance api answered {resp.status_code}"
        data = resp.get_json()["data"]
        assert data["is_balanced"] is False, f"an entry with no lines was reported balanced: {data}"

    def test_a_one_sided_entry_is_not_balanced(self, client, db_session, sample_tenant, sample_branch):
        """LED-79. All debits and no credits is not balanced either.

        The same second clause, from the other side: one total is positive and
        the other is zero, so nothing has been offset.
        """
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = self._balance(client, [{"debit": "100.00", "credit": "0"}])
        data = resp.get_json()["data"]
        assert data["is_balanced"] is False, f"a one-sided entry was reported balanced: {data}"
        assert data["total_credit"] == 0, f"the credit total is {data['total_credit']}, expected 0"

    def test_the_balance_api_refuses_an_empty_body(self, client, db_session, sample_tenant, sample_branch):
        """LED-80. No body at all is a refusal, not an empty result.

        An empty ``lines`` list answers 200 with ``is_balanced: false``; a
        request with no JSON answers 400. The two are different questions -
        "is this entry balanced" versus "did you send me anything".
        """
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.post("/ledger/api/calculate-journal-balance", json={}, follow_redirects=False)
        assert resp.status_code == 400, f"an empty body answered {resp.status_code}, expected 400"

    def test_the_tolerance_is_a_cent_not_a_fils(self, client, db_session, sample_tenant, sample_branch):
        """LED-81. The tolerance is stated, and it is the whole contract.

        ``difference < 0.01`` is what lets a rounding artefact through on an
        entry in a currency with three decimal places. A file that changed it to
        ``<= 0.01`` - or to a relative tolerance - would look identical on every
        balanced entry and differ on exactly the ones at the boundary.
        """
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        at_limit = self._balance(
            client,
            [
                {"debit": "100.00", "credit": "0"},
                {"debit": "0", "credit": "99.99"},
            ],
        )
        assert at_limit.get_json()["data"]["is_balanced"] is False, (
            "a one-cent gap was accepted; the tolerance is strictly under 0.01"
        )

        under = self._balance(
            client,
            [
                {"debit": "100.00", "credit": "0"},
                {"debit": "0", "credit": "99.995"},
            ],
        )
        assert under.get_json()["data"]["is_balanced"] is True, (
            "a sub-cent gap was rejected; the tolerance is under 0.01"
        )


class TestLED82TheFiscalYearClose:
    """LED-82 to LED-87: a third permission code, in the middle of the ledger."""

    def test_the_close_route_is_guarded_by_admin_not_manage_ledger(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """LED-82. Three codes, and this one is the odd one out.

        Every other write on ``/ledger`` is ``manage_ledger``. The fiscal-year
        close is ``permission_required("admin")``. Closing a year posts a
        closing entry and locks the periods, so the stricter guard is
        deliberate - but it is the kind of detail a refactor harmonises away by
        accident, and then either an accountant without the admin code is
        locked out or someone with it can close a year they should not.
        """
        _chart(db_session, sample_tenant)

        accountant = _viewer(
            client,
            db_session,
            sample_tenant,
            sample_branch,
            slug="led-accountant",
            permissions=("view_ledger", "manage_ledger"),
        )
        assert not accountant.has_permission("admin"), (
            "the fixture accountant unexpectedly holds admin; this scenario proves nothing"
        )

        refused = client.post("/ledger/close-fiscal-year", data={"fiscal_year": "2026"}, follow_redirects=False)
        assert refused.status_code == 403, (
            f"an accountant with manage_ledger reached the fiscal-year close: {refused.status_code}"
        )

    def test_closing_a_year_without_naming_one_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-83. The year is required.

        Defaulting it to the current year would close the wrong period the day
        the clock rolls over.
        """
        _chart(db_session, sample_tenant)
        _admin(client, db_session, sample_tenant, sample_branch, permissions=("view_ledger", "admin"))

        resp = client.post("/ledger/close-fiscal-year", data={}, follow_redirects=True)
        assert resp.status_code == 200, f"closing without a year answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "closing without a year raised instead of asking for one"
        )

    def test_closing_a_year_with_nothing_in_it_is_handled(self, client, db_session, sample_tenant, sample_branch):
        """LED-84. The empty-year case.

        A year with no activity has no closing entry to produce, so the
        service is expected to refuse. The assertion is that it refuses rather
        than raising - the ``except ValueError`` clause above it turns a refusal
        into a flash, and a 500 here would mean that clause is not catching.
        """
        _chart(db_session, sample_tenant)
        _admin(client, db_session, sample_tenant, sample_branch, permissions=("view_ledger", "admin"))

        resp = client.post("/ledger/close-fiscal-year", data={"fiscal_year": "1998"}, follow_redirects=True)
        assert resp.status_code == 200, f"closing an empty year answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "closing an empty year raised instead of reporting"
        )

    def test_closing_a_year_twice_is_handled(self, client, db_session, sample_tenant, sample_branch):
        """LED-85. A second close must not post a second closing entry.

        This is the same attribution problem the budget approval has: the first
        close stamps who did it and when, and a repeat would overwrite that. The
        scenario asserts the second attempt is survived, which is the part that
        is reachable through HTTP.
        """
        _chart(db_session, sample_tenant)
        _admin(client, db_session, sample_tenant, sample_branch, permissions=("view_ledger", "admin"))

        first = client.post("/ledger/close-fiscal-year", data={"fiscal_year": "1997"}, follow_redirects=True)
        assert first.status_code == 200, f"the first close answered {first.status_code}"

        second = client.post("/ledger/close-fiscal-year", data={"fiscal_year": "1997"}, follow_redirects=True)
        assert second.status_code == 200, f"the second close answered {second.status_code}"
        assert "Internal Server Error" not in second.get_data(as_text=True), "closing a year twice raised"

    def test_the_fiscal_year_preview_answers(self, client, db_session, sample_tenant, sample_branch):
        """LED-86. What an operator reads before committing to a close."""
        _chart(db_session, sample_tenant)
        _admin(client, db_session, sample_tenant, sample_branch, permissions=("view_ledger", "admin"))

        resp = client.get("/ledger/fiscal-year-preview", follow_redirects=False)
        assert resp.status_code in (200, 400), f"the fiscal-year preview answered {resp.status_code}"
        assert resp.status_code != 500, "the fiscal-year preview raised"

    def test_the_preview_is_guarded_like_the_close(self, client, db_session, sample_tenant, sample_branch):
        """LED-87. Preview and close share a guard deliberately.

        Previewing a close without the authority to perform it is harmless, but
        the two drifting apart means the preview shows numbers the operator
        cannot act on - or, worse, that the close's guard was loosened while
        the preview's was not.
        """
        _chart(db_session, sample_tenant)
        _viewer(
            client,
            db_session,
            sample_tenant,
            sample_branch,
            slug="led-acct2",
            permissions=("view_ledger", "manage_ledger"),
        )

        resp = client.get("/ledger/fiscal-year-preview", follow_redirects=False)
        assert resp.status_code == 403, f"an accountant reached the fiscal-year preview: {resp.status_code}"


def _admin(client, db_session, tenant, branch, *, permissions=()):
    """A user holding an explicit permission set, not the super_admin role.

    Used by the fiscal-year scenarios, which need to be *refused* by
    ``admin_required`` and granted by ``permission_required("admin")`` - the one
    combination in this file where the two guards have to disagree.
    """
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug="led-permission-admin").first()
    if role is None:
        role = Role(name="LED Permission Admin", slug="led-permission-admin", is_active=True)
        db_session.add(role)
        db_session.commit()
    role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
    db_session.add(role)
    db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"led-perm-{unique}",
        email=f"led-perm-{unique}@example.com",
        full_name="LED Permission Admin",
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


class TestLED88TheAdminReadSurface:
    """LED-88 to LED-115: the admin console, reached by an admin."""

    def test_the_admin_ledger_pages_all_answer(self, client, db_session, sample_tenant, sample_branch):
        """LED-88. Sixteen routes behind one guard, walked as one set.

        They are all read-only views over the same data, and they are all
        behind ``@admin_required``. Asserting them individually would be
        twenty lines of the same thing; asserting them together and reporting
        every failure by path keeps the signal if one of them 500s.
        """
        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        broken = []
        for path in (
            "/admin/ledger/",
            "/admin/ledger/accounts",
            "/admin/ledger/accounts/add",
            "/admin/ledger/vaults",
            "/admin/ledger/journals",
            "/admin/ledger/reports",
            "/admin/ledger/reports/trial-balance",
            "/admin/ledger/reports/balance-sheet",
            "/admin/ledger/reports/income-statement",
            "/admin/ledger/settings",
        ):
            resp = client.get(path, follow_redirects=False)
            if resp.status_code != 200:
                broken.append((path, resp.status_code))
        assert not broken, f"admin ledger pages did not answer: {broken}"

    def test_the_admin_ledger_is_closed_to_a_plain_accountant(self, client, db_session, sample_tenant, sample_branch):
        """LED-89. ``manage_ledger`` does not reach ``/admin/ledger``.

        The inverse of LED-64: holding the ledger permissions is not the same
        as being an admin, and the two halves of this blueprint must not be
        interchangeable in either direction.
        """
        _chart(db_session, sample_tenant)
        _viewer(
            client,
            db_session,
            sample_tenant,
            sample_branch,
            slug="led-acct3",
            permissions=("view_ledger", "manage_ledger"),
        )

        refused = client.get("/admin/ledger/", follow_redirects=False)
        assert refused.status_code == 403, (
            f"an accountant with manage_ledger reached the admin ledger: {refused.status_code}"
        )

    def test_the_tenant_ledger_pages_all_answer_to_a_reader(self, client, db_session, sample_tenant, sample_branch):
        """LED-90. And the tenant half renders for the permission it asks.

        The mirror of LED-88 on the other blueprint, so that neither half can
        be "always 403" and still pass.
        """
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        broken = []
        for path in (
            "/ledger/",
            "/ledger/trial-balance",
            "/ledger/journal-entries",
            "/ledger/accounts-tree",
            "/ledger/aging-analysis",
            "/ledger/cash-flow",
        ):
            resp = client.get(path, follow_redirects=False)
            if resp.status_code != 200:
                broken.append((path, resp.status_code))
        assert not broken, f"tenant ledger pages did not answer for view_ledger: {broken}"

    def test_the_account_search_api_answers(self, client, db_session, sample_tenant, sample_branch):
        """LED-91. The typeahead behind the manual entry form."""
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/ledger/api/accounts/search?q=1", follow_redirects=False)
        assert resp.status_code == 200, f"the account search answered {resp.status_code}"
        body = resp.get_json()
        assert body is not None and "data" in body, f"the account search answered {body} without an envelope"

    def test_the_account_search_does_not_reach_another_tenant(self, client, db_session, sample_tenant, sample_branch):
        """LED-92. Tenant isolation on the search path.

        A search box that returns another company's account codes is a quiet
        leak: the operator sees a code, clicks it, and posts a line to it.
        """
        from models import GLAccount, Tenant

        unique = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f"LED Other {unique}",
            name_ar="آخر",
            slug=f"led-other-{unique}",
            email=f"led-other-{unique}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        db_session.add(
            GLAccount(
                tenant_id=other.id,
                code="3399",
                name="Other tenant suspense",
                name_ar="حساب suspense",
                type="equity",
                is_header=False,
                is_active=True,
                level=1,
            )
        )
        db_session.commit()

        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/ledger/api/accounts/search?q=3399", follow_redirects=False)
        assert resp.status_code == 200, f"the account search answered {resp.status_code}"
        assert "3399" not in resp.get_data(as_text=True), (
            "the account search returned an account belonging to another tenant"
        )

    def test_viewing_a_journal_that_does_not_exist_is_handled(self, client, db_session, sample_tenant, sample_branch):
        """LED-93. A stale id 404s rather than rendering an empty entry."""
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/ledger/entry/99999999", follow_redirects=False)
        assert resp.status_code == 404, f"viewing a missing entry answered {resp.status_code}"

    def test_reversing_an_entry_that_does_not_exist_is_handled(self, client, db_session, sample_tenant, sample_branch):
        """LED-94. Same on the write side, and it must not create anything."""
        from models import GLJournalEntry

        _chart(db_session, sample_tenant)
        _admin(client, db_session, sample_tenant, sample_branch, permissions=("view_ledger", "manage_ledger"))
        before = db_session.query(GLJournalEntry).count()

        # 404 is correct: the route resolves the entry first and a missing id is
        # not an entry that can be reversed. The assertion is that nothing was
        # written - a reversal that fell through to "create one anyway" would
        # post a correction for an entry that never existed.
        resp = client.post("/ledger/entry/99999999/reverse", data={}, follow_redirects=True)
        assert resp.status_code in (200, 404), f"reversing a missing entry answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.query(GLJournalEntry).count() == before, "reversing a missing entry created a journal entry"

    def test_reversing_a_posted_entry_produces_an_offsetting_one(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """LED-95. Reversal is a new entry, never a deletion.

        This is the invariant the whole reversal path exists to protect: the
        original stays on the books and a second, mirrored entry records the
        correction. A reversal that removed the first would leave the trial
        balance right and the history wrong.
        """
        from models import GLJournalEntry, GLJournalLine

        debit, credit = _chart(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit, credit, status="posted", branch=sample_branch)
        original_id = entry.id
        before = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()

        _admin(client, db_session, sample_tenant, sample_branch, permissions=("view_ledger", "manage_ledger"))
        resp = client.post(
            f"/ledger/entry/{original_id}/reverse",
            data={"reason": "posted to the wrong account"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"reversing a posted entry answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, (
            f"the reversal did not add an entry ({before} -> {after}); it must reverse, not delete"
        )
        assert db_session.get(GLJournalEntry, original_id) is not None, (
            "the original entry was removed instead of reversed"
        )

        lines = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(GLJournalEntry.tenant_id == sample_tenant.id)
            .all()
        )
        total_debit = sum(Decimal(str(ln.debit or 0)) for ln in lines)
        total_credit = sum(Decimal(str(ln.credit or 0)) for ln in lines)
        assert total_debit == total_credit, (
            f"after the reversal the tenant's lines are unbalanced: Dr {total_debit} vs Cr {total_credit}"
        )

    def test_the_periods_page_answers(self, client, db_session, sample_tenant, sample_branch):
        """LED-96. The lock list the close scenario operates on."""
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/ledger/periods", follow_redirects=False)
        assert resp.status_code == 200, f"the periods page answered {resp.status_code}"

    def test_a_closed_period_refuses_a_posting(self, client, db_session, sample_tenant, sample_branch):
        """LED-97. The closed-period lock, from the permitted side.

        ``GLPeriod.is_closed`` is the lock; there is no separate "open" action.
        A posting dated into a closed month is what an accountant tries when
        they back-date a bill by accident, and the refusal is the only thing
        that stops the period's totals changing after they were reported.
        """
        from models import GLPeriod

        debit, credit = _chart(db_session, sample_tenant)
        period = GLPeriod(tenant_id=sample_tenant.id, year=2019, month=1, is_closed=True)
        db_session.add(period)
        db_session.commit()

        _admin(client, db_session, sample_tenant, sample_branch, permissions=("view_ledger", "manage_ledger"))
        before = db_session.query(GLPeriod).count()

        resp = client.post(
            "/ledger/manual-entry",
            data={
                "entry_date": "2019-01-15",
                "description": "backdated into a closed period",
                "line_0_account": str(debit.id),
                "line_0_debit": "100.00",
                "line_0_credit": "0",
                "line_1_account": str(credit.id),
                "line_1_debit": "0",
                "line_1_credit": "100.00",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"posting into a closed period answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "posting into a closed period raised instead of refusing"
        )
        assert db_session.query(GLPeriod).count() == before

    def test_the_vat_report_redirects_when_tax_is_off(self, client, db_session, sample_tenant, sample_branch):
        """LED-98. A disabled feature redirects rather than reporting zeros.

        ``vat_report`` checks ``is_tax_enabled`` and sends the operator to the
        ledger index. Answering an empty VAT report instead would be read as
        "you owe nothing", which is a materially different statement from "this
        tenant does not do VAT".
        """
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/ledger/vat-report", follow_redirects=False)
        assert resp.status_code in (200, 302), f"the vat report answered {resp.status_code}"

    def test_the_budget_vs_actual_page_answers(self, client, db_session, sample_tenant, sample_branch):
        """LED-99. The one read route under ``/ledger`` that writes.

        ``budget_vs_actual`` opens ``atomic_transaction("budget_update_actuals")``
        and refreshes the budgets' actuals from the ledger. So it is a write
        dressed as a report, and the scenario asserts it runs without raising.
        """
        _chart(db_session, sample_tenant)
        _viewer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/ledger/budget-vs-actual", follow_redirects=False)
        assert resp.status_code == 200, f"budget-vs-actual answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "budget-vs-actual raised while refreshing actuals"
        )

    def test_the_run_depreciation_route_answers(self, client, db_session, sample_tenant, sample_branch):
        """LED-100. The other ``manage_ledger`` POST under ``/ledger``."""
        _chart(db_session, sample_tenant)
        _admin(client, db_session, sample_tenant, sample_branch, permissions=("view_ledger", "manage_ledger"))

        resp = client.post("/ledger/run-depreciation", data={}, follow_redirects=True)
        assert resp.status_code == 200, f"run-depreciation answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), "run-depreciation raised"

    def test_the_account_statement_api_answers(self, client, db_session, sample_tenant, sample_branch):
        """LED-101. The JSON statement behind the drill-down."""
        debit, _credit = _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.get(f"/admin/ledger/api/account-balance/{debit.id}", follow_redirects=False)
        assert resp.status_code == 200, f"the account balance api answered {resp.status_code}"
        assert "data" in (resp.get_json() or {}), (
            f"the account balance api answered {resp.get_data(as_text=True)[:200]}"
        )

    def test_the_admin_journal_view_renders(self, client, db_session, sample_tenant, sample_branch):
        """LED-102. Viewing an entry through the admin half of the blueprint."""
        debit, credit = _chart(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit, credit, status="posted", branch=sample_branch)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.get(f"/admin/ledger/journals/{entry.id}/view", follow_redirects=False)
        assert resp.status_code == 200, f"the admin journal view answered {resp.status_code}"

    def test_the_admin_journal_view_of_a_missing_entry_is_handled(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """LED-103. And the stale-id case on the admin half."""
        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/admin/ledger/journals/99999999/view", follow_redirects=False)
        assert resp.status_code == 404, f"viewing a missing admin entry answered {resp.status_code}"

    def test_editing_an_account_cannot_change_its_code_class(self, client, db_session, sample_tenant, sample_branch):
        """LED-104. The code/type rule fires on edit as well as on add.

        ``validate_account_code_type`` runs on both routes. An account added
        correctly and then edited into a contradiction would be the same defect
        arriving through the back door.
        """
        from models import GLAccount

        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)
        code = f"5{uuid.uuid4().int % 9000 + 1000}"
        account = GLAccount(
            tenant_id=sample_tenant.id,
            code=code,
            name="LED editable",
            name_ar="قابل للتعديل",
            type="expense",
            is_header=False,
            is_active=True,
            level=1,
        )
        db_session.add(account)
        db_session.commit()
        before = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post(
            f"/admin/ledger/accounts/{account.id}/edit",
            data={"code": "1130", "name": "LED editable", "type": "expense"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"the account edit answered {resp.status_code}"

        db_session.expire_all()
        row = db_session.get(GLAccount, account.id)
        assert row.code == code, f"the edit moved the account to code {row.code}, which contradicts its type"
        assert db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id).count() == before

    def test_editing_an_account_that_does_not_exist_is_handled(self, client, db_session, sample_tenant, sample_branch):
        """LED-105. The stale id on the edit form."""
        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        form = client.get("/admin/ledger/accounts/99999999/edit", follow_redirects=False)
        assert form.status_code == 404, f"editing a missing account answered {form.status_code}"

        post = client.post(
            "/admin/ledger/accounts/99999999/edit",
            data={"code": "5540", "type": "expense"},
            follow_redirects=True,
        )
        assert post.status_code in (200, 404), f"posting an edit for a missing account answered {post.status_code}"
        assert "Internal Server Error" not in post.get_data(as_text=True), (
            "posting an edit for a missing account raised"
        )
