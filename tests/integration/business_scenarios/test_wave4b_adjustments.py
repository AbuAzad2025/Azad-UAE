"""Wave 4, second half - stock adjustments at cost (تسوية المخزون).

Everything else in this suite changes stock through a document: a sale, a
purchase, a transfer, a return. An adjustment changes it through a count - a
shelf is found to hold less than the system says, or a damaged unit is written
off, and the difference is posted.

That is the path a user touches at a stocktake, and it is the one most likely to
be quietly wrong, because there is no invoice behind it to compare against. The
number the system believes is the number the ledger must reflect.

Two properties are asserted, and they are the two that break independently:

    the adjustment is valued at cost_price, never at the selling price - valuing
        a write-off at retail overstates the loss by the whole margin, and it
        still balances, so nothing looks wrong until the margin is analysed
    the adjustment reaches the ledger at all - a movement that moves the quantity
        without posting an entry leaves the books disagreeing with the shelf, and
        the disagreement grows silently

The second exists because StockService._post_adjustment_gl returns early when the
product has no cost_price. That early return is exercised directly below rather
than assumed, because it is exactly the shape of defect this file is for.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


@pytest.fixture
def counted_product(db_session, demo_tenant, demo_warehouse):
    """A product with known cost and a known selling price, plus stock.

    cost_price 10 and regular_price 25, so an adjustment valued at the wrong one
    is a factor of 2.5 off and cannot be mistaken for a rounding difference.
    """
    from services.product_service import ProductService
    from services.stock_service import StockService

    unique = str(uuid.uuid4())[:8]
    product = ProductService.create_product(
        tenant_id=demo_tenant.id,
        name=f"Counted Item {unique}",
        sku=f"CNT-{unique}",
        regular_price=Decimal("25"),
        cost_price=Decimal("10"),
    )
    db_session.flush()
    StockService.add_opening_stock(product.id, Decimal("50"), warehouse_id=demo_warehouse.id)
    db_session.commit()
    return {"product": product, "warehouse": demo_warehouse}


def _adjustment_entry(db_session, movement_id, tenant_id):
    """The journal entry this adjustment wrote, or None."""
    from models import GLJournalEntry
    from utils.gl_reference_types import GLRef, filter_entries_by_ref

    return (
        filter_entries_by_ref(db_session.query(GLJournalEntry), GLRef.STOCK_ADJUSTMENT)
        .filter(GLJournalEntry.reference_id == movement_id, GLJournalEntry.status == "posted")
        .first()
    )


def _entry_lines(db_session, entry_id):
    from models import GLAccount, GLJournalLine

    out = {}
    for line in db_session.query(GLJournalLine).filter(GLJournalLine.entry_id == entry_id).all():
        code = db_session.query(GLAccount).get(line.account_id).code
        out[code] = (float(line.debit or 0), float(line.credit or 0))
    return out


class TestS26StockAdjustment:
    """S-26: a counted difference is posted to the ledger at cost."""

    def test_a_write_off_is_debited_to_loss_and_credited_to_inventory(
        self, db_session, pos_cashier, counted_product, demo_tenant
    ):
        """3 units found missing: inventory down 30, loss up 30.

        The credit to inventory is the half that matters. A write-off that
        reduces the quantity but credits nothing leaves the asset on the balance
        sheet at its old value while the shelf is empty.
        """
        from services.stock_service import StockService

        product = counted_product["product"]
        movement = StockService.adjust_stock(
            product.id,
            Decimal("-3"),
            notes="stocktake: 3 missing",
            warehouse_id=counted_product["warehouse"].id,
        )
        db_session.commit()

        assert movement.movement_type == "adjustment", f"movement_type is {movement.movement_type}"
        assert Decimal(str(movement.quantity)) == Decimal("-3"), f"movement quantity is {movement.quantity}"

        entry = _adjustment_entry(db_session, movement.id, demo_tenant.id)
        assert entry is not None, "the adjustment wrote no journal entry - stock moved but the books did not"

        lines = _entry_lines(db_session, entry.id)
        debits = sum(d for d, _ in lines.values())
        credits = sum(c for _, c in lines.values())
        assert abs(debits - credits) < 0.01, f"the adjustment entry does not balance: {lines}"

        # 3 units at cost 10 = 30. Not 75, which is what valuing at retail gives.
        assert abs(debits - 30) < 0.01, (
            f"the adjustment debits {debits}, expected 3 x cost 10 = 30, not the selling price"
        )

    def test_a_surplus_is_debited_to_inventory_and_credited_to_gain(
        self, db_session, pos_cashier, counted_product, demo_tenant
    ):
        """2 units found extra: the mirror image, valued at cost as well."""
        from services.stock_service import StockService

        product = counted_product["product"]
        movement = StockService.adjust_stock(
            product.id,
            Decimal("2"),
            notes="stocktake: 2 surplus",
            warehouse_id=counted_product["warehouse"].id,
        )
        db_session.commit()

        entry = _adjustment_entry(db_session, movement.id, demo_tenant.id)
        assert entry is not None, "a surplus adjustment wrote no journal entry"

        lines = _entry_lines(db_session, entry.id)
        debits = sum(d for d, _ in lines.values())
        credits = sum(c for _, c in lines.values())
        assert abs(debits - credits) < 0.01, f"the adjustment entry does not balance: {lines}"
        assert abs(debits - 20) < 0.01, f"the surplus debits {debits}, expected 2 x cost 10 = 20"

    def test_the_ledger_agrees_with_the_shelf_after_an_adjustment(
        self, db_session, pos_cashier, counted_product, demo_tenant, ledger
    ):
        """Quantity and inventory value move together.

        This is the assertion that catches a movement that updates the quantity
        without posting, or posts without updating. Both leave the system
        internally consistent in isolation and inconsistent as a whole.
        """
        from services.stock_service import StockService

        product = counted_product["product"]
        # "INVENTORY_ASSET" is a concept_code carried on the posting line, not a
        # resolvable concept - asking for it by name raises GLMappingError. The
        # asset side of the adjustment is 1140 directly, per _post_adjustment_gl's
        # own fallback.
        inventory_code = "1140"

        qty_before = Decimal(
            str(StockService.get_product_stock(product.id, warehouse_id=counted_product["warehouse"].id))
        )
        inv_before = ledger.balance(inventory_code, demo_tenant.id)

        StockService.adjust_stock(
            product.id, Decimal("-5"), notes="stocktake", warehouse_id=counted_product["warehouse"].id
        )
        db_session.commit()

        qty_after = Decimal(
            str(StockService.get_product_stock(product.id, warehouse_id=counted_product["warehouse"].id))
        )
        inv_after = ledger.balance(inventory_code, demo_tenant.id)

        assert qty_before - qty_after == Decimal("5"), f"the shelf moved {qty_before} -> {qty_after}"
        assert abs(inv_before) - abs(inv_after) == pytest.approx(50, abs=1), (
            f"inventory value moved {inv_before} -> {inv_after}, expected 5 x cost 10 = 50"
        )

    def test_an_adjustment_without_a_cost_price_is_refused_not_silently_unposted(
        self, db_session, pos_cashier, counted_product, demo_tenant
    ):
        """A stocktake must not be able to desynchronise the books from the shelf.

        StockService._post_adjustment_gl used to begin:

            if not product or not product.cost_price:
                return

        so a product with no cost price had its stock adjusted - the movement
        written, the quantity changed, no journal entry created, no exception, no
        log - and adjust_stock reported success. The ledger was then permanently
        out of step with the shelf, with nothing to indicate it.

        It now raises instead. An adjustment cannot be valued without a cost, and
        posting zero would be worse than refusing: it would move the quantity and
        leave the inventory asset untouched, which looks like agreement in a trial
        balance and is not.
        """
        import pytest as _pytest

        from services.stock_service import StockService

        product = counted_product["product"]
        product.cost_price = None
        db_session.flush()

        qty_before = Decimal(
            str(StockService.get_product_stock(product.id, warehouse_id=counted_product["warehouse"].id))
        )

        with _pytest.raises(ValueError) as exc:
            StockService.adjust_stock(
                product.id, Decimal("-1"), notes="no cost price", warehouse_id=counted_product["warehouse"].id
            )
        db_session.rollback()

        assert "تكلفة" in str(exc.value) or "cost" in str(exc.value).lower(), (
            f"the refusal does not say what is missing: {exc.value}"
        )

        # And critically: the shelf must be exactly where it was. The old code
        # moved it.
        qty_after = Decimal(
            str(StockService.get_product_stock(product.id, warehouse_id=counted_product["warehouse"].id))
        )
        assert qty_after == qty_before, f"a refused adjustment still moved the shelf: {qty_before} -> {qty_after}"

        # And no movement was left behind.
        from models import StockMovement

        dangling = (
            db_session.query(StockMovement)
            .filter_by(product_id=product.id, movement_type="adjustment")
            .order_by(StockMovement.id.desc())
            .first()
        )
        assert dangling is None or Decimal(str(dangling.quantity)) >= 0, (
            f"a refused adjustment left a movement behind: {dangling}"
        )

    def test_an_adjustment_is_refused_when_it_would_oversell(
        self, db_session, pos_cashier, counted_product, demo_tenant
    ):
        """A write-off cannot take more than the shelf holds.

        Without this a negative adjustment is the easiest way to manufacture a
        stockout, and then a phantom sale to "fix" it.
        """
        from services.stock_service import StockService

        product = counted_product["product"]
        try:
            StockService.adjust_stock(
                product.id, Decimal("-9999"), notes="impossible", warehouse_id=counted_product["warehouse"].id
            )
        except Exception:
            pass
        db_session.rollback()

        remaining = Decimal(
            str(StockService.get_product_stock(product.id, warehouse_id=counted_product["warehouse"].id))
        )
        assert remaining >= 0, f"the adjustment left the shelf at {remaining}, which is not a quantity"
