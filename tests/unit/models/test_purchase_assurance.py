from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from models.purchase import PurchaseLine


class TestPurchaseModel:
    def test_repr(self, sample_purchase):
        assert "PUR-TEST-001" in repr(sample_purchase)

    def test_warehouse_property_with_id(
        self, sample_purchase, sample_warehouse, db_session
    ):
        sample_purchase.warehouse_id = sample_warehouse.id
        db_session.flush()
        wh = sample_purchase.warehouse
        assert wh is not None
        assert wh.id == sample_warehouse.id

    def test_warehouse_property_without_id(self, sample_purchase):
        sample_purchase.warehouse_id = None
        assert sample_purchase.warehouse is None

    def test_amount_base_alias(self, sample_purchase):
        sample_purchase.amount_base = Decimal("200.000")
        assert sample_purchase.amount_aed == Decimal("200.000")
        assert sample_purchase.amount_base == Decimal("200.000")

    def test_base_amount_alias(self, sample_purchase):
        sample_purchase.base_amount = Decimal("300.000")
        assert sample_purchase.amount_aed == Decimal("300.000")

    def test_total_landed_cost(self, sample_purchase):
        sample_purchase.freight = Decimal("10")
        sample_purchase.insurance = Decimal("5")
        sample_purchase.customs_duty = Decimal("3")
        sample_purchase.other_landed_cost = Decimal("2")
        assert sample_purchase.total_landed_cost == Decimal("20")

    def test_to_dict(self, sample_purchase):
        data = sample_purchase.to_dict()
        assert data["purchase_number"] == "PUR-TEST-001"
        assert "total_amount" in data

    def test_to_dict_with_lines(self, sample_purchase, sample_product, db_session):
        line = PurchaseLine(
            tenant_id=sample_purchase.tenant_id,
            purchase_id=sample_purchase.id,
            product_id=sample_product.id,
            quantity=Decimal("2"),
            unit_cost=Decimal("10"),
            line_total=Decimal("20"),
        )
        db_session.add(line)
        db_session.commit()
        data = sample_purchase.to_dict(include_lines=True)
        assert len(data["lines"]) == 1


class TestPurchaseGetPaidAmount:
    def test_direct_payment(self, db_session, sample_purchase, mocker):
        mocker.patch(
            "models.purchase.db.session.query",
        ).return_value.filter.return_value.scalar.return_value = Decimal("40")
        paid = sample_purchase.get_paid_amount(as_of_date=date(2030, 1, 1))
        assert paid == Decimal("40")

    def test_fifo_allocation(self, db_session, sample_purchase, mocker):
        query = mocker.patch("models.purchase.db.session.query")
        direct_q = MagicMock()
        direct_q.filter.return_value.scalar.return_value = None
        fifo_q = MagicMock()
        fifo_q.filter.return_value.scalar.return_value = Decimal("200")
        other_purchase = SimpleNamespace(amount_aed=Decimal("50"))
        purchase_q = MagicMock()
        purchase_q.filter.return_value.all.return_value = [other_purchase]
        query.side_effect = [direct_q, fifo_q]
        mocker.patch("models.Purchase.query", purchase_q)
        sample_purchase.amount_aed = Decimal("105")
        paid = sample_purchase.get_paid_amount(as_of_date=date(2030, 1, 1))
        assert paid == Decimal("105")

    def test_fifo_zero_when_other_total_covers_payments(
        self, db_session, sample_purchase, mocker
    ):
        query = mocker.patch("models.purchase.db.session.query")
        direct_q = MagicMock()
        direct_q.filter.return_value.scalar.return_value = None
        fifo_q = MagicMock()
        fifo_q.filter.return_value.scalar.return_value = Decimal("100")
        other_purchase = SimpleNamespace(amount_aed=Decimal("200"))
        purchase_q = MagicMock()
        purchase_q.filter.return_value.all.return_value = [other_purchase]
        query.side_effect = [direct_q, fifo_q]
        mocker.patch("models.Purchase.query", purchase_q)
        assert sample_purchase.get_paid_amount(as_of_date=date(2030, 1, 1)) == Decimal(
            "0"
        )

    def test_no_payments_returns_zero(self, db_session, sample_purchase, mocker):
        query = mocker.patch("models.purchase.db.session.query")
        direct_q = MagicMock()
        direct_q.filter.return_value.scalar.return_value = None
        fifo_q = MagicMock()
        fifo_q.filter.return_value.scalar.return_value = None
        query.side_effect = [direct_q, fifo_q]
        assert sample_purchase.get_paid_amount() == Decimal("0")

    def test_base_amount_getter(self, sample_purchase):
        assert sample_purchase.base_amount == sample_purchase.amount_aed

    def test_fifo_with_branch_filters(
        self, db_session, sample_purchase, sample_branch, mocker
    ):
        sample_purchase.branch_id = sample_branch.id
        query = mocker.patch("models.purchase.db.session.query")
        direct_q = MagicMock()
        direct_q.filter.return_value = direct_q
        direct_q.scalar.return_value = None
        fifo_q = MagicMock()
        fifo_q.filter.return_value = fifo_q
        fifo_q.scalar.return_value = Decimal("150")
        purchase_q = MagicMock()
        purchase_q.filter.return_value = purchase_q
        purchase_q.all.return_value = [SimpleNamespace(amount_aed=Decimal("30"))]
        query.side_effect = [direct_q, fifo_q]
        mocker.patch("models.Purchase.query", purchase_q)
        sample_purchase.amount_aed = Decimal("80")
        paid = sample_purchase.get_paid_amount(as_of_date=date(2030, 1, 1))
        assert paid == Decimal("80")
        sample_purchase.branch_id = sample_branch.id
        query = mocker.patch("models.purchase.db.session.query")
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.scalar.return_value = Decimal("10")
        query.return_value = chain
        paid = sample_purchase.get_paid_amount(as_of_date=date(2030, 1, 1))
        assert paid == Decimal("10")
        assert chain.filter.call_count >= 1


class TestPurchaseCalculateTotals:
    @staticmethod
    def _purchase_with_line(
        sample_purchase, sample_product, _db_session, **line_kwargs
    ):
        line = PurchaseLine(
            tenant_id=sample_purchase.tenant_id,
            purchase_id=sample_purchase.id,
            product_id=sample_product.id,
            quantity=Decimal("10"),
            unit_cost=Decimal("10"),
            line_total=Decimal("100"),
            **line_kwargs,
        )
        sample_purchase.lines = [line]
        return sample_purchase

    def test_calculate_totals_vat_exclusive(
        self, sample_purchase, sample_product, db_session
    ):
        p = self._purchase_with_line(sample_purchase, sample_product, db_session)
        p.tax_rate = Decimal("5")
        p.discount_amount = Decimal("10")
        p.freight = Decimal("5")
        p.calculate_totals()
        assert p.taxable_amount == Decimal("90")
        assert p.tax_amount == Decimal("4.50")
        assert p.total_amount == Decimal("99.500")
        assert p.amount_aed == Decimal("99.500")

    def test_calculate_totals_vat_inclusive(
        self, sample_purchase, sample_product, db_session
    ):
        p = self._purchase_with_line(sample_purchase, sample_product, db_session)
        p.prices_include_vat = True
        p.tax_rate = Decimal("5")
        p.discount_amount = Decimal("0")
        p.calculate_totals()
        assert p.tax_amount > Decimal("0")
        assert p.total_amount == Decimal("100.000")

    def test_calculate_totals_zero_tax_rate_inclusive(
        self, sample_purchase, sample_product, db_session
    ):
        p = self._purchase_with_line(sample_purchase, sample_product, db_session)
        p.prices_include_vat = True
        p.tax_rate = Decimal("0")
        p.calculate_totals()
        assert p.tax_amount == Decimal("0")


class TestPurchaseLine:
    def test_repr(self, sample_product):
        line = PurchaseLine(
            tenant_id=1,
            purchase_id=1,
            product_id=sample_product.id,
            quantity=Decimal("1"),
            unit_cost=Decimal("1"),
            line_total=Decimal("1"),
        )
        assert str(sample_product.id) in repr(line)

    def test_calculate_line_total_with_discount(self):
        line = PurchaseLine(
            tenant_id=1,
            purchase_id=1,
            product_id=1,
            quantity=Decimal("2"),
            unit_cost=Decimal("50"),
            discount_percent=Decimal("10"),
            line_total=Decimal("0"),
        )
        line.calculate_line_total()
        assert line.line_total == Decimal("90.000")

    def test_landed_unit_cost_zero_qty(self):
        line = PurchaseLine(
            tenant_id=1,
            purchase_id=1,
            product_id=1,
            quantity=Decimal("0"),
            unit_cost=Decimal("10"),
            line_total=Decimal("0"),
        )
        assert line.landed_unit_cost == Decimal("0")

    def test_landed_unit_cost_with_landed(self):
        line = PurchaseLine(
            tenant_id=1,
            purchase_id=1,
            product_id=1,
            quantity=Decimal("2"),
            unit_cost=Decimal("10"),
            line_total=Decimal("20"),
            landed_cost=Decimal("4"),
        )
        assert line.landed_unit_cost == Decimal("12.000")

    def test_inventory_unit_cost_vat_exclusive(self):
        purchase = MagicMock(prices_include_vat=False, tax_rate=Decimal("5"))
        line = PurchaseLine(
            tenant_id=1,
            purchase_id=1,
            product_id=1,
            quantity=Decimal("2"),
            unit_cost=Decimal("10"),
            discount_percent=Decimal("0"),
            line_total=Decimal("20"),
        )
        line.purchase = purchase
        assert line.inventory_unit_cost == Decimal("10.000")

    def test_inventory_unit_cost_vat_inclusive(self):
        purchase = MagicMock(prices_include_vat=True, tax_rate=Decimal("5"))
        line = PurchaseLine(
            tenant_id=1,
            purchase_id=1,
            product_id=1,
            quantity=Decimal("2"),
            unit_cost=Decimal("10.50"),
            discount_percent=Decimal("0"),
            line_total=Decimal("21"),
        )
        line.purchase = purchase
        assert line.inventory_unit_cost > Decimal("0")

    def test_inventory_unit_cost_zero_qty(self):
        line = PurchaseLine(
            tenant_id=1,
            purchase_id=1,
            product_id=1,
            quantity=Decimal("0"),
            unit_cost=Decimal("10"),
            line_total=Decimal("0"),
        )
        assert line.inventory_unit_cost == Decimal("0")

    def test_landed_inventory_unit_cost_zero_qty(self):
        line = PurchaseLine(
            tenant_id=1,
            purchase_id=1,
            product_id=1,
            quantity=Decimal("0"),
            unit_cost=Decimal("10"),
            line_total=Decimal("0"),
        )
        assert line.landed_inventory_unit_cost == Decimal("0")

    def test_landed_inventory_unit_cost(self):
        purchase = MagicMock(prices_include_vat=False, tax_rate=Decimal("0"))
        line = PurchaseLine(
            tenant_id=1,
            purchase_id=1,
            product_id=1,
            quantity=Decimal("2"),
            unit_cost=Decimal("10"),
            discount_percent=Decimal("0"),
            line_total=Decimal("20"),
            landed_cost=Decimal("4"),
        )
        line.purchase = purchase
        assert line.landed_inventory_unit_cost == Decimal("12.000")

    def test_branch_filter_applied(
        self, db_session, sample_purchase, sample_branch, mocker
    ):
        sample_purchase.branch_id = sample_branch.id
        query = mocker.patch("models.purchase.db.session.query")
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.scalar.return_value = Decimal("10")
        query.return_value = chain
        paid = sample_purchase.get_paid_amount(as_of_date=date(2030, 1, 1))
        assert paid == Decimal("10")
        assert chain.filter.call_count >= 1

    def test_to_dict(self, sample_product):
        line = PurchaseLine(
            tenant_id=1,
            purchase_id=1,
            product_id=sample_product.id,
            quantity=Decimal("3"),
            unit_cost=Decimal("5"),
            discount_percent=Decimal("0"),
            line_total=Decimal("15"),
            landed_cost=Decimal("1.5"),
        )
        line.product = sample_product
        data = line.to_dict()
        assert data["quantity"] == 3.0
        assert data["landed_unit_cost"] > 0
