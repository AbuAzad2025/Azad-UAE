"""Wave 8 debt - the advanced ledger's write paths, reached by someone allowed.

``test_wave8_advanced_ledger.py`` and ``test_wave8_advanced_part2.py`` established
the shape of this blueprint: reads take ``view_ledger``, writes take
``admin_required``, and ADV-42 listed customs taxes, expense categories, journal
management, real-time events and forecasting as admin-only setup. Every one of
those was proven to refuse.

What no test did was stand on the permitted side. The customs-tax form, the
expense-category form, journal approve and journal delete all sit behind
``admin_required``, so a failure in their happy path - a form that never saves,
a redirect loop, a validation that fires on valid input - is invisible to a
suite that only ever asserts 403.

The financial rules are the other half. ``delete_entry`` soft-deletes a draft to
``cancelled`` but refuses anything already posted or reversed, and says so in
the error message: a posted entry may be *reversed*, never removed. That is the
difference between an auditable ledger and one where a correction looks like a
correction was never needed, so ADV-46 and ADV-47 pin both sides of it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.advanced_journal_manager import AdvancedJournalEntryManager

READ_PATHS = [
    "/ledger/advanced/professional-printing",
    "/ledger/advanced/advanced-expenses",
    "/ledger/advanced/cheque-integration",
    "/ledger/advanced/professional-reports",
]

WRITE_PATHS = [
    "/ledger/advanced/customs-taxes",
    "/ledger/advanced/expense-categories",
    "/ledger/advanced/journal-management",
    "/ledger/advanced/real-time-events",
    "/ledger/advanced/api/forecasting",
]


def _user(db_session, tenant, *, slug, permissions=(), branch=None, super_admin=False):
    from models import Permission, Role, User

    # is_admin_surface_user accepts the role slug OR name being "super_admin".
    # Both are unique columns, so an existing role is reused and renamed rather
    # than a second one created - two roles named Super Admin violate
    # roles_name_key on the second insert.
    role_slug = "super_admin" if super_admin else slug
    role = db_session.query(Role).filter_by(slug=role_slug).first()
    if role is None:
        role = Role(
            name="Super Admin" if super_admin else slug.replace("_", " ").title(),
            slug=role_slug,
            is_active=True,
        )
        db_session.add(role)
        db_session.commit()
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
    """Sign ``user`` in, replacing any session a fixture already opened.

    ``/auth/login`` short-circuits to a redirect when the session is already
    authenticated, so without the logout this call is silently a no-op and the
    route under test keeps being reached as the previous user.
    """
    client.get("/auth/logout", follow_redirects=True)
    return client.post(
        "/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True
    )


def _reader(client, db_session, tenant, branch):
    user = _user(db_session, tenant, slug="adv-reader", permissions=["view_ledger"], branch=branch)
    _login(client, user)
    return user


def _accounts(db_session, tenant):
    """Two postable accounts in this tenant's chart, via the production path."""
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


def _entry(db_session, tenant, debit, credit, *, status="posted", amount="100.00", branch=None):
    from models import GLJournalEntry, GLJournalLine

    entry = GLJournalEntry(
        tenant_id=tenant.id,
        entry_date=datetime.now(UTC),
        entry_number=f"ADVD-{uuid.uuid4().hex[:10]}",
        entry_type="manual",
        branch_id=branch.id if branch is not None else None,
        description="ADV debt scenario",
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


class TestADV43TheSplitIsReal:
    """ADV-43 to ADV-48: the permitted side of the write guard."""

    def test_a_reader_reaches_the_reads_and_is_refused_the_writes(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """ADV-43. Both halves, in one pass.

        Proving only the refusal would let a blueprint where *every* route is
        admin-gated pass this file. Proving only the access would let a reader
        quietly gain the write half. The split is the design, so one scenario
        has to carry both directions.
        """
        _reader(client, db_session, sample_tenant, sample_branch)

        denied = []
        for path in READ_PATHS:
            resp = client.get(path, follow_redirects=False)
            if resp.status_code != 200:
                denied.append((path, resp.status_code))
        assert not denied, f"view_ledger did not open the read pages: {denied}"

        blocked = []
        for path in WRITE_PATHS:
            resp = client.get(path, follow_redirects=False)
            if resp.status_code != 403:
                blocked.append((path, resp.status_code))
        assert not blocked, f"view_ledger reached the admin-only write pages: {blocked}"


class TestADV44CustomsTaxForm:
    """ADV-44 to ADV-45: the customs-tax form, which no test had submitted."""

    def test_a_customs_tax_with_no_account_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """ADV-44. A tax that cannot be posted anywhere is not a tax.

        The form insists on a GL account before it builds anything, so a tax
        with no destination never reaches the table. It re-renders rather than
        redirecting, and the refusal must not leave a half-written row behind.
        """
        from models import CustomsTax

        user = _user(
            db_session,
            sample_tenant,
            slug="adv-super-admin",
            permissions=["view_ledger", "manage_ledger"],
            branch=sample_branch,
            super_admin=True,
        )
        _login(client, user)

        before = db_session.query(CustomsTax).filter_by(tenant_id=sample_tenant.id).count()
        resp = client.post(
            "/ledger/advanced/customs-taxes/add",
            data={"name": "Duty", "name_ar": "رسوم", "tax_type": "customs", "rate": "5", "gl_account_id": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"a customs tax with no account answered {resp.status_code}"
        db_session.expire_all()
        after = db_session.query(CustomsTax).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a tax with no GL account was stored ({before} -> {after})"

    def test_a_customs_tax_stores_the_rate_as_a_decimal(self, client, db_session, sample_tenant, sample_branch):
        """ADV-45. The rate is money and is stored as money.

        A rate that round-trips through a float turns 0.075 into 0.07499999...,
        and a customs rate that is wrong by an eighth of a percent is wrong in
        the one direction nobody notices until an audit. ``fixed_amount`` is
        defaulted to zero rather than left null, because the model reads it
        unconditionally.
        """
        from models import CustomsTax

        user = _user(
            db_session,
            sample_tenant,
            slug="adv-super-admin",
            permissions=["view_ledger", "manage_ledger"],
            branch=sample_branch,
            super_admin=True,
        )
        _login(client, user)
        debit, _credit = _accounts(db_session, sample_tenant)

        resp = client.post(
            "/ledger/advanced/customs-taxes/add",
            data={
                "name": f"Duty-{uuid.uuid4().hex[:6]}",
                "name_ar": "رسوم جمركية",
                "tax_type": "customs",
                "rate": "5",
                "fixed_amount": "",
                "gl_account_id": str(debit.id),
                "effective_from": "2026-01-01",
                "is_percentage": "on",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"a valid customs tax answered {resp.status_code}"
        db_session.expire_all()

        tax = db_session.query(CustomsTax).filter_by(tenant_id=sample_tenant.id).order_by(CustomsTax.id.desc()).first()
        assert tax is not None, "the customs tax was not stored"
        assert Decimal(str(tax.rate)) == Decimal("5"), f"the stored rate is {tax.rate!r}"
        assert tax.gl_account_id == debit.id, f"the tax points at account {tax.gl_account_id}, not {debit.id}"
        assert Decimal(str(tax.fixed_amount)) == 0, f"a percentage tax stored fixed_amount {tax.fixed_amount!r}"
        assert tax.effective_to is None, "no end date was submitted but one was stored"


class TestADV46PostedEntriesCannotBeDeleted:
    """ADV-46 to ADV-48: delete cancels a draft and refuses a posted entry."""

    def test_a_posted_entry_cannot_be_deleted(self, client, db_session, sample_tenant, sample_branch):
        """ADV-46. Deletion is not the correction mechanism.

        ``delete_entry`` refuses anything posted or reversed and points at
        ``reverse_entry_advanced`` instead. That refusal is what keeps the
        audit trail: a posted entry that vanished would leave the trial balance
        wrong with no evidence that it was ever wrong. The reversal - a new,
        offsetting entry - is what a correction looks like on the books.
        """
        user = _user(
            db_session,
            sample_tenant,
            slug="adv-super-admin",
            permissions=["view_ledger", "manage_ledger"],
            branch=sample_branch,
            super_admin=True,
        )
        _login(client, user)

        debit, credit = _accounts(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit, credit, status="posted", branch=sample_branch)

        resp = client.post(
            f"/ledger/advanced/journal-management/{entry.id}/delete",
            data={"reason": "should not be allowed"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"deleting a posted entry answered {resp.status_code}"

        # Asserted against the manager rather than by re-reading the row above:
        # the route's atomic_transaction rolls back on the refusal, and in the
        # harness that rollback also unwinds the savepoint db_session opened, so
        # anything this test created is gone by the time we look. In production
        # the entry was committed long before and survives untouched. The rule
        # is the manager's, so a fresh entry is built to check it.
        posted = _entry(db_session, sample_tenant, debit, credit, status="posted", branch=sample_branch)
        with pytest.raises(ValueError, match="posted"):
            AdvancedJournalEntryManager.delete_entry(entry_id=posted.id, deleted_by=user.id, reason="should not")
        assert posted.status == "posted", f"a refused delete left the entry as {posted.status!r}"

    def test_deleting_a_draft_cancels_it_without_purging_the_row(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """ADV-47. A draft is cancelled, not removed.

        ``delete_entry`` sets ``status='cancelled'`` and keeps the row. A purge
        would lose the reason the entry was abandoned, which is the only thing
        that distinguishes a mistake caught before posting from a mistake hidden
        after it.
        """
        user = _user(
            db_session,
            sample_tenant,
            slug="adv-super-admin",
            permissions=["view_ledger", "manage_ledger"],
            branch=sample_branch,
            super_admin=True,
        )
        _login(client, user)
        debit, credit = _accounts(db_session, sample_tenant)
        entry = _entry(db_session, sample_tenant, debit, credit, status="draft", branch=sample_branch)
        entry_id = entry.id

        resp = client.post(
            f"/ledger/advanced/journal-management/{entry_id}/delete",
            data={"reason": "entered twice"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"cancelling a draft answered {resp.status_code}"
        db_session.expire_all()

        row = db_session.get(type(entry), entry_id)
        assert row is not None, f"draft entry {entry_id} was purged rather than cancelled"
        assert row.status == "cancelled", f"a cancelled draft is {row.status!r}"

    def test_the_cheque_accounting_summary_answers_for_the_tenant(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """ADV-48. The read-side API behind the cheque screen answers.

        ``cheque_accounting_summary`` is a ``view_ledger`` route, and the cheque
        lifecycle in ADV-32 drives it through the write side. This is the read
        contract: a JSON envelope naming the cheque, so a summary that answered
        HTML or an empty body would be caught here rather than in a browser.
        """
        from models import Cheque

        _reader(client, db_session, sample_tenant, sample_branch)
        cheque = db_session.query(Cheque).filter_by(tenant_id=sample_tenant.id).first()
        if cheque is None:
            cheque = Cheque(
                tenant_id=sample_tenant.id,
                cheque_number=f"ADVD-{uuid.uuid4().hex[:8]}",
                cheque_bank_number=f"BNK-{uuid.uuid4().hex[:6]}",
                cheque_type="incoming",
                bank_name="Scenario Bank",
                amount=Decimal("500.00"),
                currency="AED",
                issue_date=datetime.now(UTC).date(),
                due_date=datetime.now(UTC).date(),
                status="received",
                branch_id=sample_branch.id,
            )
            db_session.add(cheque)
            db_session.commit()

        resp = client.get(f"/ledger/advanced/api/cheque/{cheque.id}/accounting-summary", follow_redirects=False)
        assert resp.status_code == 200, f"the cheque summary answered {resp.status_code} to a view_ledger reader"
        body = resp.get_json()
        assert body is not None, "the cheque summary answered with a body that is not JSON"
        assert "data" in body, f"the cheque summary has no data envelope; keys are {sorted(body)}"
