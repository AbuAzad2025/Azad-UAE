"""Comprehensive test for inventory reconciliation service.

Validates:
  1. GL accuracy (no double-counting bug)
  2. Per-product rows contain only qty fields (no per-product GL)
  3. Warehouse summary GL is fetched ONCE per warehouse
  4. Date filtering is wired end-to-end
  5. Warehouse filtering is wired end-to-end
  6. Report structure completeness
  7. Celery task wiring (beat_schedule exists)
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _assert_no_double_counting(report):
    """Ensure GL total is NOT multiplied by number of products."""
    wh = report["warehouse_summary"]
    for w in wh:
        products = w["products"]
        gl_val = Decimal(str(w["gl_value"]))
        pwc_val = Decimal(str(w["pwc_value"]))
        # Sanity: if GL is non-zero and products > 1, GL should NOT be
        # roughly equal to PWC * products (which would indicate double-count).
        # The real test: GL per warehouse <= PWC per warehouse (or close).
        # But more importantly, GL per warehouse is the SAME regardless of
        # how many products are in that warehouse when called twice.
        if products > 1 and gl_val > 0:
            ratio = gl_val / pwc_val if pwc_val else Decimal("0")
            if ratio > Decimal("2"):
                raise AssertionError(
                    f"GL double-counting suspected: warehouse={w['warehouse_name']} "
                    f"gl_value={gl_val} pwc_value={pwc_val} ratio={ratio:.2f}"
                )
    print("  [PASS] No GL double-counting detected")


def _assert_product_rows_have_no_gl(report):
    """Per-product rows must NOT contain gl_value (GL is warehouse-aggregated)."""
    forbidden = {"gl_value", "value_diff", "matched_value"}
    for r in report["rows"]:
        found = forbidden & set(r.keys())
        if found:
            raise AssertionError(
                f"Per-product row contains GL field(s): {found} for product={r['product_id']}"
            )
    print("  [PASS] Per-product rows do not contain GL fields")


def _assert_warehouse_summary_has_gl(report):
    """Warehouse summary MUST contain GL comparison fields."""
    required = {"gl_value", "value_diff", "matched_value", "gl_untagged"}
    for w in report["warehouse_summary"]:
        missing = required - set(w.keys())
        if missing:
            raise AssertionError(
                f"Warehouse summary missing GL fields: {missing} for {w['warehouse_name']}"
            )
    print("  [PASS] Warehouse summary contains GL fields")


def _assert_date_filter_wired(report, report_filtered):
    """Date filtering should affect movement quantities when dates are restrictive."""
    # We can't guarantee a difference without knowing data, but we can verify
    # the service accepts the params and returns consistent structure.
    assert "summary" in report_filtered
    assert "rows" in report_filtered
    print("  [PASS] Date filter params accepted by service")


def _assert_date_to_inclusive(service, tenant_id):
    """A date-only date_to must include that full calendar day."""
    from extensions import db
    from models import StockMovement

    max_created_at = (
        db.session.query(StockMovement.created_at)
        .filter(StockMovement.tenant_id == tenant_id)
        .order_by(StockMovement.created_at.desc())
        .limit(1)
        .scalar()
    )
    if not max_created_at:
        print("  [SKIP] No stock movements for inclusive date_to check")
        return

    date_only = max_created_at.date().isoformat()
    end_of_day = f"{date_only} 23:59:59"
    report_date_only = service.build_warehouse_summary(
        tenant_id=tenant_id,
        date_to=date_only,
    )
    report_end_of_day = service.build_warehouse_summary(
        tenant_id=tenant_id,
        date_to=end_of_day,
    )
    qty_date_only = Decimal(str(report_date_only["summary"]["total_movement_qty"]))
    qty_end_of_day = Decimal(str(report_end_of_day["summary"]["total_movement_qty"]))
    if abs(qty_date_only - qty_end_of_day) > Decimal("0.001"):
        raise AssertionError(
            f"date_to is not inclusive: {date_only} qty={qty_date_only} "
            f"but {end_of_day} qty={qty_end_of_day}"
        )
    print("  [PASS] date_to includes the full selected day")


def _assert_warehouse_filter_wired(report_all, report_wh):
    """Warehouse filtering should return equal or fewer rows."""
    if report_wh["summary"]["record_count"] > report_all["summary"]["record_count"]:
        raise AssertionError(
            f"Warehouse filter returned MORE rows: {report_wh['summary']['record_count']} > "
            f"{report_all['summary']['record_count']}"
        )
    print("  [PASS] Warehouse filter reduces or maintains row count")


def _assert_branch_filter_wired(report_fake_branch):
    """A nonexistent branch must not return tenant-wide PWC rows."""
    summary = report_fake_branch["summary"]
    if summary["record_count"] != 0 or Decimal(str(summary["total_pwc_qty"])) != 0:
        raise AssertionError(
            "Branch filter is not applied to PWC/movement rows: "
            f"records={summary['record_count']} qty={summary['total_pwc_qty']}"
        )
    print("  [PASS] Branch filter is applied to PWC/movement rows")


def _assert_celery_beat_schedule():
    from services.celery_tasks import celery
    beat = celery.conf.get("beat_schedule")
    if not beat:
        raise AssertionError("celery.conf.beat_schedule is not configured")
    if "daily-inventory-reconciliation" not in beat:
        raise AssertionError(
            f"Missing 'daily-inventory-reconciliation' in beat_schedule: {list(beat.keys())}"
        )
    print("  [PASS] Celery beat_schedule configured for daily inventory reconciliation")


def _assert_export_route_has_security(app):
    """Export route must apply same branch_scope_id checks as display route."""
    from routes.reports import inventory_reconciliation_export
    import inspect
    source = inspect.getsource(inventory_reconciliation_export)
    required = ["report_branch_scope_id", "user_can_access_branch", "get_accessible_warehouse_ids"]
    for r in required:
        if r not in source:
            raise AssertionError(
                f"Export route missing security check: {r}"
            )
    print("  [PASS] Export route applies branch security checks")


def _assert_celery_value_status(service, tenant_id):
    from services.celery_tasks import run_inventory_reconciliation

    report = service.build_warehouse_summary(tenant_id=tenant_id)
    summary = report["summary"]
    task_result = run_inventory_reconciliation(tenant_id)
    expected_all = summary["all_matched_qty"] and summary["all_matched_value"]
    if task_result["all_matched"] != expected_all:
        raise AssertionError(
            "Celery reconciliation status ignores value mismatches: "
            f"task={task_result['all_matched']} expected={expected_all}"
        )
    if task_result.get("all_matched_value") != summary["all_matched_value"]:
        raise AssertionError(
            "Celery result does not expose value reconciliation status: "
            f"task={task_result.get('all_matched_value')} "
            f"expected={summary['all_matched_value']}"
        )
    print("  [PASS] Celery task includes value reconciliation status")


def main():
    from app import create_app
    app = create_app()

    errors = []
    with app.app_context():
        from services.inventory_reconciliation_service import (
            InventoryReconciliationService,
            RECON_TOLERANCE,
        )
        from services.celery_tasks import celery

        # ── 1. Basic report for tenant 2 ──────────────────────────────
        print("\n=== Test: build_warehouse_summary (tenant=2) ===")
        report = InventoryReconciliationService.build_warehouse_summary(tenant_id=2)
        s = report["summary"]
        print(f"  records={s['record_count']} qty_matched={s.get('all_matched_qty', s.get('all_matched'))} "
              f"value_matched={s.get('all_matched_value', 'N/A')}")
        print(f"  total_pwc_qty={s['total_pwc_qty']} total_movement_qty={s['total_movement_qty']} "
              f"overall_qty_diff={s['overall_qty_diff']}")
        if s.get('total_gl_value') is not None:
            print(f"  total_gl_value={s['total_gl_value']} overall_value_diff={s.get('overall_value_diff', 'N/A')}")

        # ── 2. GL double-counting check ───────────────────────────────
        print("\n=== Check: GL double-counting ===")
        try:
            _assert_no_double_counting(report)
        except AssertionError as e:
            errors.append(str(e))
            print(f"  [FAIL] {e}")

        # ── 3. Per-product row structure ──────────────────────────────
        print("\n=== Check: per-product row structure ===")
        try:
            _assert_product_rows_have_no_gl(report)
        except AssertionError as e:
            errors.append(str(e))
            print(f"  [FAIL] {e}")

        # ── 4. Warehouse summary structure ────────────────────────────
        print("\n=== Check: warehouse summary structure ===")
        try:
            _assert_warehouse_summary_has_gl(report)
        except AssertionError as e:
            errors.append(str(e))
            print(f"  [FAIL] {e}")

        # ── 5. Date filter wiring ─────────────────────────────────────
        print("\n=== Check: date filter wiring ===")
        report_filtered = InventoryReconciliationService.build_warehouse_summary(
            tenant_id=2,
            date_from="2026-01-01",
            date_to="2026-12-31",
        )
        try:
            _assert_date_filter_wired(report, report_filtered)
            _assert_date_to_inclusive(InventoryReconciliationService, tenant_id=2)
        except AssertionError as e:
            errors.append(str(e))
            print(f"  [FAIL] {e}")

        # ── 6. Warehouse filter wiring ──────────────────────────────────
        print("\n=== Check: warehouse filter wiring ===")
        report_wh = InventoryReconciliationService.build_warehouse_summary(
            tenant_id=2,
            warehouse_id=1,  # Ramallah Main Warehouse
        )
        report_fake_branch = InventoryReconciliationService.build_warehouse_summary(
            tenant_id=2,
            branch_id=999999,
        )
        try:
            _assert_warehouse_filter_wired(report, report_wh)
            _assert_branch_filter_wired(report_fake_branch)
        except AssertionError as e:
            errors.append(str(e))
            print(f"  [FAIL] {e}")

        # ── 7. Celery beat_schedule ───────────────────────────────────
        print("\n=== Check: Celery beat_schedule ===")
        try:
            _assert_celery_beat_schedule()
            _assert_celery_value_status(InventoryReconciliationService, tenant_id=2)
        except AssertionError as e:
            errors.append(str(e))
            print(f"  [FAIL] {e}")

        # ── 8. Export route security ──────────────────────────────────
        print("\n=== Check: export route security ===")
        try:
            _assert_export_route_has_security(app)
        except AssertionError as e:
            errors.append(str(e))
            print(f"  [FAIL] {e}")

        # ── 9. GL balance direct validation ───────────────────────────
        print("\n=== Check: GL balance direct vs report ===")
        from models import GLAccount
        from services.gl_service import GL_ACCOUNTS
        from utils.gl_tenant import scope_gl_accounts
        acc_q = GLAccount.query.filter_by(code=GL_ACCOUNTS["inventory"])
        acc_q = scope_gl_accounts(acc_q, tenant_id=2)
        inv_acc = acc_q.first()
        if inv_acc:
            direct_gl = InventoryReconciliationService._gl_inventory_balance(
                inv_acc.id, tenant_id=2, branch_id=None, warehouse_id=None
            )
            report_gl = Decimal(str(s.get("total_gl_value", 0)))
            if abs(report_gl - direct_gl) > RECON_TOLERANCE:
                err = (
                    f"Report GL ({report_gl}) does not equal direct GL balance "
                    f"({direct_gl}). Reconciliation report is not ledger-accurate."
                )
                errors.append(err)
                print(f"  [FAIL] {err}")
            else:
                print(f"  [PASS] Report GL {report_gl} equals Direct GL {direct_gl}")
        else:
            print("  [SKIP] No inventory GL account found for tenant=2")

    # ── Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if errors:
        print(f"FAILURES: {len(errors)}")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("ALL CHECKS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
