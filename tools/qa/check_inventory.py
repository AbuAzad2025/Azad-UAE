"""Check inventory/stock data in the database.

Reports:
- Product / serial / movement / warehouse counts
- GL coverage per reference_type (Purchase, Sale, StockAdjustment, StockTransfer)
- Orphaned movements (no parent document)
- PWC vs movement net quantity reconciliation
"""
import os, sys
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
os.chdir(project_root)
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()


def check_inventory():
    """Check inventory/stock records."""
    with app.app_context():
        conn = db.engine.connect()

        # Basic counts
        for label, sql in [
            ("Products", "SELECT COUNT(*) FROM products"),
            ("Product Serials", "SELECT COUNT(*) FROM product_serials"),
            ("Stock Movements", "SELECT COUNT(*) FROM stock_movements"),
            ("Warehouses", "SELECT COUNT(*) FROM warehouses"),
        ]:
            try:
                result = conn.execute(text(sql))
                print(f"{label}: {result.scalar()}")
            except Exception as e:
                print(f"Error checking {label.lower()}: {e}")

        # Stock movements by reference_type
        print("\n--- Stock Movements by Reference Type ---")
        try:
            result = conn.execute(text("""
                SELECT reference_type, COUNT(*) AS cnt,
                       SUM(CASE WHEN movement_type = 'in' THEN quantity ELSE 0 END) AS total_in,
                       SUM(CASE WHEN movement_type = 'out' THEN quantity ELSE 0 END) AS total_out
                FROM stock_movements
                GROUP BY reference_type
                ORDER BY reference_type
            """))
            for row in result.fetchall():
                print(f"  {row.reference_type or 'NULL'}: count={row.cnt} in={row.total_in} out={row.total_out}")
        except Exception as e:
            print(f"Error: {e}")

        # GL coverage per operational reference_type
        print("\n--- GL Coverage per Reference Type ---")
        for ref_type in ['purchase', 'sale', 'StockAdjustment', 'StockTransfer', 'ProductReturn']:
            try:
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM stock_movements sm
                    WHERE sm.reference_type = :ref_type
                      AND NOT EXISTS (
                          SELECT 1 FROM gl_journal_entries e
                          WHERE e.reference_id = sm.reference_id
                            AND LOWER(e.reference_type) IN (
                                LOWER(:ref_type),
                                'stock_movement',
                                'stockadjustment'
                            )
                      )
                """), {'ref_type': ref_type})
                missing = result.scalar()
                if missing > 0:
                    print(f"  {ref_type}: {missing} movements missing GL entries")
                else:
                    print(f"  {ref_type}: OK (all covered)")
            except Exception as e:
                print(f"  {ref_type}: error - {e}")

        # Orphaned movements (no parent document)
        print("\n--- Orphaned Movements (no parent document) ---")
        try:
            result = conn.execute(text("""
                SELECT sm.reference_type, COUNT(*) AS cnt
                FROM stock_movements sm
                WHERE sm.reference_id IS NOT NULL
                  AND sm.reference_type IN ('sale', 'purchase', 'return')
                  AND NOT EXISTS (
                      SELECT 1 FROM sales s WHERE s.id = sm.reference_id AND sm.reference_type = 'sale'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM purchases p WHERE p.id = sm.reference_id AND sm.reference_type = 'purchase'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM product_returns r WHERE r.id = sm.reference_id AND sm.reference_type = 'return'
                  )
                GROUP BY sm.reference_type
                ORDER BY sm.reference_type
            """))
            rows = result.fetchall()
            if rows:
                for row in rows:
                    print(f"  {row.reference_type}: {row.cnt} orphaned")
            else:
                print("  None found")
        except Exception as e:
            print(f"Error: {e}")

        # PWC reconciliation check
        print("\n--- PWC vs Movement Net Quantity Check ---")
        try:
            result = conn.execute(text("""
                SELECT pwc.tenant_id, pwc.product_id, pwc.warehouse_id,
                       pwc.total_quantity AS pwc_qty,
                       COALESCE(SUM(sm.quantity), 0) AS movement_net
                FROM product_warehouse_costs pwc
                LEFT JOIN stock_movements sm ON sm.product_id = pwc.product_id
                                            AND sm.warehouse_id = pwc.warehouse_id
                                            AND sm.tenant_id = pwc.tenant_id
                GROUP BY pwc.id, pwc.tenant_id, pwc.product_id, pwc.warehouse_id, pwc.total_quantity
                HAVING pwc.total_quantity != COALESCE(SUM(sm.quantity), 0)
            """))
            mismatches = result.fetchall()
            if mismatches:
                print(f"  {len(mismatches)} PWC records with quantity mismatch:")
                for row in mismatches[:5]:
                    print(f"    tenant={row.tenant_id} product={row.product_id} warehouse={row.warehouse_id} pwc_qty={row.pwc_qty} movement_net={row.movement_net}")
                if len(mismatches) > 5:
                    print(f"    ... and {len(mismatches)-5} more")
            else:
                print("  All PWC records match movement net quantities")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    check_inventory()
