"""Transfer service tests."""

from __future__ import annotations

import pytest

from services.transfer_service import TransferService
from tests.factories import WarehouseFactory


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
