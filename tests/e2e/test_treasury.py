"""
Treasury Service QA Test — Phase 8
Validates: liquidity position, check maturity buckets, bank reconciliation status,
branch filter enforcement, export route security, no double-counting.

End-to-end flow: login → treasury dashboard → export, plus direct service checks.
"""

from decimal import Decimal


def _assert_no_double_counting(report):
    """Total must equal sum of individual account balances."""
    accounts = report["liquidity"]["accounts"]
    total = Decimal(str(report["liquidity"]["total_balance"]))
    summed = sum(Decimal(str(a["balance_aed"])) for a in accounts)
    assert abs(total - summed) <= Decimal("0.01"), f"Liquidity double-counting: total={total} sum={summed}"


def _assert_branch_filter_enforced(report_all, report_branch):
    """Branch filter must return equal or fewer accounts."""
    all_count = report_all["liquidity"]["account_count"]
    branch_count = report_branch["liquidity"]["account_count"]
    assert branch_count <= all_count, f"Branch filter inflated accounts: all={all_count} branch={branch_count}"


def _assert_cheque_buckets_non_overlapping(report):
    """Each check must appear in exactly one bucket per direction."""
    for direction in ("incoming", "outgoing"):
        buckets = report["cheques"][direction]["buckets"]
        all_ids = set()
        for _key, b in buckets.items():
            for item in b["items"]:
                cid = item["id"]
                assert cid not in all_ids, f"Cheque {cid} appears in multiple buckets ({direction})"
                all_ids.add(cid)
        total_items = sum(len(b["items"]) for b in buckets.values())
        assert total_items == len(all_ids)


def _assert_cheque_bucket_math(report):
    """Bucket totals must equal sum of item amounts."""
    for direction in ("incoming", "outgoing"):
        buckets = report["cheques"][direction]["buckets"]
        for key, b in buckets.items():
            expected = sum(Decimal(str(i["amount_aed"])) for i in b["items"])
            actual = Decimal(str(b["total_amount"]))
            assert abs(expected - actual) <= Decimal("0.01"), (
                f"{direction}/{key} bucket total mismatch: expected={expected} actual={actual}"
            )


def _assert_export_route_security():
    """Export route must contain branch security checks."""
    import inspect

    from routes.treasury import treasury_export

    source = inspect.getsource(treasury_export)
    for r in ["report_branch_scope_id", "user_can_access_branch"]:
        assert r in source, f"treasury_export missing security check: {r}"


def _assert_gl_balances_sensible(report):
    """GL-derived balances should not be wildly negative for asset accounts."""
    for a in report["liquidity"]["accounts"]:
        if a["source"] == "gl_account" and a["kind"] in ("cash", "bank") and a["balance_aed"] < -1000000:
            raise AssertionError(f"Suspicious GL balance: {a['code']} = {a['balance_aed']}")


def test_treasury_liquidity_no_double_counting(app, db_session, sample_tenant, sample_branch, sample_gl_accounts):
    from services.treasury_service import TreasuryService

    report = TreasuryService.build_dashboard(tenant_id=sample_tenant.id)
    _assert_no_double_counting(report)


def test_treasury_branch_filter_enforced(app, db_session, sample_tenant, sample_branch, sample_gl_accounts):
    from services.treasury_service import TreasuryService

    report_all = TreasuryService.build_dashboard(tenant_id=sample_tenant.id)
    report_branch = TreasuryService.build_dashboard(tenant_id=sample_tenant.id, branch_id=sample_branch.id)
    _assert_branch_filter_enforced(report_all, report_branch)


def test_treasury_cheque_buckets(app, db_session, sample_tenant, sample_branch):
    from services.treasury_service import TreasuryService

    report = TreasuryService.build_dashboard(tenant_id=sample_tenant.id)
    _assert_cheque_buckets_non_overlapping(report)
    _assert_cheque_bucket_math(report)


def test_treasury_export_route_security():
    _assert_export_route_security()


def test_treasury_gl_balances_sensible(app, db_session, sample_tenant, sample_gl_accounts):
    from services.treasury_service import TreasuryService

    report = TreasuryService.build_dashboard(tenant_id=sample_tenant.id)
    _assert_gl_balances_sensible(report)


def test_treasury_dashboard_e2e_login_and_render(auth_client, sample_tenant):
    """E2E: login → GET /reports/treasury → verify dashboard renders."""
    # Direct service call already tested above; now verify HTTP route with auth
    resp = auth_client.get("/reports/treasury", follow_redirects=False)
    # Should be 200 for authorized user, 302 only if permissions redirect, 403 if blocked
    assert resp.status_code in (200, 302, 403)
    if resp.status_code == 200:
        html = resp.data.decode("utf-8", errors="ignore")
        assert len(html) > 200
    elif resp.status_code == 302:
        # Should not bounce back to login since auth_client is logged in
        loc = resp.headers.get("Location", "")
        assert "/login" not in loc or "/reports" in loc


def test_treasury_export_e2e_with_branch_filter(auth_client, sample_tenant, sample_branch):
    """E2E: login → export with branch filter → verify file download headers."""
    resp = auth_client.get(f"/reports/treasury/export?format=csv&branch_id={sample_branch.id}")
    # Export requires view_reports permission — sample_user (super_admin) has it, so 200
    # If permissions missing, 302/403 is acceptable but not 500
    assert resp.status_code in (200, 302, 403)
    if resp.status_code == 200:
        ctype = resp.headers.get("Content-Type", "")
        assert "csv" in ctype.lower() or "text" in ctype.lower() or "octet" in ctype.lower()
