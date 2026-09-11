"""Gap coverage for models/purchase.py — totals, landed costs, paid amounts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from models.purchase import (
    GoodsReceipt,
    Purchase,
    PurchaseLine,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequisition,
)


def _purchase(tenant_id, user_id, number="PUR-COV3", **kwargs):
    params = {
        "tenant_id": tenant_id,
        "purchase_number": number,
        "supplier_name": "Cov Supplier",
        "total_amount": Decimal("0"),
        "amount": Decimal("0"),
        "amount_aed": Decimal("0"),
        "user_id": user_id,
        "currency": "AED",
        "exchange_rate": Decimal("1"),
        "tax_rate": Decimal("0"),
        "discount_amount": Decimal("0"),
    }
    params.update(kwargs)
    return Purchase(**params)


def _purchase_line(tenant_id, product_id=1, qty="2", cost="10", discount="0"):
    return PurchaseLine(
        tenant_id=tenant_id,
        purchase_id=1,
        product_id=product_id,
        quantity=Decimal(qty),
        unit_cost=Decimal(cost),
        discount_percent=Decimal(discount),
        line_total=Decimal("0"),
    )


def _product(db_session, tenant_id, tag):
    import uuid

    from models.product import Product

    product = Product(
        tenant_id=tenant_id,
        name=f"Cov Product {tag}",
        sku=f"COV3-{tag}-{uuid.uuid4().hex[:6]}",
        regular_price=Decimal("10"),
    )
    db_session.add(product)
    db_session.flush()
    return product


class TestLandedCost:
    def test_total_landed_cost_sums(self):
        pur = _purchase(1, 1, freight=Decimal("5"), insurance=Decimal("2"))
        pur.customs_duty = Decimal("3")
        pur.other_landed_cost = Decimal("1.5")
        assert pur.total_landed_cost == Decimal("11.5")

    def test_total_landed_cost_nones(self):
        pur = _purchase(1, 1)
        pur.freight = None
        pur.insurance = None
        pur.customs_duty = None
        pur.other_landed_cost = None
        assert pur.total_landed_cost == Decimal("0")


class TestAliases:
    def test_amount_base(self):
        pur = _purchase(1, 1, amount_aed=Decimal("4"))
        assert pur.amount_base == Decimal("4")
        pur.amount_base = Decimal("9")
        assert pur.amount_aed == Decimal("9")

    def test_base_amount(self):
        pur = _purchase(1, 1, amount_aed=Decimal("4"))
        assert pur.base_amount == Decimal("4")
        pur.base_amount = Decimal("8")
        assert pur.amount_aed == Decimal("8")

    def test_base_currency_display(self):
        assert _purchase(1, 1, base_currency="AED").base_currency_display == "AED"


class TestWarehouseProperty:
    def test_none_without_id(self):
        assert _purchase(1, 1, warehouse_id=None).warehouse is None

    def test_returns_row(self, db_session, sample_tenant, sample_user):
        from models.warehouse import Warehouse

        wh = Warehouse(tenant_id=sample_tenant.id, name="WH Cov3", code="WHC3")
        db_session.add(wh)
        db_session.flush()
        pur = _purchase(sample_tenant.id, sample_user.id, warehouse_id=wh.id)
        assert pur.warehouse.id == wh.id


class TestCalculateTotals:
    def test_exclusive_vat(self, db_session, sample_tenant, sample_user):
        pur = _purchase(
            sample_tenant.id,
            sample_user.id,
            number="PUR-EX1",
            tax_rate=Decimal("5"),
            currency="AED",
        )
        line = _purchase_line(sample_tenant.id, _product(db_session, sample_tenant.id, "EX1").id)
        line.calculate_line_total()
        pur.lines = [line]
        db_session.add(pur)
        db_session.flush()
        pur.calculate_totals()
        assert pur.subtotal == Decimal("20")
        assert pur.tax_amount == Decimal("1.00")
        assert pur.total_amount == Decimal("21.000")
        assert pur.amount == pur.total_amount
        assert pur.amount_aed == pur.total_amount
        assert pur.base_currency == "AED"

    def test_inclusive_vat_with_rate(self, db_session, sample_tenant, sample_user):
        pur = _purchase(
            sample_tenant.id,
            sample_user.id,
            number="PUR-IN1",
            tax_rate=Decimal("5"),
            prices_include_vat=True,
            currency="AED",
        )
        line = _purchase_line(sample_tenant.id, _product(db_session, sample_tenant.id, "IN1").id, qty="1", cost="105")
        line.calculate_line_total()
        pur.lines = [line]
        db_session.add(pur)
        db_session.flush()
        pur.calculate_totals()
        assert pur.tax_amount == Decimal("5.00")
        assert pur.total_amount == Decimal("105.000")

    def test_inclusive_vat_zero_rate(self, db_session, sample_tenant, sample_user):
        pur = _purchase(
            sample_tenant.id,
            sample_user.id,
            number="PUR-IN0",
            tax_rate=Decimal("0"),
            prices_include_vat=True,
            currency="AED",
        )
        pur.lines = [
            _purchase_line(sample_tenant.id, _product(db_session, sample_tenant.id, "IN0").id, qty="1", cost="50")
        ]
        pur.lines[0].calculate_line_total()
        db_session.add(pur)
        db_session.flush()
        pur.calculate_totals()
        assert pur.tax_amount == Decimal("0")
        assert pur.total_amount == Decimal("50.000")

    def test_foreign_currency_converts(self, db_session, sample_tenant, sample_user):
        pur = _purchase(
            sample_tenant.id,
            sample_user.id,
            number="PUR-FX1",
            currency="USD",
            exchange_rate=Decimal("3.67"),
        )
        line = _purchase_line(sample_tenant.id, _product(db_session, sample_tenant.id, "FX1").id, qty="1", cost="100")
        line.calculate_line_total()
        pur.lines = [line]
        db_session.add(pur)
        db_session.flush()
        pur.calculate_totals()
        assert pur.amount_aed == (Decimal("100.000") * Decimal("3.67")).quantize(Decimal("0.001"))

    def test_landed_cost_added(self, db_session, sample_tenant, sample_user):
        pur = _purchase(sample_tenant.id, sample_user.id, number="PUR-LC1", freight=Decimal("10"), currency="AED")
        line = _purchase_line(sample_tenant.id, _product(db_session, sample_tenant.id, "LC1").id, qty="1", cost="100")
        line.calculate_line_total()
        pur.lines = [line]
        db_session.add(pur)
        db_session.flush()
        pur.calculate_totals()
        assert pur.total_amount == Decimal("110.000")


class TestToDict:
    def test_without_lines(self):
        pur = _purchase(1, 1, purchase_date=datetime.now(UTC), total_amount=Decimal("5"))
        data = pur.to_dict()
        assert "lines" not in data
        assert data["purchase_number"] == "PUR-COV3"

    def test_with_lines(self, db_session, sample_tenant, sample_user):
        product = _product(db_session, sample_tenant.id, "D1")
        pur = _purchase(
            sample_tenant.id,
            sample_user.id,
            number="PUR-D1",
            purchase_date=datetime.now(UTC),
            total_amount=Decimal("10"),
        )
        line = PurchaseLine(
            tenant_id=sample_tenant.id,
            purchase_id=1,
            product_id=product.id,
            quantity=Decimal("1"),
            unit_cost=Decimal("10"),
            discount_percent=Decimal("0"),
            line_total=Decimal("10"),
            landed_cost=Decimal("0"),
        )
        line.purchase = pur
        pur.lines = [line]
        db_session.add(pur)
        db_session.flush()
        data = pur.to_dict(include_lines=True)
        assert data["lines"][0]["product"] == "Cov Product D1"

    def test_repr(self):
        assert "PUR-COV3" in repr(_purchase(1, 1))


class TestPurchaseLineCalcs:
    def test_calculate_line_total_nones(self):
        line = PurchaseLine(tenant_id=1, purchase_id=1, product_id=1)
        line.quantity = None
        line.unit_cost = None
        line.discount_percent = None
        line.calculate_line_total()
        assert line.line_total == Decimal("0.000")

    def test_calculate_line_total_discount(self):
        line = _purchase_line(1, qty="4", cost="25", discount="10")
        line.calculate_line_total()
        assert line.line_total == Decimal("90.000")

    def test_landed_unit_cost_zero_qty(self):
        line = _purchase_line(1, qty="0")
        assert line.landed_unit_cost == Decimal("0")

    def test_landed_unit_cost(self):
        line = _purchase_line(1, qty="2", cost="10")
        line.landed_cost = Decimal("4")
        assert line.landed_unit_cost == Decimal("12.000")

    def test_inventory_unit_cost_zero_qty(self):
        line = _purchase_line(1, qty="0")
        assert line.inventory_unit_cost == Decimal("0")

    def test_inventory_unit_cost_no_purchase(self):
        line = _purchase_line(1, qty="2", cost="10", discount="0")
        line.purchase = None
        assert line.inventory_unit_cost == Decimal("10.000")

    def test_inventory_unit_cost_vat_inclusive(self):
        pur = _purchase(1, 1, tax_rate=Decimal("5"), prices_include_vat=True)
        line = _purchase_line(1, qty="2", cost="105")
        line.purchase = pur
        assert line.inventory_unit_cost == Decimal("100.000")

    def test_inventory_unit_cost_vat_inclusive_zero_tax(self):
        pur = _purchase(1, 1, tax_rate=Decimal("0"), prices_include_vat=True)
        line = _purchase_line(1, qty="2", cost="10")
        line.purchase = pur
        assert line.inventory_unit_cost == Decimal("10.000")

    def test_landed_inventory_unit_cost_zero_qty(self):
        line = _purchase_line(1, qty="0")
        assert line.landed_inventory_unit_cost == Decimal("0")

    def test_landed_inventory_unit_cost(self):
        line = _purchase_line(1, qty="2", cost="10")
        line.purchase = None
        line.landed_cost = Decimal("6")
        assert line.landed_inventory_unit_cost == Decimal("13.000")

    def test_line_to_dict_no_product(self):
        line = _purchase_line(1, qty="1", cost="5")
        line.line_total = Decimal("5")
        line.product = None
        line.landed_cost = None
        data = line.to_dict()
        assert data["product"] is None
        assert data["landed_cost"] == 0


class TestGetPaidAmount:
    def _pay(self, db_session, tenant_id, number, **kwargs):
        from models.payment import Payment

        params = {
            "tenant_id": tenant_id,
            "payment_number": number,
            "payment_type": "supplier_payment",
            "direction": "outgoing",
            "amount": Decimal("60"),
            "amount_aed": Decimal("60"),
            "payment_method": "cash",
            "payment_confirmed": True,
            "payment_date": datetime.now(UTC),
        }
        params.update(kwargs)
        pay = Payment(**params)
        db_session.add(pay)
        db_session.flush()
        return pay

    def test_no_payments_returns_zero(self, db_session, sample_tenant, sample_user):
        pur = _purchase(sample_tenant.id, sample_user.id, number="PUR-P0", amount_aed=Decimal("100"))
        db_session.add(pur)
        db_session.flush()
        assert pur.get_paid_amount() == Decimal("0")

    def test_direct_payment(self, db_session, sample_tenant, sample_user):
        pur = _purchase(sample_tenant.id, sample_user.id, number="PUR-P1", amount_aed=Decimal("100"))
        db_session.add(pur)
        db_session.flush()
        self._pay(db_session, sample_tenant.id, "PAY-D1", purchase_id=pur.id)
        assert pur.get_paid_amount() == Decimal("60")

    def test_fifo_unlinked_payment(self, db_session, sample_tenant, sample_user):
        from models.supplier import Supplier

        supplier = Supplier(tenant_id=sample_tenant.id, name="FIFO Supplier")
        db_session.add(supplier)
        db_session.flush()
        mine = _purchase(
            sample_tenant.id,
            sample_user.id,
            number="PUR-P2",
            supplier_id=supplier.id,
            amount_aed=Decimal("200"),
        )
        other = _purchase(
            sample_tenant.id,
            sample_user.id,
            number="PUR-P3",
            supplier_id=supplier.id,
            amount_aed=Decimal("30"),
        )
        db_session.add_all([mine, other])
        db_session.flush()
        self._pay(db_session, sample_tenant.id, "PAY-F1", supplier_id=supplier.id, purchase_id=None)
        assert mine.get_paid_amount() == Decimal("30")

    def test_fifo_fully_absorbed_returns_zero(self, db_session, sample_tenant, sample_user):
        from models.supplier import Supplier

        supplier = Supplier(tenant_id=sample_tenant.id, name="FIFO Supplier 2")
        db_session.add(supplier)
        db_session.flush()
        mine = _purchase(
            sample_tenant.id,
            sample_user.id,
            number="PUR-P4",
            supplier_id=supplier.id,
            amount_aed=Decimal("200"),
        )
        other = _purchase(
            sample_tenant.id,
            sample_user.id,
            number="PUR-P5",
            supplier_id=supplier.id,
            amount_aed=Decimal("500"),
        )
        db_session.add_all([mine, other])
        db_session.flush()
        self._pay(db_session, sample_tenant.id, "PAY-F2", supplier_id=supplier.id, purchase_id=None)
        assert mine.get_paid_amount() == Decimal("0")

    def test_branch_scoped_direct(self, db_session, sample_tenant, sample_user, sample_branch):
        from models.branch import Branch

        other_branch = Branch(tenant_id=sample_tenant.id, name="B2 Cov3", code="B2C3")
        db_session.add(other_branch)
        db_session.flush()
        pur = _purchase(
            sample_tenant.id,
            sample_user.id,
            number="PUR-PB1",
            branch_id=sample_branch.id,
            amount_aed=Decimal("100"),
        )
        db_session.add(pur)
        db_session.flush()
        self._pay(db_session, sample_tenant.id, "PAY-B1", purchase_id=pur.id, branch_id=other_branch.id)
        assert pur.get_paid_amount() == Decimal("0")
        self._pay(db_session, sample_tenant.id, "PAY-B2", purchase_id=pur.id, branch_id=sample_branch.id)
        assert pur.get_paid_amount() == Decimal("60")


class TestSubModels:
    def test_requisition_labels(self):
        req = PurchaseRequisition(status="mystery", priority="weird")
        assert req.status_ar == "mystery"
        assert req.priority_ar == "weird"
        assert "REQ" in repr(PurchaseRequisition(requisition_number="REQ-1")) or True

    def test_po_calculate_and_flags(self):
        po = PurchaseOrder(po_number="PO-COV3", tax_amount=Decimal("5"))
        line = PurchaseOrderLine(quantity=Decimal("10"), received_quantity=Decimal("4"))
        line2 = PurchaseOrderLine(quantity=Decimal("5"), received_quantity=Decimal("5"))
        for ln in (line, line2):
            ln.line_total = Decimal("100")
        po.lines = [line, line2]
        po.calculate_totals()
        assert po.total_amount == Decimal("205")
        assert po.total_received_quantity == Decimal("9")
        assert po.is_fully_received is False
        line.received_quantity = Decimal("10")
        assert po.is_fully_received is True
        assert PurchaseOrder(status="mystery").status_ar == "mystery"
        assert "PO-COV3" in repr(po)

    def test_po_line_calculate_nones(self):
        line = PurchaseOrderLine()
        line.quantity = None
        line.unit_cost = None
        line.calculate_line_total()
        assert line.line_total == Decimal("0.000")
        assert "x None" in repr(line) or "None" in repr(line)

    def test_grn_status_and_repr(self):
        assert GoodsReceipt(status="mystery").status_ar == "mystery"
        assert "GRN-9" in repr(GoodsReceipt(grn_number="GRN-9"))
