"""
Data cleanup script for orphaned records and historical inconsistencies.

Addresses findings from KODEX audit:
1. Orphaned stock movements in tenant 2 (no parent sale/purchase/return documents).
2. ILS cheque FX rate inconsistencies (exchange_rate=1.0 but amount_aed != amount).
3. Reconciles ProductWarehouseCost after cleanup.

Run with: python tools/cleanup_orphaned_data.py --dry-run
           python tools/cleanup_orphaned_data.py --apply
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def find_orphaned_movements(db):
    """Find stock movements whose parent document no longer exists."""
    from sqlalchemy import text
    result = db.session.execute(text('''
        SELECT sm.id, sm.reference_type, sm.reference_id, sm.movement_type,
               sm.quantity, sm.product_id, sm.warehouse_id, sm.tenant_id
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
        ORDER BY sm.reference_type, sm.id
    '''))
    return result.fetchall()


def find_orphaned_gl_entries(db, orphaned_ref_ids):
    """Find GL entries referencing orphaned parent document IDs."""
    from sqlalchemy import text
    if not orphaned_ref_ids:
        return []
    placeholders = ','.join(str(i) for i in orphaned_ref_ids)
    result = db.session.execute(text(f'''
        SELECT id, reference_type, reference_id, description
        FROM gl_journal_entries
        WHERE reference_id IN ({placeholders})
          AND reference_type IN ('sale', 'purchase', 'return', 'Sale', 'Purchase', 'ProductReturn')
    '''))
    return result.fetchall()


def find_ils_cheque_mismatches(db):
    """Find ILS cheques where exchange_rate=1.0 but amount_aed != amount."""
    from sqlalchemy import text
    result = db.session.execute(text('''
        SELECT id, cheque_number, amount, exchange_rate, amount_aed
        FROM cheques
        WHERE currency != 'AED'
          AND (amount_aed IS NULL OR ABS(amount_aed - (amount::numeric * exchange_rate::numeric)) > 0.01)
    '''))
    return result.fetchall()


def cleanup_orphaned_movements(db, dry_run=True):
    from sqlalchemy import text

    movements = find_orphaned_movements(db)
    print(f"Found {len(movements)} orphaned stock movements across all tenants")

    orphaned_ref_ids = list(set(m.reference_id for m in movements))
    gl_entries = find_orphaned_gl_entries(db, orphaned_ref_ids)
    print(f"Found {len(gl_entries)} orphaned GL entries referencing missing parent docs")

    # Group movements by tenant/product/warehouse for PWC reconciliation
    pwc_impacts = {}
    for m in movements:
        key = (m.tenant_id, m.product_id, m.warehouse_id)
        if key not in pwc_impacts:
            pwc_impacts[key] = Decimal('0')
        if m.movement_type == 'in':
            pwc_impacts[key] += Decimal(str(m.quantity))
        else:
            pwc_impacts[key] -= Decimal(str(m.quantity))

    if dry_run:
        print("\n[DRY RUN] Would perform the following changes:")
        print(f"  - Delete {len(movements)} orphaned stock_movements")
        print(f"  - Delete {len(gl_entries)} orphaned gl_journal_entries")
        for (tid, pid, wid), qty_delta in pwc_impacts.items():
            print(f"  - Adjust PWC tenant={tid} product={pid} warehouse={wid} by {-qty_delta} (removing ghost qty)")
        return

    # Apply changes
    print("\n[APPLY] Cleaning up orphaned data...")

    # 1. Delete orphaned GL entries
    if gl_entries:
        gl_ids = [e.id for e in gl_entries]
        placeholders = ','.join(str(i) for i in gl_ids)
        # Delete associated journal lines first
        db.session.execute(text(f'''
            DELETE FROM gl_journal_lines WHERE entry_id IN ({placeholders})
        '''))
        db.session.execute(text(f'''
            DELETE FROM gl_journal_entries WHERE id IN ({placeholders})
        '''))
        print(f"  Deleted {len(gl_entries)} orphaned GL entries + lines")

    # 2. Delete orphaned stock movements
    if movements:
        sm_ids = [m.id for m in movements]
        placeholders = ','.join(str(i) for i in sm_ids)
        db.session.execute(text(f'''
            DELETE FROM stock_movements WHERE id IN ({placeholders})
        '''))
        print(f"  Deleted {len(movements)} orphaned stock movements")

    # 3. Reconcile PWC
    from models import ProductWarehouseCost
    reconciled = 0
    for (tid, pid, wid), qty_delta in pwc_impacts.items():
        pwc = ProductWarehouseCost.query.filter_by(
            tenant_id=tid, product_id=pid, warehouse_id=wid
        ).first()
        if pwc:
            old_qty = pwc.total_quantity
            pwc.total_quantity -= qty_delta
            # Recalculate total_value to match new qty at same avg cost
            if pwc.total_quantity > 0 and old_qty > 0:
                pwc.total_value = pwc.total_quantity * pwc.average_cost
            elif pwc.total_quantity <= 0:
                pwc.total_value = Decimal('0')
                pwc.average_cost = Decimal('0')
            print(f"  Reconciled PWC tenant={tid} product={pid} warehouse={wid}: qty {old_qty} -> {pwc.total_quantity}")
            reconciled += 1
    print(f"  Reconciled {reconciled} PWC records")

    db.session.commit()
    print("  Committed.")


def normalize_cheque_fx(db, dry_run=True):
    from sqlalchemy import text
    mismatches = find_ils_cheque_mismatches(db)
    print(f"\nFound {len(mismatches)} non-AED cheques with FX inconsistency")

    if dry_run:
        print("[DRY RUN] Would update exchange_rate = amount_aed / amount for:")
        for c in mismatches[:5]:
            amt = Decimal(str(c.amount))
            aed = Decimal(str(c.amount_aed)) if c.amount_aed else Decimal('0')
            if amt > 0:
                rate = (aed / amt).quantize(Decimal('0.000001'))
                print(f"  {c.cheque_number}: exchange_rate 1.0 -> {rate} (amount={amt}, amount_aed={aed})")
        if len(mismatches) > 5:
            print(f"  ... and {len(mismatches)-5} more")
        return

    print("[APPLY] Normalizing ILS cheque FX rates...")
    updated = 0
    for c in mismatches:
        amt = Decimal(str(c.amount))
        aed = Decimal(str(c.amount_aed)) if c.amount_aed else Decimal('0')
        if amt > 0:
            rate = (aed / amt).quantize(Decimal('0.000001'))
            db.session.execute(text('''
                UPDATE cheques
                SET exchange_rate = :rate
                WHERE id = :id
            '''), {'rate': rate, 'id': c.id})
            updated += 1
    db.session.commit()
    print(f"  Updated {updated} cheques.")


def main():
    from app import create_app
    from extensions import db

    dry_run = '--apply' not in sys.argv
    if dry_run:
        print("Running in DRY-RUN mode. Use --apply to execute changes.\n")
    else:
        print("Running in APPLY mode. Changes will be committed.\n")

    app = create_app()
    with app.app_context():
        cleanup_orphaned_movements(db, dry_run=dry_run)
        normalize_cheque_fx(db, dry_run=dry_run)
        print("\nDone.")


if __name__ == '__main__':
    main()
