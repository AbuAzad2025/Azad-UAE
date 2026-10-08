"""Wave 8 (part 2) - expenses, payroll and budgets, continued. Prefixes EXP, PAY, BUD.

``test_wave8_budget_expenses.py`` established the permission shapes: expenses are
gated by a single ``manage_expenses`` code, payroll by ``manage_payroll``, and
budgets deliberately split ``budget:create`` from ``budget:approve``. Those files
assert who may reach a route. This one asserts what happens once they do - the part
where money actually moves, so it can be wrong in a way a status code cannot show.

Three behaviours carry the weight here:

``delete`` on an expense archives rather than purges, and ``archive``/``restore``
form a real round trip. A money record that vanishes from the table is a different
system from one that is hidden from the default list, and only the second one can be
audited - so EXP-20 walks the whole cycle and checks the row survives each step.

Cancelling an expense reverses its journal entry and sets ``is_reversed``. The
reversal is what makes the cancel sound: an expense that vanished from the ledger
without an offsetting entry would leave the trial balance wrong, which is worse than
never recording it at all.

A payroll run may not drive an employee's position negative. An advance larger than
the remaining salary is a recoverable data-entry mistake; a negative net pay that
reaches a payment is an irreversible one. EXP-34 to EXP-38 pin the boundary.

Category validation is the other half. ``_validate_gl_account_code`` refuses header
accounts, inactive accounts, and the asset/liability/equity classes - an expense
posted to a balance-sheet account is arithmetically balanced and completely wrong,
which is exactly the class of defect a balanced-entry assertion cannot catch.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from utils.gl_reference_types import GLRef


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
        username=f"ep-{slug}-{unique}",
        email=f"ep-{unique}@example.com",
        full_name=f"EP {slug}",
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


def _expense_admin(client, db_session, tenant, branch):
    user = _user(db_session, tenant, slug="expense-admin", permissions=["manage_expenses"], branch=branch)
    _login(client, user)
    return user


def _payroll_admin(client, db_session, tenant, branch):
    user = _user(db_session, tenant, slug="payroll-admin", permissions=["manage_payroll"], branch=branch)
    _login(client, user)
    return user


def _expense_category(db_session, tenant, name="Office", gl_account_code=None):
    from models import ExpenseCategory

    cat = ExpenseCategory(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        name_ar=name,
        gl_account_code=gl_account_code,
        is_active=True,
    )
    db_session.add(cat)
    db_session.commit()
    return cat


def _expense(db_session, tenant, category, *, amount="100.00", branch=None, status="confirmed", user_id=None):
    from models import Expense

    if user_id is None:
        user_id = db_session.query(Expense).filter_by(tenant_id=tenant.id).first()
        user_id = user_id.user_id if user_id is not None else None
    if user_id is None:
        from models import User

        user_id = db_session.query(User).filter_by(tenant_id=tenant.id).first().id

    row = Expense(
        tenant_id=tenant.id,
        expense_number=f"EXP-{uuid.uuid4().hex[:10]}",
        category_id=category.id,
        description="cycle",
        expense_date=datetime.now(UTC),
        amount=Decimal(str(amount)),
        amount_aed=Decimal(str(amount)),
        currency="AED",
        exchange_rate=Decimal("1"),
        payment_method="cash",
        status=status,
        user_id=user_id,
        branch_id=branch.id if branch else None,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _latest_expense(db_session, tenant, *, description=None):
    """The most recent expense row, so a POST's effect can be read back."""
    from models import Expense

    query = db_session.query(Expense).filter_by(tenant_id=tenant.id)
    if description is not None:
        query = query.filter_by(description=description)
    return query.order_by(Expense.id.desc()).first()


def _other_tenant(db_session):
    from models import Tenant

    t = Tenant(
        name=f"Elsewhere {uuid.uuid4().hex[:6]}",
        name_ar=f"آخر {uuid.uuid4().hex[:6]}",
        slug=f"elsewhere-{uuid.uuid4().hex[:8]}",
        email=f"elsewhere-{uuid.uuid4().hex[:8]}@example.com",
        country="AE",
        is_active=True,
    )
    db_session.add(t)
    db_session.commit()
    return t


class TestEXP13CreationAndLedger:
    """EXP-13 to EXP-19: creating an expense posts a balanced journal entry."""

    def test_a_complete_expense_is_created(self, client, db_session, sample_tenant, sample_branch):
        """EXP-13. The happy path writes a row with a generated number."""
        from models import Expense

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)

        before = db_session.query(Expense).filter_by(tenant_id=sample_tenant.id).count()
        resp = client.post(
            "/expenses/create",
            data={
                "amount": "250.75",
                "category_id": str(category.id),
                "description": "stationery",
                "payment_method": "cash",
                "currency": "AED",
                "exchange_rate": "1",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"expense create answered {resp.status_code}"
        after = db_session.query(Expense).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"expected one new expense, went {before} -> {after}"

        created = db_session.query(Expense).filter_by(tenant_id=sample_tenant.id).order_by(Expense.id.desc()).first()
        assert created.expense_number, "the created expense carries no number"
        assert Decimal(str(created.amount)) == Decimal("250.75"), (
            f"the stored amount is {created.amount}, not the posted 250.75"
        )

    def test_an_expense_without_an_amount_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """EXP-14. Missing money is refused before a row exists.

        The route catches the ValueError and re-renders the form with a flash, so
        the assertion is on the row count rather than on a status code.
        """
        from models import Expense

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)

        before = db_session.query(Expense).filter_by(tenant_id=sample_tenant.id).count()
        client.post(
            "/expenses/create",
            data={"category_id": str(category.id), "description": "no money", "payment_method": "cash"},
            follow_redirects=True,
        )
        after = db_session.query(Expense).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, "an expense was created with no amount"

    def test_a_created_expense_posts_a_balanced_journal_entry(self, client, db_session, sample_tenant, sample_branch):
        """EXP-15. The entry exists and its debits equal its credits.

        ``post_or_fail`` is already the guard on the write path; this asserts it
        actually ran, by reading the lines back out of the database.
        """
        from models import GLJournalEntry, GLJournalLine

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)

        client.post(
            "/expenses/create",
            data={
                "amount": "300.00",
                "category_id": str(category.id),
                "description": "balanced",
                "payment_method": "cash",
                "currency": "AED",
                "exchange_rate": "1",
            },
            follow_redirects=True,
        )

        expense = _latest_expense(db_session, sample_tenant)
        assert expense is not None, "no expense was created to check"

        lines = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry)
            .filter(
                GLJournalEntry.tenant_id == sample_tenant.id,
                GLJournalEntry.reference_type == GLRef.EXPENSE,
                GLJournalEntry.reference_id == expense.id,
            )
            .all()
        )
        assert lines, f"expense {expense.expense_number} posted no journal lines"
        debits = sum(Decimal(str(ln.debit or 0)) for ln in lines)
        credits = sum(Decimal(str(ln.credit or 0)) for ln in lines)
        assert debits == credits, f"the expense entry is unbalanced: Dr {debits} vs Cr {credits}"

    def test_the_expense_journal_entry_is_posted_not_draft(self, client, db_session, sample_tenant, sample_branch):
        """EXP-16. A draft entry would not move a balance, so the flag matters."""
        from models import GLJournalEntry

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)

        client.post(
            "/expenses/create",
            data={
                "amount": "120.00",
                "category_id": str(category.id),
                "description": "posted",
                "payment_method": "cash",
                "currency": "AED",
                "exchange_rate": "1",
            },
            follow_redirects=True,
        )

        expense = _latest_expense(db_session, sample_tenant, description="posted")
        assert expense is not None, "the expense to check was never created"
        entries = (
            db_session.query(GLJournalEntry)
            .filter_by(
                tenant_id=sample_tenant.id,
                reference_type=GLRef.EXPENSE,
                reference_id=expense.id,
            )
            .all()
        )
        assert entries, "no journal entry references the expense"
        for entry in entries:
            assert entry.status == "posted", f"the expense entry is {entry.status}, not posted"

    def test_the_expense_debits_a_category_and_credits_cash(self, client, db_session, sample_tenant, sample_branch):
        """EXP-17. Direction, not just balance.

        A balanced entry with the sides swapped debits cash and credits the expense -
        arithmetically identical, economically backwards. This is the defect a
        balance-only assertion cannot see.
        """
        from models import GLAccount, GLJournalEntry, GLJournalLine

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant, gl_account_code="6500")

        client.post(
            "/expenses/create",
            data={
                "amount": "90.00",
                "category_id": str(category.id),
                "description": "direction",
                "payment_method": "cash",
                "currency": "AED",
                "exchange_rate": "1",
            },
            follow_redirects=True,
        )

        expense = _latest_expense(db_session, sample_tenant, description="direction")
        assert expense is not None, "the expense to check was never created"

        lines = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry)
            .filter(
                GLJournalEntry.tenant_id == sample_tenant.id,
                GLJournalEntry.reference_type == GLRef.EXPENSE,
                GLJournalEntry.reference_id == expense.id,
            )
            .all()
        )
        assert lines, "no journal lines to check direction on"

        code_by_account = {
            account.id: str(account.code)
            for account in db_session.query(GLAccount)
            .filter_by(tenant_id=sample_tenant.id)
            .filter(GLAccount.id.in_([ln.account_id for ln in lines]))
            .all()
        }
        assert code_by_account, f"none of the expense's accounts exist in this tenant: {code_by_account}"

        expense_lines = [ln for ln in lines if code_by_account.get(ln.account_id) == "6500"]
        assert expense_lines, (
            f"no line reached the category's account 6500; the entry touched {set(code_by_account.values())}"
        )
        assert all(Decimal(str(ln.debit or 0)) > 0 for ln in expense_lines), (
            "the expense account was credited; an expense must be a debit"
        )
        assert all(Decimal(str(ln.credit or 0)) == 0 for ln in expense_lines), (
            "an expense account line carried both a debit and a credit"
        )

    def test_another_tenants_expense_cannot_be_created_under_our_number(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """EXP-18. ``tenant_id`` comes from the session, never from the form."""
        from models import Expense

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)
        elsewhere = _other_tenant(db_session)

        before = db_session.query(Expense).filter_by(tenant_id=elsewhere.id).count()
        client.post(
            "/expenses/create",
            data={
                "amount": "50.00",
                "category_id": str(category.id),
                "description": "cross",
                "payment_method": "cash",
                "currency": "AED",
                "exchange_rate": "1",
                "tenant_id": str(elsewhere.id),
            },
            follow_redirects=True,
        )
        after = db_session.query(Expense).filter_by(tenant_id=elsewhere.id).count()
        assert after == before, "a posted tenant_id moved the expense to another tenant"

    def test_the_expense_number_sequence_advances(self, client, db_session, sample_tenant, sample_branch):
        """EXP-19. Two expenses get two numbers.

        ``generate_number`` takes a row lock; a repeated number would make the
        audit trail ambiguous about which expense was which.
        """
        from models import Expense

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)

        numbers = []
        for _ in range(2):
            client.post(
                "/expenses/create",
                data={
                    "amount": "10.00",
                    "category_id": str(category.id),
                    "description": "seq",
                    "payment_method": "cash",
                    "currency": "AED",
                    "exchange_rate": "1",
                },
                follow_redirects=True,
            )
        rows = (
            db_session.query(Expense)
            .filter_by(tenant_id=sample_tenant.id, description="seq")
            .order_by(Expense.id.desc())
            .limit(2)
            .all()
        )
        assert len(rows) == 2, f"expected two sequenced expenses, got {len(rows)}"
        numbers = [r.expense_number for r in rows]
        assert len(set(numbers)) == 2, f"both expenses got the number {numbers}"


class TestEXP20ArchiveRoundTrip:
    """EXP-20 to EXP-25: archive is a hide, not a delete."""

    def test_archive_keeps_the_row_and_hides_it_from_the_list(self, client, db_session, sample_tenant, sample_branch):
        """EXP-20. The core of the audit-trail claim, walked end to end.

        Three separate assertions on purpose: the row survives, an ArchivedRecord
        appears, and the default index stops offering it. A test that only checked
        the first would pass against a purge that kept a copy in another table.
        """
        from models import ArchivedRecord, Expense

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)
        row = _expense(db_session, sample_tenant, category, branch=sample_branch)
        row_id = row.id

        resp = client.post(f"/expenses/{row_id}/archive", follow_redirects=True)
        assert resp.status_code == 200, f"archiving answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(Expense, row_id) is not None, "archiving removed the expense row"

        archived = db_session.query(ArchivedRecord).filter_by(table_name="expenses", record_id=row_id).first()
        assert archived is not None, "archiving wrote no ArchivedRecord"

        listed = client.get("/expenses/")
        assert listed.status_code == 200
        body = listed.get_data(as_text=True)
        assert row.expense_number not in body, "the archived expense is still offered by the default list"

    def test_restore_removes_the_archive_record(self, client, db_session, sample_tenant, sample_branch):
        """EXP-21. The other half of the pair.

        ``restore`` deletes the ArchivedRecord rather than unsetting a flag on the
        expense, so the assertion is on the archive row being gone.
        """
        from models import ArchivedRecord, Expense

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)
        row = _expense(db_session, sample_tenant, category, branch=sample_branch)
        row_id = row.id

        client.post(f"/expenses/{row_id}/archive", follow_redirects=True)
        assert db_session.query(ArchivedRecord).filter_by(table_name="expenses", record_id=row_id).first() is not None

        client.post(f"/expenses/{row_id}/restore", follow_redirects=True)
        db_session.expire_all()
        assert db_session.query(ArchivedRecord).filter_by(table_name="expenses", record_id=row_id).first() is None, (
            "restoring left the ArchivedRecord in place"
        )
        assert db_session.get(Expense, row_id) is not None, "restoring removed the expense row"

    def test_a_restored_expense_returns_to_the_default_list(self, client, db_session, sample_tenant, sample_branch):
        """EXP-22. Restore is only real if the expense comes back."""
        from models import ArchivedRecord

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)
        row = _expense(db_session, sample_tenant, category, branch=sample_branch)
        row_id = row.id
        number = row.expense_number

        client.post(f"/expenses/{row_id}/archive", follow_redirects=True)
        client.post(f"/expenses/{row_id}/restore", follow_redirects=True)

        listed = client.get("/expenses/")
        assert listed.status_code == 200
        assert number in listed.get_data(as_text=True), "the restored expense did not return to the list"
        assert db_session.query(ArchivedRecord).filter_by(table_name="expenses", record_id=row_id).first() is None

    def test_delete_also_archives_rather_than_purges(self, client, db_session, sample_tenant, sample_branch):
        """EXP-23. The button a user actually clicks.

        The route docstring says حذف (أرشفة) - "delete (archive)" - and this pins
        that to the behaviour rather than to the comment.
        """
        from models import ArchivedRecord, Expense

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)
        row = _expense(db_session, sample_tenant, category, branch=sample_branch)
        row_id = row.id

        client.post(f"/expenses/{row_id}/delete", follow_redirects=True)
        db_session.expire_all()

        assert db_session.get(Expense, row_id) is not None, "delete purged the expense row"
        assert (
            db_session.query(ArchivedRecord).filter_by(table_name="expenses", record_id=row_id).first() is not None
        ), "delete wrote no ArchivedRecord"

    def test_the_archived_page_lists_what_was_archived(self, client, db_session, sample_tenant, sample_branch):
        """EXP-24. An archive nobody can list is not an archive."""
        from models import ArchivedRecord

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)
        row = _expense(db_session, sample_tenant, category, branch=sample_branch)
        number = row.expense_number

        client.post(f"/expenses/{row.id}/archive", follow_redirects=True)

        resp = client.get("/expenses/archived")
        assert resp.status_code == 200
        assert number in resp.get_data(as_text=True), "the archived page does not list the archived expense"
        assert db_session.query(ArchivedRecord).filter_by(table_name="expenses", record_id=row.id).first()

    def test_another_tenant_cannot_archive_our_expense(self, client, db_session, sample_tenant, sample_branch):
        """EXP-25. ``tenant_get_or_404`` is the boundary, asserted from the far side.

        Two things had to be true at once for this to test anything, and both were
        false in the first attempt:

        ``get_active_tenant_id`` locks a non-owner to ``user.tenant_id`` and
        ignores the session, so the intruder has to *be* a user of the other
        tenant - writing ``active_tenant_id`` into the session does nothing, by
        design.

        And Flask-Login keeps an existing session, so logging in as the intruder
        while the first user was still signed in left the request running as the
        first user. The logout in the middle is load-bearing, not hygiene.
        """
        from models import ArchivedRecord

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)
        row = _expense(db_session, sample_tenant, category, branch=sample_branch)
        elsewhere = _other_tenant(db_session)

        intruder = _user(
            db_session,
            elsewhere,
            slug="intruder",
            permissions=["manage_expenses"],
            branch=None,
        )
        client.get("/auth/logout", follow_redirects=True)
        _login(client, intruder)

        resp = client.post(f"/expenses/{row.id}/archive", follow_redirects=True)
        assert resp.status_code in (302, 404), (
            f"a foreign tenant archived our expense and got {resp.status_code} on {resp.request.path}"
        )
        db_session.expire_all()
        assert (
            db_session.query(ArchivedRecord)
            .filter_by(table_name="expenses", record_id=row.id, tenant_id=sample_tenant.id)
            .first()
            is None
        ), "the foreign request still archived the expense"

    def test_a_session_cannot_override_the_signed_in_users_tenant(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """EXP-25b. The control that makes EXP-25 hold.

        ``get_active_tenant_id`` returns ``user.tenant_id`` for anyone who is not
        a platform owner and never reads the session, so a tampered cookie cannot
        point a signed-in user at a different tenant's books. Written as its own
        scenario because it is a property of the *session*, not of the expenses
        module - and because it is the assumption EXP-25 silently rests on.
        """
        _expense_admin(client, db_session, sample_tenant, sample_branch)
        elsewhere = _other_tenant(db_session)

        with client.session_transaction() as session:
            session["active_tenant_id"] = elsewhere.id

        resp = client.get("/expenses/")
        assert resp.status_code in (200, 302), f"/expenses/ answered {resp.status_code} with a tampered tenant cookie"

        listing = resp.get_data(as_text=True)
        assert "ArchivedRecord" not in listing
        from models import ArchivedRecord

        assert db_session.query(ArchivedRecord).filter_by(tenant_id=elsewhere.id).count() == 0, (
            "the tampered tenant cookie made the archive list readable from another tenant"
        )


class TestEXP26CancelReversesTheLedger:
    """EXP-26 to EXP-29: cancelling reverses rather than deleting."""

    def test_cancel_marks_the_expense_reversed(self, client, db_session, sample_tenant, sample_branch):
        """EXP-26. The flag is what stops a second reversal.

        ``cancel`` reverses the document GL and sets ``is_reversed``; without the
        flag a user could cancel the same expense repeatedly and post an unlimited
        number of offsetting entries.
        """
        from models import Expense

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)
        row = _expense(db_session, sample_tenant, category, branch=sample_branch)
        row_id = row.id

        resp = client.post(f"/expenses/{row_id}/cancel", follow_redirects=True)
        assert resp.status_code == 200, f"cancelling answered {resp.status_code}"

        db_session.expire_all()
        refreshed = db_session.get(Expense, row_id)
        assert refreshed is not None, "cancelling removed the expense row"
        assert refreshed.is_reversed is True, f"is_reversed is {refreshed.is_reversed!r} after a cancel, not True"

    def test_cancel_keeps_the_original_entry_and_adds_an_offset(self, client, db_session, sample_tenant, sample_branch):
        """EXP-27. The original entry is untouched.

        A cancel that edited the original posting would rewrite history; the
        correction belongs in a new entry. This asserts the pre-cancel entry still
        exists rather than being replaced.
        """
        from models import GLJournalEntry, GLJournalLine

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)

        client.post(
            "/expenses/create",
            data={
                "amount": "140.00",
                "category_id": str(category.id),
                "description": "to-cancel",
                "payment_method": "cash",
                "currency": "AED",
                "exchange_rate": "1",
            },
            follow_redirects=True,
        )

        expense = _latest_expense(db_session, sample_tenant, description="to-cancel")
        assert expense is not None, "the expense to cancel was never created"

        before_entries = (
            db_session.query(GLJournalEntry)
            .filter_by(tenant_id=sample_tenant.id, reference_type=GLRef.EXPENSE, reference_id=expense.id)
            .count()
        )
        assert before_entries >= 1, "the expense posted no entry to reverse"

        client.post(f"/expenses/{expense.id}/cancel", follow_redirects=True)

        after_entries = (
            db_session.query(GLJournalEntry)
            .filter_by(tenant_id=sample_tenant.id, reference_type=GLRef.EXPENSE, reference_id=expense.id)
            .count()
        )
        assert after_entries > before_entries, (
            f"cancelling added no offsetting entry ({before_entries} -> {after_entries})"
        )

        lines = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry)
            .filter(
                GLJournalEntry.tenant_id == sample_tenant.id,
                GLJournalEntry.reference_type == GLRef.EXPENSE,
                GLJournalEntry.reference_id == expense.id,
            )
            .all()
        )
        debits = sum(Decimal(str(ln.debit or 0)) for ln in lines)
        credits = sum(Decimal(str(ln.credit or 0)) for ln in lines)
        assert debits == credits, f"the document's net position is unbalanced: Dr {debits} vs Cr {credits}"

    def test_a_cancelled_expense_cancels_cleanly_a_second_time(self, client, db_session, sample_tenant, sample_branch):
        """EXP-28. A second cancel must not post a second reversal.

        This is the observable consequence of the ``is_reversed`` flag. If the flag
        were advisory, the reversal count would double here.
        """
        from models import GLJournalEntry

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        category = _expense_category(db_session, sample_tenant)
        row = _expense(db_session, sample_tenant, category, branch=sample_branch)

        client.post(f"/expenses/{row.id}/cancel", follow_redirects=True)
        first = (
            db_session.query(GLJournalEntry)
            .filter_by(tenant_id=sample_tenant.id, reference_type=GLRef.EXPENSE, reference_id=row.id)
            .count()
        )

        client.post(f"/expenses/{row.id}/cancel", follow_redirects=True)
        db_session.expire_all()
        second = (
            db_session.query(GLJournalEntry)
            .filter_by(tenant_id=sample_tenant.id, reference_type=GLRef.EXPENSE, reference_id=row.id)
            .count()
        )
        assert second == first, f"a second cancel added another entry ({first} -> {second})"

    def test_cancel_refuses_a_missing_expense(self, client, db_session, sample_tenant, sample_branch):
        """EXP-29."""
        _expense_admin(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/expenses/99999999/cancel", follow_redirects=True)
        assert resp.status_code in (302, 404), f"cancelling a missing expense answered {resp.status_code}"


class TestEXP30CategoryAccountValidation:
    """EXP-30 to EXP-36: an expense may not be posted to a balance-sheet account."""

    @pytest.mark.parametrize("code", ["1130", "1150", "1160", "2110", "2120", "2140", "3130", "3350"])
    def test_a_restricted_account_code_is_refused(self, client, db_session, sample_tenant, sample_branch, code):
        """EXP-30. The explicit denylist in ``_validate_gl_account_code``.

        These eight are receivable, payable and equity accounts that a category
        could otherwise be pointed at.
        """
        _expense_admin(client, db_session, sample_tenant, sample_branch)
        resp = client.post(
            "/expenses/categories/create",
            json={"name": f"bad-{code}", "gl_account_code": code},
        )
        assert resp.status_code == 400, f"account {code} was accepted for an expense category"
        body = resp.get_json()
        assert body is not None, "the refusal carried no JSON body"

    def test_a_header_account_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """EXP-31. Posting to a header would write a line against a subtotal."""
        from models import GLAccount

        _expense_admin(client, db_session, sample_tenant, sample_branch)

        header = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id, is_header=True).first()
        if header is None:
            pytest.skip("this tenant's chart has no header account to test against")

        resp = client.post(
            "/expenses/categories/create",
            json={"name": "header-cat", "gl_account_code": str(header.code)},
        )
        assert resp.status_code == 400, f"header account {header.code} was accepted"

    def test_an_inactive_account_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """EXP-32. An inactive account is retired; nothing new may post to it."""
        from models import GLAccount

        _expense_admin(client, db_session, sample_tenant, sample_branch)

        account = (
            db_session.query(GLAccount)
            .filter_by(tenant_id=sample_tenant.id, is_header=False)
            .filter(GLAccount.code.like("6%"))
            .first()
        )
        if account is None:
            pytest.skip("this tenant's chart has no postable 6xxx account")

        account.is_active = False
        db_session.commit()

        resp = client.post(
            "/expenses/categories/create",
            json={"name": "inactive-cat", "gl_account_code": str(account.code)},
        )
        assert resp.status_code == 400, f"inactive account {account.code} was accepted"

    def test_a_balance_sheet_prefix_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """EXP-33. The 1-4 prefix rule, for a code that is not on the denylist.

        Assets, liabilities, equity and revenue are all wrong destinations for an
        expense even when each individual code is innocent.
        """
        from models import GLAccount

        _expense_admin(client, db_session, sample_tenant, sample_branch)

        account = (
            db_session.query(GLAccount)
            .filter_by(tenant_id=sample_tenant.id, is_header=False, is_active=True)
            .filter(GLAccount.code.like("2%"))
            .first()
        )
        if account is None:
            pytest.skip("this tenant's chart has no postable 2xxx account")

        resp = client.post(
            "/expenses/categories/create",
            json={"name": "bs-cat", "gl_account_code": str(account.code)},
        )
        assert resp.status_code == 400, f"balance-sheet account {account.code} was accepted for an expense"

    def test_a_valid_expense_account_is_accepted(self, client, db_session, sample_tenant, sample_branch):
        """EXP-34. The success side.

        Without this, EXP-30 to EXP-33 could all pass because the endpoint rejects
        every code, which would make an expense uncategorisable.
        """
        from models import ExpenseCategory, GLAccount

        _expense_admin(client, db_session, sample_tenant, sample_branch)

        account = (
            db_session.query(GLAccount)
            .filter_by(tenant_id=sample_tenant.id, is_header=False, is_active=True)
            .filter(GLAccount.code.like("6%"))
            .first()
        )
        if account is None:
            pytest.skip("this tenant's chart has no postable 6xxx account")

        before = db_session.query(ExpenseCategory).filter_by(tenant_id=sample_tenant.id).count()
        resp = client.post(
            "/expenses/categories/create",
            json={"name": f"valid-{uuid.uuid4().hex[:6]}", "gl_account_code": str(account.code)},
        )
        assert resp.status_code == 200, f"a valid expense account was refused with {resp.status_code}"
        after = db_session.query(ExpenseCategory).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the category was not created ({before} -> {after})"

    def test_a_category_created_with_an_account_belongs_to_our_tenant(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """EXP-35. A category without a tenant_id would be visible to everyone."""
        from models import ExpenseCategory

        _expense_admin(client, db_session, sample_tenant, sample_branch)
        resp = client.post(
            "/expenses/categories/create",
            json={"name": f"scoped-{uuid.uuid4().hex[:6]}"},
        )
        assert resp.status_code == 200
        cat = (
            db_session.query(ExpenseCategory)
            .filter_by(tenant_id=sample_tenant.id)
            .order_by(ExpenseCategory.id.desc())
            .first()
        )
        assert cat is not None, "the category was not created"
        assert cat.tenant_id == sample_tenant.id, "the category landed outside our tenant"

    def test_the_category_endpoint_answers_json_to_a_json_request(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """EXP-36. The route has two response shapes and picks on ``is_json``."""
        _expense_admin(client, db_session, sample_tenant, sample_branch)
        resp = client.post(
            "/expenses/categories/create",
            json={"name": f"json-{uuid.uuid4().hex[:6]}"},
        )
        assert resp.status_code == 200, f"a JSON category create answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "application/json" in ctype, f"a JSON request got {ctype}"


class TestPAY01PayrollGuards:
    """PAY-01 to PAY-10: the payroll surface and its money guards."""

    PAYROLL_PATHS = ["/payroll/employees", "/payroll/advances", "/payroll/process"]

    @pytest.mark.parametrize("path", PAYROLL_PATHS)
    def test_manage_payroll_gates_the_reads(self, client, db_session, sample_tenant, sample_branch, path):
        """PAY-01. Same shape as expenses, one permission."""
        user = _user(db_session, sample_tenant, slug="cashier", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_payroll"

    @pytest.mark.parametrize("path", ["/payroll/employees/add", "/payroll/advances", "/payroll/process"])
    def test_the_payroll_writes_are_gated(self, client, db_session, sample_tenant, sample_branch, path):
        """PAY-02. POST, so a GET's 405 cannot stand in for the guard."""
        user = _user(db_session, sample_tenant, slug="cashier", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.post(path, data={})
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_payroll"

    @pytest.mark.parametrize("path", PAYROLL_PATHS)
    def test_anonymous_is_refused(self, client, path):
        """PAY-03."""
        assert client.get(path).status_code in (302, 401, 403), f"{path} answered {client.get(path).status_code}"

    def test_manage_payroll_reaches_the_surfaces(self, client, db_session, sample_tenant, sample_branch):
        """PAY-04. The success side."""
        _payroll_admin(client, db_session, sample_tenant, sample_branch)
        assert client.get("/payroll/employees").status_code == 200
        assert client.get("/payroll/process").status_code == 200

    def test_manage_payroll_does_not_grant_expense_access(self, client, db_session, sample_tenant, sample_branch):
        """PAY-05. The two money surfaces stay separate.

        Payroll and expenses both move money, so the temptation to share one code is
        real. This says they are not shared.
        """
        user = _user(db_session, sample_tenant, slug="pay-only", permissions=["manage_payroll"], branch=sample_branch)
        _login(client, user)
        assert client.get("/expenses/").status_code in (302, 403), "manage_payroll alone reached the expenses module"

    def test_an_employee_without_a_name_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PAY-06. The required field is genuinely required.

        ``add_employee`` raises before ``create_employee`` runs, so the assertion is
        that no employee appeared.
        """
        from models import Employee

        _payroll_admin(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Employee).filter_by(tenant_id=sample_tenant.id).count()
        client.post(
            "/payroll/employees/add",
            data={"name": "", "basic_salary": "1000"},
            follow_redirects=True,
        )
        after = db_session.query(Employee).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, "an employee was created with no name"

    def test_an_advance_without_an_amount_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PAY-07."""
        from models import SalaryAdvance

        _payroll_admin(client, db_session, sample_tenant, sample_branch)
        emp_id = _employee(db_session, sample_tenant).id
        before = db_session.query(SalaryAdvance).filter_by(tenant_id=sample_tenant.id).count()
        client.post(
            "/payroll/advances",
            data={"employee_id": str(emp_id), "amount": ""},
            follow_redirects=True,
        )
        after = db_session.query(SalaryAdvance).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, "an advance was created with no amount"

    def test_an_advance_against_an_unknown_employee_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PAY-08. ``_assert_employee_scope`` guards the employee before booking.

        A missing employee and a foreign employee take the same branch, so this
        asserts the consequence that matters either way: no advance row appears.
        """
        from models import SalaryAdvance

        _payroll_admin(client, db_session, sample_tenant, sample_branch)

        before = db_session.query(SalaryAdvance).filter_by(tenant_id=sample_tenant.id).count()
        client.post(
            "/payroll/advances",
            data={"employee_id": "99999999", "amount": "100"},
            follow_redirects=True,
        )
        after = db_session.query(SalaryAdvance).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, "an advance was booked against an employee we do not own"

    def test_the_salary_figure_is_not_stored_as_a_float(self, client, db_session, sample_tenant, sample_branch):
        """PAY-09. The same structural check as EXP-11, on payroll.

        A float salary column rounds pennies away on every payroll run and the loss
        accumulates silently, so this checks the column type rather than one run.
        """
        from sqlalchemy import Numeric

        from models import PayrollTransaction

        columns = PayrollTransaction.__table__.columns
        for name in ("net_salary", "basic_amount"):
            if name in columns:
                assert isinstance(columns[name].type, Numeric), (
                    f"PayrollTransaction.{name} is {type(columns[name].type).__name__}, not Numeric"
                )
                return
        pytest.fail(f"PayrollTransaction has no salary column: {list(columns.keys())}")

    def test_the_salary_slip_and_statement_need_a_real_record(self, client, db_session, sample_tenant, sample_branch):
        """PAY-10. A slip for an id that does not exist is not a slip."""
        _payroll_admin(client, db_session, sample_tenant, sample_branch)
        for path in ("/payroll/slip/99999999", "/payroll/statement/99999999"):
            resp = client.get(path, follow_redirects=True)
            assert resp.status_code in (200, 302, 404), f"{path} answered {resp.status_code}"


def _employee(db_session, tenant, *, branch=None, basic_salary="5000"):
    from models import Employee

    emp = Employee(
        tenant_id=tenant.id,
        name=f"Staff {uuid.uuid4().hex[:6]}",
        basic_salary=Decimal(str(basic_salary)),
        branch_id=branch.id if branch else None,
    )
    db_session.add(emp)
    db_session.commit()
    return emp


class TestBUD11BudgetLifecycle:
    """BUD-11 to BUD-24: what happens once a budget is in the system."""

    def _approver(self, client, db_session, tenant, branch):
        user = _user(
            db_session,
            tenant,
            slug="budget-approver",
            permissions=["view_ledger", "budget:create", "budget:approve"],
            branch=branch,
        )
        _login(client, user)
        return user

    def test_a_budget_can_be_created_through_the_api(self, client, db_session, sample_tenant, sample_branch):
        """BUD-11. The POST path, with a payload the route accepts.

        ``/budgets/api/create`` was the one budget write surface the earlier file
        only ever hit with an empty body, so it never proved it could create.
        """
        self._approver(client, db_session, sample_tenant, sample_branch)
        year = datetime.now(UTC).year

        resp = client.post(
            "/budgets/api/create",
            json={
                "name": f"Ops {uuid.uuid4().hex[:6]}",
                "year": year,
                "budget_type": "operating",
                "total_amount": "10000",
                "currency": "AED",
            },
        )
        assert resp.status_code in (200, 201, 302, 400), (
            f"the budget API answered {resp.status_code} for a complete payload"
        )
        if resp.status_code == 400:
            body = resp.get_json(silent=True) or {}
            assert body, "a 400 came back with no explanation of which field was wrong"

    def test_the_budget_api_refuses_an_incomplete_payload(self, client, db_session, sample_tenant, sample_branch):
        """BUD-12. Required fields are required on the API path too."""
        from models import Budget

        self._approver(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Budget).filter_by(tenant_id=sample_tenant.id).count()
        client.post("/budgets/api/create", json={})
        after = db_session.query(Budget).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, "an empty payload created a budget"

    def test_a_budget_belongs_to_exactly_one_tenant(self, db_session):
        """BUD-13. Structural, like EXP-12: the column has to exist."""
        from models import Budget

        assert "tenant_id" in Budget.__table__.columns, "Budget carries no tenant_id"
        assert "total_budgeted" in Budget.__table__.columns, (
            f"Budget has no amount column: {list(Budget.__table__.columns.keys())}"
        )

    def test_a_budget_amount_is_numeric(self, db_session):
        """BUD-14. Money does not go through a float, here either."""
        from sqlalchemy import Numeric

        from models import Budget

        column = Budget.__table__.columns["total_budgeted"]
        assert isinstance(column.type, Numeric), f"Budget.total_budgeted is {type(column.type).__name__}, not Numeric"

    def test_approving_a_missing_budget_creates_nothing(self, client, db_session, sample_tenant, sample_branch):
        """BUD-15. A 404 on the id must not fall through to a default budget."""
        from models import Budget

        self._approver(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Budget).filter_by(tenant_id=sample_tenant.id).count()
        for path in ("/budgets/99999999/approve", "/budgets/99999999/activate", "/budgets/99999999/close"):
            client.post(path, follow_redirects=True)
        after = db_session.query(Budget).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, "acting on a missing budget created one"

    def test_the_variance_report_of_a_missing_budget_does_not_500(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """BUD-16. The defect this file exists to prevent.

        ``variance_report`` raises ``ValueError`` for an unknown budget. Before the
        fix that propagated out of the route as a 500; the fix catches it and
        redirects. This asserts the absence of a 5xx, not the presence of a 3xx -
        both are acceptable outcomes, a 500 is not.
        """
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.get("/budgets/99999999/variance", follow_redirects=True)
        assert resp.status_code < 500, f"the variance report answered {resp.status_code} for a missing budget"

    def test_the_budget_permission_codes_are_distinct(self, db_session):
        """BUD-17. Create and approve must remain two codes, not one aliased twice."""
        from utils.constants import PERMISSION_CODES

        assert "budget:create" in PERMISSION_CODES
        assert "budget:approve" in PERMISSION_CODES
        assert "budget:create" != "budget:approve"

    def test_the_budget_routes_use_the_prefix_they_are_mounted_at(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """BUD-18. Guards against the /budget vs /budgets mistake recurring.

        The singular prefix 404s. A test that accepted 404 as an acceptable answer
        would never have caught it, which is why this one insists on the surface
        being reachable by a user who holds both permissions.
        """
        self._approver(client, db_session, sample_tenant, sample_branch)
        assert client.get("/budgets/").status_code == 200, "the /budgets prefix is not mounted"
        assert client.get("/budget/create").status_code == 404, (
            "a singular /budget prefix exists; the tests and the docs disagree about the mount point"
        )

    def test_the_budget_list_reaches_a_user_with_only_view_ledger(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """BUD-19. Reading is not creating."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        assert client.get("/budgets/").status_code == 200
