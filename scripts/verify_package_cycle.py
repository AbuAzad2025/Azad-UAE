"""End-to-end verification: seed packages → owner plan change → tenant sync.

Runs against the local dev DB. Mutations on the demo tenant are restored at
the end; seed_packages() is idempotent so it is left in place (it is the
intended production state).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.factory import create_app
from extensions import db
from models.package import TENANT_FLAG_COLUMNS, TENANT_LIMIT_COLUMNS, Package
from models.tenant import Tenant
from services.saas_provisioning_service import SaaSProvisioningService, seed_packages

app = create_app()

SNAPSHOT_COLS = [
    "subscription_plan",
    "subscription_plan_duration",
    "is_trial",
    *TENANT_LIMIT_COLUMNS,
    *TENANT_FLAG_COLUMNS,
    "enable_pos",
    "allow_custom_integrations",
]

with app.app_context():
    # 1) Seed (idempotent upsert)
    result = seed_packages()
    print(f"[1] seed_packages → created={result['created']} updated={result['updated']}")
    for slug in ("basic", "pro", "enterprise"):
        pkg = Package.query.filter_by(slug=slug).first()
        print(
            f"    {slug}: tier={pkg.tier_level} users={pkg.max_users} sales/mo={pkg.max_sales_per_month} payroll={pkg.enable_payroll} ai={pkg.enable_ai}"
        )

    tenant = Tenant.query.filter_by(slug="demo").first() or Tenant.query.first()
    original = {col: getattr(tenant, col) for col in SNAPSHOT_COLS}
    print(f"[2] demo tenant id={tenant.id} plan={tenant.subscription_plan} users={tenant.max_users}")

    try:
        # 3) Upgrade to pro → template must apply
        applied = SaaSProvisioningService.apply_plan_with_template(tenant, "pro", "monthly", False)
        db.session.flush()
        pro = Package.query.filter_by(slug="pro").first()
        checks = [
            ("applied", applied is True),
            ("plan=pro", tenant.subscription_plan == "pro"),
            ("max_users=pro(10)", tenant.max_users == pro.max_users),
            ("max_sales/mo=pro(3000)", tenant.max_sales_per_month == pro.max_sales_per_month),
            ("payroll=True", tenant.enable_payroll is True),
            ("ai=False", tenant.enable_ai is False),
            ("store=False", tenant.enable_store is False),
        ]
        print("[3] upgrade → pro:")
        for name, ok in checks:
            print(f"    {'PASS' if ok else 'FAIL'}  {name}")

        # 4) Manual override + same-plan re-select → override preserved
        tenant.max_users = 99
        db.session.flush()
        applied_again = SaaSProvisioningService.apply_plan_with_template(tenant, "pro", "annual", None)
        db.session.flush()
        print("[4] same-plan re-select after manual override (max_users=99):")
        print(f"    {'PASS' if applied_again is False else 'FAIL'}  applied={applied_again} (expected False)")
        print(f"    {'PASS' if tenant.max_users == 99 else 'FAIL'}  max_users preserved = {tenant.max_users}")
        print(f"    {'PASS' if tenant.subscription_plan_duration == 'annual' else 'FAIL'}  duration updated to annual")

        # 5) Downgrade to basic → limits shrink, payroll locked
        SaaSProvisioningService.apply_plan_with_template(tenant, "basic", "monthly", None)
        db.session.flush()
        basic = Package.query.filter_by(slug="basic").first()
        print("[5] downgrade → basic:")
        print(
            f"    {'PASS' if tenant.max_users == basic.max_users else 'FAIL'}  max_users={tenant.max_users} (basic={basic.max_users})"
        )
        print(f"    {'PASS' if tenant.enable_payroll is False else 'FAIL'}  payroll locked")
        print(f"    {'PASS' if tenant.max_sales_per_month == 300 else 'FAIL'}  sales/mo={tenant.max_sales_per_month}")

        # 6) Feature gate + monthly quota helpers see the downgraded tenant
        from utils.pos_features import plan_meets
        from utils.tenant_limits import get_tenant_usage_summary

        usage = {row["key"]: row for row in get_tenant_usage_summary(tenant)}
        print("[6] derived views on basic:")
        print(f"    {'PASS' if not plan_meets('basic', 'pro') else 'FAIL'}  plan_meets(basic, pro) is False (DB tier)")
        print(
            f"    INFO usage users: {usage['users']['current']}/{usage['users']['limit']} warn={usage['users']['warn']}"
        )
        print(f"    INFO usage sales/mo: {usage['sales_per_month']['current']}/{usage['sales_per_month']['limit']}")

        failed = [name for name, ok in checks if not ok]
        overall = not failed and applied_again is False and tenant.max_sales_per_month == 300
    finally:
        # 7) Restore the demo tenant exactly as found
        for col, value in original.items():
            setattr(tenant, col, value)
        db.session.commit()
        print(f"[7] demo tenant restored (plan={tenant.subscription_plan}, users={tenant.max_users})")

    print("RESULT:", "ALL GREEN ✅" if overall else "FAILURES ❌")
