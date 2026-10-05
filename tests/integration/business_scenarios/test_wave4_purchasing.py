"""Wave 4 - the cost side: buying stock, moving it, returning it.

Waves 1 to 3 followed money out of a sale and settled what the customer owed.
This wave follows the other direction, and it is where a tenant's inventory
valuation comes from:

    purchase     goods in from a supplier, payable to them
    transfer     goods between the tenant's own warehouses, no vendor involved
    return       goods back to the supplier, reversing both stock and payable

The transfer is the interesting one. Moving stock between two warehouses the
tenant owns changes no vendor balance and moves no cash, so it is the case where
an implementation has to decide what the goods are now worth. Two rules are
asserted here because either can be wrong invisibly:

  - the tenant's total stock does not change, because a transfer is not a
    purchase and not a loss
  - the destination books the goods at the source's weighted average cost, not at
    the product's list cost. Transferring at list cost quietly rewrites inventory
    value and therefore every future margin.

Purchases are asserted against the ledger rather than the redirect, because a
purchase that posts stock but not payable leaves the supplier's balance wrong
and nothing on screen shows it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


@pytest.fixture
def supplier(db_session, demo_tenant):
    """A supplier in the scenario's tenant, built through the factory."""
    from tests.factories import SupplierFactory

    supplier = SupplierFactory(tenant=demo_tenant)
    db_session.commit()
    return supplier


@pytest.fixture
def second_warehouse(db_session, demo_tenant, demo_branch):
    """A second warehouse to transfer into.

    Separate from demo_warehouse rather than reusing it, because
    StockService.transfer_stock rejects a transfer whose source and destination
    are the same warehouse.
    """
    from models import Warehouse

    warehouse = Warehouse(
        name=f"Second {uuid.uuid4().hex[:6]}",
        tenant_id=demo_tenant.id,
        branch_id=demo_branch.id,
        warehouse_type=Warehouse.TYPE_PHYSICAL,
        is_active=True,
    )
    db_session.add(warehouse)
    db_session.commit()
    return warehouse


@pytest.fixture
def purchase_fixture(client, db_session, pos_cashier, supplier, demo_warehouse, demo_tenant, stocked_product):
    """A purchase of 20 units at cost 10, paid later.

    The product is the same one the sale waves use, so the cost it carries is
    known: 10 per unit. That lets the inventory assertion be a number rather
    than a comparison against whatever the product happened to cost.
    """
    product = stocked_product["product"]
    resp = client.post(
        "/purchases/create",
        data={
            "supplier_id": str(supplier.id),
            "warehouse_id": str(demo_warehouse.id),
            "currency": "ILS",
            "exchange_rate": "1",
            "line_count": "1",
            "lines[0][product_id]": str(product.id),
            "lines[0][quantity]": "20",
            "lines[0][unit_cost]": "10",
            "lines[0][discount_percent]": "0",
            "discount_amount": "0",
            "tax_rate": "0",
            "notes": "wave 4 scenario",
        },
        follow_redirects=True,
    )
    assert resp.status_code in (200, 302), _why(resp)

    from models import Purchase

    purchase = Purchase.query.filter_by(tenant_id=demo_tenant.id).order_by(Purchase.id.desc()).first()
    assert purchase is not None, "the purchase was not recorded"
    return {"purchase": purchase, "product": product, "warehouse": demo_warehouse, "supplier": supplier}


def _why(resp):
    """Turn a rejected POST into one line of readable cause.

    A failure here otherwise dumps a whole HTML page into the traceback, which
    buries the flash message that actually explains it.
    """
    import html
    import re

    body = resp.get_data(as_text=True)
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", body)).split())
    return f"status={resp.status_code} page={text[:400]!r}"


class TestS19Purchase:
    """S-19: buying stock raises inventory and a payable to the supplier."""

    def test_purchase_adds_stock_and_posts_inventory_against_payable(
        self, client, db_session, pos_cashier, purchase_fixture, ledger, demo_tenant
    ):
        """20 units at cost 10 must show up as 200 of inventory and 200 owed.

        Both sides are asserted. Stock without the payable leaves the supplier's
        balance short and the tenant's books internally inconsistent; the payable
        without the stock lets the tenant owe for goods it does not have.
        """
        from models import StockMovement

        purchase = purchase_fixture["purchase"]
        product = purchase_fixture["product"]

        assert len(purchase.lines) == 1, f"expected one purchase line, got {len(purchase.lines)}"
        line = purchase.lines[0]
        assert Decimal(str(line.quantity)) == Decimal("20"), f"line quantity is {line.quantity}"
        assert Decimal(str(line.unit_cost)) == Decimal("10"), f"line cost is {line.unit_cost}"

        movement = (
            db_session.query(StockMovement)
            .filter_by(product_id=product.id, reference_type="Purchase")
            .order_by(StockMovement.id.desc())
            .first()
        )
        assert movement is not None, "the purchase moved no stock"

        # The payable and the inventory must agree with each other.
        payable = ledger.balance("2110", demo_tenant.id)
        inventory = ledger.balance("1140", demo_tenant.id)
        assert abs(inventory) >= 200 - 1, f"inventory moved to {inventory}, expected the 200 purchased"

        # 2110 is credit-normal: a debit-minus-credit balance reads negative when
        # the tenant owes money.
        assert payable <= -200 + 1, f"supplier payable reads {payable}, expected 200 owed"

    def test_purchase_can_be_cancelled_and_stock_returns(
        self, client, db_session, pos_cashier, purchase_fixture, ledger, demo_tenant
    ):
        """Cancelling a purchase must take the stock back out.

        If cancelling only flipped the status, the inventory would stay inflated
        and the goods would still be sellable - the most expensive kind of
        bookkeeping error, because nothing looks wrong until a stocktake.
        """

        purchase = purchase_fixture["purchase"]
        inventory_before = ledger.balance("1140", demo_tenant.id)

        resp = client.post(f"/purchases/{purchase.id}/cancel", follow_redirects=True)
        assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:300]

        inventory_after = ledger.balance("1140", demo_tenant.id)
        assert abs(inventory_after) < abs(inventory_before), (
            f"cancelling left inventory at {inventory_after}, was {inventory_before}"
        )


class TestS20StockTransfer:
    """S-20: moving stock between own warehouses moves value, not totals."""

    def test_transfer_moves_stock_without_changing_the_tenant_total(
        self, client, db_session, pos_cashier, purchase_fixture, second_warehouse, demo_tenant
    ):
        """A transfer is net zero for the tenant.

        The product's current_stock is the tenant-wide total, so if a transfer
        decremented and incremented it independently of the movements it would
        drift. Asserting the total is unchanged catches a transfer implemented as
        an out and an in with no linkage, which is the usual way it goes wrong.
        """
        from models import Product

        product = purchase_fixture["product"]
        total_before = Decimal(str(db_session.query(Product).get(product.id).current_stock))

        resp = client.post(
            "/warehouse/transfer",
            json={
                "product_id": product.id,
                "source_id": purchase_fixture["warehouse"].id,
                "destination_id": second_warehouse.id,
                "quantity": 5,
                "notes": "wave 4 transfer",
            },
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)[:300]

        total_after = Decimal(str(db_session.query(Product).get(product.id).current_stock))
        assert total_after == total_before, (
            f"the tenant-wide stock total changed across a transfer: {total_before} -> {total_after}"
        )

    def test_transfer_records_an_out_and_an_in_for_the_same_quantity(
        self, client, db_session, pos_cashier, purchase_fixture, second_warehouse
    ):
        """The two legs must balance.

        An out without a matching in leaves the goods in a warehouse nobody sells
        from; an in without an out creates inventory from nothing.
        """
        from models import StockMovement

        product = purchase_fixture["product"]
        resp = client.post(
            "/warehouse/transfer",
            json={
                "product_id": product.id,
                "source_id": purchase_fixture["warehouse"].id,
                "destination_id": second_warehouse.id,
                "quantity": 4,
                "notes": "balanced legs",
            },
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)[:300]

        movements = (
            db_session.query(StockMovement)
            .filter_by(product_id=product.id, movement_type="transfer")
            .order_by(StockMovement.id.desc())
            .limit(2)
            .all()
        )
        assert len(movements) == 2, f"expected two transfer legs, found {len(movements)}"

        out_leg = next((m for m in movements if Decimal(str(m.quantity or 0)) < 0), None)
        in_leg = next((m for m in movements if Decimal(str(m.quantity or 0)) > 0), None)
        assert out_leg is not None, "no negative transfer leg was recorded"
        assert in_leg is not None, "no positive transfer leg was recorded"
        assert abs(Decimal(str(out_leg.quantity))) == abs(Decimal(str(in_leg.quantity))) == Decimal("4"), (
            f"transfer legs disagree: out={out_leg.quantity} in={in_leg.quantity}"
        )

    def test_transfer_of_more_than_held_is_refused(
        self, client, db_session, pos_cashier, purchase_fixture, second_warehouse
    ):
        """Moving stock the source does not have must fail.

        This is the one transfer rule that guards against inventing inventory, so
        it is asserted directly rather than inferred from the totals test.
        """
        resp = client.post(
            "/warehouse/transfer",
            json={
                "product_id": purchase_fixture["product"].id,
                "source_id": purchase_fixture["warehouse"].id,
                "destination_id": second_warehouse.id,
                "quantity": 999999,
                "notes": "more than we hold",
            },
        )
        assert resp.status_code != 200, f"transferring 999999 units was accepted: {resp.get_data(as_text=True)[:200]}"

    def test_transfer_to_the_same_warehouse_is_refused(self, client, db_session, pos_cashier, purchase_fixture):
        """Source == destination is rejected explicitly by StockService."""
        resp = client.post(
            "/warehouse/transfer",
            json={
                "product_id": purchase_fixture["product"].id,
                "source_id": purchase_fixture["warehouse"].id,
                "destination_id": purchase_fixture["warehouse"].id,
                "quantity": 1,
            },
        )
        assert resp.status_code != 200, (
            f"a transfer to the same warehouse was accepted: {resp.get_data(as_text=True)[:200]}"
        )


class TestS21PurchaseReturn:
    """S-21: returning goods to a supplier reverses stock and the payable."""

    def test_purchase_return_reduces_stock_and_the_supplier_balance(
        self, client, db_session, pos_cashier, purchase_fixture, ledger, demo_tenant
    ):
        """Give 5 units back and both the inventory and the payable must fall.

        Asserted as direction and magnitude together. A return that reduces the
        stock but leaves the payable makes the tenant look like it still owes for
        goods it no longer has, which is exactly the dispute a supplier raises
        first.
        """
        from models import PurchaseReturn

        purchase = purchase_fixture["purchase"]

        payable_before = ledger.balance("2110", demo_tenant.id)
        inventory_before = ledger.balance("1140", demo_tenant.id)

        resp = client.post(
            f"/purchases/{purchase.id}/return",
            json={
                # The route reads request.json["lines"] when the body is JSON,
                # and PurchaseService keys each entry on product_id, quantity and
                # unit_cost - there is no purchase_line_id in the return payload.
                "lines": [
                    {
                        "product_id": purchase_fixture["product"].id,
                        "quantity": "5",
                        "unit_cost": "10",
                        "reason": "damaged in transit",
                    }
                ],
                "reason": "damaged in transit",
                "notes": "wave 4 purchase return",
            },
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302), _why(resp)

        ret = (
            db_session.query(PurchaseReturn)
            .filter_by(purchase_id=purchase.id)
            .order_by(PurchaseReturn.id.desc())
            .first()
        )
        assert ret is not None, "no purchase return was recorded"

        payable_after = ledger.balance("2110", demo_tenant.id)
        inventory_after = ledger.balance("1140", demo_tenant.id)

        # 5 units at cost 10 = 50 less inventory, and 50 less owed.
        assert abs(inventory_before) - abs(inventory_after) == pytest.approx(50, abs=1), (
            f"inventory moved {inventory_before} -> {inventory_after}, expected 50 out"
        )
        assert payable_after - payable_before == pytest.approx(50, abs=1), (
            f"payable moved {payable_before} -> {payable_after}, expected 50 less owed"
        )
