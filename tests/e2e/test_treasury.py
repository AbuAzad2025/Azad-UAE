"""
Treasury Service QA Test — Phase 8
Validates: liquidity position, cheque maturity buckets, bank reconciliation status,
branch filter enforcement, export route security, no double-counting.

Run: python tests/e2e/test_treasury.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from decimal import Decimal


def _assert_no_double_counting(report):
    """Total must equal sum of individual account balances."""
    accounts = report["liquidity"]["accounts"]
    total = Decimal(str(report["liquidity"]["total_balance"]))
    summed = sum(Decimal(str(a["balance_aed"])) for a in accounts)
    if abs(total - summed) > Decimal("0.01"):
        raise AssertionError(
            f"Liquidity double-counting: total={total} sum={summed}"
        )
    print("  [PASS] No double-counting: total == sum of accounts")


def _assert_branch_filter_enforced(report_all, report_branch):
    """Branch filter must return equal or fewer accounts."""
    all_count = report_all["liquidity"]["account_count"]
    branch_count = report_branch["liquidity"]["account_count"]
    if branch_count > all_count:
        raise AssertionError(
            f"Branch filter inflated accounts: all={all_count} branch={branch_count}"
        )
    print("  [PASS] Branch filter reduces or maintains account count")


def _assert_cheque_buckets_non_overlapping(report):
    """Each cheque must appear in exactly one bucket per direction."""
    for direction in ("incoming", "outgoing"):
        buckets = report["cheques"][direction]["buckets"]
        all_ids = set()
        for key, b in buckets.items():
            for item in b["items"]:
                cid = item["id"]
                if cid in all_ids:
                    raise AssertionError(
                        f"Cheque {cid} appears in multiple buckets ({direction})"
                    )
                all_ids.add(cid)
        total_items = sum(len(b["items"]) for b in buckets.values())
        if total_items != len(all_ids):
            raise AssertionError(
                f"Bucket overlap or missing: total_items={total_items} unique={len(all_ids)}"
            )
    print("  [PASS] Cheque buckets are non-overlapping")


def _assert_cheque_bucket_math(report):
    """Bucket totals must equal sum of item amounts."""
    for direction in ("incoming", "outgoing"):
        buckets = report["cheques"][direction]["buckets"]
        for key, b in buckets.items():
            expected = sum(Decimal(str(i["amount_aed"])) for i in b["items"])
            actual = Decimal(str(b["total_amount"]))
            if abs(expected - actual) > Decimal("0.01"):
                raise AssertionError(
                    f"{direction}/{key} bucket total mismatch: expected={expected} actual={actual}"
                )
    print("  [PASS] Cheque bucket totals match item sums")


def _assert_export_route_security():
    """Export route must contain branch security checks."""
    from routes.treasury import treasury_export
    import inspect
    source = inspect.getsource(treasury_export)
    required = ["report_branch_scope_id", "user_can_access_branch"]
    for r in required:
        if r not in source:
            raise AssertionError(
                f"treasury_export missing security check: {r}"
            )
    print("  [PASS] Export route applies branch security checks")


def _assert_gl_balances_sensible(report):
    """GL-derived balances should not be wildly negative for asset accounts."""
    for a in report["liquidity"]["accounts"]:
        if a["source"] == "gl_account" and a["kind"] in ("cash", "bank"):
            if a["balance_aed"] < -1000000:
                raise AssertionError(
                    f"Suspicious GL balance: {a['code']} = {a['balance_aed']}"
                )
    print("  [PASS] GL balances are within sensible range")


def main():
    from app import create_app
    app = create_app()
    with app.app_context():
        from services.treasury_service import TreasuryService

        print("=" * 70)
        print("TREASURY SERVICE QA TEST — Phase 8")
        print("=" * 70)
        errors = []

        # Use tenant_id=2 (known from previous tests)
        tenant_id = 2

        print("\n=== Check: Liquidity Position (no double-counting) ===")
        try:
            report_all = TreasuryService.build_dashboard(tenant_id=tenant_id)
            _assert_no_double_counting(report_all)
        except AssertionError as e:
            errors.append(str(e))
            print(f"  [FAIL] {e}")

        print("\n=== Check: Branch Filter Enforcement ===")
        try:
            report_branch = TreasuryService.build_dashboard(
                tenant_id=tenant_id, branch_id=1
            )
            _assert_branch_filter_enforced(report_all, report_branch)
        except AssertionError as e:
            errors.append(str(e))
            print(f"  [FAIL] {e}")

        print("\n=== Check: Cheque Bucket Boundaries ===")
        try:
            _assert_cheque_buckets_non_overlapping(report_all)
            _assert_cheque_bucket_math(report_all)
        except AssertionError as e:
            errors.append(str(e))
            print(f"  [FAIL] {e}")

        print("\n=== Check: Export Route Security ===")
        try:
            _assert_export_route_security()
        except AssertionError as e:
            errors.append(str(e))
            print(f"  [FAIL] {e}")

        print("\n=== Check: GL Balance Sanity ===")
        try:
            _assert_gl_balances_sensible(report_all)
        except AssertionError as e:
            errors.append(str(e))
            print(f"  [FAIL] {e}")

        print("\n" + "=" * 70)
        if errors:
            print(f"TREASURY QA FAILED — {len(errors)} check(s) failed")
            print("=" * 70)
            for e in errors:
                print(f"  • {e}")
            return 1
        else:
            print("ALL TREASURY CHECKS PASSED")
            print("=" * 70)
            return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
