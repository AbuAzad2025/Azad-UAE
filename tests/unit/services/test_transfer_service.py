"""Transfer service tests."""

from __future__ import annotations

import pytest

from models import Warehouse
from services.transfer_service import TransferService


class TestTransferWorkflow:
    def test_create_transfer(self, db_session, sample_tenant, sample_user, sample_product):
        wh1 = Warehouse(tenant_id=sample_tenant.id, name="WH1", code="WH1")
        wh2 = Warehouse(tenant_id=sample_tenant.id, name="WH2", code="WH2")
        db_session.add_all([wh1, wh2])
        db_session.flush()

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
        wh1 = Warehouse(tenant_id=sample_tenant.id, name="WH3", code="WH3")
        db_session.add(wh1)
        db_session.flush()

        with pytest.raises(ValueError):
            TransferService.create_transfer(
                {"from_warehouse_id": wh1.id, "to_warehouse_id": wh1.id, "lines": []},
                sample_user,
            )

    def test_approve_transfer(self, db_session, sample_tenant, sample_user):
        wh1 = Warehouse(tenant_id=sample_tenant.id, name="WH4", code="WH4")
        wh2 = Warehouse(tenant_id=sample_tenant.id, name="WH5", code="WH5")
        db_session.add_all([wh1, wh2])
        db_session.flush()

        t = TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        TransferService.approve_transfer(t, sample_user)
        assert t.status == "approved"
        assert t.approved_by == sample_user.id

    def test_approve_non_draft_raises(self, db_session, sample_tenant, sample_user):
        wh1 = Warehouse(tenant_id=sample_tenant.id, name="WH6", code="WH6")
        wh2 = Warehouse(tenant_id=sample_tenant.id, name="WH7", code="WH7")
        db_session.add_all([wh1, wh2])
        db_session.flush()

        t = TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        TransferService.approve_transfer(t, sample_user)
        with pytest.raises(ValueError):
            TransferService.approve_transfer(t, sample_user)

    def test_cancel_transfer(self, db_session, sample_tenant, sample_user):
        wh1 = Warehouse(tenant_id=sample_tenant.id, name="WH8", code="WH8")
        wh2 = Warehouse(tenant_id=sample_tenant.id, name="WH9", code="WH9")
        db_session.add_all([wh1, wh2])
        db_session.flush()

        t = TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        TransferService.cancel_transfer(t)
        assert t.status == "cancelled"

    def test_list_transfers(self, db_session, sample_tenant, sample_user):
        wh1 = Warehouse(tenant_id=sample_tenant.id, name="WH10", code="WH10")
        wh2 = Warehouse(tenant_id=sample_tenant.id, name="WH11", code="WH11")
        db_session.add_all([wh1, wh2])
        db_session.flush()

        TransferService.create_transfer(
            {"from_warehouse_id": wh1.id, "to_warehouse_id": wh2.id, "lines": []},
            sample_user,
        )
        result = TransferService.list_transfers(sample_tenant.id)
        assert len(result) >= 1
