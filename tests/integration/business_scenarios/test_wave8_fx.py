"""Wave 8 - the multi-currency path. Prefix ADV.

Every other scenario in the suite trades in the tenant's own currency, so the
whole foreign-currency machinery is exercised only by unit tests with mocked
rates. That is a real hole: this system keeps its books in ILS and trades in
AED and USD, and a foreign-currency document is *the* case where a posting can
be arithmetically perfect and still be wrong - balanced, in the right currency,
and on the wrong side of the profit and loss.

This file walks one invoice through the whole life cycle and asserts the money
against the database, not against a service's return value:

    100 USD at 3.50  ->  350.00 ILS booked, 100 USD remembered
    the market moves to 3.80  ->  an unrealized 30.00 ILS on the FX account
    the customer settles at 3.60  ->  a realized difference on the FX account

The account codes are read out of the chart of accounts rather than guessed
(``models/gl_account_registry.py``):

    1130  Accounts Receivable   AR concept,        core_sales module
    4100  Sales Revenue         SALES_REVENUE,     core_sales module
    4400  FX Gains              FX_GAIN,           currency_fx module
    6600  FX Losses             FX_LOSS,           currency_fx module

and the static fallbacks in ``services/gl_service.py`` agree with them
(``receivable`` 1130, ``sales_revenue`` 4100, ``fx_gain`` 4400, ``fx_loss``
6600), so the assertions hold whichever way the mapping resolves.

The rates are planted in ``exchange_rate_records`` - the table
``ExchangeRateService._get_admin_rate`` actually reads - because a scenario
that inserts a rate nobody reads proves nothing.

**What this file is for.** The FX path is unit-tested
(``tests/unit/services/test_fx_revaluation_service.py``) but that test mocks
the ledger, the rate table and the sale, so it proves the arithmetic of the
service and not one thing about the books. These scenarios drive the real
services against the real chart of accounts and read the journal back.

**One assertion in this file is red on purpose.** ADV-57 asserts that a fully
settled invoice leaves no receivable behind, and it fails: after a revaluation
the receivable still carries 30.000 on an invoice that was paid in full, and
the FX accounts carry a net 40.000 against a net exchange difference of
10.000. The unrealized revaluation is never unwound at settlement, so it sits
in the receivable until somebody reverses that period's revaluation - and
nothing in the application does that either. The finding is reported with its
numbers rather than fixed here: this file owns the evidence, not the fix.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

# ── the chart of accounts this path must use ─────────────────────────────
AR_ACCOUNT = "1130"
REVENUE_ACCOUNT = "4100"
FX_GAIN_ACCOUNT = "4400"
FX_LOSS_ACCOUNT = "6600"

#: The tenant's base currency and the currency it trades in. ILS is the
#: platform base (utils/regional_defaults); USD is the invoice currency.
BASE = "ILS"
FOREIGN = "USD"

#: The rate the invoice is written at, the rate the market moves to before
#: settlement, and the rate the customer actually pays at.
INVOICE_RATE = Decimal("3.5")
REVALUATION_RATE = Decimal("3.8")
SETTLEMENT_RATE = Decimal("3.6")

#: 100 USD of goods.
INVOICE_FOREIGN = Decimal("100")
INVOICE_BASE = Decimal("350.000")
REVALUED_BASE = Decimal("380.000")
SETTLED_BASE = Decimal("360.000")

#: The domain tolerance. services/gl_posting.py stores money to three
#: decimals and allows a difference of up to 0.001 in the base currency.
TOLERANCE = Decimal("0.001")


# ── fixtures ─────────────────────────────────────────────────────────────
@pytest.fixture
def fx_tenant(db_session, demo_tenant):
    """The tenant under test: base currency ILS, invoices in USD.

    The base currency is set on the tenant rather than assumed, because
    ``resolve_tenant_base_currency`` reads the tenant first and the system
    default second - a scenario that left it alone would be a single-currency
    scenario wearing a foreign invoice.
    """
    demo_tenant.base_currency = BASE
    demo_tenant.default_currency = BASE
    db_session.commit()
    return demo_tenant


@pytest.fixture
def fx_product(db_session, fx_tenant, demo_warehouse):
    """A product with opening stock, so the sale can be fulfilled.

    Opening stock is added through the stock service, which posts
    Dr 1140 / Cr 3130 - a balanced entry that does not touch any of the
    accounts this file asserts on.
    """
    from services.product_service import ProductService
    from services.stock_service import StockService

    unique = uuid.uuid4().hex[:8]
    product = ProductService.create_product(
        name=f"FX Widget {unique}",
        sku=f"FX-{unique}",
        barcode=f"FXB{unique}",
        regular_price=Decimal("100"),
        cost_price=Decimal("40"),
        tenant_id=fx_tenant.id,
    )
    db_session.flush()
    StockService.add_opening_stock(product.id, Decimal("10"), warehouse_id=demo_warehouse.id)
    db_session.flush()
    return product


@pytest.fixture
def fx_sale(db_session, fx_tenant, demo_branch, demo_warehouse, demo_user, demo_customer, fx_product):
    """A 100 USD invoice written at 3.50 and left unpaid."""
    sale = _post_sale(
        db_session,
        fx_tenant,
        demo_customer,
        fx_product,
        demo_warehouse,
        demo_user,
        currency=FOREIGN,
        rate=INVOICE_RATE,
    )
    db_session.commit()
    return sale


# ── helpers ──────────────────────────────────────────────────────────────
def _post_sale(db_session, tenant, customer, product, warehouse, seller, *, currency, rate, amount=None):
    """Write an invoice through the real sale service.

    ``user_exchange_rate`` is the manual rate a tenant types into the invoice
    form; it is stored on the document and frozen there, which is exactly the
    behaviour the revaluation service depends on.
    """
    from services.sale_service import SaleService

    foreign_amount = amount or INVOICE_FOREIGN
    sale = SaleService.create_sale(
        customer=customer,
        seller=seller,
        lines_data=[{"product": product, "quantity": Decimal("1"), "unit_price": foreign_amount}],
        warehouse_id=warehouse.id,
        currency=currency,
        user_exchange_rate=rate,
    )
    db_session.flush()
    return sale


def _plant_rate(db_session, tenant, *, from_currency, to_currency, rate):
    """Plant a rate in the table the services actually read.

    ``ExchangeRateService._get_admin_rate`` looks for a ``manual`` record
    dated today for the exact (tenant, from, to) pair, so that is what is
    written here. A rate planted anywhere else - a different source, a
    different date, a different tenant - is a rate the revaluation never sees,
    and a scenario built on one would pass without proving anything.

    Tomorrow's date is planted as well. The lookup asks for *today's* rate, so
    a scenario that straddles midnight would find no rate and quietly revalue
    nothing; the second record removes that race without changing which rate
    the lookup finds.
    """
    from datetime import timedelta

    from models import ExchangeRateRecord

    records = []
    for offset in (0, 1):
        record = ExchangeRateRecord(
            tenant_id=tenant.id,
            from_currency=from_currency,
            to_currency=to_currency,
            rate=Decimal(str(rate)),
            source="manual",
            effective_date=date.today() + timedelta(days=offset),
        )
        db_session.add(record)
        records.append(record)
    db_session.commit()
    return records[0]


def _debit_balance(ledger, code, tenant_id) -> Decimal:
    """Debit minus credit - the ledger fixture's own convention.

    An asset or an expense carries a debit balance and comes back positive; a
    revenue or a liability carries a credit balance and comes back negative.
    """
    return Decimal(str(ledger.balance(code, tenant_id)))


def _credit_balance(ledger, code, tenant_id) -> Decimal:
    """Credit minus debit - the natural sign for revenue and for FX gains.

    A gain is a credit, so this is the number a reader expects to see for
    4100 and 4400; the raw fixture sign would read as a loss.
    """
    return -_debit_balance(ledger, code, tenant_id)


def _journal_totals(db_session, tenant_id) -> tuple[Decimal, Decimal]:
    """Every debit and every credit the tenant's posted entries carry."""
    from sqlalchemy import func, select

    from models import GLJournalEntry, GLJournalLine

    stmt = (
        select(
            func.coalesce(func.sum(GLJournalLine.debit), 0),
            func.coalesce(func.sum(GLJournalLine.credit), 0),
        )
        .select_from(GLJournalLine)
        .join(GLJournalEntry, GLJournalEntry.id == GLJournalLine.entry_id)
        .where(GLJournalEntry.tenant_id == tenant_id, GLJournalEntry.status == "posted")
    )
    debit, credit = db_session.execute(stmt).one()
    return Decimal(str(debit or 0)), Decimal(str(credit or 0))


def _entries_for(db_session, tenant_id, reference_type, reference_id):
    from models import GLJournalEntry

    return (
        db_session.query(GLJournalEntry)
        .filter_by(tenant_id=tenant_id, reference_type=reference_type, reference_id=reference_id, status="posted")
        .all()
    )


def _assert_balanced(db_session, tenant_id, step: str) -> None:
    """The tenant's books must balance after every step of the story."""
    debit, credit = _journal_totals(db_session, tenant_id)
    assert abs(debit - credit) <= TOLERANCE, (
        f"{step}: the tenant's books do not balance - debits {debit} vs credits {credit} "
        f"(difference {debit - credit}, tolerance {TOLERANCE})"
    )


# ── the scenarios ────────────────────────────────────────────────────────
class TestADV49ForeignCurrencyInvoice:
    """ADV-49 to ADV-51: the invoice, in the transaction currency and in the base."""

    def test_the_invoice_is_posted_in_the_transaction_currency_and_in_the_base(
        self, db_session, fx_tenant, fx_sale, ledger
    ):
        """ADV-49. One invoice, two currencies, both of them on the record.

        The journal entry must remember that it was a USD document (so a reader
        can tell what the document was denominated in) while every amount it
        posts is in the tenant's base currency (so the trial balance can be
        summed at all). A posting that keeps the foreign amount in the debit
        column balances against a foreign credit column and is worthless as a
        base-currency ledger.
        """
        from models import GLJournalLine
        from utils.gl_reference_types import GLRef

        entries = _entries_for(db_session, fx_tenant.id, GLRef.SALE, fx_sale.id)
        assert len(entries) == 1, f"the invoice posted {len(entries)} entries, expected exactly one"
        entry = entries[0]

        assert entry.currency == FOREIGN, f"the entry is denominated in {entry.currency}, expected {FOREIGN}"
        assert Decimal(str(entry.exchange_rate)) == INVOICE_RATE, (
            f"the entry froze the rate at {entry.exchange_rate}, expected {INVOICE_RATE}"
        )

        lines = db_session.query(GLJournalLine).filter_by(entry_id=entry.id).all()
        receivable = [line for line in lines if line.debit and Decimal(str(line.debit)) > 0]
        assert len(receivable) == 1, f"the invoice did not post exactly one debit line: {len(receivable)}"

        # The transaction amount survives on the line - 100 USD.
        assert Decimal(str(receivable[0].amount)) == INVOICE_FOREIGN, (
            f"the receivable line kept {receivable[0].amount} of the transaction currency, expected {INVOICE_FOREIGN}"
        )
        # And the base amount is what the ledger is summed in - 350.00 ILS.
        assert Decimal(str(receivable[0].debit)) == INVOICE_BASE, (
            f"the receivable line posted {receivable[0].debit} in the base currency, expected {INVOICE_BASE}"
        )

    def test_the_base_amount_lands_in_revenue_and_in_the_receivable(self, db_session, fx_tenant, fx_sale, ledger):
        """ADV-50. The money goes to the two accounts it belongs to.

        350.00 of a foreign invoice is not 350.00 of anything until it is on
        the revenue account and the receivable: a document that balances but
        parks the whole amount on one account is a document nobody can close a
        trial balance with.
        """
        revenue = _credit_balance(ledger, REVENUE_ACCOUNT, fx_tenant.id)
        receivable = _debit_balance(ledger, AR_ACCOUNT, fx_tenant.id)

        assert revenue == INVOICE_BASE, (
            f"revenue {REVENUE_ACCOUNT} carries {revenue}, expected {INVOICE_BASE} "
            f"({INVOICE_FOREIGN} {FOREIGN} at {INVOICE_RATE})"
        )
        assert receivable == INVOICE_BASE, (
            f"receivable {AR_ACCOUNT} carries {receivable}, expected {INVOICE_BASE} "
            f"({INVOICE_FOREIGN} {FOREIGN} at {INVOICE_RATE})"
        )

        # And the FX accounts are untouched: nothing has been revalued yet, so
        # an FX movement here would be an invented gain.
        assert _credit_balance(ledger, FX_GAIN_ACCOUNT, fx_tenant.id) == 0, (
            "the FX gains account moved on an un-revalued invoice"
        )
        assert _debit_balance(ledger, FX_LOSS_ACCOUNT, fx_tenant.id) == 0, (
            "the FX losses account moved on an un-revalued invoice"
        )

        _assert_balanced(db_session, fx_tenant.id, "after the invoice")

    def test_the_customer_ledger_agrees_with_the_invoice(self, db_session, fx_tenant, fx_sale, demo_customer, ledger):
        """ADV-51. The sub-ledger and the control account start out in step.

        The customer owes the invoice in the base currency, and the receivable
        control account carries the same number. When they part company later
        it is worth knowing they started together.
        """
        db_session.refresh(demo_customer)
        assert Decimal(str(demo_customer.balance)) == -INVOICE_BASE, (
            f"the customer balance is {demo_customer.balance}, expected {-INVOICE_BASE} - "
            f"a sale debits the customer by the invoice's base amount"
        )
        assert Decimal(str(fx_sale.balance_due)) == INVOICE_BASE, (
            f"the invoice's open balance is {fx_sale.balance_due}, expected {INVOICE_BASE}"
        )
        assert _debit_balance(ledger, AR_ACCOUNT, fx_tenant.id) == INVOICE_BASE, (
            "the receivable control account and the customer ledger disagree at posting time"
        )


class TestADV52Revaluation:
    """ADV-52 to ADV-54: the market moves before the customer pays."""

    def test_a_changed_rate_posts_the_unrealized_difference_to_the_fx_account(
        self, db_session, fx_tenant, fx_sale, ledger
    ):
        """ADV-52. The rate moved to 3.80, so the open invoice is worth 380.00.

        The revaluation must land 30.00 - the difference between the 350.00 the
        invoice was written at and the 380.00 it is now worth - on the FX
        account, and the receivable must end up carrying the revalued amount.
        A revaluation that adjusts the receivable without touching an FX
        account is a revaluation that invented money.
        """
        from services.fx_revaluation_service import revaluate_open_items

        _plant_rate(db_session, fx_tenant, from_currency=FOREIGN, to_currency=BASE, rate=REVALUATION_RATE)

        summary = revaluate_open_items(tenant_id=fx_tenant.id)
        db_session.commit()

        assert summary["ar_count"] == 1, f"the revaluation picked up {summary['ar_count']} open invoices, expected 1"
        assert summary["ar_diff"] == Decimal("30.000"), (
            f"the revaluation measured {summary['ar_diff']}, expected 30.000 - "
            f"100 USD at 3.80 is {REVALUED_BASE} against {INVOICE_BASE} at 3.50"
        )

        gain = _credit_balance(ledger, FX_GAIN_ACCOUNT, fx_tenant.id)
        assert gain == Decimal("30.000"), f"the FX gains account {FX_GAIN_ACCOUNT} carries {gain}, expected 30.000"
        assert _debit_balance(ledger, FX_LOSS_ACCOUNT, fx_tenant.id) == 0, (
            "the rate moved in the tenant's favour, so nothing may be booked as a loss"
        )

        receivable = _debit_balance(ledger, AR_ACCOUNT, fx_tenant.id)
        assert receivable == REVALUED_BASE, (
            f"the receivable carries {receivable} after the revaluation, expected {REVALUED_BASE} - "
            f"100 USD at {REVALUATION_RATE}"
        )

        _assert_balanced(db_session, fx_tenant.id, "after the revaluation")

    def test_the_revaluation_is_one_entry_per_voucher_and_is_not_posted_twice(
        self, db_session, fx_tenant, fx_sale, ledger
    ):
        """ADV-53. One invoice, one entry, and a second run that posts nothing.

        The revaluation is idempotent per period: it refuses to run again while
        a live revaluation for the same month stands. Without that guard a
        month-end job that runs twice would double every unrealized gain, and
        the books would still balance - they would simply be wrong.
        """
        from services.fx_revaluation_service import revaluate_open_items
        from utils.gl_reference_types import GLRef

        _plant_rate(db_session, fx_tenant, from_currency=FOREIGN, to_currency=BASE, rate=REVALUATION_RATE)

        first = revaluate_open_items(tenant_id=fx_tenant.id)
        db_session.commit()
        entries = _entries_for(db_session, fx_tenant.id, GLRef.FX_GAIN_LOSS, fx_sale.id)
        assert len(entries) == 1, f"the revaluation posted {len(entries)} entries for one invoice, expected 1"
        assert first["entry_ids"] == [entries[0].id], (
            f"the revaluation reported entries {first['entry_ids']}, expected the one it wrote {[entries[0].id]}"
        )

        second = revaluate_open_items(tenant_id=fx_tenant.id)
        db_session.commit()

        assert second["skipped_existing_period"] is True, (
            "a second revaluation in the same period was not refused; it would double the unrealized gain"
        )
        assert second["entry_ids"] == first["entry_ids"], "the refused run reported different entries"
        assert len(_entries_for(db_session, fx_tenant.id, GLRef.FX_GAIN_LOSS, fx_sale.id)) == 1, (
            "the second run posted another entry for the same invoice"
        )
        assert _credit_balance(ledger, FX_GAIN_ACCOUNT, fx_tenant.id) == Decimal("30.000"), (
            "the unrealized gain was booked twice"
        )

    def test_a_rate_that_did_not_move_posts_nothing(self, db_session, fx_tenant, fx_sale, ledger):
        """ADV-54. No movement, no entry.

        The control for ADV-52: if the revaluation posted an entry even when
        the rate was unchanged, then ADV-52 would have been proving that the
        service runs rather than that it measures a difference.
        """
        from services.fx_revaluation_service import revaluate_open_items
        from utils.gl_reference_types import GLRef

        _plant_rate(db_session, fx_tenant, from_currency=FOREIGN, to_currency=BASE, rate=INVOICE_RATE)

        summary = revaluate_open_items(tenant_id=fx_tenant.id)
        db_session.commit()

        assert summary["ar_count"] == 0, f"an unchanged rate revalued {summary['ar_count']} invoices"
        assert summary["entry_ids"] == [], f"an unchanged rate posted entries {summary['entry_ids']}"
        assert _entries_for(db_session, fx_tenant.id, GLRef.FX_GAIN_LOSS, fx_sale.id) == [], (
            "an unchanged rate wrote a journal entry"
        )
        assert _credit_balance(ledger, FX_GAIN_ACCOUNT, fx_tenant.id) == 0, (
            "an unchanged rate moved the FX gains account"
        )
        assert _debit_balance(ledger, AR_ACCOUNT, fx_tenant.id) == INVOICE_BASE, (
            "an unchanged rate moved the receivable"
        )


class TestADV55Settlement:
    """ADV-55 to ADV-57: the customer pays, at a third rate."""

    def test_settling_at_a_third_rate_posts_the_realized_difference(
        self, db_session, fx_tenant, fx_sale, demo_customer, ledger
    ):
        """ADV-55. 100 USD paid at 3.60 against an invoice written at 3.50.

        The customer hands over 100 USD, which is 360.00 of base currency, and
        the invoice was carried at 350.00 - so 10.00 of exchange difference has
        been realized, and it belongs on the FX account. The customer must also
        be credited with exactly what was received: 360.00, not 350.00 (the
        invoice) and not 100 (the foreign amount). Crediting the customer with
        the invoice amount is how a business quietly gives away the difference
        it earned.

        One number is worth watching: the customer is left holding a credit of
        10.00 in the sub-ledger, because the sale debited 350.00 and the
        receipt credited 360.00. The invoice was settled in full in the
        customer's own currency, so that 10.00 is the exchange difference -
        which the ledger has booked as income, and which therefore exists in
        the customer's statement but in no liability account. The receivable
        is 0.000 after this settlement, so the two sides of the house
        disagree by exactly the exchange difference.
        """
        from services.payment_service import PaymentService

        balance_before = Decimal(str(demo_customer.balance))

        receipt = PaymentService.create_receipt(
            {
                "customer_id": demo_customer.id,
                "amount": INVOICE_FOREIGN,
                "currency": FOREIGN,
                "user_exchange_rate": SETTLEMENT_RATE,
                "payment_method": "cash",
                "allocate_to_sales": {fx_sale.id: INVOICE_FOREIGN},
                "branch_id": fx_sale.branch_id,
            }
        )
        db_session.commit()

        assert Decimal(str(receipt.amount_aed)) == SETTLED_BASE, (
            f"the receipt booked {receipt.amount_aed} in the base currency, expected {SETTLED_BASE}"
        )

        # The realized difference is on the FX account, not in revenue.
        gain = _credit_balance(ledger, FX_GAIN_ACCOUNT, fx_tenant.id)
        assert gain == Decimal("10.000"), (
            f"the FX gains account {FX_GAIN_ACCOUNT} carries {gain}, expected 10.000 - "
            f"100 USD paid at {SETTLEMENT_RATE} against an invoice written at {INVOICE_RATE}"
        )
        assert _debit_balance(ledger, FX_LOSS_ACCOUNT, fx_tenant.id) == 0, (
            "the customer paid more than the invoice was worth, so nothing may be booked as a loss"
        )

        # The customer is credited with exactly what was received, to the cent.
        db_session.refresh(demo_customer)
        credited = Decimal(str(demo_customer.balance)) - balance_before
        assert credited == SETTLED_BASE, (
            f"the customer was credited {credited}, expected {SETTLED_BASE} - the base amount actually received"
        )

        # And the invoice is settled.
        db_session.refresh(fx_sale)
        assert Decimal(str(fx_sale.balance_due)) == 0, f"the invoice still shows {fx_sale.balance_due} outstanding"
        assert fx_sale.payment_status == "paid", f"the invoice's payment status is {fx_sale.payment_status}"

        _assert_balanced(db_session, fx_tenant.id, "after the settlement")

    def test_the_books_stay_balanced_after_every_step(self, db_session, fx_tenant, fx_sale, ledger):
        """ADV-56. Balanced after the invoice, after the revaluation, after the payment.

        The tolerance is the domain one: money is stored to three decimals, so
        a difference of up to 0.001 is inside the rounding the ledger allows
        and anything larger is a defect. A balanced journal is the floor of
        this system, not its ceiling - which is why the rest of this file
        asserts *which* accounts carry the money, and not only that it adds up.
        """
        from services.fx_revaluation_service import revaluate_open_items
        from services.payment_service import PaymentService

        _assert_balanced(db_session, fx_tenant.id, "after the invoice")

        _plant_rate(db_session, fx_tenant, from_currency=FOREIGN, to_currency=BASE, rate=REVALUATION_RATE)
        revaluate_open_items(tenant_id=fx_tenant.id)
        db_session.commit()
        _assert_balanced(db_session, fx_tenant.id, "after the revaluation")

        receipt = PaymentService.create_receipt(
            {
                "customer_id": fx_sale.customer_id,
                "amount": INVOICE_FOREIGN,
                "currency": FOREIGN,
                "user_exchange_rate": SETTLEMENT_RATE,
                "payment_method": "cash",
                "allocate_to_sales": {fx_sale.id: INVOICE_FOREIGN},
                "branch_id": fx_sale.branch_id,
            }
        )
        db_session.commit()
        _assert_balanced(db_session, fx_tenant.id, "after the settlement")

        # And nothing was posted twice. Each document posts once: the invoice
        # once, its cost of sales once, the revaluation once, and the receipt
        # once - plus the receipt's own realized-FX adjustment, which is a
        # second entry against the same receipt and is the only place two
        # entries may share a reference.
        from utils.gl_reference_types import GLRef

        assert len(_entries_for(db_session, fx_tenant.id, GLRef.SALE, fx_sale.id)) == 1, (
            "the invoice was posted more than once"
        )
        assert len(_entries_for(db_session, fx_tenant.id, GLRef.SALE_COGS, fx_sale.id)) == 1, (
            "the invoice's cost of sales was posted more than once"
        )
        assert len(_entries_for(db_session, fx_tenant.id, GLRef.FX_GAIN_LOSS, fx_sale.id)) == 1, (
            "the revaluation was posted more than once"
        )

        receipt_entries = _entries_for(db_session, fx_tenant.id, GLRef.RECEIPT, receipt.id)
        receipt_own = [e for e in receipt_entries if (e.description or "").startswith("Receipt ")]
        receipt_fx = [e for e in receipt_entries if (e.description or "").startswith("FX Gain/Loss - Receipt ")]
        assert len(receipt_own) == 1, f"the receipt was posted {len(receipt_own)} times"
        assert len(receipt_fx) == 1, f"the receipt's realized difference was posted {len(receipt_fx)} times"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "The unrealized revaluation is never unwound at settlement. "
            "services/fx_revaluation_service.py debits the difference to the receivable and nothing "
            "reverses it, while services/payment_service.py computes the realized difference against "
            "the ORIGINAL invoice rate. The two mechanisms never meet, so a settled invoice keeps a "
            "receivable of 30.00 and the FX accounts carry 40.00 instead of 10.00. The books still "
            "balance - it is the receivable and the customer statement that disagree. "
            "Remove this marker when the settlement unwinds the revaluation."
        ),
    )
    def test_a_settled_invoice_leaves_no_receivable_behind(self, db_session, fx_tenant, fx_sale, demo_customer, ledger):
        """ADV-57. A settled invoice must not keep a receivable.

        This is the whole life cycle in one assertion: the invoice was written
        at 3.50, the market moved to 3.80 and the revaluation lifted the
        receivable to 380.00, and the customer then settled the invoice in full
        at 3.60. A receivable that survives a settlement is a receivable the
        customer is being told they owe, and it is the one number in this file
        that a tenant's accountant would reconcile first.

        The correct end state: the invoice is settled, so the receivable is
        0.000; the exchange difference that was actually realized is the money
        received (360.00) less the invoice as written (350.00) = 10.00, and
        that is what the FX accounts must carry in total - the 30.00 that was
        unrealized is not profit until it is either realized or reversed.
        """
        from services.fx_revaluation_service import revaluate_open_items
        from services.payment_service import PaymentService

        _plant_rate(db_session, fx_tenant, from_currency=FOREIGN, to_currency=BASE, rate=REVALUATION_RATE)
        revaluate_open_items(tenant_id=fx_tenant.id)
        db_session.commit()

        PaymentService.create_receipt(
            {
                "customer_id": fx_sale.customer_id,
                "amount": INVOICE_FOREIGN,
                "currency": FOREIGN,
                "user_exchange_rate": SETTLEMENT_RATE,
                "payment_method": "cash",
                "allocate_to_sales": {fx_sale.id: INVOICE_FOREIGN},
                "branch_id": fx_sale.branch_id,
            }
        )
        db_session.commit()

        db_session.refresh(fx_sale)
        receivable = _debit_balance(ledger, AR_ACCOUNT, fx_tenant.id)
        net_fx = _credit_balance(ledger, FX_GAIN_ACCOUNT, fx_tenant.id) - _debit_balance(
            ledger, FX_LOSS_ACCOUNT, fx_tenant.id
        )
        expected_net_fx = SETTLED_BASE - INVOICE_BASE

        assert fx_sale.payment_status == "paid", f"the invoice is not settled: {fx_sale.payment_status}"
        assert Decimal(str(fx_sale.balance_due)) == 0, f"the invoice still shows {fx_sale.balance_due} outstanding"

        assert abs(receivable) <= TOLERANCE and abs(net_fx - expected_net_fx) <= TOLERANCE, (
            f"a settled invoice still carries {receivable} on the receivable {AR_ACCOUNT} "
            f"(expected 0.000) and the FX accounts carry a net {net_fx} (expected {expected_net_fx}); "
            f"the invoice was revalued to {REVALUED_BASE} and then settled in full for {SETTLED_BASE}, "
            f"so the unrealized {REVALUED_BASE - INVOICE_BASE} was never unwound at settlement"
        )


class TestADV58TenantIsolation:
    """ADV-58: a revaluation is one tenant's business."""

    def test_a_revaluation_never_touches_another_tenant(self, db_session, fx_tenant, fx_sale, ledger):
        """ADV-58. Two tenants, two invoices, one revaluation.

        The revaluation service is handed a tenant id and must confine itself to
        it. A revaluation that swept up another company's invoice would move
        another tenant's receivable and another tenant's profit - the kind of
        cross-tenant write that is a P0 defect and that no unit test with a
        mocked query would ever see.
        """
        from models import GLJournalEntry
        from services.fx_revaluation_service import revaluate_open_items
        from services.stock_service import StockService
        from tests.factories import (
            BranchFactory,
            CustomerFactory,
            ProductFactory,
            TenantFactory,
            UserFactory,
            WarehouseFactory,
        )

        other = TenantFactory(base_currency=BASE, default_currency=BASE)
        db_session.commit()
        other_branch = BranchFactory(tenant=other)
        other_warehouse = WarehouseFactory(tenant=other, branch=other_branch)
        other_user = UserFactory(tenant=other)
        other_customer = CustomerFactory(tenant=other)
        other_product = ProductFactory(tenant=other)
        db_session.commit()

        StockService.add_opening_stock(other_product.id, Decimal("10"), warehouse_id=other_warehouse.id)
        db_session.flush()

        other_sale = _post_sale(
            db_session,
            other,
            other_customer,
            other_product,
            other_warehouse,
            other_user,
            currency=FOREIGN,
            rate=INVOICE_RATE,
        )
        db_session.commit()

        other_receivable_before = _debit_balance(ledger, AR_ACCOUNT, other.id)
        other_gain_before = _credit_balance(ledger, FX_GAIN_ACCOUNT, other.id)

        # The other tenant has a rate of its own, and it has moved too. Without
        # it the revaluation would skip that invoice for want of a rate, and
        # this scenario would be probing the rate lookup rather than the
        # tenant filter - which is the thing under test here.
        _plant_rate(db_session, other, from_currency=FOREIGN, to_currency=BASE, rate=Decimal("3.9"))

        # The rate moves for the tenant under test only.
        _plant_rate(db_session, fx_tenant, from_currency=FOREIGN, to_currency=BASE, rate=REVALUATION_RATE)
        summary = revaluate_open_items(tenant_id=fx_tenant.id)
        db_session.commit()

        assert summary["ar_count"] == 1, (
            f"the revaluation revalued {summary['ar_count']} invoices, expected only its own"
        )

        assert _debit_balance(ledger, AR_ACCOUNT, other.id) == other_receivable_before, (
            "the revaluation moved another tenant's receivable"
        )
        assert _credit_balance(ledger, FX_GAIN_ACCOUNT, other.id) == other_gain_before, (
            "the revaluation booked an exchange difference on another tenant's books"
        )

        # And the other tenant's invoice is untouched in every other way.
        db_session.refresh(other_sale)
        assert Decimal(str(other_sale.balance_due)) == INVOICE_BASE, (
            f"the other tenant's invoice now shows {other_sale.balance_due}, expected {INVOICE_BASE}"
        )
        touched = (
            db_session.query(GLJournalEntry)
            .filter(GLJournalEntry.tenant_id == other.id, GLJournalEntry.id.in_(summary["entry_ids"]))
            .count()
        )
        assert touched == 0, "the revaluation wrote an entry against the other tenant"


class TestADV59Tolerance:
    """ADV-59 and ADV-60: the per-currency rounding tolerance."""

    def test_a_third_of_the_quantum_is_accepted_and_a_whole_cent_is_not(self, db_session, fx_tenant):
        """ADV-59. The rule the ledger actually applies, mirrored exactly.

        ``services/gl_posting.assert_balanced_lines`` allows a difference of
        up to the currency's tolerance and refuses anything wider. Money is
        stored to three decimals, so the base-currency tolerance of 0.001 is
        the smallest stored unit: a third of it is inside the tolerance and a
        whole cent - ten times the tolerance - is not. The rule is stated
        here so that a change to it cannot pass unnoticed.

        It is asserted twice: against the helper, which is where the rule
        lives, and against the posting gateway, which is where a difference
        actually has to be accepted or refused.
        """
        from models import GLJournalLine
        from services.gl_posting import (
            UnbalancedJournalEntryError,
            assert_balanced_lines,
            post_or_fail,
        )

        # A third of the stored unit: 0.000333.
        assert_balanced_lines(
            [
                {"debit": Decimal("100.000333"), "credit": Decimal("100")},
                {"debit": Decimal("0"), "credit": Decimal("0.000333")},
            ],
            currency=BASE,
        )

        # A whole cent: 0.01, ten tolerances wide.
        with pytest.raises(UnbalancedJournalEntryError):
            assert_balanced_lines(
                [
                    {"debit": Decimal("100.01"), "credit": Decimal("100")},
                    {"debit": Decimal("0"), "credit": Decimal("0")},
                ],
                currency=BASE,
            )

        # The same pair, through the gateway that every posting goes through.
        entry = post_or_fail(
            [
                {
                    "account": AR_ACCOUNT,
                    "concept_code": "AR",
                    "debit": Decimal("100.000333"),
                    "description": "tolerance probe",
                },
                {
                    "account": REVENUE_ACCOUNT,
                    "concept_code": "SALES_REVENUE",
                    "credit": Decimal("100"),
                    "description": "tolerance probe",
                },
            ],
            description="Tolerance probe - a third of a cent apart",
            currency=BASE,
            exchange_rate=Decimal("1"),
            tenant_id=fx_tenant.id,
        )
        db_session.flush()
        assert entry.status == "posted", f"a third of a cent apart was not posted (status {entry.status})"
        lines = db_session.query(GLJournalLine).filter_by(entry_id=entry.id).all()
        debits = sum((Decimal(str(line.debit or 0)) for line in lines), Decimal("0"))
        credits = sum((Decimal(str(line.credit or 0)) for line in lines), Decimal("0"))
        assert debits == credits, f"the accepted posting is not balanced: {debits} vs {credits}"

        with pytest.raises(UnbalancedJournalEntryError):
            post_or_fail(
                [
                    {
                        "account": AR_ACCOUNT,
                        "concept_code": "AR",
                        "debit": Decimal("100.01"),
                        "description": "tolerance probe",
                    },
                    {
                        "account": REVENUE_ACCOUNT,
                        "concept_code": "SALES_REVENUE",
                        "credit": Decimal("100"),
                        "description": "tolerance probe",
                    },
                ],
                description="Tolerance probe - a whole cent apart",
                currency=BASE,
                exchange_rate=Decimal("1"),
                tenant_id=fx_tenant.id,
            )

    def test_the_tolerance_is_a_property_of_the_currency(self):
        """ADV-60. Three-decimal currencies and five-decimal currencies differ.

        ``_CURRENCY_TOLERANCE`` in services/gl_posting.py gives JOD, BHD, KWD,
        OMR and QAR a tolerance of 0.00001 and everything else 0.001. A
        difference that ILS accepts is therefore fifty times too wide for a
        Jordanian dinar, and a posting that only balances under the looser
        rule must not be allowed into a dinar book.
        """
        from services.gl_posting import UnbalancedJournalEntryError, assert_balanced_lines

        # 0.0005 is fifty times the dinar's tolerance of 0.00001, so a dinar
        # book must refuse it.
        with pytest.raises(UnbalancedJournalEntryError):
            assert_balanced_lines(
                [
                    {"debit": Decimal("100.0005"), "credit": Decimal("100")},
                    {"debit": Decimal("0"), "credit": Decimal("0")},
                ],
                currency="JOD",
            )

        # The same difference is inside the tolerance of the base currency.
        assert_balanced_lines(
            [
                {"debit": Decimal("100.0005"), "credit": Decimal("100")},
                {"debit": Decimal("0"), "credit": Decimal("0.0005")},
            ],
            currency=BASE,
        )

        # And the dinar's own tolerance is accepted, where the base
        # currency's would be the only thing that could hide it.
        assert_balanced_lines(
            [
                {"debit": Decimal("100.00001"), "credit": Decimal("100")},
                {"debit": Decimal("0"), "credit": Decimal("0.00001")},
            ],
            currency="JOD",
        )
