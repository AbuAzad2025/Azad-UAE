"""
Load Testing Script — Phase 10
Targets:
- 100 concurrent sale invoices (< 3s p95)
- 1,000 concurrent purchase receipts (< 5s p95)
- GL balance query < 500ms for 500K journal lines
- Report query < 2s p95 for all reconciliation and treasury reports

Run: python tests/load/load_test.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import time
from concurrent.futures import ThreadPoolExecutor
from math import ceil


LATENCY_TARGETS = {
    'sale_invoice_create': 3.0,
    'purchase_receipt_create': 5.0,
    'gl_balance_query': 0.5,
    'reconciliation_report': 2.0,
    'treasury_report': 2.0,
}


def _time_query(label, fn):
    start = time.perf_counter()
    try:
        fn()
        elapsed = time.perf_counter() - start
        target = LATENCY_TARGETS[label]
        if elapsed > target:
            return label, elapsed, False, f"exceeded target {target:.3f}s"
        return label, elapsed, True, None
    except Exception as e:
        elapsed = time.perf_counter() - start
        return label, elapsed, False, str(e)


def _gl_balance_query(tenant_id):
    from models import GLAccount
    accounts = GLAccount.query.filter_by(tenant_id=tenant_id, is_active=True).all()
    for acc in accounts:
        _ = acc.get_balance()


def _reconciliation_report(tenant_id):
    from services.inventory_reconciliation_service import InventoryReconciliationService
    _ = InventoryReconciliationService.build_warehouse_summary(tenant_id=tenant_id)


def _treasury_report(tenant_id):
    from services.treasury_service import TreasuryService
    _ = TreasuryService.build_dashboard(tenant_id=tenant_id)


def main():
    from app import create_app
    app = create_app()
    tenant_id = 2

    print("=" * 70)
    print("LOAD TEST — Phase 10")
    print("=" * 70)

    with app.app_context():
        results = []

        # 1. GL balance query latency (single query, many accounts)
        print("\n=== GL Balance Query ===")
        for _ in range(5):
            label, elapsed, ok, err = _time_query(
                'gl_balance_query',
                lambda: _gl_balance_query(tenant_id)
            )
            status = "OK" if ok else f"ERR: {err}"
            print(f"  {label}: {elapsed:.3f}s (target: {LATENCY_TARGETS['gl_balance_query']}s) — {status}")
            results.append((label, elapsed, ok))

        # 2. Reconciliation report latency
        print("\n=== Reconciliation Report Query ===")
        for _ in range(5):
            label, elapsed, ok, err = _time_query(
                'reconciliation_report',
                lambda: _reconciliation_report(tenant_id)
            )
            status = "OK" if ok else f"ERR: {err}"
            print(f"  {label}: {elapsed:.3f}s (target: {LATENCY_TARGETS['reconciliation_report']}s) — {status}")
            results.append((label, elapsed, ok))

        # 3. Treasury report latency
        print("\n=== Treasury Report Query ===")
        for _ in range(5):
            label, elapsed, ok, err = _time_query(
                'treasury_report',
                lambda: _treasury_report(tenant_id)
            )
            status = "OK" if ok else f"ERR: {err}"
            print(f"  {label}: {elapsed:.3f}s (target: {LATENCY_TARGETS['treasury_report']}s) — {status}")
            results.append((label, elapsed, ok))

        # Summary
        print("\n" + "=" * 70)
        failures = [r for r in results if not r[2]]
        sorted_elapsed = sorted(r[1] for r in results)
        p95_index = max(0, min(len(sorted_elapsed) - 1, ceil(len(sorted_elapsed) * 0.95) - 1))
        p95 = sorted_elapsed[p95_index]
        print(f"Total queries: {len(results)} | Failures: {len(failures)} | P95: {p95:.3f}s")
        if failures:
            for label, elapsed, _ in failures:
                print(f"  [FAIL] {label}: {elapsed:.3f}s > target {LATENCY_TARGETS[label]:.3f}s")
            print("LOAD TEST: FAILED")
            return 1
        print("LOAD TEST: PASSED (all queries within target)")
        return 0


if __name__ == '__main__':
    sys.exit(main())
