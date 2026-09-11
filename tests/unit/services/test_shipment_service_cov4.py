"""Cov4: shipment_service — source-type/status/list arcs."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.shipment_service import ShipmentService


def test_create_sale_and_purchase_return_sources(db_session, sample_tenant, sample_customer, sample_user):
    from models import Sale, Purchase, Supplier, PurchaseReturn

    # Create a Sale for the sale shipment
    sale = Sale(
        tenant_id=sample_tenant.id,
        sale_number="SAL-SHIP-1",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        sale_date=datetime.now(UTC),
        subtotal=Decimal("100"),
        total_amount=Decimal("100"),
        amount=Decimal("100"),
        amount_aed=Decimal("100"),
        balance_due=Decimal("0"),
        currency="AED",
    )
    db_session.add(sale)
    db_session.flush()

    s = ShipmentService.create_shipment("sale", sale.id, "Aramex", "TRK-1", tenant_id=sample_tenant.id)
    assert s.sale_id == sale.id and s.purchase_return_id is None
    db_session.flush()

    # Create a PurchaseReturn for the purchase_return shipment
    supplier = Supplier(tenant_id=sample_tenant.id, name="Test Supplier", phone="123")
    db_session.add(supplier)
    db_session.flush()

    purchase = Purchase(
        tenant_id=sample_tenant.id,
        purchase_number="PUR-SHIP-1",
        supplier_id=supplier.id,
        supplier_name="Test Supplier",
        purchase_date=datetime.now(UTC),
        total_amount=Decimal("200"),
        amount=Decimal("200"),
        amount_aed=Decimal("200"),
        currency="AED",
        status="confirmed",
        user_id=sample_user.id,
    )
    db_session.add(purchase)
    db_session.flush()

    pr_model = PurchaseReturn(
        tenant_id=sample_tenant.id,
        return_number="PR-SHIP-1",
        purchase_id=purchase.id,
        supplier_id=supplier.id,
        amount_aed=Decimal("50"),
    )
    db_session.add(pr_model)
    db_session.flush()

    pr = ShipmentService.create_shipment(
        "purchase_return", pr_model.id, "DHL", "TRK-2",
        tenant_id=sample_tenant.id, shipping_cost=5, status="shipped"
    )
    assert pr.purchase_return_id == pr_model.id and pr.sale_id is None
    assert float(pr.shipping_cost) == 5.0
    db_session.flush()


def test_update_status_delivered_sets_date(db_session, sample_tenant, sample_customer, sample_user):
    from models import Sale

    sale = Sale(
        tenant_id=sample_tenant.id,
        sale_number="SAL-SHIP-2",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        sale_date=datetime.now(UTC),
        subtotal=Decimal("100"),
        total_amount=Decimal("100"),
        amount=Decimal("100"),
        amount_aed=Decimal("100"),
        balance_due=Decimal("0"),
        currency="AED",
    )
    db_session.add(sale)
    db_session.flush()

    s = ShipmentService.create_shipment("sale", sale.id, "C", "T-DEL", tenant_id=sample_tenant.id)
    db_session.add(s)
    db_session.flush()
    ShipmentService.update_status(s.id, "delivered")
    assert s.status == "delivered"
    assert s.actual_delivery is not None
    ShipmentService.update_status(s.id, "in_transit")
    assert s.status == "in_transit"


def test_update_status_missing_shipment_is_noop():
    assert ShipmentService.update_status(999999999, "delivered") is None


def test_getters_and_list(db_session, sample_tenant, sample_customer, sample_user):
    from models import Sale

    sale = Sale(
        tenant_id=sample_tenant.id,
        sale_number="SAL-SHIP-3",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        sale_date=datetime.now(UTC),
        subtotal=Decimal("100"),
        total_amount=Decimal("100"),
        amount=Decimal("100"),
        amount_aed=Decimal("100"),
        balance_due=Decimal("0"),
        currency="AED",
    )
    db_session.add(sale)
    db_session.flush()

    s = ShipmentService.create_shipment("sale", sale.id, "C", "T-L1", tenant_id=sample_tenant.id)
    db_session.add(s)
    db_session.flush()
    assert ShipmentService.get_shipments_for_sale(sale.id)
    assert ShipmentService.get_shipments_for_sale(987654321) == []
    assert ShipmentService.get_shipments_for_purchase(987654321) == []
    assert ShipmentService.list_shipments(None) == []
    assert ShipmentService.list_shipments("") == []
    rows = ShipmentService.list_shipments(sample_tenant.id)
    assert any(r.tracking_number == "T-L1" for r in rows)
