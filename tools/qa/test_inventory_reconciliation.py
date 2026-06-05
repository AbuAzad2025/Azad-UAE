"""Quick test for inventory reconciliation service."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def main():
    from app import create_app
    app = create_app()

    with app.app_context():
        from services.inventory_reconciliation_service import InventoryReconciliationService

        report = InventoryReconciliationService.build_warehouse_summary(tenant_id=2)

        print("=== Summary ===")
        s = report["summary"]
        print(f"record_count: {s['record_count']}")
        print(f"all_matched: {s['all_matched']}")
        print(f"total_pwc_qty: {s['total_pwc_qty']}")
        print(f"total_movement_qty: {s['total_movement_qty']}")
        print(f"overall_qty_diff: {s['overall_qty_diff']}")
        print()

        print("=== Warehouse Summary ===")
        for w in report["warehouse_summary"]:
            print(
                f"  {w['warehouse_name']}: products={w['products']} "
                f"pwc_qty={w['pwc_qty']:.3f} movement_qty={w['movement_qty']:.3f} "
                f"diff={w['qty_diff']:+.3f} matched={w['matched_qty']}"
            )
        print()

        print("=== First 3 Product Rows ===")
        for r in report["rows"][:3]:
            print(
                f"  {r['product_name']} @ {r['warehouse_name']}: "
                f"pwc={r['pwc_qty']:.3f} movement={r['movement_qty']:.3f} "
                f"diff={r['qty_diff']:+.3f}"
            )

        if s["all_matched"]:
            print("\nAll quantities matched!")
            return 0
        else:
            mismatched = [r for r in report["rows"] if not r["matched_qty"]]
            print(f"\n{len(mismatched)} records have quantity mismatches")
            return 1


if __name__ == "__main__":
    sys.exit(main())
