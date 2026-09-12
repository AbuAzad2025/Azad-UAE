"""Cov5: transfer_service — partial line_receives skips unmatched lines."""

from __future__ import annotations

from decimal import Decimal


def test_confirm_receive_partial_lines_skips_missing(
    db_session, sample_tenant, sample_user, sample_product
):
    from services.transfer_service import TransferService
    from tests.factories import WarehouseFactory

    wh1 = WarehouseFactory(tenant=sample_tenant, name="WHC5-1", code="WHC5-1")
    wh2 = WarehouseFactory(tenant=sample_tenant, name="WHC5-2", code="WHC5-2")
    db_session.commit()
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

    first, second = t.lines[0], t.lines[1]
    TransferService.confirm_receive(t, sample_user, {str(first.id): "2"})
    assert first.received_quantity == Decimal("2.000")
    assert second.received_quantity != Decimal("3.000")
