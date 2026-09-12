"""Cov5: procurement_service — wrong-status guards + three-way-match skip arcs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


def _requisition(db_session, sample_user, sample_product):
    from services.procurement_service import ProcurementService

    data = {"lines": [{"product_id": str(sample_product.id), "quantity": "5", "unit_cost_estimate": "100"}]}
    return ProcurementService.create_requisition(data, sample_user)


def test_approve_wrong_status_raises(db_session, sample_user, sample_product):
    from services.procurement_service import ProcurementService

    pr = _requisition(db_session, sample_user, sample_product)
    with pytest.raises(ValueError):
        ProcurementService.approve_requisition(pr, sample_user)


def test_reject_wrong_status_raises(db_session, sample_user, sample_product):
    from services.procurement_service import ProcurementService

    pr = _requisition(db_session, sample_user, sample_product)
    with pytest.raises(ValueError):
        ProcurementService.reject_requisition(pr, sample_user, "no")


def test_submit_po_wrong_status_raises(db_session, sample_tenant, sample_user, sample_supplier, sample_warehouse):
    from models import PurchaseOrder
    from services.procurement_service import ProcurementService

    po = PurchaseOrder(
        tenant_id=sample_tenant.id,
        po_number=f"PO-CV5-{sample_tenant.id}",
        supplier_id=sample_supplier.id,
        warehouse_id=sample_warehouse.id,
        order_date=date.today(),
        status="submitted",
        total_amount=Decimal("10"),
        created_by=sample_user.id,
    )
    db_session.add(po)
    db_session.flush()
    with pytest.raises(ValueError):
        ProcurementService.submit_po(po)


def test_confirm_po_wrong_status_raises(db_session, sample_tenant, sample_user, sample_supplier, sample_warehouse):
    from models import PurchaseOrder
    from services.procurement_service import ProcurementService

    po = PurchaseOrder(
        tenant_id=sample_tenant.id,
        po_number=f"PO-CV5C-{sample_tenant.id}",
        supplier_id=sample_supplier.id,
        warehouse_id=sample_warehouse.id,
        order_date=date.today(),
        status="confirmed",
        total_amount=Decimal("10"),
        created_by=sample_user.id,
    )
    db_session.add(po)
    db_session.flush()
    with pytest.raises(ValueError):
        ProcurementService.confirm_po(po, sample_user)


def test_three_way_match_skips_unconfirmed_grn_and_unmatched_lines(
    db_session, app, sample_tenant, sample_user, sample_supplier, sample_product, sample_warehouse
):
    import flask_login

    from models import PurchaseOrder, PurchaseOrderLine
    from services.procurement_service import ProcurementService

    po = PurchaseOrder(
        tenant_id=sample_tenant.id,
        po_number=f"PO-CV5M-{sample_tenant.id}-{sample_product.id}",
        supplier_id=sample_supplier.id,
        warehouse_id=sample_warehouse.id,
        order_date=date.today(),
        status="confirmed",
        total_amount=Decimal("100"),
        created_by=sample_user.id,
    )
    db_session.add(po)
    db_session.flush()
    for qty in ("10", "4"):
        db_session.add(
            PurchaseOrderLine(
                tenant_id=sample_tenant.id,
                po_id=po.id,
                product_id=sample_product.id,
                quantity=Decimal(qty),
                unit_cost=Decimal("5"),
                line_total=Decimal(qty) * Decimal("5"),
            )
        )
    db_session.flush()
    first_line = [ln for ln in po.lines if ln.quantity == Decimal("10")][0]
    grn = ProcurementService.create_grn(
        po.id, {"lines": [{"po_line_id": first_line.id, "received_quantity": "10"}]}, sample_user
    )
    ProcurementService.confirm_grn(grn)
    # Draft GRN: skipped by the confirmed-status guard
    ProcurementService.create_grn(
        po.id, {"lines": [{"po_line_id": first_line.id, "received_quantity": "1"}]}, sample_user
    )
    with app.test_request_context():
        flask_login.login_user(sample_user)
        results = ProcurementService.three_way_match(po.id, "50", "AED")
    assert results["po_id"] == po.id
    assert len(results["line_matches"]) == 2
