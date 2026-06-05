"""Backfill GL inventory opening reconciliation entries.

Creates auditable, balanced GL entries so the 1140 inventory balance matches
the operational PWC inventory value for historical opening-balance data.

Default mode is dry-run. Use --execute to write entries.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

TOLERANCE = Decimal("0.01")
REFERENCE_TYPE = "InventoryGLReconciliation"


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _pick_single_dimension(rows, key):
    values = {getattr(row, key) for row in rows if getattr(row, key) is not None}
    return next(iter(values)) if len(values) == 1 else None


def _tenant_pwc_dimensions(db, ProductWarehouseCost, Warehouse, tenant_id):
    pwc_rows = ProductWarehouseCost.query.filter_by(tenant_id=tenant_id).all()
    warehouses = [
        db.session.get(Warehouse, row.warehouse_id)
        for row in pwc_rows
        if row.warehouse_id is not None
    ]
    warehouses = [warehouse for warehouse in warehouses if warehouse is not None]
    return (
        pwc_rows,
        _pick_single_dimension(warehouses, "branch_id"),
        _pick_single_dimension(warehouses, "id"),
    )


def _tag_legacy_inventory_lines(
    db,
    GLAccount,
    GLJournalEntry,
    GLJournalLine,
    inventory_account,
    tenant_id,
    branch_id,
    warehouse_id,
    execute,
):
    if branch_id is None or warehouse_id is None:
        return 0

    lines = (
        GLJournalLine.query
        .join(GLJournalEntry, GLJournalEntry.id == GLJournalLine.entry_id)
        .filter(GLJournalEntry.tenant_id == tenant_id)
        .filter(GLJournalEntry.is_posted.is_(True))
        .filter(GLJournalLine.account_id == inventory_account.id)
        .filter(GLJournalLine.warehouse_id.is_(None))
        .all()
    )

    if execute:
        for line in lines:
            line.warehouse_id = warehouse_id
            if line.branch_id is None:
                line.branch_id = branch_id
            if line.entry and line.entry.branch_id is None:
                line.entry.branch_id = branch_id

    return len(lines)


def _tenant_ids_with_inventory_scope(db, ProductWarehouseCost, GLAccount, GLJournalLine, GLJournalEntry):
    pwc_ids = {
        row[0]
        for row in db.session.query(ProductWarehouseCost.tenant_id).distinct().all()
    }
    gl_ids = {
        row[0]
        for row in (
            db.session.query(GLJournalEntry.tenant_id)
            .join(GLJournalLine, GLJournalLine.entry_id == GLJournalEntry.id)
            .join(GLAccount, GLAccount.id == GLJournalLine.account_id)
            .filter(GLAccount.code == "1140")
            .filter(GLJournalEntry.is_posted.is_(True))
            .distinct()
            .all()
        )
    }
    return sorted(tid for tid in (pwc_ids | gl_ids) if tid is not None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="create reconciliation entries")
    args = parser.parse_args(argv)

    from app import create_app
    from extensions import db
    from models import GLAccount, GLJournalEntry, GLJournalLine, ProductWarehouseCost, Warehouse
    from services import gl_helpers
    from services.inventory_reconciliation_service import InventoryReconciliationService
    from utils.gl_tenant import scope_gl_accounts

    app = create_app()
    with app.app_context():
        tenant_ids = _tenant_ids_with_inventory_scope(
            db, ProductWarehouseCost, GLAccount, GLJournalLine, GLJournalEntry
        )
        print(f"Inventory GL reconciliation backfill | execute={args.execute}")

        created = 0
        tagged = 0
        skipped = 0
        for tenant_id in tenant_ids:
            inventory_account = scope_gl_accounts(
                GLAccount.query.filter_by(code="1140", is_active=True, is_header=False),
                tenant_id=tenant_id,
            ).first()
            retained_account = scope_gl_accounts(
                GLAccount.query.filter_by(code="3200", is_active=True, is_header=False),
                tenant_id=tenant_id,
            ).first()
            if not inventory_account or not retained_account:
                print(f"SKIP tenant={tenant_id}: missing active 1140 or 3200 account")
                skipped += 1
                continue

            pwc_rows, branch_id, warehouse_id = _tenant_pwc_dimensions(
                db, ProductWarehouseCost, Warehouse, tenant_id
            )
            tagged_count = _tag_legacy_inventory_lines(
                db,
                GLAccount,
                GLJournalEntry,
                GLJournalLine,
                inventory_account,
                tenant_id,
                branch_id,
                warehouse_id,
                args.execute,
            )
            tagged += tagged_count
            if tagged_count:
                print(
                    f"TAG tenant={tenant_id}: {tagged_count} legacy 1140 line(s) "
                    f"-> warehouse={warehouse_id}"
                )

            pwc_value = sum((_decimal(row.total_value) for row in pwc_rows), Decimal("0"))
            gl_value = InventoryReconciliationService._gl_inventory_balance(
                inventory_account.id,
                tenant_id=tenant_id,
                branch_id=None,
                warehouse_id=None,
            )
            diff = pwc_value - gl_value

            if abs(diff) <= TOLERANCE:
                print(
                    f"OK tenant={tenant_id}: PWC={pwc_value:.3f} GL={gl_value:.3f} diff={diff:+.3f}"
                )
                skipped += 1
                continue

            amount = abs(diff).quantize(Decimal("0.001"))

            print(
                f"FIX tenant={tenant_id}: PWC={pwc_value:.3f} GL={gl_value:.3f} "
                f"diff={diff:+.3f} branch={branch_id} warehouse={warehouse_id}"
            )

            if not args.execute:
                continue

            entry = GLJournalEntry(
                tenant_id=tenant_id,
                entry_number=gl_helpers.next_entry_number(tenant_id),
                entry_date=datetime.now(timezone.utc),
                description="Inventory GL reconciliation opening adjustment",
                reference_type=REFERENCE_TYPE,
                reference_id=None,
                branch_id=branch_id,
                entry_type="adjustment",
                currency="AED",
                exchange_rate=Decimal("1"),
                is_posted=True,
                total_debit=amount,
                total_credit=amount,
                created_by=1,
            )
            db.session.add(entry)
            db.session.flush()

            if diff > 0:
                inventory_debit = amount
                inventory_credit = Decimal("0")
                retained_debit = Decimal("0")
                retained_credit = amount
            else:
                inventory_debit = Decimal("0")
                inventory_credit = amount
                retained_debit = amount
                retained_credit = Decimal("0")

            db.session.add(GLJournalLine(
                tenant_id=tenant_id,
                entry_id=entry.id,
                account_id=inventory_account.id,
                debit=inventory_debit,
                credit=inventory_credit,
                amount=inventory_debit - inventory_credit,
                amount_aed=inventory_debit - inventory_credit,
                description="Inventory opening reconciliation to PWC value",
                branch_id=branch_id,
                warehouse_id=warehouse_id,
            ))
            db.session.add(GLJournalLine(
                tenant_id=tenant_id,
                entry_id=entry.id,
                account_id=retained_account.id,
                debit=retained_debit,
                credit=retained_credit,
                amount=retained_debit - retained_credit,
                amount_aed=retained_debit - retained_credit,
                description="Offset for inventory opening reconciliation",
                branch_id=branch_id,
            ))
            created += 1

        if args.execute:
            db.session.commit()
        else:
            db.session.rollback()

        print(f"created={created} tagged={tagged} skipped={skipped} dry_run={not args.execute}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
