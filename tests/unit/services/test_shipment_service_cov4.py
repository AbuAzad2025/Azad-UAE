"""Cov4: shipment_service — source-type/status/list arcs."""

from __future__ import annotations

from services.shipment_service import ShipmentService


def test_create_sale_and_purchase_return_sources(db_session, sample_tenant):
    s = ShipmentService.create_shipment("sale", 11, "Aramex", "TRK-1", tenant_id=sample_tenant.id)
    assert s.sale_id == 11 and s.purchase_return_id is None
    db_session.flush()
    pr = ShipmentService.create_shipment(
        "purchase_return", 22, "DHL", "TRK-2", tenant_id=sample_tenant.id, shipping_cost=5, status="shipped"
    )
    assert pr.purchase_return_id == 22 and pr.sale_id is None
    assert float(pr.shipping_cost) == 5.0
    other = ShipmentService.create_shipment("purchase", 33, "FedEx", "TRK-3", tenant_id=sample_tenant.id)
    assert other.sale_id is None and other.purchase_return_id is None
    db_session.flush()


def test_update_status_delivered_sets_date(db_session, sample_tenant):
    s = ShipmentService.create_shipment("sale", 1, "C", "T-DEL", tenant_id=sample_tenant.id)
    db_session.add(s)
    db_session.flush()
    ShipmentService.update_status(s.id, "delivered")
    assert s.status == "delivered"
    assert s.actual_delivery is not None
    ShipmentService.update_status(s.id, "in_transit")
    assert s.status == "in_transit"


def test_update_status_missing_shipment_is_noop():
    assert ShipmentService.update_status(999999999, "delivered") is None


def test_getters_and_list(db_session, sample_tenant):
    s = ShipmentService.create_shipment("sale", 101, "C", "T-L1", tenant_id=sample_tenant.id)
    db_session.add(s)
    db_session.flush()
    assert ShipmentService.get_shipments_for_sale(101)
    assert ShipmentService.get_shipments_for_sale(987654321) == []
    assert ShipmentService.get_shipments_for_purchase(987654321) == []
    assert ShipmentService.list_shipments(None) == []
    assert ShipmentService.list_shipments("") == []
    rows = ShipmentService.list_shipments(sample_tenant.id)
    assert any(r.tracking_number == "T-L1" for r in rows)
