"""
End-to-end MWAC test:
1. Purchase receipt at new cost -> WAC recalculation
2. Sale -> COGS computed from updated WAC
3. Verify ProductCostHistory audit trail
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def main():
    from app import create_app
    from extensions import db
    from models import (
        Tenant,
        Product,
        Warehouse,
        ProductWarehouseCost,
        ProductCostHistory,
        Purchase,
        PurchaseLine,
        Sale,
        SaleLine,
        Supplier,
        Customer,
    )
    from services.stock_service import StockService
    from decimal import Decimal
    import sqlalchemy as sa

    app = create_app()

    with app.app_context():
        from flask import current_app

        # Temporarily enable MWAC for test
        mwac_original = current_app.config.get("ENABLE_MWAC", False)
        current_app.config["ENABLE_MWAC"] = True

        try:
            tenant = Tenant.query.filter(Tenant.is_active).first()
            if not tenant:
                print("FAIL: No active tenant")
                return 1

            tid = tenant.id
            print(f"Tenant: {tenant.name} (id={tid})")

            # Find a product with existing PWC
            pwc = ProductWarehouseCost.query.filter_by(tenant_id=tid).first()
            if not pwc:
                print(
                    "FAIL: No ProductWarehouseCost record found. Run seed_opening_wac.py first."
                )
                return 1

            product = Product.query.get(pwc.product_id)
            warehouse = Warehouse.query.get(pwc.warehouse_id)
            print(f"Product: {product.name} (id={product.id})")
            print(f"Warehouse: {warehouse.name} (id={warehouse.id})")
            print(
                f"Initial PWC: qty={pwc.total_quantity} avg_cost={pwc.average_cost} value={pwc.total_value}"
            )

            old_pwc_qty = pwc.total_quantity
            old_pwc_avg = pwc.average_cost
            old_pwc_val = pwc.total_value

            # Step 1: Create a purchase at a DIFFERENT cost to force WAC change
            supplier = Supplier.query.filter_by(tenant_id=tid).first()
            if not supplier:
                supplier = Supplier(
                    tenant_id=tid,
                    name="Test Supplier",
                    phone="0500000000",
                )
                db.session.add(supplier)
                db.session.flush()
                print(f"Created test supplier: id={supplier.id}")

            # Create purchase manually
            new_unit_cost = Decimal("250.00")  # different from current cost
            purchase_qty = Decimal("20")
            test_id = str(int(datetime.now(timezone.utc).timestamp()))

            purchase = Purchase(
                tenant_id=tid,
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                warehouse_id=warehouse.id,
                branch_id=warehouse.branch_id,
                purchase_number=f"TEST-MWAC-PUR-{test_id}",
                purchase_date=sa.func.now(),
                currency="AED",
                exchange_rate=Decimal("1"),
                status="received",
                user_id=1,
                subtotal=new_unit_cost * purchase_qty,
                total_amount=new_unit_cost * purchase_qty,
                amount_aed=new_unit_cost * purchase_qty,
            )
            db.session.add(purchase)
            db.session.flush()  # get purchase.id

            pl = PurchaseLine(
                purchase_id=purchase.id,
                product_id=product.id,
                quantity=purchase_qty,
                unit_cost=new_unit_cost,
                line_total=new_unit_cost * purchase_qty,
                tenant_id=tid,
            )
            db.session.add(pl)
            db.session.flush()

            # Trigger MWAC update via process_purchase_lines
            StockService.process_purchase_lines(purchase, warehouse_id=warehouse.id)
            db.session.commit()

            # Refresh PWC
            db.session.refresh(pwc)
            print(f"\r\nAfter Purchase (qty={purchase_qty} @ {new_unit_cost}):")
            print(
                f"  PWC qty={pwc.total_quantity} avg_cost={pwc.average_cost} value={pwc.total_value}"
            )

            # Verify WAC formula
            expected_qty = old_pwc_qty + purchase_qty
            expected_value = old_pwc_val + (purchase_qty * new_unit_cost)
            expected_avg = expected_value / expected_qty

            assert pwc.total_quantity == expected_qty, (
                f"Qty mismatch: {pwc.total_quantity} != {expected_qty}"
            )
            assert abs(
                pwc.average_cost - expected_avg.quantize(Decimal("0.0001"))
            ) < Decimal("0.001"), f"Avg mismatch: {pwc.average_cost} != {expected_avg}"
            print("  ✅ WAC recalculation correct")

            # Verify ProductCostHistory for purchase
            purchase_history = ProductCostHistory.query.filter_by(
                tenant_id=tid,
                product_id=product.id,
                warehouse_id=warehouse.id,
                reference_type="Purchase",
                reference_id=purchase.id,
            ).first()
            assert purchase_history is not None, (
                "Missing ProductCostHistory for purchase"
            )
            print("  ✅ ProductCostHistory record exists for purchase")

            # Step 2: Create a sale and verify COGS
            customer = Customer.query.filter_by(tenant_id=tid).first()
            if not customer:
                customer = Customer(
                    tenant_id=tid,
                    name="Test Customer",
                    phone="0500000000",
                )
                db.session.add(customer)
                db.session.flush()
                print(f"Created test customer: id={customer.id}")

            sale_qty = Decimal("5")
            unit_price = Decimal("400")

            sale = Sale(
                tenant_id=tid,
                customer_id=customer.id,
                seller_id=1,
                warehouse_id=warehouse.id,
                branch_id=warehouse.branch_id,
                sale_number=f"TEST-MWAC-SALE-{test_id}",
                sale_date=sa.func.now(),
                currency="AED",
                exchange_rate=Decimal("1"),
                status="confirmed",
                subtotal=unit_price * sale_qty,
                total_amount=unit_price * sale_qty,
                amount_aed=unit_price * sale_qty,
            )
            db.session.add(sale)
            db.session.flush()

            sl = SaleLine(
                sale_id=sale.id,
                product_id=product.id,
                quantity=sale_qty,
                unit_price=unit_price,
                cost_price=product.cost_price,
                line_total=unit_price * sale_qty,
                tenant_id=tid,
            )
            db.session.add(sl)
            db.session.flush()

            # Process sale (stock + COGS)
            StockService.process_sale_lines(sale, warehouse_id=warehouse.id)
            cogs_total = StockService.calculate_sale_cogs_and_deduct(
                sale, warehouse_id=warehouse.id
            )
            db.session.commit()

            expected_cogs = (pwc.average_cost * sale_qty).quantize(Decimal("0.001"))
            print(f"\r\nAfter Sale (qty={sale_qty}):")
            print(f"  COGS computed: {cogs_total}")
            print(f"  Expected COGS: {expected_cogs}")

            assert abs(cogs_total - expected_cogs) < Decimal("0.01"), (
                f"COGS mismatch: {cogs_total} != {expected_cogs}"
            )
            print("  ✅ COGS computed correctly from WAC")

            # Refresh PWC after sale
            db.session.refresh(pwc)
            print(
                f"  PWC qty={pwc.total_quantity} avg_cost={pwc.average_cost} value={pwc.total_value}"
            )

            expected_qty_after_sale = expected_qty - sale_qty
            assert pwc.total_quantity == expected_qty_after_sale, (
                f"Qty after sale mismatch: {pwc.total_quantity} != {expected_qty_after_sale}"
            )
            print("  ✅ PWC quantity deducted correctly")

            # Verify ProductCostHistory for sale
            sale_history = ProductCostHistory.query.filter_by(
                tenant_id=tid,
                product_id=product.id,
                warehouse_id=warehouse.id,
                reference_type="Sale",
                reference_id=sale.id,
            ).first()
            assert sale_history is not None, "Missing ProductCostHistory for sale"
            print("  ✅ ProductCostHistory record exists for sale")

            print("\r\n=== ALL MWAC TESTS PASSED ===")
            return 0

        finally:
            # Cleanup: delete test data
            print("\r\n--- Cleanup ---")
            for table, cond in [
                (
                    "stock_movements",
                    "reference_id IN (SELECT id FROM sales WHERE sale_number LIKE 'TEST-MWAC%')",
                ),
                (
                    "stock_movements",
                    "reference_id IN (SELECT id FROM purchases WHERE purchase_number LIKE 'TEST-MWAC%')",
                ),
                (
                    "sale_lines",
                    "sale_id IN (SELECT id FROM sales WHERE sale_number LIKE 'TEST-MWAC%')",
                ),
                ("sales", "sale_number LIKE 'TEST-MWAC%'"),
                (
                    "purchase_lines",
                    "purchase_id IN (SELECT id FROM purchases WHERE purchase_number LIKE 'TEST-MWAC%')",
                ),
                ("purchases", "purchase_number LIKE 'TEST-MWAC%'"),
                (
                    "product_cost_history",
                    "reference_id IN (SELECT id FROM sales WHERE sale_number LIKE 'TEST-MWAC%') OR reference_id IN (SELECT id FROM purchases WHERE purchase_number LIKE 'TEST-MWAC%')",
                ),
            ]:
                try:
                    tbl = sa.table(table)
                    db.session.execute(sa.delete(tbl).where(sa.text(cond)))
                except Exception as e:
                    print(f"  Cleanup warning for {table}: {e}")
            db.session.commit()

            # Restore PWC to original state (test stock movements were deleted,
            # but PWC was modified by StockService and needs manual rollback)
            if pwc and old_pwc_qty is not None:
                db.session.execute(
                    sa.text("""
                    UPDATE product_warehouse_costs
                    SET total_quantity = :qty,
                        average_cost = :avg,
                        total_value = :val
                    WHERE id = :id
                """),
                    {
                        "qty": float(old_pwc_qty),
                        "avg": float(old_pwc_avg),
                        "val": float(old_pwc_val),
                        "id": pwc.id,
                    },
                )
                db.session.commit()
                print(
                    f"PWC restored to qty={old_pwc_qty} avg={old_pwc_avg} val={old_pwc_val}"
                )

            # Restore original MWAC flag
            current_app.config["ENABLE_MWAC"] = mwac_original
            print("Flag restored.")


if __name__ == "__main__":
    sys.exit(main())
