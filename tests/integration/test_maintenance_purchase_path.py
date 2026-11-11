"""The maintenance purchase path, exercised end to end.

Buying the parts is the other half of the module: the workshop buys
spare parts from suppliers, and the parts it buys are what it later
issues at the moving average cost. So the assertions here are made
against the database, not against a service return value:

* receiving an order puts the goods on the shelf at the supplier's cost
  and moves the warehouse's moving average with them;
* the ledger records the inventory against the supplier's payable, and
  the recoverable tax against the input-tax account - the tax is never
  capitalised into the stock, because that would inflate the moving
  average every part is later issued at;
* receiving the same order twice is refused, so the shelf cannot be
  loaded twice by one document.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models import (
    GLAccount,
    GLJournalEntry,
    GLJournalLine,
    MaintenancePurchaseOrderStatus,
    ProductWarehouseCost,
    StockMovement,
)
from services.maintenance_purchase_service import MaintenancePurchaseService


def _account_balance(db, tenant_id: int, code: str) -> Decimal:
    """Debit minus credit for one account code, from posted journal lines."""
    stmt = (
        select(
            func.coalesce(func.sum(GLJournalLine.debit), 0),
            func.coalesce(func.sum(GLJournalLine.credit), 0),
        )
        .select_from(GLJournalLine)
        .join(GLJournalEntry, GLJournalEntry.id == GLJournalLine.entry_id)
        .join(GLAccount, GLAccount.id == GLJournalLine.account_id)
        .where(
            GLAccount.code == str(code),
            GLJournalEntry.tenant_id == int(tenant_id),
            GLJournalEntry.status == "posted",
        )
    )
    debit, credit = db.execute(stmt).one()
    return Decimal(str(debit or 0)) - Decimal(str(credit or 0))


def _trial_balance(db, tenant_id: int) -> tuple[Decimal, Decimal]:
    stmt = (
        select(
            func.coalesce(func.sum(GLJournalLine.debit), 0),
            func.coalesce(func.sum(GLJournalLine.credit), 0),
        )
        .select_from(GLJournalLine)
        .join(GLJournalEntry, GLJournalEntry.id == GLJournalLine.entry_id)
        .where(
            GLJournalEntry.tenant_id == int(tenant_id),
            GLJournalEntry.status == "posted",
        )
    )
    debit, credit = db.execute(stmt).one()
    return Decimal(str(debit or 0)), Decimal(str(credit or 0))


def _purchase_order(db, tenant, user, warehouse, *, tax_rate="5", supplier_id=None):
    return MaintenancePurchaseService.create_purchase_order(
        tenant_id=tenant.id,
        branch_id=warehouse.branch_id,
        warehouse_id=warehouse.id,
        supplier_id=supplier_id,
        supplier_name="Spare Parts Supplier",
        tax_rate=Decimal(tax_rate),
    )


class TestPurchaseOrderCreation:
    """The order names the supplier and the shelf before any part."""

    def test_a_purchase_order_is_created_with_a_number(self, db_session, sample_tenant, sample_warehouse):
        order = _purchase_order(db_session, sample_tenant, None, sample_warehouse)
        db_session.flush()

        assert order.po_number.startswith("MPO-")
        assert order.status == MaintenancePurchaseOrderStatus.DRAFT
        assert order.warehouse_id == sample_warehouse.id
        assert order.branch_id == sample_warehouse.branch_id
        assert order.total_amount == Decimal("0")

    def test_a_warehouse_of_another_tenant_is_refused(self, db_session, sample_tenant, sample_warehouse):
        """مستودع شركة أخرى مرفوض."""
        from uuid import uuid4

        from models import Tenant, Warehouse
        from utils.tenanting import without_tenant_scope

        with without_tenant_scope():
            other = Tenant(
                name="Other Purchase Tenant",
                name_ar="شركة أخرى",
                slug=f"other-po-{uuid4().hex[:8]}",
                country="AE",
                default_currency="AED",
                base_currency="AED",
            )
            db_session.add(other)
            db_session.flush()
            other_warehouse = Warehouse(
                tenant_id=other.id,
                name="Other Warehouse",
                is_active=True,
            )
            db_session.add(other_warehouse)
            db_session.flush()

        with pytest.raises(ValueError, match="المستودع غير موجود"):
            MaintenancePurchaseService.create_purchase_order(
                tenant_id=sample_tenant.id,
                branch_id=None,
                warehouse_id=other_warehouse.id,
                supplier_id=None,
                supplier_name=None,
                tax_rate=Decimal("5"),
            )

    def test_a_negative_quantity_is_refused(self, db_session, sample_tenant, sample_warehouse, sample_product):
        order = _purchase_order(db_session, sample_tenant, None, sample_warehouse)
        db_session.flush()

        with pytest.raises(ValueError, match="الكمية"):
            MaintenancePurchaseService.add_line(
                purchase_order_id=order.id,
                tenant_id=sample_tenant.id,
                product_id=sample_product.id,
                quantity=Decimal("-1"),
                unit_cost=Decimal("10"),
            )


class TestPurchaseReceipt:
    """Receiving the order is the moment the parts become the workshop's stock."""

    def _received_order(self, db_session, tenant, user, warehouse, product, *, qty="10", cost="25"):
        order = _purchase_order(db_session, tenant, user, warehouse)
        db_session.flush()
        MaintenancePurchaseService.add_line(
            purchase_order_id=order.id,
            tenant_id=tenant.id,
            product_id=product.id,
            quantity=Decimal(qty),
            unit_cost=Decimal(cost),
        )
        db_session.flush()
        return order

    def test_receiving_puts_the_goods_on_the_shelf_at_the_supplier_cost(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_product
    ):
        order = self._received_order(db_session, sample_tenant, sample_user, sample_warehouse, sample_product)

        received = MaintenancePurchaseService.receive_purchase_order(
            order.id,
            sample_tenant.id,
            received_by=sample_user.id,
        )
        db_session.flush()

        assert received.status == MaintenancePurchaseOrderStatus.RECEIVED
        assert received.received_at is not None
        assert received.received_by == sample_user.id

        # The goods are on the shelf.
        movement = (
            db_session.query(StockMovement)
            .filter_by(tenant_id=sample_tenant.id, product_id=sample_product.id)
            .filter(StockMovement.movement_type == "purchase")
            .one()
        )
        assert movement.quantity == Decimal("10.000")
        assert movement.warehouse_id == sample_warehouse.id

        # And the warehouse's moving average is the supplier's cost.
        pwc = (
            db_session.query(ProductWarehouseCost)
            .filter_by(
                tenant_id=sample_tenant.id,
                product_id=sample_product.id,
                warehouse_id=sample_warehouse.id,
            )
            .one()
        )
        assert pwc.total_quantity == Decimal("10.000")
        assert pwc.total_value == Decimal("250.000")
        assert pwc.average_cost == Decimal("25.0000")

    def test_the_ledger_records_inventory_against_the_payable(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_product
    ):
        """المخزون مقابل ذمم المورد، والضريبة على ضريبة المدخلات."""
        order = self._received_order(db_session, sample_tenant, sample_user, sample_warehouse, sample_product)
        assert order.subtotal == Decimal("250.000")
        assert order.tax_amount == Decimal("12.500")
        assert order.total_amount == Decimal("262.500")

        MaintenancePurchaseService.receive_purchase_order(
            order.id,
            sample_tenant.id,
            received_by=sample_user.id,
        )
        db_session.flush()

        # The inventory carries the net amount only - the tax is
        # recoverable and never capitalised into the stock.
        assert _account_balance(db_session, sample_tenant.id, "1140") == Decimal("250.000")
        # The payable carries the gross.
        assert _account_balance(db_session, sample_tenant.id, "2110") == Decimal("-262.500")
        # And the tax sits in the input-tax account.
        assert _account_balance(db_session, sample_tenant.id, "2122") == Decimal("12.500")
        # The books balance.
        debit, credit = _trial_balance(db_session, sample_tenant.id)
        assert debit == credit

    def test_receiving_twice_is_refused(self, db_session, sample_tenant, sample_user, sample_warehouse, sample_product):
        order = self._received_order(db_session, sample_tenant, sample_user, sample_warehouse, sample_product)
        MaintenancePurchaseService.receive_purchase_order(
            order.id,
            sample_tenant.id,
            received_by=sample_user.id,
        )
        db_session.flush()
        movements_after_first = db_session.query(StockMovement).filter_by(tenant_id=sample_tenant.id).count()

        with pytest.raises(ValueError, match="مسبقاً"):
            MaintenancePurchaseService.receive_purchase_order(
                order.id,
                sample_tenant.id,
                received_by=sample_user.id,
            )
        assert db_session.query(StockMovement).filter_by(tenant_id=sample_tenant.id).count() == movements_after_first

    def test_a_line_cannot_be_added_after_the_receipt(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_product
    ):
        order = self._received_order(db_session, sample_tenant, sample_user, sample_warehouse, sample_product)
        MaintenancePurchaseService.receive_purchase_order(
            order.id,
            sample_tenant.id,
            received_by=sample_user.id,
        )
        db_session.flush()

        with pytest.raises(ValueError, match="تم استلامه"):
            MaintenancePurchaseService.add_line(
                purchase_order_id=order.id,
                tenant_id=sample_tenant.id,
                product_id=sample_product.id,
                quantity=Decimal("1"),
                unit_cost=Decimal("30"),
            )

    def test_an_empty_order_cannot_be_received(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = _purchase_order(db_session, sample_tenant, sample_user, sample_warehouse)
        db_session.flush()

        with pytest.raises(ValueError, match="بدون سطور"):
            MaintenancePurchaseService.receive_purchase_order(
                order.id,
                sample_tenant.id,
                received_by=sample_user.id,
            )
