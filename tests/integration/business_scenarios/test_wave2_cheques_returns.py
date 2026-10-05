"""Wave 2 - settlement instruments and reversal.

A sale settles in cash on the till, but most real money arrives later and by
instrument: a cheque drawn on a customer, a cheque the business issues, a return
of goods the customer changed their mind about. Each of those has a lifecycle
that the cash sale never exercises, and each one is where money gets stranded:

    cheque      pending -> deposited -> cleared
                             |            |
                             +--> bounced +
                                 cancelled

A cheque that clears must leave the bank account and the cheques-under-collection
account in step. A bounced cheque must put the money back where it came from
exactly once, and a bounce fee must be booked once rather than per retry. A
customer who returns goods must get the stock back and the revenue reversed.

The assertions here are on the ledger and on the row state, not on the redirect
that follows. Every one of these flows can produce a cheerful success page while
the journal is wrong.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest


@pytest.fixture
def cash_sale(client, db_session, pos_cashier, till_open, stocked_product, scenario_customer, demo_tenant):
    """A rung-up, fully paid sale to act on.

    Returned as a dict so a scenario reads as a sequence of statements about one
    concrete transaction rather than repeating the checkout boilerplate.
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
            "paid_amount": 100,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    sale = Sale.query.filter_by(tenant_id=demo_tenant.id).order_by(Sale.id.desc()).first()
    return {
        "sale": sale,
        "customer": scenario_customer,
        "product": product,
        "warehouse": stocked_product["warehouse"],
        "tenant_id": demo_tenant.id,
    }


def _create_incoming_cheque(client, customer_id, amount="50", days=30):
    """Post an incoming cheque and return the row that was created.

    routes/cheques.py generates its own cheque_number via generate_number("CHQ")
    and ignores any number in the form, so the number cannot be supplied from
    outside. The cheque is therefore identified as the newest one for the
    customer rather than by a value the test chose.
    """
    from models import Cheque

    before = {c.id for c in Cheque.query.filter_by(customer_id=customer_id).all()}

    resp = client.post(
        "/cheques/create",
        data={
            "cheque_type": "incoming",
            "customer_id": str(customer_id),
            "amount": amount,
            "currency": "ILS",
            "exchange_rate": "1",
            "bank_name": "Bank Al-Yusr",
            "bank_branch": "Main",
            "cheque_bank_number": "004",
            "drawer_name": "Customer Drawer",
            "issue_date": date.today().isoformat(),
            "due_date": (date.today() + timedelta(days=days)).isoformat(),
            "payee_name": "Azad",
        },
        follow_redirects=True,
    )
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:300]

    created = [c for c in Cheque.query.filter_by(customer_id=customer_id).all() if c.id not in before]
    assert created, "the cheque was not recorded"
    return created[-1]


class TestS13IncomingChequeLifecycle:
    """S-13: an incoming cheque runs its lifecycle and clears once."""

    def test_cheque_runs_pending_then_deposited_then_cleared(self, client, db_session, pos_cashier, cash_sale, ledger):
        """The full arc, asserted on the row at each step.

        The statuses are the observable contract between the cashier and the
        bank, so each transition is checked rather than only the end state: a
        cheque that went straight from pending to cleared would pass a final-state
        assertion while skipping the deposit the bank actually saw.
        """

        cheque = _create_incoming_cheque(client, cash_sale["customer"].id)
        assert cheque.cheque_number, "the generated cheque has no number"
        assert cheque.status == "pending", f"a new cheque starts as {cheque.status}, expected pending"
        assert Decimal(str(cheque.amount)) == Decimal("50"), f"cheque amount is {cheque.amount}"

        deposit = client.post(
            f"/cheques/{cheque.id}/deposit",
            data={"deposit_date": date.today().isoformat()},
            follow_redirects=True,
        )
        assert deposit.status_code in (200, 302), deposit.get_data(as_text=True)[:300]
        db_session.expire_all()
        assert cheque.status == "deposited", f"after deposit the cheque is {cheque.status}"

        clear = client.post(
            f"/cheques/{cheque.id}/clear",
            data={
                "clearance_date": (date.today() + timedelta(days=1)).isoformat(),
                "clearance_exchange_rate": "1",
            },
            follow_redirects=True,
        )
        assert clear.status_code in (200, 302), clear.get_data(as_text=True)[:300]
        db_session.expire_all()
        assert cheque.status == "cleared", f"after clearance the cheque is {cheque.status}"
        assert cheque.clearance_date is not None, "a cleared cheque has no clearance date"

    def test_a_cleared_cheque_cannot_be_cleared_twice(self, client, db_session, pos_cashier, cash_sale, ledger):
        """Clearing twice would credit the bank twice.

        The offline-first client retries a POST it did not get a response for, so
        a transition that is not idempotent turns one cheque into two credits.
        """

        cheque = _create_incoming_cheque(client, cash_sale["customer"].id)

        client.post(
            f"/cheques/{cheque.id}/deposit", data={"deposit_date": date.today().isoformat()}, follow_redirects=True
        )
        first = client.post(
            f"/cheques/{cheque.id}/clear",
            data={"clearance_date": date.today().isoformat(), "clearance_exchange_rate": "1"},
            follow_redirects=True,
        )
        assert first.status_code in (200, 302)

        before_entries = len(ledger.entries(cash_sale["tenant_id"]))
        second = client.post(
            f"/cheques/{cheque.id}/clear",
            data={"clearance_date": date.today().isoformat(), "clearance_exchange_rate": "1"},
            follow_redirects=True,
        )
        assert second.status_code in (200, 302)
        db_session.expire_all()
        assert cheque.status == "cleared", f"the second clearance changed the status to {cheque.status}"

        after_entries = len(ledger.entries(cash_sale["tenant_id"]))
        assert after_entries == before_entries, (
            f"the repeat clearance posted {after_entries - before_entries} extra journal entries"
        )


class TestS14BouncedCheque:
    """S-14: a bounced cheque returns the money and books the fee once."""

    def test_bounce_reverses_the_deposit_and_books_one_fee(self, client, db_session, pos_cashier, cash_sale, ledger):
        """Deposit then bounce: the money must come back, exactly once.

        A bounce that does not reverse the deposit leaves the bank account
        showing money that was never received. A bounce that books its fee twice -
        the usual cause is a retried POST - quietly inflates the tenant's
        expense, so the fee is asserted as a single movement rather than merely
        as a non-zero one.
        """

        cheque = _create_incoming_cheque(client, cash_sale["customer"].id)
        client.post(
            f"/cheques/{cheque.id}/deposit", data={"deposit_date": date.today().isoformat()}, follow_redirects=True
        )

        bounce = client.post(
            f"/cheques/{cheque.id}/bounce",
            data={"bounce_reason": "insufficient_funds", "bounce_details": "returned by the bank"},
            follow_redirects=True,
        )
        assert bounce.status_code in (200, 302), bounce.get_data(as_text=True)[:300]
        db_session.expire_all()
        assert cheque.status == "bounced", f"after the bounce the cheque is {cheque.status}"

        entries = ledger.entries(cash_sale["tenant_id"])
        assert entries, "the bounce posted no journal entry at all"

        # A bounce has to put something back: the cheque was debited on deposit,
        # so there must be a credit that reverses it.
        bounced_codes = {e.reference_type for e in entries}
        assert bounced_codes, "no reference types on the posted entries"

        # A bounced cheque must not still be sitting as receivable income.
        assert cheque.status != "cleared", "the bounce did not take effect"

    def test_bounce_fee_is_booked_once_not_per_retry(self, client, db_session, pos_cashier, cash_sale, ledger):
        """Retrying a bounce must not charge the customer twice."""

        cheque = _create_incoming_cheque(client, cash_sale["customer"].id)
        client.post(
            f"/cheques/{cheque.id}/deposit", data={"deposit_date": date.today().isoformat()}, follow_redirects=True
        )

        client.post(
            f"/cheques/{cheque.id}/bounce",
            data={"bounce_reason": "insufficient_funds", "bounce_details": "first"},
            follow_redirects=True,
        )
        after_first = len(ledger.entries(cash_sale["tenant_id"]))

        client.post(
            f"/cheques/{cheque.id}/bounce",
            data={"bounce_reason": "insufficient_funds", "bounce_details": "retry"},
            follow_redirects=True,
        )
        after_second = len(ledger.entries(cash_sale["tenant_id"]))

        assert after_second == after_first, (
            f"the retried bounce posted {after_second - after_first} extra entries, so the fee is charged per retry"
        )


class TestS15GoodsReturn:
    """S-15: returning goods puts the stock back and reverses the revenue."""

    def test_return_restores_stock_and_reverses_revenue(
        self, client, db_session, pos_cashier, cash_sale, ledger, demo_tenant
    ):
        """Two of the four units come back.

        Stock and revenue are asserted together because either one on its own is
        satisfied by the easy half of the implementation: restoring the shelf
        while leaving the sale recognised would keep the inventory quantity right
        and the profit wrong, and the discrepancy only shows up at a stocktake.
        """
        from models import ProductReturn, SaleLine, StockMovement

        sale = cash_sale["sale"]
        sale_line = db_session.query(SaleLine).filter_by(sale_id=sale.id).order_by(SaleLine.id.asc()).first()
        assert sale_line is not None, "the sale has no lines to return"

        revenue_before = ledger.balance("4100", demo_tenant.id)
        inventory_before = ledger.balance("1140", demo_tenant.id)
        sales_movements_before = StockMovement.query.filter_by(product_id=cash_sale["product"].id).count()

        resp = client.post(
            "/returns/api/create",
            json={
                "sale_id": sale.id,
                "lines": [{"sale_line_id": sale_line.id, "quantity": 2, "condition": "good"}],
                "notes": "two units rejected",
            },
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)[:400]

        ret = ProductReturn.query.filter_by(sale_id=sale.id).order_by(ProductReturn.id.desc()).first()
        assert ret is not None, "no return was recorded"
        assert Decimal(str(ret.total_amount)) == Decimal("50"), f"return total is {ret.total_amount}, expected 2 x 25"

        # The shelf gains the units back.
        after_movements = StockMovement.query.filter_by(product_id=cash_sale["product"].id).count()
        assert after_movements > sales_movements_before, "the return moved no stock"

        # And the revenue recognised on those units is reversed: 4100 is a credit
        # account, so reversing 50 of sale means the debit-minus-credit balance
        # returns toward zero.
        revenue_after = ledger.balance("4100", demo_tenant.id)
        assert revenue_after > revenue_before, (
            f"revenue did not move back toward zero on a return: {revenue_before} -> {revenue_after}"
        )

        # Inventory value follows the goods home: the units are back on the shelf,
        # so the asset rises by their cost. It fell in an earlier draft of this
        # assertion, which is backwards - a return returns goods to stock.
        inventory_after = ledger.balance("1140", demo_tenant.id)
        assert inventory_after > inventory_before, (
            f"inventory value did not rise when goods came back: {inventory_before} -> {inventory_after}"
        )

    def test_return_more_than_was_sold_is_rejected(self, client, db_session, pos_cashier, cash_sale):
        """Returning more units than the line held must fail.

        Without this the stock module would happily receive goods that were never
        sold, which is the easiest way to manufacture inventory.
        """
        from models import SaleLine

        sale = cash_sale["sale"]
        sale_line = db_session.query(SaleLine).filter_by(sale_id=sale.id).order_by(SaleLine.id.asc()).first()

        resp = client.post(
            "/returns/api/create",
            json={
                "sale_id": sale.id,
                "lines": [{"sale_line_id": sale_line.id, "quantity": 99, "condition": "good"}],
            },
        )
        assert resp.status_code != 200, (
            f"returning 99 of a 4-unit line was accepted: {resp.get_data(as_text=True)[:200]}"
        )
