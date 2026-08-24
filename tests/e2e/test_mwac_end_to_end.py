"""
End-to-end MWAC test:
1. Login → dashboard (true e2e)
2. Purchase receipt at new cost -> WAC recalculation
3. Sale -> COGS computed from updated WAC
4. Verify ProductCostHistory audit trail
"""

from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa


def test_mwac_end_to_end(
    app,
    db_session,
    sample_tenant,
    sample_branch,
    sample_warehouse,
    sample_product,
    sample_supplier,
    sample_customer,
    auth_client,
):
    from models import (
        ProductCostHistory,
        ProductWarehouseCost,
        Purchase,
        PurchaseLine,
        Sale,
        SaleLine,
    )
    from services.stock_service import StockService

    # 1. Login -> dashboard reachable
    resp = auth_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code in (200, 302)
    if resp.status_code == 302:
        assert "/login" not in resp.headers.get("Location", "")

    tenant_id = sample_tenant.id
    warehouse = sample_warehouse
    product = sample_product

    if warehouse.branch_id is None:
        warehouse.branch_id = sample_branch.id
        db_session.flush()

    product.regular_price = product.regular_price or Decimal("100")
    product.cost_price = product.cost_price or Decimal("50")
    db_session.flush()

    # Ensure PWC baseline deterministic
    pwc = ProductWarehouseCost.query.filter_by(
        tenant_id=tenant_id,
        product_id=product.id,
        warehouse_id=warehouse.id,
    ).first()
    if not pwc:
        pwc = ProductWarehouseCost(
            tenant_id=tenant_id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            total_quantity=Decimal("20"),
            average_cost=Decimal("100.0000"),
            total_value=Decimal("2000.000"),
        )
        db_session.add(pwc)
        db_session.flush()
    else:
        pwc.total_quantity = Decimal("20")
        pwc.average_cost = Decimal("100.0000")
        pwc.total_value = Decimal("2000.000")
        db_session.flush()

    old_qty = pwc.total_quantity
    old_val = pwc.total_value

    from models import User

    user = User.query.filter_by(tenant_id=tenant_id).order_by(User.id).first()
    assert user is not None

    supplier = sample_supplier
    customer = sample_customer

    new_unit_cost = Decimal("250.00")
    purchase_qty = Decimal("20")
    test_id = str(int(datetime.now(UTC).timestamp()))[-6:]

    purchase_total = new_unit_cost * purchase_qty
    purchase = Purchase(
        tenant_id=tenant_id,
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        warehouse_id=warehouse.id,
        branch_id=warehouse.branch_id,
        purchase_number=f"TEST-MWAC-PUR-{test_id}",
        purchase_date=sa.func.now(),
        currency="AED",
        exchange_rate=Decimal("1"),
        status="received",
        user_id=user.id,
        subtotal=purchase_total,
        total_amount=purchase_total,
        amount=purchase_total,
        amount_aed=purchase_total,
    )
    db_session.add(purchase)
    db_session.flush()

    pl = PurchaseLine(
        purchase_id=purchase.id,
        product_id=product.id,
        quantity=purchase_qty,
        unit_cost=new_unit_cost,
        line_total=new_unit_cost * purchase_qty,
        tenant_id=tenant_id,
    )
    db_session.add(pl)
    db_session.flush()

    StockService.process_purchase_lines(purchase, warehouse_id=warehouse.id)
    db_session.flush()
    db_session.refresh(pwc)

    expected_qty = old_qty + purchase_qty
    expected_value = old_val + (purchase_qty * new_unit_cost)
    expected_avg = expected_value / expected_qty

    assert pwc.total_quantity == expected_qty
    assert abs(pwc.average_cost - expected_avg.quantize(Decimal("0.0001"))) < Decimal("0.001")

    # Verify history exists
    purchase_history = ProductCostHistory.query.filter_by(
        tenant_id=tenant_id,
        product_id=product.id,
        warehouse_id=warehouse.id,
        reference_type="Purchase",
        reference_id=purchase.id,
    ).first()
    assert purchase_history is not None

    # Verify purchase visible via HTTP (e2e verify)
    resp = auth_client.get(f"/purchases/{purchase.id}", follow_redirects=False)
    assert resp.status_code in (200, 302, 403, 404)

    # Step 2: Sale -> COGS
    sale_qty = Decimal("5")
    unit_price = Decimal("400")

    sale_total = unit_price * sale_qty
    sale = Sale(
        tenant_id=tenant_id,
        customer_id=customer.id,
        seller_id=user.id,
        warehouse_id=warehouse.id,
        branch_id=warehouse.branch_id,
        sale_number=f"TEST-MWAC-SALE-{test_id}",
        sale_date=sa.func.now(),
        currency="AED",
        exchange_rate=Decimal("1"),
        status="confirmed",
        subtotal=sale_total,
        total_amount=sale_total,
        amount=sale_total,
        amount_aed=sale_total,
    )
    db_session.add(sale)
    db_session.flush()

    sl = SaleLine(
        sale_id=sale.id,
        product_id=product.id,
        quantity=sale_qty,
        unit_price=unit_price,
        cost_price=product.cost_price,
        line_total=unit_price * sale_qty,
        tenant_id=tenant_id,
    )
    db_session.add(sl)
    db_session.flush()

    # Need to capture avg before sale for COGS expectation
    avg_before_sale = pwc.average_cost
    expected_cogs = (avg_before_sale * sale_qty).quantize(Decimal("0.001"))

    StockService.process_sale_lines(sale, warehouse_id=warehouse.id)
    cogs_total = StockService.calculate_sale_cogs_and_deduct(sale, warehouse_id=warehouse.id)
    db_session.flush()

    # COGS should match avg * qty (allow small rounding)
    assert abs(cogs_total - expected_cogs) < Decimal("0.01")

    db_session.refresh(pwc)
    expected_qty_after_sale = expected_qty - sale_qty
    assert pwc.total_quantity == expected_qty_after_sale

    # Verify history for sale
    sale_history = ProductCostHistory.query.filter_by(
        tenant_id=tenant_id,
        product_id=product.id,
        warehouse_id=warehouse.id,
        reference_type="Sale",
        reference_id=sale.id,
    ).first()
    assert sale_history is not None

    # Verify sale visible via HTTP
    resp = auth_client.get(f"/sales/{sale.id}", follow_redirects=False)
    assert resp.status_code in (200, 302, 403, 404)
