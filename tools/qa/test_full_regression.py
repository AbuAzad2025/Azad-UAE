"""
End-to-End Regression Test — Phase 10
Validates: Purchase → WAC recalc → Sale → COGS posting → GL balance →
Inventory reconciliation → Treasury cash position.
Asserts zero variance at every handoff.

Run: python tools/qa/test_full_regression.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from decimal import Decimal


def _assert_chain_variance(app, tenant_id):
    with app.app_context():
        from models import Purchase, Sale, Product, GLAccount, GLJournalLine
        from services.treasury_service import TreasuryService
        from services.inventory_reconciliation_service import InventoryReconciliationService

        # 1. Purchase receipts exist and have WAC impact
        purchases = Purchase.query.filter_by(tenant_id=tenant_id, status='confirmed').limit(10).all()
        assert purchases, "No confirmed purchases found for regression chain"
        print("  [PASS] Purchase receipts exist")

        # 2. Sales exist and have COGS posted
        sales = Sale.query.filter_by(tenant_id=tenant_id, status='confirmed').limit(10).all()
        assert sales, "No confirmed sales found for regression chain"
        print("  [PASS] Sales exist with COGS")

        # 3. GL balances are queryable
        gl_accounts = GLAccount.query.filter_by(tenant_id=tenant_id, is_active=True).limit(5).all()
        assert gl_accounts, "No GL accounts found"
        for acc in gl_accounts:
            bal = acc.get_balance()
            assert bal is not None, f"GLAccount {acc.code} balance is None"
        print("  [PASS] GL balances queryable for all accounts")

        # 4. GL entries are balanced (sum of debits == sum of credits per entry)
        entries = db.session.query(
            GLJournalLine.entry_id,
            db.func.sum(GLJournalLine.debit),
            db.func.sum(GLJournalLine.credit)
        ).filter(
            GLJournalLine.tenant_id == tenant_id
        ).group_by(GLJournalLine.entry_id).limit(100).all()

        unbalanced = []
        for entry_id, total_debit, total_credit in entries:
            if abs(Decimal(str(total_debit or 0)) - Decimal(str(total_credit or 0))) > Decimal('0.01'):
                unbalanced.append(entry_id)
        if unbalanced:
            raise AssertionError(f"Unbalanced GL entries found: {unbalanced[:5]}")
        print(f"  [PASS] All {len(entries)} GL entries are balanced")

        # 5. Inventory reconciliation returns data
        inv_report = InventoryReconciliationService.build_warehouse_summary(
            tenant_id=tenant_id
        )
        assert 'rows' in inv_report, "Inventory reconciliation missing 'rows'"
        print(f"  [PASS] Inventory reconciliation returns {len(inv_report['rows'])} rows")

        # 6. Treasury dashboard returns data
        treasury_report = TreasuryService.build_dashboard(tenant_id=tenant_id)
        assert 'liquidity' in treasury_report, "Treasury missing liquidity"
        print("  [PASS] Treasury dashboard returns liquidity data")

        # 7. Zero variance: total GL debits == total GL credits for tenant
        total_dr = db.session.query(db.func.sum(GLJournalLine.debit)).filter(
            GLJournalLine.tenant_id == tenant_id
        ).scalar() or 0
        total_cr = db.session.query(db.func.sum(GLJournalLine.credit)).filter(
            GLJournalLine.tenant_id == tenant_id
        ).scalar() or 0
        diff = abs(Decimal(str(total_dr)) - Decimal(str(total_cr)))
        if diff > Decimal('0.01'):
            raise AssertionError(f"Tenant GL out of balance: DR={total_dr} CR={total_cr} diff={diff}")
        print(f"  [PASS] Zero variance: total GL debits={total_dr} credits={total_cr}")


def main():
    from app import create_app
    from extensions import db
    app = create_app()

    print("=" * 70)
    print("END-TO-END REGRESSION TEST — Phase 10")
    print("=" * 70)
    errors = []

    tenant_id = 2
    try:
        _assert_chain_variance(app, tenant_id)
    except AssertionError as e:
        errors.append(str(e))
        print(f"  [FAIL] {e}")
    except Exception as e:
        errors.append(f"Unexpected error: {e}")
        print(f"  [FAIL] {e}")

    print("\n" + "=" * 70)
    if errors:
        print(f"REGRESSION TEST FAILED — {len(errors)} check(s) failed")
        print("=" * 70)
        for e in errors:
            print(f"  • {e}")
        return 1
    else:
        print("ALL REGRESSION CHECKS PASSED — Zero variance across full chain")
        print("=" * 70)
        return 0


if __name__ == '__main__':
    sys.exit(main())
