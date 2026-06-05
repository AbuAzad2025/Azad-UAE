"""
PWC Opening Balance Backfill — Professional Inventory Reconciliation

Problem: ProductWarehouseCost (PWC) records have quantities seeded before
stock_movement tracking existed. This creates 37 mismatches where:
  PWC.total_quantity != SUM(stock_movements.quantity)

Solution (Accounting-Professional):
  Create "opening_balance" stock_movements for the missing quantities.
  This preserves historical inventory data while making PWC fully auditable
  through stock_movement records. The cost basis is the current WAC.

This script is idempotent: running it twice will detect existing
opening_balance movements and skip already-reconciled records.
"""
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def main():
    from app import create_app
    from extensions import db
    from sqlalchemy import text
    from models import StockMovement

    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("PWC Opening Balance Backfill — Professional Reconciliation")
        print("=" * 60)

        # ============================================================
        # Step 1: Identify all mismatched PWC records
        # ============================================================
        mismatches = db.session.execute(text('''
            SELECT pwc.id, pwc.tenant_id, pwc.product_id, pwc.warehouse_id,
                   pwc.total_quantity AS pwc_qty,
                   pwc.average_cost AS pwc_avg,
                   pwc.total_value AS pwc_val,
                   COALESCE(SUM(sm.quantity), 0) AS movement_net
            FROM product_warehouse_costs pwc
            LEFT JOIN stock_movements sm
                ON sm.tenant_id = pwc.tenant_id
               AND sm.product_id = pwc.product_id
               AND sm.warehouse_id = pwc.warehouse_id
            GROUP BY pwc.id, pwc.tenant_id, pwc.product_id, pwc.warehouse_id,
                     pwc.total_quantity, pwc.average_cost, pwc.total_value
            HAVING pwc.total_quantity != COALESCE(SUM(sm.quantity), 0)
        ''')).fetchall()

        if not mismatches:
            print("No PWC mismatches found. Database is already reconciled.")
            return 0

        print(f"\nFound {len(mismatches)} PWC records with quantity mismatches:\n")

        for m in mismatches:
            diff = Decimal(str(m.pwc_qty)) - Decimal(str(m.movement_net))
            print(
                f"  tenant={m.tenant_id} product={m.product_id} "
                f"warehouse={m.warehouse_id}\n"
                f"    PWC qty={m.pwc_qty}  |  Movement net={m.movement_net}  |  "
                f"Diff={diff:+.3f}\n"
                f"    WAC={m.pwc_avg}  value={m.pwc_val}"
            )

        # ============================================================
        # Step 2: Ask for confirmation
        # ============================================================
        print(f"\n{'=' * 60}")
        print(
            "Action: Create 'opening_balance' stock_movements for the "
            f"{len(mismatches)} discrepancies above."
        )
        print("This preserves inventory quantities by creating auditable movement records.")
        print(f"{'=' * 60}\n")

        response = input("Proceed? (yes/no): ").strip().lower()
        if response not in ('yes', 'y'):
            print("Aborted. No changes made.")
            return 0

        # ============================================================
        # Step 3: Create opening_balance stock movements
        # ============================================================
        created = 0
        zeroed = 0
        unchanged = 0

        for m in mismatches:
            pwc_qty = Decimal(str(m.pwc_qty))
            movement_net = Decimal(str(m.movement_net))
            diff = pwc_qty - movement_net

            # Case A: PWC > movements → create opening_balance IN movement
            if diff > 0:
                # Check if an opening_balance already exists for this combo
                existing = db.session.execute(text('''
                    SELECT COUNT(*) FROM stock_movements
                    WHERE tenant_id = :tid
                      AND product_id = :pid
                      AND warehouse_id = :wid
                      AND movement_type = 'opening_balance'
                '''), {
                    'tid': m.tenant_id,
                    'pid': m.product_id,
                    'wid': m.warehouse_id,
                }).scalar()

                if existing > 0:
                    print(
                        f"  SKIP tenant={m.tenant_id} product={m.product_id}: "
                        f"opening_balance movement already exists"
                    )
                    unchanged += 1
                    continue

                unit_cost = Decimal(str(m.pwc_avg)) if m.pwc_avg else Decimal('0')

                op = StockMovement(
                    tenant_id=m.tenant_id,
                    product_id=m.product_id,
                    warehouse_id=m.warehouse_id,
                    movement_type='opening_balance',
                    quantity=diff,
                    reference_type='inventory',
                    reference_id=None,
                    user_id=1,
                    notes=(
                        f"Opening balance backfill | "
                        f"PWC qty={pwc_qty} movement_net={movement_net} | "
                        f"auto-created {datetime.now(timezone.utc).isoformat()}"
                    ),
                )
                db.session.add(op)
                db.session.flush()

                print(
                    f"  CREATED tenant={m.tenant_id} product={m.product_id} "
                    f"warehouse={m.warehouse_id}: qty=+{diff} "
                    f"unit_cost={unit_cost} movement_id={op.id}"
                )
                created += 1

            # Case B: PWC < movements (negative diff) → abnormal, report
            elif diff < 0:
                print(
                    f"  WARN tenant={m.tenant_id} product={m.product_id}: "
                    f"movements exceed PWC by {abs(diff)}. "
                    f"Manual review required."
                )
                zeroed += 1

            else:
                unchanged += 1

        db.session.commit()

        # ============================================================
        # Step 4: Verify
        # ============================================================
        print(f"\n{'=' * 60}")
        print("Backfill Complete")
        print(f"{'=' * 60}")
        print(f"  Opening balance movements created: {created}")
        print(f"  Skipped (already reconciled):      {unchanged}")
        print(f"  Warnings (movements > PWC):        {zeroed}")

        remaining = db.session.execute(text('''
            SELECT COUNT(*) FROM (
                SELECT pwc.id
                FROM product_warehouse_costs pwc
                LEFT JOIN stock_movements sm
                    ON sm.tenant_id = pwc.tenant_id
                   AND sm.product_id = pwc.product_id
                   AND sm.warehouse_id = pwc.warehouse_id
                GROUP BY pwc.id
                HAVING pwc.total_quantity != COALESCE(SUM(sm.quantity), 0)
            ) sub
        ''')).scalar()

        print(f"  Remaining mismatches:              {remaining}")

        if remaining == 0:
            print("\n  All PWC records are now reconciled with stock movements.")

        return 0


if __name__ == '__main__':
    sys.exit(main())
