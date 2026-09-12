"""Cov5: purchase_service — quick purchase with tenant adds stock."""

from __future__ import annotations

from decimal import Decimal


def test_quick_purchase_with_tenant_adds_stock(
    db_session, sample_tenant, sample_user, sample_supplier, sample_product, sample_warehouse
):
    from models import PurchaseLine
    from services.purchase_service import PurchaseService

    purchase = PurchaseService.create_quick_purchase(
        sample_supplier.id,
        sample_product.id,
        2,
        "10",
        tenant_id=sample_tenant.id,
        user_id=sample_user.id,
    )
    assert purchase.purchase_number.startswith("PUR-")
    line = PurchaseLine.query.filter_by(purchase_id=purchase.id).first()
    assert line is not None
    assert line.line_total == Decimal("20.000")
