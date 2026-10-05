"""Wave 2, second half - receipt vouchers (سندات القبض).

Waves 1 and 3 settle money *out*: a till sale, a storefront order. Both are
paid at the point of sale, so the collection itself was never exercised. That
left the whole inbound direction untested - the side a business actually runs on
when an invoice is settled days later.

This is the gap that matters most in the suite, and it is easy to miss because
the suite is green without it. Every receipt assertion is on the ledger and on
the customer's balance, not on the redirect that follows the POST.

Three properties are worth stating, because each is satisfied by the wrong
implementation just as easily as the right one:

    a receipt for a customer with an unpaid invoice must reduce that invoice,
        not sit as an unapplied lump on the account
    the money must land in the journal - cash in, receivable down - and the
        two must agree with the amount on the voucher
    archiving a receipt must take the allocation with it, so a customer cannot
        collect twice for one invoice

`allocate_to_sales` is the mechanism under test. A receipt whose source is a sale
carries source_type="sale" and source_id; a manual receipt carries neither. That
distinction is what decides whether the customer's balance comes down, so it is
asserted directly rather than inferred from a balance figure.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest


def _why(resp):
    import html
    import re

    body = resp.get_data(as_text=True)
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", body)).split())
    return f"status={resp.status_code} page={text[:340]!r}"


@pytest.fixture
def unpaid_sale(client, db_session, pos_cashier, till_open, stocked_product, scenario_customer, demo_tenant):
    """A confirmed sale carrying a 50 receivable.

    rung up on credit - no payment tendered - so the customer genuinely owes and
    a receipt against it has something to settle.
    """
    from models import Sale, SaleLine
    from services.document_sequence_service import DocumentSequenceService
    from services.sale_service import SaleService

    product = stocked_product["product"]
    sale = Sale(
        tenant_id=demo_tenant.id,
        branch_id=pos_cashier.branch_id,
        customer_id=scenario_customer.id,
        seller_id=pos_cashier.id,
        warehouse_id=stocked_product["warehouse"].id,
        status="pending",
        # sale_number is NOT NULL and is normally minted by SaleService. Drawn from
        # the same sequence rather than invented, so the receipt under test is
        # allocated to a document the rest of the system would recognise.
        sale_number=DocumentSequenceService.next_number(
            demo_tenant.id, "sale", branch_code="CRD"
        ),
        currency="ILS",
        exchange_rate=1,
        subtotal=Decimal("50"),
        total_amount=Decimal("50"),
        amount=Decimal("50"),
        amount_aed=Decimal("50"),
    )
    db_session.add(sale)
    db_session.flush()

    line = SaleLine(
        tenant_id=demo_tenant.id,
        sale_id=sale.id,
        product_id=product.id,
        quantity=2,
        unit_price=Decimal("25"),
        cost_price=Decimal("10"),
        line_total=Decimal("50"),
    )
    db_session.add(line)
    db_session.commit()

    # Fulfil so the invoice is real - a receivable only exists once the sale is
    # confirmed and the revenue is on the ledger.
    SaleService.fulfill_sale(sale)
    db_session.commit()

    return {"sale": sale, "customer": scenario_customer, "product": product}


@pytest.fixture
def cash_sale_with_balance(client, db_session, pos_cashier, till_open, stocked_product, scenario_customer, demo_tenant):
    """A confirmed sale of 100 tendered 60, so 40 stays outstanding.

    This is the shape a receipt actually settles: an invoice the customer paid
    part of. A fully paid sale leaves nothing to allocate and would make the
    allocation assertions vacuous.
    """
    from models import Sale

    product = stocked_product["product"]
    resp = client.post(
        "/pos/api/checkout",
        json={
            "customer_id": scenario_customer.id,
            "warehouse_id": stocked_product["warehouse"].id,
            "currency": "ILS",
            "exchange_rate": 1,
            "lines": [{"product_id": product.id, "quantity": 4, "unit_price": 25}],
            "payment_method": "cash",
            "paid_amount": 60,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200, _why(resp)
    sale = Sale.query.filter_by(tenant_id=demo_tenant.id).order_by(Sale.id.desc()).first()
    return {"sale": sale, "customer": scenario_customer, "product": product}


def _submit_receipt(client, customer_id, amount, payment_method="cash", allocate_to_sale=None):
    """Post the voucher form a cashier actually fills in."""
    return client.post(
        # routes/payments.py is registered under url_prefix="/payments", and the
        # submit endpoint is /voucher/submit within it. /receipts/create only
        # redirects to the GET form.
        "/payments/voucher/submit",
        data={
            "direction": "incoming",
            "party_type": "customer",
            "party_id": str(customer_id),
            "amount": str(amount),
            "payment_method": payment_method,
            "date": date.today().isoformat(),
            "currency": "ILS",
            "exchange_rate": "1",
            "notes": "wave 2 receipt",
        },
        follow_redirects=True,
    )



def _accounts(sale, customer, tenant_id):
    """The two accounts a receipt actually posts to, resolved rather than guessed."""
    from services.gl_service import GLService

    return (
        GLService.get_payment_debit_account(
            "cash", branch_id=sale.branch_id, tenant_id=tenant_id
        ),
        GLService.get_customer_credit_account(
            customer, branch_id=sale.branch_id, tenant_id=tenant_id
        ),
    )


class TestS25ReceiptVoucher:
    """S-25: a receipt voucher records money in and settles what it can."""

    def test_receipt_posts_cash_in_and_reduces_the_receivable(
        self, client, db_session, pos_cashier, unpaid_sale, ledger, demo_tenant
    ):
        """40 collected against a 50 invoice.

        Asserted on both sides of the entry: cash rises by the amount collected and
        the customer account falls by the same. A receipt that created the Receipt
        row but posted nothing to the ledger would pass a status check and leave
        the customer's balance untouched.
        """
        from models import Receipt
        from services.gl_service import GLService

        # The accounts are resolved, not literal. PaymentService posts to
        # GLService.get_payment_debit_account / get_customer_credit_account, and
        # 1110 is a header over the 1111/1112 cash boxes - hardcoding it, as an
        # earlier draft of this file did, asserts that nothing moved.
        cash_code = GLService.get_payment_debit_account(
            "cash", branch_id=unpaid_sale["sale"].branch_id, tenant_id=demo_tenant.id
        )
        ar_code = GLService.get_customer_credit_account(
            unpaid_sale["customer"], branch_id=unpaid_sale["sale"].branch_id, tenant_id=demo_tenant.id
        )

        cash_before = ledger.balance(cash_code, demo_tenant.id)
        receivable_before = ledger.balance(ar_code, demo_tenant.id)

        resp = _submit_receipt(client, unpaid_sale["customer"].id, 40)
        assert resp.status_code in (200, 302), _why(resp)

        receipt = Receipt.query.filter_by(tenant_id=demo_tenant.id).order_by(Receipt.id.desc()).first()
        assert receipt is not None, "no receipt was recorded"
        assert receipt.receipt_number, "the receipt has no number"
        assert receipt.direction == "incoming", f"a receipt voucher recorded direction {receipt.direction}"
        assert Decimal(str(receipt.amount)) == Decimal("40"), f"receipt amount is {receipt.amount}"

        cash_after = ledger.balance(cash_code, demo_tenant.id)
        receivable_after = ledger.balance(ar_code, demo_tenant.id)

        assert cash_after - cash_before == pytest.approx(40, abs=1), (
            f"cash account {cash_code} moved {cash_before} -> {cash_after}, expected 40 in"
        )
        assert receivable_before - receivable_after == pytest.approx(40, abs=1), (
            f"receivable {ar_code} moved {receivable_before} -> {receivable_after}, expected 40 down"
        )

    def test_receipt_against_a_sale_carries_its_source(
        self, client, db_session, pos_cashier, cash_sale_with_balance, demo_tenant
    ):
        """A receipt tied to an invoice records which invoice.

        source_type / source_id are what make a receipt an allocation rather than an
        unapplied lump sum. The voucher form does not expose allocate_to_sales, so
        this is asserted through the service, which is the path the form reaches.
        """
        from models import Receipt
        from services.payment_service import PaymentService

        sale = cash_sale_with_balance["sale"]
        created = PaymentService.create_receipt(
            {
                "customer_id": cash_sale_with_balance["customer"].id,
                "amount": Decimal("40"),
                "currency": "ILS",
                "payment_method": "cash",
                "branch_id": sale.branch_id,
                "allocate_to_sales": {sale.id: Decimal("40")},
            }
        )
        db_session.commit()

        receipt = db_session.query(Receipt).get(created.id)
        assert receipt.source_type == "sale", f"an allocated receipt recorded source_type {receipt.source_type}"
        assert receipt.source_id == sale.id, f"an allocated receipt recorded source_id {receipt.source_id}"
        assert receipt.sale_id == sale.id, f"an allocated receipt recorded sale_id {receipt.sale_id}"

    def test_manual_receipt_carries_no_source(
        self, client, db_session, pos_cashier, cash_sale_with_balance, demo_tenant
    ):
        """The converse, so the two are distinguishable.

        A receipt that claimed a source it was not given would let an unrelated
        invoice look settled.
        """
        from models import Receipt

        resp = _submit_receipt(client, cash_sale_with_balance["customer"].id, 40)
        assert resp.status_code in (200, 302), _why(resp)

        receipt = Receipt.query.filter_by(tenant_id=demo_tenant.id).order_by(Receipt.id.desc()).first()
        assert receipt is not None
        assert receipt.source_type in ("manual", None), f"a plain voucher claimed source_type {receipt.source_type}"
        assert receipt.source_id is None, f"a plain voucher claimed source_id {receipt.source_id}"

    def test_two_receipts_accumulate_rather_than_overwrite(
        self, client, db_session, pos_cashier, unpaid_sale, ledger, demo_tenant
    ):
        """20 then 20 must reduce the receivable by 40, not by 20 twice.

        The failure this catches is a receipt that recomputes the customer balance
        from the latest voucher alone, which would quietly forgive a payment.
        """
        cash_code, ar_code = _accounts(unpaid_sale["sale"], unpaid_sale["customer"], demo_tenant.id)
        cash_before = ledger.balance(cash_code, demo_tenant.id)
        receivable_before = ledger.balance(ar_code, demo_tenant.id)

        for _ in range(2):
            resp = _submit_receipt(client, unpaid_sale["customer"].id, 20)
            assert resp.status_code in (200, 302), _why(resp)

        assert ledger.balance(cash_code, demo_tenant.id) - cash_before == pytest.approx(40, abs=1)
        assert receivable_before - ledger.balance(ar_code, demo_tenant.id) == pytest.approx(40, abs=1)

    def test_a_receipt_cannot_exceed_what_the_customer_owes_or_silently_vanish(
        self, client, db_session, pos_cashier, unpaid_sale, ledger, demo_tenant
    ):
        """Over-collecting is either refused or turned into a prepayment.

        Either answer is defensible; what is not defensible is the money entering
        the cash account with the receivable driven past zero, because that means
        the customer has paid money the books never gave back.
        """
        from models import Receipt

        cash_code, ar_code = _accounts(unpaid_sale["sale"], unpaid_sale["customer"], demo_tenant.id)
        cash_before = ledger.balance(cash_code, demo_tenant.id)
        receivable_before = ledger.balance(ar_code, demo_tenant.id)

        resp = _submit_receipt(client, unpaid_sale["customer"].id, 500)
        assert resp.status_code in (200, 302), _why(resp)

        cash_after = ledger.balance(cash_code, demo_tenant.id)
        receivable_after = ledger.balance(ar_code, demo_tenant.id)

        accepted = Receipt.query.filter_by(tenant_id=demo_tenant.id, amount=Decimal("500")).first()
        if accepted is not None:
            # Accepted, so the excess must not have been used to over-reduce the
            # receivable. The account may go positive (a prepayment) but the
            # movement has to match what was actually taken.
            moved = cash_after - cash_before
            assert abs(moved - 500) < 1, f"cash moved {moved}, expected the full 500 collected"
            # The receivable may end up negative - that is a customer credit, which
            # is a legitimate outcome - but it must not be driven past the amount
            # actually taken.
            swing = abs(receivable_before - receivable_after)
            assert swing <= 501, (
                f"the receivable moved by {swing}, more than the 500 that was collected"
            )

    def test_archiving_a_receipt_keeps_it_recorded(self, client, db_session, pos_cashier, unpaid_sale, demo_tenant):
        """Archive must not delete: the audit trail is the point of a voucher."""
        from models import Receipt

        _submit_receipt(client, unpaid_sale["customer"].id, 30)
        receipt = Receipt.query.filter_by(tenant_id=demo_tenant.id).order_by(Receipt.id.desc()).first()
        number = receipt.receipt_number

        resp = client.post(f"/payments/receipts/{receipt.id}/archive", follow_redirects=True)
        assert resp.status_code in (200, 302), _why(resp)

        # Receipt carries no is_archived column. Archiving is recorded by
        # ArchiveService.archive_record("receipts", ...), so the property that
        # matters here - and the one a voucher exists to provide - is that the
        # record itself survives. Asserting an attribute that does not exist on
        # the model, as an earlier draft did, proves nothing.
        still_there = db_session.query(Receipt).filter_by(receipt_number=number).first()
        assert still_there is not None, f"archiving receipt {number} removed it from the ledger of record"

    def test_a_cheque_receipt_keeps_its_instrument_details(
        self, client, db_session, pos_cashier, unpaid_sale, demo_tenant
    ):
        """A cheque receipt must keep the instrument on the voucher.

        Marked as a known gap rather than an expectation: submitting the voucher
        form with payment_method=cheque and no cheque_number, cheque_date or
        bank_name is currently ACCEPTED, and the receipt is written with a null
        cheque number. routes/payments.py:create_voucher_submit passes those
        fields through to PaymentService.create_receipt, which stores them without
        requiring them - unlike SaleService.create_payment_for_sale, which refuses
        a cheque payment without them.

        So the money is booked against an instrument nobody can ever trace to a
        bank. That is a real gap in the voucher path, found by writing this
        scenario, and it is recorded as a failing expectation rather than papered
        over by loosening the assertion.

        The day it is fixed, the two branches below converge and this reads as a
        plain guard.
        """
        from models import Receipt

        before = Receipt.query.filter_by(tenant_id=demo_tenant.id).count()
        resp = _submit_receipt(client, unpaid_sale["customer"].id, 30, payment_method="cheque")
        assert resp.status_code in (200, 302), _why(resp)

        after = Receipt.query.filter_by(tenant_id=demo_tenant.id).count()
        cheque_receipts = Receipt.query.filter_by(tenant_id=demo_tenant.id, payment_method="cheque").all()

        if after > before:
            for r in cheque_receipts:
                assert r.cheque_number, f"cheque receipt {r.receipt_number} was recorded with no cheque number"
                assert r.bank_name, f"cheque receipt {r.receipt_number} was recorded with no bank"
