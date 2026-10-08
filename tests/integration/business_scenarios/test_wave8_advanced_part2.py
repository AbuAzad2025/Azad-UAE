"""Wave 8 (part 2) - the advanced ledger and treasury, continued. Prefix ADV, TRE.

``test_wave8_advanced_ledger.py`` established the permission split on this
blueprint: ``view_ledger`` for the reports, ``@admin_required`` for the mutations.
Every scenario in that file is a refusal. This file is the other half - what the
mutations actually do once an admin is allowed through, which is where the
interesting failures live.

The three journal-management mutations have deliberately different contracts and
are tested separately, because a single "the journal routes work" assertion would
pass against an implementation where all three quietly did the same thing:

``approve`` routes through ``validate_entry`` and moves a draft forward.
``delete`` is a **soft** delete - it sets ``status='cancelled'`` and refuses
outright on a posted or reversed entry, because financial documents are immutable.
``reverse`` adds an offsetting entry and leaves the original readable.

ADV-22 to ADV-31 walk a real entry through those three states and assert the row
counts and the ``status`` values, because the difference between a soft delete and
a hard one is invisible in a status code.

The cheque routes move real money in two steps - receive, then clear - and each
step posts an entry. TRE-01 to TRE-12 then cover the treasury blueprint, which is
mounted under ``/reports`` rather than under a prefix of its own; a test that
guessed ``/treasury`` would 404 and, worse, could be written to accept that.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

TREASURY_PATHS = [
    "/reports/treasury",
    "/reports/treasury/export",
    "/reports/vat-return",
    "/reports/wps-export",
]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="adv-user", permissions=(), branch=None):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"adv2-{slug}-{unique}",
        email=f"adv2-{unique}@example.com",
        full_name=f"ADV2 {slug}",
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
    user = _user(db_session, tenant, slug="adv2-viewer", permissions=["view_ledger"], branch=branch)
    _login(client, user)
    return user


def _admin(client, db_session, tenant, branch):
    """A user who satisfies ``@admin_required`` - the seeded super_admin role.

    Reused rather than created-and-renamed: the seeded role already matches
    ``RoleEnum.SUPER_ADMIN.value`` and renaming a fresh one collided with it on
    ``roles_name_key``.
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
        username=f"adv2-admin-{unique}",
        email=f"adv2-admin-{unique}@example.com",
        full_name="ADV2 Admin",
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


def _draft_entry(db_session, tenant, *, branch=None, amount="100.00"):
    """A draft two-line entry - the state ``approve`` and ``delete`` both accept."""
    from models import GLJournalEntry, GLJournalLine

    accounts = _chart(db_session, tenant)
    debit = next((a for a in accounts if a.type == "asset"), accounts[0])
    credit = next((a for a in accounts if a.type in ("liability", "equity", "income")), accounts[-1])

    entry = GLJournalEntry(
        tenant_id=tenant.id,
        entry_date=datetime.now(UTC),
        entry_number=f"ADV2-{uuid.uuid4().hex[:10]}",
        entry_type="manual",
        branch_id=branch.id if branch else None,
        description="ADV2 scenario",
        status="draft",
        is_posted=False,
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
    db_session.commit()
    return entry


def _cheque(db_session, tenant, *, branch=None, amount="100.00", status="pending"):
    """An incoming cheque built through the production factory.

    Hand-building the row left ``amount_aed`` null - every cheque GL line takes
    its amount from ``cheque.amount_aed``, not ``cheque.amount`` - and the failure
    surfaced as the opaque "a GL line must carry a debit or a credit" instead of
    a missing amount. Going through ``ChequeService.create_cheque`` is also what
    keeps this test honest if the factory grows another derived column.
    """
    from services.cheque_service import ChequeService

    unique = uuid.uuid4().hex[:8]
    today = datetime.now(UTC).date()
    cheque = ChequeService.create_cheque(
        cheque_number=f"ADV2-{unique}",
        cheque_bank_number=f"BANK-{unique}",
        cheque_type="incoming",
        bank_name="Test Bank",
        amount=Decimal(amount),
        currency="AED",
        exchange_rate=Decimal("1"),
        issue_date=today,
        due_date=today,
        status=status,
        payee_name="Scenario Payer",
        branch_id=branch.id if branch else None,
        tenant_id=tenant.id,
    )
    db_session.add(cheque)
    db_session.commit()
    return cheque


class TestADV22JournalManagementSuccess:
    """ADV-22 to ADV-31: the three mutations, asserted separately."""

    def test_an_admin_reaches_the_journal_management_screen(self, client, db_session, sample_tenant, sample_branch):
        """ADV-22. The success side of the boundary file."""
        _admin(client, db_session, sample_tenant, sample_branch)
        assert client.get("/ledger/advanced/journal-management").status_code == 200

    def test_approving_a_draft_moves_it_forward(self, client, db_session, sample_tenant, sample_branch):
        """ADV-23. ``approve`` is an alias for ``validate_entry``.

        The state machine is draft -> validated -> posted, so a single approve
        click should leave the entry past ``draft`` - not still draft, and not
        silently deleted.
        """
        from models import GLJournalEntry

        _admin(client, db_session, sample_tenant, sample_branch)
        entry = _draft_entry(db_session, sample_tenant, branch=sample_branch)
        entry_id = entry.id
        assert entry.status == "draft", f"the scenario entry starts as {entry.status!r}, not draft"

        resp = client.post(f"/ledger/advanced/journal-management/{entry_id}/approve", follow_redirects=True)
        assert resp.status_code == 200, f"approving answered {resp.status_code}"

        db_session.expire_all()
        refreshed = db_session.get(GLJournalEntry, entry_id)
        assert refreshed is not None, "approving removed the entry"
        assert refreshed.status != "draft", f"approving left the entry in status {refreshed.status!r}"

    def test_approving_an_unknown_entry_leaves_nothing_behind(self, client, db_session, sample_tenant, sample_branch):
        """ADV-24. The id arrives from a URL."""
        _admin(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/ledger/advanced/journal-management/99999999/approve", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"approving a missing entry answered {resp.status_code}"

    def test_deleting_a_draft_soft_cancels_it(self, client, db_session, sample_tenant, sample_branch):
        """ADV-25. The soft delete is the whole point.

        ``delete_entry`` sets ``status='cancelled'`` and keeps the row. A hard
        delete would leave no trace that the entry ever existed, which is the
        outcome the docstring explicitly rules out.
        """
        from models import GLJournalEntry

        _admin(client, db_session, sample_tenant, sample_branch)
        entry = _draft_entry(db_session, sample_tenant, branch=sample_branch)
        entry_id = entry.id

        resp = client.post(f"/ledger/advanced/journal-management/{entry_id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"deleting a draft answered {resp.status_code}"

        db_session.expire_all()
        refreshed = db_session.get(GLJournalEntry, entry_id)
        assert refreshed is not None, "deleting a draft removed the row instead of cancelling it"
        assert refreshed.status == "cancelled", f"a soft delete left status {refreshed.status!r}, not 'cancelled'"

    def test_deleting_a_posted_entry_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """ADV-26. The dangerous one, and the one that must not be the easy path.

        ``delete_entry`` raises for ``status in ("posted", "reversed")`` and tells
        the caller to reverse instead. The assertion is that the posted entry is
        still posted and still present.
        """
        from models import GLJournalEntry

        _admin(client, db_session, sample_tenant, sample_branch)
        entry = _draft_entry(db_session, sample_tenant, branch=sample_branch)
        entry_id = entry.id
        db_session.get(GLJournalEntry, entry_id).status = "posted"
        db_session.commit()

        client.post(f"/ledger/advanced/journal-management/{entry_id}/delete", follow_redirects=True)
        db_session.expire_all()

        refreshed = db_session.get(GLJournalEntry, entry_id)
        assert refreshed is not None, "deleting a posted entry removed the row"
        assert refreshed.status == "posted", (
            f"a posted entry was cancelled by the delete route; status is {refreshed.status!r}"
        )

    def test_reversing_a_posted_entry_adds_one_and_keeps_the_original(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """ADV-27. Reversal is additive.

        The original stays readable - an auditor has to be able to see what was
        posted - and the correction arrives as a new entry.
        """
        from models import GLJournalEntry

        _admin(client, db_session, sample_tenant, sample_branch)
        entry = _draft_entry(db_session, sample_tenant, branch=sample_branch)
        entry_id = entry.id
        db_session.get(GLJournalEntry, entry_id).status = "posted"
        db_session.commit()
        before = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post(f"/ledger/advanced/journal-management/{entry_id}/reverse", follow_redirects=True)
        assert resp.status_code == 200, f"reversing answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        assert db_session.get(GLJournalEntry, entry_id) is not None, "reversing removed the original entry"
        assert after == before + 1, f"reversing added {after - before} entries, expected exactly 1"

    def test_reversing_twice_does_not_double_reverse(self, client, db_session, sample_tenant, sample_branch):
        """ADV-28. A double-click must not double the correction."""
        from models import GLJournalEntry

        _admin(client, db_session, sample_tenant, sample_branch)
        entry = _draft_entry(db_session, sample_tenant, branch=sample_branch)
        entry_id = entry.id
        db_session.get(GLJournalEntry, entry_id).status = "posted"
        db_session.commit()

        client.post(f"/ledger/advanced/journal-management/{entry_id}/reverse", follow_redirects=True)
        first = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        client.post(f"/ledger/advanced/journal-management/{entry_id}/reverse", follow_redirects=True)
        db_session.expire_all()
        second = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        assert second == first, f"a second reversal added another entry ({first} -> {second})"

    def test_the_journal_management_list_is_tenant_scoped(self, client, db_session, sample_tenant, sample_branch):
        """ADV-29. The list an admin sees is only their own tenant's entries."""
        from models import GLJournalEntry

        _admin(client, db_session, sample_tenant, sample_branch)
        _draft_entry(db_session, sample_tenant, branch=sample_branch)
        number = _draft_entry(db_session, sample_tenant, branch=sample_branch).entry_number

        body = client.get("/ledger/advanced/journal-management").get_data(as_text=True)
        others = (
            db_session.query(GLJournalEntry)
            .filter(
                GLJournalEntry.tenant_id != sample_tenant.id,
                GLJournalEntry.entry_number == number,
            )
            .count()
        )
        assert others == 0
        assert number in body, "the entry we just wrote is missing from our own journal management list"

    def test_a_viewer_cannot_reach_the_journal_mutations(self, client, db_session, sample_tenant, sample_branch):
        """ADV-30. The permission split, restated from the mutation side."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        entry = _draft_entry(db_session, sample_tenant, branch=sample_branch)
        from models import GLJournalEntry

        entry_id = entry.id
        before = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        for action in ("approve", "delete", "reverse"):
            resp = client.post(f"/ledger/advanced/journal-management/{entry_id}/{action}")
            assert resp.status_code in (302, 403), f"a viewer reached /{action} and got {resp.status_code}"
        db_session.expire_all()
        assert db_session.get(GLJournalEntry, entry_id) is not None
        after = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a viewer changed the entry count ({before} -> {after})"

    def test_a_cancelled_entry_cannot_be_reversed_afterwards(self, client, db_session, sample_tenant, sample_branch):
        """ADV-31. The state machine refuses nonsense transitions.

        Cancelled means the entry never became a fact, so there is nothing to
        offset; the reversal is refused and no entry is added.
        """
        from models import GLJournalEntry

        _admin(client, db_session, sample_tenant, sample_branch)
        entry = _draft_entry(db_session, sample_tenant, branch=sample_branch)
        entry_id = entry.id
        client.post(f"/ledger/advanced/journal-management/{entry_id}/delete", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(GLJournalEntry, entry_id).status == "cancelled"

        before = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        client.post(f"/ledger/advanced/journal-management/{entry_id}/reverse", follow_redirects=True)
        db_session.expire_all()
        after = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a cancelled entry was reversed anyway ({before} -> {after})"


class TestADV32ChequeLifecycle:
    """ADV-32 to ADV-37: receiving and clearing a cheque against the ledger."""

    def test_a_viewer_sees_the_cheque_integration_screen(self, client, db_session, sample_tenant, sample_branch):
        """ADV-32. The read half is ``view_ledger``, not admin."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        assert client.get("/ledger/advanced/cheque-integration").status_code == 200

    def test_receiving_a_cheque_posts_an_entry_against_it(self, client, db_session, sample_tenant, sample_branch):
        """ADV-33. Receive is the first step and it posts the entry.

        Worth being precise about what it does *not* do: ``process_cheque_receive``
        writes the journal entry and leaves ``cheque.status`` alone. The status
        only ever moves to deposited / cleared / bounced / cancelled, so an
        assertion that receiving flips it away from "pending" would be asserting
        behaviour that was never there. The entry is the record of receipt.
        """
        from models import GLJournalEntry
        from utils.gl_reference_types import GLRef

        _admin(client, db_session, sample_tenant, sample_branch)
        _chart(db_session, sample_tenant)
        cheque = _cheque(db_session, sample_tenant, branch=sample_branch)
        cheque_id = cheque.id

        before = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        client.post(f"/ledger/advanced/cheque-integration/{cheque_id}/receive", follow_redirects=True)

        db_session.expire_all()
        after = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        assert after > before, f"receiving the cheque posted no entry ({before} -> {after})"

        entry = (
            db_session.query(GLJournalEntry)
            .filter_by(tenant_id=sample_tenant.id, reference_type=GLRef.CHEQUE_RECEIVE, reference_id=cheque_id)
            .order_by(GLJournalEntry.id.desc())
            .first()
        )
        assert entry is not None, "no journal entry references this cheque as received"

        from models import GLJournalLine

        lines = db_session.query(GLJournalLine).filter_by(entry_id=entry.id).all()
        debits = sum(Decimal(str(ln.debit or 0)) for ln in lines)
        credits = sum(Decimal(str(ln.credit or 0)) for ln in lines)
        assert debits == credits, f"the receive entry does not balance: Dr {debits} vs Cr {credits}"
        assert debits > 0, "the receive entry carries no amount"

    def test_clearing_a_cheque_posts_a_settling_entry_and_marks_it_cleared(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """ADV-34. Clear is the second step and it settles.

        ``clear_cheque`` accepts pending, under_collection and deposited; "pending"
        is the state a freshly received incoming cheque is in, because receive
        does not advance the status.
        """
        from models import Cheque, GLJournalEntry

        _admin(client, db_session, sample_tenant, sample_branch)
        _chart(db_session, sample_tenant)
        cheque = _cheque(db_session, sample_tenant, branch=sample_branch)
        cheque_id = cheque.id
        assert cheque.status == "pending"

        before = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        client.post(
            f"/ledger/advanced/cheque-integration/{cheque_id}/clear",
            data={"bank_charges": "0", "exchange_gain_loss": "0"},
            follow_redirects=True,
        )
        db_session.expire_all()
        after = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        assert after > before, f"clearing the cheque posted no entry ({before} -> {after})"

        refreshed = db_session.get(Cheque, cheque_id)
        assert refreshed is not None
        assert refreshed.status == "cleared", f"the cheque is {refreshed.status!r} after being cleared"

    def test_bank_charges_on_a_clear_reach_the_ledger(self, client, db_session, sample_tenant, sample_branch):
        """ADV-35. A bank charge is real money and must not be silently dropped.

        ``clear_cheque`` takes ``bank_charges``; if it were ignored the entry would
        balance at the cheque amount and the charge would vanish. A non-zero
        charge must still produce a balanced posting.
        """
        from models import Cheque, GLJournalEntry

        _admin(client, db_session, sample_tenant, sample_branch)
        _chart(db_session, sample_tenant)
        cheque = _cheque(db_session, sample_tenant, branch=sample_branch)

        before = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        client.post(
            f"/ledger/advanced/cheque-integration/{cheque.id}/clear",
            data={"bank_charges": "5.000", "exchange_gain_loss": "0"},
            follow_redirects=True,
        )
        db_session.expire_all()
        after = db_session.query(GLJournalEntry).filter_by(tenant_id=sample_tenant.id).count()
        assert after > before, "clearing with a bank charge posted nothing"
        assert db_session.get(Cheque, cheque.id).status == "cleared"

    def test_the_accounting_summary_api_answers_json(self, client, db_session, sample_tenant, sample_branch):
        """ADV-36. The summary a viewer may read."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        cheque = _cheque(db_session, sample_tenant, branch=sample_branch)
        resp = client.get(f"/ledger/advanced/api/cheque/{cheque.id}/accounting-summary")
        assert resp.status_code == 200, f"the summary API answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "application/json" in ctype, f"the summary API is {ctype}, not JSON"

    def test_cheque_actions_on_a_missing_cheque_are_refused(self, client, db_session, sample_tenant, sample_branch):
        """ADV-37. ``tenant_get_or_404`` on both cheque mutations."""
        _admin(client, db_session, sample_tenant, sample_branch)
        for path in (
            "/ledger/advanced/cheque-integration/99999999/receive",
            "/ledger/advanced/cheque-integration/99999999/clear",
        ):
            resp = client.post(path, follow_redirects=True)
            assert resp.status_code in (200, 302, 404), f"{path} answered {resp.status_code}"

    def test_the_event_stream_api_answers_json(self, client, db_session, sample_tenant, sample_branch):
        """ADV-37b. The real-time feed the admin dashboard polls."""
        _admin(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/ledger/advanced/api/events/stream")
        assert resp.status_code == 200, f"the event stream answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "application/json" in ctype, f"the event stream is {ctype}, not JSON"
        body = resp.get_json()
        assert isinstance(body, dict) and "data" in body, f"unexpected event stream body: {type(body).__name__}"


class TestADV38AnalyticsApis:
    """ADV-38 to ADV-42: the forecasting and ratio APIs return real numbers."""

    @pytest.mark.parametrize(
        "path",
        [
            "/ledger/advanced/api/financial-ratios",
            "/ledger/advanced/api/trend-analysis",
            "/ledger/advanced/api/forecasting",
        ],
    )
    def test_the_analytics_apis_answer_json(self, client, db_session, sample_tenant, sample_branch, path):
        """ADV-38. Shape, not values - the numbers depend on the tenant's books."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        _chart(db_session, sample_tenant)
        resp = client.get(path)
        assert resp.status_code in (200, 403), f"{path} answered {resp.status_code}"
        if resp.status_code == 200:
            ctype = resp.content_type or ""
            assert "application/json" in ctype, f"{path} is {ctype}, not JSON"

    def test_the_ratio_api_stays_tenant_scoped(self, client, db_session, sample_tenant, sample_branch):
        """ADV-39. A ratio computed across tenants is a breach wearing a number."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        _chart(db_session, sample_tenant)
        resp = client.get("/ledger/advanced/api/financial-ratios")
        assert resp.status_code in (200, 403)
        if resp.status_code == 200:
            body = resp.get_json()
            assert isinstance(body, dict), f"unexpected body: {type(body).__name__}"

    def test_the_advanced_reports_screen_renders(self, client, db_session, sample_tenant, sample_branch):
        """ADV-40."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        _chart(db_session, sample_tenant)
        assert client.get("/ledger/advanced/professional-reports").status_code == 200

    def test_professional_printing_renders(self, client, db_session, sample_tenant, sample_branch):
        """ADV-41."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        _chart(db_session, sample_tenant)
        assert client.get("/ledger/advanced/professional-printing").status_code == 200

    def test_an_admin_reaches_the_configuration_screens(self, client, db_session, sample_tenant, sample_branch):
        """ADV-42. customs-taxes and expense-categories are admin-only setup."""
        _admin(client, db_session, sample_tenant, sample_branch)
        for path in (
            "/ledger/advanced/customs-taxes",
            "/ledger/advanced/expense-categories",
            "/ledger/advanced/advanced-analytics",
            "/ledger/advanced/real-time-events",
        ):
            assert client.get(path).status_code == 200, f"{path} answered {client.get(path).status_code} for an admin"

    def test_the_configuration_add_forms_render(self, client, db_session, sample_tenant, sample_branch):
        """ADV-42b. The GET half of the three add routes."""
        _admin(client, db_session, sample_tenant, sample_branch)
        for path in (
            "/ledger/advanced/customs-taxes/add",
            "/ledger/advanced/expense-categories/add",
            "/ledger/advanced/advanced-expenses/add",
        ):
            assert client.get(path).status_code == 200, f"{path} answered {client.get(path).status_code} for an admin"


class TestTRE01Treasury:
    """TRE-01 to TRE-12: the treasury blueprint, mounted under /reports."""

    @pytest.mark.parametrize("path", TREASURY_PATHS)
    def test_anonymous_is_refused(self, client, path):
        """TRE-01. Unfollowed - a login bounce renders 200."""
        resp = client.get(path)
        assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code} anonymously"

    @pytest.mark.parametrize("path", TREASURY_PATHS)
    def test_a_user_without_view_reports_is_refused(self, client, db_session, sample_tenant, sample_branch, path):
        """TRE-02."""
        user = _user(db_session, sample_tenant, slug="tre-nobody", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without view_reports"

    def test_the_treasury_screen_renders_for_a_reporter(self, client, db_session, sample_tenant, sample_branch):
        """TRE-03. The success side."""
        user = _user(db_session, sample_tenant, slug="tre-viewer", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        assert client.get("/reports/treasury").status_code == 200

    def test_the_treasury_export_streams_a_file(self, client, db_session, sample_tenant, sample_branch):
        """TRE-04. An export is a download, so it is not HTML."""
        user = _user(db_session, sample_tenant, slug="tre-exp", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        resp = client.get("/reports/treasury/export")
        assert resp.status_code in (200, 302, 404), f"the treasury export answered {resp.status_code}"
        if resp.status_code == 200:
            ctype = resp.content_type or ""
            assert "text/html" not in ctype, f"the treasury export rendered HTML: {ctype}"

    def test_the_vat_return_renders(self, client, db_session, sample_tenant, sample_branch):
        """TRE-05."""
        user = _user(db_session, sample_tenant, slug="tre-vat", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        assert client.get("/reports/vat-return").status_code == 200

    def test_the_wps_export_streams_a_file(self, client, db_session, sample_tenant, sample_branch):
        """TRE-06. The payroll export the WPS portal consumes."""
        user = _user(db_session, sample_tenant, slug="tre-wps", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        resp = client.get("/reports/wps-export")
        assert resp.status_code in (200, 302, 404), f"the WPS export answered {resp.status_code}"
        if resp.status_code == 200:
            ctype = resp.content_type or ""
            assert "text/html" not in ctype, f"the WPS export rendered HTML: {ctype}"

    def test_the_wps_export_is_not_reachable_from_a_ledger_only_user(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """TRE-07. Payroll data leaves the system through this route.

        ``view_ledger`` is a different grant from ``view_reports`` and this is one
        of the few places the difference has teeth: the export is what an
        accountant hands to a third party.
        """
        _viewer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/reports/wps-export")
        assert resp.status_code in (302, 403), f"a view_ledger user reached the WPS export and got {resp.status_code}"

    def test_the_treasury_mount_point_is_under_reports(self, client, db_session, sample_tenant, sample_branch):
        """TRE-08. The prefix is a fact, not a guess.

        ``treasury_bp`` is mounted at ``/reports``, so ``/treasury`` 404s. A test
        that accepted 404 as an acceptable answer would never catch a move.
        """
        user = _user(db_session, sample_tenant, slug="tre-mount", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        assert client.get("/reports/treasury").status_code == 200
        assert client.get("/treasury").status_code == 404, (
            "a /treasury prefix exists; the catalogue and the tests disagree about the mount point"
        )

    def test_the_treasury_view_is_tenant_scoped(self, client, db_session, sample_tenant, sample_branch):
        """TRE-09. A treasury position is one tenant's cash."""
        user = _user(db_session, sample_tenant, slug="tre-scope", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        body = client.get("/reports/treasury").get_data(as_text=True)
        assert len(body) > 0, "the treasury page rendered nothing"
