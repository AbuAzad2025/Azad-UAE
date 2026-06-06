"""
Seed ProductWarehouseCost with opening balances calculated from historical purchases.

Strategy:
1. For each (product_id, warehouse_id) pair with purchase history:
   WAC = SUM(purchase_line.unit_cost * purchase_line.quantity) / SUM(purchase_line.quantity)
2. For products with no purchase history: use Product.cost_price as fallback.
3. Insert into ProductWarehouseCost.
4. Append to ProductCostHistory as 'opening_balance' type.

Usage:
    python scripts/seed/seed_opening_wac.py [--dry-run]
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description="Seed opening WAC balances")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--tenant-id", type=int, default=None, help="Limit to specific tenant")
    args = parser.parse_args()

    from app import create_app
    from extensions import db
    from models import Product, ProductWarehouseCost, ProductCostHistory, Tenant
    from decimal import Decimal
    from datetime import datetime, timezone
    import sqlalchemy as sa

    app = create_app()

    with app.app_context():
        # Determine which tenants to process
        tenant_filter = ""
        params = {}
        if args.tenant_id:
            tenant_filter = "WHERE p.tenant_id = :tid"
            params = {"tid": args.tenant_id}
            tenants = [Tenant.query.get(args.tenant_id)]
        else:
            tenants = Tenant.query.filter(Tenant.is_active == True).all()

        print(f"Processing {len(tenants)} tenant(s)...\n")

        total_seeded = 0
        total_history = 0

        for tenant in tenants:
            tid = tenant.id
            print(f"--- Tenant: {tenant.name} (id={tid}) ---")

            # Step 1: Calculate WAC from purchase history per (product, warehouse)
            sql = sa.text(f"""
                SELECT
                    pl.product_id,
                    p.warehouse_id,
                    SUM(pl.unit_cost * pl.quantity) AS total_cost,
                    SUM(pl.quantity) AS total_qty
                FROM purchase_lines pl
                JOIN purchases p ON p.id = pl.purchase_id
                WHERE pl.tenant_id = :tid AND p.warehouse_id IS NOT NULL
                GROUP BY pl.product_id, p.warehouse_id
            """)
            result = db.session.execute(sql, {"tid": tid})
            wac_rows = []
            for row in result:
                product_id, warehouse_id, total_cost, total_qty = row
                if total_qty and total_qty > 0:
                    avg_cost = Decimal(total_cost) / Decimal(total_qty)
                    wac_rows.append({
                        "product_id": product_id,
                        "warehouse_id": warehouse_id,
                        "total_quantity": Decimal(total_qty),
                        "average_cost": avg_cost.quantize(Decimal("0.0001")),
                        "total_value": Decimal(total_cost).quantize(Decimal("0.0001")),
                    })

            # Step 2: Find products with stock but NO purchase history
            # Assign them to the tenant's primary warehouse
            primary_wh_sql = sa.text("""
                SELECT id FROM warehouses
                WHERE tenant_id = :tid
                ORDER BY id ASC LIMIT 1
            """)
            primary_wh = db.session.execute(primary_wh_sql, {"tid": tid}).scalar()
            if not primary_wh:
                print(f"  No warehouse found for tenant {tid}, skipping.")
                continue

            sql_missing = sa.text("""
                SELECT id, current_stock, cost_price
                FROM products
                WHERE tenant_id = :tid AND current_stock > 0
            """)
            products_with_stock = db.session.execute(sql_missing, {"tid": tid}).fetchall()
            product_ids_with_wac = {r["product_id"] for r in wac_rows}

            fallback_rows = []
            for prod_id, stock, cost_price in products_with_stock:
                if prod_id not in product_ids_with_wac and stock and stock > 0:
                    cost = Decimal(cost_price) if cost_price else Decimal("0")
                    fallback_rows.append({
                        "product_id": prod_id,
                        "warehouse_id": primary_wh,
                        "total_quantity": Decimal(stock),
                        "average_cost": cost.quantize(Decimal("0.0001")),
                        "total_value": (Decimal(stock) * cost).quantize(Decimal("0.0001")),
                    })

            all_rows = wac_rows + fallback_rows
            print(f"  WAC from purchases: {len(wac_rows)} product-warehouse pairs")
            print(f"  WAC from cost_price fallback: {len(fallback_rows)} product-warehouse pairs")

            if args.dry_run:
                for r in all_rows:
                    print(f"    [DRY-RUN] product={r['product_id']} wh={r['warehouse_id']} "
                          f"qty={r['total_quantity']} avg_cost={r['average_cost']}")
                continue

            # Step 3: Insert into ProductWarehouseCost
            for r in all_rows:
                existing = ProductWarehouseCost.query.filter_by(
                    product_id=r["product_id"],
                    warehouse_id=r["warehouse_id"],
                    tenant_id=tid,
                ).first()

                if existing:
                    existing.total_quantity = r["total_quantity"]
                    existing.average_cost = r["average_cost"]
                    existing.total_value = r["total_value"]
                    existing.updated_at = datetime.now(timezone.utc)
                    print(f"    Updated PWC: product={r['product_id']} wh={r['warehouse_id']}")
                else:
                    pwc = ProductWarehouseCost(
                        tenant_id=tid,
                        product_id=r["product_id"],
                        warehouse_id=r["warehouse_id"],
                        total_quantity=r["total_quantity"],
                        average_cost=r["average_cost"],
                        total_value=r["total_value"],
                    )
                    db.session.add(pwc)
                    print(f"    Created PWC: product={r['product_id']} wh={r['warehouse_id']}")
                total_seeded += 1

                # Step 4: Append ProductCostHistory
                pch = ProductCostHistory(
                    tenant_id=tid,
                    product_id=r["product_id"],
                    warehouse_id=r["warehouse_id"],
                    old_average_cost=r["average_cost"],
                    new_average_cost=r["average_cost"],
                    quantity_change=r["total_quantity"],
                    old_total_quantity=Decimal("0"),
                    new_total_quantity=r["total_quantity"],
                    old_total_value=Decimal("0"),
                    new_total_value=r["total_value"],
                    movement_type="opening_balance",
                    reference_type="opening_balance",
                    reference_id=0,
                    movement_unit_cost=r["average_cost"],
                )
                db.session.add(pch)
                total_history += 1

            db.session.commit()
            print(f"  Committed for tenant {tid}.\n")

        print(f"=== SUMMARY ===")
        print(f"Total ProductWarehouseCost rows: {total_seeded}")
        print(f"Total ProductCostHistory rows: {total_history}")
        if args.dry_run:
            print("(DRY-RUN: no data written)")


if __name__ == "__main__":
    main()
