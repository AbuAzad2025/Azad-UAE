"""Transfer service tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from models import StockMovement, Tenant, WarehouseTransfer
from services.stock_service import StockService
from services.transfer_service import TransferService
from tests.factories import WarehouseFactory
from utils.gl_reference_types import GLRef


@pytest.fixture
def two_warehouses(db_session, sample_tenant):
    """A pair of warehouses under the sample tenant."""
    wh1 = WarehouseFactory(tenant=sample_tenant, name="WH1", code="WH1")
    wh2 = WarehouseFactory(tenant=sample_tenant, name="WH2", code="WH2")
    db_session.commit()
    return wh1, wh2


class TestTransferWorkflow:
    def test_create_transfer(self, db_session, sample_tenant, sample_user, sample_product, two_warehouses):
        wh1, wh2 = two_warehouses
        t = TransferService.create_transfer(
            {
                "from_warehouse_id": wh1.id,
                "to_warehouse_id": wh2.id,
                "lines": [{"product_id": sample_product.id, "quantity": 10}],
            },
            sample_user,
        )
        assert t.id is not None
        assert t.status == "draft"
        assert t.transfer_number.startswith("TR")

    def test_same_warehouse_raises(self, db_session, sample_tenant, sample_user):
        wh1 = WarehouseFactory(tenant=sample_tenant, name="WH3", code="WH3")
        db_session.commit()

        with pytest.raises(ValueError):
            TransferService.create_transfer(
                {"from_warehouse_id": wh1.id, "to_warehouse_id": wh1.id, "lines": []},
                sample_user,
            )

    def test_approve_transfer(self, db_session, sample_tenant, sample_user, two_warehouses):
        wh1, wh2 = two_warehouses
        t = TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        TransferService.approve_transfer(t, sample_user)
        assert t.status == "approved"
        assert t.approved_by == sample_user.id

    def test_approve_non_draft_raises(self, db_session, sample_tenant, sample_user, two_warehouses):
        wh1, wh2 = two_warehouses
        t = TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        TransferService.approve_transfer(t, sample_user)
        with pytest.raises(ValueError):
            TransferService.approve_transfer(t, sample_user)

    def test_cancel_transfer(self, db_session, sample_tenant, sample_user, two_warehouses):
        wh1, wh2 = two_warehouses
        t = TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        TransferService.cancel_transfer(t)
        assert t.status == "cancelled"

    def test_list_transfers(self, db_session, sample_tenant, sample_user, two_warehouses):
        wh1, wh2 = two_warehouses
        TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        result = TransferService.list_transfers(sample_tenant.id)
        assert len(result) >= 1


def _q3(value):
    return Decimal(str(value)).quantize(Decimal("0.001"))


class TestShipTransfer:
    def test_ship_approved_transfer(self, db_session, sample_tenant, sample_user, two_warehouses):
        wh1, wh2 = two_warehouses
        t = TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        TransferService.approve_transfer(t, sample_user)
        result = TransferService.ship_transfer(t)
        assert result.status == "in_transit"

    def test_ship_draft_raises(self, db_session, sample_tenant, sample_user, two_warehouses):
        wh1, wh2 = two_warehouses
        t = TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        with pytest.raises(ValueError):
            TransferService.ship_transfer(t)


class TestCompleteTransferStockMovement:
    """complete_transfer must move real stock in BOTH directions (out + in)."""

    def _in_transit_transfer(self, sample_tenant, sample_user, two_warehouses, product, qty="10"):
        from services.stock_service import StockService

        wh1, wh2 = two_warehouses
        StockService.add_stock(product.id, 50, warehouse_id=wh1.id)
        t = TransferService.create_transfer(
            {
                "from_warehouse_id": wh1.id,
                "to_warehouse_id": wh2.id,
                "lines": [{"product_id": product.id, "quantity": qty}],
            },
            sample_user,
        )
        TransferService.approve_transfer(t, sample_user)
        TransferService.ship_transfer(t)
        return t

    def test_complete_moves_stock_both_directions(
        self, db_session, sample_tenant, sample_user, sample_product, two_warehouses
    ):
        wh1, wh2 = two_warehouses
        t = self._in_transit_transfer(sample_tenant, sample_user, two_warehouses, sample_product)

        result = TransferService.complete_transfer(t, sample_user)

        assert result.status == "completed"
        assert result.completed_date is not None
        assert result.received_by == sample_user.id

        movements = (
            StockMovement.query.filter_by(
                tenant_id=sample_tenant.id,
                product_id=sample_product.id,
                reference_type=GLRef.STOCK_TRANSFER,
            )
            .order_by(StockMovement.id.asc())
            .all()
        )
        # Seed movement is "purchase"; exactly two new "transfer" movements exist.
        transfer_movements = [m for m in movements if m.movement_type == "transfer"]
        assert len(transfer_movements) == 2
        out_m, in_m = transfer_movements[0], transfer_movements[1]
        assert out_m.warehouse_id == wh1.id
        assert out_m.quantity == Decimal("-10.000")
        assert in_m.warehouse_id == wh2.id
        assert in_m.quantity == Decimal("10.000")
        assert in_m.reference_id == out_m.id

    def test_complete_updates_per_warehouse_balances(
        self, db_session, sample_tenant, sample_user, sample_product, two_warehouses
    ):
        from models import ProductWarehouseStock

        wh1, wh2 = two_warehouses
        t = self._in_transit_transfer(sample_tenant, sample_user, two_warehouses, sample_product)
        TransferService.complete_transfer(t, sample_user)

        q1 = ProductWarehouseStock.query.filter_by(product_id=sample_product.id, warehouse_id=wh1.id).first()
        q2 = ProductWarehouseStock.query.filter_by(product_id=sample_product.id, warehouse_id=wh2.id).first()
        assert q1.quantity == _q3("40")
        assert q2.quantity == _q3("10")

    def test_complete_prefers_received_quantity(
        self, db_session, sample_tenant, sample_user, sample_product, two_warehouses
    ):
        wh1, wh2 = two_warehouses
        t = self._in_transit_transfer(sample_tenant, sample_user, two_warehouses, sample_product)
        line = t.lines[0]
        TransferService.confirm_receive(t, sample_user, {str(line.id): "4"})
        TransferService.complete_transfer(t, sample_user)

        movements = StockMovement.query.filter_by(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            reference_type=GLRef.STOCK_TRANSFER,
            movement_type="transfer",
        ).all()
        quantities = sorted(m.quantity for m in movements)
        assert quantities == [Decimal("-4.000"), Decimal("4.000")]

    def test_complete_skips_zero_quantity_lines(
        self, db_session, sample_tenant, sample_user, sample_product, two_warehouses
    ):
        wh1, wh2 = two_warehouses
        StockService.add_stock(sample_product.id, 50, warehouse_id=wh1.id)
        t = TransferService.create_transfer(
            {
                "from_warehouse_id": wh1.id,
                "to_warehouse_id": wh2.id,
                "lines": [{"product_id": sample_product.id, "quantity": 0}],
            },
            sample_user,
        )
        TransferService.approve_transfer(t, sample_user)
        TransferService.ship_transfer(t)
        TransferService.complete_transfer(t, sample_user)

        assert t.status == "completed"
        transfer_movements = StockMovement.query.filter_by(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            reference_type=GLRef.STOCK_TRANSFER,
            movement_type="transfer",
        ).all()
        assert transfer_movements == []

    def test_complete_non_transit_raises(self, db_session, sample_tenant, sample_user, two_warehouses):
        wh1, wh2 = two_warehouses
        t = TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        with pytest.raises(ValueError):
            TransferService.complete_transfer(t, sample_user)


class TestCancelGuards:
    def test_cancel_completed_raises(self, db_session, sample_tenant, sample_user, sample_product, two_warehouses):
        wh1, wh2 = two_warehouses
        StockService.add_stock(sample_product.id, 50, warehouse_id=wh1.id)
        t = TransferService.create_transfer(
            {
                "from_warehouse_id": wh1.id,
                "to_warehouse_id": wh2.id,
                "lines": [{"product_id": sample_product.id, "quantity": 5}],
            },
            sample_user,
        )
        TransferService.approve_transfer(t, sample_user)
        TransferService.ship_transfer(t)
        TransferService.complete_transfer(t, sample_user)

        with pytest.raises(ValueError):
            TransferService.cancel_transfer(t)


class TestConfirmReceive:
    def test_confirm_receive_defaults_to_requested(
        self, db_session, sample_tenant, sample_user, sample_product, two_warehouses
    ):
        wh1, wh2 = two_warehouses
        t = TransferService.create_transfer(
            {
                "from_warehouse_id": wh1.id,
                "to_warehouse_id": wh2.id,
                "lines": [
                    {"product_id": sample_product.id, "quantity": 7},
                    {"product_id": sample_product.id, "quantity": 3, "sort_order": 1},
                ],
            },
            sample_user,
        )
        TransferService.approve_transfer(t, sample_user)
        TransferService.ship_transfer(t)

        result = TransferService.confirm_receive(t, sample_user)

        assert result.received_by == sample_user.id
        for line in result.lines:
            assert line.received_quantity == line.requested_quantity
        assert result.lines[0].received_quantity == Decimal("7.000")

    def test_confirm_receive_explicit_lines_decimal_conversion(
        self, db_session, sample_tenant, sample_user, sample_product, two_warehouses
    ):
        wh1, wh2 = two_warehouses
        t = TransferService.create_transfer(
            {
                "from_warehouse_id": wh1.id,
                "to_warehouse_id": wh2.id,
                "lines": [{"product_id": sample_product.id, "quantity": 10}],
            },
            sample_user,
        )
        TransferService.approve_transfer(t, sample_user)
        TransferService.ship_transfer(t)

        TransferService.confirm_receive(t, sample_user, {str(t.lines[0].id): "6.5"})

        assert t.lines[0].received_quantity == Decimal("6.500")

    def test_confirm_receive_wrong_status_raises(self, db_session, sample_tenant, sample_user, two_warehouses):
        wh1, wh2 = two_warehouses
        t = TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        with pytest.raises(ValueError):
            TransferService.confirm_receive(t, sample_user)


class TestTransferLookup:
    def test_get_transfer_found(self, db_session, sample_tenant, sample_user, two_warehouses):
        wh1, wh2 = two_warehouses
        t = TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        assert TransferService.get_transfer(t.id).id == t.id

    def test_get_transfer_missing_raises(self, db_session):
        with pytest.raises(ValueError):
            TransferService.get_transfer(99999999)

    def test_get_transfer_cross_tenant_raises(self, db_session, sample_tenant, sample_user, two_warehouses):
        wh1, wh2 = two_warehouses
        other_tenant = Tenant(name="Other Co", name_ar="آخر", slug=f"other-{db_session.query(Tenant).count()}",
                              email="other@test.local", country="AE", subscription_plan="basic")
        db_session.add(other_tenant)
        db_session.flush()

        foreign = WarehouseTransfer(
            tenant_id=other_tenant.id,
            transfer_number="TR-FOREIGN-1",
            from_warehouse_id=wh1.id,
            to_warehouse_id=wh2.id,
            requested_by=sample_user.id,
        )
        db_session.add(foreign)
        db_session.flush()

        assert TransferService.get_transfer(foreign.id, tenant_id=None).id == foreign.id
        with pytest.raises(ValueError):
            TransferService.get_transfer(foreign.id, tenant_id=sample_tenant.id)


class TestListFilters:
    def test_list_filters_status_and_warehouses(self, db_session, sample_tenant, sample_user, two_warehouses):
        wh1, wh2 = two_warehouses
        t1 = TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []}, sample_user
        )
        TransferService.approve_transfer(t1, sample_user)
        TransferService.create_transfer({"from_warehouse_id": wh2.id, "to_warehouse_id": wh1.id, "lines": []}, sample_user)

        by_status = TransferService.list_transfers(sample_tenant.id, filters={"status": "approved"})
        assert [t.id for t in by_status] == [t1.id]

        by_from = TransferService.list_transfers(sample_tenant.id, filters={"from_warehouse_id": str(wh2.id)})
        assert all(t.from_warehouse_id == wh2.id for t in by_from)
        assert len(by_from) >= 1

        by_to = TransferService.list_transfers(sample_tenant.id, filters={"to_warehouse_id": str(wh1.id)})
        assert all(t.to_warehouse_id == wh1.id for t in by_to)
        assert len(by_to) >= 1
