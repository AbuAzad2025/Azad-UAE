"""Field-sales shipment model tests — pre-invoice van shipment + partial invoicing."""

from __future__ import annotations

from decimal import Decimal

import pytest

from models.shipment import Shipment, ShipmentLine


class TestShipmentSourceType:
    def test_valid_source_types(self):
        for st in ("sale", "purchase_return", "field_sale", "delivery"):
            s = Shipment(source_type=st, source_id=0)
            assert s.source_type == st

    def test_invalid_source_type_raises(self):
        with pytest.raises(ValueError, match="Invalid source_type"):
            Shipment(source_type="invalid_xyz", source_id=1)

    def test_valid_statuses_set(self):
        assert "draft" in Shipment.VALID_STATUSES
        assert "in_transit" in Shipment.VALID_STATUSES
        assert "arrived" in Shipment.VALID_STATUSES
        assert "selling" in Shipment.VALID_STATUSES
        assert "closed" in Shipment.VALID_STATUSES
        assert "cancelled" in Shipment.VALID_STATUSES
        assert "field_sale" in Shipment.VALID_SOURCE_TYPES


class TestDestinationNameValidation:
    def test_field_sale_requires_destination_name(self):
        with pytest.raises(ValueError, match="destination_name"):
            Shipment(source_type="field_sale", source_id=0, destination_name="")

    def test_field_sale_whitespace_rejected(self):
        with pytest.raises(ValueError, match="destination_name"):
            Shipment(source_type="field_sale", source_id=0, destination_name="   ")

    def test_field_sale_trims_destination(self):
        s = Shipment(source_type="field_sale", source_id=0, destination_name="  Site A  ")
        assert s.destination_name == "Site A"

    def test_delivery_requires_destination_name(self):
        with pytest.raises(ValueError, match="destination_name"):
            Shipment(source_type="delivery", source_id=0, destination_name=None)

    def test_sale_allows_empty_destination(self):
        s = Shipment(source_type="sale", source_id=1, destination_name=None)
        assert s.destination_name is None
        s2 = Shipment(source_type="sale", source_id=1, destination_name="")
        assert s2.destination_name == ""

    def test_field_sale_valid_destination_passes(self):
        s = Shipment(source_type="field_sale", source_id=0, destination_name="Van Site 1")
        assert s.destination_name == "Van Site 1"


class TestShipmentStatusAr:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("pending", "قيد الانتظار"),
            ("draft", "مسودة"),
            ("in_transit", "في الطريق"),
            ("arrived", "وصلت"),
            ("selling", "قيد البيع"),
            ("closed", "مغلقة"),
            ("cancelled", "ملغاة"),
            ("delivered", "تم التسليم"),
        ],
    )
    def test_status_ar_mapping(self, status, expected):
        s = Shipment(source_type="field_sale", source_id=0, destination_name="X", status=status)
        assert s.status_ar == expected

    def test_status_ar_fallback(self):
        s = Shipment(source_type="sale", source_id=1, status="unknown_xyz")
        assert s.status_ar == "unknown_xyz"


class TestShipmentEditableClosable:
    @pytest.mark.parametrize("status", ["draft", "pending"])
    def test_is_editable_true(self, status):
        s = Shipment(source_type="sale", source_id=1, status=status)
        assert s.is_editable is True

    @pytest.mark.parametrize("status", ["in_transit", "arrived", "selling", "closed", "cancelled", "delivered"])
    def test_is_editable_false(self, status):
        s = Shipment(source_type="sale", source_id=1, status=status)
        assert s.is_editable is False

    @pytest.mark.parametrize("status", ["arrived", "selling"])
    def test_is_closable_true(self, status):
        s = Shipment(source_type="field_sale", source_id=0, destination_name="X", status=status)
        assert s.is_closable is True

    @pytest.mark.parametrize("status", ["draft", "pending", "in_transit", "closed", "cancelled"])
    def test_is_closable_false(self, status):
        s = Shipment(source_type="field_sale", source_id=0, destination_name="X", status=status)
        assert s.is_closable is False


class TestShipmentCalculateTotals:
    def test_calculate_totals_sums_lines(self):
        s = Shipment(source_type="field_sale", source_id=0, destination_name="Site", status="draft")
        l1 = ShipmentLine(product_id=1, quantity=Decimal("5"), unit_cost=Decimal("10"))
        l1.line_total = Decimal("50.000")
        l2 = ShipmentLine(product_id=2, quantity=Decimal("3"), unit_cost=Decimal("20"))
        l2.line_total = Decimal("60.000")
        s.lines = [l1, l2]
        s.calculate_totals()
        assert s.total_quantity == Decimal("8")
        assert s.total_value == Decimal("110.000")

    def test_calculate_totals_empty_lines(self):
        s = Shipment(source_type="field_sale", source_id=0, destination_name="Site", status="draft")
        s.lines = []
        s.calculate_totals()
        assert s.total_quantity == Decimal("0")
        assert s.total_value == Decimal("0")

    def test_calculate_totals_single_line(self):
        s = Shipment(source_type="field_sale", source_id=0, destination_name="Site", status="draft")
        sh_line = ShipmentLine(product_id=1, quantity=Decimal("2.5"), unit_cost=Decimal("4"))
        sh_line.line_total = Decimal("10.000")
        s.lines = [sh_line]
        s.calculate_totals()
        assert s.total_quantity == Decimal("2.500")
        assert s.total_value == Decimal("10.000")

    def test_calculate_totals_uses_line_total_not_quantity_times_cost(self):
        s = Shipment(source_type="field_sale", source_id=0, destination_name="Site", status="draft")
        sh_line = ShipmentLine(product_id=1, quantity=Decimal("10"), unit_cost=Decimal("5"))
        sh_line.line_total = Decimal("99.999")
        s.lines = [sh_line]
        s.calculate_totals()
        assert s.total_value == Decimal("99.999")


class TestShipmentLine:
    def test_calculate_line_total(self):
        line = ShipmentLine(product_id=1, quantity=Decimal("3"), unit_cost=Decimal("7.5"))
        line.calculate_line_total()
        assert line.line_total == Decimal("22.5")

    def test_calculate_line_total_zero(self):
        line = ShipmentLine(product_id=1, quantity=Decimal("0"), unit_cost=Decimal("10"))
        line.calculate_line_total()
        assert line.line_total == Decimal("0")

    def test_quantity_remaining(self):
        line = ShipmentLine(product_id=1, quantity=Decimal("10.000"), quantity_invoiced=Decimal("3.000"))
        assert line.quantity_remaining == Decimal("7.000")

    def test_quantity_remaining_full(self):
        line = ShipmentLine(product_id=1, quantity=Decimal("5"), quantity_invoiced=Decimal("0.000"))
        assert line.quantity_remaining == Decimal("5.000")

    def test_quantity_remaining_fully_invoiced(self):
        line = ShipmentLine(product_id=1, quantity=Decimal("5"), quantity_invoiced=Decimal("5.000"))
        assert line.quantity_remaining == Decimal("0.000")

    def test_quantity_remaining_quantized(self):
        line = ShipmentLine(product_id=1, quantity=Decimal("10"), quantity_invoiced=Decimal("0"))
        # Decimal quantize to 3 decimals
        assert str(line.quantity_remaining) == "10.000"

    def test_repr(self):
        line = ShipmentLine(product_id=7, quantity=Decimal("3"))
        assert "7" in repr(line)
        assert "3" in repr(line)

    def test_defaults(self):
        line = ShipmentLine(product_id=1, quantity=Decimal("1"))
        # SQLAlchemy column defaults are applied on flush/DB insert; in-memory they may be None
        assert line.quantity_invoiced in (None, Decimal("0.000"), Decimal("0"), 0)
        assert line.unit_cost in (None, Decimal("0.000"), Decimal("0"), 0)
        assert line.unit_price in (None, Decimal("0.000"), Decimal("0"), 0)
        # After calculate, line_total should be computable even if defaults are None
        line.unit_cost = line.unit_cost or Decimal("0")
        line.calculate_line_total()
        assert line.line_total == Decimal("0") or line.line_total == Decimal("0.000")


class TestShipmentRepr:
    def test_repr_with_shipment_number(self):
        s = Shipment(
            source_type="field_sale", source_id=0, destination_name="X", shipment_number="SH-2026-0001", status="draft"
        )
        assert "SH-2026-0001" in repr(s)
        assert "draft" in repr(s)

    def test_repr_fallback_to_source(self):
        s = Shipment(source_type="sale", source_id=42, status="pending")
        assert "sale#42" in repr(s)


class TestShipmentExplicitFKValidation:
    def test_sale_fk_requires_sale_source_type(self, db_session, sample_tenant):
        # sale_id set while source_type is purchase_return should fail
        s = Shipment(tenant_id=sample_tenant.id, source_type="purchase_return", source_id=1)
        # try to set sale_id -> mismatch
        with pytest.raises(ValueError, match="source_type"):
            s.sale_id = 1

    def test_exactly_one_fk_violation(self, db_session, sample_tenant):
        s = Shipment(tenant_id=sample_tenant.id, source_type="sale", source_id=10, sale_id=10)
        with pytest.raises(ValueError, match="exactly one"):
            s.purchase_return_id = 20

    def test_sale_fk_matches_source_id(self, db_session, sample_tenant, sample_customer, sample_user):
        from datetime import UTC, datetime

        from models.sale import Sale

        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="SAL-FK-001",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(UTC),
            subtotal=Decimal("100"),
            total_amount=Decimal("100"),
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            balance_due=Decimal("100"),
            currency="AED",
        )
        db_session.add(sale)
        db_session.flush()
        s = Shipment(tenant_id=sample_tenant.id, source_type="sale", source_id=sale.id, sale_id=sale.id)
        assert s.sale_id == sale.id

    def test_sale_fk_mismatch_source_id_raises(self):
        # Direct construction with mismatched sale_id/source_id must raise
        with pytest.raises(ValueError, match="must match source_id"):
            Shipment(source_type="sale", source_id=99, sale_id=100)
        # Also via assignment after construction
        s2 = Shipment(source_type="sale", source_id=10)
        with pytest.raises(ValueError, match="must match source_id"):
            s2.sale_id = 20


class TestShipmentModelDBIntegration:
    def test_field_shipment_persists_with_warehouse(self, db_session, sample_tenant, sample_branch, sample_product):
        from models.warehouse import Warehouse

        wh = Warehouse(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            name="Field WH",
            is_active=True,
        )
        db_session.add(wh)
        db_session.flush()
        s = Shipment(
            tenant_id=sample_tenant.id,
            shipment_number="SH-TEST-INT-001",
            source_type="field_sale",
            source_id=0,
            from_warehouse_id=wh.id,
            destination_name="Site Alpha",
            status="draft",
            total_value=Decimal("0"),
            total_quantity=Decimal("0"),
        )
        db_session.add(s)
        db_session.flush()
        line = ShipmentLine(
            shipment_id=s.id,
            product_id=sample_product.id,
            quantity=Decimal("5"),
            unit_cost=Decimal("10"),
            unit_price=Decimal("15"),
            line_total=Decimal("50"),
        )
        db_session.add(line)
        db_session.flush()
        s.calculate_totals()
        assert s.total_quantity == Decimal("5")
        assert s.total_value == Decimal("50")
        assert s.is_editable is True

    def test_shipment_line_quantity_remaining_db(self, db_session, sample_tenant, sample_branch, sample_product):
        from models.warehouse import Warehouse

        wh = Warehouse(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            name="WH2",
            is_active=True,
        )
        db_session.add(wh)
        db_session.flush()
        s = Shipment(
            tenant_id=sample_tenant.id,
            source_type="field_sale",
            source_id=0,
            from_warehouse_id=wh.id,
            destination_name="Site Beta",
            status="draft",
        )
        db_session.add(s)
        db_session.flush()
        line = ShipmentLine(
            shipment_id=s.id,
            product_id=sample_product.id,
            quantity=Decimal("10"),
            quantity_invoiced=Decimal("4"),
            unit_cost=Decimal("5"),
            line_total=Decimal("50"),
        )
        db_session.add(line)
        db_session.flush()
        assert line.quantity_remaining == Decimal("6.000")


class TestSaleShipmentFK:
    def test_sale_shipment_id_nullable(self, db_session, sample_tenant, sample_customer, sample_user):
        from datetime import UTC, datetime

        from models.sale import Sale

        s = Sale(
            tenant_id=sample_tenant.id,
            sale_number="SAL-NOSHIP-001",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(UTC),
            subtotal=Decimal("100"),
            total_amount=Decimal("100"),
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            balance_due=Decimal("100"),
            currency="AED",
            shipment_id=None,
        )
        db_session.add(s)
        db_session.flush()
        assert s.shipment_id is None
        assert hasattr(Sale, "shipment_id")

    def test_sale_with_shipment_link(
        self, db_session, sample_tenant, sample_branch, sample_customer, sample_user, sample_product
    ):
        from datetime import UTC, datetime

        from models.sale import Sale
        from models.warehouse import Warehouse

        wh = Warehouse(tenant_id=sample_tenant.id, branch_id=sample_branch.id, name="WH-SALE", is_active=True)
        db_session.add(wh)
        db_session.flush()
        shipment = Shipment(
            tenant_id=sample_tenant.id,
            source_type="field_sale",
            source_id=0,
            from_warehouse_id=wh.id,
            destination_name="Van Site",
            status="selling",
        )
        db_session.add(shipment)
        db_session.flush()
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="SAL-WITHSHIP-001",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(UTC),
            subtotal=Decimal("200"),
            total_amount=Decimal("200"),
            amount=Decimal("200"),
            amount_aed=Decimal("200"),
            balance_due=Decimal("200"),
            currency="AED",
            shipment_id=shipment.id,
            warehouse_id=wh.id,
        )
        db_session.add(sale)
        db_session.flush()
        assert sale.shipment_id == shipment.id
        assert sale.shipment.id == shipment.id

    def test_sale_direct_invoice_preserved(self, db_session, sample_tenant, sample_customer, sample_user):
        """Old flow: Sale without shipment must still be valid and queryable."""
        from datetime import UTC, datetime

        from models.sale import Sale

        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="SAL-DIRECT-001",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(UTC),
            subtotal=Decimal("50"),
            total_amount=Decimal("50"),
            amount=Decimal("50"),
            amount_aed=Decimal("50"),
            balance_due=Decimal("50"),
            currency="AED",
        )
        db_session.add(sale)
        db_session.flush()
        fetched = db_session.get(Sale, sale.id)
        assert fetched is not None
        assert fetched.shipment_id is None
