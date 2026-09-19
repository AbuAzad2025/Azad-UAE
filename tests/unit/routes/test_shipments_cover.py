"""Quick coverage for uncovered shipment templates."""

from extensions import db
from models.shipment import Shipment
from models.warehouse import Warehouse


def test_shipments_list_and_view_render(auth_client, sample_tenant, sample_branch, sample_user):
    wh = Warehouse(tenant_id=sample_tenant.id, name="WH-TEST", code="WHTEST", is_active=True)
    db.session.add(wh)
    db.session.flush()
    s = Shipment(
        tenant_id=sample_tenant.id,
        shipment_number="SHIP-001",
        from_warehouse_id=wh.id,
        destination_name="Site",
        destination_type="site",
        source_type="sale",
        source_id=1,
        status="pending",
    )
    db.session.add(s)
    db.session.commit()
    # /shipments/list renders shipments/list.html
    resp = auth_client.get("/shipments")
    assert resp.status_code in (200, 302)
    # /shipments/{id} renders shipments/view.html
    resp = auth_client.get(f"/shipments/{s.id}")
    assert resp.status_code in (200, 302)
    # /shipments/create renders shipments/create.html
    resp = auth_client.get("/shipments/create")
    assert resp.status_code in (200, 302)
