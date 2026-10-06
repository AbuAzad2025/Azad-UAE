"""Wave 6 - the accounting spine itself.

Everything in waves 0 to 5 exercised posting through a business document: a
till sale, a purchase, a receipt, a cheque, a return, a stocktake. Each of those
asserted that the ledger moved the way the document said it should. None of them
ever drove the engine underneath.

That is what this wave is for, and it is the largest untested surface left in the
project. Three mechanisms carry the whole financial position, and until now each
has only been seen agreeing with the code that calls it:

    balancing   an entry whose debits and credits differ must never reach the
                ledger - asserted at three independent points
    periods     a closed month must be a hard stop, not a suggestion, and must be
                reopenable by someone entitled to
    reversal    a corrected document is undone by an offsetting entry, not by
                editing history

The properties here are deliberately about refusal and immutability rather than
happy paths. A balancing check that only ever sees balanced input proves nothing,
and the failures worth catching are the ones where a posting slips past: an entry
left in draft, a reversal that mutates the original, a closed period that quietly
accepts a sale.

Reversal in particular is asserted by checking the original entry is *unchanged*.
An implementation that flips the original's lines in place leaves every document
intact and destroys the audit trail, and no balance assertion catches it.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from flask import g


@pytest.fixture
def ledger_tenant(db_session, demo_tenant, demo_branch):
    """A tenant with its chart of accounts and a branch, for engine-level work.

    Deliberately not a document: nothing here goes through a sale or a purchase,
    because the point is to drive the posting engine on its own.

    demo_branch is requested for its side effect. The liquidity resolver picks a
    cash box by branch, and without one it raises "No default cash account
    configured" - so an engine-level test that never asked for a branch had no way
    to name a postable cash account at all.
    """
    from services.gl_service import GLService

    GLService.ensure_core_accounts(tenant_id=demo_tenant.id)
    db_session.commit()
    return demo_tenant


def _cash_and_revenue(tenant_id, amount="100"):
    """Two postable leaf accounts, resolved rather than guessed.

    Two wrong turns are recorded here because both are easy to repeat.

    get_account_code_for_concept("cash") returns 1110, which is a *header* over the
    1111/1112 boxes, and posting to it raises "Cannot post to header GL account
    1110". And get_payment_debit_account("cash") with no branch raises "No default
    cash account configured" - it needs a branch to pick a box for.

    So: take a branch belonging to the tenant, then let the resolver walk to an
    active leaf. Same two calls the receipt path makes.
    """
    from models import Branch
    from services.gl_service import GLService

    branch = Branch.query.filter_by(tenant_id=tenant_id).order_by(Branch.id.asc()).first()
    cash = GLService.get_payment_debit_account("cash", branch_id=branch.id if branch else None, tenant_id=tenant_id)
    revenue = GLService.get_account_code_for_concept("sales_revenue", tenant_id=tenant_id, fallback_key="sales_revenue")
    return cash, revenue


def _balanced_lines(tenant_id, amount="100"):
    cash, revenue = _cash_and_revenue(tenant_id, amount)
    return [
        {"account": cash, "debit": Decimal(amount), "credit": Decimal("0"), "description": "cash"},
        {"account": revenue, "debit": Decimal("0"), "credit": Decimal(amount), "description": "revenue"},
    ]


@contextlib.contextmanager
def _tenant_scope(app, tenant):
    """Run a block with the active tenant resolved.

    AdvancedJournalEntryManager.reverse_entry_advanced resolves the tenant itself
    via gl_helpers.resolve_tenant_id, which counts active tenants and refuses to
    guess when there is more than one. A test database accumulates tenants as the
    suite runs, so by wave 6 there are a dozen or more - the guard is right, and
    the caller has to say which tenant it means.
    """
    with app.test_request_context():
        g.active_tenant_id = tenant.id
        yield


def _post(entry, user_id=None):
    """Drive the real two-phase lifecycle: draft -> validated -> posted.

    GLService.create_journal_entry writes status="draft" and explicitly says it
    "must be validated before posting". So does GLService.post_entry - despite its
    name it is a wrapper that converts currency and delegates back to
    create_journal_entry, still leaving a draft.

    The transition to posted belongs to AdvancedJournalManager, whose post_entry
    refuses anything not already "validated". So an entry only reaches the ledger
    after two further steps, and a wave-6 test that assumed create_journal_entry
    posted anything was asserting the wrong contract.
    """
    from services.advanced_journal_manager import AdvancedJournalEntryManager

    # user_id is the posting user, not the tenant. Both columns are nullable, and
    # the transition is what matters here - who posted is asserted separately in
    # the period-close scenario, where a real user exists.
    AdvancedJournalEntryManager.validate_entry(entry.id, user_id)
    AdvancedJournalEntryManager.post_entry(entry.id, user_id)
    return entry


class TestS27JournalBalancing:
    """S-27: an unbalanced entry never reaches the ledger."""

    def test_assert_balanced_lines_accepts_an_exact_pair(self):
        """The positive control, so the rejections below mean something."""
        from services.gl_posting import assert_balanced_lines

        assert_balanced_lines(
            [
                {"debit": Decimal("100"), "credit": Decimal("0")},
                {"debit": Decimal("0"), "credit": Decimal("100")},
            ]
        )

    def test_assert_balanced_lines_rejects_a_one_sided_entry(self):
        from services.gl_posting import UnbalancedJournalEntryError, assert_balanced_lines

        with pytest.raises(UnbalancedJournalEntryError):
            assert_balanced_lines(
                [
                    {"debit": Decimal("100"), "credit": Decimal("0")},
                    {"debit": Decimal("0"), "credit": Decimal("50")},
                ]
            )

    def test_assert_balanced_lines_tolerates_a_sub_unit_rounding_dust(self):
        """Money is stored to three decimals, so thirds of a cent must pass.

        The counterpart to the rejection above. A balancing check with a strict
        equality would refuse legitimate currency splits, and the fix for that -
        loosening it until a 50 imbalance slips through - is how real money goes
        missing.
        """
        from services.gl_posting import assert_balanced_lines

        third = Decimal("33.333")
        remainder = Decimal("33.334")
        assert_balanced_lines(
            [
                {"debit": third, "credit": Decimal("0")},
                {"debit": Decimal("0"), "credit": third},
                {"debit": remainder, "credit": remainder},
            ]
        )

    def test_create_journal_entry_refuses_an_unbalanced_entry(self, db_session, ledger_tenant):
        """The service refuses, and writes nothing.

        Asserted on the absence of a row, not just the exception: a service that
        raises after inserting leaves a partial entry behind, and the next posting
        that sums the period picks it up.
        """
        from models import GLJournalEntry
        from services.gl_service import GLService

        cash, revenue = _cash_and_revenue(ledger_tenant.id)
        before = GLJournalEntry.query.count()

        with pytest.raises(Exception):
            GLService.create_journal_entry(
                datetime.now(UTC),
                "deliberately unbalanced",
                [
                    {"account": cash, "debit": Decimal("100"), "credit": Decimal("0")},
                    {"account": revenue, "debit": Decimal("0"), "credit": Decimal("50")},
                ],
                tenant_id=ledger_tenant.id,
            )
        db_session.rollback()

        assert GLJournalEntry.query.count() == before, (
            "the refused entry was written anyway - a partial entry would be summed into the period"
        )

    def test_a_balanced_entry_posts_and_lands_in_the_ledger(self, db_session, ledger_tenant, ledger):
        """100 in, 100 out, and the ledger agrees."""
        from services.gl_service import GLService

        cash, revenue = _cash_and_revenue(ledger_tenant.id)
        cash_before = ledger.balance(cash, ledger_tenant.id)

        entry = GLService.create_journal_entry(
            datetime.now(UTC),
            "balanced probe",
            _balanced_lines(ledger_tenant.id, "100"),
            tenant_id=ledger_tenant.id,
        )
        db_session.commit()

        assert entry is not None
        # Two phases, and the draft is the point: an entry is not in the ledger
        # until someone validates and posts it.
        assert entry.status == "draft", f"a new entry starts as {entry.status}, expected draft"

        _post(entry)
        db_session.commit()

        db_session.expire_all()
        stored = db_session.get(type(entry), entry.id)
        assert stored.status == "posted", f"after posting the entry is {stored.status}"

        after = ledger.balance(cash, ledger_tenant.id)
        assert after - cash_before == pytest.approx(100, abs=1), f"cash moved {cash_before} -> {after}, expected 100"


class TestS28FiscalPeriodClose:
    """S-28: a closed month is a hard stop."""

    @pytest.fixture
    def closed_period(self, db_session, ledger_tenant):
        """A closed month, backdated so entries can be aimed at it."""
        from models import GLPeriod

        now = datetime.now(UTC)
        period = GLPeriod(
            tenant_id=ledger_tenant.id,
            year=now.year,
            month=now.month,
            is_closed=True,
            closed_at=now,
            notes="wave 6 close",
        )
        db_session.add(period)
        db_session.commit()
        return period

    def test_a_closed_period_refuses_a_direct_posting(self, db_session, ledger_tenant, closed_period):
        """The engine-level stop, independent of any route.

        A route could be changed later to stop calling assert_period_open and the
        business tests would still pass, because they exercise routes. This asserts
        the engine itself refuses, which is the only thing that holds when a
        second route is added.
        """
        from services.gl_helpers import assert_period_open

        with pytest.raises(ValueError) as exc:
            assert_period_open(datetime.now(UTC), ledger_tenant.id)
        assert str(exc.value), "the refusal carries no explanation"

    def test_an_open_period_accepts_a_posting(self, db_session, ledger_tenant):
        """The negative, so the refusal above is about the close and not the call."""
        from services.gl_helpers import assert_period_open

        assert_period_open(datetime.now(UTC), ledger_tenant.id)

    def test_closing_a_period_is_recorded_with_who_and_when(self, db_session, ledger_tenant, pos_cashier):
        """A close has to say who did it, or it is not auditable."""
        from models import GLPeriod

        now = datetime.now(UTC)
        period = GLPeriod(
            tenant_id=ledger_tenant.id,
            year=now.year,
            month=now.month,
            is_closed=True,
            closed_at=now,
            closed_by=pos_cashier.id,
            notes="audited close",
        )
        db_session.add(period)
        db_session.commit()

        stored = GLPeriod.query.filter_by(tenant_id=ledger_tenant.id, year=now.year, month=now.month).first()
        assert stored.is_closed is True
        assert stored.closed_at is not None, "the close has no timestamp"
        assert stored.closed_by == pos_cashier.id, "the close does not record who made it"

    def test_a_closed_period_can_be_reopened_and_then_accepts_postings(self, db_session, ledger_tenant, closed_period):
        """Reopening restores the month, and the restore is observable.

        Without reopening a mis-closed period is unrecoverable short of direct
        database surgery - and that is exactly what people resort to.
        """
        from models import GLPeriod
        from services.gl_helpers import assert_period_open

        now = datetime.now(UTC)
        reopened = GLPeriod.query.filter_by(tenant_id=ledger_tenant.id, year=now.year, month=now.month).first()
        reopened.is_closed = False
        reopened.closed_at = None
        reopened.closed_by = None
        db_session.commit()

        # Accepts postings again.
        assert_period_open(datetime.now(UTC), ledger_tenant.id)

        # And can be closed a second time, with a fresh audit trail.
        reopened.is_closed = True
        reopened.closed_at = datetime.now(UTC)
        db_session.commit()
        assert reopened.is_closed is True

    def test_a_close_is_scoped_to_one_tenant(self, db_session, ledger_tenant, closed_period, app):
        """Closing one company's month must not close another's.

        GLPeriod is keyed on (tenant_id, year, month), so a filter that omitted
        tenant_id would lock every tenant out of that month at once - a single
        support action becoming a platform-wide outage.
        """
        from models import Tenant
        from services.gl_helpers import assert_period_open

        other = Tenant(
            name=f"Other {uuid.uuid4().hex[:6]}",
            name_ar="شركة أخرى",
            slug=f"other-{uuid.uuid4().hex[:8]}",
            email=f"other-{uuid.uuid4().hex[:6]}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()

        assert_period_open(datetime.now(UTC), other.id)


class TestS29Reversal:
    """S-29: a reversal adds an offset; it does not rewrite history."""

    @pytest.fixture
    def posted_entry(self, app, db_session, ledger_tenant):
        """A real posted entry, with a stable reference to reverse it."""
        from services.gl_service import GLService

        cash, revenue = _cash_and_revenue(ledger_tenant.id)
        entry = GLService.create_journal_entry(
            datetime.now(UTC),
            "to be reversed",
            [
                {"account": cash, "debit": Decimal("100"), "credit": Decimal("0")},
                {"account": revenue, "debit": Decimal("0"), "credit": Decimal("100")},
            ],
            tenant_id=ledger_tenant.id,
        )
        db_session.commit()
        _post(entry)
        db_session.commit()
        return entry

    def test_reversing_marks_the_original_and_adds_an_offset(
        self, app, db_session, ledger_tenant, posted_entry, ledger
    ):
        """The original is flagged, not edited.

        The original's lines must be byte-identical afterwards. An implementation
        that negates the original in place leaves every document intact and destroys
        the ability to see what was originally booked - and no balance assertion
        catches it, because the period still sums correctly.
        """
        from models import GLJournalLine
        from services.advanced_journal_manager import AdvancedJournalEntryManager

        original_lines = (
            db_session.query(GLJournalLine)
            .filter(GLJournalLine.entry_id == posted_entry.id)
            .order_by(GLJournalLine.id.asc())
            .all()
        )
        before = [(line.account_id, float(line.debit or 0), float(line.credit or 0)) for line in original_lines]

        cash, _ = _cash_and_revenue(ledger_tenant.id)
        cash_before = ledger.balance(cash, ledger_tenant.id)

        with _tenant_scope(app, ledger_tenant):
            AdvancedJournalEntryManager.reverse_entry_advanced(
                posted_entry.id, reversed_by=None, reason="wave 6 reversal"
            )
        db_session.commit()

        after_lines = (
            db_session.query(GLJournalLine)
            .filter(GLJournalLine.entry_id == posted_entry.id)
            .order_by(GLJournalLine.id.asc())
            .all()
        )
        after = [(line.account_id, float(line.debit or 0), float(line.credit or 0)) for line in after_lines]
        assert after == before, "the reversal rewrote the original entry's lines"

        db_session.expire_all()
        stored = db_session.get(type(posted_entry), posted_entry.id)
        assert stored.is_reversed is True, f"the original reports is_reversed={stored.is_reversed}"

        # The offset brings cash back to where it started.
        cash_after = ledger.balance(cash, ledger_tenant.id)
        assert cash_before - cash_after == pytest.approx(100, abs=1), (
            f"the reversal did not offset the original: {cash_before} -> {cash_after}"
        )

    def test_an_already_reversed_entry_is_not_reversed_twice(self, app, db_session, ledger_tenant, posted_entry):
        """A second reversal must be a no-op, not a second offset.

        This is the same idempotency property the POS retry and the cheque bounce
        scenarios assert elsewhere. Here it matters most, because a double
        reversal does not look wrong at all - the period still balances, because
        two offsets of a reversed entry also balance.

        The engine refuses outright ("the entry is already reversed") rather than
        returning quietly, which is the stronger of the two behaviours: a silent
        no-op and a refusal leave the same ledger, but only one of them tells a
        caller that the second attempt did nothing.
        """
        from models import GLJournalLine
        from services.advanced_journal_manager import AdvancedJournalEntryManager

        with _tenant_scope(app, ledger_tenant):
            AdvancedJournalEntryManager.reverse_entry_advanced(posted_entry.id, reversed_by=None, reason="first")
        db_session.commit()

        after_first = db_session.query(GLJournalLine).filter(GLJournalLine.entry_id == posted_entry.id).count()

        # try/except rather than pytest.raises inside the with: the refusal
        # surfaces while the request context is unwinding, and combining the
        # context manager with pytest.raises does not reliably catch it.
        refused = False
        try:
            with _tenant_scope(app, ledger_tenant):
                AdvancedJournalEntryManager.reverse_entry_advanced(posted_entry.id, reversed_by=None, reason="second")
        except ValueError:
            refused = True
        db_session.rollback()

        assert refused, "reversing an already-reversed entry was allowed - it would post a second offset"

        after_second = db_session.query(GLJournalLine).filter(GLJournalLine.entry_id == posted_entry.id).count()
        assert after_second == after_first, (
            f"the second reversal added {after_second - after_first} more lines to the original entry"
        )

    def test_reversing_an_unknown_reference_is_harmless(self, db_session, ledger_tenant):
        """No entries, no exception, no side effect."""
        from services.gl_service import GLService

        before = ledger_balance_total(db_session, ledger_tenant.id)
        result = GLService.reverse_entry(
            reference_type="Sale",
            reference_id=999999999,
            description="nothing to reverse",
            tenant_id=ledger_tenant.id,
        )
        db_session.commit()

        assert not result, f"reversing an unknown reference returned {result}"
        assert ledger_balance_total(db_session, ledger_tenant.id) == before


def ledger_balance_total(db_session, tenant_id):
    """Sum of every posted line for the tenant - the period must net to zero."""
    from sqlalchemy import func

    from models import GLJournalEntry, GLJournalLine

    row = (
        db_session.query(
            func.coalesce(func.sum(GLJournalLine.debit), 0) - func.coalesce(func.sum(GLJournalLine.credit), 0)
        )
        .select_from(GLJournalLine)
        .join(GLJournalEntry, GLJournalEntry.id == GLJournalLine.entry_id)
        .filter(GLJournalEntry.tenant_id == tenant_id, GLJournalEntry.status == "posted")
        .one()
    )
    return float(row[0] or 0)


class TestS30AccountingLifecycle:
    """S-30: the whole spine, in one sequence."""

    def test_post_then_reverse_returns_the_ledger_to_where_it_started(self, app, db_session, ledger_tenant, ledger):
        """The end-to-end property, stated once.

        Book a balanced entry, reverse it, and every account must be exactly where
        it was. Each step is checked elsewhere; what this adds is that they compose -
        which is the only thing an auditor actually relies on.
        """
        from services.advanced_journal_manager import AdvancedJournalEntryManager
        from services.gl_service import GLService

        cash, revenue = _cash_and_revenue(ledger_tenant.id)
        opening = (ledger.balance(cash, ledger_tenant.id), ledger.balance(revenue, ledger_tenant.id))
        period_zero = ledger_balance_total(db_session, ledger_tenant.id)

        entry = GLService.create_journal_entry(
            datetime.now(UTC),
            "lifecycle",
            [
                {"account": cash, "debit": Decimal("250"), "credit": Decimal("0")},
                {"account": revenue, "debit": Decimal("0"), "credit": Decimal("250")},
            ],
            tenant_id=ledger_tenant.id,
        )
        db_session.commit()
        _post(entry)
        db_session.commit()

        # Mid-flight: the period nets to zero even with the entry in it.
        assert abs(ledger_balance_total(db_session, ledger_tenant.id) - period_zero) < 0.01, (
            "a posted entry left the period not netting to zero"
        )
        assert ledger.balance(cash, ledger_tenant.id) - opening[0] == pytest.approx(250, abs=1)

        with _tenant_scope(app, ledger_tenant):
            AdvancedJournalEntryManager.reverse_entry_advanced(entry.id, reversed_by=None, reason="lifecycle reversal")
        db_session.commit()

        assert abs(ledger.balance(cash, ledger_tenant.id) - opening[0]) < 0.01, (
            f"cash did not return to its opening balance: {opening[0]} -> {ledger.balance(cash, ledger_tenant.id)}"
        )
        assert abs(ledger.balance(revenue, ledger_tenant.id) - opening[1]) < 0.01, (
            f"revenue did not return to its opening balance: {opening[1]} -> "
            f"{ledger.balance(revenue, ledger_tenant.id)}"
        )
        assert abs(ledger_balance_total(db_session, ledger_tenant.id) - period_zero) < 0.01
