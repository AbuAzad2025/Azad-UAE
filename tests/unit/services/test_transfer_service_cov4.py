"""Cov4: transfer_service — create/approve/ship/complete/cancel/receive/get/list arcs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.transfer_service import TransferService


def _user(sample_user):
    return sample_user


def _make_transfer(db_session, sample_tenant, w1, w2, user, **kw):
    data = {
        "from_warehouse_id": w1.id,
        "to_warehouse_id": w2.id,
        "lines": [{"product_id": kw.get("product_id"), "quantity": "3"}],
    }
    return TransferService.create_transfer(data, user)


def test_create_same_warehouse_raises(sample_user, sample_warehouse):
    with pytest.raises(ValueError):
        TransferService.create_transfer(
            {"from_warehouse_id": sample_warehouse.id, "to_warehouse_id": sample_warehouse.id}, sample_user
        )


def test_create_and_lifecycle(db_session, sample_tenant, sample_user, sample_warehouse, sample_product, sample_branch):
    from models import Warehouse

    w2 = Warehouse(tenant_id=sample_tenant.id, branch_id=sample_branch.id, name="W2", code="W2-COV4", is_active=True)
    db_session.add(w2)
    db_session.flush()
    t = TransferService.create_transfer(
        {
            "from_warehouse_id": sample_warehouse.id,
            "to_warehouse_id": w2.id,
            "branch_id": sample_branch.id,
            "notes": "n",
            "lines": [{"product_id": sample_product.id, "quantity": "2", "sort_order": 1}],
        },
        sample_user,
    )
    assert t.status == "draft"
    assert len(t.lines) == 1
    TransferService.approve_transfer(t, sample_user)
    assert t.status == "approved"
    with pytest.raises(ValueError):
        TransferService.approve_transfer(t, sample_user)
    with pytest.raises(ValueError):
        TransferService.complete_transfer(t, sample_user)  # not in_transit yet
    TransferService.ship_transfer(t)
    assert t.status == "in_transit"
    with pytest.raises(ValueError):
        TransferService.ship_transfer(t)
    # confirm receive with mapping + without
    line_id = str(t.lines[0].id)
    TransferService.confirm_receive(t, sample_user, {line_id: "1.5"})
    assert float(t.lines[0].received_quantity) == 1.5
    TransferService.confirm_receive(t, sample_user)


def test_cancel_completed_raises(db_session, sample_user):
    t = SimpleNamespace(status="completed")
    with pytest.raises(ValueError):
        TransferService.cancel_transfer(t)
    t2 = SimpleNamespace(status="draft")
    TransferService.cancel_transfer(t2)
    assert t2.status == "cancelled"


def test_get_transfer_guards(db_session, sample_tenant):
    with pytest.raises(ValueError, match="غير موجود"):
        TransferService.get_transfer(999999999)
    from models import WarehouseTransfer

    t = WarehouseTransfer.query.filter_by(tenant_id=sample_tenant.id).first()
    if t is not None:
        with pytest.raises(ValueError, match="غير مصرح"):
            TransferService.get_transfer(t.id, tenant_id=-7)
        assert TransferService.get_transfer(t.id, tenant_id=t.tenant_id).id == t.id
        assert TransferService.get_transfer(t.id).id == t.id


def test_list_transfers_filters(sample_tenant):
    all_t = TransferService.list_transfers(sample_tenant.id)
    assert isinstance(all_t, list)
    assert TransferService.list_transfers(sample_tenant.id, {"status": "draft"}) is not None
    assert (
        TransferService.list_transfers(
            sample_tenant.id, {"status": "draft", "from_warehouse_id": 1, "to_warehouse_id": 2}
        )
        is not None
    )


def test_complete_transfer_moves_stock(
    db_session, sample_tenant, sample_user, sample_warehouse, sample_product, sample_branch
):
    from unittest.mock import patch

    from models import Warehouse

    w2 = Warehouse(tenant_id=sample_tenant.id, branch_id=sample_branch.id, name="W3", code="W3-COV4", is_active=True)
    db_session.add(w2)
    db_session.flush()
    t = TransferService.create_transfer(
        {
            "from_warehouse_id": sample_warehouse.id,
            "to_warehouse_id": w2.id,
            "lines": [{"product_id": sample_product.id, "quantity": "4"}],
        },
        sample_user,
    )
    TransferService.approve_transfer(t, sample_user)
    TransferService.ship_transfer(t)
    TransferService.confirm_receive(t, sample_user)
    with patch("services.stock_service.StockService.transfer_stock", return_value=None) as ts:
        TransferService.complete_transfer(t, sample_user)
        ts.assert_called_once()
    assert t.status == "completed"
