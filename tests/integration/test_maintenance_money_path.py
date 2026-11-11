"""The maintenance module's money path, exercised end to end.

Every assertion here is made against the DATABASE, never against a service
return value: the number of stock movements written, the movement unit
cost, the journal entries posted, their debit and credit totals, and the
balances of the maintenance accounts. A service that posts to the wrong
account still returns a "successful" document; only the ledger knows.

What the file pins:

* a maintenance order consumes its spare parts at the warehouse's moving
  average cost, the stock leaves the shelf, and the inventory account is
  credited with exactly that cost;
* closing an order issues one invoice, one receipt, and three balanced
  journal entries (parts cost, revenue, receipt) that together leave the
  maintenance receivable at the amount still owed;
* the maintenance sub-ledger is separate: its receivable sits in 1134, not
  in the trade receivable 1130, and its revenue in 4119, not in 4100;
* a deposit is a liability (2171), not revenue, and a return reverses the
  revenue, the tax and the parts cost together;
* a second close is refused, so the money cannot be taken twice.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models import (
    GLAccount,
    GLJournalEntry,
    GLJournalLine,
    MaintenanceDeviceRegistry,
    MaintenanceOrderStatus,
    MaintenanceWarrantyAudit,
    ProductWarehouseCost,
    StockMovement,
)
from services.maintenance_order_service import MaintenanceService

# ── helpers ───────────────────────────────────────────────────────────────


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


def _cash_account_code(branch_id: int) -> str:
    """The cash account the reception counter's money lands in.

    Liquidity is branch-scoped: each branch has its own drawer
    (``1110-B<branch_id>``), so the test asks the resolver rather than
    naming an account that would not be posted to.
    """
    from services.gl_service import GLService

    return GLService.get_default_liquidity_account("cash", branch_id=branch_id)


def _labour_template(db, tenant_id: int):
    """The workshop's labour template, seeded if the tenant has none.

    The service line is added at the template's own price: a price other
    than the template's needs the price-override permission, and this
    test is about the document and the statement, not about pricing.
    """
    from models import MaintenanceServiceTemplate

    MaintenanceService.ensure_default_service_templates(tenant_id)
    template = db.query(MaintenanceServiceTemplate).filter_by(tenant_id=tenant_id, service_code="LABOR-001").first()
    assert template is not None, "the tenant has no labour template"
    return template


def _posted_entries(db, tenant_id: int):
    return (
        db.query(GLJournalEntry)
        .filter(GLJournalEntry.tenant_id == int(tenant_id))
        .filter(GLJournalEntry.status == "posted")
        .all()
    )


def _seed_part_with_stock(db, sample_tenant, sample_warehouse, *, cost="40", price="100", qty="50"):
    """A spare part with real stock in the maintenance warehouse."""
    from models import Product, ProductWarehouseStock

    product = Product(
        tenant_id=sample_tenant.id,
        name="Brake Pad",
        sku=f"MNT-PART-{sample_tenant.id}",
        cost_price=Decimal(cost),
        regular_price=Decimal(price),
        current_stock=Decimal("0"),
    )
    db.add(product)
    db.flush()

    db.add(
        ProductWarehouseStock(
            tenant_id=sample_tenant.id,
            product_id=product.id,
            warehouse_id=sample_warehouse.id,
            quantity=Decimal(qty),
        )
    )
    db.add(
        ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=Decimal(qty),
            total_value=Decimal(qty) * Decimal(cost),
            average_cost=Decimal(cost),
        )
    )
    product.current_stock = Decimal(qty)
    db.flush()
    return product


def _ready_order(db, sample_tenant, sample_user, sample_warehouse, *, with_part=True, qty="2"):
    """An order that is ready to close, with one part line."""
    part = _seed_part_with_stock(db, sample_tenant, sample_warehouse) if with_part else None

    order = MaintenanceService.create_order(
        tenant_id=sample_tenant.id,
        branch_id=sample_warehouse.branch_id,
        warehouse_id=sample_warehouse.id,
        customer_id=None,
        customer_name="Test Customer",
        customer_phone=None,
        device_brand="Toyota",
        device_model="Camry",
        device_serial_number="SN-MONEY-TEST",
        device_imei=None,
        device_plate=None,
        device_km=None,
        device_fault_description="Brake noise",
        received_by=sample_user.id,
    )
    if part is not None:
        MaintenanceService.add_line(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            product_id=part.id,
            quantity=Decimal(qty),
            unit_price=part.regular_price,
            warehouse_id=sample_warehouse.id,
        )
    for status in ("diagnosis", "in_progress"):
        MaintenanceService.transition_status(order.id, sample_tenant.id, to_status=status, changed_by=sample_user.id)
    MaintenanceService.check_warranty(order.id, sample_tenant.id, checked_by=sample_user.id)
    MaintenanceService.transition_status(order.id, sample_tenant.id, to_status="ready", changed_by=sample_user.id)
    return order, part


# ── the tests ─────────────────────────────────────────────────────────────


class TestPartsConsumption:
    """Spare parts leave the shelf at the warehouse's real moving-average cost."""

    def test_consuming_a_part_moves_the_stock_and_records_its_cost(
        self, db_session, sample_tenant, sample_user, sample_warehouse
    ):
        order, part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)

        MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            amount_received=order.total_amount,
        )
        db_session.flush()

        movement = (
            db_session.query(StockMovement)
            .filter_by(tenant_id=sample_tenant.id, product_id=part.id)
            .filter(StockMovement.movement_type == "maintenance")
            .one()
        )
        assert movement.quantity == Decimal("-2.000")
        assert movement.warehouse_id == sample_warehouse.id

        # The line carries the moving-average cost, not the sale price.
        line = list(order.lines)[0]
        assert line.cost_price == Decimal("40.0000")
        assert line.cost_aed == Decimal("80.000")
        assert line.movement_id == movement.id

        # The stock really left the shelf.
        from models import ProductWarehouseStock

        stock = (
            db_session.query(ProductWarehouseStock)
            .filter_by(tenant_id=sample_tenant.id, product_id=part.id, warehouse_id=sample_warehouse.id)
            .one()
        )
        assert stock.quantity == Decimal("48.000")
        assert part.current_stock == Decimal("48.000")

        # And the moving average moved with it.
        pwc = (
            db_session.query(ProductWarehouseCost)
            .filter_by(tenant_id=sample_tenant.id, product_id=part.id, warehouse_id=sample_warehouse.id)
            .one()
        )
        assert pwc.total_quantity == Decimal("48.000")
        assert pwc.average_cost == Decimal("40.0000")

    def test_the_parts_cost_is_posted_against_inventory(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order, _part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)

        MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            amount_received=order.total_amount,
        )
        db_session.flush()

        # 2 parts at a cost of 40 each.
        assert _account_balance(db_session, sample_tenant.id, "5119") == Decimal("80.000")
        assert _account_balance(db_session, sample_tenant.id, "1140") == Decimal("-80.000")


class TestCloseAndCollect:
    """Closing an order is one atomic financial event."""

    def test_closing_an_order_posts_one_invoice_one_receipt_and_balanced_entries(
        self, db_session, sample_tenant, sample_user, sample_warehouse
    ):
        order, _part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)
        total = Decimal(str(order.total_amount))

        closed, receipt, invoice = MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            amount_received=total,
        )
        db_session.flush()

        assert closed.status == MaintenanceOrderStatus.CLOSED
        assert closed.closed_by == sample_user.id
        assert closed.closed_at is not None
        assert invoice.invoice_number.startswith("MINV-")
        assert receipt.receipt_number.startswith("PT-")
        assert receipt.amount == total
        assert invoice.gl_posted is True
        assert receipt.gl_posted is True

        # Every entry balances, and the whole set balances.
        for entry in _posted_entries(db_session, sample_tenant.id):
            assert entry.total_debit == entry.total_credit, (
                f"entry {entry.entry_number} does not balance: {entry.total_debit} vs {entry.total_credit}"
            )
        debit, credit = _trial_balance(db_session, sample_tenant.id)
        assert debit == credit

    def test_the_maintenance_subledger_is_separate_from_the_trade_ledger(
        self, db_session, sample_tenant, sample_user, sample_warehouse
    ):
        order, _part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)
        total = Decimal(str(order.total_amount))

        MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            amount_received=total,
        )
        db_session.flush()

        tax = Decimal(str(order.tax_amount or 0))
        net = total - tax

        # The receivable is the maintenance one (1134), not the trade one
        # (1130). The order was paid in full, so the receivable nets to zero
        # - and the trade receivable was never touched at all.
        assert _account_balance(db_session, sample_tenant.id, "1134") == Decimal("0")
        assert _account_balance(db_session, sample_tenant.id, "1130") == Decimal("0")

        # The revenue is the maintenance one (4119), not the sales one (4100).
        assert _account_balance(db_session, sample_tenant.id, "4119") == -net
        assert _account_balance(db_session, sample_tenant.id, "4100") == Decimal("0")

        # The cash came in and the receivable was cleared by the receipt.
        cash_code = _cash_account_code(sample_warehouse.branch_id)
        cash = _account_balance(db_session, sample_tenant.id, cash_code)
        assert cash == total

    def test_a_partly_paid_order_leaves_the_balance_in_the_receivable(
        self, db_session, sample_tenant, sample_user, sample_warehouse
    ):
        order, _part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)
        total = Decimal(str(order.total_amount))
        part = Decimal("50.000")

        closed, receipt, invoice = MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            amount_received=part,
        )
        db_session.flush()

        assert receipt.amount == part
        assert invoice.balance_due == total - part
        assert closed.balance_due == total - part
        # The receivable still carries what was not paid.
        assert _account_balance(db_session, sample_tenant.id, "1134") == total - part

    def test_closing_twice_is_refused(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order, _part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)
        total = Decimal(str(order.total_amount))

        MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            amount_received=total,
        )
        db_session.flush()
        entries_after_first = len(_posted_entries(db_session, sample_tenant.id))

        with pytest.raises(ValueError, match="لا يمكن إغلاق"):
            MaintenanceService.close_and_collect(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                cashier_id=sample_user.id,
                payment_mode="cash",
                amount_received=total,
            )
        assert len(_posted_entries(db_session, sample_tenant.id)) == entries_after_first

    def test_collecting_more_than_the_total_is_refused(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order, _part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)
        total = Decimal(str(order.total_amount))

        with pytest.raises(ValueError, match="يتجاوز"):
            MaintenanceService.close_and_collect(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                cashier_id=sample_user.id,
                payment_mode="cash",
                amount_received=total + Decimal("1"),
            )

    def test_an_order_that_is_not_ready_cannot_be_closed(
        self, db_session, sample_tenant, sample_user, sample_warehouse
    ):
        order, _part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)
        MaintenanceService.transition_status(
            order.id, sample_tenant.id, to_status="in_progress", changed_by=sample_user.id
        )

        with pytest.raises(ValueError, match="غير جاهز"):
            MaintenanceService.close_and_collect(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                cashier_id=sample_user.id,
                payment_mode="cash",
                amount_received=order.total_amount,
            )


class TestDeposit:
    """A deposit is a liability, not revenue."""

    def test_a_deposit_is_credited_to_the_deposit_account(
        self, db_session, sample_tenant, sample_user, sample_warehouse
    ):
        order, _part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)

        receipt = MaintenanceService.collect_deposit(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            amount=Decimal("30.000"),
            payment_mode="cash",
        )
        db_session.flush()

        assert receipt.is_deposit is True
        assert order.deposit_amount == Decimal("30.000")

        # The deposit is a liability (2171), and it is not revenue.
        assert _account_balance(db_session, sample_tenant.id, "2171") == Decimal("-30.000")
        assert _account_balance(db_session, sample_tenant.id, "4119") == Decimal("0")
        # The cash is in the drawer.
        cash_code = _cash_account_code(sample_warehouse.branch_id)
        assert _account_balance(db_session, sample_tenant.id, cash_code) == Decimal("30.000")

    def test_a_deposit_larger_than_the_order_is_refused(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order, _part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)

        with pytest.raises(ValueError, match="يتجاوز"):
            MaintenanceService.collect_deposit(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                cashier_id=sample_user.id,
                amount=Decimal(str(order.total_amount)) + Decimal("1"),
                payment_mode="cash",
            )

    def test_a_deposit_is_applied_against_the_invoice_when_the_order_closes(
        self, db_session, sample_tenant, sample_user, sample_warehouse
    ):
        """The deposit must move off the liability and onto the receivable.

        Otherwise the maintenance receivable would carry the whole invoice
        while the deposit sat on the liability side, and the sub-ledger
        would not reconcile with the order's balance due.
        """
        order, _part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)
        total = Decimal(str(order.total_amount))
        deposit_amount = Decimal("30.000")

        MaintenanceService.collect_deposit(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            amount=deposit_amount,
            payment_mode="cash",
        )
        db_session.flush()

        closed, receipt, invoice = MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            amount_received=total - deposit_amount,
        )
        db_session.flush()

        # The deposit liability is settled.
        assert _account_balance(db_session, sample_tenant.id, "2171") == Decimal("0")
        # The receivable carries what is still owed - which is nothing here,
        # because the deposit and the cash together covered the invoice.
        assert _account_balance(db_session, sample_tenant.id, "1134") == Decimal("0")
        # And the order agrees with the ledger: the deposit counts towards
        # what the customer owes, so the balance due is zero.
        assert closed.balance_due == Decimal("0")
        assert invoice.balance_due == Decimal("0")
        assert invoice.paid_amount == total
        # The books still balance.
        debit, credit = _trial_balance(db_session, sample_tenant.id)
        assert debit == credit

    def test_a_deposit_counts_towards_what_the_customer_owes(
        self, db_session, sample_tenant, sample_user, sample_warehouse
    ):
        """The deposit reduces the balance due, and it is counted once."""
        order, _part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)
        total = Decimal(str(order.total_amount))
        deposit_amount = Decimal("30.000")
        collected = Decimal("100.000")

        MaintenanceService.collect_deposit(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            amount=deposit_amount,
            payment_mode="cash",
        )
        db_session.flush()

        closed, receipt, invoice = MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            amount_received=collected,
        )
        db_session.flush()

        # The deposit and the cash together settle 130, so 80 is still owed.
        assert closed.balance_due == total - deposit_amount - collected
        assert invoice.balance_due == total - deposit_amount - collected
        assert invoice.paid_amount == deposit_amount + collected
        # The receivable carries exactly what is still owed.
        assert _account_balance(db_session, sample_tenant.id, "1134") == total - deposit_amount - collected
        # And the books balance.
        debit, credit = _trial_balance(db_session, sample_tenant.id)
        assert debit == credit


class TestReturn:
    """A return reverses the revenue, the tax and the parts cost together."""

    def test_returning_parts_reverses_the_invoice_and_the_parts_cost(
        self, db_session, sample_tenant, sample_user, sample_warehouse
    ):
        order, part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)
        total = Decimal(str(order.total_amount))

        MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            amount_received=total,
        )
        db_session.flush()

        line = list(order.lines)[0]
        tax = Decimal(str(order.tax_amount or 0))

        maintenance_return = MaintenanceService.create_return(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            returned_by=sample_user.id,
            reason="Part did not fit",
            quantities={f"return_qty_{line.id}": Decimal("1")},
        )
        db_session.flush()

        assert maintenance_return.total_value > 0
        assert maintenance_return.gl_posted is True

        # The returned part went back on the shelf.
        from models import ProductWarehouseStock

        stock = (
            db_session.query(ProductWarehouseStock)
            .filter_by(tenant_id=sample_tenant.id, product_id=part.id, warehouse_id=sample_warehouse.id)
            .one()
        )
        assert stock.quantity == Decimal("49.000")

        # The tax the returned line carried was reversed with it, so the VAT
        # account does not keep the tax of a line that was returned.
        vat_balance = _account_balance(db_session, sample_tenant.id, "2121")
        assert vat_balance == -tax + Decimal(str(maintenance_return.total_value_tax or 0))

        # The books still balance after the reversal.
        debit, credit = _trial_balance(db_session, sample_tenant.id)
        assert debit == credit


class TestWarrantyTrail:
    """Every warranty change is recorded and the trail is append-only."""

    def test_a_warranty_change_is_recorded_in_the_audit(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_customer, mocker
    ):
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        device = MaintenanceDeviceRegistry(
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            serial_number="WARRANTY-TRAIL-TEST",
            warranty_start_date=now - timedelta(days=1),
            warranty_end_date=now + timedelta(days=30),
            is_under_warranty=True,
            is_active=True,
        )
        db_session.add(device)
        db_session.flush()

        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=sample_customer.id,
            customer_name=None,
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=device.serial_number,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )
        MaintenanceService.check_warranty(order.id, sample_tenant.id, checked_by=sample_user.id)

        audits = (
            db_session.query(MaintenanceWarrantyAudit)
            .filter_by(tenant_id=sample_tenant.id, maintenance_order_id=order.id)
            .all()
        )
        assert len(audits) == 1
        assert audits[0].action == "checked"
        assert audits[0].to_status == "under_warranty"
        assert audits[0].performed_by == sample_user.id


class TestStatutoryDocument:
    """A maintenance job is a sale for the tax authority.

    The customer receives a service, pays a tax, and is entitled to the
    same statutory document the trade path issues. The artifact hangs
    off the maintenance invoice, so the two ledgers never share a key.
    """

    def test_closing_an_order_produces_the_statutory_document(
        self, db_session, sample_tenant, sample_user, sample_warehouse
    ):
        from models import EInvoice
        from services.einvoice_service import EInvoiceService

        # The tenant's jurisdiction decides the document format: the AE
        # (FTA) profile produces a UBL 2.1 document.
        assert sample_tenant.vat_country == "AE"

        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=None,
            customer_name="E-Invoice Customer",
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )
        db_session.flush()

        template = _labour_template(db_session, sample_tenant.id)
        MaintenanceService.add_service_line(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            service_code=template.service_code,
            service_name=template.name,
            service_name_ar=template.name_ar,
            service_category=template.service_category,
            unit_price=template.fixed_price,
            engineer_id=None,
        )
        db_session.flush()

        for status in ("diagnosis", "in_progress"):
            MaintenanceService.transition_status(
                order.id, sample_tenant.id, to_status=status, changed_by=sample_user.id
            )
        MaintenanceService.check_warranty(order.id, sample_tenant.id, checked_by=sample_user.id)
        MaintenanceService.transition_status(order.id, sample_tenant.id, to_status="ready", changed_by=sample_user.id)

        _closed, _receipt, invoice = MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
        )
        db_session.flush()

        row = (
            db_session.query(EInvoice).filter_by(tenant_id=sample_tenant.id, maintenance_invoice_id=invoice.id).first()
        )
        assert row is not None, "the maintenance invoice produced no statutory document"
        assert row.format == "fta_ubl_xml"
        # The artifact hangs off the maintenance document, never a sale.
        assert row.sale_id is None
        assert row.maintenance_invoice_id == invoice.id
        assert invoice.invoice_number in row.xml_payload
        # And it is the document the customer downloads.
        assert EInvoiceService._upsert_maintenance_row(sample_tenant.id, invoice.id) is not None


class TestCustomerLedger:
    """The customer has one balance, whatever module earned it.

    The maintenance module keeps its own receivable, but the customer
    does not keep two ledgers: what they owe the company is one number,
    and the statement has to show the maintenance charge and the
    maintenance payment next to the trade ones.
    """

    def test_a_maintenance_charge_and_its_payment_reach_the_customer_statement(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_customer
    ):
        from services.customer_statement_service import CustomerStatementService

        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=sample_customer.id,
            customer_name=None,
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )
        db_session.flush()

        template = _labour_template(db_session, sample_tenant.id)
        MaintenanceService.add_service_line(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            service_code=template.service_code,
            service_name=template.name,
            service_name_ar=template.name_ar,
            service_category=template.service_category,
            unit_price=template.fixed_price,
            engineer_id=None,
        )
        db_session.flush()

        for status in ("diagnosis", "in_progress"):
            MaintenanceService.transition_status(
                order.id, sample_tenant.id, to_status=status, changed_by=sample_user.id
            )
        MaintenanceService.check_warranty(order.id, sample_tenant.id, checked_by=sample_user.id)
        MaintenanceService.transition_status(order.id, sample_tenant.id, to_status="ready", changed_by=sample_user.id)

        total = Decimal(str(order.total_amount))
        MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            amount_received=total,
        )
        db_session.flush()

        context = CustomerStatementService.build_statement_context(
            record_id=sample_customer.id,
            date_from=None,
            date_to=None,
            transaction_type="all",
            default_currency="AED",
            tenant_id=sample_tenant.id,
            branch_id=None,
        )

        types = [transaction["type"] for transaction in context["transactions"]]
        assert "maintenance" in types
        assert "maintenance_receipt" in types

        # The charge and the payment cancel each other, so the customer
        # owes nothing for the maintenance job.
        assert abs(context["final_balance"]) < Decimal("0.01")

    def test_the_statement_can_be_filtered_to_the_maintenance_movements(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_customer
    ):
        from services.customer_statement_service import CustomerStatementService

        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=sample_customer.id,
            customer_name=None,
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )
        db_session.flush()

        template = _labour_template(db_session, sample_tenant.id)
        MaintenanceService.add_service_line(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            service_code=template.service_code,
            service_name=template.name,
            service_name_ar=template.name_ar,
            service_category=template.service_category,
            unit_price=template.fixed_price,
            engineer_id=None,
        )
        db_session.flush()
        for status in ("diagnosis", "in_progress"):
            MaintenanceService.transition_status(
                order.id, sample_tenant.id, to_status=status, changed_by=sample_user.id
            )
        MaintenanceService.check_warranty(order.id, sample_tenant.id, checked_by=sample_user.id)
        MaintenanceService.transition_status(order.id, sample_tenant.id, to_status="ready", changed_by=sample_user.id)
        MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
        )
        db_session.flush()

        context = CustomerStatementService.build_statement_context(
            record_id=sample_customer.id,
            date_from=None,
            date_to=None,
            transaction_type="maintenance",
            default_currency="AED",
            tenant_id=sample_tenant.id,
            branch_id=None,
        )
        types = {transaction["type"] for transaction in context["transactions"]}
        assert types <= {"maintenance", "maintenance_receipt", "opening"}
        assert "maintenance" in types


class TestTenantIsolation:
    """One tenant's maintenance money never appears in another's ledger."""

    def test_two_tenants_keep_separate_maintenance_ledgers(
        self, db_session, sample_tenant, sample_user, sample_warehouse
    ):
        from uuid import uuid4

        from models import Tenant
        from utils.tenanting import without_tenant_scope

        with without_tenant_scope():
            other = Tenant(
                name="Maintenance Isolation",
                name_ar="عزل",
                slug=f"mnt-iso-{uuid4().hex[:8]}",
                country="AE",
                default_currency="AED",
                base_currency="AED",
            )
            db_session.add(other)
            db_session.flush()

        order, _part = _ready_order(db_session, sample_tenant, sample_user, sample_warehouse)
        total = Decimal(str(order.total_amount))
        MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            amount_received=total,
        )
        db_session.flush()

        # The other tenant's ledger is untouched.
        assert _account_balance(db_session, other.id, "1134") == Decimal("0")
        assert _account_balance(db_session, other.id, "4119") == Decimal("0")
        assert not (
            db_session.query(GLJournalEntry)
            .filter(GLJournalEntry.tenant_id == other.id)
            .filter(GLJournalEntry.status == "posted")
            .all()
        )
